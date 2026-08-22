# OpenAI-Compatible API Reference

**Status**: `[VERIFIED]`

---

## 1. Architectural Justification: FastAPI Gateway vs. Native Colibrì Server

`[VERIFIED]` The project supports two interchangeable serving modes:

1. **Native Colibrì C Server (`coli serve`)**:
   - `[VERIFIED]` Thin, ultra-low-overhead C HTTP server and `c/openai_server.py` implementation natively packaged with Colibrì.
   - Ideal for direct production deployment in Linux/Colab runtimes.

2. **FastAPI Gateway (`api/app.py`)**:
   - `[VERIFIED]` Python-level abstraction providing decoupled security middleware, CORS management, structured `/health` readiness telemetry, and synthetic mock inference execution for offline test harnesses.
   - Enables end-to-end integration testing and automated verification without requiring live C compilations or 400 GB weight allocations on development machines.

---

## 2. Authentication & Security

`[VERIFIED]` All requests to `/v1/*` endpoints must include the `Authorization` header with a valid Bearer token matching `COLI_API_KEY`:

```http
Authorization: Bearer <COLI_API_KEY>
```

- Default binding is strictly `127.0.0.1:8000` to prevent unintended public network exposure.

---

## 3. Endpoints & Payloads

### `GET /health`
Returns runtime operational health and memory residency.

```json
{
  "status": "healthy",
  "engine": "colibri",
  "version": "1.5.0+",
  "model_id": "glm-5.2-744b-moe-int4",
  "resident_ram_gb": 9.9,
  "uptime_seconds": 1420
}
```

### `GET /v1/models`
Enumerates loaded model metadata.

### `POST /v1/chat/completions`
Standard OpenAI chat completions supporting both buffered JSON responses and Server-Sent Events (SSE) `text/event-stream` streaming.
