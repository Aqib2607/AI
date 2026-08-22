# OpenAI-Compatible REST API Gateway

The API layer provides a standardized OpenAI and Anthropic compatible interface for the Colibrì inference engine, supporting both buffered JSON responses and Server-Sent Events (SSE) streaming.

---

## 📡 Endpoints

### 1. Health Probe
- **Endpoint**: `GET /health`
- **Authentication**: None
- **Response**:
```json
{
  "status": "healthy",
  "engine": "colibri",
  "model": "mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp",
  "version": "1.4.0+",
  "resident_ram_gb": 9.9
}
```

### 2. List Models
- **Endpoint**: `GET /v1/models`
- **Authentication**: `Bearer <COLI_API_KEY>`
- **Response**:
```json
{
  "object": "list",
  "data": [
    {
      "id": "glm-5.2-744b-moe-int4",
      "object": "model",
      "created": 1724371200,
      "owned_by": "colibri"
    }
  ]
}
```

### 3. Chat Completions
- **Endpoint**: `POST /v1/chat/completions`
- **Authentication**: `Bearer <COLI_API_KEY>`
- **Request Body**:
```json
{
  "model": "glm-5.2-744b-moe-int4",
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Explain recursion in simple terms."}
  ],
  "temperature": 0.7,
  "top_p": 0.9,
  "max_tokens": 512,
  "stream": true
}
```

---

## 🔒 Authentication

All `/v1/*` endpoints require a Bearer token in the `Authorization` header:
```
Authorization: Bearer <COLI_API_KEY>
```
If `COLI_API_KEY` is set in the environment or `.env`, requests without the corresponding matching token will be rejected with HTTP `401 Unauthorized`.
