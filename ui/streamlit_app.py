# 파일 위치: ui/streamlit_app.py
"""FormForge AI — 메인 Streamlit 앱 (DESIGN.md "The Diagnostic Freeze-Frame").

플로우: 업로드 → 검증된 Cloud Run Job(formforge-pipeline)을 트리거해 '진짜' 파이프라인 실행
→ Firestore 1초 폴링으로 pose→토론→판결이 순차로 채워지는 걸 렌더 → 피드백(페르소나 진화).
백엔드 import는 지연 처리(데모 모드는 클라우드 불필요).

⚠️ 왜 Job 트리거인가: Streamlit 비-메인 ScriptRunner 스레드 + Cloud Run CPU 스로틀링 안에선
OTel 계측 ADK 토론이 hang/무진척(실측 v7~v9: 스레드·블로킹 subprocess·비동기 subprocess 전부).
파이프라인을 별도 Job(깨끗한 메인스레드·풀 CPU, 실측 65s 완주)으로 떼어 실행 → 진짜 결과를
Firestore 로 받아 폴링 렌더. 자세한 근거는 _trigger_job() / agents/run_pipeline.py 참조.

로컬 실행:  streamlit run ui/streamlit_app.py
데모(클라우드 없이 렌더 확인):  streamlit run ui/streamlit_app.py 후 URL에 ?demo=1
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import Any

import streamlit as st

# 프로젝트 루트를 path에 (storage/ agents/ 임포트용)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui.theme import apply_theme, page_config  # noqa: E402
from ui.components import debate_view as dv  # noqa: E402
from ui.components import trace_view as tv  # noqa: E402
from ui.components import feedback_form as fb  # noqa: E402
from ui.components import hero as hero  # noqa: E402

EXERCISES = ["squat", "deadlift", "pushup"]
DONE = ("feedback_pending", "done")

# 파이프라인 동기 실행 중 발생한 에러를 UI로 전달하는 프로세스 전역
_PIPELINE_ERRORS: dict[str, str] = {}


# ----------------------------------------------------------------- backend (lazy)
def _trigger_job(debate_id: str, video_uri: str, user_context: dict[str, Any],
                 exercise_type: str, persona_state: dict | None, user_id: str) -> None:
    """검증된 Cloud Run Job(formforge-pipeline)을 실행해 '진짜' 파이프라인을 돌린다.

    Streamlit 컨테이너(비-메인 ScriptRunner 스레드 + Cloud Run CPU 스로틀링) 안에선 OTel 계측
    ADK 토론이 hang/무진척이다(실측 v7~v9: 스레드·블로킹 subprocess·비동기 subprocess 전부).
    그래서 파이프라인을 별도 Job(깨끗한 메인스레드 + 풀 CPU, 실측 65s 완주)으로 떼어 실행한다.
    Job 의 run_full_e2e 가 Firestore(debate_id)에 pose→rounds→consensus 를 기록하고, UI 는
    폴링으로 따라간다(무한 로딩 X, 진짜 결과). PHOENIX_* 는 서비스 env 에서 override 로 Job 에
    전달 → P1 trace 유지(시크릿은 코드/로그 미노출). Job 은 실행 시간만 과금(무료 티어 내).
    """
    import json

    import google.auth
    import requests
    from google.auth.transport.requests import Request as _GAuthRequest

    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "formforge-prod")
    region = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    job = os.environ.get("FF_PIPELINE_JOB", "formforge-pipeline")
    params = {
        "debate_id": debate_id, "video_uri": video_uri, "exercise_type": exercise_type,
        "user_context": user_context, "persona_state": persona_state,
        "user_id": user_id, "use_mcp": True,
    }
    # default=str: persona_state 에 섞인 Firestore 전용 타입(DatetimeWithNanoseconds 등)을
    # 문자열로 직렬화(토론은 persona 의 숫자 필드만 쓰므로 무해). 없으면 JSON 직렬화 TypeError.
    env = [{"name": "FF_PARAMS", "value": json.dumps(params, ensure_ascii=False, default=str)}]
    # 서비스가 가진 Phoenix 설정을 Job 으로 전달(P1) — 값은 런타임 env 에서만 읽어 코드/로그 미노출.
    for k in ("PHOENIX_API_KEY", "PHOENIX_COLLECTOR_ENDPOINT", "PHOENIX_PROJECT_NAME"):
        v = os.environ.get(k)
        if v:
            env.append({"name": k, "value": v})
    try:
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(_GAuthRequest())
        url = f"https://run.googleapis.com/v2/projects/{project}/locations/{region}/jobs/{job}:run"
        body = {"overrides": {"containerOverrides": [{"env": env}], "taskCount": 1, "timeout": "900s"}}
        r = requests.post(url, json=body,
                          headers={"Authorization": f"Bearer {creds.token}"}, timeout=30)
        if r.status_code not in (200, 201):
            _PIPELINE_ERRORS[debate_id] = f"Job 실행 실패 {r.status_code}: {r.text[:160]}"
            print(f"[trigger_job] FAIL {r.status_code}: {r.text[:300]}", file=sys.stderr, flush=True)
        else:
            print(f"[trigger_job] OK job={job} debate={debate_id}", file=sys.stderr, flush=True)
    except Exception as exc:  # noqa: BLE001 — 트리거 실패만 여기서 처리
        _PIPELINE_ERRORS[debate_id] = f"Job 트리거 실패: {type(exc).__name__}: {exc}"
        print(f"[trigger_job] EXC {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)


def _poll(debate_id: str) -> dict[str, Any] | None:
    from storage.firestore_client import get_debate_snapshot
    return get_debate_snapshot(debate_id)


def _persona_state(user_id: str) -> dict | None:
    try:
        from storage.firestore_client import get_user_persona_state
        return get_user_persona_state(user_id)
    except Exception:  # noqa: BLE001
        return None


# ----------------------------------------------------------------- header
def _header() -> None:
    # DESIGN.md / Hero v2 topbar (brand + nav + ENGINE LIVE). 두 화면 공통.
    st.markdown(hero.topbar_html(), unsafe_allow_html=True)


# ----------------------------------------------------------------- screen: upload
def screen_upload() -> None:
    # 진단 그리드 배경(랜딩 전용) → topbar → 2단 히어로.
    st.markdown(hero.field_html(), unsafe_allow_html=True)
    _header()
    st.write("")

    # 좌: lede + 실제 업로드 위젯 + stats / 우: 캡처 쇼케이스(실제 스켈레톤 영상).
    left, right = st.columns([0.86, 1.14], gap="large")
    with left:
        st.markdown(hero.hero_intro_html(), unsafe_allow_html=True)
        file = st.file_uploader("Workout video", type=["mp4", "mov", "avi", "mkv", "webm"])
        exercise = st.selectbox("Exercise", EXERCISES, format_func=str.title)
        injuries = st.text_input("Injury history (optional)", placeholder="e.g. left knee pain last year")
        experience = st.selectbox("Experience level", ["beginner", "intermediate", "advanced"], index=1)
        start = st.button("⚡ Run a diagnostic — summon both coaches", type="primary", disabled=file is None)
        demo = st.button("Watch a teardown (sample · no cloud)")
        st.markdown(hero.hero_stats_html(), unsafe_allow_html=True)
    with right:
        # 우측 영웅 = 우리 진짜 진단 프리즈프레임(스켈레톤·실측각도 baked) 우선.
        # 없으면 움직이는 스켈레톤 영상, 둘 다 없으면 SVG 일러스트로 graceful fallback.
        st.markdown(
            hero.hero_capture_html(
                image_url=_demo_keyframe_uri(),
                video_url=_demo_skeleton_uri() or _demo_video_uri(),
            ),
            unsafe_allow_html=True,
        )

    if demo:
        st.session_state["demo"] = True
        st.rerun()

    if start and file is not None:
        _trigger(file, exercise, injuries, experience)


def _trigger(file: Any, exercise: str, injuries: str, experience: str) -> None:
    debate_id = uuid.uuid4().hex[:16]
    user_id = st.session_state["user_id"]
    try:
        from storage.cloud_storage_client import upload_video_stream
        from storage.firestore_client import create_debate, create_user, get_user
        with st.spinner("Uploading video…"):
            video_uri = upload_video_stream(file, file.name, debate_id=debate_id)
            if get_user(user_id) is None:
                create_user(user_id, {"experience_level": experience})
            create_debate(debate_id, user_id, video_uri, exercise)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Couldn't start: {type(exc).__name__}: {exc}\n\nCheck .env / service-account.json / GCP credentials. "
                 "To preview the UI without the cloud, use ‘Preview with sample data’.")
        return

    user_context = {"user_id": user_id, "injury_history": injuries or "", "experience_level": experience}
    st.session_state["debate_id"] = debate_id  # 폴링 화면으로 전환되게 먼저 set
    _trigger_job(debate_id, video_uri, user_context, exercise, _persona_state(user_id), user_id)
    st.rerun()  # → 폴링(autorefresh) 화면이 Job 진행(Firestore)을 따라감


# ----------------------------------------------------------------- screen: debate
def _signed_video(debate: dict[str, Any]) -> str | None:
    uri = debate.get("video_uri")
    if not uri or not str(uri).startswith("gs://"):
        return None
    try:
        from storage.cloud_storage_client import get_signed_url
        return get_signed_url(uri)
    except Exception:  # noqa: BLE001
        return None


@st.cache_data(show_spinner=False)
def _demo_video_uri() -> str | None:
    """데모 영웅용: 샘플 squat 영상을 base64 data URI로 인라인 (1회 인코딩 후 캐시)."""
    import base64
    p = Path(__file__).resolve().parent.parent / "data" / "sample_videos" / "squat_demo.mp4"
    if not p.exists():
        return None
    return "data:video/mp4;base64," + base64.b64encode(p.read_bytes()).decode("ascii")


@st.cache_data(show_spinner=False)
def _demo_skeleton_uri() -> str | None:
    """데모 영웅용: 미리 구운 스켈레톤 오버레이 영상(§8, 움직이는) data URI. scripts/gen_demo_skeleton.py 산출."""
    import base64
    p = Path(__file__).resolve().parent.parent / "data" / "demo_skeleton.mp4"
    if not p.exists():
        return None
    return "data:video/mp4;base64," + base64.b64encode(p.read_bytes()).decode("ascii")


@st.cache_data(show_spinner=False)
def _demo_keyframe_uri() -> str | None:
    """데모 영웅용 정지 프리즈프레임 data URI (스켈레톤 영상 도입 후 fallback 후보로 보존)."""
    import base64
    p = Path(__file__).resolve().parent.parent / "data" / "demo_keyframe.jpg"
    if not p.exists():
        return None
    return "data:image/jpeg;base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def screen_debate(debate: dict[str, Any], *, demo: bool = False) -> None:
    _header()
    status = debate.get("status", "pending")

    # subprocess 가 비동기로 도는 동안 1초 폴링으로 진행(pose→토론→판결)을 따라간다.
    # 완료(DONE)·에러일 땐 폴링 중단. (status='error' = subprocess 가 실패를 Firestore 에 기록.)
    err = _PIPELINE_ERRORS.get(debate.get("debate_id", ""))
    if not err and status == "error":
        err = "Analysis failed — please try again. (See Cloud Run logs for details.)"
    if err:
        st.error(f"Analysis pipeline error: {err}")
    elif not demo and status not in DONE:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=1000, key="debate_poll")

    st.markdown(dv.tale_of_the_tape(debate), unsafe_allow_html=True)

    left, right = st.columns([1.05, 0.95])
    with left:
        # 데모: 키프레임(프리즈프레임)이 있으면 영상 인코딩 생략(viewer_html이 img 우선).
        if demo:
            # 데모 영웅 = 미리 구운 스켈레톤 영상(움직이는 오버레이). 없으면 원본 영상 fallback.
            video_url = _demo_skeleton_uri() or _demo_video_uri()
            autoplay = True
        else:
            # 라이브 = pose_extractor 가 만든 스켈레톤 영상(skeleton_video_url) 우선, 없으면 원본 영상.
            skeleton = (debate.get("pose_data") or {}).get("skeleton_video_url")
            video_url = skeleton or _signed_video(debate)
            autoplay = bool(skeleton)  # 스켈레톤이면 autoplay loop, 원본 영상이면 controls
        st.markdown(dv.viewer_html(debate.get("pose_data"), video_url, autoplay=autoplay), unsafe_allow_html=True)
        st.markdown(dv.readout_html(debate.get("pose_data")), unsafe_allow_html=True)
    with right:
        st.markdown(dv.debate_feed(debate, stagger=demo), unsafe_allow_html=True)

    if debate.get("consensus"):
        st.markdown(
            dv.verdict_html(
                debate.get("consensus"),
                mcp_tool_calls=debate.get("mcp_tool_calls"),
                trace_ids=debate.get("trace_ids"),
            ),
            unsafe_allow_html=True,
        )

    st.markdown(
        tv.trace_strip(
            debate,
            phoenix_base=os.getenv("PHOENIX_COLLECTOR_ENDPOINT"),
            project_name=os.getenv("PHOENIX_PROJECT_NAME"),
        ),
        unsafe_allow_html=True,
    )

    # 피드백 (P3) — 토론 완료 시
    if status in DONE or demo:
        st.write("")
        # B: 검증된 자기개선 수치(+28%) 헤드라인 — 피드백 전/후 항상 노출(Arize thesis 증거).
        st.markdown(fb.calibration_headline_html(), unsafe_allow_html=True)
        if st.session_state.get("fb_done"):
            st.success("Feedback applied — both coaches evolved a step toward you.")
            ps = fb.persona_drift_html(st.session_state.get("persona_after"))
            if ps:
                st.markdown(ps, unsafe_allow_html=True)
        else:
            result = fb.render_feedback()
            if result:
                _submit_feedback(debate, result, demo=demo)

    st.write("")
    if st.button("↺ Start over"):
        for k in ("debate_id", "demo", "fb_done", "persona_after"):
            st.session_state.pop(k, None)
        st.rerun()


def _submit_feedback(debate: dict[str, Any], result: dict[str, Any], *, demo: bool) -> None:
    if demo:
        from ui.sample_data import sample_persona_state
        st.session_state["fb_done"] = True
        st.session_state["persona_after"] = sample_persona_state()
        st.rerun()
        return
    try:
        from evals.feedback_handler import process_feedback_sync
        process_feedback_sync(
            debate.get("debate_id"), st.session_state["user_id"],
            result["encourager_rating"], result["scrutinizer_rating"],
            result["mediator_rating"], result["free_text"],
        )
        st.session_state["fb_done"] = True
        st.session_state["persona_after"] = _persona_state(st.session_state["user_id"])
        st.rerun()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to save feedback: {type(exc).__name__}: {exc}")


# ----------------------------------------------------------------- entry
def main() -> None:
    page_config()
    apply_theme()
    st.session_state.setdefault("user_id", "guest-" + uuid.uuid4().hex[:8])

    # 데모 모드: 샘플 스냅샷 렌더 (클라우드 불필요)
    if st.session_state.get("demo") or st.query_params.get("demo") == "1":
        from ui.sample_data import sample_debate
        screen_debate(sample_debate(), demo=True)
        return

    debate_id = st.session_state.get("debate_id")
    if not debate_id:
        screen_upload()
        return

    debate = _poll(debate_id)
    if debate is None:
        st.info("Loading debate…")
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=1000, key="wait_poll")
        return
    debate.setdefault("debate_id", debate_id)
    screen_debate(debate)


main()
