# -*- coding: utf-8 -*-
"""EJQI Suite — 경제 뉴스 품질 자동 분석 시스템 + 경제 뉴스 데스크 챗봇(ENDC).

한 페이지에 두 서비스를 담는다.
  · 🔬 품질 분석 시스템 : 기사 1건을 EJQI 4차원 12항목으로 채점하고 3층으로 산출
  · 💬 데스크 챗봇 ENDC : EJQI 기준·전문가 인터뷰·코퍼스 실측을 근거로 조언

Gemini API 키는 이용자가 직접 입력한다. 서버에 저장하지 않는다.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import streamlit as st

from ejqi import __version__ as EJQI_VERSION
from ejqi import norms as _norms
from ejqi import report as rpt
from ejqi.config import MODEL, TERM_WINDOW_CHARS, TOPICS
from ejqi.evaluate import evaluate, paragraph_preview
from ejqi.llm import ApiKeyError, QuotaError, Usage, generate_text, make_client
from ejqi.schema import DIM_NAMES

ROOT = Path(__file__).resolve().parent
KEY_URL = "https://aistudio.google.com/app/apikey"

st.set_page_config(page_title="EJQI Suite — 경제 뉴스 품질 진단",
                   page_icon="📰", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
  .block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1180px;}
  h1, h2, h3 {letter-spacing: -0.02em;}
  .ejqi-hero {background: linear-gradient(100deg,#0f2542 0%,#1f4e79 60%,#2a6ba8 100%);
              color:#fff; padding: 1.5rem 1.8rem; border-radius: 14px; margin-bottom: 1.2rem;}
  .ejqi-hero h1 {color:#fff; margin:0 0 .35rem 0; font-size:1.75rem;}
  .ejqi-hero p  {color:#d7e5f5; margin:0; font-size:.94rem; line-height:1.6;}
  .pill {display:inline-block; padding:.16rem .6rem; border-radius:999px;
         background:rgba(255,255,255,.16); font-size:.78rem; margin-right:.35rem;}
  .card {border:1px solid #e3e8ef; border-radius:12px; padding:1rem 1.15rem; background:#fff;}
  .muted {color:#667085; font-size:.86rem;}
  .ev {background:#f6f8fb; border-left:3px solid #b9c8dc; padding:.5rem .75rem;
       border-radius:4px; font-size:.87rem; color:#334155; margin:.25rem 0 .1rem 0;}
  .rs {color:#7a8699; font-size:.82rem; margin:0 0 .5rem 0;}
  .gate {background:#fff4f4; border-left:3px solid #d05353; padding:.55rem .8rem;
         border-radius:4px; font-size:.88rem; margin:.3rem 0;}
  .warnbox {background:#fffaf0; border:1px solid #f0d9a8; border-radius:10px;
            padding:.85rem 1rem; font-size:.88rem; color:#6b5320;}
  div[data-testid="stMetricValue"] {font-size:1.5rem;}
  .stTabs [data-baseweb="tab"] {font-size:1rem; padding:.6rem 1.1rem;}
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════
# 공통 상태
# ══════════════════════════════════════════════════════════
ss = st.session_state
ss.setdefault("api_key", "")
ss.setdefault("result", None)
ss.setdefault("chat", [])
ss.setdefault("usage_total", {"calls": 0, "in": 0, "out": 0, "cost": 0.0})


@st.cache_data(show_spinner=False)
def load_knowledge() -> str:
    p = ROOT / "data" / "endc_knowledge.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def add_usage(u: Usage):
    t = ss["usage_total"]
    t["calls"] += u.calls; t["in"] += u.pin; t["out"] += u.pout; t["cost"] += u.cost_usd


def need_key() -> bool:
    if not ss["api_key"].strip():
        st.warning("왼쪽 사이드바에 **Gemini API 키**부터 넣을 것. "
                   "발급 방법은 사이드바의 안내를 펼치면 나옴.", icon="🔑")
        return True
    return False


# ══════════════════════════════════════════════════════════
# 사이드바 — API 키
# ══════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### 🔑 Gemini API 키")
    ss["api_key"] = st.text_input(
        "API 키", value=ss["api_key"], type="password",
        placeholder="AIza...", label_visibility="collapsed",
        help="입력한 키는 서버에 저장되지 않음. 브라우저 세션에만 남고 "
             "Google API 호출에만 쓰임.")
    if ss["api_key"].strip():
        st.success("키 입력됨 — 두 서비스 모두 사용 가능.", icon="✅")
    else:
        st.info("키를 넣어야 분석·대화 시작 가능함.", icon="ℹ️")

    with st.expander("🔎 API 키 받는 법 (무료)"):
        st.markdown(f"""
1. **[Google AI Studio 키 발급 페이지]({KEY_URL})** 로 이동
   `{KEY_URL}`
2. 구글 계정으로 로그인
3. **`Create API key`**(API 키 만들기) 버튼 클릭
4. 프로젝트를 고르라고 하면 아무 것이나 선택하거나 새로 생성
5. 만들어진 `AIza...` 로 시작하는 문자열을 복사해 위 칸에 붙여넣기

**참고**
- 무료 등급으로도 사용 가능. 단, 분당 요청 수에 제한이 있음
- 기사 1건 분석 비용은 **약 0.001달러(1~2원)** 수준
- 키는 **본인만 알 수 있게 보관**할 것. 공용 PC에서는 쓴 뒤 브라우저를 닫을 것
- 이 앱은 키를 저장·전송·기록하지 않음. 소스는 이 Space의 `Files` 탭에서 확인 가능
""")

    st.divider()
    st.markdown("### ⚙️ 실행 정보")
    st.caption(f"모델 **`{MODEL}`** (버전 고정)")
    st.caption(f"temperature 0 · 분석 창 {TERM_WINDOW_CHARS:,}자 · EJQI {EJQI_VERSION}")
    nm = _norms.load()
    if nm:
        st.caption(f"비교 기준표 **30,178건** 기반 · 비교군 {len(nm['cells'])}개")

    t = ss["usage_total"]
    if t["calls"]:
        st.divider()
        st.markdown("### 📊 이번 세션 사용량")
        c1, c2 = st.columns(2)
        c1.metric("호출", f"{t['calls']}회")
        c2.metric("추정 비용", f"${t['cost']:.4f}")
        st.caption(f"입력 {t['in']:,} · 출력 {t['out']:,} 토큰")

    st.divider()
    st.caption("한국언론진흥재단 연구과제 · 경제 뉴스 보도 현황과 전문성 향상 방안")


# ══════════════════════════════════════════════════════════
# 헤더
# ══════════════════════════════════════════════════════════
st.markdown("""
<div class="ejqi-hero">
  <h1>📰 EJQI Suite</h1>
  <p><b>경제 뉴스 품질 평가 지수(EJQI)</b> 기반 자동 분석 시스템과 데스크 챗봇.
  네이버 경제 섹션 <b>30,178건</b>(2024.07~2026.06)의 비교 기준표 위에서 작동함.</p>
  <p style="margin-top:.55rem;">
    <span class="pill">4차원 12항목</span>
    <span class="pill">단일 점수 없음 · 3층 산출</span>
    <span class="pill">인용 검증 내장</span>
    <span class="pill">전문가 인터뷰 11명 근거</span>
  </p>
