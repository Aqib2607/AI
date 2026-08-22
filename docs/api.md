# OpenAI-Compatible API Reference

The runtime exposes a compliant OpenAI/Anthropic REST API gateway at `http://127.0.0.1:8000`.

---

## 1. Authentication

All requests to `/v1/*` endpoints must include the `Authorization` header with a valid Bearer token matching `COLI_API_KEY`:

```http
Authorization: Bearer <COLI_API_KEY>
```

---

## 2. API Endpoints

### `GET /health`
Returns the operational health and ready status of the inference engine.

**Response**:
```json
{
  "status": "healthy",
  "engine": "colibri",
  "version": "1.4.0+",
  "model_id": "glm-5.2-744b-moe-int4",
  "resident_ram_gb": 9.9,
  "uptime_seconds": 1420
}
```

### `GET /v1/models`
Enumerates loaded and available models.

**Response**:
```json
{
  "object": "list",
  "data": [
    {
      "id": "glm-5.2-744b-moe-int4",
      "object": "model",
      "created": 1724371200,
      "owned_by": "colibri",
      "permission": [],
      "root": "mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp",
      "parent": null
    }
  ]
}
```

### `POST /v1/chat/completions`
Generates completions for a sequence of conversation messages.

**Request Schema**:
```json
{
  "model": "glm-5.2-744b-moe-int4",
  "messages": [
    {"role": "system", "content": "You are an expert systems programmer."},
    {"role": "user", "content": "Write a C function to parse an 8-byte Safetensors header length."}
  ],
  "temperature": 0.7,
  "top_p": 0.9,
  "max_tokens": 1024,
  "stream": true
}
```

**SSE Stream Output**:
```
data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1724371205,"model":"glm-5.2-744b-moe-int4","choices":[{"index":0,"delta":{"role":"assistant","content":"Here is"},"finish_reason":null}]}

data: {"id":"chatcmpl-1","object":"chat.completion.chunk","created":1724371206,"model":"glm-5.2-744b-moe-int4","choices":[{"index":0,"delta":{"content":" the C code:"},"finish_reason":null}]}

data: [DONE]
```
