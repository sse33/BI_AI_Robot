"""
ai_client.py — 统一 AI 调用封装

所有模块通过此接口调用 AI，provider / streaming / vision 细节对调用方透明。

用法：
  from ai_client import call_ai

  # 基本调用（自动读取 AI_PROVIDER 环境变量）
  text = call_ai(system, user)

  # 流式输出到控制台
  text = call_ai(system, user, on_delta=sys.stdout.write)

  # Vision 调用（Gemini 专用）
  text = call_ai("", prompt, provider="gemini", image_b64=img_b64)
"""

import json
import os
from typing import Callable

import requests


def call_ai(
    system: str,
    user: str,
    provider: str | None = None,
    *,
    temperature: float = 0.2,
    max_tokens: int = 4096,
    stream: bool = True,
    on_delta: Callable[[str], None] | None = None,
    image_b64: str | None = None,
    image_mime: str = "image/png",
    thinking: bool = False,
    thinking_budget: int | None = None,
) -> str:
    """
    统一 AI 调用入口。

    provider        默认读取环境变量 AI_PROVIDER（gemini / claude / azure / openai）。
    stream          True 时使用流式，避免企业代理超时，推荐始终开启。
    on_delta        每收到一个文本块时的回调，常用于实时打印到控制台。
    image_b64       base64 图片数据，Gemini Vision 专用。
    thinking        仅 Claude，启用 adaptive thinking。
    thinking_budget Gemini 专用，限制 thinking token 预算（0 = 关闭 thinking）。
    """
    if provider is None:
        provider = os.environ.get("AI_PROVIDER", "gemini").lower()

    if provider == "gemini":
        return _gemini(system, user, temperature, max_tokens, stream, on_delta,
                       image_b64, image_mime, thinking_budget)
    elif provider == "claude":
        return _claude(system, user, temperature, max_tokens, stream, on_delta, thinking)
    elif provider == "azure":
        return _azure(system, user, temperature, max_tokens, on_delta)
    elif provider == "openai":
        return _openai(system, user, temperature, max_tokens, on_delta)
    else:
        raise ValueError(f"不支持的 provider: {provider}，可选: gemini / claude / azure / openai")


# ── Gemini ────────────────────────────────────────────────────────────────────

def _gemini(
    system: str, user: str, temperature: float, max_tokens: int,
    stream: bool, on_delta, image_b64: str | None, image_mime: str,
    thinking_budget: int | None = None,
) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    model   = os.environ.get("GEMINI_MODEL", "gemini-2.5-pro")

    user_parts = [{"text": user}]
    if image_b64:
        user_parts.append({"inline_data": {"mime_type": image_mime, "data": image_b64}})

    gen_cfg: dict = {"temperature": temperature, "maxOutputTokens": max_tokens}
    if thinking_budget is not None:
        gen_cfg["thinkingConfig"] = {"thinkingBudget": thinking_budget}

    body: dict = {
        "contents": [{"role": "user", "parts": user_parts}],
        "generationConfig": gen_cfg,
    }
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}

    if stream:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:streamGenerateContent?alt=sse&key={api_key}"
        )
        print(f"[Gemini] {model}（流式）")
        resp = requests.post(
            url, headers={"Content-Type": "application/json"},
            json=body, stream=True, timeout=300,
        )
        if not resp.ok:
            raise RuntimeError(f"Gemini API 错误 {resp.status_code}: {resp.text[:200]}")

        full_text = ""
        buf = ""
        for raw in resp.iter_content(chunk_size=None):
            buf += raw.decode("utf-8")
            lines = buf.split("\n")
            buf = lines.pop()
            for line in lines:
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                if data in ("", "[DONE]"):
                    continue
                try:
                    obj   = json.loads(data)
                    parts = (obj.get("candidates", [{}])[0]
                             .get("content", {}).get("parts", []))
                    delta = "".join(
                        p.get("text", "") for p in parts
                        if not p.get("thought", False)
                    )
                    if delta:
                        if on_delta:
                            on_delta(delta)
                        full_text += delta
                except Exception:
                    pass
        resp.close()
        return full_text

    else:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        print(f"[Gemini] {model}")
        resp = requests.post(
            url, headers={"Content-Type": "application/json"},
            json=body, timeout=120,
        )
        resp.raise_for_status()
        rj = resp.json()
        candidate = rj.get("candidates", [{}])[0]
        finish_reason = candidate.get("finishReason", "")
        # 迭代所有 parts，拼接非 thinking 的文本（兼容 Gemini 2.5 Pro thinking mode）
        parts = candidate.get("content", {}).get("parts", [])
        text = "".join(
            p.get("text", "") for p in parts if not p.get("thought", False)
        )
        if not text:
            import json as _json
            raise RuntimeError(
                f"Gemini 返回空文本（finishReason={finish_reason}）\n"
                f"response: {_json.dumps(rj, ensure_ascii=False)[:500]}"
            )
        if on_delta:
            on_delta(text)
        return text


# ── Claude ────────────────────────────────────────────────────────────────────

def _claude(
    system: str, user: str, temperature: float, max_tokens: int,
    stream: bool, on_delta, thinking: bool,
) -> str:
    import anthropic
    model  = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    print(f"[Claude] {model}")

    thinking_cfg = {"type": "adaptive"} if thinking else {"type": "disabled"}

    if stream:
        full_text = ""
        with client.messages.stream(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
            thinking=thinking_cfg,
        ) as s:
            for delta in s.text_stream:
                if on_delta:
                    on_delta(delta)
                full_text += delta
        return full_text
    else:
        msg = client.messages.create(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = msg.content[0].text
        if on_delta:
            on_delta(text)
        return text


# ── Azure OpenAI ──────────────────────────────────────────────────────────────

def _azure(system: str, user: str, temperature: float, max_tokens: int, on_delta) -> str:
    endpoint    = os.environ.get("AZURE_OPENAI_ENDPOINT")
    api_key     = os.environ.get("AZURE_OPENAI_API_KEY")
    deployment  = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2025-01-01-preview")
    url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
    print(f"[Azure] {deployment}")

    resp = requests.post(
        url,
        headers={"Content-Type": "application/json", "api-key": api_key},
        json={
            "messages": [
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            "temperature": temperature,
            "max_tokens":  max_tokens,
        },
        timeout=300,
    )
    if not resp.ok:
        raise RuntimeError(f"Azure API 错误 {resp.status_code}: {resp.text[:200]}")
    text = resp.json()["choices"][0]["message"]["content"] or ""
    if on_delta:
        on_delta(text)
    return text


# ── OpenAI ────────────────────────────────────────────────────────────────────

def _openai(system: str, user: str, temperature: float, max_tokens: int, on_delta) -> str:
    from openai import OpenAI
    model  = os.environ.get("OPENAI_MODEL", "gpt-4o")
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    print(f"[OpenAI] {model}")

    full_text = ""
    s = client.chat.completions.create(
        model=model, stream=True, temperature=temperature, max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
    )
    for chunk in s:
        delta = chunk.choices[0].delta.content or ""
        if on_delta and delta:
            on_delta(delta)
        full_text += delta
    return full_text
