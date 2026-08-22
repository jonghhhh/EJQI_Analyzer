// EJQI v3 — 문단 분할 · 분석 창 · 인용 검증 · 파생 지표 · 규준 백분위
//
// 연구 본편(ejqi/verify.py, ejqi/norms.py)의 JS 포팅이다.
// **동작이 한 글자라도 달라지면 30,178건 규준과의 비교가 성립하지 않는다.**
// scripts/parity_test.py 로 파이썬 원본과의 일치를 검증한다.

// ── 상수 (ejqi/config.py 와 동일) ────────────────────────────
export const PARA_MIN = 120;              // 이 길이 미만 조각은 앞 문단에 합친다
export const PARA_MAX = 400;              // 이 길이를 넘는 조각은 글자 수로 강제 분할
export const TERM_WINDOW_CHARS = 1200;    // 용어 추출 창 목표 크기
export const TERM_CAP = 25;
export const BLOCKER_CAP = 10;
export const QUOTE_MIN_LEN = 8;
export const QUOTE_FUZZY_THRESHOLD = 0.85;
export const MODEL = "gemini-3.1-flash-lite";

export const EXPLAIN_LEVEL = { "없음": 0.0, "사전적": 0.5, "맥락번역": 0.85, "중요성설명": 1.0 };
export const BLOCKER_TYPES = ["용어 미해설", "수치 기준 부재", "인과 생략",
                              "주체 불명", "전제 지식 요구", "문장 구조 복잡"];

// (코드, 필드, 표시명, 차원) — 보고 순서
export const SCORED_ITEMS = [
  ["A1", "numeric_context",     "수치 맥락화",   "A"],
  ["A2", "causal_uncertainty",  "인과·불확실성", "A"],
  ["A3", "verification",        "검증·반론",     "A"],
  ["A4", "impact_scope",        "영향 범위",     "A"],
  ["B3", "interest_disclosure", "이해관계 공시", "B"],
  ["C1", "difficulty",          "이해 난이도",     "C"],
  ["C2", "effort",              "설명 노력",     "C"],
  ["C4", "scaffold_number",     "수치 체감화",   "C"],
  ["C5", "scaffold_case",       "사례·비유",     "C"],
  ["D1", "background",          "배경·시계열",   "D"],
  ["D2", "reader_implication",  "독자 함의",     "D"],
];
export const DERIVED_ITEMS = [["C3", "term_explanation_rate", "용어 해설률", "C"]];

const DIM_SEQ = { A: 0, B: 1, C: 2, D: 3 };
export const ALL_ITEMS = [...SCORED_ITEMS, ...DERIVED_ITEMS]
  .sort((x, y) => (DIM_SEQ[x[3]] - DIM_SEQ[y[3]]) || x[0].localeCompare(y[0]));

export const DIM_NAMES = { A: "분석 깊이", B: "취재원·투명성",
                           C: "이해 가능성", D: "맥락 충실성" };

// 차원별 항목 — C는 난이도(difficulty)를 제외한다.
// difficulty는 '쉬움'을 재므로 품질 합성에 넣으면 방향이 뒤집힌다.
export const DIMS = {
  A: ["numeric_context", "causal_uncertainty", "verification", "impact_scope"],
  B: ["interest_disclosure"],
  C: ["effort", "scaffold_number", "scaffold_case"],
  D: ["background", "reader_implication"],
};
export const DIM_ORDER = ["A", "C", "D", "B"];   // 인터뷰에서 방어 가능한 것은 이 서수뿐

export const TOPICS = ["경제 일반", "산업/재계", "증권", "금융", "부동산",
                       "생활경제", "중기/벤처", "글로벌 경제", "기타"];

// 본 연구 전량 30,178건의 참고 평균
export const CORPUS_MEAN = {
  numeric_context: 2.238, causal_uncertainty: 3.219, verification: 1.250,
  impact_scope: 2.551, interest_disclosure: 2.832, difficulty: 4.201,
  effort: 1.858, term_explanation_rate: 13.50, scaffold_number: 1.705,
  scaffold_case: 1.857, background: 2.536, reader_implication: 1.185,
};

