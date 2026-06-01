"""Provider failover proof.

Verifies that with `AI_PROVIDER_CHAIN=anthropic,openai` an LLM call which
fails on anthropic transitions to openai. We deliberately inject a failure by
pointing the api_base for the primary provider to an invalid URL via env
override, then call the chat layer directly.

Strategy: easier than env hacking — directly construct AIProviderService with
a forced chain whose head is a known-broken provider. We monkey-patch
`PROVIDER_DEFAULT_CHAT_MODEL` for the head to a model that the Emergent proxy
will reject, forcing failover.

Run:
    cd /app/backend
    python -m scripts.failover_check
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")


async def main() -> int:
    from services import ai_provider as ap

    # Patch model registry: make 'anthropic' point to a nonexistent model so
    # the call fails, then the chain falls back to openai (real model).
    original = dict(ap.PROVIDER_DEFAULT_CHAT_MODEL)
    ap.PROVIDER_DEFAULT_CHAT_MODEL["anthropic"] = "does-not-exist-model-xyz"

    os.environ["AI_PROVIDER"] = "anthropic"
    os.environ["AI_PROVIDER_CHAIN"] = "anthropic,openai"

    # Fresh singleton so it picks up env + patched registry
    ap._singleton = None
    provider = ap.get_ai_provider()
    print(f"[failover] chain={provider.provider_chain}")

    try:
        result = await provider.chat(
            messages=[
                {"role": "system", "content": "Reply with the single word OK."},
                {"role": "user", "content": "ping"},
            ],
            json_mode=False,
            temperature=0,
            max_tokens=20,
        )
        print(f"[failover] provider_used={result.provider_used}")
        print(f"[failover] text={result.text!r}")
        print(f"[failover] fallback_event={result.fallback_event}")
        print(f"[failover] tokens={result.token_usage}")
        if result.fallback_event and result.fallback_event.get("from_provider") == "anthropic" \
                and result.fallback_event.get("to_provider") == "openai":
            print("[failover] OVERALL: PASS")
            return 0
        print("[failover] OVERALL: FAIL — expected anthropic→openai fallback")
        return 1
    finally:
        ap.PROVIDER_DEFAULT_CHAT_MODEL.clear()
        ap.PROVIDER_DEFAULT_CHAT_MODEL.update(original)


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
