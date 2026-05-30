"""
PoseExtractor Stage 1 — MediaPipe Pose 기반 정량 측정 모듈.

ARCHITECTURE.md §2.1 명세 구현:
- 33개 키포인트 추출 (MediaPipe Tasks PoseLandmarker)
- NumPy로 관절 각도·tempo·rep count 정확 계산
- LLM은 직접 측정에 관여하지 않음 (거짓 정밀 방지)

⚠️ MediaPipe API 노트:
  mediapipe 0.10.30+ 부터 legacy `mp.solutions.pose` API 가 패키지에서 제거됨
  (현재 0.10.35 에는 `tasks`/`modules` 만 있고 `solutions` 폴더 없음).
  → 공식 권장 Tasks API(`mediapipe.tasks.python.vision.PoseLandmarker`)로 구현.
  모델 자산: data/models/pose_landmarker_full.task (BlazePose GHUM, 33 keypoint).
  랜드마크 인덱스/visibility 는 legacy 와 동일하므로 각도·rep·tempo 로직은 그대로 재사용.

CLI 사용:
    python agents/pose_mediapipe.py data/sample_videos/squat_demo.mp4 squat

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
from mediapipe.tasks.python import BaseOptions, vision

# RunningMode 는 vision 에서 re-export 되지만 mediapipe 버전에 따라 경로가 흔들릴 수
# 있어, 검증된 vision.RunningMode 를 모듈 레벨 별칭으로 고정한다 (리뷰 #5).
RunningMode = vision.RunningMode

# PoseLandmarker 모델 자산 경로
_MODEL_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "models"
    / "pose_landmarker_full.task"
)


# MediaPipe Pose 33 키포인트 인덱스 (BlazePose GHUM 표준 — legacy PoseLandmark enum 과 동일).
# Tasks API 에는 PoseLandmark enum 이 없으므로 정수 상수로 정의.
class LM:
    LEFT_SHOULDER = 11
    RIGHT_SHOULDER = 12
    LEFT_HIP = 23
    RIGHT_HIP = 24
    LEFT_KNEE = 25
    RIGHT_KNEE = 26
    LEFT_ANKLE = 27
    RIGHT_ANKLE = 28
    LEFT_FOOT_INDEX = 31
    RIGHT_FOOT_INDEX = 32


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
    knee_vis_left: float = 0.0     # 좌무릎 visibility (occlusion 가중 평균용)
    knee_vis_right: float = 0.0    # 우무릎 visibility


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
    """Tasks API 의 pose_landmarks[0][idx] → (x, y) numpy 벡터.

    legacy(solutions) 와 동일하게 정규화 좌표 .x/.y 를 사용한다.
    """
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
    # 코사인 정의상 분모는 두 벡터 노름의 곱. vertical 노름은 1.0 이지만, 향후 수직축을
    # 바꿔도 안전하도록 명시한다 (리뷰 #2 — 수식 정확성).
    cos = np.dot(spine, vertical) / (
        np.linalg.norm(spine) * np.linalg.norm(vertical) + 1e-9
    )
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

    # Tasks API NormalizedLandmark 에는 .visibility 가 존재 (legacy 와 동일).
    visibilities = [getattr(lm, "visibility", 0.0) for lm in landmarks]

    def vis(idx: int) -> float:
        try:
            return float(getattr(landmarks[idx], "visibility", 0.0))
        except IndexError:
            return 0.0

    return FrameMetrics(
        frame_idx=frame_idx,
        timestamp_sec=ts,
        knee_angle_left=safe_triplet(JOINT_TRIPLETS_LEFT["knee"]),
        knee_angle_right=safe_triplet(JOINT_TRIPLETS_RIGHT["knee"]),
        hip_angle_left=safe_triplet(JOINT_TRIPLETS_LEFT["hip"]),
        hip_angle_right=safe_triplet(JOINT_TRIPLETS_RIGHT["hip"]),
        back_angle_deg=_back_angle_vs_vertical(landmarks),
        avg_visibility=float(np.mean(visibilities)) if visibilities else 0.0,
        knee_vis_left=vis(LM.LEFT_KNEE),
        knee_vis_right=vis(LM.RIGHT_KNEE),
    )


# ---------------------------------------------------------------------------
# Rep 카운트 (스쿼트 기준: 무릎 각도 시계열의 local minima)
# ---------------------------------------------------------------------------

def _smooth(values: list[float], window: int = 5) -> np.ndarray:
    """moving average. edge 패딩으로 경계 왜곡 방지 (리뷰 #3·#6).

    np.convolve(mode="same") 는 경계에서 커널이 배열 밖을 0으로 간주해
    시계열 양끝이 0 쪽으로 끌려 내려간다 → 첫/마지막 rep 의 tempo·depth 왜곡 원인.
    → edge 패딩(양끝값 복제) 후 mode="valid" 로 길이를 보존하면서 경계값을 자기
    자신으로 채운다. window 는 대칭 커널을 위해 홀수로 강제.
    """
    arr = np.array(values, dtype=np.float64)
    if window < 2:
        return arr
    if window % 2 == 0:
        window += 1
    if len(arr) < window:
        return arr
    half = window // 2
    padded = np.pad(arr, half, mode="edge")
    kernel = np.ones(window, dtype=np.float64) / window
    return np.convolve(padded, kernel, mode="valid")


def _find_reps(knee_angles: list[float],
               fps: float = 30.0,
               min_depth_deg: float = 110.0) -> list[tuple[int, int, int]]:
    """
    무릎 각도 시계열에서 rep 구간을 찾는다.
    rep 구간 = (start_idx, bottom_idx, end_idx).
    - bottom: 무릎 각도 local minimum (스쿼트면 가장 깊이 앉은 지점)
    - start/end: bottom 양쪽으로 '서 있는 자세(top)' 로 회복하는 지점

    fps 비례 파라미터 (30fps 가정 하드코딩 제거 — tempo 현실화 핵심):
    - smoothing window  ≈ 0.25s 치 프레임 (59fps→15, 30fps→7) → 남은 노이즈 제거
    - minima 비교 반경   ≈ 0.10s 치 프레임 → 좁은 ±3프레임 대신 fps 무관 일정 시간
    - start/end 는 '단조증가 추적'(노이즈 진동에 1~2프레임 만에 멈춰 tempo=0.03s 가 되던
      원인) 대신 'standing 으로 80% 회복하는 첫 지점' 으로 잡아 실제 down/up 길이를 반영.

    rep 병합은 prominence 기반 (시간 간격 기반 X): 깊게 앉아 머무는 동안의 출렁임이나
    한 rep 안의 멈칫을 별개 rep 으로 오검출하던 문제 → '인접 골짜기 사이에 충분히
    일어섰는가(top 회복량)' 로 판정한다.
    """
    n = len(knee_angles)

    # fps 비례 smoothing window (홀수)
    win = max(3, int(round(fps * 0.25)))
    if win % 2 == 0:
        win += 1
    smoothed = _smooth(knee_angles, window=win)
    if n < max(10, win):
        return []

    # minima 비교 반경 (0.10s 치, 최소 2프레임)
    radius = max(2, int(round(fps * 0.10)))

    # 서 있는 자세(top) 각도 추정 — 상위 분위수(서 있는 프레임이 다수라 가정).
    # 스쿼트 비율이 높아 90th percentile 이 min_depth_deg 이하로 오염되면(I-2)
    # 신호 최댓값으로 폴백한다.
    standing = float(np.percentile(smoothed, 90))
    if standing <= min_depth_deg:
        standing = float(np.max(smoothed))

    # 1) local minima 후보: 좌우 radius 구간 최솟값이고 임계값 미만.
    #    경계(앞뒤 radius)에서도 가능한 만큼만 비교해 영상 끝부분의 마지막 bottom 을
    #    놓치지 않는다 (한쪽 slice 가 비면 그쪽 비교는 통과로 간주). 경계 과검출은
    #    뒤의 prominence 병합이 걸러낸다.
    minima_idx: list[int] = []
    for i in range(n):
        if smoothed[i] >= min_depth_deg:
            continue
        seg_l = smoothed[max(0, i - radius):i]
        seg_r = smoothed[i + 1:i + 1 + radius]
        le_l = (seg_l.size == 0) or (smoothed[i] <= seg_l.min())
        le_r = (seg_r.size == 0) or (smoothed[i] <= seg_r.min())
        if le_l and le_r:
            minima_idx.append(i)

    # 2) prominence 기반 병합: 인접 minima 사이 top 회복(rise)이 부족하면 같은 rep.
    #    각도는 작을수록 깊다. 두 골짜기 중 '더 얕은(각도가 큰) 쪽'(shallower_ang)을
    #    기준으로 사이 봉우리(peak)가 얼마나 솟았는지 본다 — 봉우리가 더 얕은 골짜기보다
    #    충분히 높지 않으면 그 골짜기는 독립 rep 이 아니라 한 rep 의 출렁임/멈칫이다.
    #    rise = peak - shallower_ang. 이게 (standing - shallower_ang)*0.4 미만이면 병합
    #    하고 각도가 더 작은(더 깊은) 쪽만 남긴다. (max 가 정확 — 더 얕은 골의 두드러짐)
    filtered: list[int] = []
    for idx in minima_idx:
        if not filtered:
            filtered.append(idx)
            continue
        prev = filtered[-1]
        peak = float(np.max(smoothed[prev:idx + 1]))
        shallower_ang = max(float(smoothed[prev]), float(smoothed[idx]))
        if peak - shallower_ang < (standing - shallower_ang) * 0.4:
            if smoothed[idx] < smoothed[prev]:
                filtered[-1] = idx
        else:
            filtered.append(idx)

    # 3) 각 bottom 양쪽에서 standing 80% 회복 지점 = down/up phase 경계.
    reps: list[tuple[int, int, int]] = []
    for j, bottom in enumerate(filtered):
        bottom_ang = float(smoothed[bottom])
        # 평평한 신호(standing≈bottom): recovery 가 bottom 과 거의 같아 while 루프가
        # 전체 영상 범위로 달려 tempo 가 수십 초로 부풀므로 해당 rep 을 skip (C-1).
        if standing - bottom_ang < 10.0:
            continue
        recovery = bottom_ang + (standing - bottom_ang) * 0.8
        # 탐색 경계를 인접 rep bottom 과의 '중간점' 으로 clamp → 연속 rep 의 down/up
        # 구간이 겹쳐 같은 회복 구간을 이중 카운트하던 문제 차단 (C-2).
        lo = (filtered[j - 1] + bottom) // 2 if j > 0 else 0
        hi = (bottom + filtered[j + 1]) // 2 if j < len(filtered) - 1 else n - 1
        # start: 뒤로 가며 recovery 이상으로 서 있던 마지막 지점 (down phase 시작)
        start = bottom
        while start > lo and smoothed[start] < recovery:
            start -= 1
        # end: 앞으로 가며 recovery 회복하는 첫 지점 (up phase 끝)
        end = bottom
        while end < hi and smoothed[end] < recovery:
            end += 1
        reps.append((start, bottom, end))
    return reps


# ---------------------------------------------------------------------------
# 메인 분석 함수
# ---------------------------------------------------------------------------

def analyze_video(video_path: str, exercise_type: str = "squat",
                  target_fps: float = 30.0) -> PoseAnalysis:
    """
    비디오 파일을 MediaPipe Tasks PoseLandmarker(VIDEO 모드)로 분석해 정량 메트릭 반환.
    Acceptance 목표: 30초 영상 분석 5초 이내 (CPU) — 실측 후 model/샘플링 조정 가능.

    target_fps: 이보다 높은 fps 영상은 stride 로 다운샘플해 inference 횟수를 줄인다
    (가장 비싼 단계인 detect_for_video 만 줄이고, rep 검출 정확도는 30fps 면 충분).
    """
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"비디오 파일을 찾을 수 없음: {video_path}")
    if not _MODEL_PATH.exists():
        raise FileNotFoundError(
            f"PoseLandmarker 모델 자산 없음: {_MODEL_PATH}\n"
            "  → curl 로 다운로드: "
            "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
            "pose_landmarker_full/float16/latest/pose_landmarker_full.task"
        )

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV가 비디오를 열지 못함: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0.0

    # 프레임 샘플링: 고fps(예: 59) 영상은 inference 비용이 2배 → target_fps 로 다운샘플.
    # stride 만큼 건너뛰며 처리. 인덱스 기반 window 계산엔 effective_fps 를 사용한다.
    stride = max(1, int(round(fps / target_fps))) if fps > target_fps else 1
    effective_fps = fps / stride

    # Tasks PoseLandmarker (VIDEO 모드 — 프레임 간 트래킹).
    options = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(_MODEL_PATH)),
        running_mode=RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    landmarker = None
    frames: list[FrameMetrics] = []
    frame_idx = 0
    miss_count = 0
    last_ts_ms = -1
    elapsed = 0.0

    try:
        # create_from_options 를 try 안에 두어 실패 시에도 finally 의 cap.release() 가
        # 실행되도록(리소스 누수 방지). landmarker=None 가드로 NameError 도 차단 (리뷰 #7).
        landmarker = vision.PoseLandmarker.create_from_options(options)
        start_time = time.perf_counter()
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                break
            # stride 샘플링 — inference 대상이 아닌 프레임은 디코딩만 하고 건너뜀
            # (디코딩은 inference 보다 훨씬 싸므로 detect_for_video 호출이 stride배 감소).
            if frame_idx % stride != 0:
                frame_idx += 1
                continue
            ts = frame_idx / fps
            # detect_for_video 는 timestamp 가 단조증가해야 함 → 중복 ms 방지로 +1 보정.
            ts_ms = int(round(ts * 1000))
            if ts_ms <= last_ts_ms:
                ts_ms = last_ts_ms + 1
            last_ts_ms = ts_ms

            # MediaPipe는 RGB 입력
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
            result = landmarker.detect_for_video(mp_image, ts_ms)

            if result.pose_landmarks:
                # pose_landmarks: List[List[NormalizedLandmark]] — 첫 번째 사람 사용
                frames.append(_process_frame(frame_idx, ts, result.pose_landmarks[0]))
            else:
                miss_count += 1
            frame_idx += 1
        elapsed = time.perf_counter() - start_time
    finally:
        cap.release()
        if landmarker is not None:
            landmarker.close()

    # ---- rep 추출 (visibility 가중 무릎 각도) ----
    # 측면 촬영에서 카메라 먼 쪽(가려진) 무릎이 depth 를 오염시키지 않도록 잘 보이는
    # 쪽에 가중을 둔다. 둘 다 잘 보이면(정면) 일반 평균에 수렴한다.
    knee_angles: list[float] = []
    for f in frames:
        parts = []  # (angle, weight=visibility)
        if f.knee_angle_left is not None:
            parts.append((f.knee_angle_left, f.knee_vis_left))
        if f.knee_angle_right is not None:
            parts.append((f.knee_angle_right, f.knee_vis_right))
        if not parts:
            knee_angles.append(180.0)
            continue
        wsum = sum(w for _, w in parts)
        if wsum > 1e-6:
            knee_angles.append(sum(a * w for a, w in parts) / wsum)
        else:
            knee_angles.append(float(np.mean([a for a, _ in parts])))

    rep_indices = _find_reps(knee_angles, fps=effective_fps)

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
        # 무릎 키포인트 한정 신뢰도: 좌우 모두 낮으면 depth(무릎 각도) 자체가 의심.
        # downstream(Gemini Stage 2)이 오염된 depth 를 그대로 신뢰하지 않도록 신호한다.
        low_knee = sum(
            1 for f in frames
            if max(f.knee_vis_left, f.knee_vis_right) < MIN_LANDMARK_VISIBILITY
        )
        if low_knee / len(frames) > 0.3:
            warnings.append(
                f"⚠️ {low_knee}/{len(frames)} 프레임에서 양쪽 무릎 visibility 낮음 "
                f"(< {MIN_LANDMARK_VISIBILITY}). depth(무릎 각도) 신뢰도 주의 — "
                f"피사체를 더 크게/가까이 잡고 하체 조명·노출 확인 권장."
            )
    # 미검출률 분모는 컨테이너 헤더값(total_frames)이 아니라 실제 read·처리된 프레임 수
    # (len(frames)+miss_count). 헤더값은 가변프레임/손상 mp4 에서 실측과 다를 수 있음 (리뷰 #4).
    processed_frames = len(frames) + miss_count
    if processed_frames > 0 and miss_count / processed_frames > 0.2:
        warnings.append(
            f"⚠️ {miss_count}/{processed_frames} 프레임에서 자세 미검출. 사람이 전신으로 보이는지 확인."
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
            "model": "mediapipe-tasks-pose-landmarker-full",
            "frames_analyzed": len(frames),
            "frames_missed": miss_count,
            "analysis_duration_sec": round(elapsed, 2),
            "fps": round(fps, 1),
            "effective_fps": round(effective_fps, 1),
            "frame_stride": stride,
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
    meta = payload["_metadata"]
    analysis_sec = meta["analysis_duration_sec"]
    duration = payload["duration_seconds"]
    eff_fps = meta.get("effective_fps", meta["fps"])
    stride = meta.get("frame_stride", 1)
    print("\n--- Self-check ---", file=sys.stderr)
    print(f"  영상 길이:   {duration:.1f}s", file=sys.stderr)
    print(f"  분석 시간:   {analysis_sec:.2f}s  (실측 {meta['fps']}fps → "
          f"effective {eff_fps}fps, stride {stride})", file=sys.stderr)
    print(f"  검출 rep:    {result.rep_count}", file=sys.stderr)
    # duration=0(손상 mp4/헤더 오류)이면 환산값이 0 이 되어 거짓 통과 판정이 나므로
    # Acceptance 판정 자체를 생략한다 (I-4).
    if duration <= 0:
        print("  ⚠️ 영상 길이 측정 불가(duration=0) — Acceptance 판정 생략. "
              "손상 mp4/헤더 오류 가능.", file=sys.stderr)
    else:
        # 30s 영상 환산 분석 시간 (현재 영상 길이와 무관하게 Acceptance 비교용)
        est_30s = (analysis_sec / duration) * 30.0
        print(f"  30s 환산:    {est_30s:.1f}s (Acceptance 목표 ≤5s)", file=sys.stderr)
        if est_30s <= 5.0:
            print("  ✅ Acceptance 통과 (30s 영상 5s 이내 환산)", file=sys.stderr)
        else:
            print("  ⚠️ Acceptance 미달. stride 샘플링은 이미 적용됨 → 추가 단축은 "
                  "lite 모델(pose_landmarker_lite.task) 전환 검토.", file=sys.stderr)

    for w in result.warnings:
        print(f"  {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
