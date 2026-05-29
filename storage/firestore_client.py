# 파일 위치: storage/firestore_client.py
"""
Firestore CRUD 클라이언트.

ARCHITECTURE.md §3.1 컬렉션 구조 구현:
  - users/{user_id}  → profile + persona_state
  - debates/{debate_id}
  - feedback/{feedback_id}
  - evals/{eval_id}

Streamlit 폴링 패턴(§3.2)도 여기서 제공.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from google.cloud import firestore

load_dotenv()

# ---------------------------------------------------------------------------
# 싱글톤 클라이언트 (모듈 import 시 1회 초기화)
# ---------------------------------------------------------------------------

_db: firestore.Client | None = None


def init_firestore() -> firestore.Client:
    """Firestore 클라이언트를 초기화하고 반환. 이미 초기화되어 있으면 재사용."""
    global _db
    if _db is not None:
        return _db

    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if credentials_path and os.path.exists(credentials_path):
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_file(
            credentials_path
        )
        _db = firestore.Client(project=project_id, credentials=credentials)
    else:
        # Cloud Run 등 ADC(Application Default Credentials) 환경
        _db = firestore.Client(project=project_id)

    return _db


def _db_client() -> firestore.Client:
    """내부 헬퍼 — init이 안 됐으면 자동 init."""
    return init_firestore()


# ---------------------------------------------------------------------------
# users 컬렉션
# ---------------------------------------------------------------------------

_DEFAULT_PERSONA_STATE = {
    "encourager": {"warmth": 0.5, "detail": 0.5},
    "scrutinizer": {"harshness": 0.5, "detail": 0.5},
    "last_updated_at": None,
    "total_feedback_count": 0,
}


def create_user(user_id: str, profile: dict[str, Any]) -> None:
    """
    users/{user_id} 문서 생성.

    profile 예시:
        {
            "name": "민혁",
            "email": "user@example.com",
            "experience_level": "intermediate",
            "injury_history": ["lower_back_strain_2025"],
        }
    """
    db = _db_client()
    now = datetime.now(timezone.utc)
    doc = {
        "profile": {**profile, "created_at": now},
        "persona_state": {**_DEFAULT_PERSONA_STATE, "last_updated_at": now},
    }
    db.collection("users").document(user_id).set(doc)


def get_user(user_id: str) -> dict[str, Any] | None:
    """users/{user_id} 전체 문서 반환. 없으면 None."""
    db = _db_client()
    snap = db.collection("users").document(user_id).get()
    return snap.to_dict() if snap.exists else None


def get_user_persona_state(user_id: str) -> dict[str, Any]:
    """
    persona_state 반환. 문서가 없으면 기본값 반환.

    반환 예:
        {
            "encourager": {"warmth": 0.5, "detail": 0.5},
            "scrutinizer": {"harshness": 0.5, "detail": 0.5},
            "last_updated_at": ...,
            "total_feedback_count": 0,
        }
    """
    doc = get_user(user_id)
    if doc and "persona_state" in doc:
        return doc["persona_state"]
    return {**_DEFAULT_PERSONA_STATE}


def update_user_persona_state(
    user_id: str,
    new_state: dict[str, Any],
    increment_feedback_count: bool = True,
) -> None:
    """
    persona_state 부분 업데이트.

    중첩 dict는 dot-notation으로 평탄화되어 sibling 맵 필드를 보존합니다.
    예) {"encourager": {"warmth": 0.7}} 를 넘기면
        → "persona_state.encourager.warmth" = 0.7 만 수정
        → encourager.detail 등 다른 키는 그대로 유지

    total_feedback_count 처리:
      - 기본: Firestore Increment(1)로 자동 +1
      - new_state에 total_feedback_count 명시되면 그 값을 그대로 사용
      - increment_feedback_count=False면 auto-increment 비활성

    선행 조건: users/{user_id} 문서가 존재해야 함 (create_user 이후 호출).
    """
    db = _db_client()
    updates: dict[str, Any] = {}
    explicit_feedback_count = "total_feedback_count" in new_state

    def _flatten(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                _flatten(f"{prefix}.{k}", v)
        else:
            updates[prefix] = value

    for key, value in new_state.items():
        _flatten(f"persona_state.{key}", value)

    updates["persona_state.last_updated_at"] = datetime.now(timezone.utc)

    if increment_feedback_count and not explicit_feedback_count:
        updates["persona_state.total_feedback_count"] = firestore.Increment(1)

    db.collection("users").document(user_id).update(updates)


def get_user_injury_history(user_id: str) -> list[str]:
    """profile.injury_history 반환. 없으면 빈 리스트."""
    doc = get_user(user_id)
    if doc:
        return doc.get("profile", {}).get("injury_history", [])
    return []


# ---------------------------------------------------------------------------
# debates 컬렉션
# ---------------------------------------------------------------------------

def create_debate(debate_id: str, user_id: str, video_uri: str, exercise_type: str) -> None:
    """debates/{debate_id} 초기 문서 생성."""
    db = _db_client()
    now = datetime.now(timezone.utc)
    db.collection("debates").document(debate_id).set({
        "user_id": user_id,
        "video_uri": video_uri,
        "exercise_type": exercise_type,
        "pose_data": None,
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "rounds": [],
        "consensus": None,
        "trace_ids": {},
    })


def get_debate_snapshot(debate_id: str) -> dict[str, Any] | None:
    """
    Streamlit에서 1초마다 호출. 최신 debate 문서 반환.

    on_snapshot() 콜백 금지(§3.2). 폴링으로만 업데이트 감지.
    """
    db = _db_client()
    snap = db.collection("debates").document(debate_id).get()
    return snap.to_dict() if snap.exists else None


def update_debate_status(debate_id: str, status: str) -> None:
    """status 및 updated_at만 업데이트."""
    db = _db_client()
    db.collection("debates").document(debate_id).update({
        "status": status,
        "updated_at": datetime.now(timezone.utc),
    })


def append_debate_round(debate_id: str, round_data: dict[str, Any]) -> None:
    """rounds 배열에 한 라운드 추가 (ArrayUnion)."""
    db = _db_client()
    db.collection("debates").document(debate_id).update({
        "rounds": firestore.ArrayUnion([round_data]),
        "updated_at": datetime.now(timezone.utc),
    })


def set_debate_pose_data(debate_id: str, pose_data: dict[str, Any]) -> None:
    """PoseExtractor 결과 저장."""
    db = _db_client()
    db.collection("debates").document(debate_id).update({
        "pose_data": pose_data,
        "updated_at": datetime.now(timezone.utc),
    })


def set_debate_consensus(debate_id: str, consensus: dict[str, Any], trace_ids: dict[str, str]) -> None:
    """Mediator 합의 결과 저장."""
    db = _db_client()
    db.collection("debates").document(debate_id).update({
        "consensus": consensus,
        "trace_ids": trace_ids,
        "status": "feedback_pending",
        "updated_at": datetime.now(timezone.utc),
    })


def get_recent_debates(user_id: str, exercise_type: str | None = None, limit: int = 5) -> list[dict]:
    """
    사용자의 최근 debate 목록 반환 (Phoenix MCP 쿼리 보조용).

    Firestore 쿼리 빌더 규칙:
      where 필터들을 먼저 모두 붙이고, order_by + limit을 마지막에 적용.
      (order_by 뒤에 where를 추가하면 InvalidArgument 예외 발생)

    참고: user_id + exercise_type 조합 필터 + created_at 정렬은
    Firestore 복합 인덱스가 필요. 첫 실행 시 GCP 콘솔에 인덱스 생성 링크가
    포함된 FailedPrecondition 에러가 나면, 그 링크 클릭으로 자동 생성.
    """
    db = _db_client()
    q = db.collection("debates").where("user_id", "==", user_id)
    if exercise_type:
        q = q.where("exercise_type", "==", exercise_type)
    q = q.order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit)
    # snap.id(= debate_id)를 dict 에 보존.
    #   Phoenix MCP 의 past_debate_references 가 "실제 doc id" 를 쓰도록 하기 위함.
    #   (예전엔 id 를 버려서 Mediator LLM 이 created_at 으로 debate_id 를 합성했음 — P4 결함)
    #   debates 문서에는 원래 "debate_id" 라는 필드가 없으므로 키 충돌 없음.
    results: list[dict] = []
    for snap in q.stream():
        data = snap.to_dict() or {}
        data["debate_id"] = snap.id
        results.append(data)
    return results


# ---------------------------------------------------------------------------
# feedback 컬렉션
# ---------------------------------------------------------------------------

def save_feedback(
    feedback_id: str,
    debate_id: str,
    user_id: str,
    encourager_rating: str,
    scrutinizer_rating: str,
    mediator_rating: int,
    free_text: str = "",
) -> None:
    """피드백 문서 저장."""
    db = _db_client()
    db.collection("feedback").document(feedback_id).set({
        "debate_id": debate_id,
        "user_id": user_id,
        "encourager_rating": encourager_rating,   # "too_warm" | "perfect" | "too_cold"
        "scrutinizer_rating": scrutinizer_rating,  # "too_harsh" | "perfect" | "too_soft"
        "mediator_rating": mediator_rating,         # 1-5
        "free_text": free_text,
        "created_at": datetime.now(timezone.utc),
    })


# ---------------------------------------------------------------------------
# evals 컬렉션
# ---------------------------------------------------------------------------

def save_eval_result(
    eval_id: str,
    debate_id: str,
    quality_score: float,
    persona_adjustment: dict[str, Any],
) -> None:
    """LLM-as-a-Judge 평가 결과 저장."""
    db = _db_client()
    db.collection("evals").document(eval_id).set({
        "debate_id": debate_id,
        "debate_quality_score": quality_score,
        "persona_adjustment_recommendation": persona_adjustment,
        "created_at": datetime.now(timezone.utc),
    })
