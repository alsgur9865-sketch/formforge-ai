# 파일 위치: ui/theme.py
"""DESIGN.md "The Diagnostic Freeze-Frame" 디자인 시스템을 Streamlit에 주입.

- 토큰(색·타이포·간격)은 DESIGN.md 단일 진실원과 일치.
- 컴포넌트 클래스는 모두 `ff-` 프리픽스(Streamlit 내부 클래스와 충돌 방지).
- 폰트: Cabinet Grotesk(Fontshare) / Geist · Geist Mono(Google Fonts) — CSS @import.
"""
from __future__ import annotations

import streamlit as st

# DESIGN.md §3 컬러 토큰 — CSS 변수로 단일 정의
_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap');
@import url('https://api.fontshare.com/v2/css?f[]=cabinet-grotesk@700,800&display=swap');

:root{
  --bg-base:#0B0E14; --bg-surface:#141A24; --bg-elevated:#1A2230;
  --hairline:#222C3A; --strong:#2E3A4D;
  --text:#E6EAF2; --muted:#8A93A6; --faint:#586073;
  --enc:#F4A340; --enc-glow:rgba(244,163,64,.16);
  --scr:#34D1C4; --scr-glow:rgba(52,209,196,.16);
  --risk:#FF5C5C; --risk-glow:rgba(255,92,92,.18);
  --good:#3DDC84; --good-glow:rgba(61,220,132,.16);
  --warning:#FFC24B;
  --vbg:#080B11;
}

/* ---- Streamlit chrome ---- */
.stApp{background:var(--bg-base)}
#MainMenu,header[data-testid="stHeader"],footer{visibility:hidden;height:0}
[data-testid="stToolbar"]{display:none}
.block-container{max-width:1320px;padding-top:1.6rem;padding-bottom:5rem}
section.main > div{gap:0}
[data-testid="stVerticalBlock"]{gap:.7rem}

/* base type */
html,body,[class*="css"]{font-family:'Geist',system-ui,sans-serif}
.ff *{box-sizing:border-box}
.ff-mono{font-family:'Geist Mono',monospace;font-variant-numeric:tabular-nums}
.ff-micro{font-size:11px;text-transform:uppercase;letter-spacing:.10em;color:var(--muted);font-weight:500}

