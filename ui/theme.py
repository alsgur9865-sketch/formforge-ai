# 파일 위치: ui/theme.py
"""디자인 토큰 + 폰트 + Streamlit 페이지 셸 — "Fight Card" UI 시스템의 단일 진실원천.

`ui/design_reference/README.md` 의 Design Tokens 섹션을 코드로 옮긴 것.
색/폰트 값은 절대 변경 금지(코치 아이덴티티). 각 템플릿은 자기 `:root` 를 인라인으로
들고 있지만(컴포넌트 iframe 격리 때문), 여기 TOKENS 는 파이썬 측(Streamlit 위젯 스타일,
계산용)에서 동일 값을 참조하기 위한 사본이다.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 디자인 토큰 (hex) — README "Design Tokens" 와 1:1
# ---------------------------------------------------------------------------

TOKENS: dict[str, str] = {
    # ink / surfaces
    "ink": "#111219",
    "ink_trace": "#0E0F16",
    "ink2": "#171922",
    "panel": "#1A1D28",
    "line": "#2A2D3A",
    "line2": "#373B4C",
    "hi": "#ECEAE2",
    "mid": "#9A988C",
    "dim": "#67655B",
    # coaches / accents (아이덴티티 — 변경 금지)
    "enc": "#37B36A",
    "enc_soft": "#8FE0B0",
    "scr": "#E8415C",
    "scr_soft": "#F79DAC",
    "gold": "#C9A24B",
    "gold2": "#E2C57A",
    "ember": "#E2672E",
    "slate": "#6E7486",
    # paper (scorecard / corner note)
    "bone": "#EAE3D2",
    "bone2": "#D8CFB8",
    "bone_ink": "#2A2519",
    "paper": "#ECE5D3",
}

# Google Fonts — Saira Condensed(헤드/이름) · Archivo(본문) · JetBrains Mono(라벨/데이터)
FONTS_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    "family=Saira+Condensed:wght@500;600;700;800;900"
    "&family=Archivo:wght@400;500;600;700;800"
    "&family=JetBrains+Mono:wght@400;500;700&display=swap\" rel=\"stylesheet\">"
)

# FormForge 마크 (struck spark / forge glyph) — stroke 색을 컨텍스트별로 교체
def mark_svg(stroke: str = "#111219", size: int = 14) -> str:
    """헤더 좌측 흰 라운드 사각형 안에 들어가는 forge 마크."""
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none">'
        f'<path d="M3 14l6-2 2-6 3 9 2-3 5 2" stroke="{stroke}" stroke-width="2.2" '
        f'stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )


# P5 의료 면책 — 모든 분석 화면 푸터 필수 (절대 원칙 P5)
DISCLAIMER_PRIMARY = "⚕ FOR INFORMATION ONLY — NOT MEDICAL ADVICE."
DISCLAIMER_CLAUSE2 = (
    "FORMFORGE ANALYZES MOVEMENT, NOT YOUR BODY. "
    "STOP AND CONSULT A PROFESSIONAL IF YOU FEEL PAIN."
)
# 한국어 면책 (Mediator/PoseExtractor 가 실제 출력하는 문구와 동일 톤)
DISCLAIMER_KO = "정보 제공용입니다. 의학적 조언이 아닙니다. 통증이나 부상이 있으면 전문가와 상담하세요."


# ---------------------------------------------------------------------------
# Streamlit 페이지 셸 — 1440px 고정폭 캔버스를 ink 배경에 레터박스 + 기본 chrome 숨김
# ---------------------------------------------------------------------------

def page_shell_css() -> str:
    """st.markdown(unsafe_allow_html=True) 로 주입. 디자인이 1440px 고정폭이라
    Streamlit 기본 패딩/헤더를 걷어내고 컴포넌트 iframe 을 ink 배경 위에 중앙 정렬한다."""
    ink = TOKENS["ink"]
    ink2 = TOKENS["ink2"]
    line2 = TOKENS["line2"]
    mid = TOKENS["mid"]
    gold = TOKENS["gold"]
    return f"""
<style>
  /* 전체 배경을 ink 로 (레터박스 느낌) */
  .stApp {{ background:{ink}; }}
  /* 기본 상단 헤더/툴바/푸터 숨김 */
  header[data-testid="stHeader"] {{ background:transparent; height:0; }}
  #MainMenu, footer, [data-testid="stToolbar"] {{ display:none; }}
  /* 사이드바 접힘 시 '펼치기(›)' 버튼이 height:0 헤더에 가려지지 않도록 강제 노출 */
  [data-testid="stSidebarCollapsedControl"],
  [data-testid="collapsedControl"] {{ display:flex !important; visibility:visible !important;
     position:fixed !important; top:8px; left:8px; z-index:100000; }}
  /* 메인 블록 패딩 최소화 + 확대된 캔버스 수용 (max-width 해제, 가로 스크롤 허용) */
  .block-container {{ padding:0.2rem 0.5rem 1rem; max-width:initial; }}
  section.main > div {{ padding-top:0; }}
  /* iframe(화면 캔버스) 중앙 정렬 — 좌우 여백 균등 레터박스 */
  .block-container iframe {{ display:block; margin:0 auto; }}
  /* 사이드바 톤을 디자인에 맞춤 */
  section[data-testid="stSidebar"] {{ background:{ink2}; border-right:1px solid {line2};
     transform:none !important; visibility:visible !important; margin-left:0 !important;
     min-width:248px !important; width:248px !important; overflow:visible !important; }}
  section[data-testid="stSidebar"] > div {{ width:248px !important; }}
  section[data-testid="stSidebar"] * {{ color:{mid}; }}
  section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2,
  section[data-testid="stSidebar"] h3 {{ color:{gold}; font-family:'Saira Condensed',sans-serif;
     text-transform:uppercase; letter-spacing:.14em; }}
  /* 인터랙션 위젯 컨테이너 톤 */
  div[data-testid="stExpander"] {{ border:1px solid {line2}; border-radius:6px; background:{ink2}; }}
</style>
{FONTS_LINK}
"""
