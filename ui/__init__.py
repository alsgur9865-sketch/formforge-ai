# 파일 위치: ui/__init__.py
"""FormForge AI — Streamlit "Fight Card" UI 패키지.

구성:
  - theme.py        : 디자인 토큰(색/폰트/spacing) + Streamlit 페이지 셸 CSS
  - render.py       : Jinja2 템플릿 렌더 + 파이프라인 출력 → 템플릿 컨텍스트 매핑
  - sample_state.py : 데모/폴백 상태 (라이브 데이터 없이도 6화면이 그대로 렌더)
  - templates/      : 디자인 핸드오프 6화면을 Jinja 템플릿으로 변환한 HTML
  - streamlit_app.py: 메인 앱 — 멀티페이지 + 1초 폴링 + 업로드/피드백 인터랙션
"""
