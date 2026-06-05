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

_ENC = {"너무 따뜻함": "too_warm", "딱 좋음": "perfect", "너무 차가움": "too_cold"}
_SCR = {"너무 가혹함": "too_harsh", "딱 좋음": "perfect", "너무 무름": "too_soft"}


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
        bars += _bar("Encourager · 온기", enc["warmth"], "var(--enc)")
    if scr.get("harshness") is not None:
        bars += _bar("Scrutinizer · 가혹도", scr["harshness"], "var(--scr)")
    return f"""
<div style="border:1px solid var(--hairline);border-radius:12px;background:var(--bg-surface);padding:16px 18px">
  <div class="ff-feed-head"><span class="ff-dot" style="background:var(--enc)"></span>
    <span class="t">페르소나 진화</span>
    <span class="ff-live" style="color:var(--muted);background:transparent;border-color:var(--strong)">보정 {_esc(count)}×</span>
  </div>
  {bars}
  <div class="ff-drift">피드백이 쌓일수록 두 코치가 <b>당신만의 critic</b>으로 진화합니다.</div>
</div>"""


def render_feedback() -> dict[str, Any] | None:
    """제출되면 process_feedback_sync(**dict) 호출용 인자를 반환, 아니면 None."""
    st.markdown(
        '<div class="ff-feed-head" style="margin-top:6px">'
        '<span class="ff-dot"></span><span class="t">이 판결, 어땠나요?</span></div>',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        enc_label = st.radio("The Encourager 톤", list(_ENC.keys()), index=1, horizontal=True, key="fb_enc")
    with c2:
        scr_label = st.radio("The Scrutinizer 톤", list(_SCR.keys()), index=1, horizontal=True, key="fb_scr")
    mediator_rating = st.slider("The Mediator 판결 만족도", 1, 5, 4, key="fb_med")
    free_text = st.text_area("한마디 (선택)", placeholder="예: 무릎 지적은 정확했는데 톤이 좀 셌어요", key="fb_txt")

    if st.button("판결 보정 →  코치 진화시키기", type="primary", key="fb_submit"):
        return {
            "encourager_rating": _ENC[enc_label],
            "scrutinizer_rating": _SCR[scr_label],
            "mediator_rating": int(mediator_rating),
            "free_text": free_text or "",
        }
    return None
