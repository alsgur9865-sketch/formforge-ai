# 파일 위치: tests/test_feedback_loop.py
"""
Self-Improvement Loop 단위 테스트 — Day 13 Task 13.1/13.2 (Gemini/Firestore 없이 빠름).

검증 범위 (결정론 코어 — Task 13.2 acceptance):
  - too_harsh 1번 → scrutinizer.harshness 0.5 → 0.35  (정확히 -0.15)
  - too_soft  1번 → scrutinizer.harshness 0.5 → 0.60  (양방향 +0.10)
  - perfect        → 변화 없음 (anchor)
  - too_warm/too_cold → encourager.warmth 양방향
  - clamp [0,1] 경계
  - detail 은 LLM judge 추천(judge_result)에서만 변경, 없으면 보존
  - sibling 파라미터(detail) 보존
  - extract_debate_texts: Firestore snapshot → judge 입력 텍스트

실제 LLM judge e2e 는: python evals/llm_judge.py
전체 피드백 루프 e2e 는: python tests/test_feedback_loop.py --e2e
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.feedback_handler import (
    apply_persona_adjustment,
    extract_debate_texts,
    _clamp,
)
from evals.llm_judge import (
    JudgeResult,
    PersonaAdjustment,
    EncouragerDelta,
    ScrutinizerDelta,
)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _base_state() -> dict:
    return {
        "encourager": {"warmth": 0.5, "detail": 0.5},
        "scrutinizer": {"harshness": 0.5, "detail": 0.5},
    }


def _judge_with_detail(enc_detail_delta: float, scr_detail_delta: float) -> JudgeResult:
    return JudgeResult(
        debate_quality_score=0.8,
        persona_adjustment_recommendation=PersonaAdjustment(
            encourager=EncouragerDelta(warmth_delta=0.0, detail_delta=enc_detail_delta),
            scrutinizer=ScrutinizerDelta(harshness_delta=0.0, detail_delta=scr_detail_delta),
        ),
        reasoning="테스트용 judge 결과.",
    )


# ---------------------------------------------------------------------------
# acceptance: 핵심 파라미터 결정론 조정
# ---------------------------------------------------------------------------

def test_too_harsh_lowers_harshness():
    # acceptance 1: too_harsh → 0.5 → 0.35
    new = apply_persona_adjustment(_base_state(), "perfect", "too_harsh")
    assert new["scrutinizer"]["harshness"] == 0.35, new
    print("  ✅ too_harsh: harshness 0.5 → 0.35 (-0.15)")


def test_too_soft_raises_harshness():
    # acceptance 2 (양방향): too_soft → 0.5 → 0.60
    new = apply_persona_adjustment(_base_state(), "perfect", "too_soft")
    assert new["scrutinizer"]["harshness"] == 0.60, new
    print("  ✅ too_soft: harshness 0.5 → 0.60 (+0.10, 양방향)")


def test_perfect_is_anchor():
    # acceptance 3: perfect → 변화 없음 (judge_result=None → detail 도 불변)
    new = apply_persona_adjustment(_base_state(), "perfect", "perfect")
    assert new["scrutinizer"]["harshness"] == 0.5, new
    assert new["encourager"]["warmth"] == 0.5, new
    assert new["scrutinizer"]["detail"] == 0.5, new
    assert new["encourager"]["detail"] == 0.5, new
    print("  ✅ perfect: 모든 파라미터 변화 없음 (anchor)")


def test_too_warm_lowers_warmth():
    new = apply_persona_adjustment(_base_state(), "too_warm", "perfect")
    assert new["encourager"]["warmth"] == 0.4, new
    print("  ✅ too_warm: warmth 0.5 → 0.4 (-0.10)")


def test_too_cold_raises_warmth():
    new = apply_persona_adjustment(_base_state(), "too_cold", "perfect")
    assert new["encourager"]["warmth"] == 0.6, new
    print("  ✅ too_cold: warmth 0.5 → 0.6 (+0.10, 양방향)")


# ---------------------------------------------------------------------------
# clamp 경계
# ---------------------------------------------------------------------------

def test_clamp_lower_bound():
    state = {
        "encourager": {"warmth": 0.5, "detail": 0.5},
        "scrutinizer": {"harshness": 0.05, "detail": 0.5},
    }
    new = apply_persona_adjustment(state, "perfect", "too_harsh")
    assert new["scrutinizer"]["harshness"] == 0.0, new  # 0.05-0.15=-0.1 → 0.0
    print("  ✅ clamp 하한: harshness 0.05 + (-0.15) → 0.0")


def test_clamp_upper_bound():
    state = {
        "encourager": {"warmth": 0.95, "detail": 0.5},
        "scrutinizer": {"harshness": 0.5, "detail": 0.5},
    }
    new = apply_persona_adjustment(state, "too_cold", "perfect")
    assert new["encourager"]["warmth"] == 1.0, new  # 0.95+0.10=1.05 → 1.0
    print("  ✅ clamp 상한: warmth 0.95 + 0.10 → 1.0")


def test_unknown_rating_is_noop():
    # 잘못된 rating 문자열 → delta 0 (방어적)
    new = apply_persona_adjustment(_base_state(), "garbage", "nonsense")
    assert new["encourager"]["warmth"] == 0.5, new
    assert new["scrutinizer"]["harshness"] == 0.5, new
    print("  ✅ 알 수 없는 rating: 변화 없음 (방어)")


# ---------------------------------------------------------------------------
# detail: LLM judge 추천 경로
# ---------------------------------------------------------------------------

def test_detail_from_judge_applied():
    judge = _judge_with_detail(enc_detail_delta=0.10, scr_detail_delta=-0.10)
    new = apply_persona_adjustment(_base_state(), "perfect", "perfect", judge_result=judge)
    assert new["encourager"]["detail"] == 0.6, new
    assert new["scrutinizer"]["detail"] == 0.4, new
    # 핵심 파라미터는 perfect 라 불변
    assert new["encourager"]["warmth"] == 0.5, new
    assert new["scrutinizer"]["harshness"] == 0.5, new
    print("  ✅ detail: judge 추천 적용 (enc +0.10, scr -0.10) + 핵심 파라미터 불변")


def test_detail_preserved_without_judge():
    new = apply_persona_adjustment(_base_state(), "too_warm", "too_harsh", judge_result=None)
    # judge 없으면 detail 은 원래 값 그대로
    assert new["encourager"]["detail"] == 0.5, new
    assert new["scrutinizer"]["detail"] == 0.5, new
    print("  ✅ detail: judge 없으면 보존")


def test_sibling_preserved_on_warmth_change():
    # warmth 만 조정해도 같은 맵의 detail 보존 (Firestore dot-notation 평탄화 전제와 일치)
    state = {
        "encourager": {"warmth": 0.5, "detail": 0.77},
        "scrutinizer": {"harshness": 0.5, "detail": 0.33},
    }
    new = apply_persona_adjustment(state, "too_warm", "perfect")
    assert new["encourager"]["detail"] == 0.77, new
    assert new["scrutinizer"]["detail"] == 0.33, new
    print("  ✅ sibling: warmth 변경 시 detail 보존")


# ---------------------------------------------------------------------------
# 토론 텍스트 추출
# ---------------------------------------------------------------------------

def test_extract_debate_texts_full():
    snapshot = {
        "rounds": [
            {"round": 1, "encourager": {"praise": "first"}, "scrutinizer": {"x": 1}},
            {"round": 2, "encourager": {"praise": "마지막 라운드"},
             "scrutinizer": {"primary_risk": {"name": "전방 기울기"}}},
        ],
        "consensus": {"agent": "mediator", "consensus": "중량을 줄이세요."},
    }
    enc, scr, med = extract_debate_texts(snapshot)
    assert "마지막 라운드" in enc, enc          # 마지막 라운드 사용
    assert "전방 기울기" in scr, scr
    assert med == "중량을 줄이세요.", med
    print("  ✅ extract_debate_texts: 마지막 라운드 + consensus 본문")


def test_extract_debate_texts_empty():
    assert extract_debate_texts(None) == ("", "", "")
    assert extract_debate_texts({}) == ("", "", "")
    print("  ✅ extract_debate_texts: 빈 snapshot → 빈 문자열")


def test_clamp_rounds():
    assert _clamp(0.5499999999) == 0.55
    assert _clamp(-0.3) == 0.0
    assert _clamp(1.4) == 1.0
    print("  ✅ _clamp: 부동소수점 4자리 정리 + 경계")


# ---------------------------------------------------------------------------
# 러너
# ---------------------------------------------------------------------------

_TESTS = [
    test_too_harsh_lowers_harshness,
    test_too_soft_raises_harshness,
    test_perfect_is_anchor,
    test_too_warm_lowers_warmth,
    test_too_cold_raises_warmth,
    test_clamp_lower_bound,
    test_clamp_upper_bound,
    test_unknown_rating_is_noop,
    test_detail_from_judge_applied,
    test_detail_preserved_without_judge,
    test_sibling_preserved_on_warmth_change,
    test_extract_debate_texts_full,
    test_extract_debate_texts_empty,
    test_clamp_rounds,
]


def _run_unit() -> int:
    print("=== Self-Improvement Loop 결정론 단위 테스트 ===")
    failed = 0
    for t in _TESTS:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"  ❌ {t.__name__}: {e}")
    print(f"\n{'✅ 전체 통과' if failed == 0 else f'❌ {failed}건 실패'} "
          f"({len(_TESTS) - failed}/{len(_TESTS)})")
    return 0 if failed == 0 else 1


def _run_e2e() -> int:
    """실제 피드백 루프 e2e — Gemini(judge) + Firestore 필요. 기존 토론 1건 사용."""
    import asyncio
    from dotenv import load_dotenv
    from evals.feedback_handler import process_feedback
    from storage import firestore_client

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    # 가장 최근 토론 1건 찾기 (consensus 가 있는 e2e_* debate).
    # exercise_type 지정 → 기존 복합 인덱스(exercise_type+user_id+created_at) 사용
    # (None 이면 user_id+created_at 인덱스가 별도로 필요해 FailedPrecondition).
    user_id = "user_001"
    recent = firestore_client.get_recent_debates(user_id, exercise_type="squat", limit=5)
    target = next((d for d in recent if d.get("consensus")), None)
    if not target:
        print("⚠️  consensus 있는 최근 squat 토론이 없습니다. 먼저 orchestrator --e2e/--full 실행 필요.")
        return 1
    debate_id = target["debate_id"]
    print(f"대상 debate_id={debate_id}")

    before = firestore_client.get_user_persona_state(user_id)
    print(f"BEFORE harshness={before.get('scrutinizer', {}).get('harshness')}")

    result = asyncio.run(
        process_feedback(
            debate_id=debate_id,
            user_id=user_id,
            encourager_rating="perfect",
            scrutinizer_rating="too_harsh",
            mediator_rating=4,
            free_text="",
            persist=True,
        )
    )
    jr = result["judge_result"]
    old_h = result["old_persona_state"].get("scrutinizer", {}).get("harshness", 0.5)
    new_h = result["new_persona_state"]["scrutinizer"]["harshness"]
    print(f"\n🧑‍⚖️ debate_quality_score={jr.debate_quality_score:.2f} "
          f"({jr.reasoning})")
    print(f"AFTER harshness={old_h} → {new_h}")

    after = firestore_client.get_user_persona_state(user_id)
    checks = {
        "judge quality 0~1": 0.0 <= jr.debate_quality_score <= 1.0,
        "too_harsh 로 harshness 하락": new_h < old_h,
        "정확히 -0.15": abs((old_h - new_h) - 0.15) < 1e-9,
        "Firestore 반영": abs(after.get("scrutinizer", {}).get("harshness", -1) - new_h) < 1e-9,
        "judge_latency 기록": result["judge_latency_seconds"] > 0,
    }
    print("\n--- e2e acceptance ---")
    for name, ok in checks.items():
        print(f"  {'✅' if ok else '❌'} {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    if "--e2e" in sys.argv:
        raise SystemExit(_run_e2e())
    raise SystemExit(_run_unit())
