# -*- coding: utf-8 -*-
"""단건 평가 진입점 (웹 배포판).

  evaluate(api_key, article)            1회 채점
  evaluate(api_key, article, repeat=3)  N회 반복 평균

반복 채점에 대하여
  항목 단위 자기일관성은 r₁ = 0.50이다(temperature 0.7 기준).
  개별 기사의 **항목 점수를 확정적으로 쓰려면** N=3~5 반복 평균이 필요하다.
  temperature=0에서는 재실행이 결정적이므로 반복 시 자동으로 온도를 올린다.
"""
from __future__ import annotations

from statistics import mean, pstdev

from . import prompts
from .config import BLOCKER_CAP, TERM_CAP, len_bin, media_type
from .llm import Usage, generate, make_client
from .schema import Article, DERIVED_ITEMS, EJQIv3, SCORED_ITEMS
from .verify import (number_paragraphs, reliability_flags, split_paragraphs,
                     term_window, verify)

REPEAT_TEMPERATURE = 0.7
_NUMERIC = [k for _, k, _, _ in SCORED_ITEMS] + [k for _, k, _, _ in DERIVED_ITEMS]


def _score_once(cli, art: Article, usage: Usage, temperature):
    paras = split_paragraphs(art.body)                 # ① 의사 문단 생성
    win_last, win_chars = term_window(paras)           # ② 용어 추출 창 확정
    prompt = prompts.build(art.title, art.subtitle,
                           number_paragraphs(paras),   # ③ [P1] [P2] … 번호 부여
                           len(paras), win_last, win_chars, TERM_CAP, BLOCKER_CAP)
    parsed: EJQIv3 = generate(cli, prompts.SYSTEM, prompt, EJQIv3, usage,
                              temperature=temperature)  # ④ LLM 1회 호출
    return verify(parsed.model_dump(), art.body,        # ⑤ 결정론적 인용 검증
                  len(paras), win_last, win_chars)


def _merge_repeats(runs: list[dict]) -> dict:
    """N회 결과를 평균낸다. 첫 실행의 근거·목록을 대표로 남긴다."""
    if len(runs) == 1:
        out = dict(runs[0]); out["n_repeats"] = 1
        return out
    out = dict(runs[0])
    for key in _NUMERIC:
        vals = [r[key] for r in runs if r.get(key) is not None]
        out[key] = round(mean(vals), 2) if vals else None
    for key in ("n_terms", "n_blockers", "n_sources", "n_terms_unexplained"):
        out[key] = round(mean(r[key] for r in runs), 1)
    out["effort_na"] = sum(r["effort_na"] for r in runs) > len(runs) / 2
    for key in ("headline_consistency", "promotional"):
        out[key] = sum(r[key] for r in runs) > len(runs) / 2
    out["headline_overstated"] = out["headline_consistency"]
    out["n_repeats"] = len(runs)
    out["repeat_sd"] = {
        key: round(pstdev([r[key] for r in runs]) * (len(runs) / max(len(runs) - 1, 1)) ** 0.5, 2)
        for key in _NUMERIC
        if out.get(key) is not None and all(r.get(key) is not None for r in runs)
    }
    return out


def evaluate(api_key: str, article, *, repeat: int = 1,
             temperature: float | None = None, on_step=None) -> dict:
    """기사 1건을 채점한다.

    article : dict 또는 Article. body는 필수, 나머지는 선택.
    repeat  : 1이면 1회 채점. 2 이상이면 temperature를 올려 반복 평균한다.
    on_step : 진행 표시용 콜백 (완료수, 전체수)
    """
    art = article if isinstance(article, Article) else Article(**article)
    if not (art.body or "").strip():
        raise ValueError("기사 본문을 입력해 주세요.")

    cli = make_client(api_key)
    usage = Usage()
    temp = temperature if temperature is not None else (
        REPEAT_TEMPERATURE if repeat > 1 else None)

    runs = []
    n = max(repeat, 1)
    for i in range(n):
        runs.append(_score_once(cli, art, usage, temp))
        if on_step:
            on_step(i + 1, n)

    scored = _merge_repeats(runs)
    scored["flags"] = reliability_flags(scored)
    scored["meta"] = {
        "press": art.press,
        "media_type": media_type(art.press),
        "topic": art.topic,
        "title": art.title,
        "subtitle": art.subtitle,
        "body_len": len(art.body),
        "len_bin": len_bin(len(art.body)),
        "usage": usage.as_dict(),
        "cost_usd": round(usage.cost_usd, 5),
    }
    return scored


def paragraph_preview(body: str) -> dict:
    """채점 전에 문단 분할과 분석 창을 미리 보여준다 (LLM 호출 없음)."""
    paras = split_paragraphs(body)
    win_last, win_chars = term_window(paras)
    return {
        "n_paragraphs": len(paras),
        "term_window_last": win_last,
        "window_chars": win_chars,
        "window_ratio": round(win_chars / max(len(body), 1), 3),
        "paragraphs": [{"no": i, "len": len(p), "in_window": i <= win_last, "text": p}
                       for i, p in enumerate(paras, 1)],
    }
