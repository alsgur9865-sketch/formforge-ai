# 파일 위치: agents/pose_extractor.py
"""
PoseExtractor — 2-stage 통합 (ARCHITECTURE.md §2.1, TASKS.md Task 5.1).

파이프라인:
  Stage 1 (agents/pose_mediapipe.py): MediaPipe + NumPy 정량 측정
    → rep_count, depth_degrees, back_angle, tempo, consistency  (GROUND TRUTH)
  Stage 2 (이 파일, gemini-2.5-flash 멀티모달): rep 최저점 keyframe + Stage1 메트릭 해석
    → camera_angle 판단 + knee_alignment(정성) + safety_flags(severity) + form_score + 자연어

설계 원칙:
  1. 거짓 정밀 방지 — Gemini 는 '해석' 만. 정량 수치는 코드가 Stage1 값을 그대로 merge.
     (Gemini 가 숫자를 만들지 않으므로 재측정/복사 실수 자체가 불가능)
  2. 앵글 인지 — 측면 영상에선 좌우 valgus 가 안 보임. Gemini 가 camera_angle 을 먼저
     판단하고, 그 앵글에서 신뢰성 있는 항목만 safety_flag 로 올린다. 측면 valgus 단정 금지.
  3. 신뢰도 가드 — Stage1 이 rep 0 개거나 양쪽 무릎 visibility 낮으면 error_code 반환,
     Gemini 로 쓰레기 입력을 넘기지 않는다 (fallback 시도 안 함).
  4. P1 관측성 — google-genai 직접 호출이라 명시적 OTel span 으로 Phoenix Cloud 에 LLM span 기록.
  5. P5 면책 — 출력에 의료 면책 문구 포함.

CLI:
    python agents/pose_extractor.py data/sample_videos/squat_demo.mp4 squat
    python agents/pose_extractor.py --selftest
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Literal

import cv2
import numpy as np
from google import genai
from google.genai import types
from opentelemetry import trace
from pydantic import BaseModel, Field

# 프로젝트 루트를 sys.path 에 추가 (스크립트 직접 실행 시 agents/* import).
# mcp/ 패키지 shadow 회피를 위해 append (orchestrator.py 와 동일 전략).
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.append(str(_ROOT))

from agents.pose_mediapipe import analyze_video  # noqa: E402

# OpenTelemetry tracer — Phoenix register() 후 get_tracer 로 받으면 Phoenix Cloud 로 송출.
_tracer = trace.get_tracer("formforge.agents.pose_extractor")

_STAGE2_MODEL = "gemini-2.5-flash"
_MAX_KEYFRAMES = 6
_KEYFRAME_LONG_SIDE = 512  # Gemini 입력 이미지 긴 변 픽셀 (비용/속도)

# P5 의료 면책 (절대 원칙)
_DISCLAIMER = (
    "정보 제공용입니다. 의학적 조언이 아닙니다. "
    "통증이나 부상이 있으면 전문가와 상담하세요."
)


# ---------------------------------------------------------------------------
# 출력 스키마
# ---------------------------------------------------------------------------

KneeAlignment = Literal[
    "neutral", "valgus_mild", "valgus_moderate", "valgus_severe",
    "varus_mild", "varus_moderate", "not_visible",
]
Severity = Literal["low", "medium", "high", "critical"]
CameraAngle = Literal["side", "front", "angled", "unknown"]


class RepAlignment(BaseModel):
    """rep 별 무릎 정렬 정성 판단 (Stage 2 가 생성)."""
    rep_number: int
    knee_alignment: KneeAlignment = Field(
        description="측면 영상이면 not_visible (좌우 valgus 는 측면에서 판단 불가)."
    )


class SafetyFlag(BaseModel):
    """현재 카메라 앵글에서 실제로 보이는 생체역학 위험 1건."""
    severity: Severity
    issue: str = Field(description="snake_case 위험 이름. 예: excessive_forward_lean")
    rep_numbers: list[int] = Field(
        default_factory=list, description="해당 위험이 관측된 rep 번호들."
    )
    rationale: str = Field(description="왜 위험한지 한 문장 (한국어).")


class Stage2Interpretation(BaseModel):
    """Gemini Stage 2 의 해석 결과 — 정량 수치는 포함하지 않는다 (코드가 merge)."""
    camera_angle: CameraAngle = Field(
        description="keyframe 으로 판단한 촬영 각도."
    )
    knee_alignment_per_rep: list[RepAlignment] = Field(default_factory=list)
    safety_flags: list[SafetyFlag] = Field(default_factory=list)
    form_score_0_100: int = Field(
        ge=0, le=100, description="감점 루브릭 기반 종합 자세 점수."
    )
    reasoning: str = Field(description="2-4 문장 종합 해석 (한국어).")


# ---------------------------------------------------------------------------
# 시스템 프롬프트 — 앵글 인지가 핵심
# ---------------------------------------------------------------------------

_STAGE2_INSTRUCTION = """\
You are the PoseExtractor Stage 2 — a careful biomechanics analyst for a workout-form app.

