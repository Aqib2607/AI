# System Architecture & Technical Specifications

---

## 1. High-Level Logical Flow

```
+─────────────────────────────────────────────────────────────────────────────+
|                         End-to-End System Topology                          |
|                                                                             |
|  [Hugging Face Repository: mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp] |
|                                      │                                      |
|                                      ▼ (Resumable HTTPS Chunk Downloader)   |
|            [Google Drive Persistent Storage (/content/drive/)]              |
|                                      │                                      |
|                 ┌────────────────────┴────────────────────┐                 |
|                 ▼ (Full NVMe Staging)                     ▼ (Dual-SSD Mirr) |
|   [Colab Local NVMe (/content/model/)]      [Dual Storage Hybrid Routing]   |
|                 │                                         │                 |
|                 └────────────────────┬────────────────────┘                 |
|                                      │                                      |
|                                      ▼                                      |
|  [Colibrì v1.4.0+ Pure-C Engine (OpenMP Parallelized, Memory Multitiering)]  |
|         ├── Tier 1: 9.9 GB Resident RAM (Attention / Shared Experts)        |
|         ├── Tier 2: Disk-Streamed Expert Matrices (pread() / O_DIRECT)      |
|         └── Tier 3: Learned Hot-Store (.coli_usage) & INT8 MTP Speculation  |
|                                      │                                      |
|                                      ▼                                      |
|          [OpenAI-Compatible REST API Gateway (FastAPI / Uvicorn)]            |
|         ├── GET  /health (Readiness / RAM telemetry)                        |
|         ├── GET  /v1/models (Model metadata)                                |
|         └── POST /v1/chat/completions (JSON & SSE Event Streams)            |
|                                      │                                      |
|                                      ▼                                      |
|               [Web Interface / Client SDK / REST Consumers]                 |
+─────────────────────────────────────────────────────────────────────────────+
```

---

## 2. Memory Tiering & Placement Architecture

The GLM-5.2 architecture activates only **~40B parameters** out of 744B per token. Colibrì exploits this sparsity:

### Tier Allocation

| Memory Tier | Hardware Location | Data Held | Access Latency |
| :--- | :--- | :--- | :--- |
| **Tier 1: Resident RAM** | Colab System RAM (~9.9 GB) | Attention matrices, shared experts, token embeddings, MLA KV cache | $\sim 50\text{--}80\text{ ns}$ |
| **Tier 2: Fast Local NVMe**| `/content/model/` (NVMe SSD) | Staged expert shards (19,456 routed experts, ~378 GB) | $\sim 0.1\text{--}0.3\text{ ms}$ |
| **Tier 3: Persistent Drive**| `/content/drive/...` (FUSE) | Cold model weights & fallback shards | $\sim 50\text{--}300\text{ ms}$ |

---

## 3. Data Flow During Forward Pass

1. **Token Ingestion**: Request arrives at FastAPI `/v1/chat/completions`, Bearer token is verified, and prompt is passed to Colibrì runtime.
2. **Dense Layer Forward**: Attention query/key/value projections and dense shared experts execute entirely in system RAM.
3. **MoE Routing**: Gating network computes routing logits for top-$K$ experts across all 75 layers.
4. **JIT Expert Streaming**: Required expert weights are streamed into temporary buffers via `pread()`. Prefetch worker loads layer $L+1$ while layer $L$ computes.
5. **Speculative Head**: INT8 MTP head generates draft tokens; forward validation verifies drafts in a batched pass.
6. **Response Streaming**: Tokens are streamed via SSE `data: {"choices":[{"delta":{"content":"..."}}]}`.
