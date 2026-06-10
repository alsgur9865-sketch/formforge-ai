# 파일 위치: ui/components/hero.py
"""랜딩 히어로 — DESIGN.md "Diagnostic Freeze-Frame" / FormForge Hero v2 이식.

순수 HTML 문자열 빌더(Streamlit 비의존, 테스트 가능). screen_upload()가 좌/우 컬럼에 주입.
CSS 는 ui/theme.py 의 ffh- 블록. 색/폰트 토큰은 DESIGN.md 단일 진실원과 일치.

구성:
- field_html        : 페이지 뒤 진단 그리드 배경(랜딩에서만 1회).
- topbar_html       : 브랜드 마크 + nav + ENGINE LIVE 펄스 펄.
- hero_intro_html   : kicker + h1(그라데이션 마침표) + lede. (위젯은 이 아래에 Streamlit 으로)
- hero_stats_html   : 정직한 3개 지표(거짓 정밀 회피 — 240fps/±1.4° 미사용).
- hero_capture_html : 우측 캡처 쇼케이스. 실제 스켈레톤 영상이 있으면 그걸 박고
                      (가짜 SVG 졸라맨 중복 금지), 없으면 SVG 일러스트로 graceful fallback.
"""
from __future__ import annotations

import html


def _esc(v) -> str:
    return html.escape(str(v if v is not None else ""))


def field_html() -> str:
    return '<div class="ffh-field"></div>'


def topbar_html() -> str:
    return (
        '<div class="ffh-topbar">'
        '<div class="ffh-brand"><span class="ffh-mark"></span>'
        '<span class="ffh-name">FORMFORGE</span></div>'
        '<nav class="ffh-nav">'
        '<a href="#">DIAGNOSTICS</a><a href="#">COACHES</a><a href="#">METHOD</a>'
        '<span class="ffh-pill"><span class="dot"></span>ENGINE LIVE</span>'
        '</nav></div>'
    )


def hero_intro_html() -> str:
    return (
        '<span class="ffh-kicker"><span class="bar"></span>'
        'MOVEMENT DIAGNOSTICS&nbsp;·&nbsp;<b>v2.4</b></span>'
        '<div class="ffh-h1">The argument<br>happens on<br>your body'
        '<span class="period"></span></div>'
        '<p class="ffh-body">Two AI coaches read the same rep and '
        '<strong>disagree on purpose.</strong> Frame-by-frame joint tracking turns '
        'every set into evidence — so the debate is settled by your skeleton, '
        'not your ego.</p>'
    )


def hero_stats_html() -> str:
    """정직한 지표만. CLAUDE.md '거짓 정밀 방지' — mock 의 ±1.4°/240fps 는 우리가
    보장하지 못하는 정밀 주장이라 제외. 대신 사실 + 차별화 + 실측 성과로."""
    stats = [
        ("33", "", "Tracked landmarks"),   # MediaPipe Pose 실제 keypoint 수
        ("2", "", "Adversarial coaches"),  # 차별화 핵심 (Encourager vs Scrutinizer)
        ("+28", "%", "Alignment lift"),    # 세션17 Phoenix Experiment 실측 0.62→0.795
    ]
    cells = ""
    for num, unit, lab in stats:
        u = f"<span>{_esc(unit)}</span>" if unit else ""
        cells += (
            f'<div class="ffh-stat"><div class="num">{_esc(num)}{u}</div>'
            f'<div class="lab">{_esc(lab)}</div></div>'
        )
    return f'<div class="ffh-stats">{cells}</div>'


# 가짜 SVG 스켈레톤 — 실제 영상이 없을 때만 쓰는 일러스트 fallback(§8 임상 톤).
_SVG_SKELETON = """
<svg class="ffh-overlay" viewBox="0 0 600 620" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
  <defs><filter id="ffh-node-glow" x="-120%" y="-120%" width="340%" height="340%">
    <feGaussianBlur stdDeviation="2.6" result="b"/>
    <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
  <g stroke="#9FB6CC" stroke-opacity="0.32" stroke-width="2" stroke-linecap="round">
    <line x1="252" y1="150" x2="402" y2="150"/></g>
  <g fill="#9FB6CC" fill-opacity="0.18" stroke="#9FB6CC" stroke-opacity="0.3" stroke-width="1.2">
    <rect x="244" y="132" width="11" height="36" rx="2"/><rect x="399" y="132" width="11" height="36" rx="2"/></g>
  <g stroke="#9FB6CC" stroke-opacity="0.3" stroke-width="2" stroke-linecap="round" fill="none">
    <line x1="322" y1="152" x2="330" y2="300"/><line x1="288" y1="158" x2="360" y2="156"/>
    <line x1="300" y1="300" x2="358" y2="302"/><line x1="330" y1="300" x2="300" y2="300"/>
    <line x1="330" y1="300" x2="358" y2="302"/><line x1="300" y1="300" x2="272" y2="412"/>
    <line x1="272" y1="412" x2="288" y2="524"/><circle cx="320" cy="112" r="26"/></g>
  <g stroke="#FF5C5C" stroke-opacity="0.9" stroke-width="2" stroke-linecap="round" fill="none" filter="url(#ffh-node-glow)">
    <line x1="358" y1="302" x2="330" y2="416"/><line x1="330" y1="416" x2="372" y2="524"/></g>
  <line x1="358" y1="302" x2="360" y2="416" stroke="#FF5C5C" stroke-opacity="0.35" stroke-width="1.5" stroke-dasharray="4 4"/>
  <g filter="url(#ffh-node-glow)"><g fill="#0B0E14" stroke="#34D1C4" stroke-width="1.8">
    <circle cx="288" cy="158" r="4.5"/><circle cx="360" cy="156" r="4.5"/><circle cx="300" cy="300" r="4.5"/>
    <circle cx="358" cy="302" r="4.5"/><circle cx="330" cy="300" r="4.5"/><circle cx="272" cy="412" r="4.5"/>
    <circle cx="288" cy="524" r="4.5"/><circle cx="372" cy="524" r="4.5"/></g></g>
  <g filter="url(#ffh-node-glow)">
    <circle cx="330" cy="416" r="11" fill="none" stroke="#FF5C5C" stroke-width="1.6">
      <animate attributeName="r" values="9;14;9" dur="2.6s" repeatCount="indefinite"/>
      <animate attributeName="stroke-opacity" values="0.9;0.2;0.9" dur="2.6s" repeatCount="indefinite"/></circle>
    <circle cx="330" cy="416" r="5" fill="#FF5C5C" stroke="#0B0E14" stroke-width="1.6"/></g>
</svg>"""


