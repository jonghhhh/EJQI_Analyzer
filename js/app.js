// EJQI Suite — UI 로직 (프레임워크 없음)
import * as E from "./ejqi.js";
import { EJQI_SCHEMA } from "./schema.js";
import { SYSTEM, buildPrompt } from "./prompts.js";
import * as G from "./gemini.js";
import { QUICK, buildContext, systemPrompt } from "./endc.js";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const state = { norms: null, result: null, chat: [], busy: false };
const DIM_CLASS = { A: "dimA", B: "dimB", C: "dimC", D: "dimD" };

// ══════════ 초기화 ══════════
(async function init() {
  $("modelName").textContent = E.MODEL;

  // 분야 선택
  const sel = $("fTopic");
  sel.innerHTML = '<option value="">(선택 안 함)</option>'
    + E.TOPICS.map((t) => `<option>${esc(t)}</option>`).join("");

  // 규준
  try {
    const r = await fetch("data/norms_web.json");
    state.norms = await r.json();
    $("nCells").textContent = Object.keys(state.norms.cells).length;
  } catch {
    $("nCells").textContent = "로드 실패";
  }

  // 저장된 키 복원
  const saved = localStorage.getItem("ejqi_key");
  if (saved) { $("apikey").value = saved; setKeyState("saved"); }

  // 빠른 질문
  $("quickBox").innerHTML = QUICK.map((q, i) =>
    `<button class="ghost" data-q="${i}">${esc(q[0])}</button>`).join("");
  $("quickBox").addEventListener("click", (e) => {
    const b = e.target.closest("button[data-q]");
    if (b) send(QUICK[+b.dataset.q][1]);
  });

  renderChat();
  bind();
})();

function bind() {
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("on", x === t));
    document.querySelectorAll(".panel").forEach((p) =>
      p.classList.toggle("on", p.id === "p-" + t.dataset.tab));
    window.scrollTo({ top: 0, behavior: "smooth" });
  }));

  $("apikey").addEventListener("input", () => setKeyState(""));
  $("btnPing").addEventListener("click", pingKey);
  $("btnClearKey").addEventListener("click", () => {
    $("apikey").value = ""; localStorage.removeItem("ejqi_key"); setKeyState("");
  });

  $("fBody").addEventListener("input", () => {
    const n = $("fBody").value.length;
    $("bodyLen").textContent = n ? `— ${n.toLocaleString()}자` : "";
    if ($("cbPreview").checked) renderPreview();
  });
  $("cbPreview").addEventListener("change", renderPreview);
  $("btnRun").addEventListener("click", runAnalysis);

  $("btnSend").addEventListener("click", () => send($("chatInput").value));
  $("chatInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.isComposing) send($("chatInput").value);
  });
  $("btnClearChat").addEventListener("click", () => { state.chat = []; renderChat(); });
}

// ══════════ 키 ══════════
function setKeyState(kind, msg) {
  const el = $("keyState");
  const has = $("apikey").value.trim().length > 0;
  if (kind === "ok") {
    el.className = "note ok"; el.innerHTML = msg || "키 확인 완료 — 두 기능 모두 사용 가능함.";
  } else if (kind === "bad") {
    el.className = "note err"; el.innerHTML = msg;
  } else if (kind === "saved" || has) {
    el.className = "note info";
    el.innerHTML = '키 입력됨. <b>키 확인</b>을 눌러 정상 작동 여부 점검 가능.'
      + '<br><label class="small" style="display:flex;gap:5px;align-items:center;margin-top:6px">'
      + `<input type="checkbox" id="cbSave" style="width:auto" ${localStorage.getItem("ejqi_key") ? "checked" : ""}>`
      + ' 이 브라우저에 키 저장</label>';
    const cb = $("cbSave");
    if (cb) cb.addEventListener("change", () => {
      if (cb.checked) localStorage.setItem("ejqi_key", $("apikey").value.trim());
      else localStorage.removeItem("ejqi_key");
    });
  } else {
    el.className = "note info"; el.textContent = "키를 넣어야 분석·대화 시작 가능함.";
  }
}

async function pingKey() {
  const k = $("apikey").value.trim();
  if (!k) return setKeyState("bad", "키를 먼저 입력할 것.");
  $("btnPing").disabled = true;
  setKeyState("", ""); $("keyState").innerHTML = '<span class="spin"></span> 확인 중…';
  const r = await G.pingKey(k, E.MODEL);
  $("btnPing").disabled = false;
  if (r.ok) { setKeyState("ok"); refreshUsage(); }
  else setKeyState("bad", esc(r.error?.message || "키 확인 실패."));
}

function requireKey(target) {
  const k = $("apikey").value.trim();
  if (!k) {
    $(target).innerHTML = '<div class="note warn">🔑 왼쪽 사이드바에 <b>Gemini API 키</b>를 먼저 '
      + '입력할 것. 발급 방법은 사이드바의 <b>“API 키 받는 법”</b>을 펼치면 나옴.</div>';
    return null;
  }
  return k;
}

function refreshUsage() {
  if (!G.usage.calls) return;
  $("usageBox").style.display = "";
  $("uCalls").textContent = G.usage.calls;
  $("uCost").textContent = "$" + G.costUsd().toFixed(4);
  $("uIn").textContent = G.usage.in.toLocaleString();
  $("uOut").textContent = G.usage.out.toLocaleString();
}

