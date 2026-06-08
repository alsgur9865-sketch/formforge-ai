# 파일 위치: ui/sample_data.py
"""클라우드 없이 UI 렌더를 확인하기 위한 샘플 debate 스냅샷.

⚠️ 신뢰성: pose_data(reps·각도·safety_flags·camera_angle)는 squat_demo.mp4 에 실제
run_pose_extractor 를 돌려 나온 **진짜 파이프라인 출력**이다 (측면 영상 → 무릎 정렬은
not_visible, 실제 잡힌 flag 는 excessive_forward_lean + inconsistent_depth/tempo).
토론/합의는 그 실측에 맞춰 작성된 영어 데모 콘텐츠. 가짜 valgus 같은 거짓 정밀 없음.

실제 Firestore `debates/{id}` 스키마와 필드명을 1:1로 맞춤. ?demo=1 일 때만 사용.
표시 콘텐츠는 영어(영어권 심사 대상). 백엔드 Gemini 페르소나는 별도(agents/)이며 한국어 유지.
"""
from __future__ import annotations

from typing import Any


def sample_debate() -> dict[str, Any]:
    """feedback_pending 상태(토론 완료 + 판결)까지 채워진 샘플. pose_data 는 실측."""
    return {
        "debate_id": "demo-squat-0001",
        "user_id": "demo-user",
        "video_uri": "",  # 데모: 영상 대신 미리 구운 주석 프리즈프레임(keyframe_urls) 주입
        "exercise_type": "squat",
        "status": "feedback_pending",
        "trace_ids": {"mediator_trace_id": "0a1b2c3d4e5f60718293a4b5c6d7e8f9"},
        "pose_data": {
            "exercise_type": "squat",
            "camera_angle": "side",
            "rep_count": 3,
            "duration_seconds": 23.4,
            "reps": [
                {"rep_number": 1, "depth_degrees": 26, "knee_alignment": "not_visible",
                 "back_angle_at_bottom": 42, "back_angle_at_top": 12,
                 "tempo": {"down_sec": 2.29, "up_sec": 1.38, "pause_sec": 0.0}},
                {"rep_number": 2, "depth_degrees": 29, "knee_alignment": "not_visible",
                 "back_angle_at_bottom": 45, "back_angle_at_top": 14,
                 "tempo": {"down_sec": 1.31, "up_sec": 1.55, "pause_sec": 0.0}},
                {"rep_number": 3, "depth_degrees": 41, "knee_alignment": "not_visible",
                 "back_angle_at_bottom": 45, "back_angle_at_top": 13,
                 "tempo": {"down_sec": 1.92, "up_sec": 1.01, "pause_sec": 0.0}},
            ],
            "overall_metrics": {
                "depth_consistency": 0.80,
                "tempo_consistency": 0.78,
                "form_score_0_100": 65,
            },
            "safety_flags": [
                {"severity": "medium", "issue": "excessive_forward_lean", "rep_numbers": [1, 2, 3],
                 "rationale": "The torso pitches forward excessively at the bottom (42–45° from vertical), which can load the lower back under weight."},
                {"severity": "low", "issue": "inconsistent_depth", "rep_numbers": [1, 2, 3],
                 "rationale": "Squat depth varies noticeably from rep to rep."},
                {"severity": "low", "issue": "inconsistent_tempo", "rep_numbers": [1, 2, 3],
                 "rationale": "Movement speed — especially the ascent — isn't consistent between reps."},
            ],
            "reasoning": "Filmed from the side, so knee alignment (valgus/varus) couldn't be assessed. Depth was good overall — even below parallel — but it varied rep to rep, as did tempo. The torso also tends to pitch forward excessively, which needs correction.",
            "warnings": [],
            "disclaimer": "This analysis is for informational purposes only. Not medical advice.",
            "_metadata": {"stage2_model": "gemini-2.5-flash", "keyframes_sent": 5, "stage2_latency_sec": 4.2},
            # NOTE: keyframe_urls 는 streamlit_app 이 미리 구운 demo_keyframe.jpg(data URI)로 주입
        },
        "rounds": [
            {
                "round": 1,
                "round_latency_seconds": 26.0,
                "encourager": {
                    "agent": "encourager", "round": 1,
                    "praise": "You're hitting real depth — below parallel, consistently. That's the hard part and you own it.",
                    "concern_one": "Your chest dips forward at the bottom — staying tall would protect your lower back.",
                    "actionable_tip": "Cue 'chest up, brace' on the way down — one thought, big payoff.",
                    "tone_metadata": {"warmth": 0.7, "detail": 0.6},
                    "addresses_scrutinizer": None,
                },
                "scrutinizer": {
                    "agent": "scrutinizer", "round": 1,
                    "primary_risk": {
                        "name": "excessive_forward_lean", "severity": "medium-high",
                        "mechanism": "A 42–45° forward torso lean at the bottom shifts load to the lumbar spine — shear stress under a loaded bar.",
                        "evidence_in_data": "back_angle_at_bottom 42–45° on all 3 reps.",
                        "threshold_breach": "Sustained forward lean across every rep, not a one-off.",
                    },
                    "secondary_concerns": [
                        {"name": "inconsistent_depth", "severity": "low", "note": "depth swings 26°→41° between reps."},
                    ],
                    "required_action": "Fix the torso angle before adding load. Depth isn't the problem — the spine is.",
                    "tone_metadata": {"harshness": 0.7, "detail": 0.8},
                    "addresses_encourager": None,
                },
                "verdict": {"converged": False, "shared_issue": "excessive_forward_lean",
                            "reason": "Agreement on depth; disagreement on how hard to push the forward-lean issue."},
            },
            {
                "round": 2,
                "round_latency_seconds": 24.0,
                "encourager": {
                    "agent": "encourager", "round": 2,
                    "praise": "The forward lean is real — I'm not arguing that.",
                    "concern_one": "But piling every correction on at once is how people quit.",
                    "actionable_tip": "One cue — chest up — and let the depth stay the win it already is.",
                    "tone_metadata": {"warmth": 0.68, "detail": 0.62},
                    "addresses_scrutinizer": "Agreed it's a real risk — but overwhelming them backfires.",
                },
                "scrutinizer": {
                    "agent": "scrutinizer", "round": 2,
                    "primary_risk": {
                        "name": "excessive_forward_lean", "severity": "high",
                        "mechanism": "A consistent 42–45° lean under added load is a lumbar injury waiting to happen — this isn't a style note.",
                        "evidence_in_data": "Every single rep breaches; there's no clean rep to build from.",
                        "threshold_breach": "3/3 reps — a pattern, not fatigue.",
                    },
                    "secondary_concerns": [],
                    "required_action": "No added load until the torso angle is fixed. Encouragement doesn't change the shear math.",
                    "tone_metadata": {"harshness": 0.78, "detail": 0.82},
                    "addresses_encourager": "Tone is fine, but a hard load gate is non-negotiable here.",
                },
                "verdict": {"converged": False, "shared_issue": "excessive_forward_lean",
                            "reason": "Both agree the lean is the issue — still split on how hard to gate the load."},
            },
            {
                "round": 3,
                "round_latency_seconds": 21.0,
                "encourager": {
                    "agent": "encourager", "round": 3,
                    "praise": "Okay — one cue, and a clear line on load. I can coach that.",
                    "concern_one": "Chest up + brace, and we hold load until the torso stays tall.",
                    "actionable_tip": "Film the side again next set so you can see the angle change for yourself.",
                    "tone_metadata": {"warmth": 0.66, "detail": 0.64},
                    "addresses_scrutinizer": "Taking the load gate — framed as a goal, not a punishment.",
                },
                "scrutinizer": {
                    "agent": "scrutinizer", "round": 3,
                    "primary_risk": {
                        "name": "excessive_forward_lean", "severity": "medium",
                        "mechanism": "With a chest-up cue and a load gate, the lean is correctable — the risk becomes manageable.",
                        "evidence_in_data": "The lean is consistent, so a single cue can move all 3 reps at once.",
                        "threshold_breach": "Acceptable once the torso holds under the cue.",
                    },
                    "secondary_concerns": [],
                    "required_action": "Add load only after the torso stays upright under the cue. Agreed.",
                    "tone_metadata": {"harshness": 0.6, "detail": 0.78},
                    "addresses_encourager": "Conceding on tone — the load gate holds, and we're aligned.",
                },
                "verdict": {"converged": True, "shared_issue": "excessive_forward_lean",
                            "reason": "Consensus: chest-up cue first, hold load until the torso stays tall."},
            },
        ],
        "consensus": {
            "agent": "mediator",
            "consensus": "Great depth — you're hitting below parallel. The fix is your torso: it pitches forward ~45° at the bottom and loads your lower back. Cue chest-up + brace, even out the tempo, and add load only once the torso angle holds.",
            "priority_actions": [
                {"order": 1, "action": "Keep the chest up — reduce the forward lean", "rationale": "42–45° lean at the bottom means lumbar shear under load."},
                {"order": 2, "action": "Even out tempo toward ~2s on the descent", "rationale": "Consistent control across reps."},
                {"order": 3, "action": "Re-film from the side on the next set", "rationale": "Confirm the torso angle with data."},
            ],
            "past_debate_references": [
                {"debate_id": "demo-squat-feb", "date": "2026-02-14", "outcome": "logged a forward-lean caution"},
            ],
            "disclaimer": "This analysis is for informational purposes only. Not medical advice. If you feel pain, injury, or persistent discomfort during exercise, stop and consult a qualified medical or fitness professional.",
            "round_count_used": 3,
        },
    }


def sample_persona_state() -> dict[str, Any]:
    """users/{id}.persona_state 샘플 (피드백 진화 표시용)."""
    return {
        "encourager": {"warmth": 0.66, "detail": 0.62},
        "scrutinizer": {"harshness": 0.62, "detail": 0.78},
        "total_feedback_count": 4,
    }
