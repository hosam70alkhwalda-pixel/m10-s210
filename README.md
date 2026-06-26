# Module 10 — Stretch: Multi-Service Coordinator (Honors Track)

## Overview

This project implements a **multi-service orchestration system** that decomposes a monolithic AI backend into independent microservices and introduces a coordinator pattern for intelligent routing and aggregation.

The system includes:

- **NLP Service** → entity extraction / structured NLP processing
- **KG Service** → knowledge graph queries
- **RAG Service** → retrieval-augmented generation
- **Classifier Service** → determines which services should handle a query
- **Coordinator Service** → orchestrates classification, fan-out execution, and response aggregation

The architecture demonstrates a production-style **tool routing + orchestration pipeline**:

> classify → route → parallel execution → aggregate → handle partial failure

---

## Architecture

```
User Request
↓
Coordinator (FastAPI)
↓
Classifier Service (routing decision)
↓
Selected Services:
├── NLP Service
├── KG Service
└── RAG Service
↓
Async Fan-out (httpx)
↓
Aggregator
↓
Final Response
```

---

## Services

| Service | Role | Endpoint |
|--------|------|----------|
| nlp_svc | Entity extraction | `/extract` |
| kg_svc | Knowledge graph queries | `/kg/query` |
| rag_svc | Retrieval QA | `/rag/answer` |
| classifier_svc | Route selection | `/classify` |
| coordinator | Orchestration layer | `/answer` |

---

## Run Instructions

```bash
docker compose up --build -d
```

Verify health:

Coordinator: http://localhost:8000/healthz  
Classifier: http://localhost:8001/healthz  
NLP: http://localhost:8002/healthz  
KG: http://localhost:8003/healthz  
RAG: http://localhost:8004/healthz  

---

## Example Request

```bash
curl -X POST http://localhost:8000/answer \
-H "Content-Type: application/json" \
-d '{"question": "What is knowledge graph vs RAG?"}'
```

---

## Partial Failure Handling

If one or more upstream services fail or time out:

```json
{
  "results": {
    "rag_svc": { "...": "..." },
    "nlp_svc": { "...": "..." }
  },
  "partial": true,
  "responded": ["rag_svc", "nlp_svc"]
}
```

If all upstreams fail:

```json
{
  "detail": "all_upstreams_failed"
}
```

---

## 🔍 Observability & Runbook (IMPORTANT)

The coordinator implements structured request logging, emitting one log line per request including:

- inbound question
- classifier routing decision
- upstream services called
- upstream responses / failures
- total latency
- partial failure status

### Example Coordinator Logs

```
[INFO] request_id=abc123 question="What is knowledge graph vs RAG?"
[INFO] classifier_routes=["rag_svc"]
[INFO] calling rag_svc (timeout=10s)
[INFO] rag_svc response status=ok latency_ms=11.33
[INFO] responded=["rag_svc"]
[INFO] total_latency_ms=12.01 partial=false
```

---

### Partial Failure Example

```
[INFO] request_id=xyz789 question="Explain KG and RAG systems"
[INFO] classifier_routes=["kg_svc", "rag_svc"]
[INFO] calling kg_svc (timeout=5s)
[INFO] calling rag_svc (timeout=10s)
[WARN] rag_svc failed: connection error / timeout
[INFO] responded=["kg_svc"]
[INFO] total_latency_ms=4010 partial=true
```

---

## 🔬 Real Test Evidence (Your Run)

Actual system execution:

```
rag_svc:
status=ok
latency_ms=11.33
result="A mocked grounded answer [1]."

responded=["rag_svc"]
partial=false
```

---

## Design Decisions

### Why this architecture?

**Benefits:**
- Separation of concerns across AI components
- Independent scaling of NLP / KG / RAG services
- Flexible routing via classifier
- Resilient orchestration with partial failure support
- Production-like microservice decomposition

**Trade-offs:**
- Increased infrastructure complexity (5 services + networking)
- Higher debugging overhead vs monolith
- HTTP latency between services
- Requires strict contract enforcement between services

---

## Key Engineering Concepts Demonstrated

- Microservice decomposition
- API orchestration patterns
- Async fan-out with `httpx.AsyncClient`
- Timeout + failure isolation
- Structured logging (observability-ready)
- Classifier-based routing (agent-like behavior)




