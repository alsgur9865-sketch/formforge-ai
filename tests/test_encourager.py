"""
The Encourager smoke test — 가짜 pose_data 로 한 번 호출.

Acceptance:
- 응답이 EncouragerOutput 스키마와 호환 (JSON 파싱 성공 + 필수 키 존재)
- 한국어 응답
- Phoenix Cloud 의 formforge-prod 프로젝트에 "encourager" trace 1건 추가
- exit 0 으로 종료

실행:
    python -m tests.test_encourager
    (또는 venv 활성화 후) python tests/test_encourager.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# ---- 1) .env 로드 + GEMINI_API_KEY → GOOGLE_API_KEY 매핑 ----
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

if os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

# ---- 2) Phoenix 자동 계측 등록 (ADK import 전) ----
from phoenix.otel import register  # noqa: E402
from openinference.instrumentation.google_adk import GoogleADKInstrumentor  # noqa: E402

PHOENIX_API_KEY = os.getenv("PHOENIX_API_KEY")
PHOENIX_ENDPOINT = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "https://app.phoenix.arize.com/s/alsgur9865")
PHOENIX_PROJECT = os.getenv("PHOENIX_PROJECT_NAME", "formforge-prod")
if not PHOENIX_API_KEY:
    print("❌ .env 의 PHOENIX_API_KEY 가 비어 있습니다.", file=sys.stderr)
    sys.exit(1)

tracer_provider = register(
    project_name=PHOENIX_PROJECT,
    endpoint=PHOENIX_ENDPOINT.rstrip("/") + "/v1/traces",
    headers={"authorization": f"Bearer {PHOENIX_API_KEY}"},
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

# ---- 3) ADK + Encourager import ----
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

# 패키지 경로로 못 부를 때 대비
sys.path.insert(0, str(PROJECT_ROOT))
from agents.encourager import create_encourager_agent  # noqa: E402


APP_NAME = "formforge-encourager-smoke"
USER_ID = "test_user_alpha"
SESSION_ID = "encourager_round1"


def load_sample_pose_data() -> dict:
    path = PROJECT_ROOT / "tests" / "sample_pose_data.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def build_user_message(pose_data: dict) -> types.Content:
    payload = {
        "pose_data": pose_data,
        "user_context": {
            "user_id": USER_ID,
            "injury_history": ["lower_back_strain_2025"],
            "experience_level": "intermediate",
            "persona_state": {"encourager": {"warmth": 0.7, "detail": 0.6}},
        },
        "debate_round": 1,
        "scrutinizer_previous_argument": None,
    }
    # ADK 는 사용자 텍스트로 받음. JSON 을 텍스트로 직렬화하여 전달.
    text = (
        "다음 JSON 은 PoseExtractor 가 만든 데이터입니다. "
        "ARCHITECTURE.md §2.2 의 EncouragerOutput 스키마에 맞춰 한국어로 응답해주세요.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    return types.Content(role="user", parts=[types.Part(text=text)])


async def main() -> int:
    pose_data = load_sample_pose_data()
    encourager = create_encourager_agent(warmth=0.7, detail=0.6)

    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )
    runner = Runner(
        agent=encourager,
        app_name=APP_NAME,
        session_service=session_service,
    )

    user_msg = build_user_message(pose_data)
    print("📤 The Encourager 호출 중 (Gemini 2.5 Pro)…")

    final_text: str | None = None
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=SESSION_ID,
        new_message=user_msg,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(p.text or "" for p in event.content.parts)

    if not final_text:
        print("❌ 최종 응답이 없습니다.", file=sys.stderr)
        return 1

    # ---- 검증: JSON 파싱 + 필수 키 ----
    print("\n📥 The Encourager 응답 (raw):\n")
    print(final_text)

    try:
        parsed = json.loads(final_text)
    except json.JSONDecodeError as e:
        print(f"\n❌ 응답이 JSON 파싱 실패: {e}", file=sys.stderr)
        return 1

    required = ["agent", "round", "praise", "concern_one", "actionable_tip", "tone_metadata"]
    missing = [k for k in required if k not in parsed]
    if missing:
        print(f"\n❌ 필수 키 누락: {missing}", file=sys.stderr)
        return 1

    print("\n--- 자체 검증 ---")
    print(f"  ✅ JSON 스키마 호환")
    print(f"  ✅ agent          = {parsed.get('agent')}")
    print(f"  ✅ round          = {parsed.get('round')}")
    print(f"  ✅ praise         = {parsed.get('praise')[:60]}...")
    print(f"  ✅ concern_one    = {parsed.get('concern_one')[:60]}...")
    print(f"  ✅ actionable_tip = {parsed.get('actionable_tip')[:60]}...")
    print(f"  ✅ tone_metadata  = {parsed.get('tone_metadata')}")
    print(f"\n  Phoenix Cloud 확인: https://app.phoenix.arize.com → {PHOENIX_PROJECT}")
    print(f"  → Spans 탭에서 'encourager' 이름의 trace 1건 추가됐는지 확인.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n중단됨.", file=sys.stderr)
        raise SystemExit(130)