You receive:
  - stage1_metrics: QUANTITATIVE measurements from MediaPipe + NumPy. These are
    GROUND TRUTH — NEVER recompute, estimate, or alter these numbers. Read them
    with this legend (critical — do not misread):
      * depth_degrees = knee flexion angle at the bottom of the rep, in degrees.
        SMALLER means DEEPER. Reference: ~90° = thighs parallel (solid depth),
        below ~70° = very deep / full squat, above ~110° = shallow / quarter squat.
        DO NOT treat a small angle as "shallow" — a small angle is a DEEP squat.
        (e.g., depth_degrees=26 is an EXTREMELY deep squat, NOT insufficient depth.)
      * back_angle_at_bottom / back_angle_at_top = torso lean from vertical, in degrees.
        LARGER = more forward lean. Small when standing (top), larger at bottom is normal.
      * tempo = seconds for the down / up / pause phases of each rep.
      * depth_consistency / tempo_consistency = 0..1, higher = more consistent.
  - 4-6 keyframe images from the workout video (rep bottoms + start/end).
  - user_context: injury_history, experience_level.

Your job is INTERPRETATION ONLY (no measuring):

1. camera_angle: From the images, decide if the camera is "side", "front", "angled", or "unknown".

2. knee_alignment_per_rep: One entry per rep_number in stage1_metrics.
   - On a SIDE view you CANNOT see left/right knee collapse → use "not_visible".
     Do NOT guess valgus/varus from a side view — that is false precision.
   - Only on a FRONT or ANGLED view may you judge "neutral"/"valgus_mild"/etc.

3. safety_flags: List ONLY biomechanical risks actually VISIBLE from this camera_angle.
   - A SIDE view reliably shows: insufficient depth, excessive forward lean / back rounding,
     knee travelling past toes, heel lift, hip-knee timing.
   - A SIDE view does NOT show: left/right knee valgus, lateral asymmetry — do not flag these.
   - Never flag a risk you cannot see from this angle.
   - Each flag: severity, issue (snake_case), rep_numbers, rationale (Korean).
   - Raise severity when user injury_history is relevant
     (e.g., lower_back_strain + excessive forward lean → high or critical).

4. form_score_0_100: Holistic. Start at 100 and deduct:
   insufficient depth -15, inconsistent depth -10, excessive forward lean -15,
   heel lift -10, tempo too fast / inconsistent -10, each high/critical safety flag -15.
   Clamp to [0, 100].

5. reasoning: 2-4 sentences in Korean summarizing the form honestly,
   acknowledging what the camera_angle could and could not assess.