</div>
""", unsafe_allow_html=True)

tab_intro, tab_ana, tab_chat = st.tabs(
    ["📖  안내 — 목적·구성·사용법", "🔬  품질 분석 시스템", "💬  데스크 챗봇 (ENDC)"])


# ══════════════════════════════════════════════════════════
# 탭 1. 안내
# ══════════════════════════════════════════════════════════
with tab_intro:
    st.markdown("## 1. 이 서비스는 무엇인가")
    st.markdown("""
- **경제 뉴스 한 건의 품질을 여러 각도로 진단하는 도구.** 두 개의 서비스로 구성됨
  - 🔬 **품질 분석 시스템** — 기사를 넣으면 12개 항목을 채점하고, **근거 문장**과
    비슷한 기사들 사이에서의 위치를 보여 줌
  - 💬 **데스크 챗봇(ENDC)** — 초고를 놓고 무엇을 어떻게 고칠지 대화로 조언함
- **어디에 쓰는가**
  - 기사 출고 전 자기 점검 / 데스크의 초고 검토 / 저널리즘 교육·연수 자료 / 매체·주제별 품질 모니터링
- **무엇을 근거로 만들었는가**
  - ① 선행 연구 → ② **경제 저널리스트·시장 전문가 11명 심층 인터뷰** →
    ③ **파일럿 300건 실측 검증** → ④ **본 측정 30,178건** 의 순서로 확정함
  - 이론적으로 그럴듯해도 실측에서 변별력이 없으면 버렸음. 텍스트 가독성 공식,
    질의응답식 이해도 측정, 기사 구성(structure) 항목이 그렇게 탈락함
""")

    st.markdown("## 2. EJQI의 구성 — 4차원 12항목")
    st.markdown("""
- 항목은 모두 **눈으로 확인 가능한 조건**으로 정의됨. "잘 썼다/못 썼다" 같은 인상 평가가 아님
- 모든 채점에 **본문 원문 인용**이 따라붙고, 그 인용이 실제로 본문에 있는지 코드로 대조함
  (전량 측정 기준, 지어낸 인용 비율 0.30%)
""")
    st.dataframe(pd.DataFrame([
        ["A 분석 깊이", "A1", "수치 맥락화", "0–5", "높을수록 좋음",
         "핵심 수치에 비교 기준선(전년·컨센서스·경쟁사)·시점·출처가 붙는가"],
        ["", "A2", "인과·불확실성", "0–5", "높을수록 좋음",
         "인과 메커니즘이 있고, 확인된 사실과 전망이 구분되는가"],
        ["", "A3", "검증·반론", "0–5", "높을수록 좋음",
         "발표·보도자료를 그대로 옮기지 않고 교차 확인하거나 반대 근거를 담는가"],
        ["", "A4", "영향 범위", "0–5", "높을수록 좋음",
         "영향받는 주체가 열거되고 시간 지평(단기/중장기)이 언급되는가"],
        ["B 취재원·투명성", "B3", "이해관계 공시", "0–5", "높을수록 좋음",
         "인용된 취재원이 어떤 이해관계에 서 있는지 독자가 알 수 있는가"],
        ["C 이해 가능성", "C1", "이해 난이도", "0–5", "⚠ 높을수록 **쉬움** (품질 아님)",
         "경제 지식이 없는 성인이 이 기사만 읽고 이해할 수 있는가"],
        ["", "C2", "설명 노력", "0–5", "높을수록 좋음",
         "어려운 내용이 실제로 있는데도 비전문가가 따라갈 수 있게 쓰였는가"],
        ["", "C3", "용어 해설률", "0–100", "높을수록 좋음",
         "전문용어 해설 수준의 가중 비율 (없음 0·사전적 0.5·맥락번역 0.85·중요성설명 1.0)"],
        ["", "C4", "수치 체감화", "0–5", "높을수록 좋음",
         "핵심 수치가 독자 체감으로 환산되는가 (절약액·부담액·1인당·월 단위)"],
        ["", "C5", "사례·비유", "0–5", "높을수록 좋음",
         "사례·비유·현장 목소리로 추상적 지표를 구체화하는가"],
        ["D 맥락 충실성", "D1", "배경·시계열", "0–5", "높을수록 좋음",
         "선행 맥락, 장기 추세, 사이클 안에서의 위치가 제시되는가"],
        ["", "D2", "독자 함의", "0–5", "높을수록 좋음",
         "이 정보가 왜 중요한지, 독자의 삶·자산·의사결정에 어떤 의미인지 설명되는가"],
    ], columns=["차원", "코드", "항목", "척도", "방향", "무엇을 보는가"]),
        use_container_width=True, hide_index=True)

    st.markdown("""
- **점검 표시 3종** — 점수에 넣지 않고 표시만 함
  - `제목 과장·왜곡` · `낙관·비관 균형(0–5)` · `홍보·광고성` + 홍보 유형 9분류
    (낙관·비관 균형은 5가 양쪽이 고르게 실린 상태, 0에 가까울수록 한쪽으로만 치우침)
- **목록 산출 3종** — 점수가 아니라 확인용 근거 자료임
  - **취재원** 16분류(증권사·셀사이드 ↔ 자산운용·바이사이드를 분리) ·
    **전문용어**와 해설 수준 · **비전문가가 막히는 문장** 6유형
""")

    st.markdown("## 3. 결과를 읽는 법 — 꼭 알아 둘 세 가지")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("""<div class="card">