export const ITEM_HELP = {
  numeric_context: "핵심 수치에 비교 기준선(전년 동기 수치·컨센서스·과거 시계열·경쟁 기업)과 시점·출처가 붙는가 · 0 숫자만 / 2 시점·출처만 / 4 비교 기준선 / 5 해석까지",
  causal_uncertainty: "원인 설명의 작동 원리가 있는가, 확인된 사실과 앞으로의 전망이 구분되는가 · 0 단정 / 2 메커니즘 없음 / 4 구분 명확 / 5 전제·불확실성까지",
  verification: "발표·보도자료를 그대로 옮기지 않고 따로 확인하거나 반대 근거를 담는가 · 0 받아쓰기 / 2 형식적 반론 한 줄 / 4 독립 자료·반대편 취재 / 5 전제까지 검증",
  impact_scope: "누가 영향을 받는지 열거되고 언제까지의 이야기인지(단기·중장기) 밝히는가 · 0 없음 / 2 주체 1개 / 4 복수 주체 / 5 시간 지평까지",
  interest_disclosure: "말한 사람이 어느 편에 서 있는지 독자가 알 수 있는가 · 0 소속도 불명 / 3 소속만 밝힘 / 5 이해관계와 방향까지 (취재원이 아예 없으면 0)",
  difficulty: "경제 지식이 거의 없는 성인이 이 기사만 읽고 이해 가능한가 · ⚠ 높을수록 쉽다는 뜻일 뿐 품질 점수가 아님. 내용이 단순해서(행사 안내·인사) 쉬운 경우도 5점",
  effort: "어려운 내용이 실제로 있는데도 비전문가가 따라갈 수 있게 풀어 썼는가 · 0 그대로 던짐 / 3 일부만 / 5 일관되게 풀어냄 (어려운 내용 자체가 없으면 ‘평가 불가’)",
  term_explanation_rate: "전문용어를 얼마나 풀어 줬는가 · 없음 0 · 사전적 0.5 · 맥락번역 0.85 · 중요성설명 1.0으로 가중 평균 (채점이 아니라 코드 계산 결과)",
  scaffold_number: "핵심 수치를 독자가 체감할 단위로 바꿔 주는가 · 0 없음 / 3 비율·배수 등 상대 표현 / 5 내 부담액·1인당·월 단위로 환산",
  scaffold_case: "사례·비유·현장 목소리로 추상적인 지표를 구체화하는가 · 0 없음 / 3 짧은 예시 1개 / 5 사례·비유가 논지를 지탱",
  background: "앞선 사정, 장기 흐름, 되풀이되는 경기 사이클 속 위치가 제시되는가 · 0 단발 사실만 / 3 배경 1~2문장 / 5 시계열·선행 사건 속에 배치",
  reader_implication: "이 정보가 왜 중요한지, 독자의 삶·자산·판단에 어떤 의미인지 설명되는가 · 0 없음 / 3 중요성 한 줄 / 5 무엇을 고려·대비할지까지 (투자 권유 여부가 아니라 의미 설명 여부가 기준)",
};

// ── 유틸 ────────────────────────────────────────────────────
/** 파이썬 re.sub(r"\s+", " ", s).strip() 과 동일 */
export function normWs(s) {
  return (s || "").replace(/\s+/g, " ").trim();
}
const cp = (s) => Array.from(s);          // 코드포인트 단위 배열 (파이썬 문자열 인덱싱과 일치)
const isSpace = (ch) => ch !== undefined && /\s/.test(ch);

/**
 * 파이썬 round() 재현 — 반올림이 아니라 **짝수 쪽으로 붙이는(banker's rounding)** 방식이다.
 * JS의 Math.round는 0.5를 항상 올리므로 그대로 쓰면 값이 어긋난다.
 * 실제로 용어 해설률에서 76.25 → 파이썬 76.2 / JS 76.3 으로 갈렸다.
 */
export function pyRound(x, digits = 0) {
  if (x === null || x === undefined || !isFinite(x)) return x;
  const f = Math.pow(10, digits);
  const y = x * f;
  const frac = y - Math.trunc(y);
  if (Math.abs(frac) === 0.5) {                 // 정확히 절반이면 짝수로
    const fl = Math.floor(y);
    return (fl % 2 === 0 ? fl : fl + 1) / f;
  }
  return Math.round(y) / f;
}

