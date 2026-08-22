// Gemini 구조화 출력 스키마 (ejqi/schema.py 의 EJQIv3 와 동일)
//
// REST의 responseSchema 는 OpenAPI 하위 집합만 받는다. $ref 를 쓸 수 없으므로 펼쳐 쓴다.
// propertyOrdering 을 명시해 응답 필드 순서를 고정한다 — 순서가 흔들리면 품질이 떨어진다.

const ITEM = {
  type: "object",
  description: "0–5 채점 항목. evidence → reasoning → score 순으로 채운다.",
  properties: {
    evidence: { type: "string", description: "본문 원문 인용. 해당 없으면 '없음'" },
    reasoning: { type: "string", description: "판정 근거 40자 이내" },
    score: { type: "integer", description: "0–5" },
  },
  required: ["evidence", "reasoning", "score"],
  propertyOrdering: ["evidence", "reasoning", "score"],
};

const GATE = {
  type: "object",
  description: "이진 게이트. flagged=true 가 '문제 있음'",
  properties: {
    flagged: { type: "boolean" },
    evidence: { type: "string", description: "근거 원문 인용. 없으면 '없음'" },
  },
  required: ["flagged", "evidence"],
  propertyOrdering: ["flagged", "evidence"],
};

export const SOURCE_TYPES = [
  "정부·공공", "정치권", "기업", "금융기관", "증권사·셀사이드",
  "자산운용·바이사이드", "협회·이익단체", "노동계", "학계",
  "연구기관·데이터업체", "법조", "시민·소비자", "언론·통신 인용",
  "국제·해외 기관", "익명 관계자", "기타",
];

export const PROMO_TYPES = [
  "해당없음", "신제품·서비스 출시", "행사·전시·캠페인", "수상·인증·평가",
  "실적·성과 홍보", "협약·MOU·투자유치", "CSR·ESG 활동", "인사·조직 개편", "기타 홍보",
];

const SOURCE = {
  type: "object",
  properties: {
    para: { type: "integer", description: "이 취재원이 처음 등장한 문단 번호(P1이면 1)" },
    name: { type: "string", description: "취재원 이름 또는 익명 서술(예: '업계 관계자')" },
    transparent: { type: "boolean", description: "실명+소속이 명시되면 true" },
    econ_source_type: { type: "string", enum: SOURCE_TYPES },
    anonymity_reason: { type: "string", description: "익명일 때 기사가 밝힌 사유. 없거나 실명이면 '없음'" },
    interest_disclosed: { type: "boolean", description: "이 취재원의 이해관계가 기사에 드러나면 true" },
  },
  required: ["para", "name", "transparent", "econ_source_type",
             "anonymity_reason", "interest_disclosed"],
  propertyOrdering: ["para", "name", "transparent", "econ_source_type",
                     "anonymity_reason", "interest_disclosed"],
};

const TERM = {
  type: "object",
  properties: {
    para: { type: "integer", description: "처음 등장한 문단 번호(P1이면 1)" },
    term: { type: "string", description: "본문에 나온 그대로의 용어" },
    first_sentence: { type: "string", description: "처음 등장한 문장을 본문에서 글자 그대로 인용" },
    explained: { type: "string", enum: ["없음", "사전적", "맥락번역", "중요성설명"] },
  },
  required: ["para", "term", "first_sentence", "explained"],
  propertyOrdering: ["para", "term", "first_sentence", "explained"],
};

const BLOCKER = {
  type: "object",
  properties: {
    sentence: { type: "string", description: "막히는 문장을 본문에서 글자 그대로 인용" },
    reason: {
      type: "string",
      enum: ["용어 미해설", "수치 기준 부재", "인과 생략",
             "주체 불명", "전제 지식 요구", "문장 구조 복잡"],
    },
    note: { type: "string", description: "무엇이 막히는지 20자 이내" },
  },
  required: ["sentence", "reason", "note"],
  propertyOrdering: ["sentence", "reason", "note"],
};

const ORDER = [
  "genre", "genre_reason",
  "numeric_context", "causal_uncertainty", "verification", "impact_scope",
  "sources", "interest_disclosure",
  "difficulty", "effort", "effort_na",
  "n_paragraphs_checked", "term_window_last", "terms", "blockers",
  "scaffold_number", "scaffold_case",
  "background", "reader_implication",
  "headline_consistency", "sentiment_balance", "promotional", "promotional_type",
];

export const EJQI_SCHEMA = {
  type: "object",
  properties: {
    genre: { type: "string", enum: ["시황", "스트레이트", "분석해설", "기획탐사", "논평"] },
    genre_reason: { type: "string", description: "장르 판정 근거 30자 이내" },

    // A. 분석 깊이
    numeric_context: ITEM,
    causal_uncertainty: ITEM,
    verification: ITEM,
    impact_scope: ITEM,

    // B. 취재원·투명성
    sources: { type: "array", items: SOURCE },
    interest_disclosure: ITEM,

    // C. 이해 가능성 — 합치지 말 것
    difficulty: ITEM,
    effort: ITEM,
    effort_na: {
      type: "boolean",
      description: "어려운 내용 자체가 없어 '설명 노력'을 평가할 수 없으면 true. 척도 적용 가능성 게이트를 겸한다",
    },
    n_paragraphs_checked: {
      type: "integer",
      description: "실제로 확인한 문단 수. 마지막 문단 번호와 같아야 한다",
    },
    term_window_last: {
      type: "integer",
      description: "용어 추출 대상 창의 마지막 문단 번호. 프롬프트가 지정한 값을 그대로 적는다",
    },
    terms: { type: "array", items: TERM },
    blockers: { type: "array", items: BLOCKER },
    scaffold_number: ITEM,
    scaffold_case: ITEM,

    // D. 맥락 충실성
    background: ITEM,
    reader_implication: ITEM,

    // 게이트
    headline_consistency: GATE,
    sentiment_balance: ITEM,
    promotional: GATE,
    promotional_type: {
      type: "string", enum: PROMO_TYPES,
      description: "홍보성 유형. promotional=false여도 홍보 요소가 있으면 유형을 적는다",
    },
  },
  required: ORDER,
  propertyOrdering: ORDER,
};