<b>① 하나로 합친 총점은 없음</b><br><span class="muted">
12개 항목을 평균 내지 않음. 30,178건을 분석해 보니 <b>이해관계 공시</b>와 <b>이해 난이도</b>가
나머지 항목과 따로 노는 값이었기 때문임. 이 둘을 평균에 넣으면
<b>홍보성 단신 점수가 부풀려짐</b>.</span></div>""", unsafe_allow_html=True)
    with c2:
        st.markdown("""<div class="card">
<b>② 이해 난이도는 품질 점수가 아님</b><br><span class="muted">
높을수록 <b>'읽기 쉽다'</b>는 뜻일 뿐임. 실제로 <b>설명할 내용이 아예 없는 기사가 가장 쉬웠음</b>(4.94/5).
설명 노력(C2)과는 반대 방향으로 움직임(−0.28). 더하지 말고 나란히 놓고 읽을 것.</span></div>""",
                    unsafe_allow_html=True)
    with c3:
        st.markdown("""<div class="card">
<b>③ 점수 자체보다 '비슷한 기사 중 몇 등'</b><br><span class="muted">
기사가 길수록 점수가 올라가는 효과가 매체 유형 차이보다 <b>4배</b> 컸음. 그래서
<b>장르 × 길이대</b>로 나눈 16개 비교군 안에서의 백분위를 함께 보여 줌.</span></div>""", unsafe_allow_html=True)

    st.markdown("## 4. 사용법")
    cc1, cc2 = st.columns(2)
    with cc1:
        st.markdown("""
#### 🔬 품질 분석 시스템
1. 사이드바에 **Gemini API 키** 입력
2. `품질 분석 시스템` 탭으로 이동
3. **기사 본문** 붙여넣기 (400자 이상 권장)
4. 제목·부제·언론사·분야는 넣지 않아도 됨
   - **분야**를 고르면 리포트에 함께 표기됨
   - **장르**는 모형이 자동 판정하며, 비교군을 고르는 데만 쓰임
5. `분석 시작` 클릭 — **약 5~15초** 소요
6. 결과는 세 단계로 나옴
   - **1단계 항목별 진단 카드** — 항목별 등급과 **근거 문장**. 가장 중요한 산출물임
   - **2단계 비슷한 기사들 사이에서의 위치** — 장르·길이가 비슷한 기사 중 몇 등인지
   - **3단계 백분위 범위** — 차원별 중요도를 어떻게 배분해도 벗어나지 않는 백분위 구간
     (2단계와 같은 P○ 표기. 숫자가 클수록 상위)
7. 아래쪽 **취재원·전문용어·막히는 문장** 목록 확인 후 리포트 내려받기

> 💡 기사 1건의 항목 점수를 확정적으로 쓰려면 **3회 이상 반복 채점** 권장.
> 1회 채점만으로 같은 점수가 다시 나올 확률은 약 50%임.
""")
    with cc2:
        st.markdown("""
#### 💬 데스크 챗봇 (ENDC)
1. 사이드바에 **Gemini API 키** 입력
2. `데스크 챗봇` 탭으로 이동
3. 왼쪽에 **기사 초고**를 붙여넣으면 그 기사를 놓고 대화함 (붙여넣지 않아도 됨)
   - 분석을 먼저 돌렸다면 `분석 결과 함께 전달`을 켤 것. 훨씬 구체적으로 답함
4. 아래 입력창에 질문을 적거나 **빠른 질문** 버튼 클릭
   - 예 — "이 기사에서 가장 먼저 고쳐야 할 것은?", "취재원을 어떻게 보강할까"
5. 챗봇이 근거로 삼는 것
   - EJQI 12항목의 **정의와 점수 기준**
   - 전문가 **인터뷰 11명의 원문 발언**
   - **30,178건 실측 수치**

> 💡 챗봇은 "이렇게 써야 한다"고 강요하지 않음. **기자가 의도한 선택일 수 있음**을
> 전제로 선택지만 제시함. 전문가들이 지적한 '기사 획일화 위험'을 반영한 설계임.
""")

    st.markdown("## 5. 이 도구의 한계 — 반드시 읽을 것")
    st.markdown("""<div class="warnbox">
<b>순위를 매기거나 사람을 평가하는 장치가 아님.</b><br><br>
• <b>기사 1건의 점수는 확정적이지 않음.</b> 같은 기사를 다시 채점했을 때 항목 점수가
  그대로 나올 확률이 약 50%임. 매체·분야·시기 단위의 집합 비교에는 1회로 충분하나,
  <b>개인 평가·인사 고과 연동은 권장하지 않음.</b><br>
• <b>이해 가능성(C) 차원은 아직 타당성이 확립되지 않음.</b> 다른 조건을 통제했을 때
  뚜렷한 결과가 나온 것은 용어 해설률뿐임. 이 차원은 <b>참고용 수치로만</b> 읽을 것.<br>
• <b>사람 채점자와의 대조 검증이 아직 수행되지 않음.</b> 현재 결과는
  "LLM이 채점 규칙을 적용한 결과"임.<br>
• <b>제목 과장 점검은 잘 작동하지 않음.</b> 실제 발생률의 100분의 1 수준만 잡아냄.<br>
• <b>점수가 높다고 좋은 기사인 것은 아님.</b> 통념을 뒤집는 역발상 기사가 낮게 나올 수 있음.
</div>""", unsafe_allow_html=True)

    st.markdown("## 6. 개인정보와 데이터 처리")
    st.markdown("""
