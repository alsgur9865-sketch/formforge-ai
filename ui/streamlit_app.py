# 파일 위치: ui/streamlit_app.py
"""FormForge AI — 메인 Streamlit 앱 (DESIGN.md "The Diagnostic Freeze-Frame").

플로우: 업로드 → 파이프라인(run_full_e2e)을 독립 subprocess로 실행(요청 내 블로킹, ~2분
spinner) → Firestore 기록 → 토론·판결 렌더 → 피드백(페르소나 진화). 백엔드 import는 지연
처리(데모 모드는 클라우드 불필요).

⚠️ 왜 subprocess 인가: Streamlit 스크립트는 비-메인 ScriptRunner 스레드에서 돈다. 그 스레드
에서 OTel 계측된 ADK Runner 를 asyncio.run 으로 돌리면 Cloud Run 에서 토론이 hang(rounds=0)
한다(실측). 메인스레드 프로세스에선 계측이 켜져 있어도 정상 완주. 요청 안에서 블로킹하므로
Cloud Run CPU 도 유지된다(무료 티어). 자세한 근거는 agents/run_pipeline.py 참조.

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
def _run_pipeline_sync(debate_id: str, video_uri: str, user_context: dict[str, Any],
                       exercise_type: str, persona_state: dict | None, user_id: str) -> None:
    """파이프라인(run_full_e2e)을 독립 subprocess(메인스레드)에서 실행 — 요청 안에서 블로킹.

    Streamlit ScriptRunner(비-메인 스레드)에서 직접 asyncio.run 하면 OTel 계측된 ADK Runner
    가 Cloud Run 에서 hang 한다(실측). 별도 프로세스의 메인스레드에선 계측이 켜져 있어도 정상
    완주. 요청 안에서 블로킹하므로 Cloud Run CPU 가 유지되고(무료 티어), subprocess 는 부모
    env(PHOENIX_API_KEY 등)를 상속해 P1 trace 도 정상 송출. 대가: ~2분 spinner.
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
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    try:
        json.dump(params, tmp, ensure_ascii=False)
        tmp.close()
        with st.spinner("Both coaches are analyzing your video… "
                        "(PoseExtractor → debate → ruling, up to ~2 min)"):
            proc = subprocess.run(
                [sys.executable, "-m", "agents.run_pipeline", tmp.name],
                cwd=str(root), env=os.environ.copy(),
                capture_output=True, text=True, timeout=480,
            )
        # subprocess 로그를 Cloud Run 로그로 전달(디버깅 — 부모가 캡처했으므로 재출력).
        if proc.stdout:
            print(proc.stdout, file=sys.stderr, flush=True)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr, flush=True)
        if proc.returncode != 0:
            tail = " / ".join((proc.stderr or "").strip().splitlines()[-3:])
            _PIPELINE_ERRORS[debate_id] = tail or f"pipeline exited {proc.returncode}"
    except subprocess.TimeoutExpired:
        _PIPELINE_ERRORS[debate_id] = "Analysis timed out (>8 min). Try a shorter clip."
    except Exception as exc:  # noqa: BLE001 — UI로 전달
        _PIPELINE_ERRORS[debate_id] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


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
    st.session_state["debate_id"] = debate_id  # 에러로 끝나도 debate 화면(에러 배너)으로 전환되게 먼저 set
    _run_pipeline_sync(debate_id, video_uri, user_context, exercise, _persona_state(user_id), user_id)
    st.rerun()


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

    # 정상 경로: 파이프라인이 업로드 요청 안에서 subprocess 로 완료된 뒤 이 화면이 렌더된다.
    # 단, 긴 블로킹 중 웹소켓이 끊겨 재접속하면 처리 중(미완료) 상태를 만날 수 있으므로
    # 완료(DONE) 전·에러 없음일 때만 자동 폴링으로 완료까지 따라간다.
    err = _PIPELINE_ERRORS.get(debate.get("debate_id", ""))
    if err:
        st.error(f"Analysis pipeline error: {err}")
    elif not demo and status not in DONE:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=2000, key="debate_poll")

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