// ── difflib.SequenceMatcher.ratio() 재현 ─────────────────────
// isjunk=None, autojunk는 len(b) >= 200 에서만 발동한다.
// 이 코드가 쓰이는 곳은 b의 길이가 40이므로 junk 처리가 일어나지 않는다.
export function seqRatio(aStr, bStr) {
  const a = cp(aStr), b = cp(bStr);
  const la = a.length, lb = b.length;
  if (la + lb === 0) return 1.0;

  const b2j = new Map();
  for (let j = 0; j < lb; j++) {
    const k = b[j];
    if (!b2j.has(k)) b2j.set(k, []);
    b2j.get(k).push(j);
  }

  function findLongestMatch(alo, ahi, blo, bhi) {
    let besti = alo, bestj = blo, bestsize = 0;
    let j2len = new Map();
    for (let i = alo; i < ahi; i++) {
      const newj2len = new Map();
      const idxs = b2j.get(a[i]);
      if (idxs) {
        for (const j of idxs) {
          if (j < blo) continue;
          if (j >= bhi) break;
          const k = (j2len.get(j - 1) || 0) + 1;
          newj2len.set(j, k);
          if (k > bestsize) { besti = i - k + 1; bestj = j - k + 1; bestsize = k; }
        }
      }
      j2len = newj2len;
    }
    while (besti > alo && bestj > blo && a[besti - 1] === b[bestj - 1]) {
      besti--; bestj--; bestsize++;
    }
    while (besti + bestsize < ahi && bestj + bestsize < bhi
           && a[besti + bestsize] === b[bestj + bestsize]) {
      bestsize++;
    }
    return [besti, bestj, bestsize];
  }

  let matches = 0;
  const queue = [[0, la, 0, lb]];
  while (queue.length) {
    const [alo, ahi, blo, bhi] = queue.pop();
    const [i, j, k] = findLongestMatch(alo, ahi, blo, bhi);
    if (k) {
      matches += k;
      if (alo < i && blo < j) queue.push([alo, i, blo, j]);
      if (i + k < ahi && j + k < bhi) queue.push([i + k, ahi, j + k, bhi]);
    }
  }
  return (2.0 * matches) / (la + lb);
}

// ── 문장 분리 ────────────────────────────────────────────────
// 파이썬 원본: re.compile(r"(?<=다)[.。]\s+|(?<=[.!?])\s+")
// 자바스크립트 lookbehind는 구형 사파리에서 동작하지 않으므로 직접 스캔한다.
//
// 핵심 규칙은 **구두점 뒤에 공백이 있어야 한다**는 것이다.
// 그 덕분에 "전셋값은 0.14% 상승" · "약 1000평(3305.79㎡)" · '했다."고 말했다'가 쪼개지지 않는다.
// 첫 번째 규칙은 마침표를 소비하고(…있다. → …있다), 두 번째 규칙은 공백만 소비한다.
export function splitSentences(body) {
  const s = cp(body);
  const n = s.length;
  const out = [];
  let start = 0, i = 0;
  while (i < n) {
    let cut = -1;    // 앞 조각이 끝나는 위치 (배타적)
    let ws = -1;     // 공백 소비를 시작할 위치
    // 규칙 1: (?<=다)[.。]\s+   — 구두점까지 함께 소비한다 (…있다. → …있다)
    if (i >= 1 && s[i - 1] === "다" && (s[i] === "." || s[i] === "。") && isSpace(s[i + 1])) {
      cut = i; ws = i + 1;
    // 규칙 2: (?<=[.!?])\s+     — 공백만 소비한다 (구두점은 남는다)
    } else if ((s[i] === "." || s[i] === "!" || s[i] === "?") && isSpace(s[i + 1])) {
      cut = i + 1; ws = i + 1;
    }
    if (cut >= 0) {
      let e = ws;
      while (e < n && isSpace(s[e])) e++;      // \s+ 는 탐욕적
      out.push(s.slice(start, cut).join(""));
      start = e;
      i = e;
    } else {
      i++;
    }
  }
  out.push(s.slice(start).join(""));
  return out;
}

