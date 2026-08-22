# -*- coding: utf-8 -*-
"""규준 분포 조회 (웹 배포판) — 가중치 대신 '비교군 내 위치'로 해석한다.

왜 가중치가 아니라 규준인가
  본 연구 실측에서 **길이 효과가 매체 효과의 4배**로 나타났다
  (분석 깊이: 길이대 차이 1.28점 vs 매체유형 차이 0.33점).
  절대 점수로 비교하면 기사 길이 구성 차이가 그대로 '품질 차이'로 둔갑한다.

규준 자료
  본 연구 전량 측정 30,178건(2024-07 ~ 2026-06)으로 만든 비교군 16개.
  장르 × 길이대가 기본이며, 표본이 부족하면 길이대만으로, 그래도 부족하면 전체로 완화한다.
  파일은 값→빈도 히스토그램으로 압축돼 있다(6.0MB → 0.55MB). 백분위는 동일하게 재현된다.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np

from .config import NORMS_PATH

MIN_CELL = 30

# 차원별 항목 — C 차원은 C2·C4·C5 셋만으로 낸다.
#   C1 difficulty            '쉬움'을 재므로 품질 합성에 넣으면 방향이 뒤집힌다
#   C3 term_explanation_rate 척도가 0~100이라 0–5 항목과 같은 평균에 못 넣는다
# 두 항목은 차원 밖 단독 지표로 따로 보고한다.
DIMS = {
    "A": ["numeric_context", "causal_uncertainty", "verification", "impact_scope"],
    "B": ["interest_disclosure"],
    "C": ["effort", "scaffold_number", "scaffold_case"],
    "D": ["background", "reader_implication"],
}
DIM_ORDER = ["A", "C", "D", "B"]     # 인터뷰에서 방어 가능한 것은 이 서수뿐이다


@lru_cache(maxsize=1)
def load(path: str | None = None) -> dict | None:
    p = Path(path or NORMS_PATH)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def cell_key(genre: str, len_bin: str) -> str:
    return f"{genre}/{len_bin}"


def pick_cell(norms: dict, genre: str, len_bin: str):
    """비교군 선택 — 좁은 쪽부터, 표본이 부족하면 완화한다."""
    for key in (cell_key(genre, len_bin), f"전체/{len_bin}", "전체/전체"):
        c = norms["cells"].get(key)
        if c and c["n"] >= norms.get("min_cell", MIN_CELL):
            return key, c
    c = norms["cells"].get("전체/전체")
    return ("전체/전체", c) if c else (None, None)


def percentile(hist: dict, x: float, integerize: bool = False) -> float:
    """중간순위 백분위 — 동점이 많은 0–5 척도에 적합하다.

    hist = {"값": 빈도}. 용어 해설률은 정수로 반올림돼 저장돼 있다.
    """
    if not hist:
        return float("nan")
    v = round(float(x)) if integerize else float(x)
    below = equal = total = 0
    for k, cnt in hist.items():
        kv = float(k)
        total += cnt
        if kv < v:
            below += cnt
        elif kv == v:
            equal += cnt
    if total == 0:
        return float("nan")
    return (below + 0.5 * equal) / total * 100


def item_percentile(cell: dict, item: str, value) -> float | None:
    if value is None:
        return None
    hist = cell.get("hist", {}).get(item)
    if not hist:
        return None
    return percentile(hist, value, integerize=(item == "term_explanation_rate"))


def dim_vector(r: dict) -> list[float] | None:
    """기사 1건의 차원 평균 [A, C, D, B]. 하나라도 비면 None."""
    out = []
    for d in DIM_ORDER:
        vals = [r[k] for k in DIMS[d] if r.get(k) is not None]
        if not vals:
            return None
        out.append(sum(vals) / len(vals))
    return out


def weight_interval(r: dict, norms: dict | None = None,
                    n_draw: int = 1000, seed: int = 7) -> dict | None:
    """서수 제약(A ≥ C ≥ D ≥ B)만 건 가중치 공간에서의 백분위 구간.

    가중치의 '비율'은 근거가 없다. 인터뷰에서 방어 가능한 것은 '순서'뿐이다.
    따라서 순서 제약을 만족하는 가중치를 무작위로 1,000개 뽑아
    백분위가 어느 구간에 놓이는지를 보고한다.
    """
    norms = norms or load()
    if not norms:
        return None
    cell = norms["cells"].get("전체/전체")
    if not cell or "dim_vectors" not in cell:
        return None
    mine = dim_vector(r)
    if mine is None:
        return None

    pop = np.asarray(cell["dim_vectors"], dtype=float)          # (n, 4) = [A, C, D, B]
    rng = np.random.default_rng(seed)
    # 서수 제약은 내림차순 정렬로 충족된다
    w = np.sort(rng.dirichlet(np.ones(4), size=n_draw), axis=1)[:, ::-1]
    tot = pop @ w.T
    my = w @ np.asarray(mine, dtype=float)
    a = ((tot < my).sum(axis=0) + 0.5 * (tot == my).sum(axis=0)) / pop.shape[0] * 100
    return {"mean": float(a.mean()),
            "lo": float(np.percentile(a, 2.5)),
            "hi": float(np.percentile(a, 97.5)),
            "n_pop": int(pop.shape[0]), "n_draw": n_draw}