// ══════════ 문단 미리보기 ══════════
function renderPreview() {
  const box = $("previewBox");
  const body = $("fBody").value;
  if (!$("cbPreview").checked || body.trim().length < 40) { box.innerHTML = ""; return; }
  const paras = E.splitParagraphs(body);
  const [wl, wc] = E.termWindow(paras);
  box.innerHTML = `<div class="card">
    <h3>📐 문단 나눔 미리 보기</h3>
    <p class="muted" style="margin-top:-4px">${body.length.toLocaleString()}자 → <b>${paras.length}덩어리</b>
      · 용어 분석 창 <b>P1~P${wl}</b> (${wc.toLocaleString()}자, 본문의 ${Math.round(wc / body.length * 100)}%)</p>
    <p class="small muted">수집된 기사 본문에는 줄바꿈이 없음(실측 36,334건 중 0건).
      그래서 코드가 <b>문장 3개씩 묶어</b> 약 200자짜리 덩어리를 만들고 [P1] [P2] 번호를 붙임.
      기자가 나눈 원문 문단이 아니라 <b>기사의 몇 번째 대목인지 가리키는 좌표</b>임.<br>
      🟦 창 안에서만 <b>전문용어(C3)</b>를 뽑음. 나머지 11개 항목과
      <b>취재원 목록은 기사 전체가 대상</b>임.</p>
    ${paras.map((p, i) => `<div class="para${i < wl ? " win" : ""}">
      <b>[P${i + 1}]</b> ${i < wl ? "🟦 창 안" : "⬜ 창 밖"} · ${p.length}자<br>
      <span class="muted">${esc(p.slice(0, 200))}${p.length > 200 ? "…" : ""}</span></div>`).join("")}
  </div>`;
}

// ══════════ 분석 ══════════
async function runAnalysis() {
  if (state.busy) return;
  const key = requireKey("anaMsg");
  if (!key) return;
  const body = $("fBody").value.trim();
  if (body.length < 100) {
    $("anaMsg").innerHTML = '<div class="note err">본문이 너무 짧음. '
      + '최소 100자, 400자 이상 권장.</div>';
    return;
  }

  const repeat = +$("fRepeat").value;
  const paras = E.splitParagraphs(body);
  const [wl, wc] = E.termWindow(paras);
  const prompt = buildPrompt({
    title: $("fTitle").value.trim(), subtitle: $("fSub").value.trim(),
    numberedBody: E.numberParagraphs(paras), nPara: paras.length,
    win: wl, winChars: wc, termCap: E.TERM_CAP, blockerCap: E.BLOCKER_CAP,
  });

  state.busy = true;
  $("btnRun").disabled = true;
  $("anaResult").innerHTML = "";
  const t0 = performance.now();
  const say = (m) => { $("anaMsg").innerHTML = `<div class="note info"><span class="spin"></span> ${m}</div>`; };

  try {
    const runs = [];
    for (let i = 0; i < repeat; i++) {
      say(`모형이 기사를 읽는 중… ${repeat > 1 ? `(${i + 1}/${repeat}회)` : ""}`);
      const raw = await G.generateStructured({
        apiKey: key, model: E.MODEL, system: SYSTEM, prompt, schema: EJQI_SCHEMA,
        temperature: repeat > 1 ? 0.7 : 0,     // 반복은 temp>0에서만 의미가 있다
        onRetry: (n, s) => say(`일시 오류 — 재시도 중 (${n}회째, ${s}초 후)…`),
      });
      runs.push(E.verify(raw, body, paras.length, wl, wc));
    }
    const r = mergeRepeats(runs);
    r.flags = E.reliabilityFlags(r);
    r.meta = {
      press: $("fPress").value.trim(), topic: $("fTopic").value,
      title: $("fTitle").value.trim(), subtitle: $("fSub").value.trim(),
      body_len: body.length, len_bin: E.lenBin(body.length),
    };
    r._body = body;
    state.result = r;

    $("anaMsg").innerHTML = `<div class="note ok">분석 완료 — ${((performance.now() - t0) / 1000).toFixed(1)}초 ·
      호출 ${repeat}회 · 추정 비용 $${G.costUsd().toFixed(4)}</div>`;
    renderResult(r);
    $("cbAttach").disabled = false; $("cbAttach").checked = true;
    $("attachHint").innerHTML = "※ 분석 결과 준비됨. 체크하면 대화에 함께 전달됨.";
    refreshUsage();
  } catch (e) {
    const cls = e instanceof G.ApiKeyError ? "🔑" : (e instanceof G.QuotaError ? "⏳" : "⚠");
    $("anaMsg").innerHTML = `<div class="note err">${cls} ${esc(e.message)}</div>`;
  } finally {
    state.busy = false; $("btnRun").disabled = false;
  }
}

