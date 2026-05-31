# 파일 위치: ui/streamlit_app.py
"""FormForge AI — "Fight Card" Streamlit UI (Day 14).

실행:
    ./venv/Scripts/streamlit run ui/streamlit_app.py

전략 (PROGRESS 세션 11 확정):
  - 디자인 핸드오프 6화면을 HTML 템플릿으로 충실 재현 → st.components.v1.html() 렌더.
  - "라이브" 갱신은 1초 폴링(streamlit-autorefresh) — Firestore on_snapshot 금지(§3.2).
  - 인터랙션(영상 업로드 / 피드백 제출)만 Streamlit 위젯으로 분리(하이브리드).
  - 기본 Demo 모드: GCP·Gemini 없이도 6화면이 sample_state 로 그대로 동작.
  - Live 모드: 실제 파이프라인(run_full_e2e) + Firestore 폴링 + 피드백 진화(best-effort, fail-soft).
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path 끝에 추가(append) — root/mcp 가 PyPI mcp 를 shadow 하지 않도록.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.append(str(_ROOT))

import streamlit as st  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

from ui import render, sample_state, theme  # noqa: E402

# 선택적: 라이브 폴링용 (없어도 데모는 동작)
try:
    from streamlit_autorefresh import st_autorefresh
except Exception:  # noqa: BLE001
    st_autorefresh = None


# ---------------------------------------------------------------------------
# 페이지 설정 + 셸
# ---------------------------------------------------------------------------

st.set_page_config(page_title="FormForge AI — Fight Card", page_icon="🥊",
                   layout="wide", initial_sidebar_state="expanded")
st.markdown(theme.page_shell_css(), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# 세션 상태 기본값
# ---------------------------------------------------------------------------

_DEFAULTS = {
    "mode": "Demo",
    "exercise": "squat",
    "injuries": ["Prior lower-back injury"],
    "video_name": None,
    "video_path": None,
    "enc_rating": "ok",
    "scr_rating": "harsh",
    "stars": 4,
    "note": "",
    "feedback_sent": False,
    "debate_id": None,
    "live_pose": None,
    "live_debate": None,
    "live_mediator": None,
    "live_persona_before": None,
    "live_persona_after": None,
}
for _k, _v in _DEFAULTS.items():
    st.session_state.setdefault(_k, _v)


SCREENS = {
    "🥊  Live Debate": "debate",
    "⊕  Weigh-In (Upload)": "upload",
    "⚖  Official Decision": "consensus",
    "★  Score the Corners": "feedback",
    "↻  Between Bouts": "evolution",
    "◷  Phoenix Trace": "trace",
}


# ---------------------------------------------------------------------------
# 사이드바
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### FormForge AI")
    st.caption("Adversarial Multi-Agent Workout Form Coach")
    nav_label = st.radio("FIGHT CARD", list(SCREENS.keys()), label_visibility="visible")
    screen = SCREENS[nav_label]

    st.divider()
    st.session_state["mode"] = st.radio(
        "DATA SOURCE", ["Demo", "Live"],
        help="Demo: instant render from built-in samples (no GCP). Live: real pipeline / Firestore.",
        index=0 if st.session_state["mode"] == "Demo" else 1,
    )
    if st.session_state["mode"] == "Live":
        st.text_input("user_id", value="user_001", key="user_id")
        if st.session_state.get("debate_id"):
            st.caption(f"debate_id · `{st.session_state['debate_id']}`")
    st.divider()
    st.slider("🔍 Zoom", 0.70, 1.60, 1.0, 0.05, key="zoom",
              help="Scale the fixed 1440px design up/down at a constant ratio. On a wide monitor, increase it to fill the empty margins.")
    st.divider()
    st.caption("⚕ For information only · not medical advice")


IS_LIVE = st.session_state["mode"] == "Live"
RECORD = f"RECORD {sample_state.RECORD_CURRENT}"


def show(screen_name: str, ctx: dict) -> None:
    """템플릿 렌더 → CSS 격리된 고정폭 iframe.

    전체 HTML 문서(자체 <style> + 1440px 고정폭)는 Streamlit 본문에 인라인하면
    CSS 가 충돌하므로 반드시 격리 iframe 에 띄운다. 비권장 `components.v1.html`
    (2026-06-01 이후 제거) 대신, 문서를 base64 data: URI 로 인코딩해 `st.iframe`
    (data: URI 공식 지원)에 싣는다 — 미래 안전 + CSS 완전 격리.
    """
    zoom = float(st.session_state.get("zoom", 1.0))
    html = render.render_screen(screen_name, ctx, zoom=zoom)
    w = round(1440 * zoom)
    h = round(render.SCREEN_HEIGHTS[screen_name] * zoom)
    try:
        b64 = base64.b64encode(html.encode("utf-8")).decode("ascii")
        st.iframe(f"data:text/html;base64,{b64}", width=w, height=h)
    except Exception:  # noqa: BLE001 — 구버전 Streamlit 폴백
        components.html(html, width=w, height=h, scrolling=True)


# ---------------------------------------------------------------------------
# 라이브 헬퍼 (best-effort, fail-soft)
# ---------------------------------------------------------------------------

def _poll_live_debate() -> dict | None:
    """Firestore 에서 현재 debate_id 스냅샷 폴링 → debate/mediator/pose 갱신."""
    debate_id = st.session_state.get("debate_id")
    if not debate_id:
        return None
    try:
        from storage import firestore_client
        snap = firestore_client.get_debate_snapshot(debate_id)
    except Exception as e:  # noqa: BLE001
        st.warning(f"Firestore 폴링 실패 (Demo 데이터로 대체): {type(e).__name__}: {e}")
        return None
    return snap


def _run_live_analysis(video_path: str) -> None:
    """run_full_e2e 동기 실행 (spinner). 결과를 session_state 에 저장."""
    import asyncio

    from agents.orchestrator import PoseExtractionError, run_full_e2e

    user_ctx = {
        "user_id": st.session_state.get("user_id", "user_001"),
        "injury_history": ["lower_back_strain_2025"] if st.session_state["injuries"] else [],
        "experience_level": "intermediate",
    }
    debate_id = f"ui_{int(Path(video_path).stat().st_mtime)}"
    with st.spinner("The corners are analyzing your video… (PoseExtractor → debate → ruling, up to ~2 min)"):
        try:
            e2e = asyncio.run(run_full_e2e(
                video_uri=video_path, user_context=user_ctx,
                exercise_type=st.session_state["exercise"],
                debate_id=debate_id, use_mcp=True,
            ))
        except PoseExtractionError as pe:
            st.error(f"PoseExtractor confidence guard — debate not entered: {pe}")
            return
        except Exception as e:  # noqa: BLE001
            st.error(f"Live analysis failed: {type(e).__name__}: {e}")
            return
    st.session_state["debate_id"] = debate_id
    st.session_state["live_pose"] = e2e.pose_extraction
    st.session_state["live_debate"] = e2e.session.debate.as_dict()
    st.session_state["live_mediator"] = e2e.session.mediator.as_dict()
    st.success(f"Analysis complete · debate_id={debate_id} — see the Live Debate screen.")


def _live_or_demo() -> tuple[dict, dict, dict]:
    """현재 표시할 (pose, debate, mediator) 를 Live 우선·Demo 폴백으로 반환."""
    if IS_LIVE:
        snap = _poll_live_debate()
        pose = st.session_state.get("live_pose") or (snap or {}).get("pose_data")
        debate = st.session_state.get("live_debate") or (snap or {}).get("rounds") and {
            "rounds": snap.get("rounds", []),
            "converged": (snap.get("consensus") is not None),
            "converged_at_round": len(snap.get("rounds", [])) or None,
            "shared_issue": None, "forced_stop_reason": None,
        }
        mediator = st.session_state.get("live_mediator") or (snap or {}).get("consensus")
        if pose and debate:
            return pose, debate, (mediator or {})
        st.info("No live data yet — run an analysis from Weigh-In. (Showing Demo data for now)")
    return sample_state.SAMPLE_POSE, sample_state.SAMPLE_DEBATE, sample_state.SAMPLE_MEDIATOR


# ===========================================================================
# 화면별 렌더
# ===========================================================================

if screen == "upload":
    ctx = render.upload_ctx(
        exercise_type=st.session_state["exercise"],
        injury_flags=st.session_state["injuries"],
        video_name=st.session_state["video_name"],
    )
    show("upload", ctx)

    with st.container():
        st.markdown("##### 🎬 Weigh-In — actual input (controls)")
        c1, c2 = st.columns([1.4, 1])
        with c1:
            up = st.file_uploader("Workout video (MP4 / MOV · side angle recommended)", type=["mp4", "mov", "avi", "webm"])
            if up is not None:
                tmp = _ROOT / "data" / "sample_videos" / f"_ui_upload_{up.name}"
                tmp.parent.mkdir(parents=True, exist_ok=True)
                tmp.write_bytes(up.getbuffer())
                st.session_state["video_name"] = up.name
                st.session_state["video_path"] = str(tmp)
        with c2:
            st.session_state["exercise"] = st.radio(
                "Weight class", ["squat", "deadlift", "pushup"],
                index=["squat", "deadlift", "pushup"].index(st.session_state["exercise"]),
            )
        inj = st.text_input("Injuries / limitations (comma-separated)", value=", ".join(st.session_state["injuries"]))
        st.session_state["injuries"] = [s.strip() for s in inj.split(",") if s.strip()]

        b1, b2 = st.columns([1, 3])
        with b1:
            if st.button("Send to the corners →", type="primary", use_container_width=True):
                if IS_LIVE and st.session_state.get("video_path"):
                    _run_live_analysis(st.session_state["video_path"])
                elif IS_LIVE:
                    st.warning("Live mode: upload a video first.")
                else:
                    st.success("Demo mode — go to the 'Live Debate' screen on the left to watch the debate. 🥊")

elif screen == "debate":
    if IS_LIVE and st_autorefresh is not None and st.session_state.get("debate_id"):
        # 라이브 토론 진행 중에는 1초 폴링 (status 가 done 이면 멈춤은 사용자가 화면 전환으로)
        st_autorefresh(interval=1000, key="debate_poll")
    pose, debate, mediator = _live_or_demo()
    ctx = render.debate_ctx(pose=pose, debate=debate, mediator=mediator,
                            record_label=f"{RECORD} · {'LIVE' if IS_LIVE else 'DEMO'}",
                            max_rounds=3)
    show("debate", ctx)

elif screen == "consensus":
    pose, debate, mediator = _live_or_demo()
    if not mediator:
        st.info("No consensus (Mediator) result yet.")
        mediator = sample_state.SAMPLE_MEDIATOR
    ctx = render.consensus_ctx(mediator=mediator, debate=debate, pose=pose,
                               record_label=f"{RECORD} · SQUAT")
    show("consensus", ctx)

elif screen == "feedback":
    ctx = render.feedback_ctx(
        enc_rating=st.session_state["enc_rating"],
        scr_rating=st.session_state["scr_rating"],
        stars=st.session_state["stars"],
        note=st.session_state["note"],
        sent=st.session_state["feedback_sent"],
        record_label=f"{RECORD} · POST-BOUT",
    )
    show("feedback", ctx)

    with st.container():
        st.markdown("##### ★ Score the Corners — actual input")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.session_state["enc_rating"] = st.radio(
                "The Encourager · WARMTH", ["warm", "ok", "cold"],
                index=["warm", "ok", "cold"].index(st.session_state["enc_rating"]),
                format_func=lambda v: {"warm": "Too warm", "ok": "Just right", "cold": "Too cold"}[v],
            )
        with c2:
            st.session_state["scr_rating"] = st.radio(
                "The Scrutinizer · HARSHNESS", ["harsh", "ok", "soft"],
                index=["harsh", "ok", "soft"].index(st.session_state["scr_rating"]),
                format_func=lambda v: {"harsh": "Too harsh", "ok": "Just right", "soft": "Too soft"}[v],
            )
        with c3:
            st.session_state["stars"] = st.slider("The Mediator · OVERALL", 1, 5, st.session_state["stars"])
        st.session_state["note"] = st.text_input("Notes to the corner (optional)", value=st.session_state["note"])

        if st.button("Submit your card →", type="primary"):
            if IS_LIVE and st.session_state.get("debate_id"):
                # UI 어휘 → feedback_handler 어휘 매핑
                _enc_map = {"warm": "too_warm", "ok": "perfect", "cold": "too_cold"}
                _scr_map = {"harsh": "too_harsh", "ok": "perfect", "soft": "too_soft"}
                try:
                    from evals.feedback_handler import process_feedback_sync
                    result = process_feedback_sync(
                        debate_id=st.session_state["debate_id"],
                        user_id=st.session_state.get("user_id", "user_001"),
                        encourager_rating=_enc_map[st.session_state["enc_rating"]],
                        scrutinizer_rating=_scr_map[st.session_state["scr_rating"]],
                        mediator_rating=st.session_state["stars"],
                        free_text=st.session_state["note"],
                    )
                    # before/after 페르소나를 Evolution 화면용으로 보존 (caution ← scrutinizer.detail)
                    old = result.get("old_persona_state", {}).get("scrutinizer", {})
                    new = result.get("new_persona_state", {}).get("scrutinizer", {})
                    st.session_state["live_persona_before"] = {
                        "harshness": old.get("harshness", 0.5), "caution": old.get("detail", 0.5)}
                    st.session_state["live_persona_after"] = {
                        "harshness": new.get("harshness", 0.35), "caution": new.get("detail", 0.55)}
                    st.success("Feedback applied — the personas have been re-forged. "
                               "See the change on the 'Between Bouts' screen.")
                except Exception as e:  # noqa: BLE001
                    st.warning(f"Live feedback failed (showing Demo banner only): {type(e).__name__}: {e}")
            st.session_state["feedback_sent"] = True
            st.rerun()

        if st.session_state["feedback_sent"]:
            if st.button("Score again (reset)"):
                st.session_state["feedback_sent"] = False
                st.rerun()

elif screen == "evolution":
    before = st.session_state.get("live_persona_before") or sample_state.SAMPLE_PERSONA_BEFORE
    after = st.session_state.get("live_persona_after") or sample_state.SAMPLE_PERSONA_AFTER
    ctx = render.evolution_ctx(
        before=before, after=after,
        quotes=sample_state.SAMPLE_EVOLUTION_QUOTES,
        result=sample_state.SAMPLE_RESULT,
        record_label=f"RECORD {sample_state.RECORD_PRIOR} → {sample_state.RECORD_CURRENT}",
        prior_record_label=f"RECORD {sample_state.RECORD_PRIOR}",
        current_record_label=f"RECORD {sample_state.RECORD_CURRENT}",
        trigger="too harsh",
    )
    show("evolution", ctx)

elif screen == "trace":
    ctx = render.trace_ctx(trace=sample_state.SAMPLE_TRACE,
                           record_label=f"PHOENIX TRACE · {RECORD}")
    show("trace", ctx)
    st.caption("Phoenix Cloud: https://app.phoenix.arize.com — chain trace + convergence_judge LLM span "
               "+ MCP tool calls (query_past_debates / query_safety_flags) as child spans under the Mediator.")
