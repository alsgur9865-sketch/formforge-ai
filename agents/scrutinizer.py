"""
The Scrutinizer Agent — 회의파 코치 (운동생리학 PhD).

ARCHITECTURE.md §2.3 명세 구현:
- 모델: gemini-2.5-pro
- 페르소나: PhD biomechanist. 직설, 근거 기반, severity 우선.
- 조정 가능 파라미터: harshness, detail (사용자 피드백으로 양방향 학습)
- 출력은 ScrutinizerOutput JSON 스키마 강제
"""

from __future__ import annotations

from typing import Any, Literal

from google.adk.agents import Agent
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 출력 스키마 (ARCHITECTURE.md §2.3)
# ---------------------------------------------------------------------------

SeverityT = Literal["low", "medium", "medium-high", "high", "critical"]


class PrimaryRisk(BaseModel):
    name: str = Field(description="결함 이름. 예: 'Knee valgus collapse (left)'")
    severity: SeverityT
    mechanism: str = Field(
        description="생체역학적 기전 한 문장. 예: 'Repeated valgus loading increases ACL/MCL strain.'"
    )
    evidence_in_data: str = Field(
        description="pose_data 의 어떤 수치/필드를 근거로 했는지 명시. 예: 'Rep 1,3,5 valgus 2°'"
    )
    threshold_breach: str = Field(
        description="안전 임계치 대비 얼마나 벗어났는지. 예: '> 1° (intermediate tolerance)'"
    )


class SecondaryConcern(BaseModel):
    name: str
    severity: SeverityT
    note: str


class ScrutinizerToneMetadata(BaseModel):
    harshness: float = Field(ge=0.0, le=1.0)
    detail: float = Field(ge=0.0, le=1.0)


class ScrutinizerOutput(BaseModel):
    """The Scrutinizer 의 한 라운드 응답."""
    agent: Literal["scrutinizer"] = "scrutinizer"
    round: int = Field(ge=1)
    primary_risk: PrimaryRisk
    secondary_concerns: list[SecondaryConcern] = Field(
        default_factory=list,
        description="우선 risk 외 부수 결함들. 0~3개 권장.",
    )
    required_action: str = Field(
        description="당장 취해야 할 조치. 예: 'Reduce load 10-15%, video front angle, recheck.'"
    )
    tone_metadata: ScrutinizerToneMetadata
    addresses_encourager: str | None = Field(
        default=None,
        description="round 2+ 에서 Encourager 직전 주장에 대한 반박. round 1 은 None.",
    )


# ---------------------------------------------------------------------------
# 페르소나 프롬프트
# ---------------------------------------------------------------------------

SCRUTINIZER_INSTRUCTION_TEMPLATE = """\
You are "The Scrutinizer", an exercise physiologist with a PhD in biomechanics.
You believe most lifting injuries come from form flaws ignored for too long.
You don't sugarcoat. You don't comfort. You diagnose.

Your style:
- Lead with the most dangerous finding, severity-ranked.
- Cite specific biomechanical mechanisms (e.g., "spinal flexion under load increases L4-L5 disc pressure").
- Quantify risk where possible (rep counts, angle thresholds, percentile breaches).
- Reject vague encouragement. If something is wrong, name it.
- Never give medical advice — for actual pain or injury, recommend a qualified medical professional.

Your adjustable parameters (set by user feedback over time):
- harshness = {harshness_level}     # 0.0 (clinical, neutral)  to 1.0 (blunt, no softening)
- detail    = {detail_level}        # 0.0 (brief)              to 1.0 (deep mechanistic explanation)

You will receive a JSON object with:
  - pose_data:    metrics produced by the PoseExtractor (rep-level depth, knee alignment, tempo, safety_flags).
  - user_context: user_id, injury_history, experience_level, current persona_state.
  - debate_round: integer round number.
  - encourager_previous_argument: the Encourager's last message (null in round 1).

If the Encourager understated a safety risk, you must push back in `addresses_encourager` (round 2+) with cited evidence.
Match user_context.injury_history when ranking severity — past injuries amplify risk.

Respond in Korean (한국어로). Output JSON ONLY — schema is enforced.
"""


def build_scrutinizer_instruction(harshness: float, detail: float) -> str:
    """harshness/detail 파라미터를 시스템 프롬프트에 주입."""
    return SCRUTINIZER_INSTRUCTION_TEMPLATE.format(
        harshness_level=f"{harshness:.2f}",
        detail_level=f"{detail:.2f}",
    )


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

def create_scrutinizer_agent(harshness: float = 0.7, detail: float = 0.8) -> Agent:
    """
    The Scrutinizer 에이전트 인스턴스를 만든다.

    Args:
        harshness: 0.0 ~ 1.0. 사용자 피드백으로 양방향 조정됨.
        detail: 0.0 ~ 1.0.

    Returns:
        ADK Agent. orchestrator 에서 Encourager 와 같은 토론 루프에 꽂아 사용.
    """
    if not 0.0 <= harshness <= 1.0:
        raise ValueError(f"harshness must be in [0.0, 1.0], got {harshness}")
    if not 0.0 <= detail <= 1.0:
        raise ValueError(f"detail must be in [0.0, 1.0], got {detail}")

    return Agent(
        name="scrutinizer",
        model="gemini-2.5-pro",
        description=(
            "The Scrutinizer — exercise physiology PhD. "
            "부상 위험·생체역학 결함 가차없이 지적. harshness/detail 파라미터로 톤 조정 가능."
        ),
        instruction=build_scrutinizer_instruction(harshness=harshness, detail=detail),
        output_schema=ScrutinizerOutput,
    )


# ---------------------------------------------------------------------------
# 입력 페이로드 헬퍼
# ---------------------------------------------------------------------------

def build_input_payload(
    pose_data: dict[str, Any],
    user_context: dict[str, Any],
    debate_round: int = 1,
    encourager_previous_argument: str | None = None,
) -> dict[str, Any]:
    """Scrutinizer 가 받을 user 메시지 페이로드."""
    return {
        "pose_data": pose_data,
        "user_context": user_context,
        "debate_round": debate_round,
        "encourager_previous_argument": encourager_previous_argument,
    }
