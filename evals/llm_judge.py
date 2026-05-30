# 파일 위치: evals/llm_judge.py
"""
LLM-as-a-Judge — Day 13 Task 13.2 (Self-Improvement Loop, 1등 결정 요소 ⭐⭐).

목적:
  한 번의 토론(Encourager argument + Scrutinizer argument + Mediator consensus)과
  사용자 피드백을 받아:
    1. 토론 품질을 0.0~1.0 으로 점수화 (multi-perspective / evidence / actionability)
    2. 페르소나 파라미터 조정 추천 (ARCHITECTURE.md §6.3 스키마)
  결과를 Phoenix Cloud 에 eval span 으로 기록 → Arize 트랙 평가 직결.

설계 결정 (PROGRESS 세션 11 grill-me 확정 — "하이브리드"):
  - 모델: gemini-3.5-flash (stable). 시스템 전체에서 Gemini 3 family 를 한 곳
    명시적으로 채택 → "최신 모델 활용" 시그널 (DEVPOST/README Built With 에 명기).
    ※ convergence_judge(gemini-2.5-flash, 합의 감지) 와는 역할이 다른 별개 judge.
  - 이 judge 는 ARCHITECTURE §6.3 스키마 전체(품질점수 + delta 추천 + reasoning)를
    반환한다. 단 enum 피드백(warmth/harshness)의 **실제 적용 delta 는 결정론적
    룩업 테이블**(feedback_handler.py)이 확정한다 — LLM 변동으로 acceptance 수치
    (too_harsh → 정확히 -0.15)가 깨지지 않게. LLM 추천은 detail(자유 텍스트 기반
    정성 판단)과 품질 점수에서 본 가치를 발휘.
  - Phoenix 자동 계측이 ADK Runner 만 잡으므로, google-genai 직접 호출인 이 judge 는
    convergence_judge 와 동일하게 명시적 OTel LLM span 으로 기록한다 (P1).

호출 시점:
  - feedback_handler.process_feedback() 내부에서 1회 (피드백 POST 직후).
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from google import genai
from google.genai import types
from opentelemetry import trace
from pydantic import BaseModel, Field

# Phoenix register() 후 get_tracer 로 받으면 Phoenix Cloud 로 span 자동 송출.
_tracer = trace.get_tracer("formforge.evals.llm_judge")

_JUDGE_MODEL = "gemini-3.5-flash"  # Gemini 3 family 채택 시그널 (TASKS.md 13.2)
# ⚠️ Gemini 3 family 는 현재 Vertex AI 의 `global` 엔드포인트에서만 서빙된다
#    (us-central1 등 리전 엔드포인트는 404 NOT_FOUND — 세션 11 실측).
#    그래서 judge 전용으로 location 을 global 로 오버라이드한다. 다른 모듈
#    (convergence_judge=gemini-2.5-flash 등)은 us-central1 유지.
_JUDGE_LOCATION = "global"


# ---------------------------------------------------------------------------
# 출력 스키마 (ARCHITECTURE.md §6.3)
# ---------------------------------------------------------------------------

class EncouragerDelta(BaseModel):
    warmth_delta: float = Field(
        description="Encourager warmth 변화량. too_warm→음수, too_cold→양수, perfect→0."
    )
    detail_delta: float = Field(
        default=0.0,
        description="Encourager detail 변화량 (자유 텍스트 피드백 기반 자동 판단, 보통 0).",
    )


class ScrutinizerDelta(BaseModel):
    harshness_delta: float = Field(
        description="Scrutinizer harshness 변화량. too_harsh→음수, too_soft→양수, perfect→0."
    )
    detail_delta: float = Field(
        default=0.0,
        description="Scrutinizer detail 변화량 (자유 텍스트 피드백 기반 자동 판단, 보통 0).",
    )


class PersonaAdjustment(BaseModel):
    encourager: EncouragerDelta
    scrutinizer: ScrutinizerDelta


class JudgeResult(BaseModel):
    """LLM-as-a-Judge 평가 결과 (ARCHITECTURE.md §6.3 출력 스키마)."""
    debate_quality_score: float = Field(
        ge=0.0, le=1.0,
        description="토론 품질 0.0~1.0 (다관점 커버리지 / 근거 품질 / 실행가능성).",
    )
    persona_adjustment_recommendation: PersonaAdjustment
    reasoning: str = Field(description="왜 이렇게 점수·조정했는지 한국어 한 문장.")

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()


# ---------------------------------------------------------------------------
# 시스템 프롬프트 (ARCHITECTURE.md §6.3 템플릿)
# ---------------------------------------------------------------------------

_JUDGE_INSTRUCTION = """\
You are evaluating a workout-form debate between two AI coaches and a mediator.

