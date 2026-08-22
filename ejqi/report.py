# -*- coding: utf-8 -*-
"""3층 산출 — 단일 EJQI 점수를 대체한다.

  Layer 1  진단 카드    항목별 등급 + 근거 문장 + 막히는 지점 (점수 없음)
  Layer 2  규준 프로파일 비교군 내 백분위 (가중치 개입 없음)
  Layer 3  구간 추정    서수 제약만 건 가중치 1,000조합의 백분위 95% 구간

Layer 1이 주 산출이다. 전문가 인터뷰가 요구한 형태이며
("점수보다 근거가 중요합니다. 어느 문장이 왜 감점인지 제시하고" — I08),
"주관적 가치를 점수화·정규화하기 어렵다"는 비판(I02)에 대한 직접적 답이기도 하다.

주의 — 이해 가능성(C)은 단일 점수로 합치지 않는다.
`difficulty`(난이도)와 `effort`(설명 노력)는 r = −0.28로 반대 방향이다.
"""
from __future__ import annotations

from . import norms as _norms
from .schema import DERIVED_ITEMS, DIM_NAMES, SCORED_ITEMS

_DIM_SEQ = {"A": 0, "B": 1, "C": 2, "D": 3}
ALL_ITEMS = sorted(SCORED_ITEMS + DERIVED_ITEMS,
                   key=lambda t: (_DIM_SEQ.get(t[3], 9), t[0]))

GRADE = [(4.5, "충족", "●"), (3.0, "대체로 충족", "◐"),
         (1.5, "부분 충족", "○"), (-1, "미충족", "✗")]

# 항목별 한 줄 해설 — 화면에서 물음표 아이콘으로 노출한다
ITEM_HELP = {
    "numeric_context": "핵심 수치에 비교 기준선(전년 동기·컨센서스·과거 시계열·경쟁사)·시점·출처가 붙는가",
    "causal_uncertainty": "인과 메커니즘이 제시되고, 확인된 사실과 전망이 구분되는가",
    "verification": "발표·보도자료를 그대로 옮기지 않고 교차 확인하거나 반대 근거를 담는가",
    "impact_scope": "영향을 받는 주체가 열거되고 시간 지평(단기/중장기)이 언급되는가",
    "interest_disclosure": "인용된 취재원이 어떤 이해관계에 서 있는지 독자가 알 수 있는가",
    "difficulty": "경제 지식이 없는 일반 성인이 이 기사만 읽고 이해할 수 있는가 (높을수록 쉬움. 품질 아님)",
    "effort": "어려운 내용이 실제로 등장하는데도 비전문가가 따라갈 수 있게 쓰였는가",
    "term_explanation_rate": "전문용어의 해설 수준 가중 비율. 없음 0 · 사전적 0.5 · 맥락번역 0.85 · 중요성설명 1.0",
    "scaffold_number": "핵심 수치가 독자 체감으로 환산되는가(절약액·부담액·1인당·월 단위)",
    "scaffold_case": "사례·비유·현장 목소리로 추상적 지표를 구체화하는가",
    "background": "선행 맥락, 장기 추세, 사이클 안에서의 위치가 제시되는가",
    "reader_implication": "이 정보가 왜 중요한지, 독자의 삶·자산·의사결정에 어떤 의미인지 설명되는가",
}

# 본 연구 전량 30,178건의 참고 평균 — 화면에 함께 띄운다
CORPUS_MEAN = {
    "numeric_context": 2.238, "causal_uncertainty": 3.219, "verification": 1.250,
    "impact_scope": 2.551, "interest_disclosure": 2.832, "difficulty": 4.201,
    "effort": 1.858, "term_explanation_rate": 13.50, "scaffold_number": 1.705,
    "scaffold_case": 1.857, "background": 2.536, "reader_implication": 1.185,
}


def grade(score) -> tuple[str, str]:
    if score is None:
        return "해당 없음", "–"
    for th, label, mark in GRADE:
        if score >= th:
            return label, mark
    return "미충족", "✗"


def scale5(key: str, v):
    """용어 해설률(0–100)을 등급 판정을 위해 0–5로 환산."""
    if v is None:
        return None
    return v / 20.0 if key == "term_explanation_rate" else v


def dim_scores(r: dict) -> dict:
    """차원 평균. **이 값들을 다시 합산하지 말 것.**"""
    out = {}
    for d, keys in _norms.DIMS.items():
        vals = [r[k] for k in keys if r.get(k) is not None]
        out[d] = round(sum(vals) / len(vals), 3) if vals else None
    return out


def layer1(r: dict) -> dict:
    """진단 카드 — 점수 대신 등급과 근거."""
    ev = r.get("_evidence", {})
    rows = []
    for code, key, label, dim in ALL_ITEMS:
        v = r.get(key)
        s5 = scale5(key, v)
        g, mark = grade(s5)
        note = ""
        if key == "effort" and r.get("effort_na"):
            g, mark, note = "평가 불가", "–", "어려운 내용이 없음 — 감점이 아님"
        e = ev.get(key, {})
        rows.append({
            "code": code, "key": key, "label": label, "dim": dim,
            "value": v,
            "shown": ("–" if v is None else
                      (f"{v:.0f}%" if key == "term_explanation_rate" else f"{v:g}")),
            "grade": g, "mark": mark, "note": note,
            "evidence": e.get("evidence", ""), "reasoning": e.get("reasoning", ""),
            "corpus_mean": CORPUS_MEAN.get(key),
            "help": ITEM_HELP.get(key, ""),
        })
    gates = []
    if r.get("headline_overstated", r.get("headline_consistency")):
        gates.append(("G1 제목 과장·왜곡", r.get("headline_consistency__evidence", "")))
    if r.get("promotional"):
        gates.append(("G5 홍보·광고성", r.get("promotional__evidence", "")))
    return {"items": rows, "gates": gates, "flags": r.get("flags", [])}