def hero_capture_html(image_url: str | None = None, video_url: str | None = None) -> str:
    """우측 캡처 쇼케이스. 우선순위(가장 정직·강력한 것부터):
      1) image_url — 우리 실제 진단 프리즈프레임(스켈레톤·실측각도 baked). 가짜 HUD 안 얹음.
      2) video_url — 움직이는 스켈레톤 영상 → 라이브 HUD(REC/플래그) 크롬.
      3) 둘 다 없음 — SVG 일러스트 fallback + HUD.
    코너틱·스캔·두 코치 카드는 항상. 필름스트립은 모드에 맞는 정직한 메타."""
    if image_url:
        media = f'<img src="{_esc(image_url)}" alt="diagnostic freeze-frame"/>'
        overlay = ""   # 프리즈프레임에 스켈레톤·각도가 이미 그려져 있음 — 중복 금지
        hud = ""        # baked 각도(DEPTH/LEAN)와 충돌하는 가짜 HUD 제거
        film = ('<b>SQUAT</b>&nbsp;·&nbsp;FRONT VIEW&nbsp;·&nbsp;5 REPS&nbsp;·&nbsp;'
                'DEPTH SWING 18–97°&nbsp;·&nbsp;FORM 60')   # 정면 데모 실측 요약
    else:
        if video_url:
            media = f'<video src="{_esc(video_url)}" autoplay loop muted playsinline></video>'
            overlay = ""   # 영상에 이미 스켈레톤 — 가짜 SVG 중복 금지
        else:
            media = ""
            overlay = " ".join(_SVG_SKELETON.split())  # 단일 라인화(마크다운 코드블록 오인 방지)
        hud = ('<div class="ffh-capmeta"><span class="rec">● REC</span>&nbsp;&nbsp;'
               'REP 03/05&nbsp;&nbsp;DEPTH <span class="pass">PASS</span></div>'
               '<div class="ffh-knee">R-KNEE VALGUS 14°</div>')
        film = ('<b>CAPTURE_0412.mov</b>&nbsp;·&nbsp;BACK SQUAT&nbsp;·&nbsp;3-QUARTER VIEW&nbsp;·&nbsp;'
                'L-KNEE 78°&nbsp;&nbsp;HIP 64°&nbsp;&nbsp;TEMPO 3·1·1')

    # ⚠️ Streamlit 마크다운은 "빈 줄 + 4칸 들여쓰기"를 코드블록으로 오인 → HTML 이 텍스트로 노출됨.
    #    빈 substitution 으로 빈 줄이 생기지 않게, 캡처는 줄바꿈/들여쓰기 없는 한 줄로 조립한다.
    ticks = ('<div class="ffh-ticks"><span class="tl"></span><span class="tr"></span>'
             '<span class="bl"></span><span class="br"></span></div>')
    frame_inner = (
        f'{media}<div class="ffh-scanlines"></div><div class="ffh-tint"></div>'
        f'{overlay}{ticks}<div class="ffh-scan"></div>{hud}'
    )
    enc_card = (
        '<div class="ffh-coach enc"><div class="top"><div class="av">E</div>'
        '<div class="who"><div class="nm">The Encourager</div>'
        '<div class="role">Certified PT</div></div></div>'
        '<div class="line">"Rep 3 you hit rock bottom — that <em>range is money.</em> '
        'Now nail the same depth every rep and this set is yours."</div>'
        '<span class="chip"><span class="d"></span>Own the depth</span></div>'
    )
    scr_card = (
        '<div class="ffh-coach scr"><div class="top"><div class="av">S</div>'
        '<div class="who"><div class="nm">The Scrutinizer</div>'
        '<div class="role">Physiologist, PhD</div></div></div>'
        '<div class="line">"Depth\'s a lottery — <em>18° then 97°.</em> '
        'Groove one depth before you load this, or the knees pay."</div>'
        '<span class="chip"><span class="d"></span>Gate the load</span></div>'
    )
    return (
        '<div class="ffh-capture">'
        f'<div class="ffh-frame">{frame_inner}</div>'
        f'{enc_card}{scr_card}'
        f'<div class="ffh-filmstrip">{film}</div>'
        '</div>'
    )