You receive:
- The Encourager's argument (warm, motivational coach).
- The Scrutinizer's argument (strict exercise-physiologist).
- The Mediator's consensus (balances both, considers injury history).
- The user's feedback (how they felt about each coach's tone).
- The current persona state (warmth / harshness / detail parameters, each 0.0~1.0).

Your tasks:
1. Score debate quality from 0.0 to 1.0, judging:
   - multi-perspective coverage (did the two coaches genuinely differ in view?),
   - evidence quality (are claims grounded in the metrics, not vague?),
   - actionability (can the user actually act on the advice?).

2. Recommend persona parameter adjustments.
   IMPORTANT: the core warmth/harshness deltas are applied DETERMINISTICALLY by a
   lookup table OUTSIDE this judge — your warmth_delta / harshness_delta are NOT used
   for the actual update. Focus your judgement on detail_delta.
   - detail_delta (the value that matters): default 0.0. Adjust only if the user's
     FREE TEXT explicitly asks for more/less specificity
     (e.g. "더 구체적으로" → +0.10, "너무 장황해" → -0.10).
   - warmth_delta / harshness_delta (informational only — fill to satisfy the schema):
     too_warm/too_harsh → negative, too_cold/too_soft → positive, perfect → 0.0.
   - All deltas are absolute changes (no learning-rate multiplier).

