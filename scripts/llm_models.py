"""List the models the configured API key can actually reach.

    uv run python scripts/llm_models.py

Model names move: a name that was current when code was written gets retired,
and the failure is a 404 at the first real call rather than anything a test
would catch. Asking the provider is the only reliable answer, so this exists
to be run rather than to have its answer memorised.

Only Gemini is implemented: it is the provider this project defaults to. For
another provider, read its own model list - LiteLLM does not expose a uniform
one.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

from football_ai.console import force_utf8
from football_ai.data.db import load_env

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def list_gemini(api_key: str) -> int:
    url = f"{GEMINI_URL}?key={api_key}&pageSize=200"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        print(f"HTTP {exc.code}: {body[:400]}", file=sys.stderr)
        if exc.code in (401, 403):
            print("\nThe key was rejected. Check GEMINI_API_KEY in .env.", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"cannot reach the API: {exc.reason}", file=sys.stderr)
        return 1

    models = [
        m
        for m in payload.get("models", [])
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]
    if not models:
        print("no models support generateContent with this key", file=sys.stderr)
        return 1

    print(f"{len(models)} model(s) usable for text generation:\n")
    for model in sorted(models, key=lambda m: m["name"]):
        name = model["name"].removeprefix("models/")
        label = model.get("displayName", "")
        limit = model.get("inputTokenLimit")
        extra = f"  in={limit:,}" if isinstance(limit, int) else ""
        print(f"  gemini/{name:<40} {label[:40]}{extra}")

    print("\nPut the one you want in .env, keeping the provider prefix:\n  LLM_MODEL=gemini/<name>")

    current = os.environ.get("LLM_MODEL", "")
    if not current:
        return 0

    bare = current.removeprefix("gemini/")
    listed = bare in {m["name"].removeprefix("models/") for m in models}
    print(f"\n.env asks for {current!r}: {'listed' if listed else 'NOT listed'} above.")

    # Being listed is not the same as being usable. models.list reports which
    # models exist; the "no longer available to new users" gate is applied by
    # generateContent at call time, so a model can appear here and still 404.
    # The only answer that means anything is an actual call.
    print("Checking whether it actually answers...")
    ok, detail = try_generate(api_key, bare)
    print(f"  {'WORKS' if ok else 'REFUSED'}: {detail}")
    if not ok:
        # A 503 means the model exists and is simply busy. Telling the reader
        # to pick a different name would send them to fix the wrong thing -
        # the same mistake the first version of the ask hint made with auth.
        busy = any(
            marker in detail.lower()
            for marker in ("503", "high demand", "unavailable", "overloaded", "429", "quota")
        )
        if busy:
            print(
                "\nThe name is fine - the model is busy right now. `make ask` retries\n"
                "transient failures on its own; wait a moment and try again, or pick a\n"
                "less contended model from the list (the -lite ones are usually free)."
            )
        else:
            print("\nPick another name from the list and set LLM_MODEL to it.")
        return 1
    print(
        "\nIf `make ask` times out while this call is quick, the delay is the\n"
        "real prompt (schema plus examples), not the network. Raise\n"
        "LLM_TIMEOUT_S in .env, or try a lite model from the list."
    )
    return 0


def try_generate(api_key: str, model: str, *, timeout_s: float = 120.0) -> tuple[bool, str]:
    """Smallest possible real call. Presence in a list proves nothing.

    Timed, because the number separates two very different problems: a slow
    network makes even this tiny prompt slow, while a fast tiny call next to a
    slow real one points at prompt size or at the model thinking before it
    answers.
    """
    url = f"{GEMINI_URL}/{model}:generateContent?key={api_key}"
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": "Reply with the single word: ok"}]}],
            "generationConfig": {"maxOutputTokens": 10},
        }
    ).encode()
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            json.load(response)
        elapsed = time.perf_counter() - started
        return True, f"answered a 6-word prompt in {elapsed:.1f}s"
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            message = json.loads(raw)["error"]["message"]
        except (ValueError, KeyError):
            message = raw[:200]
        return False, f"HTTP {exc.code}: {message[:220]}"
    except urllib.error.URLError as exc:
        return False, f"cannot reach the API: {exc.reason}"
    except TimeoutError:
        # A socket read timeout raises TimeoutError, which subclasses OSError
        # and not URLError, so the two handlers above do not see it. The first
        # run of this script crashed here rather than reporting the timeout.
        return False, "the request timed out after 30s; try again or check the network"
    except OSError as exc:
        return False, f"network error: {exc}"


def main() -> int:
    force_utf8()
    load_env()
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        print(
            "GEMINI_API_KEY is empty. Get one at https://aistudio.google.com/apikey "
            "and put it in .env.",
            file=sys.stderr,
        )
        return 2
    return list_gemini(key)


if __name__ == "__main__":
    sys.exit(main())
