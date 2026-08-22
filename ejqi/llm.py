# -*- coding: utf-8 -*-
"""Gemini 호출 래퍼 (웹 배포판) — 구조화 출력 + 재시도.

연구 본편과 다른 점
  · API 키를 환경변수가 아니라 **인자로 받는다**. 이용자가 화면에서 입력한 키를 쓴다
  · 배치·비동기·키 로테이션을 걷어내고 동기 단건 호출만 남겼다

키는 서버에 저장하지 않는다. 세션 메모리에만 존재하며 호출 시 Google API로만 전송된다.
"""
from __future__ import annotations

import random
import time
from typing import Type, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from .config import MAX_OUTPUT_TOKENS, MODEL, TEMPERATURE, THINKING_BUDGET

T = TypeVar("T", bound=BaseModel)
MAX_RETRY = 5

# 키 문제로 판단해 재시도를 멈춰야 하는 오류 — 사용자에게 즉시 알린다
_KEY_ERROR = ("api key not valid", "invalid api key", "unauthenticated",
              "permission_denied", "api_key_invalid", "401", "403")
_QUOTA_ERROR = ("resource_exhausted", "quota", "rate limit", "429")


class ApiKeyError(RuntimeError):
    """키가 잘못됐거나 권한이 없다."""


class QuotaError(RuntimeError):
    """할당량 소진 또는 요청 과다."""


class Usage:
    def __init__(self) -> None:
        self.calls = self.pin = self.pout = 0

    def add(self, um) -> None:
        self.calls += 1
        self.pin += getattr(um, "prompt_token_count", 0) or 0
        self.pout += ((getattr(um, "candidates_token_count", 0) or 0)
                      + (getattr(um, "thoughts_token_count", 0) or 0))

    def as_dict(self) -> dict:
        return {"calls": self.calls, "input_tokens": self.pin, "output_tokens": self.pout}

    @property
    def cost_usd(self) -> float:
        """참고 단가 기준 추정치 (입력 $0.10 / 출력 $0.40 per 1M)."""
        return self.pin / 1e6 * 0.10 + self.pout / 1e6 * 0.40


def make_client(api_key: str):
    if not (api_key or "").strip():
        raise ApiKeyError("Gemini API 키를 입력해 주세요.")
    return genai.Client(api_key=api_key.strip())


def generate(cli, system: str, prompt: str, schema: Type[T],
             usage: Usage | None = None, *, model: str | None = None,
             temperature: float | None = None,
             max_output_tokens: int | None = None,
             thinking: int | None = THINKING_BUDGET) -> T:
    """구조화 출력 1회 호출. 파싱 실패·일시 오류는 재시도한다."""
    cfg = dict(
        system_instruction=system,
        temperature=TEMPERATURE if temperature is None else temperature,
        max_output_tokens=max_output_tokens or MAX_OUTPUT_TOKENS,
        response_mime_type="application/json",
        response_schema=schema,
    )
    if thinking is not None:
        cfg["thinking_config"] = types.ThinkingConfig(thinking_budget=thinking)

    last: Exception | None = None
    for attempt in range(1, MAX_RETRY + 1):
        try:
            resp = cli.models.generate_content(
                model=model or MODEL, contents=prompt,
                config=types.GenerateContentConfig(**cfg))
            if usage is not None and resp.usage_metadata:
                usage.add(resp.usage_metadata)
            if resp.parsed is None:
                raise ValueError("구조화 출력 파싱 실패(parsed=None)")
            return resp.parsed
        except Exception as e:  # noqa: BLE001
            last = e
            s = str(e).lower()
            if "thinking" in s and "thinking_config" in cfg:
                cfg.pop("thinking_config")      # 모델이 비활성화를 거부하면 해제
                continue
            if any(t in s for t in _KEY_ERROR):
                raise ApiKeyError(
                    "API 키가 유효하지 않거나 권한이 없습니다. "
                    "키를 다시 확인해 주세요.") from e
            if any(t in s for t in _QUOTA_ERROR) and attempt == MAX_RETRY:
                raise QuotaError(
                    "요청 한도에 도달했습니다. 잠시 후 다시 시도하거나 "
                    "다른 키를 사용해 주세요.") from e
            if attempt == MAX_RETRY:
                break
            time.sleep(min(2 ** attempt, 12) + random.random())
    raise RuntimeError(f"호출 실패({MAX_RETRY}회): {str(last)[:300]}")


def generate_text(cli, system: str, messages: list[dict], *,
                  model: str | None = None, temperature: float = 0.3,
                  max_output_tokens: int = 4096,
                  usage: Usage | None = None) -> str:
    """자유 텍스트 대화 (ENDC 챗봇용). messages = [{role, text}, ...]"""
    contents = [
        types.Content(role=("model" if m["role"] == "assistant" else "user"),
                      parts=[types.Part.from_text(text=m["text"])])
        for m in messages
    ]
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )
    last: Exception | None = None
    for attempt in range(1, MAX_RETRY + 1):
        try:
            resp = cli.models.generate_content(
                model=model or MODEL, contents=contents, config=cfg)
            if usage is not None and resp.usage_metadata:
                usage.add(resp.usage_metadata)
            return (resp.text or "").strip()
        except Exception as e:  # noqa: BLE001
            last = e
            s = str(e).lower()
            if "thinking" in s:
                cfg = types.GenerateContentConfig(
                    system_instruction=system, temperature=temperature,
                    max_output_tokens=max_output_tokens)
                continue
            if any(t in s for t in _KEY_ERROR):
                raise ApiKeyError("API 키가 유효하지 않거나 권한이 없습니다.") from e
            if any(t in s for t in _QUOTA_ERROR) and attempt == MAX_RETRY:
                raise QuotaError("요청 한도에 도달했습니다.") from e
            if attempt == MAX_RETRY:
                break
            time.sleep(min(2 ** attempt, 12) + random.random())
    raise RuntimeError(f"호출 실패({MAX_RETRY}회): {str(last)[:300]}")
