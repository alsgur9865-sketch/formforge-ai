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
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

# 스크립트 직접 실행(`python agents/orchestrator.py`) 시 sys.path[0]=agents/ 라서
# `from agents.x` 가 'agents' 패키지를 못 찾는다. 프로젝트 루트를 sys.path 끝에 추가.
# ⚠️ insert(0) 가 아니라 append: 루트의 mcp/ 폴더가 PyPI mcp 패키지를 shadow 하지
#    않도록 site-packages 뒤에 둔다 (import mcp → 진짜 패키지를 먼저 발견).
_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.append(_ROOT)

from google.adk.agents import ParallelAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agents.encourager import create_encourager_agent
from agents.scrutinizer import create_scrutinizer_agent

if TYPE_CHECKING:  # 타입 힌트 전용 (런타임 import 회피 — e2e 함수는 lazy import)
    from agents.debate import DebateResult
    from agents.mediator import MediatorOutput


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


# ===========================================================================
# End-to-end 세션 — 토론 → 합의(Mediator+MCP) → Firestore 저장 (Day 9 e2e 통합)
# ===========================================================================

@dataclass
class FullSessionResult:
    """전체 세션 결과 (토론 + Mediator 합의)."""
    debate: "DebateResult"
    mediator: "MediatorOutput"
    mediator_latency_seconds: float
    mcp_tool_calls: list[str]
    total_latency_seconds: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "debate": self.debate.as_dict(),
            "mediator": self.mediator.as_dict(),
            "mediator_latency_seconds": self.mediator_latency_seconds,
            "mcp_tool_calls": self.mcp_tool_calls,
            "total_latency_seconds": self.total_latency_seconds,
        }


class PoseExtractionError(Exception):
    """
    PoseExtractor 가 신뢰도 가드/실패로 error dict 를 반환했을 때 던지는 예외.

    토론 단계로 쓰레기 입력(rep 0개 / 무릎 신뢰도 낮음 / Gemini 실패)을
    넘기지 않기 위한 방어. caller(CLI·UI)가 `.payload` 로 error_code·message 표시.
    """

    def __init__(self, error_payload: dict[str, Any]):
        self.payload = error_payload
        super().__init__(
            f"{error_payload.get('error_code')}: {error_payload.get('message')}"
        )


@dataclass
class E2EResult:
    """
    완전 end-to-end 결과 — PoseExtractor(영상 멀티모달 해석) + 토론/합의 세션.

    차별화 #4 (Multi-modal × Multi-agent) 의 실증: 한 영상이 PoseExtractor 에서
    pose_data 로 변환되고, 그 결과를 두 코치가 서로 다른 관점으로 토론한다.
    """
    pose_extraction: dict[str, Any]      # run_pose_extractor 출력 (= 토론 입력 pose_data)
    session: "FullSessionResult"          # 토론 → 합의 → Firestore
    pose_latency_seconds: float
    total_latency_seconds: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "pose_extraction": self.pose_extraction,
            "session": self.session.as_dict(),
            "pose_latency_seconds": self.pose_latency_seconds,
            "total_latency_seconds": self.total_latency_seconds,
        }


_PHOENIX_REGISTERED = False


def _ensure_phoenix_registered() -> bool:
    """
    Phoenix 자동계측(register + GoogleADKInstrumentor)을 1회만 등록 (idempotent).

    - 이미 등록됐으면 즉시 True.
    - PHOENIX_API_KEY 없으면 False (계측 비활성 — trace_id 무효지만 파이프라인은 동작).
    - register/instrument 실패해도 예외를 삼키고 False (fail-soft, P1 best-effort).

    run_full_session 에서 호출 → mediator ADK span 이 Phoenix Cloud 로 송출되고
    OTel trace_id 가 유효해진다 (B-1: trace_id 를 Firestore 에 저장하기 위함).
    """
    global _PHOENIX_REGISTERED
    if _PHOENIX_REGISTERED:
        return True
    api_key = os.getenv("PHOENIX_API_KEY")
    if not api_key:
        return False
    try:
        from openinference.instrumentation.google_adk import GoogleADKInstrumentor
        from phoenix.otel import register

        endpoint = (
            os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "https://app.phoenix.arize.com")
            .rstrip("/")
            + "/v1/traces"
        )
        tracer_provider = register(
            project_name=os.getenv("PHOENIX_PROJECT_NAME", "formforge-prod"),
            endpoint=endpoint,
            headers={"api_key": api_key},
        )
        GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)
        _PHOENIX_REGISTERED = True
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"⚠️  Phoenix register 실패 (계측 없이 계속): {type(exc).__name__}: {exc}")
        return False


