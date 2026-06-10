# 파일 위치: scripts/gen_demo_skeleton.py
"""데모 영웅용 스켈레톤 영상 생성 — 운동 영상 → data/demo_skeleton[_side].mp4 (1회 실행).

analyze_video(keep_frames=True) 로 프레임별 33좌표를 얻어 render_skeleton_video 로
스켈레톤이 몸을 따라 움직이는 H.264 mp4 를 굽는다. UI 데모(?demo=1)가 이걸 인라인 재생.

실행:
    ./venv/Scripts/python.exe scripts/gen_demo_skeleton.py          # front(기본)
    ./venv/Scripts/python.exe scripts/gen_demo_skeleton.py side     # 측면(카메라앵글 인지 데모)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.pose_mediapipe import analyze_video
from agents.pose_overlay import render_skeleton_video

_ROOT = Path(__file__).resolve().parent.parent

# 앵글별 (소스 영상, 출력 자산). 정면=깊이 편차 스토리, 측면=등 말림/전방 기울임 스토리.
CONFIG = {
    "front": (_ROOT / "data" / "sample_videos" / "squat_front_demo.mp4", _ROOT / "data" / "demo_skeleton.mp4"),
    "side": (_ROOT / "data" / "sample_videos" / "squat_side_demo.mp4", _ROOT / "data" / "demo_skeleton_side.mp4"),
}


def main() -> int:
    angle = sys.argv[1] if len(sys.argv) >= 2 else "front"
    if angle not in CONFIG:
        print(f"알 수 없는 angle: {angle} (front|side)", file=sys.stderr)
        return 2
    src, out = CONFIG[angle]
    if not src.exists():
        print(f"원본 영상 없음: {src}", file=sys.stderr)
        return 1
    print(f"[{angle}] 분석 중: {src.name} …", file=sys.stderr)
    res = analyze_video(str(src), "squat", keep_frames=True)
    print(f"  프레임 {len(res.frame_landmarks)}개 좌표 · rep {res.rep_count}", file=sys.stderr)

    print("스켈레톤 영상 렌더 중 (ffmpeg libx264) …", file=sys.stderr)
    mp4 = render_skeleton_video(str(src), res.frame_landmarks, flagged_indices=[], bg="black")
    out.write_bytes(mp4)
    print(f"✅ 생성: {out} ({len(mp4) / 1024:.0f} KB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