/**
 * 본문을 '의사 문단'으로 나눈다.
 *
 * ★ 이것은 원문 문단이 아니다. 네이버 경제 기사 본문에는 개행이 없다
 *   (실측 36,334건 중 0건). 코드가 문장 3개씩 묶어 약 200자 블록을 만든다.
 *   논문에 쓸 때는 "문단"이 아니라 "약 200자 단위 분석 블록"으로 기술해야 한다.
 */
export function splitParagraphs(body) {
  let parts = body.split(/\n+/).map((p) => p.trim()).filter((p) => p.length > 0);
  if (parts.length < 3) {                       // ① 개행이 부족하면 ②로
    const sents = splitSentences(body).filter((s) => s.trim().length > 0);
    parts = [];
    for (let i = 0; i < sents.length; i += 3) { // ② 문장 3개씩 묶음
      parts.push(sents.slice(i, i + 3).join(" "));
    }
  }
  const split = [];                             // ③ PARA_MAX 초과분은 글자 수로 강제 분할
  for (const p of parts) {
    const a = cp(p);
    if (a.length <= PARA_MAX) split.push(p);
    else for (let i = 0; i < a.length; i += PARA_MAX) split.push(a.slice(i, i + PARA_MAX).join(""));
  }
  const merged = [];                            // ④ PARA_MIN 미만은 앞 문단에 합친다
  for (const p of split) {
    if (merged.length && cp(merged[merged.length - 1]).length < PARA_MIN) {
      merged[merged.length - 1] += " " + p;
    } else merged.push(p);
  }
  return merged.length ? merged : [body];
}

export function numberParagraphs(paras) {
  return paras.map((p, i) => `[P${i + 1}] ${p}`).join("\n\n");
}

/**
 * 용어 추출 창 = 누적 글자수가 chars에 닿는 문단까지.
 * 문단 경계에서 끊으므로 실제 크기는 목표를 조금 넘거나 못 미친다.
 * 이 실제 값이 밀도의 분모다.
 *
 * 왜 문단 수가 아니라 글자 수인가: 문단 크기 편차가 커서 "앞 5문단"이
 * 기사마다 본문의 31~98%로 달라진다. 글자로 끊어야 분모가 고정된다.
 */
export function termWindow(paras, chars = TERM_WINDOW_CHARS) {
  let acc = 0;
  for (let i = 1; i <= paras.length; i++) {
    const nxt = acc + cp(paras[i - 1]).length;
    if (nxt >= chars) {
      // 목표에 더 가까운 쪽에서 끊는다 (초과 vs 미달)
      if (i > 1 && (nxt - chars) > (chars - acc)) return [i - 1, acc];
      return [i, nxt];
    }
    acc = nxt;
  }
  return [paras.length, acc];
}

// ── 인용 검증 ────────────────────────────────────────────────
/** 'exact' | 'fuzzy' | 'absent' | 'empty' */
export function quoteStatus(quote, bodyNorm, bodyArr) {
  const q = normWs(quote);
  if (!q || ["없음", "해당 없음", "해당없음"].includes(q) || cp(q).length < QUOTE_MIN_LEN) {
    return "empty";
  }
  if (bodyNorm.includes(q)) return "exact";
  const arr = bodyArr || cp(bodyNorm);
  const probe = cp(q).slice(0, 40).join("");
  const n = cp(probe).length;
  const limit = Math.max(arr.length - n, 0);
  for (let i = 0; i <= limit; i += 5) {
    if (seqRatio(probe, arr.slice(i, i + n).join("")) >= QUOTE_FUZZY_THRESHOLD) return "fuzzy";
  }
  return "absent";
}

/**
 * LLM 원 결과 + 본문 → 검증된 지표.
 *
 * 검증 실패 처리 원칙 (대상마다 다르다)
 *   evidence : 점수는 유지하되 상태를 'absent'로 표시 (신뢰도 플래그로만)
 *   terms    : **분모에서 제외**. 없는 용어로 해설률을 계산할 수 없다
 *   blockers : **제외**. 근거 산출물이므로 실재하지 않으면 쓸 수 없다
 */
