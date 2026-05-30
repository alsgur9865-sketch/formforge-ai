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
         "rationale": "상체가 45°를 넘어 기울며 전단력이 요추로 집중됩니다 — 요추 부상 이력과 결합 시 위험."},
    ],
    "reasoning": "3회 모두 깊이는 일정하고 통제됐습니다. 다만 최저점에서 상체가 47~51°로 과도하게 숙여져 "
                 "굿모닝 스쿼트 패턴이 보입니다. 측면 영상이라 좌우 무릎 외반은 판단하지 않았습니다.",
    "warnings": [],
    "disclaimer": "정보 제공용입니다. 의학적 조언이 아닙니다. 통증이나 부상이 있으면 전문가와 상담하세요.",
}


# ---------------------------------------------------------------------------
# Debate 결과 (2 라운드 → 합의)
# ---------------------------------------------------------------------------

_ENC_R1 = {
    "agent": "encourager", "round": 1,
    "praise": "스쿼트 3회 모두 깊이가 일정하게 통제됐어요 — 그 control 은 쉽게 얻는 게 아닙니다.",
    "concern_one": "한 가지만 지켜요: 드라이브 구간에서 허리를 보호하는 것.",
    "actionable_tip": "큐: 가슴을 세우고, 다음 세트는 다시 측면에서 촬영해 비교해요.",
    "addresses_scrutinizer": None,
}
_SCR_R1 = {
    "agent": "scrutinizer", "round": 1,
    "primary_risk": {
        "name": "과도한 전방 기울기 (forward lean)",
        "severity": "high",
        "mechanism": "상체가 45°를 넘어 숙여지며 전단력이 요추로 라우팅됩니다 — 게다가 요추 부상 이력이 기록돼 있습니다.",
        "evidence_in_data": "Rep 1·2·3 back_angle_at_bottom 47~51°",
        "threshold_breach": "> 45° (intermediate 허용치 초과)",
    },
    "secondary_concerns": [],
    "required_action": "필수: 중량 20–30% 감량, 브레이싱 재패턴.",
    "tone_metadata": {"harshness": 0.5, "detail": 0.8},
    "addresses_encourager": None,
}
_ENC_R2 = {
    "agent": "encourager", "round": 2,
    "praise": "", "concern_one": "", "actionable_tip": "",
    "addresses_scrutinizer": "기울기는 실재해요 — 무시하지 않습니다. 하지만 빠르게 고쳐지는 종류예요: "
                             "중량 내리고 상체 큐 주면 한두 세션에 정리됩니다. 그동안에도 훈련은 계속하게 둬요.",
}
_SCR_R2 = {
    "agent": "scrutinizer", "round": 2,
    "primary_risk": {
        "name": "과도한 전방 기울기 (forward lean)", "severity": "high",
        "mechanism": "부상 이력이 있는 상태에서 이 자세의 부하 반복은 누적 위험입니다.",
        "evidence_in_data": "Rep 1·2·3 back_angle 47~51°", "threshold_breach": "> 45°",
    },
    "secondary_concerns": [],
    "required_action": "'빠른 수정'은 위험을 과소평가합니다. 기록된 부상이 있으면 이 자세의 부하 반복은 "
                       "cue-and-continue 가 아니라 stop-and-correct 입니다.",
    "tone_metadata": {"harshness": 0.5, "detail": 0.8},
    "addresses_encourager": "'빠른 수정'은 위험을 과소평가합니다. 기록된 부상이 있으면 이 자세의 부하 반복은 "
                            "cue-and-continue 가 아니라 stop-and-correct 입니다.",
}

SAMPLE_DEBATE: dict[str, Any] = {
    "rounds": [
        {"round": 1, "encourager": _ENC_R1, "scrutinizer": _SCR_R1,
         "verdict": {"converged": False, "shared_issue": None}, "round_latency_seconds": 1.6},
        {"round": 2, "encourager": _ENC_R2, "scrutinizer": _SCR_R2,
         "verdict": {"converged": True, "shared_issue": "과도한 전방 기울기"}, "round_latency_seconds": 1.2},
    ],
    "converged": True,
    "converged_at_round": 2,
    "shared_issue": "과도한 전방 기울기",
    "total_latency_seconds": 5.8,
    "forced_stop_reason": None,
}


# ---------------------------------------------------------------------------
# Mediator 합의 (Phoenix MCP introspection 포함)
# ---------------------------------------------------------------------------

SAMPLE_MEDIATOR: dict[str, Any] = {
    "agent": "mediator",
    "consensus": "두 코너 모두 과도한 전방 기울기를 우선 과제로 봅니다. 요추 부상 이력을 고려해 "
                 "Head Coach 는 신중 쪽에 섭니다 — 지금 교정하고 나서 점진적으로 올립니다.",
    "priority_actions": [
        {"order": 1, "action": "작업 중량 20–30% 감량",
         "rationale": "재패턴 동안 요추 전단 부하를 줄입니다. Scrutinizer 의 판단을 Encourager 도 "
                      "가장 빠른 복귀 경로로 동의."},
        {"order": 2, "action": "가슴을 세우고 상체를 수직으로",
         "rationale": "드라이브 구간 '가슴 펴기' 큐. Encourager 의 큐를 Scrutinizer 의 기전 분석이 검증."},
    ],
    "past_debate_references": [
        {"debate_id": "e2e_demo_041", "date": "Apr 18, 2026",
         "outcome": "같은 전방 기울기 플래그 — 요추 위험으로 기록. 해결됐다가 부하에서 재발."},
    ],
    "disclaimer": "정보 제공용입니다. 의학적 조언이 아닙니다. 통증이나 부상이 있으면 전문가와 상담하세요.",
    "round_count_used": 2,
}


# ---------------------------------------------------------------------------
# 페르소나 진화 (before/after) + 결과
# ---------------------------------------------------------------------------

SAMPLE_PERSONA_BEFORE = {"harshness": 0.50, "caution": 0.40}
SAMPLE_PERSONA_AFTER = {"harshness": 0.35, "caution": 0.55}

SAMPLE_EVOLUTION_QUOTES = {
    "before": "교과서적인 motor control 실패입니다. 당신의 요추는 감당할 이유가 없는 부하를 받고 있어요. "
              "당장 중량 추가를 멈추세요.",
    "after": "전방 기울기는 여전히 우선 과제예요 — 하지만 분명히 노력해 온 게 보입니다. 브레이스가 자리잡을 "
             "때까지 중량은 가볍게 유지해요. 생각보다 가까워졌어요.",
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
