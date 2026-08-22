# -*- coding: utf-8 -*-
"""인용 검증 + 파생 지표 산출.

LLM이 내놓은 인용(evidence·terms·blockers)이 본문에 실재하는지 코드로 확인한다.
LLM 추가 호출은 0회다.

용어 제외율의 내역 (review_300, 추출 시도 1,128개)
  창 밖 문단          30개 (2.66%)  ← 규칙 위반. 환각이 아니다
  본문에 없음           2개 (0.18%)  ← 진짜 환각
  인용 문장 불일치        0개
`n_terms_halluc`는 이 셋의 합이므로 그대로 환각률로 보고하면 15배 부풀려진다.
사유별 내역은 `halluc_reasons`에 있다.

검증 실패 처리
  evidence  : 점수는 유지하되 `evidence_status='absent'`로 표시 (신뢰도 플래그)
  terms     : **분모에서 제외**. 존재하지 않는 용어로 해설률을 계산할 수 없다
  blockers  : **제외**. 근거 산출물이므로 실재하지 않으면 쓸 수 없다
"""
from __future__ import annotations

import difflib
import re
from typing import Iterable

from .config import (PARA_MAX, PARA_MIN, QUOTE_FUZZY_THRESHOLD,
                     QUOTE_MIN_LEN, TERM_WINDOW_CHARS, norm_ws)
from .schema import BLOCKER_TYPES, EXPLAIN_LEVEL, SCORED_ITEMS

_SENT_SPLIT = re.compile(r"(?<=다)[.。]\s+|(?<=[.!?])\s+")


def split_paragraphs(body: str) -> list[str]:
    """본문을 문단으로 나눈다.

    네이버 본문은 개행이 사라진 경우가 많아, 개행이 부족하면 문장 3개씩 묶는다.
    문단 번호는 프롬프트의 순회 강제(§16.3)에 쓰인다.
    """
    parts = [p.strip() for p in re.split(r"\n{1,}", body) if p.strip()]
    if len(parts) < 3:
        sents = [s for s in _SENT_SPLIT.split(body) if s.strip()]
        parts = [" ".join(sents[i:i + 3]) for i in range(0, len(sents), 3)]
    # 문장 분리가 실패해 한 덩어리로 남는 경우(인사 명단·표 형식 기사 등)
    # 창 고정이 무의미해지므로 글자 수로 강제 분할한다.
    split_parts: list[str] = []
    for p in parts:
        if len(p) <= PARA_MAX:
            split_parts.append(p)
        else:
            for i in range(0, len(p), PARA_MAX):
                split_parts.append(p[i:i + PARA_MAX])
    merged: list[str] = []
    for p in split_parts:
        if merged and len(merged[-1]) < PARA_MIN:
            merged[-1] += " " + p
        else:
            merged.append(p)
    return merged or [body]


def number_paragraphs(paras: Iterable[str]) -> str:
    return "\n\n".join(f"[P{i}] {p}" for i, p in enumerate(paras, 1))


def term_window(paras: list[str], chars: int = TERM_WINDOW_CHARS) -> tuple[int, int]:
    """용어 추출 창 = 누적 글자수가 `chars`에 닿는 문단까지.

    반환 (마지막 문단 번호, 창의 실제 글자수).
    문단 경계에서 끊으므로 실제 글자수는 chars를 조금 넘거나 못 미친다.
    이 실제 값을 밀도의 분모로 쓴다 — 그래야 기사 간 비교가 성립한다.

    왜 문단 수가 아니라 글자 수인가: 문단 크기가 129~309자로 편차가 커
    "앞 5문단"이 기사마다 다른 분량이 된다(본문의 31~98%). 글자로 끊으면
    분모가 고정된다.
    """
    acc = 0
    for i, p in enumerate(paras, 1):
        nxt = acc + len(p)
        if nxt >= chars:
            # 목표에 더 가까운 쪽에서 끊는다 (초과 vs 미달)
            if i > 1 and (nxt - chars) > (chars - acc):
                return i - 1, acc
            return i, nxt
        acc = nxt
    return len(paras), acc


def quote_status(quote: str, body_norm: str) -> str:
    """'exact' | 'fuzzy' | 'absent' | 'empty'."""
    q = norm_ws(quote)
    if not q or q in ("없음", "해당 없음", "해당없음") or len(q) < QUOTE_MIN_LEN:
        return "empty"
    if q in body_norm:
        return "exact"
    probe = q[:40]
    n = len(probe)
    for i in range(0, max(len(body_norm) - n, 0) + 1, 5):
        if difflib.SequenceMatcher(None, probe, body_norm[i:i + n]).ratio() >= QUOTE_FUZZY_THRESHOLD:
            return "fuzzy"
    return "absent"


