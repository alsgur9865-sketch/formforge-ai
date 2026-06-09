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


# ── B: 자기개선 "측정된" 헤드라인 — 세션17 Phoenix Experiment 실측(persona v1→v3) ──
_ALIGN_BEFORE, _ALIGN_AFTER, _ALIGN_LIFT = "0.62", "0.795", "+28%"
_PHOENIX_EXPERIMENT_URL = (
    "https://app.phoenix.arize.com/s/alsgur9865/datasets/RGF0YXNldDoy/experiments"
)


def calibration_headline_html() -> str:
    """검증된 정렬도 향상 배지 — 진짜 실측 수치(0.62→0.795). Arize 자기개선 thesis의 증거.
    개인용 가짜 점수를 지어내지 않고, 인상적 숫자는 *실제 검증된* 실험 결과가 짊어진다."""
    return (
        '<div class="ff-cal-head">'
        '<div class="lbl">SELF-IMPROVEMENT, MEASURED</div>'
        '<div class="row">'
        f'<span class="was">{_ALIGN_BEFORE}</span>'
        '<span class="arr">→</span>'
        f'<span class="now">{_ALIGN_AFTER}</span>'
        f'<span class="lift">{_ALIGN_LIFT}</span>'
        '</div>'
        f'<a class="src" href="{_PHOENIX_EXPERIMENT_URL}" target="_blank" rel="noopener">'
        'preference alignment · validated via Phoenix Experiments (persona v1→v3) ↗</a>'
        '</div>'
    )


def _personalization_pct(enc: dict[str, Any], scr: dict[str, Any]) -> int | None:
    """코치가 기본형(0.5)에서 얼마나 멀어졌나 = 평균 절대 드리프트 / 0.5 → 0~100%.
    정직한 지표(가짜 alignment 점수 아님): 피드백이 움직이는 다이얼(warmth·harshness)만."""
    dials = []
    if enc.get("warmth") is not None:
        dials.append(abs(enc["warmth"] - 0.5))
    if scr.get("harshness") is not None:
        dials.append(abs(scr["harshness"] - 0.5))
    if not dials:
        return None
    return round((sum(dials) / len(dials)) / 0.5 * 100)


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
    pct = _personalization_pct(enc, scr)
    personalized = (
        f'<div class="ff-drift">→ <b>{pct}% personalized</b> from the default coach</div>'
        if pct is not None else ""
    )
    return f"""
<div style="border:1px solid var(--hairline);border-radius:12px;background:var(--bg-surface);padding:16px 18px">
  <div class="ff-feed-head"><span class="ff-dot" style="background:var(--enc)"></span>
    <span class="t">Your coaches, personalized</span>
    <span class="ff-live" style="color:var(--muted);background:transparent;border-color:var(--strong)">{_esc(count)}× recalibrated</span>
  </div>
  {bars}
  {personalized}
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