Output JSON ONLY matching the schema. `reasoning` must be ONE Korean sentence.
"""


# ---------------------------------------------------------------------------
# 클라이언트 (싱글톤, Vertex 우선 — 세션 4 RESOURCE_EXHAUSTED 회피)
# ---------------------------------------------------------------------------

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is not None:
        return _client
    use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in (
        "true", "1", "yes",
    )
    if use_vertex:
        # location 은 env 가 아니라 _JUDGE_LOCATION(global) 고정 — Gemini 3 가용 리전.
        _client = genai.Client(
            vertexai=True,
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            location=_JUDGE_LOCATION,
        )
    else:
        _client = genai.Client(
            api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        )
    return _client


# ---------------------------------------------------------------------------
# Judge 함수
# ---------------------------------------------------------------------------

async def judge_debate(
    encourager_text: str,
    scrutinizer_text: str,
    mediator_text: str,
    user_feedback: dict[str, Any],
    persona_state: dict[str, Any],
) -> tuple[JudgeResult, float]:
    """
    토론 1회 + 사용자 피드백 → 품질 점수 + 페르소나 조정 추천.

    Args:
        encourager_text: Encourager 응답 (raw text 또는 JSON 문자열).
        scrutinizer_text: Scrutinizer 응답.
        mediator_text: Mediator consensus 텍스트.
        user_feedback: { encourager_rating, scrutinizer_rating, mediator_rating, free_text? }
        persona_state: 현재 { encourager: {warmth, detail}, scrutinizer: {harshness, detail} }

    Returns:
        (JudgeResult, latency_seconds)

    Phoenix: 명시적 LLM span("llm_judge") + eval attribute 로 Phoenix Cloud 기록.
    """
    client = _get_client()

    payload = {
        "encourager_argument": encourager_text,
        "scrutinizer_argument": scrutinizer_text,
        "mediator_consensus": mediator_text,
        "user_feedback": user_feedback,
        "current_persona_state": persona_state,
    }
    payload_str = json.dumps(payload, ensure_ascii=False)

    with _tracer.start_as_current_span(
        "llm_judge",
        attributes={
            "openinference.span.kind": "LLM",
            "llm.model_name": _JUDGE_MODEL,
            "llm.system": "google",
            "input.value": payload_str,
            "input.mime_type": "application/json",
            # Phoenix evals 탭 식별용 — 이 span 이 평가(eval) 성격임을 표시
            "eval.name": "debate_quality",
        },
    ) as span:
        try:
            start = time.monotonic()
            response = await client.aio.models.generate_content(
                model=_JUDGE_MODEL,
                contents=[types.Content(role="user", parts=[types.Part(text=payload_str)])],
                config=types.GenerateContentConfig(
                    system_instruction=_JUDGE_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=JudgeResult,
                    temperature=0.1,  # 품질 점수 재현성
                ),
            )
            latency = time.monotonic() - start

            parsed: JudgeResult
            if getattr(response, "parsed", None) is not None and isinstance(
                response.parsed, JudgeResult
            ):
                parsed = response.parsed
            else:
                parsed = JudgeResult.model_validate(json.loads(response.text or "{}"))

            # eval 결과를 span attribute 로 기록 → Phoenix Cloud 에서 점수 가시화
            span.set_attribute("output.value", parsed.model_dump_json())
            span.set_attribute("output.mime_type", "application/json")
            span.set_attribute("eval.score", parsed.debate_quality_score)
            span.set_attribute("eval.label", _quality_label(parsed.debate_quality_score))
            span.set_attribute("eval.explanation", parsed.reasoning)
            span.set_attribute("judge.latency_seconds", latency)
        except Exception as e:  # noqa: BLE001 — 실패를 span 에 ERROR 로 (P1)
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            raise

    return parsed, latency


def _quality_label(score: float) -> str:
    """Phoenix eval 라벨 — 점수를 사람이 읽는 범주로."""
    if score >= 0.8:
        return "excellent"
    if score >= 0.6:
        return "good"
    if score >= 0.4:
        return "fair"
    return "poor"


# ---------------------------------------------------------------------------
# 동기 wrapper (Streamlit 등 sync 환경 편의용)
# ---------------------------------------------------------------------------

def judge_debate_sync(
    encourager_text: str,
    scrutinizer_text: str,
    mediator_text: str,
    user_feedback: dict[str, Any],
    persona_state: dict[str, Any],
) -> tuple[JudgeResult, float]:
    import asyncio
    return asyncio.run(
        judge_debate(
            encourager_text, scrutinizer_text, mediator_text,
            user_feedback, persona_state,
        )
    )


# ---------------------------------------------------------------------------
# CLI (스모크 테스트)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    demo_feedback = {
        "encourager_rating": "perfect",
        "scrutinizer_rating": "too_harsh",
        "mediator_rating": 4,
        "free_text": "",
    }
    demo_persona = {
        "encourager": {"warmth": 0.7, "detail": 0.6},
        "scrutinizer": {"harshness": 0.7, "detail": 0.8},
    }

    result, latency = judge_debate_sync(
        encourager_text="5개 스쿼트 깊이가 일정해서 좋아요. 다음엔 상체를 조금 더 세워볼까요?",
        scrutinizer_text="과도한 전방 기울기로 요추 부담 큼. 중량 20% 감량 필요.",
        mediator_text="두 코치 모두 전방 기울기를 지적. 부상 이력 고려해 중량 감량 우선.",
        user_feedback=demo_feedback,
        persona_state=demo_persona,
    )
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    print(f"\nLatency: {latency:.2f}s  /  label={_quality_label(result.debate_quality_score)}")
