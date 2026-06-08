# 파일 위치: ui/components/feedback_form.py
"""P3 — 사용자 피드백 → 페르소나 진화 (calibration UI + 드리프트 표시).

- render_feedback(): st 위젯으로 평가 수집, 제출 시 process_feedback_sync 인자 dict 반환.
- persona_drift_html(): users/{id}.persona_state를 막대로 시각화 (순수 HTML).
백엔드 enum: encourager(too_warm|perfect|too_cold), scrutinizer(too_harsh|perfect|too_soft), mediator(1~5).
"""
from __future__ import annotations

import html
from typing import Any

import streamlit as st

_ENC = {"Too warm": "too_warm", "Just right": "perfect", "Too cold": "too_cold"}
_SCR = {"Too harsh": "too_harsh", "Just right": "perfect", "Too soft": "too_soft"}


def _esc(v: Any) -> str:
    return html.escape(str(v if v is not None else ""))


def _bar(name: str, value: float, color: str) -> str:
    pct = max(0, min(100, round((value or 0) * 100)))
    return f"""
<div class="ff-driftbar">
  <span class="name">{_esc(name)}</span>
  <span class="meter"><span class="fill" style="width:{pct}%;background:{color}"></span></span>
  <span class="val">{pct}%</span>
</div>"""


def persona_drift_html(persona_state: dict[str, Any] | None) -> str:
    if not persona_state:
        return ""
    enc = persona_state.get("encourager") or {}
    scr = persona_state.get("scrutinizer") or {}
    count = persona_state.get("total_feedback_count", 0)
    bars = ""
    if enc.get("warmth") is not None:
        bars += _bar("Encourager · Warmth", enc["warmth"], "var(--enc)")
    if scr.get("harshness") is not None:
        bars += _bar("Scrutinizer · Harshness", scr["harshness"], "var(--scr)")
    return f"""
<div style="border:1px solid var(--hairline);border-radius:12px;background:var(--bg-surface);padding:16px 18px">
  <div class="ff-feed-head"><span class="ff-dot" style="background:var(--enc)"></span>
    <span class="t">Persona Evolution</span>
    <span class="ff-live" style="color:var(--muted);background:transparent;border-color:var(--strong)">{_esc(count)}× calibrated</span>
  </div>
  {bars}
  <div class="ff-drift">As feedback accumulates, both coaches evolve into <b>your own critic</b>.</div>
</div>"""


def render_feedback() -> dict[str, Any] | None:
    """제출되면 process_feedback_sync(**dict) 호출용 인자를 반환, 아니면 None."""
    st.markdown(
        '<div class="ff-feed-head" style="margin-top:6px">'
        '<span class="ff-dot"></span><span class="t">How was this verdict?</span></div>',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        enc_label = st.radio("The Encourager tone", list(_ENC.keys()), index=1, horizontal=True, key="fb_enc")
    with c2:
        scr_label = st.radio("The Scrutinizer tone", list(_SCR.keys()), index=1, horizontal=True, key="fb_scr")
    mediator_rating = st.slider("The Mediator verdict — satisfaction", 1, 5, 4, key="fb_med")
    free_text = st.text_area("One-liner (optional)", placeholder="e.g. the knee callout was spot-on but the tone ran a bit hot", key="fb_txt")

    if st.button("Recalibrate →  evolve the coaches", type="primary", key="fb_submit"):
        return {
            "encourager_rating": _ENC[enc_label],
            "scrutinizer_rating": _SCR[scr_label],
            "mediator_rating": int(mediator_rating),
            "free_text": free_text or "",
        }
    return None