export function verify(result, body, nPara, winLast, winChars) {
  const bodyNorm = normWs(body);
  const bodyArr = cp(bodyNorm);
  winChars = winChars || cp(body).length;
  winLast = winLast || nPara;
  const kilo = Math.max(winChars, 1) / 1000;

  const out = {
    genre: result.genre, genre_reason: result.genre_reason,
    term_window_last: winLast, window_chars: winChars,
    window_ratio: pyRound(winChars / Math.max(cp(body).length, 1), 3),
  };

  // 채점 항목 + evidence 검증
  let evAbsent = 0;
  for (const [, key] of SCORED_ITEMS) {
    const item = result[key];
    out[key] = item.score;
    const st = quoteStatus(item.evidence, bodyNorm, bodyArr);
    out[key + "__ev"] = st;
    if (st === "absent") evAbsent++;
  }
  out.evidence_absent = evAbsent;
  out.effort_na = !!result.effort_na;

  // 취재원 — **기사 전체**가 대상. 분석 창(앞 1,200자) 제한을 두지 않는다.
  //   연구보고서: 반론·전문가 취재원은 기사 뒤쪽에 배치되는 일이 잦아,
  //   창을 걸면 A3(검증·반론) 판정이 왜곡되기 때문임.
  //   ※ 취재원 밀도(1,000자당 명수)는 산출하지 않기로 확정됨(2026-08). 길이 교란이 남아
  //     지표로 쓸 수 없고, '창 안 명수'로 오독될 소지가 컸음.
  const srcs = result.sources || [];
  out.n_sources = srcs.length;
  out.n_sources_named = srcs.filter((s) => s.transparent).length;
  out.n_sources_interest = srcs.filter((s) => s.interest_disclosed).length;
  out.n_anon_reasoned = srcs.filter(
    (s) => !s.transparent && s.anonymity_reason && s.anonymity_reason !== "없음").length;
  out.n_sources_anon = srcs.filter((s) => !s.transparent).length;
  out.source_types = srcs.map((s) => s.econ_source_type);
  out.sources = srcs;

  // 용어 (검증 통과분만)
  const verified = [], halluc = [];
  for (const t of (result.terms || [])) {
    const termOk = !!normWs(t.term) && bodyNorm.includes(normWs(t.term));
    const sentOk = ["exact", "fuzzy"].includes(
      quoteStatus(t.first_sentence || "", bodyNorm, bodyArr));
    const paraOk = (t.para | 0) >= 1 && (t.para | 0) <= Math.max(winLast, 1);
    if (termOk && sentOk && paraOk) verified.push(t);
    else {
      // 제외 사유 셋은 함의가 전혀 다르다. 합치면 환각률이 5.8배 부풀려진다
      halluc.push([t.term, !termOk ? "본문에 없음" : (!sentOk ? "인용 문장 불일치" : "창 밖 문단")]);
    }
  }
  const lv = {};
  for (const k of Object.keys(EXPLAIN_LEVEL)) lv[k] = verified.filter((t) => t.explained === k).length;
  const nOk = verified.length;
  out.n_terms = nOk;
  out.n_terms_halluc = halluc.length;
  out.halluc_terms = halluc.map((h) => h[0]);
  out.halluc_reasons = {};
  for (const r of ["본문에 없음", "인용 문장 불일치", "창 밖 문단"]) {
    out.halluc_reasons[r] = halluc.filter((h) => h[1] === r).length;
  }
  out.term_levels = lv;
  out.n_terms_unexplained = lv["없음"];
  out.unexplained_terms = verified.filter((t) => t.explained === "없음").map((t) => t.term);
  out.terms_detail = verified.map((t) => ({
    para: t.para, term: t.term, explained: t.explained, first_sentence: t.first_sentence }));
  // C3 용어 해설률 — 가중 산식. 설명 여부의 단순 비율이 아니다
  // (연산 순서도 파이썬과 같아야 한다: sum / n * 100)
  out.term_explanation_rate = nOk
    ? pyRound((verified.reduce((a, t) => a + EXPLAIN_LEVEL[t.explained], 0) / nOk) * 100, 1)
    : null;
  // 밀도는 창 고정 후에도 길이 교란이 남아 점수로 쓰지 않는다
  out.term_density = pyRound(nOk / kilo, 2);
  out.para_coverage = nOk
    ? pyRound(new Set(verified.map((t) => t.para)).size / Math.max(winLast, 1), 2)
    : 0.0;

  // 막히는 지점 (검증 통과분만)
  const bl = (result.blockers || []).filter(
    (b) => ["exact", "fuzzy"].includes(quoteStatus(b.sentence || "", bodyNorm, bodyArr)));
  out.n_blockers = bl.length;
  out.n_blockers_halluc = (result.blockers || []).length - bl.length;
  out.blocker_types = {};
  for (const t of BLOCKER_TYPES) out.blocker_types[t] = bl.filter((b) => b.reason === t).length;
  out.blockers = bl.map((b) => ({ sentence: b.sentence, reason: b.reason, note: b.note }));

  // 게이트 — 저장되는 값은 flagged다. **true가 '문제 있음'**이다.
  for (const key of ["headline_consistency", "promotional"]) {
    out[key] = !!result[key].flagged;
    out[key + "__evidence"] = result[key].evidence;
  }
  out.headline_overstated = out.headline_consistency;
  out.headline_overstated__evidence = out.headline_consistency__evidence;
  out.sentiment_balance = result.sentiment_balance.score;
  out.sentiment_balance__ev = quoteStatus(result.sentiment_balance.evidence, bodyNorm, bodyArr);

  // 근거 텍스트 보존 (진단 카드용)
  out._evidence = {};
  for (const [, key] of SCORED_ITEMS) {
    out._evidence[key] = { evidence: result[key].evidence, reasoning: result[key].reasoning };
  }
  out.n_paragraphs = nPara;
  out.n_paragraphs_claimed = result.n_paragraphs_checked | 0;
  out.promotional_type = result.promotional_type || "해당없음";
  return out;
}

