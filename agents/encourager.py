"""
The Encourager Agent — 격려파 코치.

ARCHITECTURE.md §2.2 명세 구현:
- 모델: gemini-2.5-pro
- 페르소나: 10년 경력 친절한 PT, 따뜻하고 동기부여 중심
- 조정 가능 파라미터: warmth, detail (사용자 피드백으로 양방향 학습)
- 출력은 EncouragerOutput JSON 스키마 강제
"""

from __future__ import annotations

from typing import Any, Literal

from google.adk.agents import Agent
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 출력 스키마 (ARCHITECTURE.md §2.2)
# ---------------------------------------------------------------------------

class ToneMetadata(BaseModel):
    warmth: float = Field(ge=0.0, le=1.0)
    detail: float = Field(ge=0.0, le=1.0)


class EncouragerOutput(BaseModel):
    """The Encourager 의 한 라운드 응답."""
    agent: Literal["encourager"] = "encourager"
    round: int = Field(ge=1)
    praise: str = Field(
        description="사용자가 잘한 점 한 가지를 구체적인 수치로 인정."
    )
    concern_one: str = Field(
        description="다음 단계로 가다듬을 단 하나의 개선 포인트 (절대 여러 개 X)."
    )
    actionable_tip: str = Field(
        description="당장 시도해볼 수 있는 구체적 cue 한 문장."
    )
    tone_metadata: ToneMetadata
    addresses_scrutinizer: str | None = Field(
        default=None,
        description="round 2+ 에서 Scrutinizer 직전 주장에 대한 응답. round 1 은 None.",
    )


# ---------------------------------------------------------------------------
# 페르소나 프롬프트
# ---------------------------------------------------------------------------

ENCOURAGER_INSTRUCTION_TEMPLATE = """\
You are "The Encourager", a warm and supportive personal trainer with 10 years of experience.
You believe people improve through positive reinforcement and incremental challenges.

Your style:
- Always start by acknowledging what the user did well (specifically, with metrics from pose_data).
- Frame problems as "next-step opportunities", not failures.
- Give ONE concrete improvement focus per response (never overwhelm).
- Use second-person ("you", "your") and a warm tone.
- Never minimize safety concerns, but contextualize them ("this is fixable").
- Never give medical advice; if the user mentions pain, recommend a qualified professional.

Your adjustable parameters (set by user feedback over time):
- warmth = {warmth_level}     # 0.0 (neutral) to 1.0 (very warm) — adjust your wording temperature.
- detail = {detail_level}     # 0.0 (brief) to 1.0 (detailed)    — adjust length and specificity.

You will receive a JSON object with:
  - pose_data:    metrics produced by the PoseExtractor (rep-level depth, knee alignment, tempo, safety_flags).
  - user_context: user_id, injury_history, experience_level, current persona_state.
  - debate_round: integer round number.
  - scrutinizer_previous_argument: the Scrutinizer's last message (null in round 1).

In round 2+, you must include a one-sentence response to the Scrutinizer in `addresses_scrutinizer`.
You will debate with "The Scrutinizer" (a strict biomechanics PhD). Stand your ground when appropriate.

Respond in Korean (한국어로). Output JSON ONLY — schema is enforced.
"""


def build_encourager_instruction(warmth: float, detail: float) -> str:
    """warmth/detail 파라미터를 시스템 프롬프트에 주입."""
    return ENCOURAGER_INSTRUCTION_TEMPLATE.format(
        warmth_level=f"{warmth:.2f}",
        detail_level=f"{detail:.2f}",
    )


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

def create_encourager_agent(warmth: float = 0.7, detail: float = 0.6) -> Agent:
    """
    The Encourager 에이전트 인스턴스를 만든다.

    Args:
        warmth: 0.0 ~ 1.0. 사용자 피드백으로 양방향 조정됨.
        detail: 0.0 ~ 1.0.

    Returns:
        ADK Agent. orchestrator 에서 SequentialAgent / debate loop 에 꽂아 사용.
    """
    if not 0.0 <= warmth <= 1.0:
        raise ValueError(f"warmth must be in [0.0, 1.0], got {warmth}")
    if not 0.0 <= detail <= 1.0:
        raise ValueError(f"detail must be in [0.0, 1.0], got {detail}")

    return Agent(
        name="encourager",
        model="gemini-2.5-pro",
        description=(
            "The Encourager — warm certified PT (10y). 좋은 점 발견 + 점진적 개선 제안. "
            "warmth/detail 파라미터로 톤 조정 가능."
        ),
        instruction=build_encourager_instruction(warmth=warmth, detail=detail),
        output_schema=EncouragerOutput,
    )


# ---------------------------------------------------------------------------
# 입력 페이로드 헬퍼 (orchestrator/tests 에서 공통 사용)
# ---------------------------------------------------------------------------

def build_input_payload(
    pose_data: dict[str, Any],
    user_context: dict[str, Any],
    debate_round: int = 1,
    scrutinizer_previous_argument: str | None = None,
) -> dict[str, Any]:
    """Encourager 가 받을 user 메시지 페이로드."""
    return {
        "pose_data": pose_data,
        "user_context": user_context,
        "debate_round": debate_round,
        "scrutinizer_previous_argument": scrutinizer_previous_argument,
    }
