# Storage Feasibility & I/O Architecture Analysis

**Date**: 2026-08-23  
**Persistent Storage**: Google Drive (FUSE Mount)  
**Ephemeral Compute**: Google Colab Runtime Local Disk (NVMe SSD)  
**Engine I/O Pattern**: Colibrì Dynamic MoE Weight Streaming (`pread` / `O_DIRECT`)

---

## 1. Storage Capacity Requirements

The GLM-5.2 INT4 grouped-quantization model package requires:

| Component | Uncompressed Size | Notes |
| :--- | :--- | :--- |
| **Model Shards (`.safetensors`)** | ~378.5 GB | 38 shard files (~9.9 GB average) |
| **Tokenizer & Config Metadata** | ~15 MB | Vocabulary, chat templates, index mappings |
| **Runtime Working Scratchpad** | ~1.5 GB | `.coli_usage` state, KV cache buffers, logs |
| **Total Persistent Requirement** | **~380 GB** | **Requires Google Drive 2 TB tier or Workspace** |

---

## 2. Google Drive FUSE vs. Local NVMe I/O Profiling

Colibrì streams expert matrices during the forward pass of every generated token. The I/O latency directly dictates token generation velocity.

```
+-------------------------------------------------------------------------------+
|                             I/O Path Comparison                               |
|                                                                               |
| [Google Drive FUSE Path]                                                      |
| Colibri Engine -> POSIX pread() -> Linux FUSE Driver -> colab-drivefs daemon   |
| -> HTTPS Range Request -> Google Drive API -> Network TLS Roundtrip (~100ms)  |
|                                                                               |
| [Local NVMe SSD Path]                                                         |
| Colibri Engine -> POSIX pread() -> Linux VFS / Page Cache -> NVMe PCIe Bus    |
| -> Sub-millisecond direct hardware DMA (<0.2ms)                              |
+-------------------------------------------------------------------------------+
```

### Performance & Latency Matrix

| Metric | Google Drive FUSE (`/content/drive`) | Colab Local NVMe (`/content/model`) | Impact Factor |
| :--- | :--- | :--- | :--- |
| **Sequential Read Bandwidth** | 15 – 50 MB/s | 1,500 – 3,200 MB/s | **30x – 100x faster locally** |
| **Random Read Latency** | 50 – 300 ms (HTTPS + FUSE) | 0.05 – 0.3 ms (PCIe NVMe) | **300x – 1,000x lower latency** |
| **Concurrent I/O Threads** | Severely throttled by API rate limits | Scalable across CPU cores / OpenMP | Local allows multithreaded readahead |
| **Estimated Decode Speed** | **0.003 – 0.02 tok/s** (50–300s/tok) | **0.05 – 0.50 tok/s** (2–20s/tok) | Direct Drive is 15x–25x slower |
| **Session Persistence** | **Permanent** (survives Colab disconnects) | **Ephemeral** (wiped on runtime restart)| Drive is mandatory for persistence |

---

## 3. Storage Architecture Strategy

To resolve the tension between Google Drive's persistent preservation and local NVMe's required I/O throughput, the system implements a **three-tier hybrid storage strategy**:

```
+------------------------------------------------------------------------------+
|                       Three-Tier Hybrid Storage Flow                         |
|                                                                              |
|  +------------------------------------------------------------------------+  |
|  |                 Tier 1: Cold Persistent Golden Store                  |  |
|  |              Google Drive (`My Drive/AI/GLM-5.2/model/`)               |  |
|  |  - Complete 380 GB model safely preserved across session restarts       |  |
|  +------------------------------------------------------------------------+  |
|                                     |                                        |
|                          (Resumable Copy / Mirror)                           |
|                                     v                                        |
|  +------------------------------------------------------------------------+  |
|  |                  Tier 2: Warm Local NVMe Staging                      |  |
|  |             Colab Local Disk (`/content/model/` or Mirror)             |  |
|  |  - Fast streaming during active inference (1.5 - 3.0 GB/s)             |  |
|  |  - Supports Full Staging or Colibri Dual-Drive Partial Mirroring        |  |
|  +------------------------------------------------------------------------+  |
|                                     |                                        |
|                             (Active Compute)                                 |
|                                     v                                        |
|  +------------------------------------------------------------------------+  |
|  |                     Tier 3: Hot System RAM Cache                       |  |
|  |                  Colab RAM (`9.9 GB Resident Dense`)                   |  |
|  |  - Attention layers, shared experts, embeddings, and LRU hot-store     |  |
|  +------------------------------------------------------------------------+  |
+------------------------------------------------------------------------------+
```

### Staging Modes
1. **Mode A: Full Local Staging (Recommended when local disk $\ge 380\text{ GB}$)**:
   - Shards are copied from `/content/drive/...` to `/content/model/` prior to launch.
   - Inference runs at peak local NVMe throughput.
2. **Mode B: Dual-Drive Mirror Staging (`COLI_MODEL_MIRROR`)**:
   - For Colab instances with limited local disk (e.g., 150–200 GB free space), Colibri's native partial mirror features (`coli mirror stage --budget-gib 150`) stage the most frequently routed expert shards onto local NVMe while falling back to Google Drive for cold shards.
3. **Mode C: Direct Drive Streaming Benchmark**:
   - The engine streams directly from `/content/drive/...` to capture authentic empirical baseline metrics for research comparison in Phase 10.

---

## 4. Google Drive Quota and Rate Limit Protections

To avoid Google Drive API quota exhaustion:
- **Resumable Chunked Download**: Downloader script uses atomic chunk writes with backoff retry logic.
- **Header Caching**: Verification routines read and cache Safetensors headers rather than scanning entire 10 GB binary bodies repeatedly.
- **POSIX Safety**: Colibri runtime handles I/O errors gracefully with warning fallbacks rather than catastrophic process termination.
