# 파일 위치: agents/orchestrator.py
"""
FormForge 토론 오케스트레이터 — Day 3 Task 4.1 (부분 구현 — Round 1만).

목적:
  같은 pose_data 를 Encourager 와 Scrutinizer 에 동시에 던져
  두 에이전트의 독립적 첫 인상(Round 1)을 한 번의 invocation 으로 받기.

확장 로드맵:
  - Day 5  : PoseExtractor Stage 2 추가 (지금은 caller 가 pose_data 직접 제공)
  - Day 8  : Round 2+ 도입 — 각 에이전트가 상대 직전 argument 를 보고 반박
            (이 시점부터는 SequentialAgent + 합의 감지로 전환)
  - Day 8  : Mediator 추가 — 두 입장 통합

설계 결정:
  - **ParallelAgent** 사용 → Round 1 은 두 에이전트가 서로의 응답을 보지 않고
    동시에 같은 pose_data 에 대한 첫 인상을 만드는 단계. 의미상 병렬이 맞고,
    실측 latency 도 절반(48s → 26s). Day 8 Round 2+ 에선 SequentialAgent
    또는 커스텀 debate loop 로 전환.
  - Phoenix trace 에서 1개 parent + 2개 child span 으로 자동 그룹화.
  - 응답 구별: Runner 가 yield 하는 event 의 `event.author` 가 agent name 과 매칭
    (ADK base_agent.py 의 `author=self.name` 패턴에 의존).

⚠️ ADK Deprecation 경고:
  현 ADK 버전에서 `ParallelAgent` 는 `@deprecated` 데코레이터가 붙어 있음
  (`google.adk.agents.parallel_agent.py`). 메시지: "ParallelAgent is deprecated
  and will be removed in future versions. Please use Workflow instead."
  Day 8 에서 Round 2+ 도입 + Workflow API 마이그레이션 시:
    1) event.author 매칭 로직이 Workflow event 구조에서도 동작하는지 재검증 필요
    2) is_final_response() + output_schema 의 streaming 이벤트 동작 재검증
    3) Phoenix trace 그룹 구조가 동일하게 parent + child 인지 확인
  지금 당장 교체하지 않는 이유: Round 1 만 검증된 상태에서 API 전환은 위험.
  Day 8 토론 로직 작성 시 자연스럽게 Workflow 전환을 함께 진행.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any

from google.adk.agents import ParallelAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.encourager import create_encourager_agent
from agents.scrutinizer import create_scrutinizer_agent


PIPELINE_NAME = "formforge_round1_pipeline"
APP_NAME = "formforge-orchestrator"


# ---------------------------------------------------------------------------
# 결과 데이터클래스
# ---------------------------------------------------------------------------

@dataclass
class Round1Result:
    """Round 1 파이프라인 실행 결과."""
    encourager: dict[str, Any] | None
    scrutinizer: dict[str, Any] | None
    encourager_raw_text: str | None
    scrutinizer_raw_text: str | None
    latency_seconds: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "encourager": self.encourager,
            "scrutinizer": self.scrutinizer,
            "latency_seconds": self.latency_seconds,
        }


# ---------------------------------------------------------------------------
# 파이프라인 빌더
# ---------------------------------------------------------------------------

def build_round1_pipeline(
    encourager_warmth: float = 0.7,
    encourager_detail: float = 0.6,
    scrutinizer_harshness: float = 0.7,
    scrutinizer_detail: float = 0.8,
) -> ParallelAgent:
    """
    Encourager 와 Scrutinizer 를 동시 실행하는 ParallelAgent 생성.

    persona 파라미터는 사용자별 persona_state 에서 가져와 주입.
    """
    encourager = create_encourager_agent(
        warmth=encourager_warmth,
        detail=encourager_detail,
    )
    scrutinizer = create_scrutinizer_agent(
        harshness=scrutinizer_harshness,
        detail=scrutinizer_detail,
    )

    return ParallelAgent(
        name=PIPELINE_NAME,
        description=(
            "FormForge Round 1 — Encourager 와 Scrutinizer 가 같은 pose_data 에 대해 "
            "각자의 페르소나로 동시(독립) 첫 인상 응답을 생성."
        ),
        sub_agents=[encourager, scrutinizer],
    )


# ---------------------------------------------------------------------------
# 실행 함수
# ---------------------------------------------------------------------------

async def run_round1(
    pose_data: dict[str, Any],
    user_context: dict[str, Any],
    persona_state: dict[str, Any] | None = None,
    user_id: str = "anonymous",
    session_id: str | None = None,
) -> Round1Result:
    """
    Round 1 파이프라인 실행.

    Args:
        pose_data: PoseExtractor 출력 (현재는 caller 가 직접 제공)
        user_context: { user_id, injury_history, experience_level, persona_state? ... }
                      Firestore 에서 꺼낸 user 문서가 `persona_state` 를 이미 포함하면
                      그것이 자동 사용됨 (아래 우선순위 참조).
        persona_state: { encourager: {warmth, detail}, scrutinizer: {harshness, detail} }
                       None 이면 기본값 (warmth=0.7, harshness=0.7).
        user_id: ADK 세션 식별자
        session_id: 재사용 가능한 세션 id. None 이면 timestamp 기반 생성.

    persona_state 우선순위 (Important #3 가드):
        1) 명시적으로 전달된 `persona_state` 인자
        2) `user_context["persona_state"]` (Firestore 직접 사용 패턴)
        3) 빈 dict → builder 가 기본값(warmth=0.7 등) 사용
        Firestore 에서 user 문서 꺼낸 결과를 user_context 로 그대로 넘겨도
        persona_state 가 조용히 빈 dict 로 덮어써지지 않는다.

    Returns:
        Round1Result — 두 에이전트의 파싱된 JSON 응답 + 원본 텍스트 + 총 소요 시간.
    """
    # ---- persona_state 결정 (Important #3 가드) ----
    persona_state = _resolve_persona_state(persona_state, user_context)
    enc = persona_state.get("encourager", {})
    scr = persona_state.get("scrutinizer", {})

    pipeline = build_round1_pipeline(
        encourager_warmth=enc.get("warmth", 0.7),
        encourager_detail=enc.get("detail", 0.6),
        scrutinizer_harshness=scr.get("harshness", 0.7),
        scrutinizer_detail=scr.get("detail", 0.8),
    )

    # ---- 입력 페이로드 (두 에이전트가 똑같이 받는다) ----
    # user_context 에 persona_state 가 이미 있어도 위에서 결정된 값으로 통일.
    payload = {
        "pose_data": pose_data,
        "user_context": {**user_context, "persona_state": persona_state},
        "debate_round": 1,
        # Round 1 은 상대의 직전 argument 가 없음
        "encourager_previous_argument": None,
        "scrutinizer_previous_argument": None,
    }
    user_msg = types.Content(
        role="user",
        parts=[types.Part(text=json.dumps(payload, ensure_ascii=False))],
    )

    # ---- ADK Runner 셋업 ----
    session_service = InMemorySessionService()
    session_id = session_id or f"round1_{int(time.time() * 1000)}"
    await session_service.create_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )

    runner = Runner(
        agent=pipeline,
        app_name=APP_NAME,
        session_service=session_service,
    )

    # ---- 실행 + event 수집 ----
    encourager_text: str | None = None
    scrutinizer_text: str | None = None

    start = time.monotonic()
    async for event in runner.run_async(
        user_id=user_id,
        session_id=session_id,
        new_message=user_msg,
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

    # ---- JSON 파싱 (output_schema 가 강제하지만 방어적으로 try) ----
    return Round1Result(
        encourager=_safe_parse_json(encourager_text),
        scrutinizer=_safe_parse_json(scrutinizer_text),
        encourager_raw_text=encourager_text,
        scrutinizer_raw_text=scrutinizer_text,
        latency_seconds=latency,
    )


def _resolve_persona_state(
    explicit: dict[str, Any] | None,
    user_context: dict[str, Any],
) -> dict[str, Any]:
    """
    persona_state 우선순위 해결 (Important #3 가드).

      1) explicit 인자가 None 이 아니면 그것을 사용
      2) user_context["persona_state"] 가 있으면 그것을 사용
      3) 빈 dict → 호출 측 builder 가 기본값 사용

    `isinstance(..., dict)` 가드로 None/리스트 등 잘못된 타입은 빈 dict 로 대체.
    """
    if explicit is not None:
        return explicit if isinstance(explicit, dict) else {}
    from_context = user_context.get("persona_state") if isinstance(user_context, dict) else None
    if isinstance(from_context, dict):
        return from_context
    return {}


def _safe_parse_json(text: str | None) -> dict[str, Any] | None:
    """ADK output_schema 가 JSON 강제하지만, 모델이 가끔 markdown fence 를 붙이는 경우 방어."""
    if not text:
        return None
    text = text.strip()
    # ```json ... ``` 펜스 제거
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline > 0:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# CLI 데모 (옵션)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from pathlib import Path

    sample_path = Path(__file__).resolve().parent.parent / "tests" / "sample_pose_data.json"
    if not sample_path.exists():
        print(f"❌ sample_pose_data.json 없음: {sample_path}", file=sys.stderr)
        sys.exit(1)

    with sample_path.open(encoding="utf-8") as f:
        sample_pose = json.load(f)

    result = asyncio.run(
        run_round1(
            pose_data=sample_pose,
            user_context={
                "user_id": "demo_user",
                "injury_history": ["lower_back_strain_2025"],
                "experience_level": "intermediate",
            },
        )
    )

    print(f"\n⏱  Latency: {result.latency_seconds:.1f}s")
    print("\n📣 ENCOURAGER:")
    print(json.dumps(result.encourager, ensure_ascii=False, indent=2))
    print("\n🔬 SCRUTINIZER:")
    print(json.dumps(result.scrutinizer, ensure_ascii=False, indent=2))