/** N회 결과 평균. 첫 실행의 근거·목록을 대표로 남긴다 */
function mergeRepeats(runs) {
  if (runs.length === 1) return { ...runs[0], n_repeats: 1 };
  const keys = [...E.SCORED_ITEMS, ...E.DERIVED_ITEMS].map((t) => t[1]);
  const out = { ...runs[0] };
  const mean = (a) => a.reduce((x, y) => x + y, 0) / a.length;
  for (const k of keys) {
    const v = runs.map((r) => r[k]).filter((x) => x !== null && x !== undefined);
    out[k] = v.length ? E.pyRound(mean(v), 2) : null;
  }
  for (const k of ["n_terms", "n_blockers", "n_sources", "n_terms_unexplained"]) {
    out[k] = E.pyRound(mean(runs.map((r) => r[k])), 1);
  }
  out.effort_na = runs.filter((r) => r.effort_na).length > runs.length / 2;
  for (const k of ["headline_consistency", "promotional"]) {
    out[k] = runs.filter((r) => r[k]).length > runs.length / 2;
  }
  out.headline_overstated = out.headline_consistency;
  out.n_repeats = runs.length;
  out.repeat_sd = {};
  for (const k of keys) {
    const v = runs.map((r) => r[k]).filter((x) => x !== null && x !== undefined);
    if (v.length === runs.length) {
      const m = mean(v);
      out.repeat_sd[k] = E.pyRound(
        Math.sqrt(v.reduce((a, x) => a + (x - m) ** 2, 0) / Math.max(v.length - 1, 1)), 2);
    }
  }
  return out;
}

// ══════════ 결과 렌더링 ══════════
function metric(k, v, s) {
  return `<div class="metric"><div class="k">${k}</div><div class="v">${v}</div>
          ${s ? `<div class="s">${s}</div>` : ""}</div>`;
}

