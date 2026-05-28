# 파일 위치: tests/test_firestore.py
"""
Task 2.1 Acceptance Criteria 검증 스크립트.

실행:
    ./venv/Scripts/python.exe tests/test_firestore.py

성공 조건:
  1) 더미 사용자(test_user_001)가 Firestore에 생성됨
  2) persona_state 기본값(warmth=0.5, harshness=0.5, detail=0.5) 반환 확인
  3) GCP 콘솔 Firestore > users > test_user_001 문서 수동 확인 가능

Phoenix trace는 이 스크립트에서 전송하지 않음 (순수 Firestore 검증만).
"""

from __future__ import annotations

import os
import sys

# 프로젝트 루트를 path에 추가 (tests/ 안에서 실행해도 storage/ import 가능)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()

from storage.firestore_client import (
    create_user,
    get_user,
    get_user_persona_state,
    update_user_persona_state,
    get_user_injury_history,
    create_debate,
    get_debate_snapshot,
    update_debate_status,
    append_debate_round,
    get_recent_debates,
)

TEST_USER_ID = "test_user_001"
TEST_DEBATE_ID = "test_debate_001"


def _pass(msg: str) -> None:
    print(f"  ✅  {msg}")


def _fail(msg: str) -> None:
    print(f"  ❌  {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# 테스트 1 — 사용자 생성 + 조회
# ---------------------------------------------------------------------------
print("\n[1] 사용자 생성 / 조회")

create_user(
    TEST_USER_ID,
    {
        "name": "테스트 유저",
        "email": "test@formforge.ai",
        "experience_level": "intermediate",
        "injury_history": ["lower_back_strain_2025"],
    },
)

doc = get_user(TEST_USER_ID)
if doc is None:
    _fail("users/test_user_001 문서 조회 실패 — Firestore 연결 또는 권한 확인 필요")

_pass(f"users/{TEST_USER_ID} 문서 생성 및 조회 성공")

# ---------------------------------------------------------------------------
# 테스트 2 — persona_state 기본값
# ---------------------------------------------------------------------------
print("\n[2] persona_state 기본값 확인")

state = get_user_persona_state(TEST_USER_ID)
enc_warmth = state["encourager"]["warmth"]
enc_detail = state["encourager"]["detail"]
scr_harshness = state["scrutinizer"]["harshness"]
scr_detail = state["scrutinizer"]["detail"]

for label, val in [
    ("encourager.warmth", enc_warmth),
    ("encourager.detail", enc_detail),
    ("scrutinizer.harshness", scr_harshness),
    ("scrutinizer.detail", scr_detail),
]:
    if val != 0.5:
        _fail(f"{label} 기본값이 0.5가 아님 (실제: {val})")
    _pass(f"{label} = {val}")

# ---------------------------------------------------------------------------
# 테스트 3 — persona_state 부분 업데이트 (dot-notation으로 sibling 보존)
# ---------------------------------------------------------------------------
print("\n[3] persona_state 부분 업데이트 (warmth만 변경)")

# warmth만 변경 — detail은 그대로 유지되어야 함 (이전 버그: 통째 덮어쓰기로 detail 사라짐)
update_user_persona_state(TEST_USER_ID, {
    "encourager": {"warmth": 0.7},
})

updated = get_user_persona_state(TEST_USER_ID)
if updated["encourager"]["warmth"] != 0.7:
    _fail(f"warmth 업데이트 실패 (실제: {updated['encourager']['warmth']})")
_pass(f"encourager.warmth 업데이트 확인: 0.5 → 0.7")

# sibling 보존 검증 (Critical #3 회귀 테스트)
if updated["encourager"].get("detail") != 0.5:
    _fail(
        f"sibling 보존 실패! warmth만 보냈는데 detail이 사라지거나 변경됨. "
        f"실제 encourager: {updated['encourager']}"
    )
_pass("encourager.detail = 0.5 보존 확인 (dot-notation 부분 업데이트 OK)")

# total_feedback_count 자동 증가 검증 (Critical #2 회귀 테스트)
# 초기값 0 → 1번 호출 후 1
if updated.get("total_feedback_count") != 1:
    _fail(
        f"total_feedback_count 자동 증가 실패. "
        f"기대값: 1, 실제: {updated.get('total_feedback_count')}"
    )
_pass(f"total_feedback_count 자동 증가: 0 → {updated['total_feedback_count']}")

# 한 번 더 호출 → 2가 되어야 함
update_user_persona_state(TEST_USER_ID, {"encourager": {"warmth": 0.75}})
updated2 = get_user_persona_state(TEST_USER_ID)
if updated2.get("total_feedback_count") != 2:
    _fail(f"두 번째 호출 후 카운트 불일치. 기대 2, 실제: {updated2.get('total_feedback_count')}")
_pass(f"두 번째 update 후 카운트 누적 확인: 1 → {updated2['total_feedback_count']}")

# ---------------------------------------------------------------------------
# 테스트 4 — injury_history 반환
# ---------------------------------------------------------------------------
print("\n[4] injury_history 반환")

injuries = get_user_injury_history(TEST_USER_ID)
if "lower_back_strain_2025" not in injuries:
    _fail(f"injury_history에 'lower_back_strain_2025' 없음. 실제: {injuries}")
_pass(f"injury_history: {injuries}")

# ---------------------------------------------------------------------------
# 테스트 5 — debate CRUD
# ---------------------------------------------------------------------------
print("\n[5] debate 생성 / 상태 업데이트 / 라운드 추가")

create_debate(
    TEST_DEBATE_ID,
    user_id=TEST_USER_ID,
    video_uri="gs://formforge-videos-test/squat_demo.mp4",
    exercise_type="squat",
)

debate = get_debate_snapshot(TEST_DEBATE_ID)
if debate is None:
    _fail("debates/test_debate_001 문서 생성 실패")
if debate["status"] != "pending":
    _fail(f"초기 status가 'pending'이 아님: {debate['status']}")
_pass("debate 생성 + 초기 status=pending 확인")

update_debate_status(TEST_DEBATE_ID, "debating")
debate = get_debate_snapshot(TEST_DEBATE_ID)
if debate["status"] != "debating":
    _fail(f"status 업데이트 실패: {debate['status']}")
_pass("debate status → debating 업데이트 확인")

append_debate_round(TEST_DEBATE_ID, {
    "round": 1,
    "encourager": {"praise": "무릎 정렬이 안정적입니다.", "concern_one": "엉덩이 하강 깊이"},
    "scrutinizer": {"primary_risk": "요추 과전만 위험", "severity": "medium"},
})
debate = get_debate_snapshot(TEST_DEBATE_ID)
if len(debate["rounds"]) != 1:
    _fail(f"rounds 배열 길이 불일치: {len(debate['rounds'])}")
_pass(f"rounds 배열 추가 확인 (현재 {len(debate['rounds'])}개 라운드)")

# ---------------------------------------------------------------------------
# 테스트 6 — get_recent_debates 쿼리 빌더 (Critical #1 회귀 테스트)
# ---------------------------------------------------------------------------
print("\n[6] get_recent_debates 쿼리 (where + order_by 순서 검증)")

# Critical #1 회귀 테스트:
#   이전 버그: 쿼리 빌더가 .order_by() 뒤에 .where()를 호출 → InvalidArgument 즉시 에러
#   수정 후: where 먼저 모두 붙이고 order_by + limit 마지막
#
# 통과 조건 2가지 (둘 중 하나면 OK):
#   (A) 정상 반환 — 복합 인덱스가 이미 생성된 상태
#   (B) FailedPrecondition — 코드는 맞고 인덱스 1회 생성만 필요 (콘솔 링크 출력)
#
# 절대 통과 X:
#   - InvalidArgument(빌더 순서 버그 재발)
#   - 그 외 모든 예외
from google.api_core.exceptions import FailedPrecondition, InvalidArgument

try:
    recent = get_recent_debates(TEST_USER_ID, limit=5)
    _pass(f"get_recent_debates(user_id) 호출 성공 — {len(recent)}건 반환 (인덱스 OK)")
except FailedPrecondition as e:
    # 인덱스 부족은 OK — 코드는 맞고 인프라 설정만 필요
    msg = str(e)
    if "requires an index" in msg or "create_composite" in msg:
        _pass("쿼리 빌더 순서 OK (FailedPrecondition: 복합 인덱스 1회 생성 필요)")
        # 콘솔 링크 추출 + 안내
        if "https://" in msg:
            link_start = msg.find("https://")
            link_end = msg.find(" ", link_start)
            link = msg[link_start:link_end] if link_end > 0 else msg[link_start:]
            print(f"      👉 인덱스 생성: {link}")
            print(f"         (Phoenix MCP가 실제로 query_past_debates 호출하는 Day 12 이전까지만 만들면 OK)")
    else:
        _fail(f"예상 못 한 FailedPrecondition: {msg}")
except InvalidArgument as e:
    _fail(f"❌ 쿼리 빌더 순서 버그 재발! Critical #1 회귀: {e}")
except Exception as e:
    _fail(f"get_recent_debates 호출 실패: {type(e).__name__}: {e}")

# ---------------------------------------------------------------------------
# 최종 결과
# ---------------------------------------------------------------------------
print()
print("=" * 55)
print("✅  Task 2.1 Acceptance Criteria 모두 통과!")
print()
print("   다음 확인 (수동):")
print("   → GCP 콘솔 > Firestore > users > test_user_001")
print("   → GCP 콘솔 > Firestore > debates > test_debate_001")
print("=" * 55)
