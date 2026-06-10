# 파일 위치: agents/pose_overlay.py
"""포즈 오버레이 렌더 — DESIGN.md §8 "Diagnostic Freeze-Frame" 프로덕션 스펙 (정직한 MVP).

실제 영상 rep-바닥 프레임 위에 트래킹 오버레이를 PIL로 그린다 (기본 MediaPipe 졸라맨 금지):
- 미세 뼈(연결선) + 블러 글로우 관절 노드 — 은은하게.
- 플래그된 관절만 빨강 하이라이트 — 크고 강하게.
- Geist Mono ttf 라벨(실측 각도만 — 가짜 정밀 금지) + 리더선.

순수 렌더 함수: 좌표·플래그·라벨을 받아 JPEG bytes 반환 (Streamlit/GCS 비의존, 테스트 가능).
플래그→관절/라벨 매핑은 호출자(pose_extractor)가 결정한다 (flags+metrics 를 보유하므로).
"""
from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ── 색 (RGB) — DESIGN.md §3/§8 토큰 ──
_BONE = (159, 182, 204)       # #9FB6CC  미세 연결선
_NODE_CORE = (216, 246, 244)  # #D8F6F4  관절 코어
_NODE_GLOW = (52, 209, 196)   # #34D1C4  노드 글로우
_RISK = (255, 92, 92)         # #FF5C5C  부상 위험 플래그
_GOOD = (61, 220, 132)        # #3DDC84  good 마커

_FONT_PATH = Path(__file__).resolve().parent.parent / "data" / "fonts" / "GeistMono.ttf"

# MediaPipe 33 키포인트 중 몸통/사지 뼈만 (얼굴 0-10 제외 — 진단엔 불필요).
_BONES = [
    (11, 12),                                           # 어깨
    (11, 13), (13, 15),                                 # 왼팔
    (12, 14), (14, 16),                                 # 오른팔
    (11, 23), (12, 24), (23, 24),                       # 몸통 + 골반
    (23, 25), (25, 27), (27, 29), (27, 31), (29, 31),   # 왼다리 + 발
    (24, 26), (26, 28), (28, 30), (28, 32), (30, 32),   # 오른다리 + 발
]
_NODES = [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]  # 노드 그릴 주요 관절
_MIN_VIS = 0.3  # 이보다 낮은 visibility 관절/뼈는 occlusion 으로 보고 생략


@dataclass
class OverlayLabel:
    """몸 위 라벨 1개."""
    anchor_idx: int           # 라벨을 붙일 관절 인덱스
    text: str                 # "DEPTH 92°" | "KNEE VALGUS (L)"
    kind: str = "risk"        # "risk"(빨강) | "good"(초록)


@lru_cache(maxsize=8)
def _font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(_FONT_PATH), max(8, size))
    except Exception:  # noqa: BLE001 — 폰트 없으면 기본(비트맵)으로 폴백
        return ImageFont.load_default()


def _disc(d: ImageDraw.ImageDraw, c: tuple[float, float], r: int, rgb: tuple[int, int, int], a: int) -> None:
    x, y = c
    d.ellipse([x - r, y - r, x + r, y + r], fill=(*rgb, a))


def _ring(d: ImageDraw.ImageDraw, c: tuple[float, float], r: int, rgb: tuple[int, int, int], a: int, width: int) -> None:
    x, y = c
    d.ellipse([x - r, y - r, x + r, y + r], outline=(*rgb, a), width=width)


def _vignette(w: int, h: int) -> Image.Image:
    """가장자리를 미세하게 어둡게 (중앙 밝은 타원 마스크 블러)."""
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse(
        [int(-w * 0.15), int(-h * 0.15), int(w * 1.15), int(h * 1.15)], fill=255
    )
    mask = mask.filter(ImageFilter.GaussianBlur(int(min(w, h) * 0.12)))
    dark = Image.new("RGBA", (w, h), (4, 6, 11, 0))
    dark.putalpha(mask.point(lambda p: int((255 - p) * 0.28)))  # 중앙 0 → 가장자리 ~28%
    return dark


