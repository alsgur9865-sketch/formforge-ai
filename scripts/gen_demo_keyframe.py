# 파일 위치: scripts/gen_demo_keyframe.py
"""데모 히어로용 주석 프리즈프레임 1장 생성 → data/demo_keyframe[_side].jpg.

라이브와 동일한 렌더 로직(agents.pose_extractor._overlay_spec + pose_overlay)을 써서
운동 영상의 실제 프레임 + 실제 좌표 위에 데모 서사(sample_data)와 일치하는 오버레이를
굽는다. 렌더 코드가 바뀌면 이 스크립트를 재실행해 자산을 갱신.

실행:
    ./venv/Scripts/python.exe scripts/gen_demo_keyframe.py          # front(기본)
    ./venv/Scripts/python.exe scripts/gen_demo_keyframe.py side     # 측면(등 말림 헤드라인)
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

# 앵글별 설정. front: 정면 깊이 편차(rep2 가 97° 로 얕음 → insufficient_depth 빨강 DEPTH).
# side: 측면 등 말림(rep1 이 78° 로 과도한 전방 기울임 → back_rounding 빨강 LEAN + 깊이는 초록).
CONFIG = {
    "front": {
        "video": _ROOT / "data" / "sample_videos" / "squat_front_demo.mp4",
        "out": _ROOT / "data" / "demo_keyframe.jpg",
        "hero_rep": 2,
        "issue": "insufficient_depth",
        "severity": "medium",
    },
    "side": {
        "video": _ROOT / "data" / "sample_videos" / "squat_side_demo.mp4",
        "out": _ROOT / "data" / "demo_keyframe_side.jpg",
        "hero_rep": 1,
        "issue": "back_rounding",
        "severity": "high",
    },
}


def main() -> int:
    angle = sys.argv[1] if len(sys.argv) >= 2 else "front"
    if angle not in CONFIG:
        print(f"알 수 없는 angle: {angle} (front|side)", file=sys.stderr)
        return 2
    cfg = CONFIG[angle]
    video, out = cfg["video"], cfg["out"]
    if not video.exists():
        print(f"❌ 샘플 영상 없음: {video}", file=sys.stderr)
        return 1

    print(f"[{angle}] · Stage1 분석 중(좌표 추출)…", file=sys.stderr)
    analysis = analyze_video(str(video), "squat")
    reps = [r for r in analysis.reps if r.bottom_landmarks]
    if not reps:
        print("❌ rep/landmark 추출 실패", file=sys.stderr)
        return 1

    # 헤드라인 rep 을 히어로로 (없으면 첫 rep). front=얕은 rep2, side=등 말린 rep1.
    hero = next((r for r in reps if r.rep_number == cfg["hero_rep"]), reps[0])

    cap = cv2.VideoCapture(str(video))
    cap.set(cv2.CAP_PROP_POS_MSEC, hero.bottom_timestamp_sec * 1000.0)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        print("❌ 프레임 seek 실패", file=sys.stderr)
        return 1

    # 실측 flag → _overlay_spec 으로 라이브와 동일 오버레이(가짜 각도 없음 — 전부 실데이터).
    flag = {"issue": cfg["issue"], "severity": cfg["severity"], "rep_numbers": [hero.rep_number]}
    rep = {"rep_number": hero.rep_number,
           "depth_degrees": hero.depth_degrees,
           "back_angle_at_bottom": hero.back_angle_at_bottom}
    flagged, labels = _overlay_spec(flag, rep)

    jpg = render_keyframe_overlay(
        frame, hero.bottom_landmarks, flagged, labels,
        exercise="squat",
        timecode=f"REP {hero.rep_number} · {hero.bottom_timestamp_sec:.1f}S",
        bg="black",  # 데모 히어로: 검정 배경 + 스켈레톤만(실제 영상 프레임 비노출)
    )
    out.write_bytes(jpg)
    print(f"✅ {out}  ({len(jpg) // 1024} KB · depth={hero.depth_degrees}° · "
          f"lean={hero.back_angle_at_bottom}° · t={hero.bottom_timestamp_sec:.1f}s · "
          f"labels={[l.text for l in labels]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