- 입력한 **API 키와 기사 본문은 이 서버에 저장되지 않음.** 브라우저 세션 메모리에만 남음
- 기사 본문은 채점을 위해 **Google Gemini API로만 전송**됨
- 외부 추적 서비스로의 전송은 코드 수준에서 차단돼 있음
- 브라우저를 닫거나 새로고침하면 입력 내용이 모두 사라짐
""")


# ══════════════════════════════════════════════════════════
# 탭 2. 품질 분석 시스템
# ══════════════════════════════════════════════════════════
DIM_COLOR = {"A": "#1f4e79", "B": "#c00000", "C": "#2e7d32", "D": "#e07b00"}


def render_result(r: dict):
    m = r.get("meta", {})
    dims = rpt.dim_scores(r)

    st.markdown("### 📋 요약")
    c = st.columns(6)
    c[0].metric("장르 (자동 판정)", r.get("genre", "–"))
    c[1].metric("본문 길이", f"{m.get('body_len', 0):,}자")
    c[2].metric("취재원", f"{r.get('n_sources', 0):g}명")
    c[3].metric("전문용어", f"{r.get('n_terms', 0):g}개")
    c[4].metric("막히는 문장", f"{r.get('n_blockers', 0):g}개")
    c[5].metric("반복 채점", f"{r.get('n_repeats', 1):g}회")
    st.caption(f"장르 판정 근거: {r.get('genre_reason', '')}")

    st.markdown("**4개 차원** — 소속 항목 평균 (0–5)")
    c = st.columns(4)
    dim_items = {"A": "A1~A4 평균", "C": "C2·C4·C5 평균", "D": "D1·D2 평균", "B": "B3 단일 항목"}
    for i, (d, label) in enumerate([("A", "A 분석 깊이"), ("C", "C 이해 가능성"),
                                    ("D", "D 맥락 충실성"), ("B", "B 취재원·투명성")]):
        v = dims.get(d)
        c[i].metric(label, "–" if v is None else f"{v:.2f}",
                    help=f"{DIM_NAMES.get(d, '')} 차원 평균 (0–5) = {dim_items[d]}. "
                         "차원 평균끼리 다시 더하지 말 것.")

    st.markdown("**차원 밖 단독 지표** — 어느 차원 평균에도 넣지 않음")
    c = st.columns(4)
    c[0].metric("C1 이해 난이도", f"{r.get('difficulty', 0):g}",
                help="0–5. ⚠ 높을수록 읽기 쉽다는 뜻. 품질 점수가 아니어서 C 차원 평균에 넣지 않음.")
    c[1].metric("C3 용어 해설률",
                "–" if r.get("term_explanation_rate") is None
                else f"{r['term_explanation_rate']:.0f}%",
                help="0–100. 척도가 달라 0–5 항목과 같은 평균에 섞지 않음. 3만 건 평균 13.5%.")
    st.caption("⚠ C1 이해 난이도와 C3 용어 해설률은 코드가 C로 시작하지만 "
               "**C 차원 평균에 넣지 않고 단독으로** 읽음 (C 차원 = C2·C4·C5). "
               "C2 설명 노력은 " + ("**평가 불가** — 어려운 내용 자체가 없음."
                                    if r.get("effort_na") else f"{r.get('effort', 0):g}점."))

    if r.get("effort_na"):
        st.info("이 기사는 **어려운 내용 자체가 없어 '설명 노력'을 평가할 수 없음.** "
                "행사 안내·인사·단순 홍보 기사가 여기 해당함. 0점은 감점이 아님. "
                "측정한 기사의 43.1%가 이 유형이었음.", icon="ℹ️")

    st.divider()

    # ── Layer 1 ───────────────────────────────────────────
    st.markdown("### 🩺 1단계 — 항목별 진단 카드")
    st.caption("점수보다 **등급과 근거 문장**이 핵심 산출물임. "
               "전문가 인터뷰에서 요구된 형태임 — “점수보다 근거가 중요합니다. "
               "어느 문장이 왜 감점인지 제시하고” (I08)")
    c1 = rpt.layer1(r)
    for it in c1["items"]:
        col = DIM_COLOR.get(it["dim"], "#555")
        cm = it["corpus_mean"]
        cmp_txt = ""
        if cm is not None and it["value"] is not None:
            diff = it["value"] - cm
            arrow = "▲" if diff > 0 else ("▼" if diff < 0 else "＝")
            unit = "%p" if it["key"] == "term_explanation_rate" else ""
            cmp_txt = (f'<span class="muted"> · 3만 건 평균 '
                       f'{cm:.2f}{"%" if it["key"] == "term_explanation_rate" else ""} '
                       f'{arrow}{abs(diff):.2f}{unit}</span>')
        st.markdown(
            f'<div style="margin:.45rem 0 .1rem 0;">'
            f'<span style="color:{col};font-weight:700;">{it["mark"]} {it["code"]}</span> '
            f'<b>{it["label"]}</b> · <b>{it["shown"]}</b> '
            f'<span style="color:{col};">{it["grade"]}</span>'
            f'{" — " + it["note"] if it["note"] else ""}{cmp_txt}</div>',
            unsafe_allow_html=True)
        if it["evidence"] and it["evidence"] not in ("없음", "해당없음", ""):
            st.markdown(f'<div class="ev">“{it["evidence"]}”</div>', unsafe_allow_html=True)
        if it["reasoning"]:
            st.markdown(f'<div class="rs">판정: {it["reasoning"]}</div>',
                        unsafe_allow_html=True)

    if c1["gates"]:
        st.markdown("#### ⚑ 게이트 발동")
        for name, e in c1["gates"]:
            st.markdown(f'<div class="gate"><b>{name}</b><br>{e}</div>',
                        unsafe_allow_html=True)
    gb = []
    if not r.get("headline_overstated", r.get("headline_consistency")):
        gb.append("G1 제목 과장·왜곡 없음")
    if not r.get("promotional"):
        gb.append("G5 홍보·광고성 아님")
    gb.append(f"G2 낙관·비관 균형 {r.get('sentiment_balance', '–')}/5 "
              "(5 = 낙관·비관 양쪽이 고르게 실림 · 0에 가까울수록 어느 한쪽으로만 치우침)")
    if r.get("promotional_type", "해당없음") != "해당없음":
        gb.append(f"홍보 유형: {r['promotional_type']}")
    st.caption(" · ".join(gb))

    if c1["flags"]:
        with st.expander(f"⚠ 신뢰도 참고 {len(c1['flags'])}건 — 사람이 직접 확인할 것"):
            for f in c1["flags"]:
                st.markdown(f"- {f}")

    st.divider()

    # ── Layer 2 ───────────────────────────────────────────
    st.markdown("### 📊 2단계 — 비슷한 기사들 사이에서의 위치")
    p2 = rpt.layer2(r, m.get("topic", ""))
    if not p2:
        st.info("비교 기준표 파일이 없어 백분위를 산출하지 못함.")
    else:
        st.caption(f"비교군 **{p2['cell']}** (n = {p2['n']:,}) · 가중치 개입 없음 · "
                   "본 연구 30,178건 기준")
        rows = []
        for row in p2["rows"]:
            if row["pct"] is None:
                rows.append({"코드": row["code"], "항목": row["label"], "값": "–",
                             "백분위": None, "위치": ""})
                continue
            pos = min(int(row["pct"] / 100 * 22), 21)
            bar = "·" * 22
            bar = bar[:pos] + "▲" + bar[pos + 1:]
            rows.append({"코드": row["code"], "항목": row["label"],
                         "값": row["shown"], "백분위": round(row["pct"]),
                         "위치": f"|{bar}|"})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
                     column_config={"백분위": st.column_config.ProgressColumn(
                         "비교군 내 백분위", min_value=0, max_value=100, format="P%d")})
        st.caption("⚠ C1 이해 난이도와 C3 용어 해설률은 위 표에 함께 실리지만 "
                   "**C 차원 평균에는 넣지 않는 단독 지표**임 (C 차원 = C2·C4·C5).\n\n"
                   "⚠ C1 이해 난이도와 C2 설명 노력은 서로 반대 방향으로 움직이는 값임(r = −0.28). "
                   "더하지 말고 나란히 놓고 읽을 것.")

    # ── Layer 3 ───────────────────────────────────────────
    st.markdown("### 🎚 3단계 — 가중치를 바꿔도 흔들리지 않는 백분위 범위")
    p3 = rpt.layer3(r)
    if not p3:
        st.info("차원 점수를 산출할 수 없어 이 단계를 건너뜀.")
    else:
        cc = st.columns([1, 1, 2])
        cc[0].metric("백분위 (평균)", f"P{p3['mean']:.0f}")
        cc[1].metric("흔들리는 폭", f"P{p3['lo']:.0f} – P{p3['hi']:.0f}")
        cc[2].caption(
            "**2단계와 같은 백분위 P○로 읽음 — 숫자가 클수록 상위임.** "
            "다른 점은 비교 상대뿐임. 2단계는 장르·길이가 비슷한 기사끼리, 여기는 **전체 기사**와 견줌.\n\n"
            f"차원별 중요도 배분을 **{p3['n_draw']:,}가지**로 바꿔 가며 낸, "
            f"전체 {p3['n_pop']:,}건 대비 백분위임. "
            "고정한 규칙은 A ≥ C ≥ D ≥ B라는 **순서** 하나뿐임 — "
            "전문가 인터뷰에서 합의된 것이 순서뿐이고, 'A 몇 %' 같은 비율은 근거가 없기 때문임. "
            "**어떤 배분을 쓰더라도 백분위가 대체로 이 폭 안에 들어옴.** "
            "폭이 좁으면 누가 봐도 평가가 비슷한 기사, 넓으면 보는 관점에 따라 갈리는 기사임.")

    st.divider()

    # ── 추출 산출물 ────────────────────────────────────────
    st.markdown("### 🔍 추출 산출물")
    t1, t2, t3, t4 = st.tabs(["취재원", "전문용어", "막히는 문장", "원자료(JSON)"])

    with t1:
        srcs = r.get("sources", [])
        if not srcs:
            st.info("이름·기관이 명시된 취재원이 없음. 이해관계 공시(B3) 해석에 주의할 것.")
        else:
            df = pd.DataFrame([{
                "문단": s.get("para"), "이름": s.get("name"),
                "유형": s.get("econ_source_type"),
                "실명·소속": "○" if s.get("transparent") else "✗(익명)",
                "이해관계 공시": "○" if s.get("interest_disclosed") else "✗",
                "익명 사유": s.get("anonymity_reason", "없음"),
            } for s in srcs])
            st.dataframe(df, use_container_width=True, hide_index=True)
            cc = st.columns(3)
            cc[0].metric("총 취재원", f"{r.get('n_sources', 0):g}명")
            cc[1].metric("실명·소속", f"{r.get('n_sources_named', 0):g}명")
            cc[2].metric("이해관계 공시", f"{r.get('n_sources_interest', 0):g}명")
            st.caption("※ 취재원은 **기사 전체**에서 셈(용어 분석 창과 무관). "
                       "반론·전문가는 기사 뒤쪽에 오는 일이 많아 창을 걸면 A3 판정이 왜곡됨.\n\n"
                       "비교 — 3만 건 평균은 기사당 2.77명, 실명률 77.7%, "
                       "익명 사유를 밝힌 취재원은 전체의 0.77%에 그쳤음.")

    with t2:
        terms = r.get("terms_detail") or []
        lv = r.get("term_levels", {})
        if lv:
            cc = st.columns(4)
            for i, k in enumerate(["없음", "사전적", "맥락번역", "중요성설명"]):
                cc[i].metric(k, f"{lv.get(k, 0)}개")
        if terms:
            LEVEL_MARK = {"없음": "✗ 없음", "사전적": "○ 사전적",
                          "맥락번역": "◐ 맥락번역", "중요성설명": "● 중요성설명"}
            st.dataframe(pd.DataFrame([{
                "문단": t["para"], "용어": t["term"],
                "설명 수준": LEVEL_MARK.get(t["explained"], t["explained"]),
                "처음 등장한 문장": t["first_sentence"],
            } for t in terms]), use_container_width=True, hide_index=True)
        elif not r.get("unexplained_terms"):
            st.info("분석 창 안에서 뽑힌 전문용어가 없음. 용어 해설률(C3)은 산출되지 않음.")
        if r.get("unexplained_terms"):
            st.markdown("**설명 없이 쓰인 용어 — 첫 등장 자리에 한 문장을 붙일 후보**")
            st.markdown("　" + " · ".join(f"`{t}`" for t in r["unexplained_terms"]))
        st.caption(
            f"분석 창: 앞 {TERM_WINDOW_CHARS:,}자를 목표로 문단 경계에서 절단 "
            f"(이 기사는 P1~P{r.get('term_window_last', '?')}, "
            f"{r.get('window_chars', 0):,}자 = 본문의 {r.get('window_ratio', 0):.0%}). "
            "창 밖 용어는 집계에서 제외됨.")
        st.caption("3만 건 측정 결과 — 전문용어의 **79.7%가 설명 없이 쓰였고**, "
                   "기사의 **50.3%는 해설률 0%**였음. "
                   "‘왜 중요한가’까지 설명한 사례는 **0.1%**에 그쳤음.")
        if r.get("n_terms_halluc"):
            st.caption(f"※ 검증에서 제외된 용어 {r['n_terms_halluc']:g}개 "
                       f"({', '.join(r.get('halluc_terms', [])[:8])})")

    with t3:
        bl = r.get("blockers", [])
        if not bl:
            st.success("비전문가가 걸려 넘어질 문장으로 지목된 곳이 없음.")
        else:
            for b in bl:
                st.markdown(f'<div class="ev"><b>[{b["reason"]}]</b> “{b["sentence"]}”</div>',
                            unsafe_allow_html=True)
                st.markdown(f'<div class="rs">→ {b["note"]}</div>', unsafe_allow_html=True)
        st.caption("3만 건 측정에서 독자가 막히는 대목의 **85.3%가 용어 미해설**이었고, "
                   "문장 구조가 복잡해서 막히는 경우는 **0.7%**뿐이었음. "
                   "문장을 짧게 쓰기보다 용어를 풀어 주는 편이 효과가 큼.")

    with t4:
        clean = {k: v for k, v in r.items() if not k.startswith("_")}
        st.json(clean, expanded=False)

    st.divider()
    d1, d2, d3 = st.columns(3)
    d1.download_button("📄 진단 리포트 (txt)", rpt.as_text(r).encode("utf-8"),
                       file_name="ejqi_report.txt", mime="text/plain",
                       use_container_width=True)
    d2.download_button("🗂 채점 원자료 (json)",
                       json.dumps(r, ensure_ascii=False, indent=1).encode("utf-8"),
                       file_name="ejqi_result.json", mime="application/json",
                       use_container_width=True)
    flat = {"genre": r.get("genre"), **{k: r.get(k) for _, k, _, _ in rpt.ALL_ITEMS},
            "dim_A": rpt.dim_scores(r)["A"], "dim_B": rpt.dim_scores(r)["B"],
            "dim_C": rpt.dim_scores(r)["C"], "dim_D": rpt.dim_scores(r)["D"],
            "effort_na": r.get("effort_na"), "promotional": r.get("promotional"),
            "promotional_type": r.get("promotional_type"),
            "headline_overstated": r.get("headline_overstated"),
            "sentiment_balance": r.get("sentiment_balance"),
            "n_sources": r.get("n_sources"), "n_terms": r.get("n_terms"),
            "n_blockers": r.get("n_blockers"), **m}
    flat.pop("usage", None)
    d3.download_button("📊 요약 행 (csv)",
                       pd.DataFrame([flat]).to_csv(index=False).encode("utf-8-sig"),
                       file_name="ejqi_row.csv", mime="text/csv",
                       use_container_width=True)


with tab_ana:
    st.markdown("## 🔬 경제 뉴스 품질 자동 분석")
    st.caption("기사 1건을 EJQI 4차원 12항목으로 채점해 3단계로 보여 줌. "
               "모든 채점에 본문 원문 인용이 따라붙고, 그 인용을 코드로 대조 검증함.")

    with st.form("ana_form"):
        c1, c2, c3, c4 = st.columns([2.2, 1.4, 1.2, 1.2])
        title = c1.text_input("제목", placeholder="기사 제목 (선택)")
        press = c2.text_input("언론사", placeholder="예: 한국경제 (선택)")
        topic = c3.selectbox("분야", ["(선택 안 함)"] + TOPICS, index=0,
                             help="포털 경제 섹션의 세부 분야. 리포트 표기에만 쓰임.")
        repeat = c4.selectbox("반복 채점", [1, 3, 5], index=0,
                              help="기사 1건의 항목 점수를 확정적으로 쓰려면 3회 이상 권장. "
                                   "1회만 채점하면 같은 점수가 다시 나올 확률이 약 50%임. "
                                   "반복 시 temperature 0.7이 적용되고 호출 비용도 그만큼 늘어남.")
        subtitle = st.text_input("부제", placeholder="부제 (선택)")
        body = st.text_area("기사 본문 *", height=260,
                            placeholder="기사 본문 붙여넣기. 400자 이상 권장.\n\n"
                                        "※ 제목·부제는 위 칸에 따로 넣을 것. "
                                        "제목이 본문에 섞이면 제목 과장 점검 결과가 왜곡됨.")
        cA, cB = st.columns([1, 3])
        submitted = cA.form_submit_button("🚀 분석 시작", use_container_width=True,
                                          type="primary")
        show_para = cB.checkbox("문단 분할·분석 창 미리보기 함께 보기", value=False)

    if body.strip() and show_para:
        pv = paragraph_preview(body)
        with st.expander(f"📐 문단 분할 미리보기 — {len(body):,}자 → {pv['n_paragraphs']}문단 · "
                         f"분석 창 P1~P{pv['term_window_last']} ({pv['window_chars']:,}자, "
                         f"본문의 {pv['window_ratio']:.0%})", expanded=True):
            st.caption("네이버 경제 기사 본문에는 줄바꿈이 없음(실측 36,334건 중 0건). "
                       "그래서 코드가 문장 3개씩 묶어 **약 200자 단위 블록**을 만듦. "
                       "원문 문단이 아님. 전문용어는 이 창 안에서만 추출함.")
            for p in pv["paragraphs"]:
                tag = "🟦 창 안" if p["in_window"] else "⬜ 창 밖"
                st.markdown(f"**[P{p['no']}]** {tag} · {p['len']}자")
                st.caption(p["text"][:220] + ("…" if len(p["text"]) > 220 else ""))

    if submitted:
        if need_key():
            st.stop()
        if len(body.strip()) < 100:
            st.error("본문이 너무 짧음. 100자 이상 입력할 것. (400자 이상 권장)")
            st.stop()
        if len(body) < 400:
            st.warning("본문이 400자 미만임. 연구의 채점 대상 기준(400자)에 미달하므로 "
                       "취재원·용어·문단 구조 평가가 불안정할 수 있음.", icon="⚠️")

        art = {"body": body.strip(), "title": title.strip(), "subtitle": subtitle.strip(),
               "press": press.strip(),
               "topic": "" if topic == "(선택 안 함)" else topic}
        prog = st.progress(0.0, text="채점 중…")
        t0 = time.time()
        try:
            def step(i, n):
                prog.progress(i / n, text=f"채점 중… {i}/{n}회 완료")

            with st.spinner("모형이 기사를 읽는 중…"):
                res = evaluate(ss["api_key"], art, repeat=int(repeat), on_step=step)
            prog.empty()
            u = Usage()
            uu = res["meta"]["usage"]
            u.calls, u.pin, u.pout = uu["calls"], uu["input_tokens"], uu["output_tokens"]
            add_usage(u)
            ss["result"] = res
            st.success(f"완료 — {time.time() - t0:.1f}초 · 호출 {uu['calls']}회 · "
                       f"추정 비용 ${res['meta']['cost_usd']:.4f}", icon="✅")
        except ApiKeyError as e:
            prog.empty(); st.error(f"🔑 {e}")
            st.stop()
        except QuotaError as e:
            prog.empty(); st.error(f"⏳ {e}")
            st.stop()
        except Exception as e:  # noqa: BLE001
            prog.empty(); st.error(f"분석 실패 — {str(e)[:400]}")
            st.stop()

    if ss["result"]:
        st.divider()
        render_result(ss["result"])
    else:
        st.info("본문을 넣고 **분석 시작**을 누를 것. "
                "결과는 항목별 진단 → 비슷한 기사 중 위치 → 백분위 범위의 순서로 나옴.", icon="👆")


# ══════════════════════════════════════════════════════════
# 탭 3. ENDC 챗봇
# ══════════════════════════════════════════════════════════
ENDC_SYSTEM = """당신은 **경제 뉴스 데스크 챗봇(ENDC, Economic News Desk Chatbot)**이다.
현직 경제 저널리스트가 기사 초고를 놓고 상의하는 상대다.

