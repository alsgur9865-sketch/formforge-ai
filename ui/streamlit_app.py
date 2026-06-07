# 파일 위치: ui/streamlit_app.py
"""FormForge AI — 메인 Streamlit 앱 (DESIGN.md "The Diagnostic Freeze-Frame").

플로우: 업로드 → 파이프라인(run_full_e2e)을 독립 subprocess로 '비동기' 기동 → Firestore
1초 폴링으로 pose→토론→판결이 순차로 채워지는 걸 렌더 → 피드백(페르소나 진화). 백엔드
import는 지연 처리(데모 모드는 클라우드 불필요).

⚠️ 왜 subprocess(메인스레드)+폴링인가:
 - Streamlit 비-메인 ScriptRunner 스레드에서 OTel 계측 ADK Runner 를 asyncio.run 하면 Cloud
   Run 에서 토론 hang(rounds=0, 실측). 별도 프로세스 메인스레드에선 계측 켜도 정상 완주.
 - 1초 폴링이 인스턴스를 활성 유지 → 기본 CPU 스로틀링(무료 티어)에서도 subprocess 가 CPU 를
   받는다. 상시-CPU(유료) 옵션 불필요 = $0. 자세한 근거는 agents/run_pipeline.py 참조.

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

EXERCISES = ["squat", "deadlift", "pushup"]
DONE = ("feedback_pending", "done")

# 파이프라인 동기 실행 중 발생한 에러를 UI로 전달하는 프로세스 전역
_PIPELINE_ERRORS: dict[str, str] = {}


# ----------------------------------------------------------------- backend (lazy)
def _spawn_pipeline(debate_id: str, video_uri: str, user_context: dict[str, Any],
                    exercise_type: str, persona_state: dict | None, user_id: str) -> None:
    """파이프라인(run_full_e2e)을 독립 subprocess(메인스레드)로 '비동기' 기동하고 즉시 반환.

    UI 는 이후 Firestore 폴링(autorefresh)으로 진행을 따라간다 — pose→토론→판결이 순차로 채워짐.
    - 왜 subprocess(메인스레드): Streamlit 비-메인 ScriptRunner 스레드에서 asyncio.run 으로 OTel
      계측 ADK Runner 를 돌리면 Cloud Run 에서 hang. 별도 프로세스 메인스레드에선 정상 완주.
    - 왜 비동기+폴링: 1초 폴링이 인스턴스를 활성 유지 → 기본 CPU 스로틀링(무료 티어)에서도
      subprocess 가 CPU 를 받는다(상시-CPU 유료 옵션 불필요 = $0). subprocess 는 부모 env 상속
      → PHOENIX_API_KEY → P1 trace 송출 유지. stdout/stderr 는 컨테이너로 상속(Cloud Run 로그).
    실패는 subprocess 가 Firestore 에 status='error' 로 기록(run_pipeline.py) → UI 가 배너 표시.
    """
    import json
    import subprocess
    import tempfile

    root = Path(__file__).resolve().parent.parent
    params = {
        "debate_id": debate_id, "video_uri": video_uri, "exercise_type": exercise_type,
        "user_context": user_context, "persona_state": persona_state,
        "user_id": user_id, "use_mcp": True,
    }
    try:
        fd, path = tempfile.mkstemp(suffix=".json", prefix="ffparams_")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(params, f, ensure_ascii=False)
        # 비동기 기동(블로킹 X) — 출력은 컨테이너 stdout/stderr 상속 → Cloud Run 로그 스트리밍.
        subprocess.Popen(
            [sys.executable, "-m", "agents.run_pipeline", path],
            cwd=str(root), env=os.environ.copy(),
        )
    except Exception as exc:  # noqa: BLE001 — 기동 실패만 여기서 처리
        _PIPELINE_ERRORS[debate_id] = f"기동 실패: {type(exc).__name__}: {exc}"


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
    st.markdown(
        '<div class="ff-brand"><div class="glyph">F</div>'
        '<div class="wm">FormForge <span>AI</span></div></div>',
        unsafe_allow_html=True,
    )


# ----------------------------------------------------------------- screen: upload
def screen_upload() -> None:
    _header()
    st.markdown(
        '<div class="ff-h1">The argument happens<br>on your body<span class="g">.</span></div>'
        '<div class="ff-lede">Upload a workout clip and two AI coaches debate your form in real time — '
        'then a Head Coach settles it into a single verdict.</div>',
        unsafe_allow_html=True,
    )
    st.write("")
    col, side = st.columns([1.4, 1])
    with col:
        file = st.file_uploader("Workout video", type=["mp4", "mov", "avi", "mkv", "webm"])
        exercise = st.selectbox("Exercise", EXERCISES, format_func=str.title)
        injuries = st.text_input("Injury history (optional)", placeholder="e.g. left knee pain last year")
        experience = st.selectbox("Experience level", ["beginner", "intermediate", "advanced"], index=1)
        start = st.button("⚡ Start analysis — summon both coaches", type="primary", disabled=file is None)
        demo = st.button("Preview with sample data (no cloud needed)")

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
    _spawn_pipeline(debate_id, video_uri, user_context, exercise, _persona_state(user_id), user_id)
    st.rerun()  # → 폴링(autorefresh) 화면이 subprocess 진행을 따라감


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
def _demo_keyframe_uri() -> str | None:
    """데모 영웅용: 미리 구운 주석 프리즈프레임(§8 오버레이) data URI. scripts/gen_demo_keyframe.py 산출."""
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
            has_kf = bool((debate.get("pose_data") or {}).get("keyframe_urls"))
            video_url = None if has_kf else _demo_video_uri()
        else:
            video_url = _signed_video(debate)
        st.markdown(dv.viewer_html(debate.get("pose_data"), video_url, autoplay=demo), unsafe_allow_html=True)
        st.markdown(dv.readout_html(debate.get("pose_data")), unsafe_allow_html=True)
    with right:
        st.markdown(dv.debate_feed(debate), unsafe_allow_html=True)

    if debate.get("consensus"):
        st.markdown(dv.verdict_html(debate.get("consensus")), unsafe_allow_html=True)

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
        deb = sample_debate()
        kf = _demo_keyframe_uri()  # 미리 구운 §8 주석 프리즈프레임을 히어로로
        if kf:
            deb.setdefault("pose_data", {})["keyframe_urls"] = [kf]
        screen_debate(deb, demo=True)
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
