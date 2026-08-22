# -*- coding: utf-8 -*-
"""EJQI v3 채점 스키마.

파일럿(`EJQI_v3_파일럿_보고서.md`) 실측으로 확정된 구성이다.
항목 채택·폐기 근거는 각 주석의 §번호 참조.

폐기된 것
  D3 structure       천장 81~89%, 참조도 52% (§14.6)
  G4 concept_error   참조 코더도 300건 중 0건 (§12.4)
  QA 3콜 구조        길이·품질 통제 후 고유 기여 0.02 (§14.2)
  C1 직접평정(v1)     difficulty가 대체 (§14.7)
  info_density 등    v3 개정안 단계에서 이미 삭제

핵심 설계 결정
  · 이해 가능성(C)은 **단일 점수로 합치지 않는다**. difficulty와 effort는
    r=−0.30으로 반대 방향이며, 합치면 v1의 개념 혼동이 재발한다 (§15.1)
  · 모든 인용 필드는 본문 대조로 검증한다. 환각 1.5~2.5%가 이렇게 걸러진다
  · 단일 EJQI 점수는 산출하지 않는다. 3층 프로파일이 주 산출이다 (§10)
"""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

GENRES = ("시황", "스트레이트", "분석해설", "기획탐사", "논평")

EXPLAIN_LEVEL = {"없음": 0.0, "사전적": 0.5, "맥락번역": 0.85, "중요성설명": 1.0}

BLOCKER_TYPES = ("용어 미해설", "수치 기준 부재", "인과 생략",
                 "주체 불명", "전제 지식 요구", "문장 구조 복잡")

# 취재원 유형 — 파일럿 250건에서 '기타'가 21%로 나와 확장했다.
# 기타에 묻혀 있던 것: 협회·이익단체, 노동계, 시장조사·데이터업체, 정치권,
# 법조, 언론 인용, 익명 관계자. 특히 **자산운용·바이사이드**는
# I08("증권사 셀사이드에 편중, 바이사이드 목소리는 드물다")을 검증하려면 필수다.
SOURCE_TYPES = (
    "정부·공공",              # 부처, 청, 공공기관, 지자체, 한국은행
    "정치권",                # 국회의원, 정당, 외국 정상·각료
    "기업",                  # 사업회사 및 그 임직원
    "금융기관",              # 은행·보험·카드·저축은행
    "증권사·셀사이드",         # 증권사 리서치, 애널리스트
    "자산운용·바이사이드",      # 운용사, 연기금, PE/VC, IB 딜메이커
    "협회·이익단체",          # 무역협회, 상의, 업종협회, 포럼
    "노동계",                # 노동조합, 노동단체, 현장 근로자 대표
    "학계",                  # 교수, 대학
    "연구기관·데이터업체",      # 국책연구원, 민간연구소, 시장조사기관, 신평사
    "법조",                  # 법원, 검찰, 로펌, 변호사
    "시민·소비자",            # 개인 소비자·투자자·시민, 시민단체
    "언론·통신 인용",          # 블룸버그·닛케이 등 타 매체 보도 인용
    "국제·해외 기관",          # IMF, OECD, 외국 정부·중앙은행
    "익명 관계자",            # "업계 관계자", "정부 고위 관계자" 등 소속만 있는 익명
    "기타",
)

# 홍보성 유형 — 이진 플래그로는 27~31%가 뭉쳐 구분이 안 된다.
# 일단 전부 분류해두고 분석 단계에서 선택적으로 걸러낸다.
PROMO_TYPES = (
    "해당없음",
    "신제품·서비스 출시",
    "행사·전시·캠페인",
    "수상·인증·평가",
    "실적·성과 홍보",
    "협약·MOU·투자유치",
    "CSR·ESG 활동",
    "인사·조직 개편",
    "기타 홍보",
)

# (코드, 필드, 표시명, 차원) — 보고 순서
SCORED_ITEMS = [
    ("A1", "numeric_context",     "수치 맥락화",      "A"),
    ("A2", "causal_uncertainty",  "인과·불확실성",    "A"),
    ("A3", "verification",        "검증·반론",       "A"),
    ("A4", "impact_scope",        "영향 범위",       "A"),
    ("B3", "interest_disclosure", "이해관계 공시",    "B"),
    ("C1", "difficulty",          "이해 난이도",       "C"),
    ("C2", "effort",              "설명 노력",       "C"),
    ("C4", "scaffold_number",     "수치 체감화",      "C"),
    ("C5", "scaffold_case",       "사례·비유",       "C"),
    ("D1", "background",          "배경·시계열",      "D"),
    ("D2", "reader_implication",  "독자 함의",       "D"),
]

# 코드에서 산출되는 파생 지표 (LLM 직접 점수가 아님)
DERIVED_ITEMS = [
    ("C3", "term_explanation_rate", "용어 해설률", "C"),
]

DIM_NAMES = {"A": "분석 깊이", "B": "취재원·투명성",
             "C": "이해 가능성", "D": "맥락 충실성"}


