# 파일 위치: ui/sample_state.py
"""데모/폴백 상태 — 라이브 파이프라인(GCP·Gemini) 없이도 6화면이 그대로 렌더되도록.

여기 값들은 **실제 백엔드 출력과 동일한 dict 구조**다:
  - SAMPLE_POSE      = agents/pose_extractor.run_pose_extractor() 출력 shape
  - SAMPLE_DEBATE    = agents/debate.DebateResult.as_dict() shape
  - SAMPLE_MEDIATOR  = agents/mediator.MediatorOutput.as_dict() shape
  - SAMPLE_PERSONA_* = storage persona_state.{encourager,scrutinizer} shape
  - SAMPLE_TRACE     = Phoenix span 목록(Gantt 행) shape

데모 모드와 라이브 모드가 **같은 render 매퍼**를 통과하므로, 데모가 곧 매핑 검증이다.
스토리: 측면 스쿼트 / 과도한 전방 기울기(forward lean) / 요추 부상 이력 — 디자인 카피와 일치.
표시 텍스트는 영어(디자인이 영어 Fight Card 톤). 백엔드 Gemini 페르소나는 한국어 유지.
"""

from __future__ import annotations

from typing import Any

# 화면 상단 record 라벨에 쓰는 번호 (디자인의 №048 / №041)
RECORD_CURRENT = "№048"
RECORD_PRIOR = "№041"


# ---------------------------------------------------------------------------
# PoseExtractor 출력 (Stage1 정량 + Stage2 해석 merge)
# ---------------------------------------------------------------------------

SAMPLE_POSE: dict[str, Any] = {
    "exercise_type": "squat",
    "camera_angle": "side",
    "rep_count": 3,
    "duration_seconds": 11.5,
    "reps": [
        {"rep_number": 1, "depth_degrees": 92, "knee_alignment": "not_visible",
         "back_angle_at_bottom": 47, "back_angle_at_top": 12,
         "tempo": {"down_sec": 1.4, "up_sec": 1.2, "pause_sec": 0.3}},
        {"rep_number": 2, "depth_degrees": 90, "knee_alignment": "not_visible",
         "back_angle_at_bottom": 49, "back_angle_at_top": 11,
         "tempo": {"down_sec": 1.5, "up_sec": 1.3, "pause_sec": 0.2}},
        {"rep_number": 3, "depth_degrees": 93, "knee_alignment": "not_visible",
         "back_angle_at_bottom": 51, "back_angle_at_top": 13,
         "tempo": {"down_sec": 1.6, "up_sec": 1.4, "pause_sec": 0.2}},
    ],
    "overall_metrics": {
        "form_score_0_100": 65,
        "depth_consistency": 0.80,
        "tempo_consistency": 0.78,
    },
    "safety_flags": [
        {"severity": "high", "issue": "excessive_forward_lean", "rep_numbers": [1, 2, 3],
         "rationale": "The torso tips past 45°, routing shear force into the lumbar spine — "
                      "dangerous when paired with a prior lower-back injury."},
    ],
    "reasoning": "All 3 reps held a consistent, controlled depth. But at the bottom the torso "
                 "folds to 47–51°, showing a good-morning squat pattern. Side-angle footage, "
                 "so left/right knee valgus was not assessed.",
    "warnings": [],
    "disclaimer": "Informational only. Not medical advice. "
                  "If you feel pain or have an injury, consult a professional.",
}


# ---------------------------------------------------------------------------
# Debate 결과 (2 라운드 → 합의)
# ---------------------------------------------------------------------------

