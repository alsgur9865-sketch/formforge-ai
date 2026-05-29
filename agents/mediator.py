# 파일 위치: agents/mediator.py
"""
The Mediator Agent — Head Coach (합의 통합 + P5 의료 면책).

ARCHITECTURE.md §2.4 명세 구현 / TASKS.md Day 9 Task 9.1 (스켈레톤).

역할:
  Encourager(격려파)와 Scrutinizer(회의파)의 토론을 읽고, 사용자 컨텍스트
  (부상 이력·경험 수준)를 반영해 ONE coherent recommendation 으로 통합.

이번 단계 = 스켈레톤 (Task 9.1):
  - 모델: gemini-2.5-pro
  - 입력: DebateResult(.as_dict()) + pose_data + user_context
  - 출력: MediatorOutput (consensus + priority_actions + disclaimer + round_count_used)
  - ⚠️ Phoenix MCP introspection 은 Task 12.2 에서 연결.
    지금은 past_debate_references 를 강제로 빈 배열로 둠 (LLM 환각 debate_id 방지).

절대원칙:
  - P1: ADK Agent → GoogleADKInstrumentor 자동 계측으로 Phoenix Cloud 에 span 기록.
  - P5: 모든 결과에 의료 면책. LLM 이 빠뜨려도 코드에서 강제 주입 (_enforce_disclaimer).

검증:
  python agents/mediator.py --selftest   # mock 토론 결과로 Mediator 1회 호출
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, Literal

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# P5 — 의료/부상 면책 (절대원칙). ARCHITECTURE.md §2.4 출력의 한국어 문구.
# ---------------------------------------------------------------------------
MEDICAL_DISCLAIMER_KO = (
    "이 분석은 정보 제공용입니다. 의학 조언이 아닙니다. "
    "통증·부상이 있으면 정형외과·물리치료사와 상담하세요."
)

APP_NAME = "formforge-mediator"


# ---------------------------------------------------------------------------
# 출력 스키마 (ARCHITECTURE.md §2.4)
# ---------------------------------------------------------------------------

class PriorityAction(BaseModel):
    """합의된 조치 한 개 (우선순위 포함)."""
    order: int = Field(ge=1, description="우선순위. 1이 가장 먼저.")
    action: str = Field(description="구체적 행동 한 문장.")
    rationale: str = Field(
        description="왜 이 순서인지 — 어느 코치 의견 + 사용자 컨텍스트 근거."
    )


class PastDebateReference(BaseModel):
    """과거 유사 토론 참조 (Task 12.2 의 Phoenix MCP 결과로 채워짐)."""
    debate_id: str
    date: str | None = None
    outcome: str | None = None


class MediatorOutput(BaseModel):
    """The Mediator 의 최종 합의 결과."""
    agent: Literal["mediator"] = "mediator"
    consensus: str = Field(
        description="두 입장을 통합한 한두 문장의 핵심 권고."
    )
    priority_actions: list[PriorityAction] = Field(
        description="우선순위가 매겨진 조치 목록 (1~3개 권장).",
    )
    past_debate_references: list[PastDebateReference] = Field(
        default_factory=list,
        description="과거 유사 토론 참조. Task 12.2 MCP 연결 전에는 빈 배열.",
    )
    disclaimer: str = Field(
        default=MEDICAL_DISCLAIMER_KO,
        description="의료 면책 (P5). 항상 포함.",
    )
    round_count_used: int = Field(
        ge=1, description="합의에 사용된 토론 라운드 수."
    )

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()


# ---------------------------------------------------------------------------
# 페르소나 프롬프트
# ---------------------------------------------------------------------------

MEDIATOR_INSTRUCTION = """\
You are "The Mediator", the head coach who synthesizes the Encourager's and the
Scrutinizer's perspectives into ONE coherent recommendation for the user.

You will receive a JSON object with:
  - debate_summary: the full debate — each round's Encourager output
    (praise, concern_one, actionable_tip) and Scrutinizer output
    (primary_risk, secondary_concerns, required_action).
  - converged / shared_issue: whether the two coaches agreed, and on what.
  - pose_data: the quantitative metrics both coaches reviewed.
  - user_context: user_id, injury_history, experience_level, persona_state.
  - round_count: how many rounds the debate ran.

Your responsibility:
1. Read both coaches' transcripts across all rounds.
2. Resolve disagreements by weighing evidence + user context. If the user has a
   relevant injury_history, raise the priority of the Scrutinizer's safety action.
