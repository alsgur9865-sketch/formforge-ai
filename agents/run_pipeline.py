# 파일 위치: agents/run_pipeline.py
"""라이브 분석 파이프라인을 독립 프로세스(메인스레드)에서 실행하는 진입점.

왜 별도 프로세스인가:
  Streamlit 은 스크립트를 비-메인 ScriptRunner 스레드에서 돌린다. 그 스레드에서
  asyncio.run 으로 OTel(GoogleADKInstrumentor) 계측된 ADK Runner 를 실행하면 Cloud Run
  에서 토론이 교착(hang)한다 — 비-메인 스레드 + asyncio + OTel 상호작용(실측: register 후
  무음·rounds=0, ~10분 요청 타임아웃까지 멈춤). 메인스레드 프로세스에선 계측이 켜져 있어도
  정상 완주(실측 Cloud Run Job 65s, span export 401 은 배치로 백그라운드 처리).
  → UI 는 이 스크립트를 subprocess 로 띄워(요청 안에서 블로킹) 파이프라인을 돌리고,
    run_full_e2e 가 Firestore(debate_id)에 기록한 결과를 폴링해 렌더한다.
    subprocess 는 부모 env(PHOENIX_API_KEY 등)를 상속하므로 P1 trace 송출도 그대로 유지된다.

입력: argv[1] = 파라미터 JSON 파일 경로
  { "debate_id", "video_uri", "exercise_type", "user_context",
    "persona_state"(nullable), "user_id", "use_mcp" }
종료코드: 0 성공 / 1 파이프라인 에러 / 2 PoseExtractor 신뢰도 가드 / 3 인자/로드 오류
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# 단독 실행(`python -m agents.run_pipeline` 또는 직접 호출) 시 import 경로 보장.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    if len(sys.argv) < 2:
        print("PIPELINE_ERROR: 파라미터 JSON 경로 인자 없음", file=sys.stderr)
        return 3
    try:
        params = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"PIPELINE_ERROR: 파라미터 로드 실패 {type(e).__name__}: {e}", file=sys.stderr)
        return 3

    from agents.orchestrator import PoseExtractionError, run_full_e2e

    try:
        asyncio.run(
            run_full_e2e(
                video_uri=params["video_uri"],
                user_context=params["user_context"],
                exercise_type=params.get("exercise_type", "squat"),
                persona_state=params.get("persona_state"),
                user_id=params.get("user_id", "anonymous"),
                debate_id=params["debate_id"],
                use_mcp=params.get("use_mcp", True),
            )
        )
    except PoseExtractionError as pe:
        # 신뢰도 가드 — 토론 미진입(쓰레기 입력 차단). UI 가 에러 배너로 표시.
        print(f"POSE_GUARD: {pe}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"PIPELINE_ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    print("PIPELINE_OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
