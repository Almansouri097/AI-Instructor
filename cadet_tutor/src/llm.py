"""Thin wrapper around the local Ollama server with retries and clear errors."""
import time
from typing import Any

import ollama

from src import config


class OllamaError(RuntimeError):
    """Raised with a human-readable message when Ollama is unusable."""


_client = ollama.Client(host=config.OLLAMA_HOST)


def _explain(exc: Exception, model: str) -> OllamaError:
    """Turn low-level Ollama/HTTP exceptions into actionable messages."""
    if isinstance(exc, ollama.ResponseError) and exc.status_code == 404:
        return OllamaError(f"Model '{model}' is not installed. Run: ollama pull {model}")
    text = str(exc).lower()
    if isinstance(exc, ConnectionError) or "connect" in text or "refused" in text:
        return OllamaError(
            f"Cannot reach Ollama at {config.OLLAMA_HOST}. "
            "Start it with `ollama serve` (or open the Ollama app) and retry."
        )
    return OllamaError(f"Ollama error with model '{model}': {exc}")


def _with_retries(fn, model: str) -> Any:
    """Call fn(); retry transient failures, fail fast on a missing model."""
    last: Exception | None = None
    for attempt in range(config.LLM_RETRIES + 1):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - re-raised as OllamaError
            err = _explain(exc, model)
            if "not installed" in str(err):
                raise err from exc
            last = err
            time.sleep(1.5 * (attempt + 1))
    raise last  # type: ignore[misc]


def check_ollama(models: tuple[str, ...] = (config.LLM_MODEL, config.EMBED_MODEL)) -> list[str]:
    """Return a list of problems (empty list = server up and all models present)."""
    try:
        listed = _client.list()
    except Exception as exc:  # noqa: BLE001
        return [str(_explain(exc, config.LLM_MODEL))]
    names = {m.model for m in listed.models}
    problems = []
    for model in models:
        if model not in names and f"{model}:latest" not in names:
            problems.append(f"Model '{model}' is not installed. Run: ollama pull {model}")
    return problems


def embed(texts: list[str]) -> list[list[float]]:
    """Embed texts with the local embedding model, in batches."""
    vectors: list[list[float]] = []
    for i in range(0, len(texts), config.EMBED_BATCH):
        batch = texts[i : i + config.EMBED_BATCH]
        resp = _with_retries(
            lambda: _client.embed(model=config.EMBED_MODEL, input=batch), config.EMBED_MODEL
        )
        vectors.extend(list(v) for v in resp.embeddings)
    return vectors


def chat(messages: list[dict[str, str]], json_mode: bool = False) -> str:
    """Send a chat request to the local LLM and return the reply text."""
    resp = _with_retries(
        lambda: _client.chat(
            model=config.LLM_MODEL,
            messages=messages,
            format="json" if json_mode else "",
            options={"temperature": config.LLM_TEMPERATURE, "num_ctx": config.LLM_NUM_CTX},
        ),
        config.LLM_MODEL,
    )
    return resp.message.content or ""
