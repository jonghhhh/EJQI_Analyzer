#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""허깅페이스 Space 배포 스크립트.

  python web/deploy_hf.py                 # 업로드 (없으면 Space 생성)
  python web/deploy_hf.py --private       # 비공개로 생성
  python web/deploy_hf.py --repo 다른이름   # 저장소 이름 변경
  python web/deploy_hf.py --dry-run       # 올릴 파일만 확인

토큰은 프로젝트 루트 `.env` 의 HUGGINGFACE_TOKEN_WRITE 를 쓴다(write 권한 필요).
`.env` 자체는 절대 업로드되지 않는다 — 아래 ALLOW 목록에 있는 것만 올린다.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from huggingface_hub import HfApi

WEB = Path(__file__).resolve().parent
ROOT = WEB.parent
DEFAULT_REPO = "EJQI-Analyzer-ENDC"

# 업로드 대상 화이트리스트 — 여기 없는 파일은 올라가지 않는다.
# `.env`·테스트 키·고정자료·Streamlit 판은 의도적으로 제외한다.
ALLOW = [
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
]
# Space 카드는 YAML 프런트매터가 필요하다. GitHub 쪽 README와 내용이 갈리므로
# 파일을 따로 두고 업로드할 때 이름만 README.md 로 바꿔 올린다.
CARD_SRC, CARD_DST = "SPACE_README.md", "README.md"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--owner", default=None, help="미지정이면 토큰 소유자")
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    load_dotenv(ROOT / ".env")
    token = (os.getenv("HUGGINGFACE_TOKEN_WRITE")
             or os.getenv("HF_TOKEN")
             or os.getenv("HUGGINGFACE_API_KEY") or "").strip()
    if not token:
        print("!! .env 에 HUGGINGFACE_TOKEN_WRITE 가 없습니다.", file=sys.stderr)
        return 1

    missing = [f for f in ALLOW + [CARD_SRC] if not (WEB / f).exists()]
    if missing:
        print("!! 누락된 파일:", missing, file=sys.stderr)
        return 1
    total = sum((WEB / f).stat().st_size for f in ALLOW + [CARD_SRC])
    print(f"업로드 대상 {len(ALLOW) + 1}개 · {total/1e6:.2f}MB")
    for f in ALLOW:
        print(f"  {f:<28} {(WEB / f).stat().st_size/1024:8.1f} KB")
    print(f"  {CARD_SRC + ' → ' + CARD_DST:<28} {(WEB / CARD_SRC).stat().st_size/1024:8.1f} KB")
    if a.dry_run:
        return 0

    api = HfApi(token=token)
    owner = a.owner or api.whoami()["name"]
    repo_id = f"{owner}/{a.repo}"

    print(f"\nSpace: https://huggingface.co/spaces/{repo_id}")
    # 허깅페이스는 현재 space_sdk 로 gradio·docker·static 만 받으며,
    # 무료 계정에서는 **static 만** 무료다. 이 앱은 서버가 필요 없으므로 static 으로 올린다.
    api.create_repo(repo_id=repo_id, repo_type="space", space_sdk="static",
                    private=a.private, exist_ok=True)
    print("  저장소 준비 완료" + (" (비공개)" if a.private else " (공개)"))

    api.upload_folder(
        folder_path=str(WEB), repo_id=repo_id, repo_type="space",
        allow_patterns=ALLOW,
        commit_message="EJQI Suite — 품질 분석 시스템 + 데스크 챗봇(ENDC)",
    )
    api.upload_file(
        path_or_fileobj=str(WEB / CARD_SRC), path_in_repo=CARD_DST,
        repo_id=repo_id, repo_type="space",
        commit_message="Space 카드 갱신",
    )
    print("  업로드 완료")
    print(f"\n▶ https://huggingface.co/spaces/{repo_id}")
    print("  빌드에 2~4분 걸립니다. Space 페이지의 Logs 탭에서 진행 상황을 볼 수 있습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
