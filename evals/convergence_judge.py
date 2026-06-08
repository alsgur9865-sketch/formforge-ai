# 파일 위치: evals/convergence_judge.py
"""
합의 감지 LLM (Day 8 Task 8.1 의 핵심 알고리즘).

목적:
  Encourager 의 `concern_one` 과 Scrutinizer 의 `primary_risk.name` 이 같은 issue 를
  가리키는지 빠르게 분류. Mediator 호출 전에 orchestrator 가 호출.

설계 결정:
  - 모델: gemini-2.5-flash (1~2초 빠른 분류, low cost)
    ※ Day 13 의 LLM-as-a-Judge (gemini-3.5-flash) 와 별개. 그건 토론 품질 평가용.
  - 출력: ConvergenceVerdict (converged + shared_issue + reason)
  - Phoenix 자동 계측이 이 호출도 별도 span 으로 기록 (acceptance criteria)

호출 시점:
  - Round N 종료 후, Mediator 호출하기 전
  - converged=True → 즉시 종료, Mediator 단계로 진입
  - converged=False → Round N+1 진행 (단, MAX_DEBATE_ROUNDS 한도 안에서)
"""

from __future__ import annotations

import json
import time
from typing import Any

from google import genai
from google.genai import types
from opentelemetry import trace
from pydantic import BaseModel, Field

# OpenTelemetry tracer — Phoenix `register()` 가 set_tracer_provider 한 뒤에
# get_tracer 로 받으면 자동으로 Phoenix Cloud 로 span 송출.
# `openinference.span.kind` 속성으로 LLM span 분류 → Phoenix UI 에서 LLM 카테고리.
_tracer = trace.get_tracer("formforge.evals.convergence_judge")


# ---------------------------------------------------------------------------
# 출력 스키마
# ---------------------------------------------------------------------------

class ConvergenceVerdict(BaseModel):
    """합의 감지 LLM 의 판정 결과."""
    converged: bool = Field(
        description="두 코치가 같은 primary issue 를 가리키면 True"
    )
    shared_issue: str | None = Field(
        default=None,
        description="converged=True 이면 공통 issue 의 짧은 이름. False 면 null.",
    )
    reason: str = Field(
        description="판정 근거 한두 문장."
    )

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump()


# ---------------------------------------------------------------------------
# 시스템 프롬프트
# ---------------------------------------------------------------------------

_JUDGE_INSTRUCTION = """\
You are a neutral arbiter classifying whether two fitness coaches are focused on the SAME primary issue.

Two coaches reviewed the same workout video. You receive:
  - The Encourager's `concern_one` (a single next-step focus, written warmly).
  - The Scrutinizer's `primary_risk.name` (the most dangerous finding).

Decide:
  - converged=true if both target the same underlying biomechanical issue
    (even if worded differently). Example: "left knee drifting inward" and
    "knee valgus collapse (left)" → converged=true, shared_issue="Left knee valgus".
  - converged=false if they target genuinely different issues
    (e.g., one says "knee tracking", the other says "spinal flexion").

Be strict: surface similarity is not convergence. If unsure, prefer false.

Respond with JSON only matching the schema.
"""


# ---------------------------------------------------------------------------
# 클라이언트 (싱글톤)
# ---------------------------------------------------------------------------

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Vertex AI 모드 우선 (세션 4 의 RESOURCE_EXHAUSTED 회피 패턴)."""
    global _client
    if _client is not None:
        return _client
    import os
    use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in (
        "true", "1", "yes",
    )
    if use_vertex:
        _client = genai.Client(
            vertexai=True,
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )
    else:
        _client = genai.Client(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    return _client


# ---------------------------------------------------------------------------
# 합의 감지 함수
# ---------------------------------------------------------------------------

async def judge_convergence(
    encourager_concern: str,
    scrutinizer_risk_name: str,
    extra_context: str | None = None,
) -> tuple[ConvergenceVerdict, float]:
    """
    두 코치의 핵심 우려가 같은 issue 인지 분류.

    Args:
        encourager_concern: Encourager.concern_one 텍스트
        scrutinizer_risk_name: Scrutinizer.primary_risk.name 텍스트
        extra_context: 선택. 추가로 LLM 이 볼 컨텍스트 (예: rep 번호, 부상 이력)

    Returns:
        (verdict, latency_seconds)
    """
    client = _get_client()

    user_msg = {
        "encourager_concern_one": encourager_concern,
        "scrutinizer_primary_risk_name": scrutinizer_risk_name,
    }
    if extra_context:
        user_msg["extra_context"] = extra_context

    # 명시적 OTel span — judge_convergence 호출이 Phoenix Cloud 에 LLM span 으로 기록됨
    # (Task 8.1 acceptance: "합의 판정 LLM call 도 trace 에 별도 span 으로 기록").
    # GoogleADKInstrumentor 는 ADK Runner 호출만 잡고 google-genai 직접 호출은 미커버.
    user_msg_str = json.dumps(user_msg, ensure_ascii=False)
    with _tracer.start_as_current_span(
        "convergence_judge",
        attributes={
            "openinference.span.kind": "LLM",
            "llm.model_name": "gemini-2.5-flash",
            "llm.system": "google",
            "input.value": user_msg_str,
            "input.mime_type": "application/json",
        },
    ) as span:
        start = time.monotonic()
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part(text=user_msg_str)],
                )
            ],
            config=types.GenerateContentConfig(
                system_instruction=_JUDGE_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=ConvergenceVerdict,
                temperature=0.1,
            ),
        )
        latency = time.monotonic() - start

        # SDK가 자동 parse 해 주면 .parsed 사용, 아니면 json.loads
        parsed: ConvergenceVerdict
        if getattr(response, "parsed", None) is not None and isinstance(
            response.parsed, ConvergenceVerdict
        ):
            parsed = response.parsed
        else:
            raw = response.text or "{}"
            parsed = ConvergenceVerdict.model_validate(json.loads(raw))

        # span 에 결과 attribute 기록 (Phoenix UI 에서 한눈에 보임)
        span.set_attribute("output.value", parsed.model_dump_json())
        span.set_attribute("output.mime_type", "application/json")
        span.set_attribute("convergence.converged", parsed.converged)
        if parsed.shared_issue:
            span.set_attribute("convergence.shared_issue", parsed.shared_issue)
        span.set_attribute("convergence.latency_seconds", latency)

    return parsed, latency


# ---------------------------------------------------------------------------
# 동기 wrapper (Streamlit 같은 sync 환경 편의용)
# ---------------------------------------------------------------------------

def judge_convergence_sync(
    encourager_concern: str,
    scrutinizer_risk_name: str,
    extra_context: str | None = None,
) -> tuple[ConvergenceVerdict, float]:
    import asyncio
    return asyncio.run(
        judge_convergence(encourager_concern, scrutinizer_risk_name, extra_context)
    )


# ---------------------------------------------------------------------------
# CLI (스모크 테스트)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    from pathlib import Path

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    if len(sys.argv) < 3:
        # 기본 데모 케이스
        encourager = "왼쪽 무릎이 살짝 안쪽으로 들어오는 경향이 있어요."
        scrutinizer = "Knee valgus collapse (left)"
    else:
        encourager, scrutinizer = sys.argv[1], sys.argv[2]

    verdict, latency = judge_convergence_sync(encourager, scrutinizer)
    print(json.dumps(verdict.as_dict(), ensure_ascii=False, indent=2))
    print(f"\nLatency: {latency:.2f}s")