_ENC_R1 = {
    "agent": "encourager", "round": 1,
    "praise": "All three squats hit a consistent, controlled depth — that kind of control isn't easy to build.",
    "concern_one": "Just protect one thing: your lower back through the drive.",
    "actionable_tip": "Cue: lift the chest, and film the next set from the side again to compare.",
    "addresses_scrutinizer": None,
}
_SCR_R1 = {
    "agent": "scrutinizer", "round": 1,
    "primary_risk": {
        "name": "Excessive forward lean",
        "severity": "high",
        "mechanism": "The torso folds past 45°, routing shear force into the lumbar spine — "
                     "and there's a documented lower-back injury on file.",
        "evidence_in_data": "Rep 1·2·3 back_angle_at_bottom 47–51°",
        "threshold_breach": "> 45° (exceeds the intermediate tolerance)",
    },
    "secondary_concerns": [],
    "required_action": "Required: cut load 20–30%, re-pattern the brace.",
    "tone_metadata": {"harshness": 0.5, "detail": 0.8},
    "addresses_encourager": None,
}
_ENC_R2 = {
    "agent": "encourager", "round": 2,
    "praise": "", "concern_one": "", "actionable_tip": "",
    "addresses_scrutinizer": "The lean is real — I'm not dismissing it. But it's the fast-fixable kind: "
                             "drop the load, cue the chest, and it cleans up in a session or two. "
                             "Meanwhile, keep them training.",
}
_SCR_R2 = {
    "agent": "scrutinizer", "round": 2,
    "primary_risk": {
        "name": "Excessive forward lean", "severity": "high",
        "mechanism": "With an injury on record, loaded reps in this position are a cumulative risk.",
        "evidence_in_data": "Rep 1·2·3 back_angle 47–51°", "threshold_breach": "> 45°",
    },
    "secondary_concerns": [],
    "required_action": "'Quick fix' underestimates the risk. With a documented injury, loaded reps in "
                       "this position are stop-and-correct, not cue-and-continue.",
    "tone_metadata": {"harshness": 0.5, "detail": 0.8},
    "addresses_encourager": "'Quick fix' underestimates the risk. With a documented injury, loaded reps in "
                            "this position are stop-and-correct, not cue-and-continue.",
}

SAMPLE_DEBATE: dict[str, Any] = {
    "rounds": [
        {"round": 1, "encourager": _ENC_R1, "scrutinizer": _SCR_R1,
         "verdict": {"converged": False, "shared_issue": None}, "round_latency_seconds": 1.6},
        {"round": 2, "encourager": _ENC_R2, "scrutinizer": _SCR_R2,
         "verdict": {"converged": True, "shared_issue": "Excessive forward lean"}, "round_latency_seconds": 1.2},
    ],
    "converged": True,
    "converged_at_round": 2,
    "shared_issue": "Excessive forward lean",
    "total_latency_seconds": 5.8,
    "forced_stop_reason": None,
}


# ---------------------------------------------------------------------------
# Mediator 합의 (Phoenix MCP introspection 포함)
# ---------------------------------------------------------------------------

SAMPLE_MEDIATOR: dict[str, Any] = {
    "agent": "mediator",
    "consensus": "Both corners agree excessive forward lean is the priority. Given the lower-back "
                 "injury history, the Head Coach sides with caution — correct it now, then build "
                 "back gradually.",
    "priority_actions": [
        {"order": 1, "action": "Cut working load 20–30%",
         "rationale": "Reduces lumbar shear load during re-patterning. The Encourager agrees with the "
                      "Scrutinizer's call as the fastest path back."},
        {"order": 2, "action": "Lift the chest, keep the torso vertical",
         "rationale": "A 'chest up' cue through the drive. The Scrutinizer's mechanism analysis "
                      "validates the Encourager's cue."},
    ],
    "past_debate_references": [
        {"debate_id": "e2e_demo_041", "date": "Apr 18, 2026",
         "outcome": "Same forward-lean flag — logged as a lumbar risk. Resolved, then recurred under load."},
    ],
    "disclaimer": "Informational only. Not medical advice. "
                  "If you feel pain or have an injury, consult a professional.",
    "round_count_used": 2,
}


# ---------------------------------------------------------------------------
# 페르소나 진화 (before/after) + 결과
# ---------------------------------------------------------------------------

