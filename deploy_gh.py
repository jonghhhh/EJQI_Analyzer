#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub 저장소 + GitHub Pages 배포.

  python web/deploy_gh.py                  # 업로드 (없으면 저장소 생성) + Pages 활성화
  python web/deploy_gh.py --private        # 비공개로 생성 (※ 무료 계정은 Pages 불가)
  python web/deploy_gh.py --no-pages       # 파일만 올리고 Pages는 건드리지 않음
  python web/deploy_gh.py --dry-run        # 올릴 파일만 확인

토큰은 프로젝트 루트 `.env` 의 GITHUB_TOKEN 을 쓴다(repo 스코프 필요).
`.env`·API 키·테스트 고정자료는 절대 올라가지 않는다 — 아래 ALLOW 목록에 있는 것만 올린다.

커밋은 Git Data API로 **한 번에 하나**만 만든다(파일마다 커밋이 생기지 않는다).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import load_dotenv

WEB = Path(__file__).resolve().parent
ROOT = WEB.parent
DEFAULT_REPO = "EJQI_Analyzer"
API = "https://api.github.com"

DESCRIPTION = ("경제 뉴스 품질 평가 지수(EJQI) 자동 분석 시스템 + 데스크 챗봇(ENDC). "
               "네이버 경제 섹션 30,178건 실측 규준 기반. 서버 없는 정적 페이지.")
TOPICS = ["journalism", "news-quality", "content-analysis", "korean",
          "economics", "llm", "gemini", "media-research"]

# 업로드 대상 화이트리스트 — 여기 없는 파일은 올라가지 않는다.
# 정적 웹 + 재현용 코드(Streamlit 판·검증 스크립트)를 함께 공개한다.
ALLOW = [
    # ── 정적 웹 (GitHub Pages 가 서빙) ──
    "index.html",
    "css/style.css",
    "js/ejqi.js",
    "js/prompts.js",
    "js/schema.js",
    "js/gemini.js",
    "js/endc.js",
    "js/app.js",
    "data/norms_web.json",
    "data/endc_knowledge.md",
    ".nojekyll",                 # Jekyll 처리를 끈다 (밑줄 파일·폴더 보호)
    # ── 문서 ──
    "README.md",
    ".gitignore",
    # ── 재현용 코드 ──
    "app.py",
    "requirements.txt",
    "Dockerfile",
    "ejqi/__init__.py",
    "ejqi/config.py",
    "ejqi/schema.py",
    "ejqi/prompts.py",
    "ejqi/llm.py",
    "ejqi/verify.py",
    "ejqi/evaluate.py",
    "ejqi/norms.py",
    "ejqi/report.py",
    "scripts/gen_prompts_js.py",
    "scripts/make_parity_fixture.py",
    "scripts/parity_test.mjs",
    "scripts/rest_smoke.py",
    # ── 배포 스크립트 ──
    "deploy_gh.py",
    "deploy_hf.py",
    "SPACE_README.md",
]

_token = ""


def api(path: str, method: str = "GET", body: dict | None = None,
        expect=(200, 201, 204)):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        API + path if path.startswith("/") else path,
        data=data, method=method,
        headers={"Authorization": f"Bearer {_token}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "Content-Type": "application/json",
                 "User-Agent": "ejqi-deploy"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"message": raw[:300]}
        if e.code not in expect:
            return e.code, payload
        return e.code, payload


