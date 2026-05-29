# 파일 위치: tests/test_mediator.py
"""
Mediator 순수 함수 단위 테스트 (Gemini 호출 없음 — 빠르고 CI 가능).

핵심: P5 절대원칙(의료 면책) 보장 로직 _enforce_disclaimer 회귀 가드.
실제 LLM 합의 품질은 `python agents/mediator.py --selftest` 로 검증.
"""

from __future__ import annotations

import sys
from pathlib import Path

# 프로젝트 루트 import 경로
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from agents.mediator import (  # noqa: E402
    MEDICAL_DISCLAIMER_KO,
    MediatorOutput,
    PriorityAction,
    _enforce_disclaimer,
    build_mediator_input_payload,
)


def _make_output(disclaimer: str) -> MediatorOutput:
    return MediatorOutput(
        consensus="테스트 합의안",
        priority_actions=[PriorityAction(order=1, action="a", rationale="r")],
        disclaimer=disclaimer,
        round_count_used=1,
    )


# --- P5: _enforce_disclaimer 회귀 가드 ---------------------------------------

def test_enforce_disclaimer_empty_is_replaced():
    """빈 disclaimer → 표준 문구로 강제 교체."""
    out = _enforce_disclaimer(_make_output(""))
    assert out.disclaimer == MEDICAL_DISCLAIMER_KO


def test_enforce_disclaimer_whitespace_is_replaced():
    """공백만 있는 disclaimer → 표준 문구."""
    out = _enforce_disclaimer(_make_output("   "))
    assert out.disclaimer == MEDICAL_DISCLAIMER_KO


def test_enforce_disclaimer_missing_keyword_is_replaced():
    """'의학 조언' 키워드 없는 엉뚱한 문구 → 표준 문구로 교체 (LLM 변형 방어)."""
    out = _enforce_disclaimer(_make_output("화이팅! 다음에도 열심히 해요."))
    assert out.disclaimer == MEDICAL_DISCLAIMER_KO


def test_enforce_disclaimer_valid_is_kept():
    """핵심 키워드를 가진 정상 문구 → 그대로 유지."""
    valid = "이 분석은 정보 제공용이며 의학 조언이 아닙니다. 전문가와 상담하세요."
    out = _enforce_disclaimer(_make_output(valid))
    assert out.disclaimer == valid


def test_default_disclaimer_is_p5_text():
    """disclaimer 미지정 시 기본값이 P5 표준 문구."""
    out = MediatorOutput(
        consensus="c",
        priority_actions=[PriorityAction(order=1, action="a", rationale="r")],
        round_count_used=2,
    )
    assert out.disclaimer == MEDICAL_DISCLAIMER_KO
    assert "의학 조언" in out.disclaimer


# --- 입력 페이로드 구조 -------------------------------------------------------

def test_build_payload_structure():
    """build_mediator_input_payload 가 기대 키 + round_count 를 정확히 만든다."""
    debate_result = {
        "rounds": [{"round": 1, "encourager": {}, "scrutinizer": {}}],
        "converged": True,
        "shared_issue": "knee valgus",
        "forced_stop_reason": None,
    }
    payload = build_mediator_input_payload(
        debate_result,
        pose_data={"exercise_type": "squat"},
        user_context={"user_id": "u1", "injury_history": ["lower_back"]},
    )
    assert payload["round_count"] == 1
    assert payload["converged"] is True
    assert payload["shared_issue"] == "knee valgus"
    assert payload["debate_summary"]["rounds"] == debate_result["rounds"]
    assert payload["pose_data"]["exercise_type"] == "squat"
    assert payload["user_context"]["user_id"] == "u1"


def test_build_payload_handles_empty_rounds():
    """rounds 가 없거나 None 이어도 round_count=0 으로 안전 처리."""
    payload = build_mediator_input_payload(
        {"rounds": None}, pose_data={}, user_context={}
    )
    assert payload["round_count"] == 0


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
