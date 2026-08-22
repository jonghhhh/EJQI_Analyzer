# -*- coding: utf-8 -*-
"""ejqi/prompts.py 의 SYSTEM·MAIN 을 그대로 JS 파일로 옮긴다.

손으로 옮기면 한 글자만 달라져도 30,178건 규준과의 비교가 깨진다.
그래서 파이썬 원본에서 직접 읽어 생성한다.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from ejqi import prompts as P

def js_str(s: str) -> str:
    """JSON 문자열 리터럴로 안전하게 인코딩 (백틱·달러·개행 문제 없음)."""
    return json.dumps(s, ensure_ascii=False)

out = f'''// 자동 생성 파일 — 직접 수정하지 마십시오.
// 원본: ejqi/prompts.py (연구 본편). scripts/gen_prompts_js.py 로 재생성합니다.
//
// 앵커 문구가 한 글자라도 달라지면 30,178건 규준과의 비교가 성립하지 않습니다.
// 인간 코더용 코드북(ejqi/codebook.py)과도 동일 정의를 유지해야 합니다.

export const SYSTEM = {js_str(P.SYSTEM)};

const MAIN = {js_str(P.MAIN)};

/**
 * 프롬프트 조립. win = 용어 추출 창의 마지막 문단 번호 (1..win 이 대상).
 */
export function buildPrompt({{ title, subtitle, numberedBody, nPara, win,
                              winChars = 0, termCap = 25, blockerCap = 10 }}) {{
  const map = {{
    title: title || "(없음)",
    subtitle: subtitle || "(없음)",
    body: numberedBody,
    last: String(nPara),
    win: String(win),
    win_next: win < nPara ? `[P${{win + 1}}]` : "(없음)",
    win_chars: String(winChars),
    term_cap: String(termCap),
    blocker_cap: String(blockerCap),
  }};
  return MAIN.replace(/\\{{(\\w+)\\}}/g, (m, k) => (k in map ? map[k] : m));
}}
'''

dst = Path(__file__).resolve().parent.parent / "js" / "prompts.js"
dst.parent.mkdir(parents=True, exist_ok=True)
dst.write_text(out, encoding="utf-8")
print(f"생성: {dst} ({dst.stat().st_size:,} bytes)")
print("SYSTEM 길이:", len(P.SYSTEM), "| MAIN 길이:", len(P.MAIN))