def layer2(r: dict, topic: str = "") -> dict | None:
    """규준 프로파일 — 비교군 내 백분위. 가중치 개입 없음."""
    nm = _norms.load()
    if not nm:
        return None
    key, cell = _norms.pick_cell(nm, r.get("genre", "?"),
                                 r.get("meta", {}).get("len_bin", "?"))
    if not cell:
        return None
    rows = []
    for code, item, label, dim in ALL_ITEMS:
        v = r.get(item)
        p = _norms.item_percentile(cell, item, v)
        rows.append({"code": code, "key": item, "label": label, "dim": dim,
                     "value": v, "pct": p,
                     "shown": ("–" if v is None else
                               (f"{v:.0f}%" if item == "term_explanation_rate" else f"{v:g}"))})
    return {"cell": key, "n": cell["n"], "rows": rows, "topic": topic}


def layer3(r: dict) -> dict | None:
    return _norms.weight_interval(r)


def as_text(r: dict) -> str:
    """다운로드용 텍스트 리포트."""
    m = r.get("meta", {})
    L = ["=" * 74,
         f"{m.get('press', '(매체 미입력)')} · {m.get('topic', '')} · "
         f"{m.get('body_len', 0):,}자 · 장르 {r.get('genre', '')}",
         f"제목: {(m.get('title') or '')[:70]}",
         "=" * 74, "",
         "[1단계] 항목별 진단 — 점수 없음, 등급과 근거만", ""]
    solo = {"difficulty", "term_explanation_rate"}
    c = layer1(r)
    for it in c["items"]:
        L.append(f" {it['mark']} {it['code']:4s} {it['label']:12s} {it['grade']}"
                 + (f"  ({it['note']})" if it["note"] else "")
                 + ("   [차원 밖 단독 지표]" if it["key"] in solo else ""))
        if it["evidence"]:
            L.append(f"      근거: {it['evidence'][:70]}")
        if it["reasoning"] and (it["value"] is not None
                                and (scale5(it["key"], it["value"]) or 0) <= 2):
            L.append(f"      결손: {it['reasoning'][:66]}")
    if r.get("unexplained_terms"):
        L += ["", f" 미해설 전문용어 ({len(r['unexplained_terms'])}개)",
              "   " + ", ".join(r["unexplained_terms"][:20])]
    if r.get("blockers"):
        L += ["", f" 비전문가가 막히는 문장 ({len(r['blockers'])}개)"]
        for b in r["blockers"][:8]:
            L.append(f"   [{b['reason']}] {b['sentence'][:58]}")
            L.append(f"      → {b['note'][:50]}")
    for name, e in c["gates"]:
        L += ["", f" ⚑ {name} 발동: {str(e)[:60]}"]
    if c["flags"]:
        L += ["", " 신뢰도 참고"] + [f"   · {f}" for f in c["flags"]]

    p2 = layer2(r)
    if p2:
        L += ["", f"[2단계] 비슷한 기사들 사이에서의 위치 — 비교군 '{p2['cell']}' (n={p2['n']:,})",
              "           ※ 가중치 개입 없음", ""]
        for row in p2["rows"]:
            if row["pct"] is None:
                L.append(f" {row['code']:4s} {row['label']:12s} –")
                continue
            pos = min(int(row["pct"] / 100 * 24), 23)
            bar = "·" * 24
            bar = bar[:pos] + "▲" + bar[pos + 1:]
            L.append(f" {row['code']:4s} {row['label']:12s} {row['shown']:>5s}  "
                     f"P{row['pct']:>3.0f}  |{bar}|")
        L += ["", "  ※ C1 이해 난이도와 C3 용어 해설률은 C 차원 평균에 넣지 않는 단독 지표다",
              "     (C 차원 = C2·C4·C5).",
              "  ※ C1 이해 난이도와 C2 설명 노력은 반대 방향의 지표다(r = −0.28).",
              "     합산하지 말고 두 값을 나란히 읽을 것."]

    p3 = layer3(r)
    if p3:
        L += ["", f"[3단계] 가중치를 바꿔도 흔들리지 않는 백분위 범위 — 서수 제약(A≥C≥D≥B)만 건 {p3['n_draw']:,}개 조합",
              "           2단계와 같은 백분위 P○ (숫자가 클수록 상위). 비교 상대만 전체 기사로 바뀐다",
              f"           전체 {p3['n_pop']:,}건 대비: 평균 P{p3['mean']:.0f}  "
              f"흔들리는 폭 [P{p3['lo']:.0f}, P{p3['hi']:.0f}]",
              "           → 어떤 가중치를 써도 백분위가 이 폭을 벗어나지 않는다."]
    u = m.get("usage", {})
    L += ["", "-" * 74,
          f"모델 gemini-3.1-flash-lite · 호출 {u.get('calls', 0)}회 · "
          f"토큰 in {u.get('input_tokens', 0):,} / out {u.get('output_tokens', 0):,} · "
          f"추정 비용 ${m.get('cost_usd', 0):.4f}",
          "EJQI v3 — 하나로 합친 총점은 내지 않음. 3단계로 나눠 보는 것이 설계임."]
    return "\n".join(L)
