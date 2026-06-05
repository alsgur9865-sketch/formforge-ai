# 파일 위치: ui/components/debate_view.py
"""시그니처 화면 렌더 — 순수 HTML 문자열 빌더(Streamlit 비의존, 테스트 가능).

DESIGN.md "The Diagnostic Freeze-Frame":
- 영웅(좌): 진단 뷰어(영상/주석 프레임) + pose readout.
- 토론(우): 멈춘 split이 아니라 하나의 격해지는 피드.
- 색 = 의미(risk 빨강 / good 초록), 페르소나 hue는 2차.

실제 Firestore `debates/{id}` 스키마 필드에 1:1 바인딩.
"""
from __future__ import annotations

import html
from typing import Any

_SEV_RISK = {"high", "medium-high", "medium", "critical"}


def _esc(v: Any) -> str:
    return html.escape(str(v if v is not None else ""))


def _humanize(token: str) -> str:
    """knee_valgus_left -> Knee Valgus (L)."""
    t = (token or "").replace("_", " ").strip()
    t = t.replace(" left", " (L)").replace(" right", " (R)")
    return t.title().replace("(L)", "(L)").replace("(R)", "(R)")


def _sev_class(severity: str) -> str:
    s = (severity or "").lower()
    if any(k in s for k in _SEV_RISK):
        return "risk"
    if "low" in s:
        return "warning"
    return "good"


# ---------------------------------------------------------------- tale of the tape
def tale_of_the_tape(debate: dict[str, Any]) -> str:
    pose = debate.get("pose_data") or {}
    exercise = _esc((debate.get("exercise_type") or pose.get("exercise_type") or "—").title())
    rep_count = pose.get("rep_count")
    rounds = debate.get("rounds") or []
    n_rounds = len(rounds)
    max_rounds = max(n_rounds, 3)

    sub_bits = []
    if rep_count:
        sub_bits.append(f"{rep_count} REPS")
    if pose.get("camera_angle"):
        sub_bits.append(f"{_esc(pose['camera_angle']).upper()} VIEW")
    sub = " · ".join(sub_bits) if sub_bits else "ANALYZING"

    # tension = 마지막 라운드 수렴 여부 + scrutinizer harshness
    converged = bool(rounds and (rounds[-1].get("verdict") or {}).get("converged"))
    if not rounds:
        needle, label = 50, "—"
    elif converged:
        needle, label = 50, "RESOLVED · 코치 합의 도달"
    else:
        needle, label = 68, "HIGH · 코치 의견 갈림"

    return f"""
<div class="ff-tape">
  <div>
    <div class="ex">{exercise}</div>
    <div class="sub ff-mono">{sub}</div>
  </div>
  <div class="tension">TENSION
    <div class="ff-tbar"><i style="left:{needle}%"></i></div>
  </div>
  <div class="pill ff-mono">ROUND {n_rounds} / {max_rounds}</div>
</div>
<div class="ff-mono" style="font-size:10.5px;color:var(--warning);margin:-8px 0 14px 2px">{_esc(label)}</div>
"""


# ---------------------------------------------------------------- diagnostic viewer (hero)
def viewer_html(pose_data: dict[str, Any] | None, video_url: str | None) -> str:
    pose = pose_data or {}
    angle = _esc((pose.get("camera_angle") or "—")).upper()
    flags = pose.get("safety_flags") or []
    top_flag = ""
    if flags:
        top_flag = f'<div class="r"><b></b>▲ {_esc(_humanize(flags[0].get("issue", "")))}</div>'

    keyframes = pose.get("keyframe_urls") or []  # §8 백엔드 도입 후 채워짐
    if keyframes:
        media = f'<img src="{_esc(keyframes[0])}" alt="annotated pose"/>'
    elif video_url:
        media = f'<video src="{_esc(video_url)}" controls preload="metadata"></video>'
    else:
        msg = "분석 중…" if not pose else "주석 프레임 준비 중 — 영상/키프레임 대기"
        media = f'<div class="vempty">{_esc(msg)}</div>'

    return f"""
<div class="ff-viewer">
  <div class="vchrome">
    <span class="l">POSE · MediaPipe · {angle}</span>
    {top_flag}
  </div>
  {media}
</div>
"""


def readout_html(pose_data: dict[str, Any] | None) -> str:
    pose = pose_data or {}
    if not pose:
        return ""
    metrics = pose.get("overall_metrics") or {}
    score = metrics.get("form_score_0_100")
    reps = pose.get("reps") or []
    depths = [r.get("depth_degrees") for r in reps if r.get("depth_degrees") is not None]
    avg_depth = round(sum(depths) / len(depths)) if depths else None

    score_html = (
        f'<span class="ff-score">{score}<small>/100</small></span>'
        if score is not None else '<span class="ff-score">—</span>'
    )

    rows = ""
    if avg_depth is not None:
        good = avg_depth <= 100  # 낮을수록 깊음(패러렐≈90)
        rows += f'<div class="row"><span class="k">DEPTH (avg)</span><span class="v" style="color:var(--{"good" if good else "warning"})">{avg_depth}°</span></div>'
    if metrics.get("depth_consistency") is not None:
        rows += f'<div class="row"><span class="k">DEPTH CONSISTENCY</span><span class="v">{round(metrics["depth_consistency"]*100)}%</span></div>'
    if metrics.get("tempo_consistency") is not None:
        rows += f'<div class="row"><span class="k">TEMPO CONSISTENCY</span><span class="v">{round(metrics["tempo_consistency"]*100)}%</span></div>'

    flags_html = ""
    for f in (pose.get("safety_flags") or []):
        cls = _sev_class(f.get("severity", ""))
        sym = "▲" if cls == "risk" else ("●" if cls == "warning" else "✓")
        flags_html += f'<span class="ff-badge {cls}">{sym} {_esc(_humanize(f.get("issue","")))}</span>'
    if not flags_html:
        flags_html = '<span class="ff-badge good">✓ NO FLAGS</span>'

    return f"""
<div class="ff-readout">
  <div style="display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:8px">
    <div><div class="ff-micro">FORM SCORE</div>{score_html}</div>
    <div class="ff-mono" style="text-align:right;font-size:11px;color:var(--muted)">REPS {_esc(pose.get("rep_count","—"))}</div>
  </div>
  {rows}
  <div class="ff-flags">{flags_html}</div>
</div>
"""


