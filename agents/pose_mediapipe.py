"""
PoseExtractor Stage 1 — MediaPipe Pose 기반 정량 측정 모듈.

ARCHITECTURE.md §2.1 명세 구현:
- 33개 키포인트 추출 (mp_pose.Pose)
- NumPy로 관절 각도·tempo·rep count 정확 계산
- LLM은 직접 측정에 관여하지 않음 (거짓 정밀 방지)

CLI 사용:
    python agents/pose_mediapipe.py data/sample_videos/squat_demo.mp4

출력: stdout에 JSON 형태로 메트릭 dump.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import mediapipe as mp
import numpy as np

# MediaPipe Pose 33 키포인트 인덱스 (PoseLandmark enum 값과 동일)
LM = mp.solutions.pose.PoseLandmark

# 관절 각도 계산용 트리플렛 (proximal, joint, distal)
# 무릎 각도: hip - knee - ankle
JOINT_TRIPLETS_LEFT = {
    "knee":  (LM.LEFT_HIP,      LM.LEFT_KNEE,     LM.LEFT_ANKLE),
    "hip":   (LM.LEFT_SHOULDER, LM.LEFT_HIP,      LM.LEFT_KNEE),
    "ankle": (LM.LEFT_KNEE,     LM.LEFT_ANKLE,    LM.LEFT_FOOT_INDEX),
}
JOINT_TRIPLETS_RIGHT = {
    "knee":  (LM.RIGHT_HIP,      LM.RIGHT_KNEE,     LM.RIGHT_ANKLE),
    "hip":   (LM.RIGHT_SHOULDER, LM.RIGHT_HIP,      LM.RIGHT_KNEE),
    "ankle": (LM.RIGHT_KNEE,     LM.RIGHT_ANKLE,    LM.RIGHT_FOOT_INDEX),
}

# 등(척추) 각도: 어깨 중점 → 엉덩이 중점 → 수직축
# confidence 임계값 (visibility) — 이보다 낮으면 신뢰성 경고
MIN_LANDMARK_VISIBILITY = 0.5


@dataclass
class FrameMetrics:
    """프레임 1장의 정량 메트릭."""
    frame_idx: int
    timestamp_sec: float
    knee_angle_left: float | None
    knee_angle_right: float | None
    hip_angle_left: float | None
    hip_angle_right: float | None
    back_angle_deg: float | None  # 척추 vs 수직축
    avg_visibility: float          # 33개 landmark visibility 평균


@dataclass
class RepMetrics:
    """한 rep(반복) 단위 집계."""
    rep_number: int
    depth_degrees: int            # 최저점의 무릎 각도 (작을수록 깊음)
    back_angle_at_bottom: int     # 최저점의 등 각도
    back_angle_at_top: int        # 시작/끝의 등 각도
    tempo: dict[str, float]       # {"down_sec", "up_sec", "pause_sec"}


@dataclass
class PoseAnalysis:
    """ARCHITECTURE.md §2.1 출력 스키마와 호환되는 결과."""
    exercise_type: str
    rep_count: int
    duration_seconds: float
    reps: list[RepMetrics] = field(default_factory=list)
    overall_metrics: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "exercise_type": self.exercise_type,
            "rep_count": self.rep_count,
            "duration_seconds": round(self.duration_seconds, 2),
            "reps": [
                {
                    "rep_number": r.rep_number,
                    "depth_degrees": r.depth_degrees,
                    "back_angle_at_bottom": r.back_angle_at_bottom,
                    "back_angle_at_top": r.back_angle_at_top,
                    "tempo": r.tempo,
                }
                for r in self.reps
            ],
            "overall_metrics": self.overall_metrics,
            "warnings": self.warnings,
            "_metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# 각도 계산
# ---------------------------------------------------------------------------

def _calc_angle(p1: np.ndarray, p2: np.ndarray, p3: np.ndarray) -> float:
    """세 점 p1→p2→p3 사이의 각도 (degrees). p2가 vertex."""
    v1 = p1 - p2
    v2 = p3 - p2
    cos = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9)
    cos = float(np.clip(cos, -1.0, 1.0))
    return float(np.degrees(np.arccos(cos)))


def _landmark_xy(landmarks, idx: int) -> np.ndarray:
    lm = landmarks[idx]
    return np.array([lm.x, lm.y], dtype=np.float64)


def _back_angle_vs_vertical(landmarks) -> float | None:
    """척추 (어깨 중점 → 엉덩이 중점) 와 수직축 사이 각도."""
    try:
        sh_l = _landmark_xy(landmarks, LM.LEFT_SHOULDER)
        sh_r = _landmark_xy(landmarks, LM.RIGHT_SHOULDER)
        hp_l = _landmark_xy(landmarks, LM.LEFT_HIP)
        hp_r = _landmark_xy(landmarks, LM.RIGHT_HIP)
    except IndexError:
        return None
    sh_mid = (sh_l + sh_r) / 2
    hp_mid = (hp_l + hp_r) / 2
    spine = sh_mid - hp_mid  # 엉덩이 → 어깨 벡터
    vertical = np.array([0.0, -1.0])  # 이미지 좌표는 y가 아래로 증가 → 위 방향은 -y
    cos = np.dot(spine, vertical) / (np.linalg.norm(spine) + 1e-9)
    cos = float(np.clip(cos, -1.0, 1.0))
    return float(np.degrees(np.arccos(cos)))


def _process_frame(frame_idx: int, ts: float, landmarks) -> FrameMetrics:
    def safe_triplet(triplet):
        try:
            p1 = _landmark_xy(landmarks, triplet[0])
            p2 = _landmark_xy(landmarks, triplet[1])
            p3 = _landmark_xy(landmarks, triplet[2])
            return _calc_angle(p1, p2, p3)
        except Exception:
            return None

    return FrameMetrics(
        frame_idx=frame_idx,
        timestamp_sec=ts,
        knee_angle_left=safe_triplet(JOINT_TRIPLETS_LEFT["knee"]),
        knee_angle_right=safe_triplet(JOINT_TRIPLETS_RIGHT["knee"]),
        hip_angle_left=safe_triplet(JOINT_TRIPLETS_LEFT["hip"]),
        hip_angle_right=safe_triplet(JOINT_TRIPLETS_RIGHT["hip"]),
        back_angle_deg=_back_angle_vs_vertical(landmarks),
        avg_visibility=float(np.mean([lm.visibility for lm in landmarks])),
    )


# ---------------------------------------------------------------------------
# Rep 카운트 (스쿼트 기준: 무릎 각도 시계열의 local minima)
# ---------------------------------------------------------------------------

def _smooth(values: list[float], window: int = 5) -> np.ndarray:
    """간단 moving average. window는 홀수 권장."""
    arr = np.array(values, dtype=np.float64)
    if len(arr) < window:
        return arr
    kernel = np.ones(window) / window
    return np.convolve(arr, kernel, mode="same")


def _find_reps(knee_angles: list[float], timestamps: list[float],
               min_depth_deg: float = 110.0, min_rep_gap_sec: float = 0.6) -> list[tuple[int, int, int]]:
    """
    무릎 각도 시계열에서 rep 구간을 찾는다.
    rep 구간 = (start_idx, bottom_idx, end_idx).
    - bottom: 무릎 각도 local minimum (스쿼트면 가장 깊이 앉은 지점)
    - start/end: bottom 양쪽으로 각도가 거의 평평해지는 지점 (top)
    """
    smoothed = _smooth(knee_angles, window=5)
    if len(smoothed) < 10:
        return []

    # 1) local minima 후보: 좌우보다 작고 임계값 미만
    minima_idx: list[int] = []
    for i in range(3, len(smoothed) - 3):
        if smoothed[i] < min_depth_deg and \
           smoothed[i] <= smoothed[i - 3] and smoothed[i] <= smoothed[i + 3]:
            minima_idx.append(i)

    # 2) 시간 간격이 너무 가까운 minima는 병합 (가장 깊은 것만 남김)
    filtered: list[int] = []
    for idx in minima_idx:
        if not filtered:
            filtered.append(idx)
            continue
        if timestamps[idx] - timestamps[filtered[-1]] < min_rep_gap_sec:
            if smoothed[idx] < smoothed[filtered[-1]]:
                filtered[-1] = idx
        else:
            filtered.append(idx)

    # 3) 각 bottom 주변에서 start/end (각도가 다시 올라간 지점) 찾기
    reps: list[tuple[int, int, int]] = []
    for bottom in filtered:
        # 뒤로 가면서 각도가 올라가는 지점까지
        start = bottom
        while start > 0 and smoothed[start - 1] > smoothed[start]:
            start -= 1
        end = bottom
        while end < len(smoothed) - 1 and smoothed[end + 1] > smoothed[end]:
            end += 1
        reps.append((start, bottom, end))
    return reps


# ---------------------------------------------------------------------------
# 메인 분석 함수
# ---------------------------------------------------------------------------

def analyze_video(video_path: str, exercise_type: str = "squat") -> PoseAnalysis:
    """
    비디오 파일을 MediaPipe로 분석해 정량 메트릭 dict 반환.
    Acceptance: 30초 영상 분석 5초 이내 (CPU).
    """
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"비디오 파일을 찾을 수 없음: {video_path}")

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV가 비디오를 열지 못함: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0.0

    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(
        static_image_mode=False,
        model_complexity=1,        # 0/1/2. 1이 속도-정확도 균형
        enable_segmentation=False,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    start_time = time.perf_counter()
    frames: list[FrameMetrics] = []
    frame_idx = 0
    miss_count = 0

    while True:
        ok, frame_bgr = cap.read()
        if not ok:
            break
        ts = frame_idx / fps
        # MediaPipe는 RGB 입력
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = pose.process(frame_rgb)
        if result.pose_landmarks:
            frames.append(_process_frame(frame_idx, ts, result.pose_landmarks.landmark))
        else:
            miss_count += 1
        frame_idx += 1

    cap.release()
    pose.close()
    elapsed = time.perf_counter() - start_time

    # ---- rep 추출 (양쪽 무릎 각도 평균 사용) ----
    timestamps = [f.timestamp_sec for f in frames]
    knee_angles: list[float] = []
    for f in frames:
        candidates = [a for a in (f.knee_angle_left, f.knee_angle_right) if a is not None]
        knee_angles.append(float(np.mean(candidates)) if candidates else 180.0)

    rep_indices = _find_reps(knee_angles, timestamps)

    rep_metrics_list: list[RepMetrics] = []
    for i, (s, b, e) in enumerate(rep_indices, start=1):
        bottom_frame = frames[b]
        start_frame = frames[s]
        end_frame = frames[e]
        depth = int(round(knee_angles[b]))
        back_bottom = int(round(bottom_frame.back_angle_deg)) if bottom_frame.back_angle_deg is not None else -1
        back_top = int(round(start_frame.back_angle_deg)) if start_frame.back_angle_deg is not None else -1

        down_sec = max(0.0, bottom_frame.timestamp_sec - start_frame.timestamp_sec)
        up_sec = max(0.0, end_frame.timestamp_sec - bottom_frame.timestamp_sec)
        rep_metrics_list.append(RepMetrics(
            rep_number=i,
            depth_degrees=depth,
            back_angle_at_bottom=back_bottom,
            back_angle_at_top=back_top,
            tempo={"down_sec": round(down_sec, 2),
                   "up_sec":   round(up_sec, 2),
                   "pause_sec": 0.0},
        ))

    # ---- 전반 메트릭 ----
    overall: dict[str, Any] = {}
    if rep_metrics_list:
        depths = [r.depth_degrees for r in rep_metrics_list]
        downs = [r.tempo["down_sec"] for r in rep_metrics_list]
        # consistency = 1 - 표준편차/평균 (clamped)
        overall["depth_consistency"] = round(
            float(max(0.0, 1.0 - (np.std(depths) / max(1.0, np.mean(depths))))), 2)
        overall["tempo_consistency"] = round(
            float(max(0.0, 1.0 - (np.std(downs) / max(0.1, np.mean(downs))))), 2)

    # ---- 경고 (Acceptance: visibility 낮으면 명확한 경고) ----
    warnings: list[str] = []
    if frames:
        avg_vis = float(np.mean([f.avg_visibility for f in frames]))
        if avg_vis < MIN_LANDMARK_VISIBILITY:
            warnings.append(
                f"⚠️ 키포인트 신뢰도 낮음 (평균 visibility={avg_vis:.2f} < {MIN_LANDMARK_VISIBILITY}). "
                f"카메라 각도·조명·전신 노출 확인 권장."
            )
    if total_frames > 0 and miss_count / total_frames > 0.2:
        warnings.append(
            f"⚠️ {miss_count}/{total_frames} 프레임에서 자세 미검출. 사람이 전신으로 보이는지 확인."
        )
    if not rep_metrics_list:
        warnings.append("⚠️ rep을 1개도 찾지 못함. 운동 동작인지 / 무릎 각도가 충분히 굽혀지는지 확인.")

    return PoseAnalysis(
        exercise_type=exercise_type,
        rep_count=len(rep_metrics_list),
        duration_seconds=duration,
        reps=rep_metrics_list,
        overall_metrics=overall,
        warnings=warnings,
        metadata={
            "model": "mediapipe-pose-v1-complexity1",
            "frames_analyzed": len(frames),
            "frames_missed": miss_count,
            "analysis_duration_sec": round(elapsed, 2),
            "fps": round(fps, 1),
        },
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_usage_and_exit() -> None:
    print(
        "사용법:\n"
        "    python agents/pose_mediapipe.py <video_path> [exercise_type]\n\n"
        "예시:\n"
        "    python agents/pose_mediapipe.py data/sample_videos/squat_demo.mp4 squat\n",
        file=sys.stderr,
    )
    sys.exit(2)


def main() -> int:
    if len(sys.argv) < 2:
        _print_usage_and_exit()
    video_path = sys.argv[1]
    exercise_type = sys.argv[2] if len(sys.argv) >= 3 else "squat"

    try:
        result = analyze_video(video_path, exercise_type=exercise_type)
    except FileNotFoundError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"❌ 분석 실패: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    payload = result.to_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    # Acceptance 즉시 자가 검증
    analysis_sec = payload["_metadata"]["analysis_duration_sec"]
    duration = payload["duration_seconds"]
    print("\n--- Self-check ---", file=sys.stderr)
    print(f"  영상 길이:   {duration:.1f}s", file=sys.stderr)
    print(f"  분석 시간:   {analysis_sec:.2f}s", file=sys.stderr)
    print(f"  검출 rep:    {result.rep_count}", file=sys.stderr)
    if duration <= 30.0 and analysis_sec <= 5.0:
        print("  ✅ Acceptance 통과: 30s 영상 5s 이내 분석", file=sys.stderr)
    elif duration > 30.0:
        ratio = analysis_sec / duration
        print(f"  ℹ️ 30s 초과 영상 → 비율 기준 평가: {ratio:.2f} (≤0.17이면 30s 영상에 5s 이내 환산)",
              file=sys.stderr)
    else:
        print("  ⚠️ Acceptance 미달: 30s 영상에 5s 이내 분석 못함. 다른 model_complexity 시도 권장.",
              file=sys.stderr)

    for w in result.warnings:
        print(f"  {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