def main() -> int:
    global _token
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--owner", default=None, help="미지정이면 토큰 소유자")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--no-pages", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--message", default="EJQI Suite — 정적 웹 + 재현용 코드")
    a = ap.parse_args()

    load_dotenv(ROOT / ".env")
    _token = (os.getenv("GITHUB_TOKEN") or "").strip().strip('"').strip("'")
    if not _token:
        print("!! .env 에 GITHUB_TOKEN 이 없습니다.", file=sys.stderr)
        return 1

    missing = [f for f in ALLOW if not (WEB / f).exists()]
    if missing:
        print("!! 누락된 파일:", missing, file=sys.stderr)
        return 1
    total = sum((WEB / f).stat().st_size for f in ALLOW)
    print(f"업로드 대상 {len(ALLOW)}개 · {total/1e6:.2f}MB")
    for f in ALLOW:
        print(f"  {f:<34} {(WEB / f).stat().st_size/1024:8.1f} KB")
    if a.dry_run:
        return 0

    st, me = api("/user")
    if st != 200:
        print(f"!! 인증 실패: {me}", file=sys.stderr)
        return 1
    owner = a.owner or me["login"]
    repo = f"{owner}/{a.repo}"
    print(f"\n대상: https://github.com/{repo}")

    # ── ① 저장소 확보 ────────────────────────────────
    st, info = api(f"/repos/{repo}", expect=(200, 404))
    if st == 404:
        st, info = api("/user/repos", "POST", {
            "name": a.repo, "description": DESCRIPTION,
            "homepage": f"https://{owner}.github.io/{a.repo}/",
            "private": a.private, "auto_init": False,
            "has_issues": True, "has_wiki": False, "has_projects": False,
        }, expect=(201,))
        if st != 201:
            print(f"!! 저장소 생성 실패: {info}", file=sys.stderr)
            return 1
        print(f"  저장소 생성 완료 ({'비공개' if a.private else '공개'})")
        time.sleep(2)
    else:
        print(f"  기존 저장소 사용 (private={info.get('private')})")
        api(f"/repos/{repo}", "PATCH", {
            "description": DESCRIPTION,
            "homepage": f"https://{owner}.github.io/{a.repo}/"}, expect=(200,))

    api(f"/repos/{repo}/topics", "PUT", {"names": TOPICS}, expect=(200,))

    # ── ①-b 빈 저장소 부트스트랩 ─────────────────────
    # Git Data API는 커밋이 하나도 없는 저장소에서 블롭을 만들지 못한다
    # ("Git Repository is empty", 409). Contents API로 첫 커밋을 만들어 준다.
    st, ref0 = api(f"/repos/{repo}/git/ref/heads/{a.branch}", expect=(200, 404, 409))
    if st != 200:
        st, r0 = api(f"/repos/{repo}/contents/.nojekyll", "PUT", {
            "message": "초기 커밋", "branch": a.branch,
            "content": base64.b64encode(b"").decode()}, expect=(201,))
        if st != 201:
            print(f"!! 초기 커밋 실패: {r0}", file=sys.stderr)
            return 1
        print(f"  초기 커밋 생성 ({a.branch})")
        time.sleep(1)

    # ── ② 블롭 → 트리 → 커밋 (커밋 1개) ──────────────
    print("  파일 업로드 중…", end="", flush=True)
    tree = []
    for f in ALLOW:
        raw = (WEB / f).read_bytes()
        st, blob = api(f"/repos/{repo}/git/blobs", "POST", {
            "content": base64.b64encode(raw).decode(), "encoding": "base64"},
            expect=(201,))
        if st != 201:
            print(f"\n!! 블롭 실패 {f}: {blob}", file=sys.stderr)
            return 1
        tree.append({"path": f, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        print(".", end="", flush=True)
    print()

    ref_path = f"/repos/{repo}/git/ref/heads/{a.branch}"
    st, ref = api(ref_path, expect=(200, 404, 409))
    parents, base_tree = [], None
    if st == 200:
        parents = [ref["object"]["sha"]]
        st2, commit = api(f"/repos/{repo}/git/commits/{parents[0]}")
        base_tree = commit["tree"]["sha"]

    payload = {"tree": tree}
    if base_tree:
        payload["base_tree"] = base_tree
    st, tr = api(f"/repos/{repo}/git/trees", "POST", payload, expect=(201,))
    if st != 201:
        print(f"!! 트리 실패: {tr}", file=sys.stderr)
        return 1

    st, commit = api(f"/repos/{repo}/git/commits", "POST", {
        "message": a.message, "tree": tr["sha"], "parents": parents}, expect=(201,))
    if st != 201:
        print(f"!! 커밋 실패: {commit}", file=sys.stderr)
        return 1

    if parents:
        st, r = api(f"/repos/{repo}/git/refs/heads/{a.branch}", "PATCH",
                    {"sha": commit["sha"], "force": False}, expect=(200,))
    else:
        st, r = api(f"/repos/{repo}/git/refs", "POST",
                    {"ref": f"refs/heads/{a.branch}", "sha": commit["sha"]},
                    expect=(201,))
    if st not in (200, 201):
        print(f"!! 브랜치 갱신 실패: {r}", file=sys.stderr)
        return 1
    print(f"  커밋 {commit['sha'][:7]} → {a.branch}")

    # ── ③ GitHub Pages ──────────────────────────────
    if not a.no_pages:
        st, pg = api(f"/repos/{repo}/pages", expect=(200, 404))
        if st == 404:
            st, pg = api(f"/repos/{repo}/pages", "POST",
                         {"source": {"branch": a.branch, "path": "/"}},
                         expect=(201, 409, 403))
            if st == 201:
                print("  Pages 활성화 완료")
            elif st == 403:
                print(f"  ! Pages 활성화 거부됨: {pg.get('message', '')[:160]}")
                print("    (비공개 저장소는 유료 플랜에서만 Pages를 쓸 수 있습니다)")
            else:
                print(f"  ! Pages 응답: {st} {pg.get('message', '')[:120]}")
        else:
            api(f"/repos/{repo}/pages", "PUT",
                {"source": {"branch": a.branch, "path": "/"}}, expect=(204,))
            print("  Pages 이미 활성화됨 (소스 갱신)")

        # 빌드 상태 확인
        for _ in range(10):
            time.sleep(6)
            st, pg = api(f"/repos/{repo}/pages", expect=(200, 404))
            if st == 200 and pg.get("status") == "built":
                print(f"  Pages 빌드 완료 → {pg.get('html_url')}")
                break
            if st == 200:
                print(f"    빌드 상태: {pg.get('status')}")
        else:
            print("    빌드가 아직 진행 중입니다. 1~2분 뒤 접속해 보십시오.")

    print(f"\n▶ 저장소   https://github.com/{repo}")
    print(f"▶ 웹 서비스 https://{owner}.github.io/{a.repo}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