function renderResult(r) {
  const d = E.dimScores(r);
  const m = r.meta || {};
  const H = [];

  // 요약
  H.push(`<div class="card"><h3>📋 요약</h3>
    <div class="metrics">
      ${metric("장르 (자동 판정)", esc(r.genre), esc(String(r.genre_reason).slice(0, 40)))}
      ${metric("본문 길이", m.body_len.toLocaleString() + "자", `길이대 ${m.len_bin}`)}
      ${metric("취재원", r.n_sources + "명", `기사 전체 기준 · 실명 ${r.n_sources_named}명`)}
      ${metric("전문용어", r.n_terms + "개", `설명 없이 쓴 것 ${r.n_terms_unexplained}개`)}
      ${metric("용어 해설률", r.term_explanation_rate === null ? "–" : r.term_explanation_rate + "%",
               "3만 건 평균 13.5%")}
      ${metric("막히는 문장", r.n_blockers + "개", "비전문가가 걸리는 대목")}
    </div>
    <div class="metrics">
      ${metric('<span class="dimA">A 분석 깊이</span>', d.A ?? "–", "3만 건 평균 2.32")}
      ${metric('<span class="dimC">C 이해 가능성</span>', d.C ?? "–", "3만 건 평균 1.81")}
      ${metric('<span class="dimD">D 맥락 충실성</span>', d.D ?? "–", "3만 건 평균 1.86")}
      ${metric('<span class="dimB">B 취재원·투명성</span>', d.B ?? "–", "3만 건 평균 2.83")}
      ${metric("C1 이해 난이도", r.difficulty, "⚠ 높을수록 쉬움 · 품질 아님")}
      ${metric("C2 설명 노력", r.effort_na ? "평가 불가" : r.effort,
               r.effort_na ? "어려운 내용 없음" : "3만 건 평균 1.86")}
    </div>
    <p class="small muted">⚠ 위 네 차원 평균을 다시 더해 총점을 만들지 말 것.
      이해관계 공시(B3)와 이해 난이도(C1)는 나머지 항목과 따로 노는 값이어서,
      평균에 넣으면 홍보성 단신의 점수가 부풀려짐.</p>
    ${r.n_repeats > 1 ? `<div class="note info">반복 채점 ${r.n_repeats}회의 평균값임.
      항목별 편차는 아래 <b>채점 원자료</b>에서 확인 가능함.</div>` : ""}
    ${r.effort_na ? `<div class="note info">이 기사는 <b>어려운 내용 자체가 없어
      ‘설명 노력(C2)’을 평가할 수 없음</b>. 행사 안내·인사·단순 홍보 기사가 여기 해당함.
      <b>이때의 0점은 감점이 아니라 ‘평가 불가’</b>임. 측정한 기사의 43.1%가 이 유형이었음.</div>` : ""}
  </div>`);

  // Layer 1
  H.push('<div class="card"><h3>🩺 1단계 — 항목별 진단 카드</h3>'
    + '<p class="small muted" style="margin-top:-4px">이 도구의 <b>가장 중요한 산출물</b>. '
    + '점수보다 <b>등급과 근거 문장</b>을 볼 것 — 어느 대목이 왜 그렇게 판정됐는지가 핵심임.<br>'
    + '등급 표기: ● 충족 · ◐ 대체로 충족 · ○ 부분 충족 · ✗ 미충족<br>'
    + '전문가 인터뷰가 요구한 형태임 — “점수보다 근거가 중요합니다. '
    + '어느 문장이 왜 감점인지 제시하고”(I08)</p>');
  for (const [code, key, label, dim] of E.ALL_ITEMS) {
    const v = r[key];
    const s5 = E.scale5(key, v);
    let [g, mark] = E.grade(s5);
    let note = "";
    if (key === "effort" && r.effort_na) { g = "평가 불가"; mark = "–"; note = " — 어려운 내용 없음(감점 아님)"; }
    const cm = E.CORPUS_MEAN[key];
    const isRate = key === "term_explanation_rate";
    const shown = v === null || v === undefined ? "–" : (isRate ? v + "%" : v);
    let cmp = "";
    if (cm !== undefined && v !== null && v !== undefined) {
      const diff = v - cm;
      const arrow = diff > 0 ? "▲" : (diff < 0 ? "▼" : "＝");
      cmp = `3만 건 평균 ${cm}${isRate ? "%" : ""} ${arrow}${Math.abs(diff).toFixed(2)}`;
    }
    const ev = r._evidence?.[key] || {};
    H.push(`<div class="item">
      <div class="h">
        <span class="code ${DIM_CLASS[dim]}">${mark} ${code}</span>
        <span class="lbl">${esc(label)}</span>
        <span class="val">${shown}</span>
        <span class="gr ${DIM_CLASS[dim]}">${g}${note}</span>
        <span class="cmp">${cmp}</span>
      </div>
      ${ev.evidence && !["없음", "해당없음", ""].includes(ev.evidence)
        ? `<div class="ev">“${esc(ev.evidence)}”</div>` : ""}
      ${ev.reasoning ? `<p class="rs">판정: ${esc(ev.reasoning)}</p>` : ""}
      <p class="rs small">${esc(E.ITEM_HELP[key] || "")}</p>
    </div>`);
  }
  const gates = [];
  if (r.headline_overstated) gates.push(["G1 제목 과장·왜곡", r.headline_consistency__evidence]);
  if (r.promotional) gates.push(["G5 홍보·광고성", r.promotional__evidence]);
  if (gates.length) {
    H.push("<h4>⚑ 점검에 걸린 항목 <span class=\"muted small\">(점수에는 반영되지 않음)</span></h4>");
    for (const [n, e] of gates) H.push(`<div class="gate"><b>${n}</b><br>${esc(e)}</div>`);
  }
  const gb = [];
  if (!r.headline_overstated) gb.push("제목 과장·왜곡 없음");
  if (!r.promotional) gb.push("홍보·광고성 아님");
  gb.push(`낙관·비관 균형 ${r.sentiment_balance}/5 (5에 가까울수록 균형)`);
  if (r.promotional_type !== "해당없음") gb.push(`홍보 유형: ${esc(r.promotional_type)}`);
  H.push(`<p class="small muted">${gb.join(" · ")}</p>`);
  if (r.flags?.length) {
    H.push(`<details><summary>⚠ 사람이 직접 확인할 것 ${r.flags.length}건</summary>
      <ul class="small">${r.flags.map((f) => `<li>${esc(f)}</li>`).join("")}</ul></details>`);
  }
  H.push("</div>");

  // Layer 2
  H.push('<div class="card"><h3>📊 2단계 — 비슷한 기사들 사이에서의 위치</h3>'
    + '<p class="small muted" style="margin-top:-4px">'
    + '<b>백분위 P○</b> = 비슷한 기사 100건 중 몇 번째로 좋은가. P50이면 딱 중간, P90이면 상위 10%.<br>'
    + '기사가 길수록 점수가 오르는 효과가 크므로 <b>장르와 길이가 비슷한 기사끼리만</b> 견줌.</p>');
  if (!state.norms) H.push('<div class="note warn">비교 기준표를 불러오지 못해 백분위를 낼 수 없음.</div>');
  else {
    const [ck, cell] = E.pickCell(state.norms, r.genre, m.len_bin);
    H.push(`<p class="muted">비교 대상 <b>${esc(ck)}</b>
      (같은 조건의 기사 ${cell.n.toLocaleString()}건) · 항목별 가중치 없이 그대로 비교 ·
      전체 30,178건 기준</p>
      <div class="tbl-wrap"><table><thead><tr>
        <th>코드</th><th>항목</th><th class="num">점수</th><th class="num">백분위</th><th>비슷한 기사 중 위치</th>
      </tr></thead><tbody>`);
    for (const [code, key, label] of E.ALL_ITEMS) {
      const v = r[key];
      const p = E.itemPercentile(cell, key, v);
      const shown = v === null || v === undefined ? "–" : (key === "term_explanation_rate" ? v + "%" : v);
      H.push(`<tr><td>${code}</td><td>${esc(label)}</td><td class="num">${shown}</td>
        <td class="num">${p === null ? "–" : "P" + Math.round(p)}</td>
        <td>${p === null ? "" : `<span class="bar"><i style="left:${Math.min(p, 99)}%"></i></span>`}</td></tr>`);
    }
    H.push(`</tbody></table></div>
      <p class="small muted">⚠ C1 이해 난이도와 C2 설명 노력은 서로 <b>반대 방향</b>으로 움직이는 값임(상관 −0.28).
      더하지 말고 나란히 읽을 것. C1이 높은데 C2가 낮으면
      ‘쉬운 기사’가 아니라 ‘설명할 내용이 없는 기사’일 수 있음.</p>`);
  }
  H.push("</div>");

  // Layer 3
  H.push('<div class="card"><h3>🎚 3단계 — 가중치를 바꿔도 흔들리지 않는 순위 범위</h3>'
    + '<p class="small muted" style="margin-top:-4px">'
    + '네 차원 중 무엇을 더 중요하게 볼지는 사람마다 다름. 그래서 <b>중요도 배분을 1,000가지로 '
    + '바꿔 가며</b> 순위를 매번 다시 계산함. 고정한 규칙은 순서 하나뿐 — '
    + '분석 깊이(A) ≥ 이해 가능성(C) ≥ 맥락 충실성(D) ≥ 취재원·투명성(B). '
    + '전문가 인터뷰에서 합의된 것이 이 순서뿐이고 “A는 몇 %” 같은 비율은 근거가 없기 때문임.</p>');
  const p3 = state.norms ? E.weightInterval(r, state.norms) : null;
  if (!p3) H.push('<div class="note warn">차원 점수가 일부 비어 있어 이 단계는 건너뜀.</div>');
  else {
    const width = p3.hi - p3.lo;
    H.push(`<div class="metrics" style="grid-template-columns:repeat(2,1fr)">
      ${metric("순위 (평균)", "P" + Math.round(p3.mean), "전체 기사 중 위치")}
      ${metric("흔들리는 범위", `P${Math.round(p3.lo)} ~ P${Math.round(p3.hi)}`,
               width < 10 ? "좁음 — 평가가 잘 안 갈림" : (width < 25 ? "보통" : "넓음 — 관점 따라 갈림"))}
    </div>
    <div class="note info" style="margin-bottom:0">
      <b>읽는 법</b>
      <ul style="margin:6px 0 0; padding-left:18px">
        <li>이 기사는 전체 ${p3.n_pop.toLocaleString()}건 가운데 대략
            <b>상위 ${100 - Math.round(p3.mean)}%</b> 위치임.</li>
        <li>중요도를 어떻게 배분하더라도 순위는
            <b>P${Math.round(p3.lo)} ~ P${Math.round(p3.hi)}</b> 안에 머무름
            (${p3.n_draw.toLocaleString()}가지 배분 중 95%).</li>
        <li>범위가 <b>좁으면</b> 누가 봐도 평가가 비슷한 기사, <b>넓으면</b> 보는 관점에 따라
            평가가 갈리는 기사 → 사람의 판단이 더 필요함.</li>
      </ul>
    </div>`);
  }
  H.push("</div>");

  // 추출 산출물
  H.push('<div class="card"><h3>🔍 함께 뽑아 낸 자료</h3>'
    + '<p class="small muted" style="margin-top:-4px">점수가 아니라 <b>고칠 자리를 찾기 위한 목록</b>임.</p>');

  H.push('<h4>취재원 <span class="muted small">— 기사 전체에서 셈 (용어 분석 창과 무관)</span></h4>');
  if (!r.sources?.length) H.push('<div class="note info">이름이나 기관명이 밝혀진 취재원이 없음. 이해관계 공시(B3) 해석에 주의할 것.</div>');
  else {
    H.push(`<div class="tbl-wrap"><table><thead><tr><th class="num">문단</th><th>이름</th><th>유형</th>
      <th>실명·소속</th><th>이해관계 공시</th><th>익명 사유</th></tr></thead><tbody>`
      + r.sources.map((s) => `<tr><td class="num">P${s.para}</td><td>${esc(s.name)}</td>
        <td>${esc(s.econ_source_type)}</td><td>${s.transparent ? "○" : "✗ 익명"}</td>
        <td>${s.interest_disclosed ? "○" : "✗"}</td><td>${esc(s.anonymity_reason || "없음")}</td></tr>`).join("")
      + "</tbody></table></div>"
      + `<p class="small muted">이 기사 <b>총 ${r.n_sources}명</b> ·
         실명·소속 밝힌 취재원 ${r.n_sources_named}명 · 이해관계까지 밝힌 취재원 ${r.n_sources_interest}명<br>
         ※ 취재원은 <b>기사 전체</b>에서 셈. 반론·전문가는 기사 뒤쪽에 오는 일이 많아
         앞부분만 보면 검증·반론(A3) 판정이 왜곡되기 때문임.<br>
         ※ 문단 번호 P○는 그 취재원이 처음 등장한 대목의 위치일 뿐임.<br>
         비교 — 3만 건 평균은 기사당 2.77명, 실명률 77.7%이며,
         익명 사유를 밝힌 취재원은 전체의 0.77%에 그쳤음.</p>`);
  }

  H.push('<h4>전문용어 <span class="muted small">— 앞 1,200자(분석 창) 안에서만 뽑음</span></h4>'
    + '<p class="small muted">설명 수준 4단계 — ✗ 없음(0) · ○ 사전적: 뜻풀이·약어만(0.5) · '
    + '◐ 맥락번역: 쉬운 말로 바꿔 설명(0.85) · ● 중요성설명: 왜 중요한지까지(1.0). '
    + '이 가중치를 평균한 값이 <b>용어 해설률(C3)</b>임.<br>'
    + '※ “상장지수펀드(ETF)”처럼 정식 명칭과 약어를 나란히 적은 것은 개념 설명으로 보지 않아 '
    + '‘없음’으로 판정함.</p>');
  const lv = r.term_levels || {};
  H.push(`<div class="metrics" style="grid-template-columns:repeat(4,1fr)">
    ${metric("없음", (lv["없음"] || 0) + "개", "")}
    ${metric("사전적", (lv["사전적"] || 0) + "개", "")}
    ${metric("맥락번역", (lv["맥락번역"] || 0) + "개", "")}
    ${metric("중요성설명", (lv["중요성설명"] || 0) + "개", "3만 건 중 0.1%뿐")}
  </div>`);
  const LM = { "없음": "✗ 없음", "사전적": "○ 사전적", "맥락번역": "◐ 맥락번역", "중요성설명": "● 중요성설명" };
  if (r.terms_detail?.length) {
    H.push(`<div class="tbl-wrap"><table><thead><tr><th class="num">문단</th><th>용어</th>
      <th>설명 수준</th><th>처음 등장한 문장</th></tr></thead><tbody>`
      + r.terms_detail.map((t) => `<tr><td class="num">P${t.para}</td><td><b>${esc(t.term)}</b></td>
        <td>${LM[t.explained] || esc(t.explained)}</td>
        <td class="small">${esc(t.first_sentence)}</td></tr>`).join("")
      + "</tbody></table></div>");
  } else {
    H.push('<div class="note info">분석 창 안에서 뽑힌 전문용어가 없음. 용어 해설률(C3)은 산출되지 않음.</div>');
  }
  if (r.unexplained_terms?.length) {
    H.push(`<p><b>설명 없이 쓴 용어</b> — 처음 나오는 자리에 한 문장을 덧붙일 후보<br>
      ${r.unexplained_terms.map((t) => `<code>${esc(t)}</code>`).join(" · ")}</p>`);
  }
  H.push(`<p class="small muted">분석 창 = 앞 1,200자를 목표로 문단 경계에서 끊은 범위
    (이 기사는 P1~P${r.term_window_last}, ${r.window_chars.toLocaleString()}자로
    본문의 ${Math.round(r.window_ratio * 100)}%). 창 밖 용어는 집계에서 뺌.
    긴 기사일수록 뒷부분 용어가 누락돼 기사끼리 비교가 안 되는 문제를 막기 위한 장치임.
    따라서 이 기사의 해설률은 <b>본문 전체가 아니라 앞 ${Math.round(r.window_ratio * 100)}%에 대한 값</b>임.<br>
    비교 — 3만 건 측정에서 전문용어의 <b>79.7%가 아무 설명 없이</b> 쓰였고,
    기사의 <b>50.3%는 해설률 0%</b>였으며, ‘왜 중요한가’까지 설명한 사례는 <b>0.1%</b>뿐이었음.
    ${r.n_terms_halluc ? `<br>※ 본문 대조에서 걸러낸 용어 ${r.n_terms_halluc}개
      (${esc((r.halluc_terms || []).slice(0, 8).join(", "))})` : ""}</p>`);

  H.push('<h4>비전문가가 막히는 문장</h4>');
  if (!r.blockers?.length) H.push('<div class="note ok">막히는 문장으로 지목된 대목이 없음.</div>');
  else {
    for (const b of r.blockers) {
      H.push(`<div class="ev"><b>[${esc(b.reason)}]</b> “${esc(b.sentence)}”</div>
              <p class="rs">→ ${esc(b.note)}</p>`);
    }
  }
  H.push(`<p class="small muted">3만 건 측정에서 독자가 막히는 대목의 <b>85.3%가 용어 미해설</b>이었고,
    문장이 복잡해서 막히는 경우는 <b>0.7%</b>뿐이었음.
    → <b>문장을 짧게 쓰기보다 용어를 풀어 주는 편이 훨씬 효과가 큼.</b></p>`);

  H.push(`<details><summary>🗂 채점 원자료 보기 (JSON)</summary>
    <pre class="small" style="max-height:340px; overflow:auto">${esc(
      JSON.stringify(Object.fromEntries(
        Object.entries(r).filter(([k]) => !k.startsWith("_"))), null, 1))}</pre></details>`);
  H.push("</div>");

  // 다운로드
  H.push(`<div class="card"><h3>⬇ 내려받기</h3>
    <p class="small muted" style="margin-top:-4px">txt는 사람이 읽는 진단서, json은 전체 원자료,
      csv는 여러 기사를 엑셀에 모아 비교할 때 쓰는 한 줄 요약임.</p>
    <div style="display:flex; gap:8px; flex-wrap:wrap">
      <button class="ghost" id="dlTxt">📄 진단 리포트 (txt)</button>
      <button class="ghost" id="dlJson">🗂 채점 원자료 (json)</button>
      <button class="ghost" id="dlCsv">📊 요약 한 줄 (csv)</button>
    </div></div>`);

  $("anaResult").innerHTML = H.join("");
  $("dlTxt").onclick = () => download("ejqi_report.txt", asText(r), "text/plain");
  $("dlJson").onclick = () => download("ejqi_result.json",
    JSON.stringify(Object.fromEntries(Object.entries(r).filter(([k]) => k !== "_body")), null, 1),
    "application/json");
  $("dlCsv").onclick = () => download("ejqi_row.csv", asCsv(r), "text/csv");
}

