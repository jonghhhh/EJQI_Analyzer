# -*- coding: utf-8 -*-
"""EJQI v3 웹 배포판 설정.

연구 본편과 다른 점: API 키를 환경변수에서 읽지 않는다.
이용자가 화면에서 입력한 키를 호출 시점에 넘긴다.

★ 아래 상수를 바꾸면 본 연구 30,178건으로 만든 규준과 비교가 성립하지 않는다.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── 모델 ───────────────────────────────────────────────
# 재현성을 위해 -latest 별칭을 쓰지 않고 버전을 고정한다.
MODEL = "gemini-3.1-flash-lite"
TEMPERATURE = 0.0
MAX_OUTPUT_TOKENS = 12288
THINKING_BUDGET = 0

# ── 문단 분할 ──────────────────────────────────────────
# 네이버 본문은 수집 시 개행이 제거돼 100% 문장 묶음 경로를 탄다.
PARA_MIN = 120          # 이 길이 미만 조각은 앞 문단에 합친다
PARA_MAX = 400          # 이 길이를 넘는 조각은 글자 수로 강제 분할
TERM_CAP = 25
BLOCKER_CAP = 10

# ── 용어 추출 분석 창 ──────────────────────────────────
# 용어 추출은 기사 길이와 무관하게 4~7개에서 포화된다.
# → 분석 창을 고정해 모든 기사에 같은 분모를 준다.
TERM_WINDOW_CHARS = 1200

# ── 인용 검증 ──────────────────────────────────────────
QUOTE_MIN_LEN = 8
QUOTE_FUZZY_THRESHOLD = 0.85

# ── 경로 ───────────────────────────────────────────────
NORMS_PATH = ROOT / "data" / "norms_web.json"

# ── 규준 비교군 ────────────────────────────────────────
LEN_BINS = [("S", 0, 800), ("M", 800, 2000), ("L", 2000, 10 ** 9)]

MEDIA_TYPE = {
    "경제지": {"한국경제", "매일경제", "서울경제", "아시아경제", "파이낸셜뉴스",
               "헤럴드경제", "머니투데이", "이데일리", "조선비즈", "디지털타임스",
               "전자신문", "이코노미스트", "한국경제TV", "SBS Biz", "머니S",
               "비즈워치", "더벨", "아주경제", "브릿지경제", "메트로신문"},
    "통신": {"연합뉴스", "뉴시스", "뉴스1"},
    "종합지·방송": {"조선일보", "중앙일보", "동아일보", "한겨레", "경향신문",
                    "세계일보", "국민일보", "서울신문", "문화일보", "한국일보",
                    "KBS", "MBC", "SBS", "JTBC", "YTN", "MBN", "채널A", "TV조선",
                    "연합뉴스TV"},
}

# 포털 경제 섹션 세부분야 (sid2). 비교군 확장 및 리포트 표기에 쓴다.
TOPICS = ["경제 일반", "산업/재계", "증권", "금융", "부동산",
          "생활경제", "중기/벤처", "글로벌 경제", "기타"]

GENRES = ["시황", "스트레이트", "분석해설", "기획탐사", "논평"]


def media_type(press: str) -> str:
    for k, v in MEDIA_TYPE.items():
        if press in v:
            return k
    return "기타"


def len_bin(n: int) -> str:
    for name, lo, hi in LEN_BINS:
        if lo <= n < hi:
            return name
    return "L"


_WS = re.compile(r"\s+")


def norm_ws(s: str) -> str:
    return _WS.sub(" ", (s or "")).strip()
