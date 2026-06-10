# 파일 위치: ui/sample_data.py
"""클라우드 없이 UI 렌더를 확인하기 위한 샘플 debate 스냅샷.

⚠️ 신뢰성: pose_data(reps·각도·safety_flags·camera_angle)는 squat_front_demo.mp4 에 실제
run_pose_extractor 를 돌려 나온 **진짜 파이프라인 출력**이다 (정면 영상 → 무릎 정렬 평가 가능,
rep1 valgus_mild + 깊이가 rep마다 18°~97° 로 극심하게 들쭉날쭉 = inconsistent_depth high).
토론/합의는 그 실측에 맞춰 작성된 영어 데모 콘텐츠. 가짜 정밀 없음.

실제 Firestore `debates/{id}` 스키마와 필드명을 1:1로 맞춤. ?demo=1 일 때만 사용.
표시 콘텐츠는 영어(영어권 심사 대상). 백엔드 Gemini 페르소나는 별도(agents/)이며 한국어 유지.
"""
from __future__ import annotations

from typing import Any


def sample_debate(angle: str = "front") -> dict[str, Any]:
    """feedback_pending 상태(토론 완료 + 판결)까지 채워진 샘플. pose_data 는 실측.

    angle="front"(기본): 정면 valgus + 깊이 편차. angle="side": 측면 등 말림/전방 기울임
    (무릎 not_visible — 카메라앵글 인지 데모). 둘 다 진짜 파이프라인 출력 기반.
    """
    if angle == "side":
        return _side_debate()
    return {
        "debate_id": "demo-squat-0001",
        "user_id": "demo-user",
        "video_uri": "",  # 데모: 영상 대신 미리 구운 주석 프리즈프레임(keyframe_urls) 주입
        "exercise_type": "squat",
        "status": "feedback_pending",
        "trace_ids": {"mediator_trace_id": "0a1b2c3d4e5f60718293a4b5c6d7e8f9"},
        "mcp_tool_calls": ["query_past_debates", "query_similar_safety_flags"],  # A: 영수증 데모용
        "pose_data": {
            "exercise_type": "squat",
            "camera_angle": "front",
            "rep_count": 5,
            "duration_seconds": 16.8,
            "reps": [
                {"rep_number": 1, "depth_degrees": 53, "knee_alignment": "valgus_mild",
                 "back_angle_at_bottom": 13, "back_angle_at_top": 11,
                 "tempo": {"down_sec": 1.27, "up_sec": 1.07, "pause_sec": 0.0}},
                {"rep_number": 2, "depth_degrees": 97, "knee_alignment": "neutral",
                 "back_angle_at_bottom": 4, "back_angle_at_top": 1,
                 "tempo": {"down_sec": 1.30, "up_sec": 0.93, "pause_sec": 0.0}},
                {"rep_number": 3, "depth_degrees": 18, "knee_alignment": "neutral",
                 "back_angle_at_bottom": 9, "back_angle_at_top": 5,
                 "tempo": {"down_sec": 1.60, "up_sec": 1.60, "pause_sec": 0.0}},
                {"rep_number": 4, "depth_degrees": 97, "knee_alignment": "neutral",
                 "back_angle_at_bottom": 5, "back_angle_at_top": 3,
                 "tempo": {"down_sec": 0.77, "up_sec": 0.33, "pause_sec": 0.0}},
                {"rep_number": 5, "depth_degrees": 31, "knee_alignment": "neutral",
                 "back_angle_at_bottom": 3, "back_angle_at_top": 1,
                 "tempo": {"down_sec": 0.87, "up_sec": 0.67, "pause_sec": 0.0}},
            ],
            "overall_metrics": {
                "depth_consistency": 0.45,
                "tempo_consistency": 0.74,
                "form_score_0_100": 60,
            },
            "safety_flags": [
                {"severity": "high", "issue": "inconsistent_depth", "rep_numbers": [1, 2, 3, 4, 5],
                 "rationale": "Squat depth swings wildly between reps — from 18° (rock-bottom) to 97° (barely a quarter squat). The body never grooves one pattern."},
                {"severity": "medium", "issue": "insufficient_depth", "rep_numbers": [2, 4],
                 "rationale": "Reps 2 and 4 stop around 97° — well above parallel, leaving most of the squat on the table."},
                {"severity": "medium", "issue": "tempo_too_fast", "rep_numbers": [4, 5],
                 "rationale": "Reps 4–5 are rushed, especially the ascent — little control out of the hole."},
                {"severity": "low", "issue": "knee_valgus", "rep_numbers": [1],
                 "rationale": "On rep 1 the knees drift slightly inward at the bottom (mild valgus)."},
            ],
            "reasoning": "Filmed from the front, so knee tracking was assessable — rep 1 showed mild inward drift. The standout problem is depth: it swings from a very deep 18° to a barely-there 97° rep to rep, which makes the set impossible to load safely. A couple of reps were also rushed.",
            "warnings": [],
            "disclaimer": "This analysis is for informational purposes only. Not medical advice.",
            "_metadata": {"stage2_model": "gemini-2.5-flash", "keyframes_sent": 6, "stage2_latency_sec": 16.5},
            # NOTE: keyframe_urls 는 streamlit_app 이 미리 구운 demo_keyframe.jpg(data URI)로 주입
        },
        "rounds": [
            {
                "round": 1,
                "round_latency_seconds": 26.0,
                "encourager": {
                    "agent": "encourager", "round": 1,
                    "praise": "When you commit, you can really sink it — rep 3 hit 18°, that's a genuinely deep, full squat. The range is in you.",
                    "concern_one": "But your depth is all over the place — some reps barely break a quarter.",
                    "actionable_tip": "Pick one depth and own it — a box or bench to tap gives you the same target every rep.",
                    "tone_metadata": {"warmth": 0.7, "detail": 0.6},
                    "addresses_scrutinizer": None,
                },
                "scrutinizer": {
                    "agent": "scrutinizer", "round": 1,
                    "primary_risk": {
                        "name": "inconsistent_depth", "severity": "medium-high",
                        "mechanism": "Depth swinging from 18° to 97° means the body never grooves one pattern — you cannot safely load a lift that changes every single rep.",
                        "evidence_in_data": "5 reps measured 53°, 97°, 18°, 97°, 31° — no two alike (depth_consistency 0.45).",
                        "threshold_breach": "Consistency 0.45 — random, not a pattern.",
                    },
                    "secondary_concerns": [
                        {"name": "knee_valgus", "severity": "low", "note": "rep 1 knees drift slightly inward."},
                    ],
                    "required_action": "Groove ONE consistent depth before any load. And keep rep 1's knees tracking out.",
                    "tone_metadata": {"harshness": 0.7, "detail": 0.8},
                    "addresses_encourager": None,
                },
                "verdict": {"converged": False, "shared_issue": "inconsistent_depth",
                            "reason": "Agreement the depth varies; disagreement on how hard to gate the load."},
            },
            {
                "round": 2,
                "round_latency_seconds": 24.0,
                "encourager": {
                    "agent": "encourager", "round": 2,
                    "praise": "The inconsistency is real — I'm not pretending otherwise.",
                    "concern_one": "But hammering them for every rep being different is how people walk away.",
                    "actionable_tip": "One target, every rep to it — let the deep reps prove the standard.",
                    "tone_metadata": {"warmth": 0.68, "detail": 0.62},
                    "addresses_scrutinizer": "Agreed it's the priority — just frame it as a target, not a failure.",
                },
                "scrutinizer": {
                    "agent": "scrutinizer", "round": 2,
                    "primary_risk": {
                        "name": "inconsistent_depth", "severity": "high",
                        "mechanism": "A 97° rep is barely a squat; an 18° rep is rock-bottom. Loading that lottery is exactly how knees and lower backs get hurt.",
                        "evidence_in_data": "Reps 2 and 4 stop at 97° — quarter squats sitting in the same set as a full 18°.",
                        "threshold_breach": "No repeatable depth = no safe load.",
                    },
                    "secondary_concerns": [],
                    "required_action": "No added load until every rep hits the same target — and rep 1's inward knee gets cued out.",
                    "tone_metadata": {"harshness": 0.78, "detail": 0.82},
                    "addresses_encourager": "Tone's fine, but the load gate is non-negotiable here.",
                },
                "verdict": {"converged": False, "shared_issue": "inconsistent_depth",
                            "reason": "Both agree depth is the issue — still split on how hard to gate the load."},
            },
            {
                "round": 3,
                "round_latency_seconds": 21.0,
                "encourager": {
                    "agent": "encourager", "round": 3,
                    "praise": "Okay — one target, hold load until every rep matches. I can coach that.",
                    "concern_one": "Box-squat to a fixed depth, knees pushing out the whole way.",
                    "actionable_tip": "Film the front again next set — you'll watch the reps line up.",
                    "tone_metadata": {"warmth": 0.66, "detail": 0.64},
                    "addresses_scrutinizer": "Taking the load gate — framed as a goal, not a punishment.",
                },
                "scrutinizer": {
                    "agent": "scrutinizer", "round": 3,
                    "primary_risk": {
                        "name": "inconsistent_depth", "severity": "medium",
                        "mechanism": "With a fixed depth target and a knees-out cue, the depth swing and the mild valgus both resolve — the set becomes loadable.",
                        "evidence_in_data": "Consistent depth turns 5 random reps into one repeatable pattern.",
                        "threshold_breach": "Acceptable once all 5 reps match.",
                    },
                    "secondary_concerns": [],
                    "required_action": "Add load only after 5/5 reps hit the same depth. Agreed.",
                    "tone_metadata": {"harshness": 0.6, "detail": 0.78},
                    "addresses_encourager": "Conceding on tone — the consistency gate holds, and we're aligned.",
                },
                "verdict": {"converged": True, "shared_issue": "inconsistent_depth",
                            "reason": "Consensus: one depth target + knees out, hold load until every rep matches."},
            },
        ],
        "consensus": {
            "agent": "mediator",
            "consensus": "Your depth is the headline — it swings from a deep 18° to a barely-there 97° rep to rep, which makes the set impossible to load safely. Lock one repeatable depth (tap a box or bench), push the knees out (rep 1 drifted in), and only add load once all five reps match.",
            "priority_actions": [
                {"order": 1, "action": "Squat to one consistent target every rep", "rationale": "Depth swung 18°→97° — consistency is only 0.45."},
                {"order": 2, "action": "Push the knees out", "rationale": "Rep 1 showed mild inward knee drift (valgus)."},
                {"order": 3, "action": "Slow the ascent on reps 4–5", "rationale": "Those reps were rushed out of the hole."},
            ],
            "past_debate_references": [
                {"debate_id": "demo-squat-jan", "date": "2026-01-30", "outcome": "flagged inconsistent depth"},
            ],
            "disclaimer": "This analysis is for informational purposes only. Not medical advice. If you feel pain, injury, or persistent discomfort during exercise, stop and consult a qualified medical or fitness professional.",
            "round_count_used": 3,
        },
    }


