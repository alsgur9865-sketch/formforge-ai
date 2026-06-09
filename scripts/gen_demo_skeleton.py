# 파일 위치: scripts/gen_demo_skeleton.py
"""데모 영웅용 스켈레톤 영상 생성 — squat_demo.mp4 → data/demo_skeleton.mp4 (1회 실행).

analyze_video(keep_frames=True) 로 프레임별 33좌표를 얻어 render_skeleton_video 로
스켈레톤이 몸을 따라 움직이는 H.264 mp4 를 굽는다. UI 데모(?demo=1)가 이걸 인라인 재생.

실행: ./venv/Scripts/python.exe scripts/gen_demo_skeleton.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.pose_mediapipe import analyze_video
from agents.pose_overlay import render_skeleton_video

_ROOT = Path(__file__).resolve().parent.parent
SRC = _ROOT / "data" / "sample_videos" / "squat_front_demo.mp4"  # 정면 valgus 데모(깊이 편차 스토리)
OUT = _ROOT / "data" / "demo_skeleton.mp4"


def main() -> int:
    if not SRC.exists():
        print(f"원본 영상 없음: {SRC}", file=sys.stderr)
        return 1
    print(f"분석 중: {SRC.name} …", file=sys.stderr)
    res = analyze_video(str(SRC), "squat", keep_frames=True)
    print(f"  프레임 {len(res.frame_landmarks)}개 좌표 · rep {res.rep_count}", file=sys.stderr)

    print("스켈레톤 영상 렌더 중 (ffmpeg libx264) …", file=sys.stderr)
    mp4 = render_skeleton_video(str(SRC), res.frame_landmarks, flagged_indices=[])
    OUT.write_bytes(mp4)
    print(f"✅ 생성: {OUT} ({len(mp4) / 1024:.0f} KB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
