# -*- coding: utf-8 -*-
"""브라우저가 보낼 것과 **동일한 REST 요청**을 그대로 쏴 본다.

js/schema.js 의 responseSchema 를 Gemini가 받아들이는지, 응답이 파이썬 파이프라인과
같은 구조로 나오는지 확인한다. 브라우저 없이 검증하기 위한 스크립트다.

  python web/scripts/rest_smoke.py --key <GEMINI_API_KEY>
  python web/scripts/rest_smoke.py            # .env 의 GOOGLE_API_KEY 사용
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # 저장소 루트(js/ · ejqi/ 가 있는 곳)
WEB = ROOT
sys.path.insert(0, str(ROOT))
# .env 와 원본 코퍼스는 연구 저장소 쪽에 있다.
RESEARCH = Path(os.getenv("EJQI_RESEARCH", str(ROOT.parent)))

BASE = "https://generativelanguage.googleapis.com/v1beta/models"
MODEL = "gemini-3.1-flash-lite"
NODE = os.getenv("NODE_BIN", "/mnt/c/Program Files/nodejs/node.exe")


def js_eval(expr_module: str, expr: str):
    """node로 ESM 모듈을 불러 값을 JSON으로 받아온다.

    `node -e` 는 상대 import 를 풀지 못하므로 임시 .mjs 파일로 실행한다.
    """
    tmp = WEB / "_jseval.mjs"
    tmp.write_text(f'import * as M from {json.dumps(expr_module)};\n'
                   f'process.stdout.write(JSON.stringify({expr}));\n', encoding="utf-8")
    try:
        p = subprocess.run([NODE, str(tmp)], capture_output=True, text=True, cwd=str(WEB))
        if p.returncode:
            raise RuntimeError("…\n" + p.stderr[-1500:])
        return json.loads(p.stdout)
    finally:
        tmp.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", default=None)
    ap.add_argument("--article", default=None, help="본문 파일 (미지정이면 코퍼스에서 1건)")
    a = ap.parse_args()

    key = a.key
    if not key:
        from dotenv import load_dotenv
        load_dotenv(RESEARCH / ".env")
        key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key:
        print("!! 키가 없습니다.", file=sys.stderr)
        return 1

    # 1) JS 모듈에서 스키마·프롬프트를 그대로 가져온다
    schema = js_eval("./js/schema.js", "M.EJQI_SCHEMA")
    system = js_eval("./js/prompts.js", "M.SYSTEM")
    print(f"스키마 필드 {len(schema['properties'])}개 · required {len(schema['required'])}개")

    # 2) 기사 준비
    if a.article:
        body = Path(a.article).read_text(encoding="utf-8")
        title = ""
    else:
        body = title = None
        with open(RESEARCH / "naver_news" / "naver_econ_articles.jsonl", encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if str(r.get("oid")) == "032" and str(r.get("aid")) == "0003305988":
                    body, title = r["body"], r["title"]
                    break
    print(f"기사 {len(body):,}자")

    # 3) JS 로 문단 분할 → 창 → 프롬프트 조립 (브라우저와 동일 경로)
    payload = js_eval(
        "./js/ejqi.js",
        f"(() => {{ const b = {json.dumps(body)};"
        " const p = M.splitParagraphs(b); const [wl, wc] = M.termWindow(p);"
        " return {nPara: p.length, win: wl, winChars: wc,"
        "         numbered: M.numberParagraphs(p)}; })()")
    prompt = js_eval(
        "./js/prompts.js",
        f"M.buildPrompt({{title: {json.dumps(title)}, subtitle: '',"
        f" numberedBody: {json.dumps(payload['numbered'])}, nPara: {payload['nPara']},"
        f" win: {payload['win']}, winChars: {payload['winChars']}}})")
    print(f"문단 {payload['nPara']}개 · 창 P1~P{payload['win']} ({payload['winChars']}자) · "
          f"프롬프트 {len(prompt):,}자")

    # 4) 브라우저와 동일한 요청 본문
    req_body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 12288,
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    req = urllib.request.Request(
        f"{BASE}/{MODEL}:generateContent",
        data=json.dumps(req_body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": key},
        method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            j = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"!! HTTP {e.code}\n{e.read().decode('utf-8')[:1200]}", file=sys.stderr)
        return 1
    el = time.time() - t0

    um = j.get("usageMetadata", {})
    print(f"응답 {el:.1f}초 · in {um.get('promptTokenCount'):,} / "
          f"out {um.get('candidatesTokenCount'):,} 토큰")

    text = "".join(p.get("text", "") for p in j["candidates"][0]["content"]["parts"])
    parsed = json.loads(text)
    print(f"파싱 OK · 최상위 키 {len(parsed)}개")

    # 5) 파이썬 스키마와 키 집합 대조
    from ejqi.schema import EJQIv3
    want = set(EJQIv3.model_fields.keys())
    got = set(parsed.keys())
    print(f"  누락 {sorted(want - got) or '없음'} | 잉여 {sorted(got - want) or '없음'}")

    # 6) 파이썬 verify 와 JS verify 를 같은 응답에 돌려 비교
    from ejqi.verify import verify as pyverify
    py = pyverify(parsed, body, payload["nPara"], payload["win"], payload["winChars"])
    jsr = js_eval(
        "./js/ejqi.js",
        f"M.verify({json.dumps(parsed)}, {json.dumps(body)}, {payload['nPara']},"
        f" {payload['win']}, {payload['winChars']})")
    def same(a, b):
        # 0.0 과 0 처럼 JSON 표기만 다른 경우는 같은 값으로 본다
        if isinstance(a, (int, float)) and not isinstance(a, bool) \
           and isinstance(b, (int, float)) and not isinstance(b, bool):
            return abs(a - b) < 1e-9
        return (json.dumps(a, ensure_ascii=False, sort_keys=True)
                == json.dumps(b, ensure_ascii=False, sort_keys=True))

    diff = []
    for k, v in py.items():
        if k == "terms_detail":
            continue
        if not same(v, jsr.get(k)):
            diff.append((k, v, jsr.get(k)))
    print(f"\n파이썬 verify vs JS verify — 불일치 {len(diff)}건")
    for k, v, g in diff[:6]:
        print(f"  ✗ {k}\n    python {str(v)[:120]}\n    js     {str(g)[:120]}")

    print(f"\n장르 {py['genre']} · 용어 {py['n_terms']}개 (해설률 {py['term_explanation_rate']}%) "
          f"· 취재원 {py['n_sources']}명 · 막힘 {py['n_blockers']}개")
    print("[OK] REST 경로 검증 통과" if not diff else "[!!] 불일치 있음")
    return 0 if not diff else 1


if __name__ == "__main__":
    raise SystemExit(main())