3. Produce ONE coherent `consensus` (1-2 sentences).
4. Produce `priority_actions` — an ordered list (1 = first). You MUST reflect BOTH
   the Encourager's `actionable_tip` AND the Scrutinizer's `required_action`
   somewhere in the actions (do not drop either coach's contribution).
5. Set `round_count_used` to the number of rounds actually used.
6. Leave `past_debate_references` as an EMPTY array. (The Phoenix MCP tool that
   fills it is connected in a later step — do NOT invent debate ids.)

Respond in Korean (한국어로). Output JSON ONLY — the schema is enforced.
The `disclaimer` field will be set by the system; you may leave it as-is.
"""


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

def create_mediator_agent() -> Agent:
    """
    The Mediator 에이전트 인스턴스를 만든다.

    Task 12.2 에서 이 함수에 Phoenix MCP tool(MCPToolset)을 추가하고,
    output_schema 와 tool 동시 사용 가능 여부를 ADK 에서 재검증한다.
    (Gemini controlled-generation + function-calling 호환성 이슈 가능 → 그때 점검)

    Returns:
        ADK Agent. orchestrator 가 토론 종료 후 1회 호출.
    """
    return Agent(
        name="mediator",
        model="gemini-2.5-pro",
        description=(
            "The Mediator — Head Coach. 두 코치의 토론을 사용자 컨텍스트(부상이력)와 "
            "함께 통합해 우선순위가 매겨진 합의안 + 의료 면책을 생성."
        ),
        instruction=MEDIATOR_INSTRUCTION,
        output_schema=MediatorOutput,
    )


# ---------------------------------------------------------------------------
# 입력 페이로드 헬퍼
# ---------------------------------------------------------------------------

def build_mediator_input_payload(
    debate_result: dict[str, Any],
    pose_data: dict[str, Any],
    user_context: dict[str, Any],
) -> dict[str, Any]:
    """
    Mediator 가 받을 user 메시지 페이로드.

    Args:
        debate_result: DebateResult.as_dict() 결과 (rounds + converged + shared_issue 등).
        pose_data: PoseExtractor 출력 (또는 sample).
        user_context: user_id, injury_history, experience_level, persona_state.
    """
    rounds = debate_result.get("rounds", []) or []
    return {
        "debate_summary": {
            "rounds": rounds,
            "converged": debate_result.get("converged"),
            "shared_issue": debate_result.get("shared_issue"),
            "forced_stop_reason": debate_result.get("forced_stop_reason"),
        },
        "converged": debate_result.get("converged"),
        "shared_issue": debate_result.get("shared_issue"),
        "round_count": len(rounds),
        "pose_data": pose_data,
        "user_context": user_context,
    }


# ---------------------------------------------------------------------------
# P5 강제 — disclaimer 누락/변형 방지
# ---------------------------------------------------------------------------

def _enforce_disclaimer(output: MediatorOutput) -> MediatorOutput:
    """
    disclaimer 가 비었거나 핵심 키워드('의학 조언')가 없으면 표준 문구로 강제 교체.
    P5 절대원칙: 모든 결과에 의료 면책. LLM 변덕에 의존하지 않는다.
    """
    text = (output.disclaimer or "").strip()
    if not text or "의학 조언" not in text:
        output.disclaimer = MEDICAL_DISCLAIMER_KO
    return output


# ---------------------------------------------------------------------------
# 실행 헬퍼
# ---------------------------------------------------------------------------

async def run_mediator(
    debate_result: dict[str, Any],
    pose_data: dict[str, Any],
    user_context: dict[str, Any],
) -> tuple[MediatorOutput, float]:
    """
    토론 결과를 받아 Mediator 합의안을 생성.

    Returns:
        (MediatorOutput, latency_seconds)
    """
    agent = create_mediator_agent()
    payload = build_mediator_input_payload(debate_result, pose_data, user_context)

    session_service = InMemorySessionService()
    user_id = str(user_context.get("user_id") or "mediator_user")
    session_id = f"mediator_{uuid.uuid4().hex[:8]}"
    await session_service.create_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    runner = Runner(
        agent=agent, app_name=APP_NAME, session_service=session_service
    )

    user_msg = types.Content(
        role="user",
        parts=[types.Part(text=json.dumps(payload, ensure_ascii=False))],
    )

    final_text: str | None = None
    start = time.monotonic()
    async for event in runner.run_async(
        user_id=user_id, session_id=session_id, new_message=user_msg
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(p.text or "" for p in event.content.parts)
    latency = time.monotonic() - start

    if not final_text:
        raise RuntimeError("Mediator 가 최종 응답을 반환하지 않음.")

    parsed = MediatorOutput.model_validate(json.loads(final_text))

    # P5 강제 + Task 9.1 단계: past_debate_references 는 빈 배열 (MCP 미연결, 환각 방지)
    parsed = _enforce_disclaimer(parsed)
    parsed.past_debate_references = []

    return parsed, latency


def run_mediator_sync(
    debate_result: dict[str, Any],
    pose_data: dict[str, Any],
    user_context: dict[str, Any],
) -> tuple[MediatorOutput, float]:
    """동기 wrapper (CLI/테스트 편의용).

    ⚠️ Streamlit 등 이미 이벤트 루프가 도는 환경에서는 asyncio.run() 충돌 가능
    → Day 14 UI 통합 시 await 경로로 전환 (convergence_judge.py 와 동일 부채)."""
    import asyncio

    return asyncio.run(run_mediator(debate_result, pose_data, user_context))


# ---------------------------------------------------------------------------
# CLI (스모크 테스트)
# ---------------------------------------------------------------------------

def _mock_debate_result() -> dict[str, Any]:
    """selftest 용 — 실제 토론 없이 Mediator 만 검증하기 위한 1라운드 mock."""
    return {
        "rounds": [
            {
                "round": 1,
                "encourager": {
                    "agent": "encourager",
                    "round": 1,
                    "praise": "5개 스쿼트 모두 평균 깊이 92도로 일정합니다. 안정적이에요.",
                    "concern_one": "왼쪽 무릎이 살짝 안쪽으로 들어오는 경향이 있어요.",
                    "actionable_tip": "발바닥 전체로 바닥을 밀며 무릎으로 밴드를 양옆으로 찢는다고 상상해보세요.",
                    "tone_metadata": {"warmth": 0.7, "detail": 0.6},
                },
                "scrutinizer": {
                    "agent": "scrutinizer",
                    "round": 1,
                    "primary_risk": {
                        "name": "왼쪽 무릎 내측 무너짐 (Knee Valgus Collapse, left)",
                        "severity": "high",
                        "mechanism": "반복적 valgus 부하가 ACL/MCL 긴장을 키웁니다.",
                        "evidence_in_data": "Rep 1,3,5 valgus 2°",
                        "threshold_breach": "> 1° (intermediate 허용치)",
                    },
                    "secondary_concerns": [],
                    "required_action": "중량 10-15% 감소, 전면 각도 재촬영 후 재점검.",
                    "tone_metadata": {"harshness": 0.7, "detail": 0.8},
                },
                "verdict": {
                    "converged": True,
                    "shared_issue": "좌측 무릎 내전 (knee valgus)",
                    "reason": "두 코치 모두 좌측 무릎 내측 무너짐을 지목.",
                },
                "round_latency_seconds": 26.0,
            }
        ],
        "converged": True,
        "converged_at_round": 1,
        "shared_issue": "좌측 무릎 내전 (knee valgus)",
        "total_latency_seconds": 30.0,
        "forced_stop_reason": None,
    }


if __name__ == "__main__":
    import sys
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    # ADK 는 GOOGLE_API_KEY 를 참조 → GEMINI_API_KEY 별칭 매핑 (Vertex 모드면 무시됨)
    import os

    if os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

    if "--selftest" not in sys.argv:
        print("사용법: python agents/mediator.py --selftest")
        raise SystemExit(0)

    debate = _mock_debate_result()
    pose = {"exercise_type": "squat", "rep_count": 5, "avg_depth_deg": 92}
    ctx = {
        "user_id": "user_001",
        "injury_history": ["lower_back_strain_2025"],
        "experience_level": "intermediate",
        "persona_state": {},
    }

    output, latency = run_mediator_sync(debate, pose, ctx)
    print(json.dumps(output.as_dict(), ensure_ascii=False, indent=2))
    print(f"\nLatency: {latency:.1f}s")

    # ---- acceptance 자체 검증 (Task 9.1) ----
    enc_tip = debate["rounds"][0]["encourager"]["actionable_tip"]
    scr_action = debate["rounds"][0]["scrutinizer"]["required_action"]
    blob = json.dumps(output.as_dict(), ensure_ascii=False)

    checks = {
        "합의안(consensus) 생성": bool(output.consensus.strip()),
        "priority_actions 1개 이상": len(output.priority_actions) >= 1,
        "P5 의료 면책 포함": "의학 조언" in output.disclaimer,
        "round_count_used 정확": output.round_count_used == 1,
        "past_debate_references 빈 배열(9.1)": output.past_debate_references == [],
    }
    print("\n=== Acceptance (Task 9.1) ===")
    for name, ok in checks.items():
        print(f"  {'✅' if ok else '❌'} {name}")
    all_ok = all(checks.values())
    print(f"\n{'✅ Task 9.1 acceptance 통과' if all_ok else '❌ 미충족 항목 있음'}")
    raise SystemExit(0 if all_ok else 1)