## 당신이 근거로 삼는 것
아래 [지식 베이스]는 ① EJQI 12개 항목의 조작적 정의와 앵커, ② 경제 저널리스트·시장 전문가
11명의 심층 인터뷰 원문, ③ 네이버 경제 섹션 30,178건 실측 결과이다.
조언은 반드시 이 자료에 근거해야 하며, 가능하면 출처를 함께 밝힌다
(예: "A3 검증·반론 앵커 기준으로", "I08은 …라고 했습니다", "코퍼스 30,178건에서 64.7%가 …").

## 답변 원칙
1. **점수가 아니라 문장을 지목한다.** "A3가 낮습니다"로 끝내지 말고, 어느 대목이 왜 그런지
   기사에서 인용하고 어떻게 고칠지 예시 문장을 제시한다.
2. **비용이 낮은 개선을 먼저 제안한다.** 순서는 ① 용어 첫 등장에 한 문장 ② 수치에 비교 기준선
   ③ 독자 함의 한 문단 ④ 반대 근거·교차 검증 ⑤ 추가 취재이다. 재취재가 필요한 조언은 뒤로 미룬다.
3. **평가 불가를 구분한다.** 인사·부고·행사 공지·단순 홍보물은 평가형 척도가 성립하지 않는다.
   이런 기사에 "품질이 낮다"고 말하지 않는다. 코퍼스의 43.1%가 이 유형이다.
