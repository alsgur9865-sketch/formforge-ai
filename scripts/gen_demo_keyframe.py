# 파일 위치: scripts/gen_demo_keyframe.py
"""데모 히어로용 주석 프리즈프레임 1장 생성 → data/demo_keyframe.jpg.

라이브와 동일한 렌더 로직(agents.pose_extractor._overlay_spec + pose_overlay)을 써서
squat_demo 의 실제 프레임 + 실제 좌표 위에 데모 서사(sample_data: 왼무릎 valgus)와
일치하는 오버레이를 굽는다. 렌더 코드가 바뀌면 이 스크립트를 재실행해 자산을 갱신.

실행:
    ./venv/Scripts/python.exe scripts/gen_demo_keyframe.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from agents.pose_extractor import _overlay_spec  # noqa: E402  (라이브와 동일 flag→오버레이 매핑)
from agents.pose_mediapipe import analyze_video  # noqa: E402
from agents.pose_overlay import render_keyframe_overlay  # noqa: E402

_VIDEO = _ROOT / "data" / "sample_videos" / "squat_demo.mp4"
_OUT = _ROOT / "data" / "demo_keyframe.jpg"


def main() -> int:
    if not _VIDEO.exists():
        print(f"❌ 샘플 영상 없음: {_VIDEO}", file=sys.stderr)
        return 1

    print("· Stage1 분석 중(좌표 추출)…", file=sys.stderr)
    analysis = analyze_video(str(_VIDEO), "squat")
    reps = [r for r in analysis.reps if r.bottom_landmarks]
    if not reps:
        print("❌ rep/landmark 추출 실패", file=sys.stderr)
        return 1

    # 패러렐(~90°)에 가장 가까운 rep 을 히어로로 — 인식 쉬운 진단 포즈 + readout(avg)과 일관.
    hero = min(reps, key=lambda r: abs(r.depth_degrees - 90))

    cap = cv2.VideoCapture(str(_VIDEO))
    cap.set(cv2.CAP_PROP_POS_MSEC, hero.bottom_timestamp_sec * 1000.0)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        print("❌ 프레임 seek 실패", file=sys.stderr)
        return 1

    # squat_demo 에 실제 파이프라인이 잡는 flag = excessive_forward_lean (측면 가시·실측).
    # 라이브와 동일한 _overlay_spec 으로 힙 강조 + 실측 LEAN/DEPTH 라벨 생성 (가짜 없음 — 전부 실데이터).
    flag = {"issue": "excessive_forward_lean", "severity": "medium", "rep_numbers": [hero.rep_number]}
    rep = {"rep_number": hero.rep_number,
           "depth_degrees": hero.depth_degrees,
           "back_angle_at_bottom": hero.back_angle_at_bottom}
    flagged, labels = _overlay_spec(flag, rep)

    jpg = render_keyframe_overlay(
        frame, hero.bottom_landmarks, flagged, labels,
        exercise="squat",
        timecode=f"REP {hero.rep_number} · {hero.bottom_timestamp_sec:.1f}S",
    )
    _OUT.write_bytes(jpg)
    print(f"✅ {_OUT}  ({len(jpg) // 1024} KB · depth={hero.depth_degrees}° · "
          f"t={hero.bottom_timestamp_sec:.1f}s · labels={[l.text for l in labels]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
