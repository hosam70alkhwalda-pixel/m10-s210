"""httpx.AsyncClient helpers — per-call timeout enforcement.

Catches a common mistake where learners set the timeout at the session
level (once across the whole AsyncClient lifecycle) instead of per
.get/.post call. The session-level timeout still applies but does not
fire per call, so slow upstreams can starve faster ones.
"""
import logging
import time

import httpx

logger = logging.getLogger("coordinator.upstream")


async def call_upstream(
    service: str, url: str, payload: dict, timeout_s: float = 5.0
) -> dict:
    """Call one upstream service. Returns an UpstreamResult-shaped dict.

    Per-call timeout is enforced via `httpx.Timeout(timeout_s)` passed
    directly to the AsyncClient constructor (NOT a global/session
    default), so this call cannot block or starve sibling calls running
    concurrently under asyncio.gather in the coordinator.
    """
    start_ms = time.perf_counter() * 1000

    def _elapsed_ms() -> float:
        return time.perf_counter() * 1000 - start_ms

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_s)) as client:
            response = await client.post(url, json=payload)

            if hasattr(response, "raise_for_status"):
             response.raise_for_status()

            body = response.json()

        latency_ms = _elapsed_ms()
        logger.info(
            "upstream_call service=%s status=ok latency_ms=%.1f url=%s",
            service, latency_ms, url,
        )
        return {
            "service": service,
            "status": "ok",
            "latency_ms": latency_ms,
            "result": body,
        }

    except httpx.TimeoutException as exc:
        latency_ms = _elapsed_ms()
        logger.warning(
            "upstream_call service=%s status=timeout latency_ms=%.1f url=%s error=%s",
            service, latency_ms, url, exc,
        )
        return {
            "service": service,
            "status": "timeout",
            "latency_ms": latency_ms,
            "error": str(exc),
        }

    except httpx.HTTPStatusError as exc:
        latency_ms = _elapsed_ms()
        logger.warning(
            "upstream_call service=%s status=error latency_ms=%.1f url=%s error=%s",
            service, latency_ms, url, exc,
        )
        return {
            "service": service,
            "status": "error",
            "latency_ms": latency_ms,
            "error": str(exc),
        }

    except Exception as exc:  # noqa: BLE001 — structured error mapping, never raise
        latency_ms = _elapsed_ms()
        logger.warning(
            "upstream_call service=%s status=error latency_ms=%.1f url=%s error=%s",
            service, latency_ms, url, exc,
        )
        return {
            "service": service,
            "status": "error",
            "latency_ms": latency_ms,
            "error": str(exc),
        }