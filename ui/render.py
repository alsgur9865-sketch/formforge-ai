# 파일 위치: ui/render.py
"""Jinja2 템플릿 렌더 + 파이프라인 출력 → 템플릿 컨텍스트 매핑.

설계:
  - 템플릿(ui/templates/*.html)은 디자인 핸드오프를 충실 재현한 self-contained HTML.
  - 여기 매퍼(*_ctx)는 백엔드 dict(pose/debate/mediator/persona/trace)를 받아
    템플릿이 기대하는 컨텍스트로 변환한다. 데모·라이브 모두 같은 매퍼를 통과한다.
  - autoescape=True → LLM/사용자 텍스트는 자동 이스케이프(마크업 깨짐·XSS 방지).
    우리가 만든 정적 HTML 조각(fonts_link, mark, trace label)만 |safe.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ui import theme

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html"]),
)

# 화면별 고정 캔버스 높이 (px) — st.components.v1.html(height=...) 에 사용
SCREEN_HEIGHTS: dict[str, int] = {
    "upload": 920,
    "debate": 1180,
    "consensus": 880,
    "feedback": 880,
    "evolution": 920,
    "trace": 900,
}

# P5 면책 — 화면별 2번째 절 (디자인 카피와 일치)
_CLAUSE2: dict[str, str] = {
    "upload": theme.DISCLAIMER_CLAUSE2,
    "debate": "STOP AND CONSULT A PROFESSIONAL IF YOU FEEL PAIN.",
    "consensus": theme.DISCLAIMER_CLAUSE2,
    "feedback": "FEEDBACK TUNES COACH PERSONA, NOT A DIAGNOSIS. STOP AND CONSULT A PROFESSIONAL IF YOU FEEL PAIN.",
    "evolution": "COACH PERSONA ADAPTS TO YOUR FEEDBACK; IT DOES NOT DIAGNOSE. STOP AND CONSULT A PROFESSIONAL IF YOU FEEL PAIN.",
    "trace": "OBSERVABILITY VIEW · OPENINFERENCE / PHOENIX TRACE · LATENCIES ARE PER-SESSION.",
}

_STAR_WORDS = {1: "needs work", 2: "below par", 3: "fair call", 4: "solid call", 5: "perfect call"}
_CAMERA_LABEL = {"side": "SIDE ANGLE", "front": "FRONT ANGLE", "angled": "ANGLED", "unknown": "ANGLE N/A"}


# ---------------------------------------------------------------------------
# 공통/유틸
# ---------------------------------------------------------------------------

def _base(screen: str) -> dict[str, Any]:
    """모든 템플릿에 주입되는 공통 컨텍스트 (폰트/마크/면책)."""
    return {
        "fonts_link": theme.FONTS_LINK,
        "mark": theme.mark_svg(stroke="#111219" if screen != "trace" else "#0E0F16"),
        "disclaimer1": theme.DISCLAIMER_PRIMARY,
        "disclaimer2": _CLAUSE2.get(screen, theme.DISCLAIMER_CLAUSE2),
    }


def _short(text: str | None, limit: int = 150) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def render_screen(screen: str, ctx: dict[str, Any]) -> str:
    """템플릿 렌더 → HTML 문자열. ctx 에 _base() 가 자동 병합된다."""
    merged = {**_base(screen), **ctx}
    return _env.get_template(f"{screen}.html").render(**merged)


# ---------------------------------------------------------------------------
# 1. Weigh-In (upload)
# ---------------------------------------------------------------------------

_CLASSES = [
    {"key": "squat", "name": "Squat", "detail": "BARBELL · BACK"},
    {"key": "deadlift", "name": "Deadlift", "detail": "CONVENTIONAL"},
    {"key": "pushup", "name": "Push-up", "detail": "BODYWEIGHT"},
]


def upload_ctx(*, exercise_type: str = "squat", injury_flags: list[str] | None = None,
               video_name: str | None = None) -> dict[str, Any]:
    return {
        "classes": _CLASSES,
        "exercise_type": exercise_type,
        "injury_flags": injury_flags or [],
        "video_name": video_name,
    }


# ---------------------------------------------------------------------------
# 2. Live Debate (debate) — HERO
# ---------------------------------------------------------------------------

def _enc_round(enc: dict[str, Any] | None, round_no: int) -> dict[str, Any]:
    enc = enc or {}
    counter_text = (enc.get("addresses_scrutinizer") or "").strip()
    if round_no >= 2 and counter_text:
        return {"counter": "Counters the Red corner", "argument": counter_text}
    return {
        "counter": None,
        "praise": enc.get("praise", ""),
        "concern": enc.get("concern_one", ""),
        "tip": enc.get("actionable_tip", ""),
    }


def _scr_round(scr: dict[str, Any] | None, round_no: int) -> dict[str, Any]:
    scr = scr or {}
    risk = scr.get("primary_risk", {}) or {}
    severity = str(risk.get("severity", "")).upper().replace("-", " ")
    counter_text = (scr.get("addresses_encourager") or "").strip()
    if round_no >= 2 and counter_text:
        return {"counter": "Counters the Green corner", "argument": counter_text, "severity": severity}
    return {
        "counter": None,
        "severity": severity,
        "risk_name": risk.get("name", ""),
        "mechanism": risk.get("mechanism", ""),
        "required": scr.get("required_action", ""),
    }


def debate_ctx(*, pose: dict[str, Any], debate: dict[str, Any] | None,
               mediator: dict[str, Any] | None = None, record_label: str,
               max_rounds: int = 3, prior_record_label: str = "Record №041",
               pending_step: str | None = None) -> dict[str, Any]:
    pose = pose or {}
    debate = debate or {}
    rounds_in = debate.get("rounds", []) or []

    rounds_out: list[dict[str, Any]] = []
    for r in rounds_in:
        rn = r.get("round", len(rounds_out) + 1)
        rounds_out.append({
            "number": rn,
            "caption": "OPENING READS" if rn == 1 else "COUNTERS",
            "enc": _enc_round(r.get("encourager"), rn),
            "scr": _scr_round(r.get("scrutinizer"), rn),
        })

    # 마지막 라운드 scrutinizer severity → tape "severity called" 우측
    last_scr_sev = "HIGH"
    if rounds_in:
        risk = (rounds_in[-1].get("scrutinizer") or {}).get("primary_risk", {}) or {}
        last_scr_sev = str(risk.get("severity", "high")).upper().replace("-", " ")

    tape = [
        {"left": "10 yrs floor", "label": "Experience", "right": "PhD · research"},
        {"left": "Warm, momentum-first", "label": "Coaching style", "right": "Cold, evidence-first", "dim": True},
        {"left": "“Quick, fixable”", "label": "Read on this set", "right": "“Stop & correct”"},
        {"left": "MODERATE", "label": "Severity called", "right": last_scr_sev,
         "lcolor": "var(--gold)", "rcolor": "var(--scr-soft)"},
    ]

    verdict = None
    if mediator and (debate.get("converged") or debate.get("forced_stop_reason")):
        actions = []
        for a in (mediator.get("priority_actions") or [])[:2]:
            actions.append({"n": f"{a.get('order', 0):02d} · {a.get('action', '')}",
                            "text": a.get("rationale", "")})
        recall = None
        refs = mediator.get("past_debate_references") or []
        if refs:
            ref = refs[0]
            recall = {"record": prior_record_label, "date": ref.get("date"),
                      "note": _short(ref.get("outcome"), 90)}
        verdict = {
            "decision": "UNANIMOUS" if debate.get("converged") else "MAJORITY",
            "recall": recall,
            "call": mediator.get("consensus", ""),
            "actions": actions,
        }

    return {
        "record_label": record_label,
        "exercise": str(pose.get("exercise_type", "squat")).upper(),
        "camera_angle": _CAMERA_LABEL.get(pose.get("camera_angle", "side"), "SIDE ANGLE"),
        "rep_count": pose.get("rep_count", "—"),
        "form_score": (pose.get("overall_metrics", {}) or {}).get("form_score_0_100", "—"),
        "current_round": debate.get("converged_at_round") or (len(rounds_out) or 1),
        "max_rounds": max_rounds,
        "tape": tape,
        "rounds": rounds_out,
        "verdict": verdict,
        "pending_step": pending_step,
    }


# ---------------------------------------------------------------------------
# 3. Official Decision (consensus)
# ---------------------------------------------------------------------------

def _coach_position(debate: dict[str, Any], side: str) -> str:
    """마지막 라운드에서 코치의 한 줄 입장(이탤릭 인용)."""
    rounds = debate.get("rounds", []) or []
    if not rounds:
        return ""
    last = rounds[-1]
    if side == "enc":
        enc = last.get("encourager") or {}
        txt = enc.get("addresses_scrutinizer") or " ".join(
            x for x in [enc.get("concern_one"), enc.get("actionable_tip")] if x)
    else:
        scr = last.get("scrutinizer") or {}
        txt = scr.get("addresses_encourager") or scr.get("required_action") or \
            (scr.get("primary_risk", {}) or {}).get("mechanism", "")
    return f'"{_short(txt, 120)}"'


def consensus_ctx(*, mediator: dict[str, Any], debate: dict[str, Any], pose: dict[str, Any],
                  record_label: str, prior_record_label: str = "Record №041") -> dict[str, Any]:
    actions = []
    for a in (mediator.get("priority_actions") or []):
        actions.append({"num": f"{a.get('order', 0):02d}", "title": a.get("action", ""),
                        "rationale": a.get("rationale", "")})

    record = None
    refs = mediator.get("past_debate_references") or []
    if refs:
        ref = refs[0]
        outcome = ref.get("outcome") or ""
        record = {
            "id": prior_record_label,
            "date": ref.get("date", ""),
            "text": outcome,
            "recurring": "Recurring · 2nd occurrence" if ("재발" in outcome or "recur" in outcome.lower()) else None,
        }

    shared = debate.get("shared_issue") or "Primary risk"
    basis = []
    basis.append({"label": _short(shared, 18), "pct": 96, "color": "gold"})
    if len(actions) >= 1:
        basis.append({"label": _short(actions[0]["title"], 18), "pct": 88, "color": "scr"})
    if len(actions) >= 2:
        basis.append({"label": _short(actions[1]["title"], 18), "pct": 64, "color": "enc"})

    return {
        "record_label": record_label,
        "decision": "UNANIMOUS" if debate.get("converged") else "MAJORITY",
        "converged_label": f"CONVERGED · {mediator.get('round_count_used', len(debate.get('rounds', [])))} ROUNDS",
        "enc_position": _coach_position(debate, "enc"),
        "scr_position": _coach_position(debate, "scr"),
        "ruling": mediator.get("consensus", ""),
        "actions": actions,
        "record": record,
        "basis": basis,
        "round_count": mediator.get("round_count_used", len(debate.get("rounds", []) or [])),
    }


# ---------------------------------------------------------------------------
# 4. Score the Corners (feedback)
# ---------------------------------------------------------------------------

def feedback_ctx(*, enc_rating: str = "ok", scr_rating: str = "harsh", stars: int = 4,
                 note: str = "", sent: bool = False, record_label: str,
                 reforge_msg: str | None = None) -> dict[str, Any]:
    return {
        "record_label": record_label,
        "enc_rating": enc_rating,
        "scr_rating": scr_rating,
        "stars": stars,
        "star_word": _STAR_WORDS.get(stars, "solid call"),
        "note": note,
        "sent": sent,
        "reforge_msg": reforge_msg or "The Scrutinizer will ease its harshness next bout. Thanks, judge.",
    }


# ---------------------------------------------------------------------------
# 5. Between Bouts (evolution)
# ---------------------------------------------------------------------------

def evolution_ctx(*, before: dict[str, float], after: dict[str, float],
                  quotes: dict[str, str], result: dict[str, Any],
                  record_label: str, prior_record_label: str = "RECORD №041",
                  current_record_label: str = "RECORD №048", trigger: str = "too harsh") -> dict[str, Any]:
    return {
        "record_label": record_label,
        "before": {"record": prior_record_label, "harshness": before.get("harshness", 0.5),
                   "caution": before.get("caution", 0.4), "quote": quotes.get("before", "")},
        "after": {"record": current_record_label, "harshness": after.get("harshness", 0.35),
                  "caution": after.get("caution", 0.55), "quote": quotes.get("after", "")},
        "trigger": trigger,
        "result": result,
    }


# ---------------------------------------------------------------------------
# 6. Official Timesheet (trace)
# ---------------------------------------------------------------------------

def trace_ctx(*, trace: dict[str, Any], record_label: str) -> dict[str, Any]:
    return {
        "record_label": record_label,
        "metrics": trace.get("metrics", {}),
        "axis_max": trace.get("axis_max", 8),
        "rows": trace.get("rows", []),
    }
