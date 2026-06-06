# 파일 위치: ui/sample_data.py
"""클라우드 없이 UI 렌더를 확인하기 위한 샘플 debate 스냅샷.

실제 Firestore `debates/{id}` 스키마와 필드명을 1:1로 맞춤 (firestore_client / mediator /
pose_extractor 출력 구조). UI 컴포넌트 렌더 검증·디자인 이터레이션용. 프로덕션 플로우에는
관여하지 않음 (streamlit_app.py에서 ?demo=1 일 때만 사용).

표시 콘텐츠는 영어(영어권 심사 대상). 백엔드 Gemini 페르소나는 별도(agents/)이며 한국어 유지.
"""
from __future__ import annotations

from typing import Any


def sample_debate() -> dict[str, Any]:
    """feedback_pending 상태(토론 완료 + 판결)까지 채워진 샘플."""
    return {
        "debate_id": "demo-squat-0001",
        "user_id": "demo-user",
        "video_uri": "",  # 데모: 영상 없이 placeholder 뷰어
        "exercise_type": "squat",
        "status": "feedback_pending",
        "trace_ids": {"mediator_trace_id": "0a1b2c3d4e5f60718293a4b5c6d7e8f9"},
        "pose_data": {
            "exercise_type": "squat",
            "camera_angle": "side",
            "rep_count": 5,
            "duration_seconds": 23.4,
            "reps": [
                {"rep_number": 1, "depth_degrees": 95, "knee_alignment": "valgus_mild",
                 "back_angle_at_bottom": 42, "back_angle_at_top": 88,
                 "tempo": {"down_sec": 1.2, "up_sec": 1.4, "pause_sec": 0.0}},
                {"rep_number": 3, "depth_degrees": 92, "knee_alignment": "valgus_mild",
                 "back_angle_at_bottom": 44, "back_angle_at_top": 87,
                 "tempo": {"down_sec": 1.1, "up_sec": 1.5, "pause_sec": 0.0}},
                {"rep_number": 5, "depth_degrees": 96, "knee_alignment": "neutral",
                 "back_angle_at_bottom": 41, "back_angle_at_top": 89,
                 "tempo": {"down_sec": 1.3, "up_sec": 1.4, "pause_sec": 0.0}},
            ],
            "overall_metrics": {
                "depth_consistency": 0.87,
                "tempo_consistency": 0.72,
                "form_score_0_100": 73,
            },
            "safety_flags": [
                {"severity": "medium", "issue": "knee_valgus_left", "rep_numbers": [1, 3],
                 "rationale": "Left knee caves inward on the descent — an ACL stress vector under load."},
                {"severity": "low", "issue": "fast_eccentric", "rep_numbers": [1, 2, 3],
                 "rationale": "The eccentric (descent) runs fast at 1.2s — a sign of reduced control."},
            ],
            "reasoning": "Depth is stable and consistent overall. That said, left-knee valgus and a fast descent show up repeatedly.",
            "warnings": [],
            "disclaimer": "This analysis is for informational purposes only. Not medical advice.",
            "_metadata": {"stage2_model": "gemini-2.5-flash", "keyframes_sent": 6, "stage2_latency_sec": 4.2},
            # NOTE: keyframe_urls 는 §8 백엔드 작업 전까지 없음 → 뷰어는 placeholder/영상으로 fallback
        },
        "rounds": [
            {
                "round": 1,
                "round_latency_seconds": 26.0,
                "encourager": {
                    "agent": "encourager", "round": 1,
                    "praise": "You're hitting parallel depth consistently — that's the part most lifters struggle with.",
                    "concern_one": "Brace your core half a beat earlier on the way down and it'll feel even more solid.",
                    "actionable_tip": "Hold just one cue: push your knees out over your toes.",
                    "tone_metadata": {"warmth": 0.7, "detail": 0.6},
                    "addresses_scrutinizer": None,
                },
                "scrutinizer": {
                    "agent": "scrutinizer", "round": 1,
                    "primary_risk": {
                        "name": "knee_valgus_left", "severity": "medium-high",
                        "mechanism": "Under load, knee valgus puts shear stress on the ACL and the medial ligaments.",
                        "evidence_in_data": "valgus_mild on reps 1 and 3, safety_flag medium.",
                        "threshold_breach": "Repeated valgus paired with a fast eccentric.",
                    },
                    "secondary_concerns": [
                        {"name": "fast_eccentric", "severity": "low", "note": "1.2s descent — control is slipping."},
                    ],
                    "required_action": "Fix knee tracking before adding load. This is not 'fine'.",
                    "tone_metadata": {"harshness": 0.7, "detail": 0.8},
                    "addresses_encourager": None,
                },
                "verdict": {"converged": False, "shared_issue": "knee_valgus_left",
                            "reason": "Agreement on depth; disagreement on how hard to push the knee issue."},
            },
            {
                "round": 2,
                "round_latency_seconds": 22.0,
                "encourager": {
                    "agent": "encourager", "round": 2,
                    "praise": "The knee absolutely needs addressing — agreed.",
                    "concern_one": "But one clean cue keeps motivation up better than scaring them off.",
                    "actionable_tip": "Knees out over the toes, and slow the descent to 2 seconds.",
                    "tone_metadata": {"warmth": 0.66, "detail": 0.62},
                    "addresses_scrutinizer": "Acknowledge the risk, but keep the coaching tone.",
                },
                "scrutinizer": {
                    "agent": "scrutinizer", "round": 2,
                    "primary_risk": {
                        "name": "knee_valgus_left", "severity": "medium",
                        "mechanism": "If a cue doesn't fix it, the rule is no more load.",
                        "evidence_in_data": "rep 5 improved to neutral — it's correctable.",
                        "threshold_breach": "But it can return under load or fatigue.",
                    },
                    "secondary_concerns": [],
                    "required_action": "Allow more load only once the cue corrects it on the spot.",
                    "tone_metadata": {"harshness": 0.62, "detail": 0.78},
                    "addresses_encourager": "Conceding on tone, holding the line on the load gate.",
                },
                "verdict": {"converged": True, "shared_issue": "knee_valgus_left",
                            "reason": "Consensus: fix the knee first, via a cue-based approach."},
            },
        ],
        "consensus": {
            "agent": "mediator",
            "consensus": "Solid squat — one priority fix. Depth passes, so let's lock down the knee: push it out over the toes and slow the descent to 2 seconds. Add load only after the knee tracking holds.",
            "priority_actions": [
                {"order": 1, "action": "Track the knee out past the toe line", "rationale": "Less left-knee valgus means less ACL stress."},
                {"order": 2, "action": "Eccentric (descent) 1.2s → 2.0s", "rationale": "Control keeps the valgus from returning."},
                {"order": 3, "action": "Re-film from the side on the next set", "rationale": "Confirm the fix with data."},
            ],
            "past_debate_references": [
                {"debate_id": "demo-squat-feb", "date": "2026-02-14", "outcome": "logged a knee_valgus caution"},
            ],
            "disclaimer": "This analysis is for informational purposes only. Not medical advice. If you feel pain, injury, or persistent discomfort during exercise, stop and consult a qualified medical or fitness professional.",
            "round_count_used": 2,
        },
    }


def sample_persona_state() -> dict[str, Any]:
    """users/{id}.persona_state 샘플 (피드백 진화 표시용)."""
    return {
        "encourager": {"warmth": 0.66, "detail": 0.62},
        "scrutinizer": {"harshness": 0.62, "detail": 0.78},
        "total_feedback_count": 4,
    }