/** 인간 검수를 권하는 신호 */
export function reliabilityFlags(s) {
  const f = [];
  if (s.evidence_absent >= 2)
    f.push(`근거로 제시된 인용 ${s.evidence_absent}건이 본문에서 확인되지 않음 — 모델이 지어냈을 가능성`);
  if (s.n_terms_halluc > 0)
    f.push(`전문용어 ${s.n_terms_halluc}개가 본문에 없거나 분석 창 밖에서 나와 집계에서 제외됨`);
  if (s.effort_na)
    f.push("어려운 내용이 없어 ‘설명 노력(C2)’ 평가 불가 — 채점 척도가 잘 맞지 않는 기사임");
  if (s.n_terms === 0) f.push("뽑힌 전문용어 0개 — 용어 해설률(C3) 산출 불가");
  if (s.n_sources === 0) f.push("이름·기관명이 밝혀진 취재원 없음 — 이해관계 공시(B3) 해석에 주의");
  if (s.para_coverage && s.para_coverage < 0.35)
    f.push(`용어가 분석 창의 ${Math.round(s.para_coverage * 100)}%에서만 나옴 — 덜 뽑혔을 가능성`);
  return f;
}

// ── 규준 ─────────────────────────────────────────────────────
export function cellKey(genre, lenBin) { return `${genre}/${lenBin}`; }

export function lenBin(n) {
  if (n < 800) return "S";
  if (n < 2000) return "M";
  return "L";
}

/** 비교군 선택 — 좁은 쪽부터, 표본이 부족하면 완화 */
export function pickCell(norms, genre, lb) {
  const minCell = norms.min_cell || 30;
  for (const k of [cellKey(genre, lb), `전체/${lb}`, "전체/전체"]) {
    const c = norms.cells[k];
    if (c && c.n >= minCell) return [k, c];
  }
  const c = norms.cells["전체/전체"];
  return c ? ["전체/전체", c] : [null, null];
}

/** 중간순위 백분위 — 동점이 많은 0–5 척도에 적합 */
export function percentile(hist, x, integerize = false) {
  if (!hist) return null;
  const v = integerize ? Math.round(Number(x)) : Number(x);
  let below = 0, equal = 0, total = 0;
  for (const [k, cnt] of Object.entries(hist)) {
    const kv = Number(k);
    total += cnt;
    if (kv < v) below += cnt;
    else if (kv === v) equal += cnt;
  }
  return total ? ((below + 0.5 * equal) / total) * 100 : null;
}

