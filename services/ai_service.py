"""
,ai - asks a question to a free, no-signup, no-API-key text
generation service (DevToolBox API, running on Cloudflare Workers).

HONEST GAP: this is a small hobbyist project with a shared global
quota (~500-1000 requests/day across ALL its users worldwide, not
just us) - it may run out or become unavailable at any time. Switched
to this from Pollinations because Pollinations' text.pollinations.ai
was returning "402 Payment Required" for anonymous requests on this
host's shared IP - a bug on their end (their own error message says
anonymous requests shouldn't be affected), not something fixable from
our side.
"""

from __future__ import annotations

import asyncio
import logging

import aiohttp

log = logging.getLogger("blade.ai")

API_URL = "https://devtoolbox-api.devtoolbox-api.workers.dev/ai/generate"


async def ask(question: str) -> str | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                API_URL, json={"prompt": question},
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                text = await resp.text()
                log.info("AI request status=%s, body preview=%r", resp.status, text[:200])

                if resp.status != 200:
                    return None

                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    return text.strip() or None

    except (aiohttp.ClientError, asyncio.TimeoutError, TimeoutError) as exc:
        log.warning("AI request failed: %r", exc)
        return None

    if isinstance(data, dict):
        answer = data.get("result") or data.get("response") or data.get("text") or data.get("output")
        if answer:
            return str(answer).strip()

    return None