4. **획일화를 경계한다.** 기자의 선택이 의도적일 수 있음을 인정한다. "이렇게 써야 합니다"가 아니라
   "이 항목이 비어 있는데, 의도한 것이라면 그대로 두어도 됩니다"라는 태도를 유지한다.
   전문가들은 "통념과 다른 역발상 기사가 오히려 낮은 점수를 받을 수 있다"(I08),
   "각 언론사의 개성과 기자의 스타일이 사라질 수 있다"(I09)고 경고했다.
5. **문장 길이를 줄이라는 조언은 하지 않는다.** 실측에서 독자가 막히는 지점의 85.3%가 용어이고
   문장 구조 복잡은 0.7%였다. 전문가들도 "읽기 귀찮게 생긴 것과 이해하기 어려운 것은 다른
   문제"(I11), "용어를 없앤다고 쉬운 기사가 되지 않는다"(I08)고 지적했다.
6. **단일 종합점수를 말하지 않는다.** EJQI는 차원별로 분리해 보고한다. 특히 이해 난이도(C1)는
   품질 지표가 아니며 높을수록 '쉽다'는 뜻일 뿐이다.
7. **모르는 것은 모른다고 한다.** 이해 가능성 차원의 타당도는 확립되지 않았고 인간 코더 검증도
   수행되지 않았다. 확정적으로 단정하지 않는다.

