// JS 포팅이 파이썬 원본과 동일하게 동작하는지 검증한다.
//
//   python web/scripts/make_parity_fixture.py --n 200
//   node   web/scripts/parity_test.mjs
//
// 한 건이라도 어긋나면 실패로 보고한다. 규준(30,178건)과의 비교가 걸려 있으므로
// 근사 일치가 아니라 **완전 일치**를 요구한다.

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const E = await import(pathToFileURL(join(HERE, "..", "js", "ejqi.js")).href);

const cases = JSON.parse(readFileSync(join(HERE, "_fixture.json"), "utf-8"));
console.log(`고정자료 ${cases.length}건 로드`);

let fail = 0, checked = 0;
const report = (label, i, exp, got, extra = "") => {
  fail++;
  if (fail <= 12) {
    console.log(`  ✗ [${i}] ${label}${extra ? " " + extra : ""}`);
    console.log(`      python: ${JSON.stringify(exp)?.slice(0, 180)}`);
    console.log(`      js    : ${JSON.stringify(got)?.slice(0, 180)}`);
  }
};

const near = (a, b) => (a === null || b === null)
  ? a === b
  : Math.abs(Number(a) - Number(b)) < 1e-9;

cases.forEach((c, i) => {
  // ① 문단 분할
  const paras = E.splitParagraphs(c.body);
  checked++;
  if (JSON.stringify(paras) !== JSON.stringify(c.paragraphs)) {
    report("split_paragraphs", i, c.paragraphs.length + "개", paras.length + "개");
    for (let k = 0; k < Math.max(paras.length, c.paragraphs.length); k++) {
      if (paras[k] !== c.paragraphs[k]) {
        if (fail <= 12) {
          console.log(`      첫 불일치 P${k + 1}`);
          console.log(`      python: ${JSON.stringify(c.paragraphs[k]?.slice(0, 90))}`);
          console.log(`      js    : ${JSON.stringify(paras[k]?.slice(0, 90))}`);
        }
        break;
      }
    }
  }

  // ② 문단 번호 부여
  checked++;
  if (E.numberParagraphs(paras).slice(0, 200) !== c.numbered_head) {
    report("number_paragraphs", i, c.numbered_head.slice(0, 80),
           E.numberParagraphs(paras).slice(0, 80));
  }

  // ③ 분석 창
  const [wl, wc] = E.termWindow(paras);
  checked++;
  if (wl !== c.win_last || wc !== c.win_chars) {
    report("term_window", i, [c.win_last, c.win_chars], [wl, wc]);
  }

  // ④ 인용 대조
  const bodyNorm = E.normWs(c.body);
  const bodyArr = Array.from(bodyNorm);
  for (const q of c.quotes) {
    checked++;
    const got = E.quoteStatus(q.q, bodyNorm, bodyArr);
    if (got !== q.status) report("quote_status", i, q.status, got, JSON.stringify(q.q.slice(0, 45)));
  }

  // ⑤ verify 전체
  const got = E.verify(c.raw, c.body, paras.length, wl, wc);
  const exp = c.scored;
  for (const k of Object.keys(exp)) {
    checked++;
    const a = exp[k], b = got[k];
    let ok;
    if (typeof a === "number") ok = near(a, b);
    else if (a === null) ok = (b === null || b === undefined);
    else ok = JSON.stringify(a) === JSON.stringify(b);
    if (!ok) report(`verify.${k}`, i, a, b);
  }
  const extra = Object.keys(got).filter((k) => !(k in exp));
  if (extra.length && !extra.every((k) => k === "terms_detail")) {
    report("verify(추가 키)", i, [], extra);
  }
});

console.log(`\n검사 ${checked.toLocaleString()}건 · 불일치 ${fail}건`);
if (fail) { console.log("❌ 파이썬 원본과 다릅니다."); process.exit(1); }
console.log("✅ 파이썬 원본과 완전히 일치합니다.");
