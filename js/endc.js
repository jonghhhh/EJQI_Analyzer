// ENDC 데스크 챗봇 — 시스템 프롬프트와 문맥 조립
//
// 지식 베이스(data/endc_knowledge.md)를 통째로 시스템 지시에 넣는다.
// ① EJQI 12항목의 조작적 정의와 앵커 ② 전문가 인터뷰 11명 원문 ③ 코퍼스 30,178건 실측.

import { ALL_ITEMS, dimScores, grade, scale5 } from "./ejqi.js";

let _knowledge = null;

export async function loadKnowledge() {
  if (_knowledge !== null) return _knowledge;
  try {
    const r = await fetch("data/endc_knowledge.md");
    _knowledge = r.ok ? await r.text() : "";
  } catch { _knowledge = ""; }
  return _knowledge;
}

const SYSTEM_HEAD = `당신은 **경제 뉴스 데스크 챗봇(ENDC, Economic News Desk Chatbot)**이다.
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
- 길어지면 **개조식**으로 정리한다. 표가 도움이 되면 마크다운 표를 쓴다.
- 기사 초고가 주어졌으면 **그 기사의 실제 문장을 인용**해 말한다. 일반론으로 흐르지 않는다.
- 고쳐 쓴 예시는 "원문 → 제안" 형태로 대비해 보여 준다.
- 답변 끝에 **"가장 먼저 할 것 한 가지"**를 한 줄로 못박는다.

[지식 베이스]
`;

export async function systemPrompt() {
  return SYSTEM_HEAD + (await loadKnowledge());
}

export const QUICK = [
  ["🎯 가장 먼저 고칠 것",
   "이 기사에서 가장 먼저 고쳐야 할 것 한 가지만 짚어 주세요. 왜 그것이 우선인지도 알려 주세요."],
  ["🔢 수치 맥락화",
   "본문의 핵심 수치에 비교 기준선이 붙어 있는지 점검하고, 없다면 어떤 기준을 붙이면 좋을지 예시 문장으로 제안해 주세요."],
  ["🔍 검증·반론",
   "이 기사가 단일 출처 받아쓰기에 가까운지 판단하고, 어떤 반대 근거나 독립 자료를 붙이면 좋을지 구체적으로 알려 주세요."],
  ["📖 용어 풀이",
   "비전문가가 막힐 만한 전문용어를 골라 주고, 각각 첫 등장 자리에 넣을 한 문장 설명을 만들어 주세요."],
  ["🙋 독자 함의",
   "이 기사가 독자의 삶·자산·의사결정에 어떤 의미인지 설명하고 있나요? 없다면 넣을 만한 한 문단을 제안해 주세요."],
  ["👥 취재원 보강",
   "취재원 구성을 평가하고, 어떤 유형의 취재원을 추가하면 좋을지 알려 주세요."],
  ["📰 제목 점검",
   "제목이 본문 내용·수치를 과장하거나 왜곡하지 않는지 점검해 주세요."],
  ["🧭 EJQI란?",
   "EJQI가 무엇이고 어떤 차원과 항목으로 구성되는지, 왜 단일 점수를 만들지 않는지 설명해 주세요."],
];

/** 초고 + (선택) 분석 결과를 질문 앞에 붙일 문맥으로 만든다 */
export function buildContext(draft, result, attach) {
  const parts = [];
  if (draft && draft.trim()) parts.push(`[검토 대상 기사 초고]\n${draft.trim()}`);
  if (attach && result) {
    const d = dimScores(result);
    const L = [
      `장르 ${result.genre} · 본문 ${(result.meta?.body_len || 0).toLocaleString()}자`,
      `차원 평균 — A 분석깊이 ${d.A} / C 이해가능성 ${d.C} / D 맥락충실성 ${d.D} / B 취재원 ${d.B}`,
      `C1 이해 난이도 ${result.difficulty} (높을수록 쉬움) · ` +
      `C2 설명 노력 ${result.effort_na ? "평가불가" : result.effort} · ` +
      `C3 용어 해설률 ${result.term_explanation_rate}%`,
      "항목별 점수와 근거:",
    ];
    for (const [code, key, label] of ALL_ITEMS) {
      const v = result[key];
      const [g] = grade(scale5(key, v));
      const ev = result._evidence?.[key] || {};
      L.push(`  ${code} ${label} = ${v === null || v === undefined ? "–" : v} (${g})`
        + (ev.evidence ? ` | 근거: ${String(ev.evidence).slice(0, 80)}` : "")
        + (ev.reasoning ? ` | 판정: ${String(ev.reasoning).slice(0, 60)}` : ""));
    }
    if (result.unexplained_terms?.length) {
      L.push("미해설 용어: " + result.unexplained_terms.slice(0, 20).join(", "));
    }
    if (result.blockers?.length) {
      L.push("막히는 지점:");
      for (const b of result.blockers.slice(0, 8)) {
        L.push(`  [${b.reason}] ${String(b.sentence).slice(0, 90)} → ${b.note}`);
      }
    }
    if (result.sources?.length) {
      L.push("취재원: " + result.sources.slice(0, 15).map(
        (s) => `${s.name}(${s.econ_source_type}${s.transparent ? "" : ",익명"})`).join(", "));
    }
    const gates = [];
    if (result.headline_overstated) gates.push("G1 제목 과장 발동");
    if (result.promotional) gates.push(`G5 홍보성 발동(${result.promotional_type})`);
    if (gates.length) L.push("게이트: " + gates.join(" / "));
    parts.push("[EJQI 분석 결과]\n" + L.join("\n"));
  }
  return parts.join("\n\n");
}