## 답변 형식
- 한국어로, **짧은 문장**으로 쓴다. 논문체가 아니라 데스크가 후배에게 말하듯 담백하게 쓴다.
- 항목 코드(A1·A3·C2·D2 등)를 함께 적어 어느 기준인지 알 수 있게 한다.
- 길어지면 **개조식**으로 정리한다. 표가 도움이 되면 표를 쓴다.
- 기사 초고가 주어졌으면 **그 기사의 실제 문장을 인용**해 말한다. 일반론으로 흐르지 않는다.
- 고쳐 쓴 예시를 제시할 때는 "원문 → 제안" 형태로 대비해 보여 준다.
- 답변 끝에 **"가장 먼저 할 것 한 가지"**를 한 줄로 못박는다.

[지식 베이스]
{knowledge}
"""

QUICK = [
    ("🎯 가장 먼저 고칠 것", "이 기사에서 가장 먼저 고쳐야 할 것 한 가지만 짚어 주세요. 왜 그것이 우선인지도 알려 주세요."),
    ("🔢 수치 맥락화", "본문의 핵심 수치에 비교 기준선이 붙어 있는지 점검하고, 없다면 어떤 기준을 붙이면 좋을지 예시 문장으로 제안해 주세요."),
    ("🔍 검증·반론", "이 기사가 단일 출처 받아쓰기에 가까운지 판단하고, 어떤 반대 근거나 독립 자료를 붙이면 좋을지 구체적으로 알려 주세요."),
    ("📖 용어 풀이", "비전문가가 막힐 만한 전문용어를 골라 주고, 각각 첫 등장 자리에 넣을 한 문장 설명을 만들어 주세요."),
    ("🙋 독자 함의", "이 기사가 독자의 삶·자산·의사결정에 어떤 의미인지 설명하고 있나요? 없다면 넣을 만한 한 문단을 제안해 주세요."),
    ("👥 취재원 보강", "취재원 구성을 평가하고, 어떤 유형의 취재원을 추가하면 좋을지 알려 주세요."),
    ("📰 제목 점검", "제목이 본문 내용·수치를 과장하거나 왜곡하지 않는지 점검해 주세요."),
    ("🧭 EJQI란?", "EJQI가 무엇이고 어떤 차원과 항목으로 구성되는지, 왜 단일 점수를 만들지 않는지 설명해 주세요."),
]


def build_endc_system() -> str:
    return ENDC_SYSTEM.format(knowledge=load_knowledge())


def build_context(draft: str, attach_result: bool) -> str:
    parts = []
    if draft.strip():
        parts.append(f"[검토 대상 기사 초고]\n{draft.strip()}")
    if attach_result and ss.get("result"):
        r = ss["result"]
        dims = rpt.dim_scores(r)
        lines = [f"장르 {r.get('genre')} · 본문 {r['meta'].get('body_len', 0):,}자",
                 f"차원 평균 — A 분석 깊이 {dims['A']} / C 이해 가능성 {dims['C']} / "
                 f"D 맥락 충실성 {dims['D']} / B 취재원·투명성 {dims['B']}",
                 "  ※ C 차원 평균 = C2·C4·C5. C1 이해 난이도와 C3 용어 해설률은 차원 밖 단독 지표임",
                 f"C1 이해 난이도 {r.get('difficulty')} (높을수록 쉬움) · "
                 f"C2 설명 노력 {'평가불가' if r.get('effort_na') else r.get('effort')} · "
                 f"C3 용어 해설률 {r.get('term_explanation_rate')}%",
                 "항목별 점수와 근거:"]
        for it in rpt.layer1(r)["items"]:
            lines.append(f"  {it['code']} {it['label']} = {it['shown']} ({it['grade']})"
                         + (f" | 근거: {it['evidence'][:80]}" if it["evidence"] else "")
                         + (f" | 판정: {it['reasoning'][:60]}" if it["reasoning"] else ""))
        if r.get("unexplained_terms"):
            lines.append("미해설 용어: " + ", ".join(r["unexplained_terms"][:20]))
        if r.get("blockers"):
            lines.append("막히는 지점:")
            for b in r["blockers"][:8]:
                lines.append(f"  [{b['reason']}] {b['sentence'][:90]} → {b['note']}")
        if r.get("sources"):
            lines.append("취재원: " + ", ".join(
                f"{s['name']}({s['econ_source_type']}"
                f"{',익명' if not s['transparent'] else ''})" for s in r["sources"][:15]))
        gates = []
        if r.get("headline_overstated"):
            gates.append("G1 제목 과장 발동")
        if r.get("promotional"):
            gates.append(f"G5 홍보성 발동({r.get('promotional_type')})")
        if gates:
            lines.append("게이트: " + " / ".join(gates))
        parts.append("[EJQI 분석 결과]\n" + "\n".join(lines))
    return "\n\n".join(parts)


with tab_chat:
    st.markdown("## 💬 경제 뉴스 데스크 챗봇 (ENDC)")
    st.caption("EJQI 12항목의 점수 기준, 전문가 인터뷰 11명의 원문 발언, 30,178건 실측을 "
               "근거로 조언함. '이렇게 써야 한다'고 강요하지 않고 선택지만 제시함.")

    left, right = st.columns([1, 1.6], gap="large")

    with left:
        st.markdown("#### 📝 검토 대상 (선택)")
        draft = st.text_area("기사 초고", height=280, key="endc_draft",
                             placeholder="초고를 붙여넣으면 그 기사를 놓고 대화 — 문장을 직접 인용해 답함.\n"
                                         "비워 두어도 됨. EJQI 기준이나 경제 저널리즘 일반에 "
                                         "대한 질문도 가능.")
        has_res = ss.get("result") is not None
        attach = st.checkbox("🔬 분석 결과 함께 전달", value=has_res, disabled=not has_res,
                             help="‘품질 분석 시스템’ 탭에서 분석을 먼저 돌려야 켜짐. "
                                  "항목별 점수·근거·미해설 용어·막히는 지점이 함께 전달돼 "
                                  "훨씬 구체적인 답이 나옴.")
        if not has_res:
            st.caption("※ `품질 분석 시스템` 탭에서 먼저 분석하면 그 결과를 함께 넘길 수 있음.")

        st.markdown("#### ⚡ 빠른 질문")
        qcols = st.columns(2)
        picked = None
        for i, (label, prompt) in enumerate(QUICK):
            if qcols[i % 2].button(label, use_container_width=True, key=f"q{i}"):
                picked = prompt

        st.divider()
        if st.button("🗑 대화 비우기", use_container_width=True):
            ss["chat"] = []
            st.rerun()

    with right:
        st.markdown("#### 💬 대화")
        box = st.container(height=430)
        with box:
            if not ss["chat"]:
                st.markdown(
                    '<div class="muted">경제 뉴스 데스크 챗봇 — 기사 초고를 놓고 상의하는 상대임.<br><br>'
                    '· 왼쪽에 초고를 붙여넣고 <b>빠른 질문</b> 버튼을 누르거나, 아래 칸에 직접 질문<br>'
                    '· EJQI 기준이 무엇인지, 특정 항목을 어떻게 채우는지도 질문 가능<br>'
                    '· 초고 없이 경제 저널리즘 일반에 대해 물어봐도 됨</div>',
                    unsafe_allow_html=True)
            for m in ss["chat"]:
                with st.chat_message("user" if m["role"] == "user" else "assistant",
                                     avatar="🧑‍💻" if m["role"] == "user" else "🗞"):
                    st.markdown(m["text"])

        typed = st.chat_input("무엇을 도와드릴까요? (예: 이 기사에서 가장 약한 부분은?)")

    user_msg = picked or typed
    if user_msg:
        if need_key():
            st.stop()
        ctx = build_context(draft, attach)
        payload = (f"{ctx}\n\n[질문]\n{user_msg}" if ctx else user_msg)
        ss["chat"].append({"role": "user", "text": user_msg, "payload": payload})

        hist = []
        for m in ss["chat"]:
            hist.append({"role": m["role"],
                         "text": m.get("payload") if m["role"] == "user" else m["text"]})
        try:
            with st.spinner("데스크가 읽는 중…"):
                u = Usage()
                cli = make_client(ss["api_key"])
                answer = generate_text(cli, build_endc_system(), hist,
                                       temperature=0.35, max_output_tokens=4096, usage=u)
            add_usage(u)
            ss["chat"].append({"role": "assistant", "text": answer})
        except ApiKeyError as e:
            ss["chat"].pop()
            st.error(f"🔑 {e}")
        except QuotaError as e:
            ss["chat"].pop()
            st.error(f"⏳ {e}")
        except Exception as e:  # noqa: BLE001
            ss["chat"].pop()
            st.error(f"응답 생성 실패 — {str(e)[:300]}")
        st.rerun()


# ══════════════════════════════════════════════════════════
st.divider()
st.caption(
    "EJQI Suite · 경제 뉴스 품질 평가 지수 v3 · 규준 30,178건(2024.07~2026.06) · "
    f"모델 `{MODEL}` · **하나로 합친 총점은 내지 않음.** "
    "점수가 높다고 좋은 기사인 것은 아니며, 개인 평가 용도로는 권장하지 않음."
)
