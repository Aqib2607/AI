# Technical Discovery: GLM-5.2 Colibri Google Drive Runtime

**Date**: 2026-08-23  
**Status**: Phase 00 Discovery Complete  
**Engine Target**: Colibrì (`JustVugg/colibri`)  
**Upstream Model**: GLM-5.2 (744B Mixture-of-Experts)

---

## 1. Executive Summary

This document establishes the technical foundation, architectural mechanics, and environment discovery for running the **GLM-5.2 (744B)** frontier Mixture-of-Experts (MoE) model on consumer and cloud infrastructure using the **Colibrì** inference engine, persistently backed by **Google Drive** and executed within **Google Colab**.

Unlike dense monolithic models, GLM-5.2 activates only ~40B parameters (~5.4%) per token. Colibrì leverages this structural sparsity through **AI memory multitiering**, retaining dense layers (~17B parameters, ~9.9 GB at INT4) permanently in RAM while dynamically streaming required routed expert matrices from disk storage on demand.

---

## 2. Local Environment Discovery

An audit of the local development workstation was conducted:

| Parameter | Specification | Project Role |
| :--- | :--- | :--- |
| **Operating System** | Windows 11 Pro (x86_64) | Local development, testing, Git management |
| **CPU** | Intel Core i7-8650U (4 Cores / 8 Threads, 1.90GHz - 4.20GHz) | Local script execution & synthetic test harness |
| **Integrated GPU** | Intel UHD Graphics 620 | UI / Display only (no CUDA compute) |
| **System RAM** | 16 GB DDR4 | Local test execution with mock tensors |
| **Local Storage** | ~476 GB SSD | Workspace & code repository storage |
| **Development Toolchain**| Git 2.55.0, Node.js v24.19.0, npm 11.17.0 | Version control and optional frontend toolchain |

### Hardware Policy & Constraint Enforcement
- **No Local Full-Model Execution**: The local machine will not download or execute the full ~380 GB GLM-5.2 model. Heavy compute is decoupled to Google Colab.
- **Mock-Driven Testing**: All automated local unit and integration tests run against synthetic model manifests and mock binary headers without allocating hundreds of gigabytes of RAM or disk.

---

## 3. Colibrì Engine Deep-Dive

### Upstream Repository & Release State
- **Source Repository**: `https://github.com/JustVugg/colibri`
- **Language**: Pure C (C99), zero external runtime dependencies (no Python runtime required for C engine, no heavy BLAS dependencies).
- **Compilation Targets**: `gcc` or `clang` with OpenMP (`-fopenmp`), vector extensions (`ARCH=native` or `ARCH=x86-64-v3`), and optional CUDA support (`CUDA=1`).
- **Interfaces**:
  - `coli chat`: Interactive TUI console.
  - `coli serve`: OpenAI/Anthropic-compatible HTTP REST server.
  - `coli web`: Web dashboard with live expert routing visualizer, memory tier monitors, and token metrics.
  - `coli doctor`: Diagnostic command verifying environment, CPU features, and model integrity.
  - `coli cluster`: Distributed expert streaming across multiple network nodes.

### Weight Placement & Memory Multitiering
GLM-5.2 comprises 75 MoE layers, each containing 256 routed experts plus shared experts and multi-token prediction (MTP) heads (totaling 19,456 routed experts).

```
+-------------------------------------------------------------------------+
|                        Unified Memory Hierarchy                         |
|                                                                         |
|  +--------------------+   +---------------------+   +----------------+  |
|  |     VRAM Tier      |   |      RAM Tier       |   |  Storage Tier  |  |
|  |  (Optional CUDA)   |   | (Dense: ~9.9 GB I4) |   | (NVMe / Drive) |  |
|  | Hot Expert Staging |   | Attention & Shared  |   | 19,456 Experts |  |
|  |                    |   |  KV State (MLA 57x) |   |  (~380 GB I4)  |  |
|  +--------------------+   +---------------------+   +----------------+  |
|           ^                         ^                       ^           |
|           |                         |                       |           |
|           +----------- Routing Engine / JIT Prefetch -------+           |
+-------------------------------------------------------------------------+
```

### Per-Token Execution Pipeline
1. **Route**: Router evaluates gating logits for the current token and determines the top-K active experts per layer.
2. **Union**: Batched expert indices across concurrent requests/tokens are computed.
3. **Place / Fetch**: Active experts not present in the RAM LRU cache or hot-store are streamed from disk via `pread` / `O_DIRECT`.
4. **Overlap / Prefetch**: The router evaluates layer $L+1$ while layer $L$ compute executes, overlapping disk I/O with arithmetic.
5. **Learn**: Routing frequency is recorded into `.coli_usage`, progressively promoting frequently activated experts into pinned RAM tiers.

---

## 4. Upstream Serving & API Gateway

Colibrì provides an integrated OpenAI-compatible API gateway (`c/openai_server.py` and native C HTTP handler):
- **Endpoints Supported**:
  - `GET /health` — Runtime health and ready state.
  - `GET /v1/models` — Active model metadata and engine status.
  - `POST /v1/chat/completions` — Standard chat completions supporting:
    - JSON non-streaming responses.
    - Server-Sent Events (SSE) `text/event-stream` streaming.
    - Temperature, top-p, max_tokens, stop sequences.
    - Tool/function calling support rendered into model prompt format.
- **Security & Authentication**:
  - Controlled via `COLI_API_KEY` (Bearer token header authentication).
  - Default binding to `127.0.0.1:8000` to prevent accidental public network exposure.

---

## 5. Summary of Differences: Reference Video vs. Current Upstream

| Feature | Reference Video Approach | Current Upstream Standard | Reason for Change |
| :--- | :--- | :--- | :--- |
| **Model Repository** | `annelo/GLM-5.2-FP8-Uncensored-Colibri-Int4` | `mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp` | Grouped INT4 (`gs64`) eliminates repetition loops and token degradation present in older per-row INT4 conversions. |
| **Speculative Decoding** | Basic / Uncalibrated | INT8 MTP (Multi-Token Prediction) Speculative Head | Substantially increases tokens-per-second when cache hits occur. |
| **Storage Architecture** | Direct streaming from mounted Google Drive | Multi-tiered persistent Drive storage + Local NVMe staging / Dual-SSD Mirror | Google Drive FUSE latency imposes massive per-token delays; staging enables usable inference speeds. |
| **Build System** | Generic script build | Pinned Makefile build with `ARCH=native` OpenMP optimizations | Ensures maximum CPU vectorization and reproducible compiler output. |