async def run_full_session(
    pose_data: dict[str, Any],
    user_context: dict[str, Any],
    *,
    persona_state: dict[str, Any] | None = None,
    user_id: str | None = None,
    max_rounds: int | None = None,
    debate_id: str | None = None,
    video_uri: str | None = None,
    exercise_type: str | None = None,
    use_mcp: bool = True,
) -> FullSessionResult:
    """
    전체 파이프라인 1회 실행: 토론 → 합의 → (옵션) Firestore consensus 저장.

    영상 없이 sample pose_data 로 end-to-end 골격 검증 가능 (PoseExtractor 는 Day 5 합류).

    Args:
        pose_data: PoseExtractor 출력 (현재 caller 제공).
        user_context: { user_id, injury_history, experience_level, persona_state? }
        debate_id: 제공되면 토론 라운드 push + Mediator consensus 저장 (fail-soft).
        use_mcp: True → Mediator 가 Phoenix MCP introspection 자동 호출 (P4).
                 False → output_schema 스켈레톤 Mediator (MCP 없음, 폴백).

    Returns:
        FullSessionResult — DebateResult + MediatorOutput + MCP tool 호출 목록.
    """
    # lazy import — test_orchestrator(run_round1) 가 debate/mediator/MCP 체인을
    # 로드하지 않도록. mediator 의 MCP import 도 함수 내부라 mcp/ shadow 안전.
    from agents.debate import run_debate
    from agents.mediator import run_mediator, run_mediator_with_mcp
    from opentelemetry import trace as _otel_trace

    # P1 + B-1: Phoenix 자동계측 등록(1회). 미등록이면 OTel trace_id 가 0(무효)이라
    # trace_ids 저장이 의미 없으므로 여기서 보장. 실패해도 fail-soft.
    _ensure_phoenix_registered()
    _tracer = _otel_trace.get_tracer("formforge.orchestrator")

    total_start = time.monotonic()

    # 1) 멀티라운드 토론 (+ debate_id 면 Firestore 라운드 push)
    debate_result = await run_debate(
        pose_data=pose_data,
        user_context=user_context,
        persona_state=persona_state,
        user_id=user_id,
        max_rounds=max_rounds,
        debate_id=debate_id,
        video_uri=video_uri,
        exercise_type=exercise_type,
    )

    # 2) Mediator 합의 (Phoenix MCP introspection).
    #    명시적 span 으로 감싸 mediator ADK trace 의 trace_id 를 추출 (B-1).
    #    run_mediator_* 내부 ADK span 들이 이 span 의 자식(같은 trace)이 된다.
    mediator_trace_id: str | None = None
    with _tracer.start_as_current_span("mediator_consensus") as _mspan:
        _ctx = _mspan.get_span_context()
        if _ctx and _ctx.trace_id:  # 0 = INVALID_TRACE_ID(미등록) → None 유지
            mediator_trace_id = format(_ctx.trace_id, "032x")
        if use_mcp:
            try:
                mediator_out, med_latency, tool_calls = await run_mediator_with_mcp(
                    debate_result.as_dict(), pose_data, user_context
                )
            except Exception as mcp_exc:  # noqa: BLE001
                # MCP 서버 다운/연결 실패 → MCP 없는 Mediator 로 fallback (앱이 안 죽음).
                # ARCHITECTURE §5.3 / Task 12.3: Phoenix 에 경고 기록 + 토론은 그대로 합의.
                _mspan.set_attribute("mcp.fallback", True)
                _mspan.set_attribute(
                    "mcp.fallback_reason",
                    f"{type(mcp_exc).__name__}: {mcp_exc}"[:500],  # OTel attr 길이 가드
                )
                _mspan.add_event("mcp_unavailable_fallback")
                print(
                    f"⚠️  MCP 호출 실패 → MCP 없는 Mediator fallback (앱 계속): "
                    f"{type(mcp_exc).__name__}: {mcp_exc}"
                )
                mediator_out, med_latency = await run_mediator(
                    debate_result.as_dict(), pose_data, user_context
                )
                tool_calls = []
        else:
            mediator_out, med_latency = await run_mediator(
                debate_result.as_dict(), pose_data, user_context
            )
            tool_calls = []

    # 3) Firestore 에 합의 저장 (fail-soft — 저장 실패가 결과 반환을 막지 않음).
    #    trace_ids 에 mediator trace_id 실저장 → 다음 토론의 query_past_debates 가
    #    실제 trace_id 를 반환하고, Phoenix REST 로 그 trace 를 다시 조회할 수 있다 (P4).
    if debate_id:
        try:
            from storage import firestore_client

            trace_ids: dict[str, str] = {}
            if mediator_trace_id:
                trace_ids["mediator_trace_id"] = mediator_trace_id
            firestore_client.set_debate_consensus(
                debate_id=debate_id,
                consensus=mediator_out.as_dict(),
                trace_ids=trace_ids,
            )
        except Exception as e:  # noqa: BLE001
            print(
                f"⚠️  Firestore set_debate_consensus 실패 (fail-soft): "
                f"{type(e).__name__}: {e}"
            )

    total_latency = time.monotonic() - total_start
    return FullSessionResult(
        debate=debate_result,
        mediator=mediator_out,
        mediator_latency_seconds=med_latency,
        mcp_tool_calls=tool_calls,
        total_latency_seconds=total_latency,
    )