export function itemPercentile(cell, item, value) {
  if (value === null || value === undefined) return null;
  const h = (cell.hist || {})[item];
  if (!h) return null;
  return percentile(h, value, item === "term_explanation_rate");
}

export function dimScores(r) {
  const out = {};
  for (const [d, keys] of Object.entries(DIMS)) {
    const vals = keys.map((k) => r[k]).filter((v) => v !== null && v !== undefined);
    out[d] = vals.length ? pyRound(vals.reduce((a, b) => a + b, 0) / vals.length, 3) : null;
  }
  return out;
}

/** 기사 1건의 차원 평균 [A, C, D, B]. 하나라도 비면 null */
export function dimVector(r) {
  const out = [];
  for (const d of DIM_ORDER) {
    const vals = DIMS[d].map((k) => r[k]).filter((v) => v !== null && v !== undefined);
    if (!vals.length) return null;
    out.push(vals.reduce((a, b) => a + b, 0) / vals.length);
  }
  return out;
}

// 재현 가능한 난수 (mulberry32)
function rng(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Layer 3 — 서수 제약(A ≥ C ≥ D ≥ B)만 건 가중치 공간에서의 백분위 구간.
 *
 * 가중치의 '비율'은 근거가 없다. 인터뷰에서 방어 가능한 것은 '순서'뿐이다.
 * 그래서 순서만 제약하고 나머지는 1,000회 추출로 적분해 없앤다.
 */
export function weightInterval(r, norms, nDraw = 1000, seed = 7) {
  const cell = norms && norms.cells["전체/전체"];
  if (!cell || !cell.dim_vectors) return null;
  const mine = dimVector(r);
  if (!mine) return null;

  const pop = cell.dim_vectors;                 // [[A, C, D, B], ...]
  const nPop = pop.length;
  const rand = rng(seed);
  const pcts = new Float64Array(nDraw);

  for (let d = 0; d < nDraw; d++) {
    // Dirichlet(1,1,1,1) = 지수분포 4개를 뽑아 정규화
    let w = [0, 0, 0, 0];
    let s = 0;
    for (let i = 0; i < 4; i++) { w[i] = -Math.log(1 - rand()); s += w[i]; }
    for (let i = 0; i < 4; i++) w[i] /= s;
    w.sort((x, y) => y - x);                    // 서수 제약 = 내림차순 정렬
    const my = w[0] * mine[0] + w[1] * mine[1] + w[2] * mine[2] + w[3] * mine[3];
    let below = 0, equal = 0;
    for (let i = 0; i < nPop; i++) {
      const v = pop[i];
      const t = w[0] * v[0] + w[1] * v[1] + w[2] * v[2] + w[3] * v[3];
      if (t < my) below++; else if (t === my) equal++;
    }
    pcts[d] = ((below + 0.5 * equal) / nPop) * 100;
  }
  const sorted = Array.from(pcts).sort((a, b) => a - b);
  const q = (p) => {
    const idx = (sorted.length - 1) * p;
    const lo = Math.floor(idx), hi = Math.ceil(idx);
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
  };
  return {
    mean: Array.from(pcts).reduce((a, b) => a + b, 0) / nDraw,
    lo: q(0.025), hi: q(0.975), n_pop: nPop, n_draw: nDraw,
  };
}

// ── 등급 ─────────────────────────────────────────────────────
const GRADE = [[4.5, "충족", "●"], [3.0, "대체로 충족", "◐"],
               [1.5, "부분 충족", "○"], [-1, "미충족", "✗"]];

export function grade(score) {
  if (score === null || score === undefined) return ["해당 없음", "–"];
  for (const [th, label, mark] of GRADE) if (score >= th) return [label, mark];
  return ["미충족", "✗"];
}

/** 용어 해설률(0–100)을 등급 판정을 위해 0–5로 환산 */
export function scale5(key, v) {
  if (v === null || v === undefined) return null;
  return key === "term_explanation_rate" ? v / 20.0 : v;
}