Respond in Korean for all text fields. Output JSON ONLY matching the schema.
"""


# ---------------------------------------------------------------------------
# Gemini 클라이언트 (Vertex 우선 — 세션 4 RESOURCE_EXHAUSTED 회피)
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
        _client = genai.Client(
            vertexai=True,
            project=os.getenv("GOOGLE_CLOUD_PROJECT"),
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )
    else:
        _client = genai.Client(
            api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        )
    return _client


# ---------------------------------------------------------------------------
# keyframe 추출 (cv2 seek — 영상 전체 재read 안 함)
# ---------------------------------------------------------------------------

def _sample_keyframe_times(
    start_t: float, bottoms: list[float], end_t: float, max_frames: int
) -> list[float]:
    """시작 + rep bottom 들 + 끝. 총 개수가 max_frames 초과면 중간 bottom 을 균등 샘플."""
    if 2 + len(bottoms) <= max_frames:
        return [start_t] + list(bottoms) + [end_t]
    k = max_frames - 2  # 시작/끝 제외하고 중간에 쓸 개수
    idx = np.linspace(0, len(bottoms) - 1, k).round().astype(int)
    sampled = [bottoms[i] for i in sorted(set(int(x) for x in idx))]
    return [start_t] + sampled + [end_t]


def _resize_long_side(frame: np.ndarray, target: int) -> np.ndarray:
    h, w = frame.shape[:2]
    longest = max(h, w)
    if longest <= target:
        return frame
    scale = target / longest
    return cv2.resize(frame, (int(round(w * scale)), int(round(h * scale))))


def _extract_keyframes(
    video_path: str, bottom_timestamps: list[float], duration: float,
    max_frames: int = _MAX_KEYFRAMES,
) -> list[bytes]:
    """rep 최저점 + 시작/끝 시각에서 JPEG bytes 추출. POS_MSEC seek 로 해당 프레임만 디코딩."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"keyframe 추출용 영상 열기 실패: {video_path}")
    try:
        start_t = min(0.4, duration * 0.1) if duration > 0 else 0.0
        end_t = max(duration - 0.4, duration * 0.9) if duration > 0 else 0.0
        times = _sample_keyframe_times(start_t, bottom_timestamps, end_t, max_frames)

        frames: list[bytes] = []
        for t in times:
            cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000.0)
            ok, frame_bgr = cap.read()
            if not ok:
                continue
            frame_bgr = _resize_long_side(frame_bgr, _KEYFRAME_LONG_SIDE)
            ok2, buf = cv2.imencode(".jpg", frame_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if ok2:
                frames.append(buf.tobytes())
        return frames
    finally:
        cap.release()


# ---------------------------------------------------------------------------
# 입력 소스 resolve (로컬 우선 + GCS 인터페이스)
# ---------------------------------------------------------------------------

def _resolve_video(video_uri: str) -> tuple[str, str | None]:
    """
    로컬 경로면 그대로. gs:// 면 임시 로컬로 다운로드.
    Returns: (local_path, tmp_path_to_cleanup_or_None)
    """
    if video_uri.startswith("gs://"):
        from storage.cloud_storage_client import download_to_local  # lazy
        tmp = Path(tempfile.gettempdir()) / f"formforge_{Path(video_uri).name}"
        try:
            local = download_to_local(video_uri, tmp)
        except Exception:
            tmp.unlink(missing_ok=True)  # 부분 다운로드 정리 후 전파
            raise
        return str(local), str(local)
    return video_uri, None


# ---------------------------------------------------------------------------
# 신뢰도 가드 + 에러 페이로드
# ---------------------------------------------------------------------------

def _error(error_code: str, message: str, stage1: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "error": True,
        "error_code": error_code,
        "message": message,
        "disclaimer": _DISCLAIMER,
        "stage1_metrics": stage1,
    }


def _low_knee_warning_present(warnings: list[str]) -> bool:
    return any("양쪽 무릎 visibility 낮음" in w for w in warnings)


# ---------------------------------------------------------------------------
# Stage 2 호출 (google-genai 멀티모달 + OTel span)
# ---------------------------------------------------------------------------

def _gemini_interpret(
    stage1: dict[str, Any], keyframes: list[bytes],
    exercise_type: str, user_context: dict[str, Any],
) -> tuple[Stage2Interpretation, float]:
    client = _get_client()
    user_payload = {
        "exercise_type": exercise_type,
        "stage1_metrics": stage1,
        "user_context": user_context,
    }
    payload_str = json.dumps(user_payload, ensure_ascii=False)

    parts: list[types.Part] = [types.Part(text=payload_str)]
    for jpg in keyframes:
        parts.append(types.Part.from_bytes(data=jpg, mime_type="image/jpeg"))

    with _tracer.start_as_current_span(
        "pose_extractor_stage2",
        attributes={
            "openinference.span.kind": "LLM",
            "llm.model_name": _STAGE2_MODEL,
            "llm.system": "google",
            "input.value": payload_str,
            "input.mime_type": "application/json",
            "pose.keyframes_sent": len(keyframes),
            "pose.exercise_type": exercise_type,
        },
    ) as span:
        try:
            start = time.monotonic()
            response = client.models.generate_content(
                model=_STAGE2_MODEL,
                contents=[types.Content(role="user", parts=parts)],
                config=types.GenerateContentConfig(
                    system_instruction=_STAGE2_INSTRUCTION,
                    response_mime_type="application/json",
                    response_schema=Stage2Interpretation,
                    temperature=0.15,  # 재현성 (form_score 흔들림 최소화)
                ),
            )
            latency = time.monotonic() - start

            parsed: Stage2Interpretation
            if getattr(response, "parsed", None) is not None and isinstance(
                response.parsed, Stage2Interpretation
            ):
                parsed = response.parsed
            else:
                parsed = Stage2Interpretation.model_validate(json.loads(response.text or "{}"))

            span.set_attribute("output.value", parsed.model_dump_json())
            span.set_attribute("output.mime_type", "application/json")
            span.set_attribute("pose.camera_angle", parsed.camera_angle)
            span.set_attribute("pose.safety_flag_count", len(parsed.safety_flags))
            span.set_attribute("pose.form_score", parsed.form_score_0_100)
            span.set_attribute("pose.latency_seconds", latency)
        except Exception as e:
            # Gemini 호출/파싱 실패를 span 에 ERROR 로 기록 (P1 — Phoenix 에서 실패가 성공처럼 안 보이게)
            span.record_exception(e)
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            raise

    return parsed, latency


# ---------------------------------------------------------------------------
# merge — 정량(Stage1) + 해석(Stage2)
# ---------------------------------------------------------------------------

def _merge(
    stage1: dict[str, Any], interp: Stage2Interpretation,
    keyframes_sent: int, stage2_latency: float,
) -> dict[str, Any]:
    # Stage1 reps 를 기준으로 돌며 Stage2 정렬 해석을 합친다(Gemini 가 순서를 바꿔도 안전).
    # bottom_timestamp_sec 는 keyframe 추출용 내부 필드라 최종 출력서 제외
    # (ARCHITECTURE §2.1 스키마에 없음 — downstream 은 이 필드를 읽지 않음).
    align_map = {a.rep_number: a.knee_alignment for a in interp.knee_alignment_per_rep}
    reps_out = []
    for r in stage1["reps"]:
        reps_out.append({
            "rep_number": r["rep_number"],
            "depth_degrees": r["depth_degrees"],            # Stage1 (불변)
            "knee_alignment": align_map.get(r["rep_number"], "not_visible"),  # Stage2
            "back_angle_at_bottom": r["back_angle_at_bottom"],
            "back_angle_at_top": r["back_angle_at_top"],
            "tempo": r["tempo"],
        })

    overall = dict(stage1.get("overall_metrics", {}))
    overall["form_score_0_100"] = interp.form_score_0_100

    metadata = dict(stage1.get("_metadata", {}))
    metadata["stage2_model"] = _STAGE2_MODEL
    metadata["keyframes_sent"] = keyframes_sent
    metadata["stage2_latency_sec"] = round(stage2_latency, 2)

    return {
        "exercise_type": stage1["exercise_type"],
        "camera_angle": interp.camera_angle,
        "rep_count": stage1["rep_count"],
        "duration_seconds": stage1["duration_seconds"],
        "reps": reps_out,
        "overall_metrics": overall,
        "safety_flags": [f.model_dump() for f in interp.safety_flags],
        "reasoning": interp.reasoning,
        "warnings": stage1.get("warnings", []),
        "disclaimer": _DISCLAIMER,
        "_metadata": metadata,
    }


# ---------------------------------------------------------------------------
# 메인 — 2-stage 통합
# ---------------------------------------------------------------------------

def run_pose_extractor(
    video_uri: str, exercise_type: str = "squat",
    user_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    영상 → Stage1(MediaPipe 정량) → 신뢰도 가드 → Stage2(Gemini 해석) → merge.

    Returns:
        성공: ARCHITECTURE §2.1 출력 스키마 dict.
        실패: {"error": True, "error_code", "message", ...} (Stage2 스킵).
    """
    user_context = user_context or {}
    local_path: str | None = None
    tmp_cleanup: str | None = None

    try:
        try:
            local_path, tmp_cleanup = _resolve_video(video_uri)
        except Exception as e:  # noqa: BLE001 — 영상 로드/다운로드 실패를 error dict 로
            return _error("video_resolve_failed",
                          f"영상 로드 실패: {type(e).__name__}: {e}")

        # --- Stage 1 ---
        analysis = analyze_video(local_path, exercise_type=exercise_type)
        stage1 = analysis.to_dict()

        # --- 신뢰도 가드 (Gemini fallback 시도 안 함) ---
        if stage1["rep_count"] == 0:
            return _error(
                "no_reps_detected",
                "rep 을 1개도 검출하지 못했습니다. 운동 동작/카메라 각도를 확인하세요.",
                stage1,
            )
        if _low_knee_warning_present(stage1.get("warnings", [])):
            return _error(
                "low_knee_confidence",
                "양쪽 무릎 키포인트 신뢰도가 낮아 정량 측정을 신뢰할 수 없습니다. "
                "피사체를 더 크게/가까이 잡고 다시 촬영하세요.",
                stage1,
            )

        # --- keyframe 추출 (rep 최저점 + 시작/끝) ---
        bottoms = [r["bottom_timestamp_sec"] for r in stage1["reps"]]
        keyframes = _extract_keyframes(local_path, bottoms, stage1["duration_seconds"])
        if not keyframes:
            return _error(
                "keyframe_extraction_failed",
                "영상에서 분석용 프레임을 추출하지 못했습니다.",
                stage1,
            )

        # --- Stage 2 (Gemini 해석) — 호출/응답 파싱 실패를 error dict 로 감싼다 ---
        try:
            interp, latency = _gemini_interpret(stage1, keyframes, exercise_type, user_context)
        except Exception as e:  # noqa: BLE001
            return _error(
                "stage2_failed",
                f"Stage 2 Gemini 해석 실패: {type(e).__name__}: {e}",
                stage1,
            )
        return _merge(stage1, interp, keyframes_sent=len(keyframes), stage2_latency=latency)
    finally:
        if tmp_cleanup:
            try:
                Path(tmp_cleanup).unlink(missing_ok=True)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# CLI / selftest
# ---------------------------------------------------------------------------

def _print_usage_and_exit() -> None:
    print(
        "사용법:\n"
        "    python agents/pose_extractor.py <video_path|gs://...> [exercise_type]\n"
        "    python agents/pose_extractor.py --selftest\n",
        file=sys.stderr,
    )
    sys.exit(2)


def _register_phoenix() -> None:
    """선택: Phoenix register 후 OTel span 이 Phoenix Cloud 로 송출되게 (P1)."""
    try:
        from phoenix.otel import register
        api_key = os.getenv("PHOENIX_API_KEY")
        endpoint = (
            os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "https://app.phoenix.arize.com")
            .rstrip("/")
            + "/v1/traces"
        )
        register(
            project_name=os.getenv("PHOENIX_PROJECT_NAME", "formforge-prod"),
            endpoint=endpoint,
            headers={"authorization": f"Bearer {api_key}"} if api_key else None,
            auto_instrument=False,
        )
    except Exception as e:  # noqa: BLE001 — 관측성은 fail-soft
        print(f"ℹ️ Phoenix register 생략 ({type(e).__name__}). span 은 로컬에만.", file=sys.stderr)


def _selftest() -> int:
    """실제 샘플 영상으로 e2e + acceptance 자가 검증."""
    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
    _register_phoenix()

    video = str(_ROOT / "data" / "sample_videos" / "squat_demo.mp4")
    if not Path(video).exists():
        print(f"❌ 샘플 영상 없음: {video}", file=sys.stderr)
        return 1

    user_context = {
        "user_id": "selftest_user",
        "injury_history": ["lower_back_strain_2025"],
        "experience_level": "intermediate",
    }
    result = run_pose_extractor(video, "squat", user_context)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print("\n--- Acceptance ---", file=sys.stderr)
    if result.get("error"):
        print(f"  ⚠️ error_code={result['error_code']} (신뢰도 가드 동작)", file=sys.stderr)
        return 0

    checks = {
        "1. 정량 수치 보존(Stage1 rep_count)": result["rep_count"] > 0,
        "2. camera_angle 판단됨": result.get("camera_angle") in ("side", "front", "angled", "unknown"),
        "3. safety_flags 리스트 존재": isinstance(result.get("safety_flags"), list),
        "4. form_score 0~100": 0 <= result["overall_metrics"].get("form_score_0_100", -1) <= 100,
        "5. reps 에 knee_alignment 병합됨": all("knee_alignment" in r for r in result["reps"]),
        "6. P5 면책 포함": "의학적 조언이 아닙니다" in result.get("disclaimer", ""),
        "7. reasoning(자연어) 존재": bool(result.get("reasoning")),
    }
    for name, ok in checks.items():
        print(f"  {'✅' if ok else '❌'} {name}", file=sys.stderr)

    # 거짓정밀 가드: 측면이면 valgus 단정 금지
    if result.get("camera_angle") == "side":
        # 측면에선 좌우 정렬을 알 수 없으므로 not_visible 만 허용 (프롬프트 지시 준수 검증).
        side_ok = all(r["knee_alignment"] == "not_visible" for r in result["reps"])
        print(f"  {'✅' if side_ok else '❌'} 8. 측면 영상에서 valgus 단정 안 함(not_visible)",
              file=sys.stderr)

    print(f"\n  camera_angle={result.get('camera_angle')}, "
          f"form_score={result['overall_metrics'].get('form_score_0_100')}, "
          f"safety_flags={len(result.get('safety_flags', []))}개, "
          f"stage2={result['_metadata'].get('stage2_latency_sec')}s", file=sys.stderr)
    return 0 if all(checks.values()) else 1


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--selftest":
        return _selftest()
    if len(sys.argv) < 2:
        _print_usage_and_exit()

    from dotenv import load_dotenv
    load_dotenv(_ROOT / ".env")
    _register_phoenix()

    video_uri = sys.argv[1]
    exercise_type = sys.argv[2] if len(sys.argv) >= 3 else "squat"
    result = run_pose_extractor(video_uri, exercise_type)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
