# 파일 위치: ui/components/trace_view.py
"""P1 — Phoenix 자동 계측 가시화 (trace strip).

정직한 구현: UI는 Phoenix REST를 직접 호출하지 않는다. Firestore에 있는 실제 필드만 사용:
- `pose_data._metadata.stage2_latency_sec` (PoseExtractor Stage 2)
- `rounds[].round_latency_seconds` (각 토론 라운드)
- `trace_ids.mediator_trace_id` (Phoenix 대시보드 딥링크)
가짜 per-agent span 워터폴을 지어내지 않는다.
"""
from __future__ import annotations

import html
from typing import Any


def _esc(v: Any) -> str:
    return html.escape(str(v if v is not None else ""))


def trace_strip(
    debate: dict[str, Any],
    phoenix_base: str | None = None,
    project_name: str | None = None,
) -> str:
    pose = debate.get("pose_data") or {}
    meta = pose.get("_metadata") or {}
    rounds = debate.get("rounds") or []

    segments: list[tuple[str, float, str]] = []  # (label, seconds, css-color)
    stage2 = meta.get("stage2_latency_sec")
    if stage2:
        segments.append(("PoseExtractor", float(stage2), "var(--faint)"))
    for i, rnd in enumerate(rounds):
        lat = rnd.get("round_latency_seconds")
        if lat:
            color = "var(--enc)" if i % 2 == 0 else "var(--scr)"
            segments.append((f"Round {rnd.get('round', i+1)}", float(lat), color))

    if not segments:
        return ""

    total = sum(s[1] for s in segments) or 1.0
    rows = ""
    offset = 0.0
    for label, secs, color in segments:
        width = secs / total * 100
        rows += (
            f'<div class="ff-span"><span class="lab">{_esc(label)}</span>'
            f'<div class="ff-track"><div class="bar" style="left:{offset:.1f}%;width:{width:.1f}%;background:{color}"></div></div>'
            f'<span class="ms">{secs:.1f}s</span></div>'
        )
        offset += width

    # Phoenix 딥링크 (mediator trace)
    trace_id = (debate.get("trace_ids") or {}).get("mediator_trace_id")
    link = ""
    if trace_id and phoenix_base:
        base = phoenix_base.rstrip("/")
        proj = project_name or "default"
        url = f"{base}/projects/{_esc(proj)}/traces/{_esc(trace_id)}"
        link = f'<a class="ff-tracelink" href="{url}" target="_blank">↗ Phoenix에서 전체 trace 보기 · {_esc(trace_id[:12])}…</a>'
    elif trace_id:
        link = f'<div class="ff-mono" style="font-size:10.5px;color:var(--faint);margin-top:8px">trace {_esc(trace_id[:16])}… · Phoenix auto-instrumented</div>'

    return f"""
<div class="ff-trace">
  <div class="ff-trace-head">
    <span class="ff-dot"></span><span class="t">Live Agent Trace</span>
    <span class="src">Arize Phoenix · auto-instrumented · {total:.1f}s</span>
  </div>
  {rows}
  {link}
</div>
"""