def verify(result: dict, body: str, n_para: int,
           win_last: int = 0, win_chars: int = 0) -> dict:
    """EJQIv3 원 결과 + 본문 → 검증된 지표 dict.

    win_last / win_chars = 용어 추출 창(문단 번호, 글자수).
    용어 밀도의 분모는 본문 전체가 아니라 **창 글자수**다.
    """
    body_norm = norm_ws(body)
    win_chars = win_chars or len(body)
    win_last = win_last or n_para
    kilo = max(win_chars, 1) / 1000
    out: dict = {"genre": result["genre"], "genre_reason": result["genre_reason"],
                 "term_window_last": win_last, "window_chars": win_chars,
                 "window_ratio": round(win_chars / max(len(body), 1), 3)}

    # ── 채점 항목 + evidence 검증 ─────────────────────────
    ev_absent = 0
    for _, key, _, _ in SCORED_ITEMS:
        item = result[key]
        out[key] = item["score"]
        st = quote_status(item["evidence"], body_norm)
        out[f"{key}__ev"] = st
        ev_absent += (st == "absent")
    out["evidence_absent"] = ev_absent
    out["effort_na"] = bool(result["effort_na"])

    # ── 취재원 ────────────────────────────────────────────
    srcs = result.get("sources", [])
    out["n_sources"] = len(srcs)
    out["n_sources_named"] = sum(1 for s in srcs if s["transparent"])
    out["n_sources_interest"] = sum(1 for s in srcs if s["interest_disclosed"])
    out["n_anon_reasoned"] = sum(
        1 for s in srcs
        if not s["transparent"] and s["anonymity_reason"] not in ("없음", ""))
    out["source_types"] = [s["econ_source_type"] for s in srcs]
    out["n_sources_anon"] = sum(1 for s in srcs if not s["transparent"])
    # 취재원은 **기사 전체**([P1]~[P{n_paras}])에서 뽑는다. 용어와 달리 분석 창을 걸지 않는다.
    #   반론·전문가 취재원은 기사 뒤쪽에 배치되는 일이 잦아, 창을 걸면
    #   A3(검증·반론) 판정이 왜곡되기 때문임.
    #   ※ 취재원 밀도(1,000자당 명수)는 산출하지 않기로 확정됨(2026-08).
    #     창을 고정해도 길이 교란이 남아 지표로 쓸 수 없고,
    #     화면에서 '창 안 O명'으로 오독될 소지가 컸음.
    # 취재원 목록 원본 — 매체×취재원 인용 네트워크 등 배치 분석에 필요하다
    # (개정안 §7: 매체 단위 취재원 편중은 단건 엔트로피보다 타당도가 높다)
    out["sources"] = srcs

    # ── 용어 (검증 통과분만) ──────────────────────────────
    verified, halluc = [], []
    for t in result.get("terms", []):
        term_ok = bool(norm_ws(t["term"])) and norm_ws(t["term"]) in body_norm
        sent_ok = quote_status(t.get("first_sentence", ""), body_norm) in ("exact", "fuzzy")
        # 창 밖 문단의 용어는 규칙 위반이므로 제외한다(분모를 고정하기 위함)
        para_ok = 1 <= int(t.get("para", 0)) <= max(win_last, 1)
        if term_ok and sent_ok and para_ok:
            verified.append(t)
        else:
            # 제외 사유는 셋이고 함의가 전혀 다르다. 개수만 세면 "창 밖에서 뽑았다"가
            # "없는 용어를 지어냈다"로 보고돼 환각률이 부풀려진다.
            halluc.append((t["term"],
                           "본문에 없음" if not term_ok else
                           "인용 문장 불일치" if not sent_ok else "창 밖 문단"))
    lv = {k: sum(1 for t in verified if t["explained"] == k) for k in EXPLAIN_LEVEL}
    n_ok = len(verified)
    out["n_terms"] = n_ok
    out["n_terms_halluc"] = len(halluc)
    # 개수만 남기면 무엇이 걸러졌는지 확인할 수 없다. unexplained_terms와 같은 이유로
    # 이름까지 보존한다 — 환각 사례 검수는 이 목록이 있어야 가능하다.
    out["halluc_terms"] = [term for term, _ in halluc]
    out["halluc_reasons"] = {r: sum(1 for _, x in halluc if x == r)
                             for r in ("본문에 없음", "인용 문장 불일치", "창 밖 문단")}
    out["term_levels"] = lv
    out["n_terms_unexplained"] = lv["없음"]
    out["unexplained_terms"] = [t["term"] for t in verified if t["explained"] == "없음"]
    # 웹 배포판 추가 — 검증 통과 용어의 원본을 남긴다.
    # 화면에서 "어느 문단의 어떤 용어를 어느 수준으로 설명했는가"를 표로 보여주기 위함이다.
    # 연구 본편은 파일 크기 때문에 개수·이름만 남긴다.
    out["terms_detail"] = [{"para": t["para"], "term": t["term"],
                            "explained": t["explained"],
                            "first_sentence": t["first_sentence"]} for t in verified]
    # C3 용어 해설률 — 파일럿에서 유일하게 노이즈 경계를 넘은 지표(§16.3)
    out["term_explanation_rate"] = (
        round(sum(EXPLAIN_LEVEL[t["explained"]] for t in verified) / n_ok * 100, 1)
        if n_ok else None)
    # 밀도는 창 고정 후에도 길이 교란 r=−0.34가 남아 점수로 쓰지 않는다(§16.5)
    out["term_density"] = round(n_ok / kilo, 2)
    out["para_coverage"] = (round(len({t["para"] for t in verified}) / max(win_last, 1), 2)
                            if n_ok else 0.0)

    # ── 막히는 지점 (검증 통과분만) ───────────────────────
    bl = [b for b in result.get("blockers", [])
          if quote_status(b.get("sentence", ""), body_norm) in ("exact", "fuzzy")]
    out["n_blockers"] = len(bl)
    out["n_blockers_halluc"] = len(result.get("blockers", [])) - len(bl)
    out["blocker_types"] = {t: sum(1 for b in bl if b["reason"] == t)
                            for t in BLOCKER_TYPES}
    out["blockers"] = [{"sentence": b["sentence"], "reason": b["reason"],
                        "note": b["note"]} for b in bl]

    # ── 게이트 ────────────────────────────────────────────
    # 저장되는 값은 Gate.flagged다. **True가 '문제 있음'**이다.
    # headline_consistency라는 이름은 True를 '정합'으로 읽게 만들어 뜻이 뒤집힌다.
    # headline_overstated(제목 과장·왜곡)를 정식 이름으로 쓰고 구 이름을 남긴다.
    for key in ("headline_consistency", "promotional"):
        g = result[key]
        out[key] = bool(g["flagged"])
        out[f"{key}__evidence"] = g["evidence"]
    out["headline_overstated"] = out["headline_consistency"]
    out["headline_overstated__evidence"] = out["headline_consistency__evidence"]
    out["sentiment_balance"] = result["sentiment_balance"]["score"]
    out["sentiment_balance__ev"] = quote_status(
        result["sentiment_balance"]["evidence"], body_norm)

    # ── 근거 텍스트 보존 (진단 카드용) ────────────────────
    out["_evidence"] = {key: {"evidence": result[key]["evidence"],
                              "reasoning": result[key]["reasoning"]}
                        for _, key, _, _ in SCORED_ITEMS}
    out["n_paragraphs"] = n_para
    out["n_paragraphs_claimed"] = int(result.get("n_paragraphs_checked", 0))
    out["promotional_type"] = result.get("promotional_type", "해당없음")
    return out


def reliability_flags(scored: dict) -> list[str]:
    """인간 검수를 권하는 신호."""
    flags = []
    if scored["evidence_absent"] >= 2:
        flags.append(
            f"근거 인용 {scored['evidence_absent']}건이 본문에서 확인되지 않음 — 환각 가능성")
    if scored["n_terms_halluc"] > 0:
        flags.append(f"전문용어 {scored['n_terms_halluc']}개가 본문에 없음(집계 제외)")
    if scored["effort_na"]:
        flags.append("어려운 내용이 없어 '설명 노력' 평가 불가 — 척도 적용이 제한적인 기사")
    if scored["n_terms"] == 0:
        flags.append("추출된 전문용어 0개 — 용어 해설률 산출 불가")
    if scored["n_sources"] == 0:
        flags.append("명시된 취재원 없음 — B차원 해석에 주의")
    if scored["para_coverage"] and scored["para_coverage"] < 0.35:
        flags.append(
            f"용어가 문단의 {scored['para_coverage']:.0%}에서만 추출됨 — 과소추출 가능성")
    return flags