class Item(BaseModel):
    """0–5 채점 항목. evidence → reasoning → score 순으로 채운다."""
    evidence: str = Field(description="본문 원문 인용. 해당 없으면 '없음'")
    reasoning: str = Field(description="판정 근거 40자 이내")
    score: int = Field(ge=0, le=5)


class Gate(BaseModel):
    """이진 게이트. flagged=True가 문제 있음."""
    flagged: bool
    evidence: str = Field(description="근거 원문 인용. 없으면 '없음'")


class Source(BaseModel):
    para: int = Field(
        description="이 취재원이 처음 등장한 문단 번호(P1이면 1). "
                    "취재원은 창 제한 없이 기사 전체에서 뽑되, 위치를 기록해 "
                    "사후에 창 안/밖을 구분할 수 있게 한다")
    name: str = Field(description="취재원 이름 또는 익명 서술(예: '업계 관계자')")
    transparent: bool = Field(description="실명+소속이 명시되면 true")
    econ_source_type: Literal[
        "정부·공공", "정치권", "기업", "금융기관", "증권사·셀사이드",
        "자산운용·바이사이드", "협회·이익단체", "노동계", "학계",
        "연구기관·데이터업체", "법조", "시민·소비자", "언론·통신 인용",
        "국제·해외 기관", "익명 관계자", "기타"]
    anonymity_reason: str = Field(
        description="익명일 때 기사가 밝힌 사유. 없거나 실명이면 '없음'")
    interest_disclosed: bool = Field(
        description="이 취재원의 이해관계가 기사에 드러나면 true")


class Term(BaseModel):
    """경제 전문용어 1개. para로 문단 순회를 강제한다(§16.3)."""
    para: int = Field(description="처음 등장한 문단 번호(P1이면 1)")
    term: str = Field(description="본문에 나온 그대로의 용어")
    first_sentence: str = Field(
        description="처음 등장한 문장을 본문에서 글자 그대로 인용")
    explained: Literal["없음", "사전적", "맥락번역", "중요성설명"]


class Blocker(BaseModel):
    """비전문가가 걸려 넘어지는 지점. 점수가 아니라 근거 산출물이다."""
    sentence: str = Field(description="막히는 문장을 본문에서 글자 그대로 인용")
    reason: Literal["용어 미해설", "수치 기준 부재", "인과 생략",
                    "주체 불명", "전제 지식 요구", "문장 구조 복잡"]
    note: str = Field(description="무엇이 막히는지 20자 이내")


class EJQIv3(BaseModel):
    """LLM 1회 호출로 채우는 전체 결과."""
    genre: Literal["시황", "스트레이트", "분석해설", "기획탐사", "논평"]
    genre_reason: str = Field(description="장르 판정 근거 30자 이내")

    # A. 분석 깊이
    numeric_context: Item
    causal_uncertainty: Item
    verification: Item
    impact_scope: Item

    # B. 취재원·투명성
    sources: List[Source]
    interest_disclosure: Item

    # C. 이해 가능성 — 합치지 말 것
    difficulty: Item                     # 순수 난이도(높을수록 쉬움). 품질과 독립
    effort: Item                         # 설명 노력
    effort_na: bool = Field(
        description="어려운 내용 자체가 없어 '설명 노력'을 평가할 수 없으면 true. "
                    "척도 적용 가능성 게이트를 겸한다")
    n_paragraphs_checked: int = Field(
        description="실제로 확인한 문단 수. 마지막 문단 번호와 같아야 한다")
    term_window_last: int = Field(
        description="용어 추출 대상 창의 마지막 문단 번호. 프롬프트가 지정한 값을 그대로 적는다")
    terms: List[Term]
    blockers: List[Blocker]
    scaffold_number: Item
    scaffold_case: Item

    # D. 맥락 충실성
    background: Item
    reader_implication: Item

    # 게이트
    headline_consistency: Gate           # G1
    sentiment_balance: Item              # G2 (0–5)
    promotional: Gate                    # G5
    promotional_type: Literal[
        "해당없음", "신제품·서비스 출시", "행사·전시·캠페인", "수상·인증·평가",
        "실적·성과 홍보", "협약·MOU·투자유치", "CSR·ESG 활동",
        "인사·조직 개편", "기타 홍보"] = Field(
        description="홍보성 유형. promotional=false여도 홍보 요소가 있으면 유형을 적는다")


class Article(BaseModel):
    """평가 입력."""
    body: str
    title: str = ""
    subtitle: str = ""
    press: str = ""
    topic: str = ""                      # 규준 비교군 키(sid2_name 등)
    article_id: Optional[str] = None
    # 수집 단계 변수(url·oid·sid·발행일·기자 등)를 그대로 결과 meta에 실어 보낸다.
    # 채점에는 쓰이지 않는다 — 분석 단계에서 원자료와 조인하기 위한 통로다.
    # 여기에 body를 넣지 마라. 결과 파일이 원자료를 이중 저장하게 된다
    # (본문은 merge_results.py가 원본 jsonl에서 붙인다).
    source_meta: Dict[str, Any] = Field(default_factory=dict)
