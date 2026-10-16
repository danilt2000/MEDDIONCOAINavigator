import hashlib
import json
import logging
import os
import re
import threading
from pathlib import Path

from app.config import settings

log = logging.getLogger(__name__)

TIMEOUT_S = 25.0
MAX_RETRIES = 3

_client = None
_client_lock = threading.Lock()


def llm_enabled() -> bool:
    return settings.llm_enabled and bool(settings.openai_api_key)


def get_client():
    global _client
    with _client_lock:
        if _client is None:
            from openai import OpenAI

            # The SDK retries connection errors, timeouts, 429 and 5xx with exponential backoff.
            _client = OpenAI(api_key=settings.openai_api_key, timeout=TIMEOUT_S, max_retries=MAX_RETRIES)
        return _client


def complete_json(
    system: str, user: str, schema: dict, name: str, effort: str | None = "low", max_tokens: int = 4000
) -> tuple[dict, dict] | None:
    """One structured-output call. Returns (parsed JSON, usage) or None on any failure."""
    import openai

    request = {
        "model": settings.llm_model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "response_format": {"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
        "max_completion_tokens": max_tokens,
    }
    if effort:
        request["reasoning_effort"] = effort
    try:
        try:
            response = get_client().chat.completions.create(**request)
        except openai.BadRequestError as error:
            if "reasoning" not in str(error).lower():
                raise
            request.pop("reasoning_effort")
            response = get_client().chat.completions.create(**request)
        choice = response.choices[0]
        if choice.finish_reason != "stop" or not choice.message.content:
            log.warning("LLM %s: no usable content (finish_reason=%s)", name, choice.finish_reason)
            return None
        usage = response.usage.model_dump(exclude_none=True) if response.usage else {}
        return json.loads(choice.message.content), usage
    except Exception as error:
        log.warning("LLM %s failed: %s", name, type(error).__name__)
        return None


def cache_path(kind: str, system: str, user: str, schema: dict) -> Path:
    key = json.dumps([settings.llm_model, system, user, schema], ensure_ascii=False, sort_keys=True)
    return settings.cache_dir / kind / f"{hashlib.sha256(key.encode('utf-8')).hexdigest()}.json"


def cached_json(kind: str, system: str, user: str, schema: dict, name: str, **options) -> dict | None:
    """Disk-cached complete_json: a hit never touches the network (even with the LLM switched off)."""
    path = cache_path(kind, system, user, schema)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))["output"]
        except (OSError, ValueError, KeyError):
            pass
    if not llm_enabled():
        return None
    result = complete_json(system, user, schema, name, **options)
    if result is None:
        return None
    output, usage = result
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"{path.stem}.{os.getpid()}.{threading.get_ident()}.tmp")
    record = {"model": settings.llm_model, "kind": kind, "user": user, "usage": usage, "output": output}
    temp.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temp, path)
    return output


_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _canonical(token: str) -> str:
    whole, _, fraction = token.replace(",", ".").partition(".")
    whole = whole.lstrip("0") or "0"
    fraction = fraction.rstrip("0")
    return f"{whole}.{fraction}" if fraction else whole


def numbers(text: str) -> set[str]:
    """Numbers in text, canonical so that "09" == "9" and "85,0" == "85"."""
    return {_canonical(match) for match in _NUMBER.findall(text)}


def adds_numbers(output: str, source: str) -> bool:
    """True when the LLM output contains a number that is not in its source text."""
    return not numbers(output) <= numbers(source)


def cache_stats(kind: str) -> dict:
    files = list((settings.cache_dir / kind).glob("*.json"))
    totals = {"files": len(files), "bytes": 0, "prompt_tokens": 0, "cached_tokens": 0, "completion_tokens": 0}
    for path in files:
        totals["bytes"] += path.stat().st_size
        usage = json.loads(path.read_text(encoding="utf-8")).get("usage", {})
        totals["prompt_tokens"] += usage.get("prompt_tokens", 0)
        totals["cached_tokens"] += usage.get("prompt_tokens_details", {}).get("cached_tokens", 0)
        totals["completion_tokens"] += usage.get("completion_tokens", 0)
    return totals