/* ---- brand / hero ---- */
.ff-brand{display:flex;align-items:center;gap:12px;margin-bottom:4px}
.ff-brand .glyph{width:30px;height:30px;border-radius:8px;background:linear-gradient(135deg,var(--enc),var(--scr));display:grid;place-items:center;color:#0B0E14;font-family:'Cabinet Grotesk';font-weight:800;font-size:17px}
.ff-brand .wm{font-family:'Cabinet Grotesk';font-weight:800;font-size:18px;color:var(--text)}
.ff-brand .wm span{color:var(--muted)}
.ff-h1{font-family:'Cabinet Grotesk';font-weight:800;font-size:clamp(30px,4vw,46px);line-height:1.04;letter-spacing:-.03em;color:var(--text);margin:14px 0 10px}
.ff-h1 .g{background:linear-gradient(90deg,var(--enc),var(--scr));-webkit-background-clip:text;background-clip:text;color:transparent}
.ff-lede{font-size:16px;color:var(--muted);max-width:660px;line-height:1.5}

/* ---- tale of the tape ---- */
.ff-tape{display:flex;align-items:center;gap:18px;padding:15px 20px;border:1px solid var(--hairline);border-radius:12px;background:var(--bg-elevated);flex-wrap:wrap;margin-bottom:14px}
.ff-tape .ex{font-family:'Cabinet Grotesk';font-weight:800;font-size:19px;color:var(--text)}
.ff-tape .sub{color:var(--muted);font-size:12px;font-family:'Geist Mono';margin-top:2px}
.ff-tape .pill{margin-left:auto;font-family:'Geist Mono';font-size:12px;padding:5px 11px;border-radius:999px;border:1px solid var(--strong);color:var(--text)}
.ff-tape .tension{display:flex;align-items:center;gap:9px;font-family:'Geist Mono';font-size:11px;color:var(--warning)}
.ff-tbar{width:120px;height:6px;border-radius:999px;background:linear-gradient(90deg,var(--enc),#3a3f4d 46%,#3a3f4d 54%,var(--scr));position:relative}
.ff-tbar i{position:absolute;top:50%;width:3px;height:14px;background:var(--text);border-radius:2px;transform:translate(-50%,-50%);box-shadow:0 0 0 3px var(--bg-elevated)}

/* ---- diagnostic viewer (hero) ---- */
.ff-viewer{background:var(--vbg);border:1px solid #1d2530;border-radius:12px;position:relative;overflow:hidden;padding:0}
.ff-viewer video,.ff-viewer img{display:block;width:100%;height:auto;max-height:500px;object-fit:contain;background:#05070b}
.ff-viewer .vchrome{position:absolute;top:10px;left:12px;right:12px;display:flex;justify-content:space-between;font-family:'Geist Mono';font-size:10.5px;pointer-events:none;z-index:2}
.ff-viewer .vchrome .l{color:#7a8597;letter-spacing:.06em}
.ff-viewer .vchrome .r{color:var(--risk);display:flex;align-items:center;gap:6px}
.ff-viewer .vchrome .r b{width:7px;height:7px;border-radius:50%;background:var(--risk);display:inline-block}
.ff-viewer .vempty{aspect-ratio:16/11;display:grid;place-items:center;color:var(--faint);font-family:'Geist Mono';font-size:12px;background:repeating-linear-gradient(135deg,#0a0d13,#0a0d13 9px,#0c1017 9px,#0c1017 18px)}
.ff-readout{border:1px solid var(--hairline);border-top:none;border-radius:0 0 12px 12px;background:var(--bg-surface);padding:13px 15px;margin-top:-4px}
.ff-readout .row{display:flex;justify-content:space-between;align-items:baseline;font-family:'Geist Mono';font-size:12.5px;padding:4px 0}
.ff-readout .row .k{color:var(--muted)} .ff-readout .row .v{color:var(--text)}
.ff-score{font-family:'Cabinet Grotesk';font-weight:800;font-size:30px;line-height:1;color:var(--text)}
.ff-score small{font-family:'Geist Mono';font-size:12px;color:var(--muted);font-weight:400}
.ff-flags{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}

/* ---- badges (의미색) ---- */
.ff-badge{font-family:'Geist Mono';font-size:10.5px;padding:3px 8px;border-radius:6px;font-weight:500}
.ff-badge.risk{color:var(--risk);background:var(--risk-glow);border:1px solid color-mix(in srgb,var(--risk) 35%,transparent)}
.ff-badge.warning{color:var(--warning);background:color-mix(in srgb,var(--warning) 15%,transparent);border:1px solid color-mix(in srgb,var(--warning) 35%,transparent)}
.ff-badge.good{color:var(--good);background:var(--good-glow);border:1px solid color-mix(in srgb,var(--good) 35%,transparent)}

/* ---- debate feed ---- */
.ff-feed-head{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.ff-feed-head .t{font-family:'Cabinet Grotesk';font-weight:700;font-size:14px;color:var(--text)}
.ff-dot{width:7px;height:7px;border-radius:50%;background:var(--scr);box-shadow:0 0 0 4px var(--scr-glow)}
.ff-live{margin-left:auto;font-family:'Geist Mono';font-size:10px;color:var(--scr);background:var(--scr-glow);border:1px solid color-mix(in srgb,var(--scr) 35%,transparent);padding:3px 8px;border-radius:999px}
.ff-rounddiv{display:flex;align-items:center;gap:10px;margin:14px 0 10px}
.ff-rounddiv::before,.ff-rounddiv::after{content:"";flex:1;height:1px;background:var(--hairline)}
.ff-rounddiv span{font-family:'Geist Mono';font-size:10px;color:var(--faint);letter-spacing:.1em;white-space:nowrap}
.ff-msg{display:flex;gap:10px;margin-bottom:10px;animation:ffrise .2s ease-out}
@keyframes ffrise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.ff-msg .av{flex:none;width:30px;height:30px;border-radius:8px;display:grid;place-items:center;font-family:'Cabinet Grotesk';font-weight:800;font-size:13px;border:1px solid var(--hairline)}
.ff-msg.enc .av{background:color-mix(in srgb,var(--enc) 14%,transparent);color:var(--enc);border-color:color-mix(in srgb,var(--enc) 35%,transparent)}
.ff-msg.scr .av{background:color-mix(in srgb,var(--scr) 14%,transparent);color:var(--scr);border-color:color-mix(in srgb,var(--scr) 35%,transparent)}
.ff-msg .b{flex:1;min-width:0}
.ff-msg .nm{font-size:11px;font-family:'Geist Mono';color:var(--faint);margin-bottom:3px}
.ff-msg.enc .nm b{color:var(--enc)} .ff-msg.scr .nm b{color:var(--scr)}
.ff-bub{background:var(--bg-surface);border:1px solid var(--hairline);border-radius:9px;padding:10px 12px;font-size:13.5px;line-height:1.5;color:var(--text)}
.ff-msg.enc .ff-bub{border-left:2px solid var(--enc)}
.ff-msg.scr .ff-bub{border-left:2px solid var(--scr)}
.ff-bub .sub{color:var(--muted);font-size:12.5px;margin-top:4px}
.ff-chip{display:inline-flex;align-items:center;gap:5px;font-family:'Geist Mono';font-size:10px;padding:2px 7px;border-radius:5px;margin-top:7px}
.ff-chip.risk{color:var(--risk);background:var(--risk-glow)}
.ff-chip.good{color:var(--good);background:var(--good-glow)}

/* ---- mediator verdict ---- */
.ff-verdict{border-radius:12px;padding:1px;background:linear-gradient(90deg,var(--enc),var(--scr));margin:6px 0}
.ff-verdict-in{background:var(--bg-surface);border-radius:11px;padding:17px 19px}
.ff-verdict .vh{display:flex;align-items:center;gap:9px;margin-bottom:9px}
.ff-verdict .vh .lbl{font-family:'Cabinet Grotesk';font-weight:800;font-size:12px;letter-spacing:.12em;background:linear-gradient(90deg,var(--enc),var(--scr));-webkit-background-clip:text;background-clip:text;color:transparent}
.ff-verdict .vh .who{font-size:11px;color:var(--faint);font-family:'Geist Mono';margin-left:auto}
.ff-verdict p{font-size:14.5px;line-height:1.5;margin-bottom:12px;color:var(--text)}
.ff-checks{list-style:none;display:flex;flex-direction:column;gap:8px;margin:0 0 12px;padding:0}
.ff-checks li{display:flex;gap:9px;font-size:13.5px;align-items:flex-start;color:var(--text)}
.ff-checks .num{flex:none;width:18px;height:18px;border-radius:5px;background:var(--bg-elevated);border:1px solid var(--strong);display:grid;place-items:center;font-family:'Geist Mono';font-size:11px;color:var(--scr);margin-top:1px}
.ff-checks .rat{display:block;color:var(--muted);font-size:12px;margin-top:2px}
.ff-recall{font-family:'Geist Mono';font-size:11px;color:var(--scr);background:var(--scr-glow);border:1px solid color-mix(in srgb,var(--scr) 30%,transparent);border-radius:7px;padding:8px 10px;margin-bottom:12px}
.ff-disc{font-size:10.5px;color:var(--faint);line-height:1.45;border-top:1px solid var(--hairline);padding-top:10px}

/* ---- trace strip ---- */
.ff-trace{border:1px solid var(--hairline);border-radius:12px;background:var(--bg-elevated);padding:14px 18px;margin-top:14px}
.ff-trace-head{display:flex;align-items:center;gap:9px;margin-bottom:12px}
.ff-trace-head .t{font-family:'Cabinet Grotesk';font-weight:700;font-size:13px;color:var(--text)}
.ff-trace-head .src{font-family:'Geist Mono';font-size:10.5px;color:var(--faint);margin-left:auto}
.ff-span{display:grid;grid-template-columns:120px 1fr 56px;align-items:center;gap:12px;margin-bottom:8px;font-family:'Geist Mono';font-size:11.5px}
.ff-span .lab{color:var(--muted);white-space:nowrap}
.ff-track{position:relative;height:14px;background:color-mix(in srgb,var(--text) 5%,transparent);border-radius:5px}
.ff-track .bar{position:absolute;top:0;bottom:0;border-radius:5px;opacity:.92}
.ff-span .ms{text-align:right;color:var(--faint)}
.ff-tracelink{display:inline-block;margin-top:8px;font-family:'Geist Mono';font-size:11px;color:var(--scr);text-decoration:none;border:1px solid color-mix(in srgb,var(--scr) 30%,transparent);border-radius:7px;padding:6px 10px}

/* ---- persona drift ---- */
.ff-drift{font-family:'Geist Mono';font-size:11px;color:var(--muted);margin-top:8px}
.ff-drift b{color:var(--scr)}
.ff-driftbar{display:flex;align-items:center;gap:8px;margin:6px 0}
.ff-driftbar .name{width:104px;font-size:12px;color:var(--text)}
.ff-driftbar .meter{flex:1;height:6px;border-radius:999px;background:var(--bg-elevated);border:1px solid var(--hairline);position:relative;overflow:hidden}
.ff-driftbar .fill{position:absolute;top:0;bottom:0;left:0;border-radius:999px}
.ff-driftbar .val{width:42px;text-align:right;font-family:'Geist Mono';font-size:11px;color:var(--muted)}

/* ---- Streamlit widgets ---- */
.stButton>button{font-family:'Geist';font-weight:500;border-radius:8px;border:1px solid var(--strong);background:var(--bg-surface);color:var(--text);transition:.15s}
.stButton>button:hover{border-color:var(--text);color:var(--text)}
div[data-testid="stFileUploader"]{background:var(--bg-surface);border:1px dashed var(--strong);border-radius:12px;padding:6px}
.stSelectbox label,.stTextArea label,.stTextInput label{font-family:'Geist Mono';font-size:11px!important;text-transform:uppercase;letter-spacing:.08em;color:var(--muted)!important}
.stProgress > div > div > div{background:linear-gradient(90deg,var(--enc),var(--scr))}
</style>
"""


def apply_theme() -> None:
    """앱 최상단에서 1회 호출 — CSS 주입."""
    st.markdown(_CSS, unsafe_allow_html=True)


def page_config() -> None:
    """set_page_config — 반드시 첫 Streamlit 명령."""
    st.set_page_config(
        page_title="FormForge AI",
        page_icon="🏋️",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
