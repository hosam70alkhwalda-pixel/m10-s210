"""Multi-service coordinator — Stretch Thu (Honors Track).

The coordinator exposes a single POST /answer endpoint. On each call it:
1. Calls the classifier service to identify which downstream service(s)
   should answer the question.
2. Fans out to the selected service(s) via httpx.AsyncClient with a
   per-call 5-second timeout (10s for rag_svc — generation dominates).
3. Aggregates the responses and returns a single AnswerResponse.
4. If any upstream returns a 5xx or times out, the coordinator returns
   200 with `partial: true` and a per-service attribution payload —
   never a 5xx that would lose a working upstream's response.
"""
import asyncio
import logging
import os
from typing import Any, Dict, List

import httpx
from fastapi import FastAPI, HTTPException

from models import AnswerRequest, AnswerResponse
from upstream import call_upstream

logger = logging.getLogger("coordinator.main")

app = FastAPI(title="Stretch Thu — Multi-Service Coordinator")

CLASSIFIER_URL = os.getenv("CLASSIFIER_URL", "http://classifier_svc:8001/classify")

SERVICE_URLS: Dict[str, str] = {
    "nlp_svc": os.getenv("NLP_SVC_URL", "http://nlp_svc:8001/extract"),
    "kg_svc": os.getenv("KG_SVC_URL", "http://kg_svc:8001/kg/query"),
    "rag_svc": os.getenv("RAG_SVC_URL", "http://rag_svc:8001/rag/answer"),
}

# RAG generation dominates latency, so it gets a longer per-call budget.
SERVICE_TIMEOUTS: Dict[str, float] = {
    "nlp_svc": 5.0,
    "kg_svc": 5.0,
    "rag_svc": 10.0,
}

CLASSIFIER_TIMEOUT_S = 5.0


async def _classify(question: str) -> List[dict]:
    """Ask the classifier which downstream service(s) should answer.

    Returns the raw `routes` list: [{"service": ..., "confidence": ...}, ...]
    """
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(CLASSIFIER_TIMEOUT_S)) as client:
            resp = await client.post(CLASSIFIER_URL, json={"question": question})
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "classifier_unreachable", "message": str(exc)},
        ) from exc

    routes = data.get("routes") or []
    if not routes:
        raise HTTPException(
            status_code=503,
            detail={"error": "no_routes", "message": "classifier returned no routes"},
        )
    return routes


@app.post("/answer", response_model=AnswerResponse)
async def answer(req: AnswerRequest) -> AnswerResponse:
    """Classify → fan out → aggregate → respond.

    `partial` is True iff at least one selected upstream failed/timed out
    while at least one other upstream succeeded. If every selected
    upstream fails, raises 503 with structured detail instead of
    returning an all-empty 200.
    """
    routes = await _classify(req.question)
    selected = [r["service"] for r in routes if r.get("service") in SERVICE_URLS]

    if not selected:
        raise HTTPException(
            status_code=503,
            detail={"error": "no_valid_routes", "routes": routes},
        )

    calls = {
        service: call_upstream(
            service,
            SERVICE_URLS[service],
            {"question": req.question},
            timeout_s=SERVICE_TIMEOUTS.get(service, 5.0),
        )
        for service in selected
    }

    outcomes = await asyncio.gather(*calls.values())

    results: Dict[str, Any] = {}
    responded: List[str] = []
    failed: List[str] = []

    for service, outcome in zip(calls.keys(), outcomes):
        if hasattr(outcome, "model_dump"):
            outcome = outcome.model_dump()
        results[service] = outcome
        if outcome.get("status") == "ok":
            responded.append(service)
        else:
            failed.append(service)

    if not responded:
        raise HTTPException(
            status_code=503,
            detail={"error": "all_upstreams_failed", "results": results},
        )

    partial = len(failed) > 0
    if partial:
        logger.info(
            "answer request question=%r responded=%s failed=%s partial=True",
            req.question, responded, failed,
        )

    return AnswerResponse(results=results, partial=partial, responded=responded)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}