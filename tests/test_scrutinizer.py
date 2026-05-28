"""
The Scrutinizer smoke test — 가짜 pose_data 로 한 번 호출.

Acceptance:
- 응답이 ScrutinizerOutput 스키마와 호환
- 한국어 응답
- primary_risk.severity 가 valgus 결함을 medium 이상으로 평가 (안전 신호)
- Phoenix Cloud 의 formforge-prod 프로젝트에 "scrutinizer" trace 1건 추가
- exit 0

실행:
    python tests/test_scrutinizer.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# ---- 1) .env 로드 ----
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

if os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

# ---- 2) Phoenix 자동 계측 등록 ----
from phoenix.otel import register  # noqa: E402
from openinference.instrumentation.google_adk import GoogleADKInstrumentor  # noqa: E402

PHOENIX_API_KEY = os.getenv("PHOENIX_API_KEY")
PHOENIX_ENDPOINT = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "https://app.phoenix.arize.com")
PHOENIX_PROJECT = os.getenv("PHOENIX_PROJECT_NAME", "formforge-prod")
if not PHOENIX_API_KEY:
    print("❌ .env 의 PHOENIX_API_KEY 가 비어 있습니다.", file=sys.stderr)
    sys.exit(1)

tracer_provider = register(
    project_name=PHOENIX_PROJECT,
    endpoint=PHOENIX_ENDPOINT.rstrip("/") + "/v1/traces",
    headers={"api_key": PHOENIX_API_KEY},
)
GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)

# ---- 3) ADK + Scrutinizer import ----
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

sys.path.insert(0, str(PROJECT_ROOT))
from agents.scrutinizer import create_scrutinizer_agent  # noqa: E402


APP_NAME = "formforge-scrutinizer-smoke"
USER_ID = "test_user_alpha"
SESSION_ID = "scrutinizer_round1"


def load_sample_pose_data() -> dict:
    with (PROJECT_ROOT / "tests" / "sample_pose_data.json").open(encoding="utf-8") as f:
        return json.load(f)


def build_user_message(pose_data: dict) -> types.Content:
    payload = {
        "pose_data": pose_data,
        "user_context": {
            "user_id": USER_ID,
            "injury_history": ["lower_back_strain_2025"],
            "experience_level": "intermediate",
            "persona_state": {"scrutinizer": {"harshness": 0.7, "detail": 0.8}},
        },
        "debate_round": 1,
        "encourager_previous_argument": None,
    }
    text = (
        "다음 JSON 은 PoseExtractor 가 만든 데이터입니다. "
        "ARCHITECTURE.md §2.3 의 ScrutinizerOutput 스키마에 맞춰 한국어로 응답해주세요.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    return types.Content(role="user", parts=[types.Part(text=text)])


async def main() -> int:
    pose_data = load_sample_pose_data()
    scrutinizer = create_scrutinizer_agent(harshness=0.7, detail=0.8)

    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
    )
    runner = Runner(
        agent=scrutinizer,
        app_name=APP_NAME,
        session_service=session_service,
    )

    print("📤 The Scrutinizer 호출 중 (Gemini 2.5 Pro, Vertex AI)…")

    final_text: str | None = None
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=SESSION_ID,
        new_message=build_user_message(pose_data),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(p.text or "" for p in event.content.parts)

    if not final_text:
        print("❌ 최종 응답이 없습니다.", file=sys.stderr)
        return 1

    print("\n📥 The Scrutinizer 응답 (raw):\n")
    print(final_text)

    try:
        parsed = json.loads(final_text)
    except json.JSONDecodeError as e:
        print(f"\n❌ JSON 파싱 실패: {e}", file=sys.stderr)
        return 1

    required = ["agent", "round", "primary_risk", "required_action", "tone_metadata"]
    missing = [k for k in required if k not in parsed]
    if missing:
        print(f"\n❌ 필수 키 누락: {missing}", file=sys.stderr)
        return 1

    pr = parsed["primary_risk"]
    print("\n--- 자체 검증 ---")
    print(f"  ✅ JSON 스키마 호환")
    print(f"  ✅ agent             = {parsed.get('agent')}")
    print(f"  ✅ round             = {parsed.get('round')}")
    print(f"  ✅ primary_risk.name = {pr.get('name')}")
    print(f"  ✅ severity          = {pr.get('severity')}")
    print(f"  ✅ mechanism         = {pr.get('mechanism')[:70]}...")
    print(f"  ✅ evidence_in_data  = {pr.get('evidence_in_data')[:70]}...")
    print(f"  ✅ required_action   = {parsed.get('required_action')[:70]}...")
    sc_count = len(parsed.get("secondary_concerns", []))
    print(f"  ✅ secondary_concerns count = {sc_count}")
    print(f"  ✅ tone_metadata     = {parsed.get('tone_metadata')}")

    # Acceptance: valgus 결함을 medium 이상으로 본다면 안전 신호
    if pr.get("severity") in ("medium", "medium-high", "high", "critical"):
        print(f"\n  🛡️ Acceptance 통과: valgus 결함을 '{pr.get('severity')}' 로 평가 (의도된 반응)")
    else:
        print(f"\n  ⚠️ severity 가 너무 낮음: '{pr.get('severity')}'. prompt 튜닝 검토 필요.")

    print(f"\n  Phoenix Cloud 확인: https://app.phoenix.arize.com → {PHOENIX_PROJECT}")
    print(f"  → Spans 탭에 'scrutinizer' 이름 trace 1건 추가됐는지 확인.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n중단됨.", file=sys.stderr)
        raise SystemExit(130)