async def run_full_e2e(
    video_uri: str,
    user_context: dict[str, Any],
    *,
    exercise_type: str = "squat",
    persona_state: dict[str, Any] | None = None,
    user_id: str | None = None,
    max_rounds: int | None = None,
    debate_id: str | None = None,
    use_mcp: bool = True,
) -> E2EResult:
    """
    완전 end-to-end: 영상 → PoseExtractor(2-stage) → 토론 → 합의(Mediator+MCP) → Firestore.

    run_full_session 앞에 PoseExtractor 를 prepend 한 형태. sample pose_data 대신
    실제 영상에서 추출한 pose_data 를 토론에 흘린다 (Task 4.1 Phase 2).

    Args:
        video_uri: 로컬 경로 또는 gs:// URI.
        user_context: { user_id, injury_history, experience_level, persona_state? }
                      PoseExtractor(injury 기반 severity 상향)와 토론 양쪽에 동일 전달.
        exercise_type: "squat" 등. PoseExtractor + Firestore 저장에 사용.
        debate_id: 제공 시 Firestore 에 pose_data/라운드/합의 저장 (fail-soft).
        use_mcp: Mediator 의 Phoenix MCP introspection 자동 호출 (P4).

    Returns:
        E2EResult — pose_extraction(영상 해석) + FullSessionResult(토론/합의).

    Raises:
        PoseExtractionError: PoseExtractor 가 신뢰도 가드/실패로 error dict 반환 시.
                             이 경우 토론 단계로 진입하지 않는다 (쓰레기 입력 차단).
    """
    # lazy import — cv2/mediapipe 가 무거우므로 test_orchestrator(run_round1) 가
    # 이 체인을 로드하지 않도록 함수 내부에서 import.
    from agents.pose_extractor import run_pose_extractor

    total_start = time.monotonic()

    # 1) PoseExtractor — blocking(cv2 + mediapipe + gemini) 이므로 to_thread 로
    #    이벤트 루프를 막지 않게 별도 스레드에서 실행.
    pose_start = time.monotonic()
    pose_result = await asyncio.to_thread(
        run_pose_extractor, video_uri, exercise_type, user_context
    )
    pose_latency = time.monotonic() - pose_start

    # 2) 신뢰도 가드 — error dict 면 토론 진입 안 함 (P5: 거짓 분석 방지).
    if pose_result.get("error"):
        raise PoseExtractionError(pose_result)

    # 3) 추출된 pose_data 를 그대로 토론 세션에 전달 (스키마 호환 — ARCHITECTURE §2.1).
    #    PoseExtractor 출력은 sample_pose_data 와 동일 구조 + camera_angle/reasoning 추가.
    session = await run_full_session(
        pose_data=pose_result,
        user_context=user_context,
        persona_state=persona_state,
        user_id=user_id,
        max_rounds=max_rounds,
        debate_id=debate_id,
        video_uri=video_uri,
        exercise_type=pose_result.get("exercise_type", exercise_type),
        use_mcp=use_mcp,
    )

    total_latency = time.monotonic() - total_start
    return E2EResult(
        pose_extraction=pose_result,
        session=session,
        pose_latency_seconds=pose_latency,
        total_latency_seconds=total_latency,
    )


