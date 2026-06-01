"""
Hello World — Day 1 핵심 자체검증.

목적: ADK 최소 에이전트 + Phoenix 자동 계측이 end-to-end로 동작하는지 증명.

이 파일이 정상 종료(exit 0)되면:
  1. 터미널에 에이전트 응답 한 줄 출력
  2. Phoenix Cloud (formforge-prod 프로젝트)에 trace 1개 표시

검증 명령:
    python agents/hello_world.py

Phoenix Cloud 확인:
    https://app.phoenix.arize.com → formforge-prod 프로젝트 → Traces 탭
"""

from __future__ import annotations

import asyncio
import os
import sys

# ---- 1단계: .env 로드 (다른 import 전에 환경 변수가 준비되어야 함) ----
from dotenv import load_dotenv

load_dotenv()

# ADK는 환경변수 GOOGLE_API_KEY를 우선 참조하므로, GEMINI_API_KEY를 별칭으로 매핑.
if os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

# ---- 2단계: Phoenix 자동 계측 등록 (ADK import 전이어야 모든 호출 추적됨) ----
PHOENIX_ENDPOINT = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "https://app.phoenix.arize.com")
PHOENIX_PROJECT = os.getenv("PHOENIX_PROJECT_NAME", "formforge-prod")
PHOENIX_API_KEY = os.getenv("PHOENIX_API_KEY")

if not PHOENIX_API_KEY:
    print("❌ .env의 PHOENIX_API_KEY가 비어 있습니다.", file=sys.stderr)
    sys.exit(1)
if not os.getenv("GOOGLE_API_KEY"):
    print("❌ .env의 GEMINI_API_KEY가 비어 있습니다.", file=sys.stderr)
    sys.exit(1)

from phoenix.otel import register  # noqa: E402
from openinference.instrumentation.google_adk import GoogleADKInstrumentor  # noqa: E402

tracer_provider = register(
    project_name=PHOENIX_PROJECT,
    endpoint=PHOENIX_ENDPOINT.rstrip("/") + "/v1/traces",
    headers={"authorization": f"Bearer {PHOENIX_API_KEY}"},
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

# ---- 3단계: ADK 에이전트 정의 ----
from google.adk.agents import Agent  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

APP_NAME = "formforge-hello"
USER_ID = "day1_smoke"
SESSION_ID = "hello_session_1"

hello_agent = Agent(
    name="hello_world",
    model="gemini-2.5-flash",
    description="FormForge AI Day 1 hello-world smoke test agent.",
    instruction=(
        "You are a brief and friendly assistant. "
        "Respond in Korean with exactly one short sentence."
    ),
)


# ---- 4단계: 실행 ----
async def main() -> int:
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )
    runner = Runner(
        agent=hello_agent,
        app_name=APP_NAME,
        session_service=session_service,
    )

    user_text = "안녕! FormForge AI 첫 출근 인사 한 줄 부탁해."
    user_msg = types.Content(role="user", parts=[types.Part(text=user_text)])
    print(f"📤 사용자: {user_text}")

    final_text: str | None = None
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=SESSION_ID,
        new_message=user_msg,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(p.text or "" for p in event.content.parts)

    # ---- 5단계: 자체 검증 ----
    if not final_text:
        print("❌ 에이전트가 최종 응답을 반환하지 않음.", file=sys.stderr)
        return 1

    print(f"📥 에이전트: {final_text}")
    print()
    print("✅ Hello World 성공!")
    print("   다음 확인:")
    print("   1) https://app.phoenix.arize.com 접속")
    print(f"   2) Project: {PHOENIX_PROJECT}")
    print("   3) Traces 탭에 방금 호출 1건이 보이면 자동 계측 OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n중단됨.", file=sys.stderr)
        raise SystemExit(130)
