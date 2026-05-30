# 파일 위치: tests/test_pose_extractor.py
"""
PoseExtractor Stage 2 단위 테스트 (Gemini 없이 빠름 — CI 가능).

검증 범위:
  - keyframe 샘플링 (rep 수에 따른 6장 capping)
  - 무릎 visibility 경고 감지 (avg visibility 경고와 구분)
  - merge: Stage1 정량 보존 + Stage2 해석 병합 + P5 면책
  - 신뢰도 가드: rep 0 / 무릎 신뢰도 낮음 → error_code 반환 + Gemini 호출 스킵

실제 영상 e2e 는: python agents/pose_extractor.py --selftest
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agents.pose_extractor as pe
from agents.pose_extractor import (
    _sample_keyframe_times, _low_knee_warning_present, _merge, _error,
    Stage2Interpretation, RepAlignment, SafetyFlag, run_pose_extractor,
)


def test_keyframe_sampling_under_limit():
    # rep 3개 → 시작 + 3 + 끝 = 5장 (max 6 이하라 그대로)
    times = _sample_keyframe_times(0.4, [1.6, 6.0, 10.0], 11.0, 6)
    assert times == [0.4, 1.6, 6.0, 10.0, 11.0], times
    print("  ✅ keyframe 샘플링: rep 3개 → 5장 (그대로)")


def test_keyframe_sampling_over_limit():
    # rep 8개 → 6장으로 capping (시작 + 4 + 끝), 시작/끝 보존
    times = _sample_keyframe_times(0.0, [1, 2, 3, 4, 5, 6, 7, 8], 9.0, 6)
    assert len(times) == 6, times
    assert times[0] == 0.0 and times[-1] == 9.0
    print("  ✅ keyframe 샘플링: rep 8개 → 6장 capping (시작/끝 보존)")


def test_low_knee_warning_detect():
    assert _low_knee_warning_present(
        ["⚠️ 80/100 프레임에서 양쪽 무릎 visibility 낮음 (< 0.5)..."])
    # avg visibility 경고는 무릎 가드를 발동시키면 안 됨 (별개 신호)
    assert not _low_knee_warning_present(
        ["⚠️ 키포인트 신뢰도 낮음 (평균 visibility=0.40 < 0.5)..."])
    assert not _low_knee_warning_present([])
    print("  ✅ 무릎 경고 감지 (avg visibility 경고와 구분)")


def _fake_stage1(rep_count=2, warnings=None):
    reps = [
        {"rep_number": 1, "depth_degrees": 26, "back_angle_at_bottom": 42,
         "back_angle_at_top": 88, "tempo": {"down_sec": 1.4, "up_sec": 1.3, "pause_sec": 0.0},
         "bottom_timestamp_sec": 1.6},
        {"rep_number": 2, "depth_degrees": 41, "back_angle_at_bottom": 45,
         "back_angle_at_top": 90, "tempo": {"down_sec": 1.9, "up_sec": 1.0, "pause_sec": 0.0},
         "bottom_timestamp_sec": 10.0},
    ]
    return {
        "exercise_type": "squat", "rep_count": rep_count, "duration_seconds": 11.0,
        "reps": reps[:rep_count],
        "overall_metrics": {"depth_consistency": 0.8, "tempo_consistency": 0.78},
        "warnings": warnings or [], "_metadata": {"fps": 59.4},
    }


def _fake_analysis(rep_count=2, warnings=None):
    """analyze_video 가 반환하는 객체(.to_dict()) 흉내."""
    payload = _fake_stage1(rep_count=rep_count, warnings=warnings)
    return type("FakeAnalysis", (), {"to_dict": lambda self: payload})()


def test_merge_preserves_quant_adds_interpretation():
    interp = Stage2Interpretation(
        camera_angle="side",
        knee_alignment_per_rep=[
            RepAlignment(rep_number=1, knee_alignment="not_visible"),
            RepAlignment(rep_number=2, knee_alignment="not_visible"),
        ],
        safety_flags=[SafetyFlag(severity="medium", issue="insufficient_depth",
                                 rep_numbers=[2], rationale="2회차 깊이 부족")],
        form_score_0_100=78,
        reasoning="측면에서 깊이는 충분하나 마지막 rep 이 얕음.",
    )
    out = _merge(_fake_stage1(), interp, keyframes_sent=4, stage2_latency=3.1)

    # Stage1 정량 불변
    assert out["reps"][0]["depth_degrees"] == 26
    assert out["reps"][1]["depth_degrees"] == 41
    assert out["overall_metrics"]["depth_consistency"] == 0.8
    # Stage2 해석 병합
    assert out["camera_angle"] == "side"
    assert out["reps"][0]["knee_alignment"] == "not_visible"
    assert out["overall_metrics"]["form_score_0_100"] == 78
    assert len(out["safety_flags"]) == 1
    # P5 면책 + 메타
    assert "의학적 조언이 아닙니다" in out["disclaimer"]
    assert out["_metadata"]["keyframes_sent"] == 4
    assert out["_metadata"]["stage2_model"] == "gemini-2.5-flash"
    print("  ✅ merge: 정량 보존 + 해석 병합 + P5 면책")


def test_error_structure():
    e = _error("no_reps_detected", "메시지", {"rep_count": 0})
    assert e["error"] is True and e["error_code"] == "no_reps_detected"
    assert "의학적 조언이 아닙니다" in e["disclaimer"]
    print("  ✅ error 페이로드 구조 + 면책")


def _no_gemini(*a, **k):
    raise AssertionError("신뢰도 가드 실패 시 Gemini 가 호출되면 안 됨")


def test_guard_rep_zero():
    orig_av, orig_gi = pe.analyze_video, pe._gemini_interpret
    try:
        pe.analyze_video = lambda *a, **k: _fake_analysis(
            rep_count=0, warnings=["⚠️ rep을 1개도 찾지 못함..."])
        pe._gemini_interpret = _no_gemini
        out = run_pose_extractor("dummy.mp4", "squat")
        assert out["error"] is True and out["error_code"] == "no_reps_detected", out
        print("  ✅ 가드: rep 0 → no_reps_detected (Gemini 스킵)")
    finally:
        pe.analyze_video, pe._gemini_interpret = orig_av, orig_gi


def test_guard_low_knee():
    orig_av, orig_gi = pe.analyze_video, pe._gemini_interpret
    try:
        pe.analyze_video = lambda *a, **k: _fake_analysis(
            warnings=["⚠️ 80/100 프레임에서 양쪽 무릎 visibility 낮음 (< 0.5)..."])
        pe._gemini_interpret = _no_gemini
        out = run_pose_extractor("dummy.mp4", "squat")
        assert out["error"] is True and out["error_code"] == "low_knee_confidence", out
        print("  ✅ 가드: 무릎 신뢰도 낮음 → low_knee_confidence (Gemini 스킵)")
    finally:
        pe.analyze_video, pe._gemini_interpret = orig_av, orig_gi


def main() -> int:
    print("=" * 60)
    print("PoseExtractor Stage 2 단위 테스트 (Gemini 없이)")
    print("=" * 60)
    tests = [
        test_keyframe_sampling_under_limit,
        test_keyframe_sampling_over_limit,
        test_low_knee_warning_detect,
        test_merge_preserves_quant_adds_interpretation,
        test_error_structure,
        test_guard_rep_zero,
        test_guard_low_knee,
    ]
    for t in tests:
        t()
    print("=" * 60)
    print(f"✅ {len(tests)}개 모두 통과")
    print("\n실제 영상 e2e: python agents/pose_extractor.py --selftest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