# ---------------------------------------------------------------------------
# CLI 데모 (옵션)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    import sys
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    if os.getenv("GEMINI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]

    sample_path = Path(__file__).resolve().parent.parent / "tests" / "sample_pose_data.json"
    if not sample_path.exists():
        print(f"❌ sample_pose_data.json 없음: {sample_path}", file=sys.stderr)
        sys.exit(1)

    with sample_path.open(encoding="utf-8") as f:
        sample_pose = json.load(f)

    user_ctx = {
        "user_id": "user_001",
        "injury_history": ["lower_back_strain_2025"],
        "experience_level": "intermediate",
    }

    # ---- 완전 e2e: 영상 → PoseExtractor → 토론 → 합의 → Firestore (Task 4.1 Phase 2) ----
    if "--e2e" in sys.argv:
        # 영상 경로: `--e2e <video>` 위치 인자, 없으면 기본 샘플 영상.
        video_path: str | None = None
        for i, a in enumerate(sys.argv):
            if a == "--e2e" and i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith("-"):
                video_path = sys.argv[i + 1]
                break
        if not video_path:
            video_path = str(
                Path(__file__).resolve().parent.parent
                / "data" / "sample_videos" / "squat_demo.mp4"
            )
        if not Path(video_path).exists():
            print(f"❌ 영상 없음: {video_path}", file=sys.stderr)
            sys.exit(1)

        debate_id = f"e2e_video_{int(time.time())}"
        try:
            e2e = asyncio.run(
                run_full_e2e(
                    video_uri=video_path,
                    user_context=user_ctx,
                    exercise_type="squat",
                    debate_id=debate_id,
                    use_mcp=True,
                )
            )
        except PoseExtractionError as pe:
            print(f"\n❌ PoseExtractor 신뢰도 가드 — 토론 미진입: {pe}", file=sys.stderr)
            print(json.dumps(pe.payload, ensure_ascii=False, indent=2))
            raise SystemExit(1)

        fs = e2e.session
        pose = e2e.pose_extraction
        print(
            f"\n⏱  Total {e2e.total_latency_seconds:.1f}s "
            f"(pose {e2e.pose_latency_seconds:.1f}s + session {fs.total_latency_seconds:.1f}s, "
            f"mediator {fs.mediator_latency_seconds:.1f}s)"
        )
        print(
            f"🎥 PoseExtractor: camera_angle={pose.get('camera_angle')}, "
            f"rep_count={pose.get('rep_count')}, "
            f"form_score={pose.get('overall_metrics', {}).get('form_score_0_100')}, "
            f"safety_flags={len(pose.get('safety_flags', []))}개"
        )
        print(
            f"🔁 라운드 {len(fs.debate.rounds)} / converged={fs.debate.converged} "
            f"/ shared_issue={fs.debate.shared_issue}"
        )
        print(f"🧰 MCP tool calls: {fs.mcp_tool_calls}")
        print("\n🧑‍⚖️ MEDIATOR 합의:")
        print(json.dumps(fs.mediator.as_dict(), ensure_ascii=False, indent=2))

        snap = None
        try:
            from storage import firestore_client

            snap = firestore_client.get_debate_snapshot(debate_id)
        except Exception as e:  # noqa: BLE001
            print(f"(Firestore 확인 실패: {type(e).__name__}: {e})")

        checks = {
            "PoseExtractor rep ≥1": pose.get("rep_count", 0) >= 1,
            "PoseExtractor camera_angle 판단": pose.get("camera_angle")
            in ("side", "front", "angled", "unknown"),
            "토론 라운드 ≥1": len(fs.debate.rounds) >= 1,
            "Mediator consensus 생성": bool(fs.mediator.consensus.strip()),
            "MCP tool 자동 호출": len(fs.mcp_tool_calls) >= 1,
            "P5 의료 면책": "의학 조언" in fs.mediator.disclaimer,
            "Firestore pose_data 저장": bool(snap and snap.get("pose_data")),
            "Firestore consensus 저장": bool(snap and snap.get("consensus")),
        }
        print(f"\n=== 완전 e2e acceptance (debate_id={debate_id}) ===")
        for name, ok in checks.items():
            print(f"  {'✅' if ok else '❌'} {name}")
        all_ok = all(checks.values())
        print(
            f"\n{'✅ 완전 e2e 통과 (영상 → PoseExtractor → 토론 → 합의 → 저장)' if all_ok else '❌ 미충족 항목 있음'}"
        )
        raise SystemExit(0 if all_ok else 1)

    # ---- e2e 전체 세션: 토론 → 합의(MCP) → Firestore (Day 9 통합, sample pose_data) ----
    if "--full" in sys.argv:
        debate_id = f"e2e_demo_{int(time.time())}"
        fs = asyncio.run(
            run_full_session(
                pose_data=sample_pose,
                user_context=user_ctx,
                debate_id=debate_id,
                exercise_type=sample_pose.get("exercise_type", "squat"),
                use_mcp=True,
            )
        )
        print(
            f"\n⏱  Total {fs.total_latency_seconds:.1f}s "
            f"(mediator {fs.mediator_latency_seconds:.1f}s)"
        )
        print(
            f"🔁 라운드 {len(fs.debate.rounds)} / converged={fs.debate.converged} "
            f"/ shared_issue={fs.debate.shared_issue}"
        )
        print(f"🧰 MCP tool calls: {fs.mcp_tool_calls}")
        print("\n🧑‍⚖️ MEDIATOR 합의:")
        print(json.dumps(fs.mediator.as_dict(), ensure_ascii=False, indent=2))

        # Firestore consensus 저장 확인
        snap = None
        try:
            from storage import firestore_client

            snap = firestore_client.get_debate_snapshot(debate_id)
        except Exception as e:  # noqa: BLE001
            print(f"(Firestore 확인 실패: {type(e).__name__}: {e})")

        checks = {
            "토론 라운드 ≥1": len(fs.debate.rounds) >= 1,
            "Mediator consensus 생성": bool(fs.mediator.consensus.strip()),
            "MCP tool 자동 호출": len(fs.mcp_tool_calls) >= 1,
            "P5 의료 면책": "의학 조언" in fs.mediator.disclaimer,
            "Firestore consensus 저장": bool(snap and snap.get("consensus")),
            "Firestore status=feedback_pending": bool(
                snap and snap.get("status") == "feedback_pending"
            ),
            "Firestore trace_ids 저장(B-1)": bool(snap and snap.get("trace_ids")),
        }
        print(f"\n=== e2e acceptance (debate_id={debate_id}) ===")
        for name, ok in checks.items():
            print(f"  {'✅' if ok else '❌'} {name}")
        if snap:
            print(f"  🔗 저장된 trace_ids = {snap.get('trace_ids')}")
        all_ok = all(checks.values())
        print(f"\n{'✅ e2e 파이프라인 통과' if all_ok else '❌ 미충족 항목 있음'}")
        raise SystemExit(0 if all_ok else 1)

    # ---- 기존 Round 1 데모 ----
    result = asyncio.run(
        run_round1(
            pose_data=sample_pose,
            user_context=user_ctx,
        )
    )

    print(f"\n⏱  Latency: {result.latency_seconds:.1f}s")
    print("\n📣 ENCOURAGER:")
    print(json.dumps(result.encourager, ensure_ascii=False, indent=2))
    print("\n🔬 SCRUTINIZER:")
    print(json.dumps(result.scrutinizer, ensure_ascii=False, indent=2))
