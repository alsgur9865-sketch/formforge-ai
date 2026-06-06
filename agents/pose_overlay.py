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
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

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
