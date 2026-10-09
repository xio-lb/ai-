import hashlib
import json
import os
import re
import time

from dotenv import load_dotenv
from openai import OpenAI

from app.services.observability import record_llm_call

load_dotenv()

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
)

MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
PROMPT_VERSION = os.getenv("PROMPT_VERSION", "v1")
INPUT_COST_PER_1M = float(os.getenv("DEEPSEEK_INPUT_COST_PER_1M", "0") or 0)
OUTPUT_COST_PER_1M = float(os.getenv("DEEPSEEK_OUTPUT_COST_PER_1M", "0") or 0)


def _prompt_hash(system_prompt: str) -> str:
    return hashlib.sha256((system_prompt or "").encode("utf-8")).hexdigest()[:12]


def _usage_value(usage: object, name: str) -> int:
    try:
        return int(getattr(usage, name, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _record_llm_response(
    response: object | None,
    prompt_name: str,
    system_prompt: str,
    started: float,
    success: bool = True,
    error: str = "",
) -> None:
    usage = getattr(response, "usage", None) if response is not None else None
    prompt_tokens = _usage_value(usage, "prompt_tokens")
    completion_tokens = _usage_value(usage, "completion_tokens")
    total_tokens = _usage_value(usage, "total_tokens") or (
        prompt_tokens + completion_tokens
    )
    estimated_cost = (
        prompt_tokens / 1_000_000 * INPUT_COST_PER_1M
        + completion_tokens / 1_000_000 * OUTPUT_COST_PER_1M
    )
    record_llm_call(
        name=prompt_name,
        model=MODEL,
        prompt_hash=_prompt_hash(system_prompt),
        prompt_version=PROMPT_VERSION,
        duration_ms=(time.perf_counter() - started) * 1000,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost=estimated_cost,
        success=success,
        error=error,
    )


def chat(
    user_prompt: str,
    system_prompt: str = "你是一个旅行规划助手。",
    prompt_name: str = "chat",
) -> str:
    started = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
        )
    except Exception as exc:
        _record_llm_response(None, prompt_name, system_prompt, started, False, str(exc))
        raise
    _record_llm_response(response, prompt_name, system_prompt, started)
    return response.choices[0].message.content


def _parse_json(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    return json.loads(content)


def chat_json(
    user_prompt: str,
    system_prompt: str = "你是一个旅行规划助手。",
    prompt_name: str = "chat_json",
) -> dict:
    started = time.perf_counter()
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.7,
            response_format={"type": "json_object"},
        )
    except Exception as exc:
        _record_llm_response(None, prompt_name, system_prompt, started, False, str(exc))
        raise
    _record_llm_response(response, prompt_name, system_prompt, started)
    content = response.choices[0].message.content
    return _parse_json(content)