function download(name, text, mime) {
  const blob = new Blob(["﻿" + text], { type: mime + ";charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function asText(r) {
  const m = r.meta || {};
  const L = ["=".repeat(74),
    `${m.press || "(매체 미입력)"} · ${m.topic || ""} · ${m.body_len.toLocaleString()}자 · 장르 ${r.genre}`,
    `제목: ${(m.title || "").slice(0, 70)}`, "=".repeat(74), "",
    "[1단계] 항목별 진단 — 등급과 근거 문장", ""];
  for (const [code, key, label] of E.ALL_ITEMS) {
    const v = r[key], s5 = E.scale5(key, v);
    let [g, mark] = E.grade(s5);
    if (key === "effort" && r.effort_na) { g = "평가 불가 (어려운 내용 없음 — 감점 아님)"; mark = "–"; }
    L.push(` ${mark} ${code.padEnd(4)} ${label.padEnd(12)} ${g}`);
    const ev = r._evidence?.[key] || {};
    if (ev.evidence) L.push(`      근거: ${String(ev.evidence).slice(0, 70)}`);
    if (ev.reasoning && s5 !== null && s5 <= 2) L.push(`      결손: ${String(ev.reasoning).slice(0, 66)}`);
  }
  if (r.unexplained_terms?.length) {
    L.push("", ` 설명 없이 쓴 전문용어 (${r.unexplained_terms.length}개)`,
      "   " + r.unexplained_terms.slice(0, 20).join(", "));
  }
  if (r.blockers?.length) {
    L.push("", ` 비전문가가 막히는 문장 (${r.blockers.length}개)`);
    for (const b of r.blockers.slice(0, 8)) {
      L.push(`   [${b.reason}] ${String(b.sentence).slice(0, 58)}`, `      → ${String(b.note).slice(0, 50)}`);
    }
  }
  if (r.n_sources) {
    L.push("", ` 취재원 ${r.n_sources}명 (기사 전체 기준) — 실명·소속 ${r.n_sources_named}명 · ` +
      `이해관계까지 밝힘 ${r.n_sources_interest}명`);
  }
  if (r.headline_overstated) L.push("", ` ⚑ 제목 과장·왜곡 점검에 걸림: ${r.headline_consistency__evidence}`);
  if (r.promotional) L.push("", ` ⚑ 홍보·광고성 점검에 걸림: ${r.promotional__evidence}`);
  if (r.flags?.length) { L.push("", " 사람이 직접 확인할 것"); for (const f of r.flags) L.push(`   · ${f}`); }

  if (state.norms) {
    const [ck, cell] = E.pickCell(state.norms, r.genre, m.len_bin);
    L.push("", `[2단계] 비슷한 기사들 사이에서의 위치 — 비교 대상 '${ck}' (${cell.n.toLocaleString()}건)`,
      "           P50 = 딱 중간, P90 = 상위 10%. 가중치 없이 그대로 비교함", "");
    for (const [code, key, label] of E.ALL_ITEMS) {
      const v = r[key], p = E.itemPercentile(cell, key, v);
      if (p === null) { L.push(` ${code.padEnd(4)} ${label.padEnd(12)} –`); continue; }
      const pos = Math.min(Math.floor(p / 100 * 24), 23);
      const bar = "·".repeat(pos) + "▲" + "·".repeat(23 - pos);
      const shown = key === "term_explanation_rate" ? v + "%" : String(v);
      L.push(` ${code.padEnd(4)} ${label.padEnd(12)} ${shown.padStart(5)}  P${String(Math.round(p)).padStart(3)}  |${bar}|`);
    }
    L.push("", "  ※ C1 이해 난이도와 C2 설명 노력은 반대 방향으로 움직이는 값임(상관 −0.28).",
      "     더하지 말고 두 값을 나란히 읽을 것.");
    const p3 = E.weightInterval(r, state.norms);
    if (p3) {
      L.push("", `[3단계] 가중치를 바꿔도 흔들리지 않는 순위 범위`,
        `           중요도 배분 ${p3.n_draw.toLocaleString()}가지 (순서만 고정: A≥C≥D≥B)`,
        `           전체 기사 대비 순위: 평균 P${Math.round(p3.mean)}  ` +
        `범위 P${Math.round(p3.lo)} ~ P${Math.round(p3.hi)}`,
        "           → 어떤 중요도 배분을 쓰더라도 순위는 이 범위 안에 머무름.",
        "           → 범위가 좁으면 평가가 잘 안 갈리는 기사, 넓으면 관점 따라 갈리는 기사.");
    }
  }
  L.push("", "-".repeat(74),
    `모델 ${E.MODEL} · 반복 채점 ${r.n_repeats}회 · 추정 비용 $${G.costUsd().toFixed(4)}`,
    "EJQI v3 — 총점(단일 종합점수)을 산출하지 않음. 3단계로 나눠 보는 것이 설계임.");
  return L.join("\n");
}

function asCsv(r) {
  const d = E.dimScores(r), m = r.meta || {};
  const row = { genre: r.genre };
  for (const [, k] of E.ALL_ITEMS) row[k] = r[k];
  Object.assign(row, {
    dim_A: d.A, dim_B: d.B, dim_C: d.C, dim_D: d.D,
    effort_na: r.effort_na, promotional: r.promotional, promotional_type: r.promotional_type,
    headline_overstated: r.headline_overstated, sentiment_balance: r.sentiment_balance,
    n_sources: r.n_sources, n_sources_named: r.n_sources_named, n_terms: r.n_terms,
    n_terms_unexplained: r.n_terms_unexplained, n_blockers: r.n_blockers,
    term_window_last: r.term_window_last, window_chars: r.window_chars,
    window_ratio: r.window_ratio, n_paragraphs: r.n_paragraphs, n_repeats: r.n_repeats,
    press: m.press, topic: m.topic, title: m.title, body_len: m.body_len, len_bin: m.len_bin,
  });
  const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  return Object.keys(row).join(",") + "\n" + Object.values(row).map(q).join(",");
}

// ══════════ ENDC ══════════
function mdLite(s) {
  // 최소한의 마크다운만 처리한다 (외부 라이브러리 없이)
  let h = esc(s);
  h = h.replace(/```([\s\S]*?)```/g, (m, c) => `<pre>${c}</pre>`);
  h = h.replace(/`([^`\n]+)`/g, "<code>$1</code>");
  h = h.replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>");
  const lines = h.split("\n");
  const out = []; let inTbl = false, inList = false;
  const closeList = () => { if (inList) { out.push("</ul>"); inList = false; } };
  const closeTbl = () => { if (inTbl) { out.push("</tbody></table></div>"); inTbl = false; } };
  for (const ln of lines) {
    const t = ln.trim();
    if (/^\|.*\|$/.test(t)) {
      const cells = t.split("|").slice(1, -1).map((c) => c.trim());
      if (/^[-: ]+$/.test(cells.join(""))) continue;
      if (!inTbl) { closeList(); out.push('<div class="tbl-wrap"><table><tbody>'); inTbl = true; }
      out.push("<tr>" + cells.map((c) => `<td>${c}</td>`).join("") + "</tr>");
      continue;
    }
    closeTbl();
    if (/^[-*·]\s+/.test(t) || /^\d+\.\s+/.test(t)) {
      if (!inList) { out.push("<ul>"); inList = true; }
      out.push("<li>" + t.replace(/^([-*·]|\d+\.)\s+/, "") + "</li>");
      continue;
    }
    closeList();
    if (/^#{1,6}\s/.test(t)) out.push(`<p><b>${t.replace(/^#+\s*/, "")}</b></p>`);
    else if (t) out.push(`<p>${t}</p>`);
  }
  closeList(); closeTbl();
  return out.join("");
}

function renderChat(typing) {
  const box = $("chatBox");
  if (!state.chat.length && !typing) {
    box.innerHTML = `<p class="muted">경제 뉴스 데스크 챗봇 — 기사 초고를 놓고 상의하는 상대임.<br><br>
      · 왼쪽에 초고를 붙여넣고 <b>빠른 질문</b> 버튼을 누르거나, 아래 칸에 직접 질문<br>
      · EJQI 기준이 무엇인지, 특정 항목을 어떻게 채우는지도 질문 가능<br>
      · 초고 없이 경제 저널리즘 일반에 대해 물어봐도 됨</p>`;
    return;
  }
  box.innerHTML = state.chat.map((m) => m.role === "user"
    ? `<div class="msg me"><div class="av">🧑‍💻</div><div class="bd">${esc(m.text)}</div></div>`
    : `<div class="msg"><div class="av">🗞</div><div class="bd">${mdLite(m.text)}</div></div>`).join("")
    + (typing ? '<div class="msg"><div class="av">🗞</div><div class="bd typing">'
        + '<span class="spin"></span> 데스크가 읽는 중…</div></div>' : "");
  box.scrollTop = box.scrollHeight;
}

async function send(text) {
  if (state.busy) return;
  const msg = (text || "").trim();
  if (!msg) return;
  const key = requireKey("chatMsg");
  if (!key) return;
  $("chatMsg").innerHTML = "";
  $("chatInput").value = "";

  const ctx = buildContext($("cDraft").value, state.result, $("cbAttach").checked);
  state.chat.push({ role: "user", text: msg, payload: ctx ? `${ctx}\n\n[질문]\n${msg}` : msg });
  renderChat(true);

  state.busy = true; $("btnSend").disabled = true;
  try {
    const answer = await G.generateChat({
      apiKey: key, model: E.MODEL, system: await systemPrompt(),
      messages: state.chat.map((m) => ({
        role: m.role, text: m.role === "user" ? m.payload : m.text })),
      onRetry: () => renderChat(true),
    });
    state.chat.push({ role: "assistant", text: answer });
    refreshUsage();
  } catch (e) {
    state.chat.pop();
    const cls = e instanceof G.ApiKeyError ? "🔑" : (e instanceof G.QuotaError ? "⏳" : "⚠");
    $("chatMsg").innerHTML = `<div class="note err">${cls} ${esc(e.message)}</div>`;
  } finally {
    state.busy = false; $("btnSend").disabled = false; renderChat();
  }
}
