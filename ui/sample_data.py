# 파일 위치: ui/sample_data.py
"""클라우드 없이 UI 렌더를 확인하기 위한 샘플 debate 스냅샷.

실제 Firestore `debates/{id}` 스키마와 필드명을 1:1로 맞춤 (firestore_client / mediator /
pose_extractor 출력 구조). UI 컴포넌트 렌더 검증·디자인 이터레이션용. 프로덕션 플로우에는
관여하지 않음 (streamlit_app.py에서 ?demo=1 일 때만 사용).
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
                 "rationale": "하강 시 왼쪽 무릎이 안쪽으로 무너지는 패턴 — 부하 하 ACL 스트레스 벡터."},
                {"severity": "low", "issue": "fast_eccentric", "rep_numbers": [1, 2, 3],
                 "rationale": "이심성(하강) 구간이 1.2초로 빠른 편 — 통제력 저하 신호."},
            ],
            "reasoning": "전반적으로 깊이는 안정적이고 일관적입니다. 다만 왼쪽 무릎 외반과 빠른 하강이 반복적으로 관찰됩니다.",
            "warnings": [],
            "disclaimer": "이 분석은 정보 제공용입니다. 의학 조언이 아닙니다.",
            "_metadata": {"stage2_model": "gemini-2.5-flash", "keyframes_sent": 6, "stage2_latency_sec": 4.2},
            # NOTE: keyframe_urls 는 §8 백엔드 작업 전까지 없음 → 뷰어는 placeholder/영상으로 fallback
        },
        "rounds": [
            {
                "round": 1,
                "round_latency_seconds": 26.0,
                "encourager": {
                    "agent": "encourager", "round": 1,
                    "praise": "패러렐 깊이를 일관되게 찍고 있어요 — 대부분의 리프터가 어려워하는 부분이에요.",
                    "concern_one": "하강 때 코어를 반 박자 일찍 잠그면 더 안정적일 거예요.",
                    "actionable_tip": "무릎을 발끝 밖으로 미는 큐 하나만 의식해보세요.",
                    "tone_metadata": {"warmth": 0.7, "detail": 0.6},
                    "addresses_scrutinizer": None,
                },
                "scrutinizer": {
                    "agent": "scrutinizer", "round": 1,
                    "primary_risk": {
                        "name": "knee_valgus_left", "severity": "medium-high",
                        "mechanism": "부하 하 무릎 외반은 ACL·내측 인대에 전단 응력을 가함.",
                        "evidence_in_data": "rep 1·3에서 valgus_mild, safety_flag medium.",
                        "threshold_breach": "반복적 외반 + 빠른 이심성 동반.",
                    },
                    "secondary_concerns": [
                        {"name": "fast_eccentric", "severity": "low", "note": "하강 1.2s — 통제력 저하."},
                    ],
                    "required_action": "증량 전에 무릎 트래킹부터 교정. '괜찮은' 수준이 아님.",
                    "tone_metadata": {"harshness": 0.7, "detail": 0.8},
                    "addresses_encourager": None,
                },
                "verdict": {"converged": False, "shared_issue": "knee_valgus_left",
                            "reason": "깊이엔 합의, 무릎 처리 강도에서 이견."},
            },
            {
                "round": 2,
                "round_latency_seconds": 22.0,
                "encourager": {
                    "agent": "encourager", "round": 2,
                    "praise": "무릎은 분명 짚고 가야죠 — 동의해요.",
                    "concern_one": "다만 겁주기보다 큐 하나로 잡는 게 동기 유지에 나아요.",
                    "actionable_tip": "발끝 밖으로 무릎 밀기 + 하강을 2초로.",
                    "tone_metadata": {"warmth": 0.66, "detail": 0.62},
                    "addresses_scrutinizer": "위험은 인정하되 코칭 톤은 유지하자.",
                },
                "scrutinizer": {
                    "agent": "scrutinizer", "round": 2,
                    "primary_risk": {
                        "name": "knee_valgus_left", "severity": "medium",
                        "mechanism": "큐로 교정 안 되면 증량 중단이 원칙.",
                        "evidence_in_data": "rep 5에서 neutral로 개선 — 교정 가능성 있음.",
                        "threshold_breach": "단, 부하·피로 시 재발 위험.",
                    },
                    "secondary_concerns": [],
                    "required_action": "큐로 즉시 교정되는지 확인 후에만 증량 허용.",
                    "tone_metadata": {"harshness": 0.62, "detail": 0.78},
                    "addresses_encourager": "톤은 양보, 증량 게이트는 유지.",
                },
                "verdict": {"converged": True, "shared_issue": "knee_valgus_left",
                            "reason": "무릎 우선 교정 + 큐 기반 접근에 합의."},
            },
        ],
        "consensus": {
            "agent": "mediator",
            "consensus": "좋은 스쿼트, 우선순위 수정 하나. 깊이는 합격이니 이제 무릎을 잡읍시다 — 발끝 밖으로 밀고 하강을 2초로. 증량은 무릎 트래킹을 잡은 뒤에.",
            "priority_actions": [
                {"order": 1, "action": "무릎을 발끝 라인 밖으로 트래킹", "rationale": "왼쪽 무릎 외반 = ACL 스트레스 감소."},
                {"order": 2, "action": "이심성(하강) 1.2s → 2.0s", "rationale": "통제력 확보로 외반 재발 방지."},
                {"order": 3, "action": "다음 세트 측면 재촬영", "rationale": "교정 여부를 데이터로 확인."},
            ],
            "past_debate_references": [
                {"debate_id": "demo-squat-feb", "date": "2026-02-14", "outcome": "knee_valgus 주의 기록"},
            ],
            "disclaimer": "이 분석은 정보 제공용입니다. 의학 조언이 아닙니다. 운동 중 통증·부상·지속적 불편이 있으면 운동을 중단하고 자격 있는 의료·피트니스 전문가와 상담하세요.",
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