# ---------------------------------------------------------------- escalating debate feed
def _enc_msg(enc: dict[str, Any], chip_good: str | None) -> str:
    praise = _esc(enc.get("praise", ""))
    sub_bits = [enc.get("concern_one"), enc.get("actionable_tip")]
    sub = " ".join(_esc(s) for s in sub_bits if s)
    addresses = enc.get("addresses_scrutinizer")
    sub_html = f'<div class="sub">{sub}</div>' if sub else ""
    if addresses:
        sub_html += f'<div class="sub" style="color:var(--faint)">↳ {_esc(addresses)}</div>'
    chip = f'<span class="ff-chip good">→ {_esc(chip_good)}</span>' if chip_good else ""
    return f"""
<div class="ff-msg enc">
  <div class="av">E</div>
  <div class="b">
    <div class="nm"><b>The Encourager</b> · Certified PT</div>
    <div class="ff-bub">{praise}{sub_html}{chip}</div>
  </div>
</div>"""


def _scr_msg(scr: dict[str, Any]) -> str:
    risk = scr.get("primary_risk") or {}
    name = _humanize(risk.get("name", "")) or "Risk"
    severity = risk.get("severity", "")
    mechanism = _esc(risk.get("mechanism", ""))
    required = _esc(scr.get("required_action", ""))
    addresses = scr.get("addresses_encourager")
    sub_html = f'<div class="sub">{required}</div>' if required else ""
    if addresses:
        sub_html += f'<div class="sub" style="color:var(--faint)">↳ {_esc(addresses)}</div>'
    cls = _sev_class(severity)
    chip = f'<span class="ff-chip risk">→ {_esc(name.upper())} ▲</span>' if cls == "risk" else \
           f'<span class="ff-chip" style="color:var(--warning);background:color-mix(in srgb,var(--warning) 15%,transparent)">→ {_esc(name.upper())}</span>'
    return f"""
<div class="ff-msg scr">
  <div class="av">S</div>
  <div class="b">
    <div class="nm"><b>The Scrutinizer</b> · Physiologist, PhD</div>
    <div class="ff-bub">{mechanism}{sub_html}{chip}</div>
  </div>
</div>"""


def debate_feed(debate: dict[str, Any]) -> str:
    rounds = debate.get("rounds") or []
    pose = debate.get("pose_data") or {}
    metrics = pose.get("overall_metrics") or {}
    score = metrics.get("form_score_0_100")
    good_chip = f"FORM {score}/100" if score is not None else "DEPTH OK"

    live = (debate.get("status") in ("pending", "debating"))
    live_html = f'<span class="ff-live">● ROUND {len(rounds)}</span>' if live and rounds else ""

    body = ""
    if not rounds:
        body = '<div class="ff-mono" style="color:var(--faint);font-size:12px;padding:20px 0">두 코치가 영상을 분석 중…</div>'
    for i, rnd in enumerate(rounds):
        n = rnd.get("round", i + 1)
        label = f"ROUND {n}" + (" — 격화" if n >= 2 else "")
        body += f'<div class="ff-rounddiv"><span>{_esc(label)}</span></div>'
        enc = rnd.get("encourager") or {}
        scr = rnd.get("scrutinizer") or {}
        # round 1만 good chip(중복 방지)
        body += _enc_msg(enc, good_chip if i == 0 else None)
        body += _scr_msg(scr)

    return f"""
<div class="ff-feed-head">
  <span class="ff-dot"></span><span class="t">Live Debate</span>{live_html}
</div>
{body}
"""


# ---------------------------------------------------------------- mediator verdict
def verdict_html(consensus: dict[str, Any] | None) -> str:
    if not consensus:
        return ""
    text = _esc(consensus.get("consensus", ""))
    actions = consensus.get("priority_actions") or []
    checks = ""
    for a in actions:
        order = _esc(a.get("order", "•"))
        action = _esc(a.get("action", ""))
        rationale = _esc(a.get("rationale", ""))
        rat_html = f'<span class="rat">{rationale}</span>' if rationale else ""
        checks += f'<li><span class="num">{order}</span><div>{action}{rat_html}</div></li>'

    refs = consensus.get("past_debate_references") or []
    recall = ""
    if refs:
        n = len(refs)
        recall = f'<div class="ff-recall">⟲ 과거 세션 {n}건 회상 — 당신의 이력이 이번 판결에 반영됨 <span style="color:var(--faint)">(Phoenix MCP)</span></div>'

    disclaimer = _esc(consensus.get("disclaimer", "이 분석은 정보 제공용입니다. 의학 조언이 아닙니다."))
    rcount = consensus.get("round_count_used")
    who = f"The Mediator · Head Coach" + (f" · {rcount} rounds" if rcount else "")

    return f"""
<div class="ff-verdict"><div class="ff-verdict-in">
  <div class="vh"><span class="lbl">VERDICT</span><span class="who">{_esc(who)}</span></div>
  <p>{text}</p>
  <ul class="ff-checks">{checks}</ul>
  {recall}
  <div class="ff-disc">⚠️ {disclaimer}</div>
</div></div>
"""
