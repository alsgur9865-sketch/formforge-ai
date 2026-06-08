# 파일 위치: evals/feedback_handler.py
"""
사용자 피드백 → 페르소나 진화 핸들러 — Day 13 Task 13.1 (Self-Improvement Loop ⭐⭐).

흐름 (ARCHITECTURE.md §6.2):
  사용자 피드백 POST
    → 1. Firestore feedback 저장
    → 2. LLM-as-a-Judge 호출 (토론 품질 점수 + 조정 추천)
    → 3. 페르소나 파라미터 조정 (하이브리드)
    → 4. Firestore persona_state 업데이트
    → 5. Phoenix 에 eval 결과 + Firestore evals 저장

하이브리드 조정 (세션 11 grill-me 확정):
  - **enum 피드백 → 핵심 파라미터 delta 는 결정론적 룩업 테이블**로 확정.
    LLM 변동으로 acceptance 수치(too_harsh → 정확히 -0.15)가 깨지지 않게.
      Encourager warmth: too_warm=-0.10 / too_cold=+0.10 / perfect=0
      Scrutinizer harshness: too_harsh=-0.15 / too_soft=+0.10 / perfect=0
  - **detail 파라미터는 LLM judge 추천**(자유 텍스트 기반 정성 판단)을 사용.
  - learning_rate 미적용 — delta 가 곧 최종 적용량 (acceptance 가 ground truth).
  - 모든 값 [0.0, 1.0] clamp.

페르소나 spec (ARCHITECTURE.md §6.1) — "perfect" 는 anchor (변화 없음).
양방향 학습으로 한쪽 끝에 박히는 문제 회피.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from evals.llm_judge import JudgeResult, judge_debate
from storage import firestore_client


# ---------------------------------------------------------------------------
# Phoenix register 보장 (P1) — llm_judge 의 eval span 을 Phoenix Cloud 로 송출.
# orchestrator 와 달리 feedback 은 UI 에서 독립 호출되는 경로라 자체 보장한다.
# GoogleADKInstrumentor 불필요 (ADK Runner 미사용, llm_judge 는 명시적 span).
# ---------------------------------------------------------------------------

_PHOENIX_REGISTERED = False


def _ensure_phoenix_registered() -> bool:
    """register 1회(idempotent). PHOENIX_API_KEY 없거나 실패 시 fail-soft(False)."""
    global _PHOENIX_REGISTERED
    if _PHOENIX_REGISTERED:
        return True
    api_key = os.getenv("PHOENIX_API_KEY")
    if not api_key:
        return False
    try:
        from phoenix.otel import register

        endpoint = (
            os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "https://app.phoenix.arize.com")
            .rstrip("/")
            + "/v1/traces"
        )
        register(
            project_name=os.getenv("PHOENIX_PROJECT_NAME", "formforge-prod"),
            endpoint=endpoint,
            headers={"authorization": f"Bearer {api_key}"},
        )
        _PHOENIX_REGISTERED = True
        return True
    except Exception as exc:  # noqa: BLE001 — 관측성은 fail-soft
        print(f"⚠️  Phoenix register 실패 (eval span 로컬에만): {type(exc).__name__}: {exc}")
        return False


# ---------------------------------------------------------------------------
# 결정론적 enum → delta 룩업 테이블 (ARCHITECTURE.md §6.3, acceptance ground truth)
# ---------------------------------------------------------------------------

# Encourager 피드백 → warmth 파라미터 변화량
_WARMTH_DELTA: dict[str, float] = {
    "too_warm": -0.10,
    "too_cold": +0.10,
    "perfect": 0.0,
}

# Scrutinizer 피드백 → harshness 파라미터 변화량 (비대칭: 가혹함은 더 크게 완화)
_HARSHNESS_DELTA: dict[str, float] = {
    "too_harsh": -0.15,
    "too_soft": +0.10,
    "perfect": 0.0,
}


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """[lo, hi] 범위로 자르고 부동소수점 오차를 4자리로 정리."""
    return round(max(lo, min(hi, v)), 4)


def _ensure_user_doc(user_id: str) -> None:
    """
    users/{user_id} 문서 보장 — update_user_persona_state 는 문서 존재를 전제한다.

    정상 플로우(UI 가 토론 시작 시 사용자 등록)에선 이미 있어 no-op. 등록 없이
    바로 피드백을 주는 엣지(orchestrator 가 debate 만 생성하는 현재 파이프라인)를
    방어해, P3(피드백 → 페르소나 영구 반영)가 조용히 NotFound 로 실패하지 않게 한다.
    create_user 가 persona_state 를 기본값(0.5)으로 세팅하므로, 이어지는
    update_user_persona_state 가 그 위에 조정값을 덮어쓴다.
    """
    if firestore_client.get_user(user_id) is None:
        firestore_client.create_user(
            user_id,
            {"experience_level": "intermediate", "injury_history": []},
        )


# ---------------------------------------------------------------------------
# 페르소나 조정 (하이브리드 — Gemini 불필요한 결정론 코어)
# ---------------------------------------------------------------------------

def apply_persona_adjustment(
    current_state: dict[str, Any],
    encourager_rating: str,
    scrutinizer_rating: str,
    judge_result: JudgeResult | None = None,
) -> dict[str, Any]:
    """
    현재 persona_state + 피드백 → 새 persona_state.

    결정론적(테스트 가능):
      - warmth (encourager): _WARMTH_DELTA 룩업
      - harshness (scrutinizer): _HARSHNESS_DELTA 룩업
    LLM 추천(judge_result 있을 때만):
      - detail (encourager/scrutinizer): judge 의 detail_delta

    judge_result=None 이면 detail 은 건드리지 않는다 → enum 만으로 결정론 검증 가능.

    Args:
        current_state: { encourager: {warmth, detail}, scrutinizer: {harshness, detail}, ... }
        encourager_rating: "too_warm" | "perfect" | "too_cold"
        scrutinizer_rating: "too_harsh" | "perfect" | "too_soft"
        judge_result: LLM-as-a-Judge 결과 (detail 추천 출처). None 이면 detail 미변경.

    Returns:
        새 persona_state ({encourager, scrutinizer} 만 포함 — 부분 업데이트용).
    """
    enc = dict(current_state.get("encourager") or {})
    scr = dict(current_state.get("scrutinizer") or {})

    # --- 핵심 파라미터: 결정론적 룩업 (알 수 없는 rating 은 0 → 변화 없음) ---
    warmth = enc.get("warmth", 0.5)
    enc["warmth"] = _clamp(warmth + _WARMTH_DELTA.get(encourager_rating, 0.0))

    harshness = scr.get("harshness", 0.5)
    scr["harshness"] = _clamp(harshness + _HARSHNESS_DELTA.get(scrutinizer_rating, 0.0))

    # --- detail: LLM judge 추천 (자유 텍스트 기반). judge 없으면 그대로 보존 ---
    if judge_result is not None:
        rec = judge_result.persona_adjustment_recommendation
        enc_detail = enc.get("detail", 0.5)
        scr_detail = scr.get("detail", 0.5)
        enc["detail"] = _clamp(enc_detail + rec.encourager.detail_delta)
        scr["detail"] = _clamp(scr_detail + rec.scrutinizer.detail_delta)

    return {"encourager": enc, "scrutinizer": scr}


# ---------------------------------------------------------------------------
# 토론 텍스트 추출 (Phoenix fetch 불필요 — Firestore 에 이미 저장됨)
# ---------------------------------------------------------------------------

def extract_debate_texts(snapshot: dict[str, Any] | None) -> tuple[str, str, str]:
    """
    debate snapshot → (encourager_text, scrutinizer_text, mediator_text).

    마지막 라운드의 두 코치 응답 + consensus 를 judge 입력용 텍스트로.
    snapshot 이 비거나 키가 없으면 빈 문자열 (judge 가 fail-soft 처리).
    """
    snapshot = snapshot or {}
    rounds = snapshot.get("rounds") or []
    last = rounds[-1] if rounds else {}

    enc = last.get("encourager")
    scr = last.get("scrutinizer")
    enc_text = json.dumps(enc, ensure_ascii=False) if enc else ""
    scr_text = json.dumps(scr, ensure_ascii=False) if scr else ""

    consensus = snapshot.get("consensus") or {}
    # consensus 는 MediatorOutput.as_dict() — "consensus" 키에 합의 본문.
    med_text = consensus.get("consensus") or (
        json.dumps(consensus, ensure_ascii=False) if consensus else ""
    )
    return enc_text, scr_text, med_text


# ---------------------------------------------------------------------------
# 메인: 피드백 처리 전체 루프
# ---------------------------------------------------------------------------

async def process_feedback(
    debate_id: str,
    user_id: str,
    encourager_rating: str,
    scrutinizer_rating: str,
    mediator_rating: int,
    free_text: str = "",
    *,
    persist: bool = True,
) -> dict[str, Any]:
    """
    피드백 1건 처리 — ARCHITECTURE.md §6.2 전체 흐름.

    Args:
        debate_id: 평가 대상 토론.
        user_id: 페르소나가 진화할 사용자.
        encourager_rating: "too_warm" | "perfect" | "too_cold"
        scrutinizer_rating: "too_harsh" | "perfect" | "too_soft"
        mediator_rating: 1~5
        free_text: 선택. detail 정성 조정 신호로 LLM judge 가 사용.
        persist: True 면 Firestore 저장(feedback/persona/evals). False 면 dry-run.

    Returns:
        {
          "judge_result": JudgeResult,
          "old_persona_state": dict,
          "new_persona_state": dict,
          "judge_latency_seconds": float,
          "persisted": bool,
        }
    """
    # P1: llm_judge eval span 이 Phoenix Cloud 로 가도록 register 보장 (fail-soft)
    _ensure_phoenix_registered()

    # 1) 현재 persona_state (문서 없으면 기본값)
    current_state = firestore_client.get_user_persona_state(user_id)

    # 2) 토론 텍스트 추출 (Firestore snapshot)
    snapshot = firestore_client.get_debate_snapshot(debate_id)
    enc_text, scr_text, med_text = extract_debate_texts(snapshot)

    feedback = {
        "encourager_rating": encourager_rating,
        "scrutinizer_rating": scrutinizer_rating,
        "mediator_rating": mediator_rating,
        "free_text": free_text,
    }

    # 3) LLM-as-a-Judge (품질 점수 + detail 추천)
    #    persona_state 에서 핵심 파라미터만 전달 — get_user_persona_state 는
    #    last_updated_at(Firestore Timestamp) / total_feedback_count 같은 메타
    #    필드를 포함하는데, 그대로 넘기면 judge 내부 json.dumps 가
    #    "DatetimeWithNanoseconds is not JSON serializable" 로 터진다 (리뷰 #2).
    persona_for_judge = {
        "encourager": current_state.get("encourager", {}),
        "scrutinizer": current_state.get("scrutinizer", {}),
    }
    judge_result, judge_latency = await judge_debate(
        encourager_text=enc_text,
        scrutinizer_text=scr_text,
        mediator_text=med_text,
        user_feedback=feedback,
        persona_state=persona_for_judge,
    )

    # 4) 페르소나 조정 (하이브리드)
    new_state = apply_persona_adjustment(
        current_state=current_state,
        encourager_rating=encourager_rating,
        scrutinizer_rating=scrutinizer_rating,
        judge_result=judge_result,
    )

    # 5) Firestore 저장 (fail-soft). P3(페르소나 진화)가 self-improvement loop 의
    #    핵심이므로, feedback/eval 기록 실패가 persona 업데이트를 막지 않도록 블록을
    #    분리한다 (리뷰 #4). persisted 는 persona 업데이트 성공 기준.
    persisted = False
    if persist:
        ts = int(time.time() * 1000)

        # 5a) 페르소나 진화 (P3 핵심) — 먼저, 독립 블록.
        #     update 는 문서 존재 전제 → 없으면 먼저 생성 (미등록 사용자 방어).
        try:
            _ensure_user_doc(user_id)
            firestore_client.update_user_persona_state(user_id, new_state)
            persisted = True
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  persona_state 업데이트 실패 (P3 직결): {type(e).__name__}: {e}")

        # 5b) 피드백/eval 기록 (보조) — 실패해도 페르소나 진화엔 영향 없음.
        try:
            firestore_client.save_feedback(
                feedback_id=f"fb_{debate_id}_{ts}",
                debate_id=debate_id,
                user_id=user_id,
                encourager_rating=encourager_rating,
                scrutinizer_rating=scrutinizer_rating,
                mediator_rating=mediator_rating,
                free_text=free_text,
            )
            firestore_client.save_eval_result(
                eval_id=f"eval_{debate_id}_{ts}",
                debate_id=debate_id,
                quality_score=judge_result.debate_quality_score,
                persona_adjustment=judge_result.persona_adjustment_recommendation.model_dump(),
            )
        except Exception as e:  # noqa: BLE001
            print(f"⚠️  feedback/eval 기록 실패 (보조, fail-soft): {type(e).__name__}: {e}")

    return {
        "judge_result": judge_result,
        "old_persona_state": current_state,
        "new_persona_state": new_state,
        "judge_latency_seconds": judge_latency,
        "persisted": persisted,
    }


def process_feedback_sync(
    debate_id: str,
    user_id: str,
    encourager_rating: str,
    scrutinizer_rating: str,
    mediator_rating: int,
    free_text: str = "",
    *,
    persist: bool = True,
) -> dict[str, Any]:
    """Streamlit 등 sync 환경 편의 wrapper."""
    import asyncio
    return asyncio.run(
        process_feedback(
            debate_id, user_id, encourager_rating, scrutinizer_rating,
            mediator_rating, free_text, persist=persist,
        )
    )


# ---------------------------------------------------------------------------
# CLI (결정론 코어 스모크 — Gemini 불필요)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # 결정론 코어(apply_persona_adjustment)만 빠르게 검증 — Gemini/Firestore 불필요.
    base = {
        "encourager": {"warmth": 0.5, "detail": 0.5},
        "scrutinizer": {"harshness": 0.5, "detail": 0.5},
    }

    cases = [
        ("too_harsh", "perfect", "perfect", 0.5, 0.35),   # acceptance 1
        ("too_soft", "perfect", "perfect", 0.5, 0.60),    # acceptance 2 (양방향)
        ("perfect", "perfect", "perfect", 0.5, 0.50),     # acceptance 3 (anchor)
    ]
    print("=== apply_persona_adjustment 결정론 검증 (judge_result=None) ===")
    all_ok = True
    for scr_rating, enc_rating, _label, before, expect in cases:
        new = apply_persona_adjustment(base, enc_rating, scr_rating, judge_result=None)
        got = new["scrutinizer"]["harshness"]
        ok = abs(got - expect) < 1e-9
        all_ok &= ok
        print(f"  {'✅' if ok else '❌'} scrutinizer={scr_rating}: "
              f"harshness {before} → {got} (기대 {expect})")

    # clamp 경계
    low = {"scrutinizer": {"harshness": 0.05, "detail": 0.5},
           "encourager": {"warmth": 0.5, "detail": 0.5}}
    clamped = apply_persona_adjustment(low, "perfect", "too_harsh", judge_result=None)
    ok = clamped["scrutinizer"]["harshness"] == 0.0
    all_ok &= ok
    print(f"  {'✅' if ok else '❌'} clamp: harshness 0.05 + (-0.15) → "
          f"{clamped['scrutinizer']['harshness']} (기대 0.0)")

    raise SystemExit(0 if all_ok else 1)
