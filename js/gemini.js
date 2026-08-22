// Gemini REST 호출 (브라우저에서 직접).
//
// 이 앱에는 서버가 없다. 이용자가 입력한 키로 브라우저가 Google API를 직접 부른다.
// 키는 이 페이지를 벗어나 어디에도 전송·저장되지 않는다.

const BASE = "https://generativelanguage.googleapis.com/v1beta/models";

export class ApiKeyError extends Error {}
export class QuotaError extends Error {}
export class BlockedError extends Error {}

const KEY_ERR = ["api key not valid", "invalid api key", "api_key_invalid",
                 "unauthenticated", "permission_denied", "permission denied"];
const QUOTA_ERR = ["resource_exhausted", "quota", "rate limit", "spending cap",
                   "exceeded its monthly"];

export const usage = { calls: 0, in: 0, out: 0 };

export function costUsd() {   // 참고 단가 (입력 $0.10 / 출력 $0.40 per 1M)
  return usage.in / 1e6 * 0.10 + usage.out / 1e6 * 0.40;
}

export function resetUsage() { usage.calls = 0; usage.in = 0; usage.out = 0; }

function addUsage(um) {
  if (!um) return;
  usage.calls += 1;
  usage.in += um.promptTokenCount || 0;
  usage.out += (um.candidatesTokenCount || 0) + (um.thoughtsTokenCount || 0);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function post(model, apiKey, body, signal) {
  const key = (apiKey || "").trim();
  if (!key) throw new ApiKeyError("Gemini API 키를 입력해 주세요.");

  const res = await fetch(`${BASE}/${model}:generateContent`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "x-goog-api-key": key },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      msg = j?.error?.message || msg;
    } catch { /* 본문이 JSON이 아닐 수 있다 */ }
    const low = msg.toLowerCase();
    if (res.status === 400 && KEY_ERR.some((t) => low.includes(t))) {
      throw new ApiKeyError("API 키가 유효하지 않습니다. 키를 다시 확인해 주세요.");
    }
    if (res.status === 401 || res.status === 403) {
      throw new ApiKeyError("API 키가 유효하지 않거나 권한이 없습니다. 키를 다시 확인해 주세요.");
    }
    if (res.status === 429 || QUOTA_ERR.some((t) => low.includes(t))) {
      throw new QuotaError(
        "요청 한도에 도달했습니다. 잠시 후 다시 시도하거나 다른 키를 사용해 주세요.\n(원문: "
        + msg.slice(0, 200) + ")");
    }
    const e = new Error(msg.slice(0, 400));
    e.status = res.status;
    throw e;
  }

  const j = await res.json();
  addUsage(j.usageMetadata);

  if (j.promptFeedback?.blockReason) {
    throw new BlockedError(`안전 필터에 걸렸습니다 (${j.promptFeedback.blockReason}).`);
  }
  const cand = j.candidates?.[0];
  if (!cand) throw new Error("응답이 비어 있습니다.");
  if (cand.finishReason === "MAX_TOKENS") {
    throw new Error("응답이 최대 길이에 도달해 잘렸습니다. 본문을 조금 줄여 다시 시도해 주세요.");
  }
  const text = (cand.content?.parts || []).map((p) => p.text || "").join("");
  if (!text.trim()) throw new Error("응답 본문이 비어 있습니다.");
  return text;
}

async function withRetry(fn, { retries = 5, onRetry } = {}) {
  let last;
  for (let i = 1; i <= retries; i++) {
    try {
      return await fn();
    } catch (e) {
      last = e;
      if (e instanceof ApiKeyError || e instanceof BlockedError) throw e;
      if (e.name === "AbortError") throw e;
      if (i === retries) break;
      const wait = Math.min(2 ** i, 8) * 1000 + Math.random() * 600;
      if (onRetry) onRetry(i, Math.round(wait / 1000), e);
      await sleep(wait);
    }
  }
  throw last;
}

/** 구조화 출력 1회 호출 → 파싱된 객체 */
export async function generateStructured({
  apiKey, model, system, prompt, schema, temperature = 0,
  maxOutputTokens = 12288, signal, onRetry,
}) {
  const body = {
    systemInstruction: { parts: [{ text: system }] },
    contents: [{ role: "user", parts: [{ text: prompt }] }],
    generationConfig: {
      temperature,
      maxOutputTokens,
      responseMimeType: "application/json",
      responseSchema: schema,
      thinkingConfig: { thinkingBudget: 0 },
    },
  };
  return withRetry(async () => {
    const text = await post(model, apiKey, body, signal);
    try {
      return JSON.parse(text);
    } catch {
      throw new Error("구조화 출력 파싱에 실패했습니다. 다시 시도해 주세요.");
    }
  }, { onRetry });
}

/** 자유 텍스트 대화 (ENDC). messages = [{role:'user'|'assistant', text}] */
export async function generateChat({
  apiKey, model, system, messages, temperature = 0.35,
  maxOutputTokens = 4096, signal, onRetry,
}) {
  const body = {
    systemInstruction: { parts: [{ text: system }] },
    contents: messages.map((m) => ({
      role: m.role === "assistant" ? "model" : "user",
      parts: [{ text: m.text }],
    })),
    generationConfig: {
      temperature, maxOutputTokens,
      thinkingConfig: { thinkingBudget: 0 },
    },
  };
  return withRetry(() => post(model, apiKey, body, signal), { onRetry });
}

/** 키가 살아 있는지 짧게 확인 (1토큰) */
export async function pingKey(apiKey, model) {
  const body = {
    contents: [{ role: "user", parts: [{ text: "ok" }] }],
    generationConfig: { maxOutputTokens: 1, temperature: 0,
                        thinkingConfig: { thinkingBudget: 0 } },
  };
  try {
    await post(model, apiKey, body);
    return { ok: true };
  } catch (e) {
    if (e.message && e.message.includes("최대 길이")) return { ok: true };   // 응답만 잘린 것
    return { ok: false, error: e };
  }
}