def _draw_label(draw, anchor, text, rgb, font, w, h, scale) -> None:
    ax, ay = anchor
    pad = int(8 * scale)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    off = int(46 * scale)
    lx = ax - off - tw - 2 * pad if ax > w * 0.5 else ax + off  # 관절이 우측이면 라벨 좌측
    ly = ay - th // 2 - pad
    lx = max(pad, min(lx, w - tw - 2 * pad))
    ly = max(pad, min(ly, h - th - 2 * pad))
    bx0, by0 = lx, ly
    bx1, by1 = lx + tw + 2 * pad, ly + th + 2 * pad
    # 리더선: 관절 → 박스 중심
    draw.line([(ax, ay), ((bx0 + bx1) // 2, (by0 + by1) // 2)],
              fill=(*rgb, 170), width=max(1, int(1.4 * scale)))
    # 박스(어두운 플레이트 — convert("RGB") 시 불투명 처리되어 가독성 ↑)
    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=int(6 * scale),
                           fill=(11, 14, 20, 235), outline=(*rgb, 235),
                           width=max(1, int(1.4 * scale)))
    draw.text((bx0 + pad, by0 + pad - bbox[1]), text, font=font, fill=(*rgb, 255))


def render_keyframe_overlay(
    frame_bgr: np.ndarray,
    landmarks: list[tuple[float, float, float]],
    flagged_indices: list[int] | None = None,
    labels: list[OverlayLabel] | None = None,
    *,
    exercise: str = "",
    timecode: str = "",
    crop_pad: float | None = 0.12,
    max_long_side: int = 1080,
    jpeg_quality: int = 90,
    bg: str = "frame",  # "frame"=실제 프레임 위 | "black"=검정 배경(스켈레톤만)
) -> bytes:
    """rep-바닥 프레임(BGR np) + 정규화 33좌표 → 오버레이 JPEG bytes.

    landmarks: [(x, y, visibility), ...] 정규화(0..1). flagged_indices: 빨강 강조할 관절.
    """
    flagged = set(flagged_indices or [])
    labels = labels or []

    # BGR(np) → RGB → PIL (풀해상도). 정규화 좌표 기준 dims.
    rgb = np.ascontiguousarray(frame_bgr[:, :, ::-1])
    base = Image.fromarray(rgb).convert("RGBA")
    bw0, bh0 = base.size

    # 몸(가시 랜드마크) 바운딩박스로 크롭 — 히어로가 빈 배경에 묻히지 않게.
    ox = oy = 0.0
    if crop_pad is not None:
        xs = [x * bw0 for x, y, v in landmarks if v >= _MIN_VIS]
        ys = [y * bh0 for x, y, v in landmarks if v >= _MIN_VIS]
        if xs and ys:
            padx, pady = crop_pad * bw0, crop_pad * bh0
            x0 = max(0, int(min(xs) - padx)); x1 = min(bw0, int(max(xs) + padx))
            y0 = max(0, int(min(ys) - pady)); y1 = min(bh0, int(max(ys) + pady))
            if x1 - x0 > 20 and y1 - y0 > 20:
                base = base.crop((x0, y0, x1, y1))
                ox, oy = float(x0), float(y0)

    # 크롭 후 긴 변 max_long_side 로 다운스케일 (히어로는 ~500px 표시).
    rs = 1.0
    if max(base.size) > max_long_side:
        rs = max_long_side / max(base.size)
        base = base.resize((round(base.width * rs), round(base.height * rs)), Image.LANCZOS)

    w, h = base.size
    # bg="black": 실제 프레임 대신 검정 배경(스켈레톤만). 좌표·크기는 프레임 기준 그대로 유지.
    if bg == "black":
        base = Image.new("RGBA", (w, h), (8, 11, 17, 255))
    scale = h / 900.0  # 렌더 요소 크기 기준(세로 900px 기준)

    def px(idx: int) -> tuple[float, float] | None:
        if idx < 0 or idx >= len(landmarks):
            return None
        x, y, v = landmarks[idx]
        if v < _MIN_VIS:
            return None
        return ((x * bw0 - ox) * rs, (y * bh0 - oy) * rs)

    base = Image.alpha_composite(base, _vignette(w, h))

    # ── 글로우 레이어 (블러) ──
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for idx in _NODES:
        p = px(idx)
        if p and idx not in flagged:
            _disc(gd, p, int(9 * scale), _NODE_GLOW, 125)
    for idx in flagged:
        p = px(idx)
        if p:
            _disc(gd, p, int(15 * scale), _RISK, 150)
    glow = glow.filter(ImageFilter.GaussianBlur(max(1, int(5 * scale))))
    base = Image.alpha_composite(base, glow)

    # ── 뼈 + 코어 노드 레이어 ──
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    bw = max(2, int(round(2.6 * scale)))
    cw = bw + max(2, int(round(2 * scale)))  # 다크 케이싱 폭
    for a, b in _BONES:
        pa, pb = px(a), px(b)
        if pa and pb:
            od.line([pa, pb], fill=(8, 11, 17, 160), width=cw)   # 케이싱: 밝은 벽·어두운 옷 양쪽서 대비
            od.line([pa, pb], fill=(*_BONE, 210), width=bw)      # 밝은 뼈
    for idx in _NODES:
        p = px(idx)
        if p and idx not in flagged:
            _disc(od, p, max(4, int(6 * scale)), (8, 11, 17), 180)   # 노드 케이싱(코어보다 큰 다크 림)
            _disc(od, p, max(3, int(5 * scale)), _NODE_CORE, 250)
    for idx in flagged:
        p = px(idx)
        if p:
            _disc(od, p, max(4, int(7 * scale)), _RISK, 255)
            _ring(od, p, max(6, int(11 * scale)), _RISK, 220, width=max(2, int(2 * scale)))
    base = Image.alpha_composite(base, ov)

    # ── 라벨 + 좌하단 푸터 ──
    draw = ImageDraw.Draw(base)
    font = _font(int(round(22 * scale)))
    for lab in labels:
        p = px(lab.anchor_idx)
        if p:
            _draw_label(draw, p, lab.text, _RISK if lab.kind == "risk" else _GOOD, font, w, h, scale)

    foot = "  ·  ".join(s for s in (exercise.upper(), timecode) if s)
    if foot:
        draw.text((int(18 * scale), h - int(34 * scale)), foot,
                  font=_font(int(round(13 * scale))), fill=(138, 147, 166, 210))

    out = io.BytesIO()
    base.convert("RGB").save(out, format="JPEG", quality=jpeg_quality)
    return out.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 스켈레톤 영상 (움직이는 오버레이) — §8 "Living Diagnostic"
# 정지 프레임용 PIL 렌더(render_keyframe_overlay)와 달리 매 프레임 경량 cv2 드로잉.
# 원본 영상을 다시 읽으며 프레임별 좌표로 뼈+노드를 그려 H.264 mp4 로 인코딩한다.
# ─────────────────────────────────────────────────────────────────────────────

_BGR_BONE = (204, 182, 159)   # #9FB6CC 미세 연결선
_BGR_CORE = (244, 246, 216)   # #D8F6F4 관절 코어
_BGR_RISK = (92, 92, 255)     # #FF5C5C 부상 위험 플래그


def _even(n: int) -> int:
    """libx264 yuv420p 는 짝수 W/H 요구."""
    return n - (n % 2)


def _draw_skeleton_frame(
    img: np.ndarray,
    pts: dict[int, tuple[int, int]],
    flagged: set[int],
    scale: float,
) -> None:
    """크롭/리사이즈된 BGR 프레임 위에 뼈+노드를 그림 (in-place). 진짜 몸이 비치게 살짝 반투명."""
    overlay = img.copy()
    bw = max(2, int(round(2.6 * scale)))
    cw = bw + max(2, int(round(2 * scale)))
    for a, b in _BONES:
        pa, pb = pts.get(a), pts.get(b)
        if pa and pb:
            cv2.line(overlay, pa, pb, (8, 11, 17), cw, cv2.LINE_AA)   # 다크 케이싱
            cv2.line(overlay, pa, pb, _BGR_BONE, bw, cv2.LINE_AA)     # 밝은 뼈
    for idx in _NODES:
        p = pts.get(idx)
        if p and idx not in flagged:
            cv2.circle(overlay, p, max(4, int(6 * scale)), (8, 11, 17), -1, cv2.LINE_AA)
            cv2.circle(overlay, p, max(3, int(5 * scale)), _BGR_CORE, -1, cv2.LINE_AA)
    for idx in flagged:
        p = pts.get(idx)
        if p:
            cv2.circle(overlay, p, max(4, int(7 * scale)), _BGR_RISK, -1, cv2.LINE_AA)
            cv2.circle(overlay, p, max(7, int(11 * scale)), _BGR_RISK, max(2, int(2 * scale)), cv2.LINE_AA)
    cv2.addWeighted(overlay, 0.92, img, 0.08, 0, img)


# ── 프레임별 실측 각도 (몸 위에 baked — 프레임마다 변동, '살아있는' 측정) ──
#    DEPTH = 무릎 굴곡각(hip-knee-ankle). 분석(_process_frame)과 같은 _calc_angle 재사용
#    → 영상 숫자 = 분석 숫자 (단일 진실원, 중복·거짓정밀 0).
_HIP_L, _KNEE_L, _ANK_L = 23, 25, 27
_HIP_R, _KNEE_R, _ANK_R = 24, 26, 28
_SHO_L, _SHO_R = 11, 12


def _angle_label(img: np.ndarray, anchor: tuple[int, int], text: str, scale: float,
                 color: tuple[int, int, int] = _BGR_CORE,
                 placed: list[tuple[int, int, int, int]] | None = None) -> None:
    """관절 옆 각도 텍스트 — 다크 아웃라인 + 컬러로 영상 위 가독성(cv2, 프레임당 경량).
    cv2 Hershey 폰트는 '°'(U+00B0)를 못 그리므로(→'?'), 끝의 °는 떼어 작은 원으로 직접 그린다.
    placed: 이미 그려진 라벨 bbox 목록 — 겹치면 세로로 밀어 분리(측면 무릎·엉덩이 라벨 충돌 회피)."""
    deg = text.endswith("°")
    base = text[:-1] if deg else text
    fs = max(0.42, 0.6 * scale)
    th = max(1, int(round(1.3 * scale)))
    (tw, tht), _ = cv2.getTextSize(base, cv2.FONT_HERSHEY_DUPLEX, fs, th)
    rr = max(2, int(round(2.2 * scale)))             # ° 반지름
    rgap = max(2, int(round(3 * scale)))             # 숫자↔° 간격
    total_w = tw + (rgap + 2 * rr + 2 if deg else 0)
    ax, ay = anchor
    gap = int(16 * scale)
    tx = ax + gap if ax < img.shape[1] * 0.5 else ax - gap - total_w  # 관절 우측이면 라벨 좌측
    ty = ay + tht // 2
    tx = max(2, min(tx, img.shape[1] - total_w - 2))
    ty = max(tht + 2, min(ty, img.shape[0] - 2))
    # 겹침 회피: 이미 그려진 라벨과 충돌하면 ty 를 아래로 밀어 분리(가독성 — DEILEAN 깨짐 방지).
    if placed is not None:
        pad = max(2, int(round(3 * scale)))
        step = tht + 2 * pad
        for _ in range(6):
            box = (tx - pad, ty - tht - pad, tx + total_w + pad, ty + pad)
            if not any(box[0] < q[2] and q[0] < box[2] and box[1] < q[3] and q[1] < box[3] for q in placed):
                break
            ty = min(ty + step, img.shape[0] - 2)
        placed.append((tx - pad, ty - tht - pad, tx + total_w + pad, ty + pad))
    cv2.putText(img, base, (tx, ty), cv2.FONT_HERSHEY_DUPLEX, fs, (8, 11, 17), th + 3, cv2.LINE_AA)
    cv2.putText(img, base, (tx, ty), cv2.FONT_HERSHEY_DUPLEX, fs, color, th, cv2.LINE_AA)
    if deg:
        cx, cy = tx + tw + rgap + rr, ty - tht + rr  # 텍스트 상단 우측에 ° 원
        cv2.circle(img, (cx, cy), rr + 1, (8, 11, 17), -1, cv2.LINE_AA)         # 다크 배킹
        cv2.circle(img, (cx, cy), rr, color, max(1, int(round(1.2 * scale))), cv2.LINE_AA)


def _draw_frame_angles(img: np.ndarray, pts: dict[int, tuple[int, int]],
                       lm: list[tuple[float, float, float]], scale: float) -> None:
    """이 프레임의 정규화 좌표에서 무릎 굴곡각(DEPTH)을 실측해 무릎 옆에 그림.
    더 잘 보이는(visibility 높은) 다리를 선택. 가짜 임계값 색칠 없이 중립색(실측만)."""
    from agents.pose_mediapipe import _calc_angle  # 분석과 동일 각도식 재사용(이미 로드됨)

    def vec(i: int) -> tuple[np.ndarray, float] | None:
        if i < 0 or i >= len(lm):
            return None
        x, y, v = lm[i]
        return np.array([x, y], dtype=np.float64), v

    placed: list[tuple[int, int, int, int]] = []  # 그려진 라벨 bbox(겹침 회피 누적)
    kl, kr = vec(_KNEE_L), vec(_KNEE_R)
    if kl is None and kr is None:
        return
    left = (kr is None) or (kl is not None and kl[1] >= kr[1])
    hip_i, knee_i, ank_i = (_HIP_L, _KNEE_L, _ANK_L) if left else (_HIP_R, _KNEE_R, _ANK_R)
    hp, kn, an = vec(hip_i), vec(knee_i), vec(ank_i)
    if hp and kn and an and kn[1] >= _MIN_VIS and knee_i in pts:
        depth = _calc_angle(hp[0], kn[0], an[0])
        _angle_label(img, pts[knee_i], f"DEPTH {depth:.0f}°", scale, placed=placed)

    # LEAN = 척추(어깨중점→엉덩이중점) vs 수직. 분석 _back_angle_vs_vertical 과 동일 식(수치 일치).
    sl, sr, hl, hr = vec(_SHO_L), vec(_SHO_R), vec(_HIP_L), vec(_HIP_R)
    if sl and sr and hl and hr and _HIP_L in pts and _HIP_R in pts:
        spine = (sl[0] + sr[0]) / 2 - (hl[0] + hr[0]) / 2   # 엉덩이중점 → 어깨중점
        vert = np.array([0.0, -1.0])                        # 이미지 y는 아래로 증가 → 위는 -y
        cos = float(np.clip(np.dot(spine, vert) / (np.linalg.norm(spine) * np.linalg.norm(vert) + 1e-9), -1.0, 1.0))
        lean = float(np.degrees(np.arccos(cos)))
        hx = (pts[_HIP_L][0] + pts[_HIP_R][0]) // 2
        hy = (pts[_HIP_L][1] + pts[_HIP_R][1]) // 2
        _angle_label(img, (hx, hy), f"LEAN {lean:.0f}°", scale, placed=placed)


def render_skeleton_video(
    video_path: str,
    frame_landmarks: list[tuple[int, list[tuple[float, float, float]]]],
    flagged_indices: list[int] | None = None,
    *,
    out_fps: float = 30.0,
    max_long_side: int = 720,
    crop_pad: float = 0.08,
    bg: str = "frame",  # "frame"=원본 영상 위 | "black"=검정 배경(스켈레톤만)
) -> bytes:
    """원본 영상 + 프레임별 33좌표 → 스켈레톤이 몸을 따라 움직이는 H.264 mp4 bytes.

    frame_landmarks: [(frame_idx, [(x,y,vis)...])] — analyze_video(keep_frames=True) 산출.
    전체 영상 통합 bbox 로 고정 크롭(프레임마다 들썩이지 않게) + 긴 변 다운스케일.
    ffmpeg(libx264, yuv420p)로 인코딩 — 브라우저 <video> 호환.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg 가 PATH 에 없음 — 스켈레톤 영상 인코딩 불가.")
    flagged = set(flagged_indices or [])
    lm_by_idx = dict(frame_landmarks)
    if not lm_by_idx:
        raise ValueError("frame_landmarks 가 비어있음 (analyze_video(keep_frames=True) 필요).")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"OpenCV 가 영상을 열지 못함: {video_path}")
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # 통합 bbox(정규화) — 모든 가시 랜드마크 + 패딩. 영상 내내 몸이 프레임 안에 꽉 차게.
    xs = [x for lm in lm_by_idx.values() for x, y, v in lm if v >= _MIN_VIS]
    ys = [y for lm in lm_by_idx.values() for x, y, v in lm if v >= _MIN_VIS]
    if xs and ys:
        x0 = max(0, int((min(xs) - crop_pad) * W)); x1 = min(W, int((max(xs) + crop_pad) * W))
        y0 = max(0, int((min(ys) - crop_pad) * H)); y1 = min(H, int((max(ys) + crop_pad) * H))
    else:
        x0, y0, x1, y1 = 0, 0, W, H
    if x1 - x0 < 20 or y1 - y0 < 20:
        x0, y0, x1, y1 = 0, 0, W, H
    cw, ch = x1 - x0, y1 - y0

    rs = min(1.0, max_long_side / max(cw, ch))
    ow, oh = _even(max(2, int(cw * rs))), _even(max(2, int(ch * rs)))
    scale = oh / 900.0

    def transform(lm: list[tuple[float, float, float]]) -> dict[int, tuple[int, int]]:
        pts: dict[int, tuple[int, int]] = {}
        for i, (x, y, v) in enumerate(lm):
            if v >= _MIN_VIS:
                pts[i] = (int(round((x * W - x0) * ow / cw)), int(round((y * H - y0) * oh / ch)))
        return pts

    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()
    proc = subprocess.Popen(
        [ffmpeg, "-y", "-loglevel", "error",
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{ow}x{oh}", "-r", str(out_fps),
         "-i", "-", "-an", "-vcodec", "libx264", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", tmp.name],
        stdin=subprocess.PIPE,
    )
    try:
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            lm = lm_by_idx.get(idx)
            if lm is not None:
                if bg == "black":
                    crop = np.full((oh, ow, 3), (17, 11, 8), dtype=np.uint8)  # 검정 배경 BGR #080B11
                else:
                    crop = frame[y0:y1, x0:x1]
                    crop = cv2.resize(crop, (ow, oh), interpolation=cv2.INTER_AREA)
                pts = transform(lm)
                _draw_skeleton_frame(crop, pts, flagged, scale)
                _draw_frame_angles(crop, pts, lm, scale)  # 프레임별 실측 DEPTH 각도 baked
                proc.stdin.write(crop.tobytes())
            idx += 1
    finally:
        cap.release()
        proc.stdin.close()
        proc.wait()

    data = Path(tmp.name).read_bytes()
    Path(tmp.name).unlink(missing_ok=True)
    return data