SAMPLE_PERSONA_BEFORE = {"harshness": 0.50, "caution": 0.40}
SAMPLE_PERSONA_AFTER = {"harshness": 0.35, "caution": 0.55}

SAMPLE_EVOLUTION_QUOTES = {
    "before": "A textbook motor-control failure. Your lumbar spine is taking load it has no reason "
              "to carry. Stop adding weight right now.",
    "after": "Forward lean is still the priority — but I can see you've been putting in the work. "
             "Keep the load light until the brace locks in. You're closer than you think.",
}
SAMPLE_RESULT = {
    "form_before": 65, "form_after": 74,
    "metric_label": "Forward lean", "metric_before": "HIGH", "metric_after": "MODERATE",
}


# ---------------------------------------------------------------------------
# Phoenix Trace (Gantt 행) — 8.4s 윈도우, 1s = 11.764%
# ---------------------------------------------------------------------------

SAMPLE_TRACE: dict[str, Any] = {
    "metrics": {
        "total_latency": "8.4", "spans": 10, "tokens": "11.9", "llm_calls": 5,
        "p50": "1.2", "mcp_calls": 2, "mcp_latency": "0.5",
    },
    "axis_max": 8,
    "rows": [
        {"type": "span", "name": "PoseExtractor", "sub": "vision", "color": "var(--slate)",
         "indent": 0, "left": 0.0, "width": 24.7, "label": "<b>2.1s</b> · 3 reps · form 65"},
        {"type": "group", "text": "Round 1 · opening reads (parallel)"},
        {"type": "span", "name": "The Encourager", "sub": "r1", "color": "var(--enc)",
         "indent": 1, "left": 24.7, "width": 16.5, "label": "<b>1.4s</b> · 1.8k tok"},
        {"type": "span", "name": "The Scrutinizer", "sub": "r1", "color": "var(--scr)",
         "indent": 1, "left": 24.7, "width": 18.8, "label": "<b>1.6s</b> · 2.1k tok"},
        {"type": "span", "name": "Convergence Judge", "sub": None, "color": "var(--gold)",
         "indent": 1, "left": 43.5, "width": 3.5, "label": "0.3s · <b>not yet &rarr; R2</b>"},
        {"type": "group", "text": "Round 2 · counters (parallel)"},
        {"type": "span", "name": "The Encourager", "sub": "r2", "color": "var(--enc)",
         "indent": 1, "left": 47.1, "width": 11.8, "label": "<b>1.0s</b> · 1.5k tok"},
        {"type": "span", "name": "The Scrutinizer", "sub": "r2", "color": "var(--scr)",
         "indent": 1, "left": 47.1, "width": 14.1, "label": "<b>1.2s</b> · 1.7k tok"},
        {"type": "span", "name": "Convergence Judge", "sub": None, "color": "var(--gold)",
         "indent": 1, "left": 61.2, "width": 3.5, "label": "0.3s · <b>converged &check;</b>"},
        {"type": "group", "text": "Ruling"},
        {"type": "span", "name": "The Mediator", "sub": "head coach", "color": "var(--ember)",
         "indent": 0, "left": 64.7, "width": 34.1, "wide": True, "label": "<b>2.9s</b> · 2.4k tok"},
        {"type": "span", "name": "⟲ query_past_debates", "sub": None, "color": "var(--gold2)",
         "indent": 2, "left": 68.2, "width": 3.5, "mcp": True, "bar_bg": "rgba(201,162,75,.5)",
         "label": "<b>128ms</b> · recalled №041"},
        {"type": "span", "name": "⟲ query_safety_flags", "sub": None, "color": "var(--gold2)",
         "indent": 2, "left": 71.8, "width": 3.0, "mcp": True, "bar_bg": "rgba(201,162,75,.5)",
         "label": "<b>96ms</b> · 2 matches"},
    ],
}
