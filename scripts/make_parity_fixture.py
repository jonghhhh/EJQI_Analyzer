# -*- coding: utf-8 -*-
"""JS 포팅 검증용 고정자료 생성.

연구 본편(ejqi/verify.py)을 실제 기사에 돌린 결과를 저장한다.
parity_test.mjs 가 같은 입력으로 web/js/ejqi.js 를 돌려 한 글자라도 다르면 실패로 잡는다.

  python web/scripts/make_parity_fixture.py --n 200

검증 범위
  · split_paragraphs   문단 분할 (문장 분리 규칙 포함)
  · term_window        분석 창
  · quote_status       인용 대조 (exact / fuzzy / absent / empty 네 경로 모두)
  · verify             전체 파생 지표
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # 저장소 루트(ejqi/ 가 있는 곳)
sys.path.insert(0, str(ROOT))
# 원본 코퍼스는 이 저장소에 없다. 연구 저장소 경로를 EJQI_CORPUS 로 넘긴다.
CORPUS = os.getenv("EJQI_CORPUS",
                   str(ROOT.parent / "naver_news" / "naver_econ_articles.jsonl"))

from ejqi.schema import BLOCKER_TYPES, EXPLAIN_LEVEL, SCORED_ITEMS, SOURCE_TYPES
from ejqi.verify import (number_paragraphs, split_paragraphs, quote_status,
                         term_window, verify, norm_ws)

PROMO_TYPES = ["해당없음", "신제품·서비스 출시", "행사·전시·캠페인", "수상·인증·평가",
               "실적·성과 홍보", "협약·MOU·투자유치", "CSR·ESG 활동",
               "인사·조직 개편", "기타 홍보"]


def synth_raw(body: str, paras: list[str], win_last: int, rng: random.Random) -> dict:
    """진짜 LLM 출력과 같은 모양의 입력을 만든다.

    exact / fuzzy / absent / empty 네 경로가 모두 밟히도록 일부러 섞는다.
      · 본문 그대로 잘라낸 인용        → exact
      · 한 글자 바꾼 인용              → fuzzy 또는 absent
      · 본문에 없는 문장               → absent
      · "없음" 또는 7자 이하           → empty
    """
    body_cut = [body[i:i + rng.randint(12, 60)]
                for i in range(0, max(len(body) - 60, 1), max(len(body) // 12, 1))]
    body_cut = [c for c in body_cut if len(c.strip()) >= 10] or [body[:40]]

    def a_quote():
        r = rng.random()
        if r < 0.55:
            return rng.choice(body_cut)                       # exact
        if r < 0.70:
            s = rng.choice(body_cut)
            k = len(s) // 2
            return s[:k] + "☆" + s[k + 1:]                     # fuzzy 경계
        if r < 0.85:
            return "이 문장은 본문 어디에도 존재하지 않는 임의의 문자열입니다"   # absent
        return rng.choice(["없음", "해당없음", "해당 없음", "짧음", ""])        # empty

    raw = {"genre": rng.choice(["시황", "스트레이트", "분석해설", "기획탐사", "논평"]),
           "genre_reason": "검증용 합성 결과"}
    for _, key, _, _ in SCORED_ITEMS:
        raw[key] = {"evidence": a_quote(), "reasoning": "합성 판정 근거",
                    "score": rng.randint(0, 5)}
    raw["effort_na"] = rng.random() < 0.4
    raw["n_paragraphs_checked"] = len(paras)
    raw["term_window_last"] = win_last

    raw["sources"] = [{
        "para": rng.randint(1, max(len(paras), 1) + 1),        # 창 밖·범위 밖도 섞는다
        "name": f"취재원{i}",
        "transparent": rng.random() < 0.7,
        "econ_source_type": rng.choice(SOURCE_TYPES),
        "anonymity_reason": rng.choice(["없음", "", "익명을 요구한"]),
        "interest_disclosed": rng.random() < 0.3,
    } for i in range(rng.randint(0, 8))]

    raw["terms"] = [{
        "para": rng.randint(0, max(len(paras), 1) + 1),        # 0·창 밖도 섞어 규칙 위반 경로 확인
        "term": (rng.choice(body_cut)[:6].strip() if rng.random() < 0.7 else "없는용어XYZ"),
        "first_sentence": a_quote(),
        "explained": rng.choice(list(EXPLAIN_LEVEL)),
    } for _ in range(rng.randint(0, 10))]

    raw["blockers"] = [{
        "sentence": a_quote(), "reason": rng.choice(BLOCKER_TYPES), "note": "합성",
    } for _ in range(rng.randint(0, 6))]

    for key in ("headline_consistency", "promotional"):
        raw[key] = {"flagged": rng.random() < 0.3, "evidence": a_quote()}
    raw["sentiment_balance"] = {"evidence": a_quote(), "reasoning": "합성",
                                "score": rng.randint(0, 5)}
    raw["promotional_type"] = rng.choice(PROMO_TYPES)
    return raw


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--source", default=CORPUS)
    ap.add_argument("--out", default=str(Path(__file__).parent / "_fixture.json"))
    ap.add_argument("--seed", type=int, default=20260817)
    a = ap.parse_args()

    rng = random.Random(a.seed)
    rows = []
    with open(a.source, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            b = r.get("body") or ""
            if len(b) >= 400:
                rows.append({"body": b, "title": r.get("title", "")})
    rng.shuffle(rows)
    rows = rows[:a.n]
    # 길이 극단도 반드시 포함시킨다
    rows.sort(key=lambda r: len(r["body"]))
    print(f"표본 {len(rows)}건 · 본문 {len(rows[0]['body'])}~{len(rows[-1]['body'])}자")

    cases = []
    for r in rows:
        body = r["body"]
        paras = split_paragraphs(body)
        win_last, win_chars = term_window(paras)
        raw = synth_raw(body, paras, win_last, rng)
        scored = verify(raw, body, len(paras), win_last, win_chars)

        # 인용 대조 단독 검증용 표본
        qs = [raw[k]["evidence"] for _, k, _, _ in SCORED_ITEMS]
        qs += [t["first_sentence"] for t in raw["terms"]]
        qs += [b["sentence"] for b in raw["blockers"]]
        body_norm = norm_ws(body)
        quotes = [{"q": q, "status": quote_status(q, body_norm)} for q in qs]

        cases.append({
            "body": body, "title": r["title"], "raw": raw,
            "paragraphs": paras,
            "numbered_head": number_paragraphs(paras)[:200],
            "win_last": win_last, "win_chars": win_chars,
            "quotes": quotes,
            "scored": scored,
        })

    Path(a.out).write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    n_q = sum(len(c["quotes"]) for c in cases)
    from collections import Counter
    st = Counter(q["status"] for c in cases for q in c["quotes"])
    print(f"저장: {a.out} ({Path(a.out).stat().st_size/1e6:.1f}MB)")
    print(f"  문단 총 {sum(len(c['paragraphs']) for c in cases):,}개")
    print(f"  인용 {n_q:,}건 — {dict(st)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
