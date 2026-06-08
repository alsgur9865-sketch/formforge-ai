# 파일 위치: agents/debate.py
"""
Multi-round Adversarial Debate Loop — Day 8 Task 8.1.

목적:
  Encourager 와 Scrutinizer 가 같은 pose_data 에 대해 최대 N 라운드 토론하다가
  합의(convergence)가 감지되면 즉시 종료, 그렇지 않으면 다음 라운드.

흐름:
  Round 1: orchestrator.run_round1 사용 (ParallelAgent, 두 에이전트 독립 첫 인상)
  ├─ judge_convergence → converged 이면 종료
  ├─ converged=False 이면 Round 2 진행
  │   - 각 에이전트가 직전 라운드 상대 argument 를 입력으로 받음
  │   - addresses_encourager / addresses_scrutinizer 필드에 cross-reference 응답
  ├─ judge_convergence → 반복
  └─ MAX_DEBATE_ROUNDS 도달 시 강제 종료 (converged=False 상태 유지)

설계 결정:
  - Round N>=2 도 ParallelAgent 패턴 유지 (각 라운드 안에서는 두 에이전트가 동시).
    상대 직전 argument 는 user message 에 JSON payload 로 전달.
  - 라운드별로 별도 Runner 호출 → Phoenix trace 가 라운드별로 분리됨
    (acceptance: "라운드별 메시지가 Phoenix trace에 명확히 구분됨")
  - 합의 감지는 evals.convergence_judge 의 별도 LLM 호출 → 별도 span
    (acceptance: "합의 판정 LLM call도 trace에 별도 span으로 기록")

⚠️ ADK ParallelAgent deprecation: orchestrator.py 의 메모와 동일.
   Workflow API 전환은 Phoenix trace 그룹 구조 재검증 필요. Day 8 진행 중 이슈
   안 생겼으니 이대로 가고, Day 10 시점에 한 번에 전환 검토.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from google.adk.agents import ParallelAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.encourager import create_encourager_agent
from agents.scrutinizer import create_scrutinizer_agent
from agents.orchestrator import _resolve_persona_state, _safe_parse_json
from evals.convergence_judge import (
    ConvergenceVerdict,
    judge_convergence,
)
from storage import firestore_client


# ---------------------------------------------------------------------------
# 결과 데이터클래스
# ---------------------------------------------------------------------------

@dataclass
class DebateRound:
    """한 라운드의 결과."""
    round_number: int
    encourager: dict[str, Any] | None
    scrutinizer: dict[str, Any] | None
    encourager_raw: str | None
    scrutinizer_raw: str | None
    round_latency_seconds: float
    verdict: ConvergenceVerdict | None = None
    verdict_latency_seconds: float = 0.0


@dataclass
class DebateResult:
    """전체 토론 결과."""
    rounds: list[DebateRound] = field(default_factory=list)
    converged: bool = False
    converged_at_round: int | None = None
    shared_issue: str | None = None
    total_latency_seconds: float = 0.0
    forced_stop_reason: str | None = None  # "max_rounds_reached" 등

    @property
    def last_round(self) -> DebateRound | None:
        return self.rounds[-1] if self.rounds else None

    def as_dict(self) -> dict[str, Any]:
        return {
            "rounds": [
                {
                    "round": r.round_number,
                    "encourager": r.encourager,
                    "scrutinizer": r.scrutinizer,
                    "verdict": r.verdict.as_dict() if r.verdict else None,
                    "round_latency_seconds": r.round_latency_seconds,
                }
                for r in self.rounds
            ],
            "converged": self.converged,
            "converged_at_round": self.converged_at_round,
            "shared_issue": self.shared_issue,
            "total_latency_seconds": self.total_latency_seconds,
            "forced_stop_reason": self.forced_stop_reason,
        }


# ---------------------------------------------------------------------------
# 라운드 단위 ParallelAgent 호출
# ---------------------------------------------------------------------------

APP_NAME = "formforge-debate"


def _build_round_pipeline(round_number: int, persona_state: dict[str, Any]) -> ParallelAgent:
    """매 라운드마다 새 ParallelAgent 인스턴스. 페르소나는 round 진입 시점 기준 고정.

    Phoenix trace 그룹 충돌 방지를 위해 name 에 라운드 번호 포함.
    """
    enc = persona_state.get("encourager", {})
    scr = persona_state.get("scrutinizer", {})
    encourager = create_encourager_agent(
        warmth=enc.get("warmth", 0.7),
        detail=enc.get("detail", 0.6),
    )
    scrutinizer = create_scrutinizer_agent(
        harshness=scr.get("harshness", 0.7),
        detail=scr.get("detail", 0.8),
    )
    return ParallelAgent(
        name=f"formforge_debate_round_{round_number}",
        description=f"FormForge debate round {round_number} (parallel encourager + scrutinizer)",
        sub_agents=[encourager, scrutinizer],
    )


async def _run_one_round(
    round_number: int,
    pipeline: ParallelAgent,
    payload: dict[str, Any],
    user_id: str,
) -> DebateRound:
    """라운드 1회 실행 → 두 에이전트 응답을 author 로 매칭."""
    session_service = InMemorySessionService()
    session_id = f"debate_r{round_number}_{uuid.uuid4().hex[:8]}"
    await session_service.create_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    runner = Runner(
        agent=pipeline,
        app_name=APP_NAME,
        session_service=session_service,
    )

    user_msg = types.Content(
        role="user",
        parts=[types.Part(text=json.dumps(payload, ensure_ascii=False))],
    )

    encourager_text: str | None = None
    scrutinizer_text: str | None = None

    start = time.monotonic()
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=user_msg
    ):
        if not (event.is_final_response() and event.content and event.content.parts):
            continue
        text = "".join(p.text or "" for p in event.content.parts)
        author = getattr(event, "author", None)
        if author == "encourager":
            encourager_text = text
        elif author == "scrutinizer":
            scrutinizer_text = text
    latency = time.monotonic() - start

    return DebateRound(
        round_number=round_number,
        encourager=_safe_parse_json(encourager_text),
        scrutinizer=_safe_parse_json(scrutinizer_text),
        encourager_raw=encourager_text,
        scrutinizer_raw=scrutinizer_text,
        round_latency_seconds=latency,
    )


# ---------------------------------------------------------------------------
# 메인 디베이트 루프
# ---------------------------------------------------------------------------

def _max_debate_rounds() -> int:
    """env 의 MAX_DEBATE_ROUNDS 또는 기본 3."""
    try:
        return max(1, int(os.getenv("MAX_DEBATE_ROUNDS", "3")))
    except ValueError:
        return 3


def _short(text: str | None, limit: int = 280) -> str:
    if not text:
        return ""
    return text if len(text) <= limit else text[:limit] + "..."


def _build_encourager_brief(encourager_output: dict[str, Any] | None) -> str | None:
    """
    다음 라운드 Scrutinizer 가 받을 Encourager 직전 라운드 brief.

    페르소나가 cross-reference 응답 (`addresses_encourager`) 하기에 충분한
    핵심 필드만 묶은 JSON 문자열. 파싱 실패(None)면 None 그대로 반환해
    페르소나 spec ("null in round 1") 과 일치하도록 처리.
    """
    if not encourager_output:
        return None
    brief = {
        "praise": encourager_output.get("praise"),
        "concern_one": encourager_output.get("concern_one"),
        "actionable_tip": encourager_output.get("actionable_tip"),
        "addresses_scrutinizer": encourager_output.get("addresses_scrutinizer"),
    }
    # None 키 제거
    brief = {k: v for k, v in brief.items() if v}
    return json.dumps(brief, ensure_ascii=False) if brief else None


def _build_scrutinizer_brief(scrutinizer_output: dict[str, Any] | None) -> str | None:
    """
    다음 라운드 Encourager 가 받을 Scrutinizer 직전 라운드 brief.

    primary_risk 전체(name/severity/mechanism/evidence) + required_action +
    addresses_encourager 포함 — 페르소나가 받아치기 위한 구체적 근거 제공.
    """
    if not scrutinizer_output:
        return None
    pr = scrutinizer_output.get("primary_risk") or {}
    brief = {
        "primary_risk": {
            "name": pr.get("name"),
            "severity": pr.get("severity"),
            "mechanism": pr.get("mechanism"),
            "evidence_in_data": pr.get("evidence_in_data"),
        },
        "required_action": scrutinizer_output.get("required_action"),
        "addresses_encourager": scrutinizer_output.get("addresses_encourager"),
    }
    # primary_risk 안의 None 제거
    brief["primary_risk"] = {k: v for k, v in brief["primary_risk"].items() if v}
    if not brief["primary_risk"]:
        brief.pop("primary_risk")
    brief = {k: v for k, v in brief.items() if v}
    return json.dumps(brief, ensure_ascii=False) if brief else None


async def run_debate(
    pose_data: dict[str, Any],
    user_context: dict[str, Any],
    persona_state: dict[str, Any] | None = None,
    user_id: str | None = None,
    max_rounds: int | None = None,
    debate_id: str | None = None,
    video_uri: str | None = None,
    exercise_type: str | None = None,
) -> DebateResult:
    """
    Multi-round adversarial debate.

    Args:
        pose_data: PoseExtractor 출력 (현재는 caller 제공)
        user_context: { user_id, injury_history, ... }
        persona_state: 우선순위는 orchestrator._resolve_persona_state 와 동일
        user_id: ADK 세션 식별자. None 이면 user_context["user_id"] → "anonymous"
        max_rounds: None 이면 env MAX_DEBATE_ROUNDS (기본 3)
        debate_id: 제공되면 Firestore `debates/{debate_id}` 에 라운드별 push (Task 8.2).
                   None 이면 Firestore 미연동 (테스트·dry run 용).
        video_uri: Firestore 저장용 비디오 URI. debate_id 와 함께 제공 필요.
        exercise_type: 미제공 시 pose_data.exercise_type 사용.

    Returns:
        DebateResult — 라운드 list + 합의 여부 + 총 latency.
    """
    persona_state = _resolve_persona_state(persona_state, user_context)
    user_id = user_id or (user_context.get("user_id") if isinstance(user_context, dict) else None) or "anonymous"
    max_rounds = max_rounds or _max_debate_rounds()

    # Firestore 연동: debate_id 제공된 경우만 활성.
    # 초기 셋업이 실패하면 Firestore 미연동 모드로 강등 (토론 자체는 진행) — 진짜 fail-soft.
    # Firestore 장애가 코어 토론 흐름을 차단하지 않음. 라운드별 push 도 fail-soft 유지.
    firestore_enabled = bool(debate_id)
    if firestore_enabled:
        exercise_type = exercise_type or pose_data.get("exercise_type", "unknown")
        try:
            firestore_client.create_debate(
                debate_id=debate_id,
                user_id=user_id,
                video_uri=video_uri or "",
                exercise_type=exercise_type,
            )
            firestore_client.set_debate_pose_data(debate_id, pose_data)
            firestore_client.update_debate_status(debate_id, "debating")
        except Exception as e:
            print(
                f"⚠️  Firestore 초기 셋업 실패 — Firestore 미연동 모드로 강등 "
                f"(토론은 그대로 진행): {type(e).__name__}: {e}"
            )
            firestore_enabled = False

    result = DebateResult()
    total_start = time.monotonic()

    # Round 별 직전 argument 캐시
    prev_encourager_arg: str | None = None
    prev_scrutinizer_arg: str | None = None

    for round_n in range(1, max_rounds + 1):
        # 라운드 페이로드
        payload = {
            "pose_data": pose_data,
            "user_context": {**user_context, "persona_state": persona_state},
            "debate_round": round_n,
            "scrutinizer_previous_argument": prev_scrutinizer_arg,
            "encourager_previous_argument": prev_encourager_arg,
        }

        pipeline = _build_round_pipeline(round_n, persona_state)
        round_result = await _run_one_round(
            round_number=round_n,
            pipeline=pipeline,
            payload=payload,
            user_id=user_id,
        )

        # 합의 감지 — Round 1 은 스킵(조기합의 방지: 두 코치가 같은 결함을 봐도 최소
        # 2 라운드는 부딪히게). Round 2+ 부터, 둘 중 하나라도 파싱 실패면 스킵.
        verdict: ConvergenceVerdict | None = None
        verdict_latency = 0.0
        enc_concern = (round_result.encourager or {}).get("concern_one")
        scr_risk = ((round_result.scrutinizer or {}).get("primary_risk") or {}).get("name")
        if round_n >= 2 and enc_concern and scr_risk:
            try:
                verdict, verdict_latency = await judge_convergence(
                    encourager_concern=_short(enc_concern),
                    scrutinizer_risk_name=_short(scr_risk),
                )
            except Exception as e:
                # 합의 감지 실패는 fail-soft — 다음 라운드 진행
                verdict = ConvergenceVerdict(
                    converged=False,
                    shared_issue=None,
                    reason=f"judge_convergence failed: {type(e).__name__}: {e}",
                )

        round_result.verdict = verdict
        round_result.verdict_latency_seconds = verdict_latency
        result.rounds.append(round_result)

        # Firestore 라운드 push — Task 8.2 acceptance:
        # "라운드 1 끝 → rounds[0] 즉시 생성, 라운드 2 끝 → rounds[1] 추가"
        # append_debate_round 가 ArrayUnion + updated_at 갱신 동시 수행.
        if firestore_enabled:
            round_doc = {
                "round": round_n,
                "encourager": round_result.encourager,
                "scrutinizer": round_result.scrutinizer,
                "verdict": verdict.as_dict() if verdict else None,
                "round_latency_seconds": round_result.round_latency_seconds,
            }
            try:
                firestore_client.append_debate_round(debate_id, round_doc)
            except Exception as e:
                # fail-soft — 토론 자체는 계속. Firestore 장애 시 디버깅 단서만 출력.
                print(
                    f"⚠️  Firestore append_debate_round 실패 (round {round_n}): "
                    f"{type(e).__name__}: {e}"
                )

        # 합의 도달 시 즉시 종료
        if verdict and verdict.converged:
            result.converged = True
            result.converged_at_round = round_n
            result.shared_issue = verdict.shared_issue
            break

        # 다음 라운드 준비 — Round 2+ cross-reference 컨텍스트 풍부화 (Critical #1):
        # concern_one / primary_risk.name 한 문장만 보내면 페르소나가 받을 컨텍스트 부족.
        # 대신 핵심 필드를 묶은 compact dict 를 JSON 문자열로 전달.
        # 페르소나 spec 의 "null in round 1" 일치를 위해 파싱 실패 시 None 유지.
        prev_encourager_arg = _build_encourager_brief(round_result.encourager)
        prev_scrutinizer_arg = _build_scrutinizer_brief(round_result.scrutinizer)

    if not result.converged:
        result.forced_stop_reason = "max_rounds_reached"

    result.total_latency_seconds = time.monotonic() - total_start

    # 종료 status 업데이트 — Mediator 단계로 진입 신호 (Day 9 Task 9.1 에서 활용)
    if firestore_enabled:
        end_status = "feedback_pending" if result.converged else "done"
        try:
            firestore_client.update_debate_status(debate_id, end_status)
        except Exception as e:
            print(f"⚠️  Firestore update_debate_status 실패: {type(e).__name__}: {e}")

    return result


# ---------------------------------------------------------------------------
# CLI (sample_pose_data 로 데모)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from pathlib import Path
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    sample = Path(__file__).resolve().parent.parent / "tests" / "sample_pose_data.json"
    with sample.open(encoding="utf-8") as f:
        pose = json.load(f)

    res = asyncio.run(
        run_debate(
            pose_data=pose,
            user_context={
                "user_id": "demo_user",
                "injury_history": ["lower_back_strain_2025"],
                "experience_level": "intermediate",
            },
        )
    )

    print(f"\n총 {len(res.rounds)} 라운드 진행, 총 {res.total_latency_seconds:.1f}s")
    if res.converged:
        print(f"✅ 합의 도달 (Round {res.converged_at_round})")
        print(f"   공통 issue: {res.shared_issue}")
    else:
        print(f"⚠️ 강제 종료: {res.forced_stop_reason}")

    for r in res.rounds:
        print(f"\n=== Round {r.round_number} ({r.round_latency_seconds:.1f}s) ===")
        if r.encourager:
            print(f"  📣 Encourager.concern_one: {_short(r.encourager.get('concern_one'), 100)}")
            print(f"  📣 addresses_scrutinizer : {_short(r.encourager.get('addresses_scrutinizer'), 100)}")
        if r.scrutinizer:
            pr = r.scrutinizer.get("primary_risk", {})
            print(f"  🔬 primary_risk.name     : {_short(pr.get('name'), 100)} (sev={pr.get('severity')})")
            print(f"  🔬 addresses_encourager  : {_short(r.scrutinizer.get('addresses_encourager'), 100)}")
        if r.verdict:
            print(f"  ⚖️  verdict: converged={r.verdict.converged}, shared_issue={r.verdict.shared_issue}")
    sys.exit(0)