def _side_debate() -> dict[str, Any]:
    """측면 영상(squat_side_demo.mp4) 실측 기반 — '카메라앵글 인지' 데모.

    무릎은 측면이라 not_visible(정직 보류) / 대신 정면이 못 보는 등 말림·전방 기울임(HIGH)을
    드러낸다. pose_data 는 로컬 run_pose_extractor 실측(깊이 13/11/28°, back 78/46/66°,
    flags = excessive_forward_lean·back_rounding·inconsistent_depth). 토론/합의는 그 실측에
    맞춘 영어 데모 콘텐츠 + Mediator 가 과거 정면 세션(무릎 valgus)을 영수증으로 참조.
    """
    return {
        "debate_id": "demo-squat-side-0001",
        "user_id": "demo-user",
        "video_uri": "",
        "exercise_type": "squat",
        "status": "feedback_pending",
        "trace_ids": {"mediator_trace_id": "1f2e3d4c5b6a79880716253443526170"},
        "mcp_tool_calls": ["query_past_debates", "query_similar_safety_flags"],
        "pose_data": {
            "exercise_type": "squat",
            "camera_angle": "side",
            "rep_count": 3,
            "duration_seconds": 13.27,
            "reps": [
                {"rep_number": 1, "depth_degrees": 13, "knee_alignment": "not_visible",
                 "back_angle_at_bottom": 78, "back_angle_at_top": 87,
                 "tempo": {"down_sec": 1.43, "up_sec": 1.20, "pause_sec": 0.0}},
                {"rep_number": 2, "depth_degrees": 11, "knee_alignment": "not_visible",
                 "back_angle_at_bottom": 46, "back_angle_at_top": 52,
                 "tempo": {"down_sec": 2.03, "up_sec": 1.17, "pause_sec": 0.0}},
                {"rep_number": 3, "depth_degrees": 28, "knee_alignment": "not_visible",
                 "back_angle_at_bottom": 66, "back_angle_at_top": 38,
                 "tempo": {"down_sec": 2.77, "up_sec": 1.00, "pause_sec": 0.0}},
            ],
            "overall_metrics": {
                "depth_consistency": 0.56,
                "tempo_consistency": 0.74,
                "form_score_0_100": 60,
            },
            "safety_flags": [
                {"severity": "high", "issue": "excessive_forward_lean", "rep_numbers": [1, 3],
                 "rationale": "The torso folds far forward at the bottom — back angle hit 78° on rep 1. From the side you can see the chest diving toward the floor instead of staying tall."},
                {"severity": "high", "issue": "back_rounding", "rep_numbers": [1, 2],
                 "rationale": "The upper back rounds under load on reps 1–2 — the spine loses its neutral arch as the squat deepens."},
                {"severity": "medium", "issue": "inconsistent_depth", "rep_numbers": [1, 2, 3],
                 "rationale": "Depth ranges from a very deep 11° to 28° — close, but not yet locked to one repeatable target."},
            ],
            "reasoning": "Filmed from the side, so knee tracking (valgus/varus) is NOT assessable — the left and right knees overlap in the frame. What the side angle does reveal is the spine: the torso folds forward sharply (78° on rep 1) and the upper back rounds as depth increases. The depth itself is genuinely deep; the risk is the back position under that depth.",
            "warnings": [],
            "disclaimer": "This analysis is for informational purposes only. Not medical advice.",
            "_metadata": {"stage2_model": "gemini-2.5-flash", "keyframes_sent": 5, "stage2_latency_sec": 15.9},
        },
        "rounds": [
            {
                "round": 1,
                "round_latency_seconds": 25.0,
                "encourager": {
                    "agent": "encourager", "round": 1,
                    "praise": "You're hitting real depth — 11° on rep 2 is rock-bottom, a full squat most people never touch.",
                    "concern_one": "But your chest is diving toward the floor as you sink.",
                    "actionable_tip": "Think 'proud chest' — lead the descent with your hips, not your head.",
                    "tone_metadata": {"warmth": 0.7, "detail": 0.6},
                    "addresses_scrutinizer": None,
                },
                "scrutinizer": {
                    "agent": "scrutinizer", "round": 1,
                    "primary_risk": {
                        "name": "back_rounding", "severity": "high",
                        "mechanism": "The torso folds to 78° and the upper back rounds — a loaded spine in flexion is the classic disc-injury setup. Depth means nothing if the back buckles to reach it.",
                        "evidence_in_data": "Back angle 78° at the bottom of rep 1; upper-back rounding on reps 1–2.",
                        "threshold_breach": "Neutral spine lost under load.",
                    },
                    "secondary_concerns": [
                        {"name": "knees — not assessable", "severity": "n/a",
                         "note": "Side view: I can't measure knee valgus/varus from here. I won't pretend to — film the front for that."},
                    ],
                    "required_action": "Brace the spine and sit back before chasing any more depth.",
                    "tone_metadata": {"harshness": 0.7, "detail": 0.8},
                    "addresses_encourager": None,
                },
                "verdict": {"converged": False, "shared_issue": "back_rounding",
                            "reason": "Both see the back folding; split on whether the depth is a win or a liability."},
            },
            {
                "round": 2,
                "round_latency_seconds": 23.0,
                "encourager": {
                    "agent": "encourager", "round": 2,
                    "praise": "The depth is real and I won't take that from you.",
                    "concern_one": "But if the back rounds to get there, that depth is borrowed against your spine.",
                    "actionable_tip": "Brace — big breath, ribs down — then sit back to a depth you can hold tall.",
                    "tone_metadata": {"warmth": 0.68, "detail": 0.62},
                    "addresses_scrutinizer": "Agreed the spine comes first — let's frame it as earning the depth back, not losing it.",
                },
                "scrutinizer": {
                    "agent": "scrutinizer", "round": 2,
                    "primary_risk": {
                        "name": "back_rounding", "severity": "high",
                        "mechanism": "78° of forward fold with a rounding upper back is how lower backs get hurt — the deeper you go in that position, the worse the lever on the spine.",
                        "evidence_in_data": "Rep 1: 78° lean, rounded thoracic; rep 3: 66° lean. The fold is consistent, the depth is not.",
                        "threshold_breach": "No load until the spine stays neutral.",
                    },
                    "secondary_concerns": [],
                    "required_action": "Cut depth to where the back stays neutral, brace hard, then rebuild range.",
                    "tone_metadata": {"harshness": 0.78, "detail": 0.82},
                    "addresses_encourager": "Tone's fine — but the spine gate is non-negotiable, and the knees stay unmeasured from this angle.",
                },
                "verdict": {"converged": False, "shared_issue": "back_rounding",
                            "reason": "Both agree spine first; still split on how much depth to give up now."},
            },
            {
                "round": 3,
                "round_latency_seconds": 20.0,
                "encourager": {
                    "agent": "encourager", "round": 3,
                    "praise": "Okay — brace first, sit back, earn the depth with a tall spine. I can coach that.",
                    "concern_one": "Box-squat to a depth you can hold neutral, chest proud.",
                    "actionable_tip": "And film the front next set — that's the only way to check your knees.",
                    "tone_metadata": {"warmth": 0.66, "detail": 0.64},
                    "addresses_scrutinizer": "Taking the spine gate — framed as earning depth back.",
                },
                "scrutinizer": {
                    "agent": "scrutinizer", "round": 3,
                    "primary_risk": {
                        "name": "back_rounding", "severity": "medium",
                        "mechanism": "Brace + sit-back fixes the forward fold; the depth is already there, so once the spine holds, this becomes a strong squat.",
                        "evidence_in_data": "A neutral spine turns an 11° deep rep from a risk into a result.",
                        "threshold_breach": "Acceptable once the back stays neutral through the full depth.",
                    },
                    "secondary_concerns": [],
                    "required_action": "Brace, sit back, hold neutral — then the depth is yours. Agreed. And get a front-angle clip for the knees.",
                    "tone_metadata": {"harshness": 0.6, "detail": 0.78},
                    "addresses_encourager": "Conceding on tone — the spine gate holds, and we're aligned.",
                },
                "verdict": {"converged": True, "shared_issue": "back_rounding",
                            "reason": "Consensus: brace + sit back for a neutral spine, then the deep range is a strength. Knees pending a front-angle clip."},
            },
        ],
        "consensus": {
            "agent": "mediator",
            "consensus": "From the side, your back is the headline — the torso folds to 78° and the upper back rounds as you sink, which puts a deep squat on a vulnerable spine. The depth itself is genuinely strong. Brace hard (breath in, ribs down), sit back, and only chase depth you can hold with a tall, neutral spine. One honest note: last session, filmed from the front, I flagged mild knee valgus — from this side angle I can't see your knees at all, so for tracking, film the front. Each angle shows what the other can't.",
            "priority_actions": [
                {"order": 1, "action": "Brace the spine and sit back", "rationale": "Back folded to 78° with upper-back rounding — neutral spine before depth or load."},
                {"order": 2, "action": "Rebuild depth from a position you can hold tall", "rationale": "Depth is already deep (11–28°); the fix is the back, not the range."},
                {"order": 3, "action": "Film the front for knee tracking", "rationale": "Side angle can't assess knee valgus/varus — the front view flagged mild valgus last session."},
            ],
            "past_debate_references": [
                {"debate_id": "demo-squat-front", "date": "2026-06-09", "outcome": "flagged mild knee valgus (front view)"},
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
