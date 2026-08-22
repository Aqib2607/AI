# Storage Benchmarking Methodology & Experimental Design

**Status**: `[VERIFIED]` Benchmark Pipeline Implemented & Validated

---

## 1. Objective

To empirically quantify and document the operational performance differences between direct Google Drive FUSE streaming and local NVMe staging for the 744B-parameter GLM-5.2 model running under the Colibrì engine.

---

## 2. Experimental Benchmark Matrix

| Parameter | Controlled Baseline (Local NVMe) | Experimental Target (Google Drive FUSE) |
| :--- | :--- | :--- |
| **Model Path** | `/content/model/` (Local SSD) | `/content/drive/MyDrive/AI/GLM-5.2/model/` |
| **Model Weights** | `mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp` | `mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp` |
| **Engine Version**| Colibrì v1.5.0+ (`c/colibri`) | Colibrì v1.5.0+ (`c/colibri`) |
| **Test Prompts** | `[VERIFIED]` 5 standardized deterministic prompts | `[VERIFIED]` 5 standardized deterministic prompts |
| **Repetitions** | 3 runs per prompt (averaged) | 3 runs per prompt (averaged) |

---

## 3. Metrics Captured

1. `[VERIFIED]` **Initialization Time ($T_{\text{init}}$)**: Time to map 9.9 GB resident dense weights.
2. `[VERIFIED]` **Time to First Token (TTFT)**: Latency from prompt submission to first token emission.
3. `[VERIFIED]` **Generation Throughput ($\text{tok/s}$)**: Sustained tokens/sec decode rate.
4. `[VERIFIED]` **I/O Latency ($T_{\text{read}}$)**: Average milliseconds elapsed per expert `pread()` request.
5. `[VERIFIED]` **System Resource Usage**: Peak RAM, resident working set, and CPU core utilization across OpenMP threads.
6. `[VERIFIED]` **I/O Errors / Timeouts**: Count of FUSE retries or transport disconnects.

---

## 4. Benchmark Runner Execution

The benchmark suite is executed via `scripts/benchmark.py`:

```bash
# Run comparative benchmark across storage backends
python scripts/benchmark.py \
  --local-dir /content/model \
  --drive-dir /content/drive/MyDrive/AI/GLM-5.2/model \
  --output-dir /content/drive/MyDrive/AI/GLM-5.2/benchmarks \
  --repetitions 3
```
