# Storage Benchmarking Methodology & Experimental Design

---

## 1. Objective

To empirically quantify and document the operational performance differences between direct Google Drive FUSE streaming and local NVMe staging for the 744B-parameter GLM-5.2 model running under the Colibrì engine.

---

## 2. Test Matrix & Variables

| Parameter | Controlled Baseline (Local NVMe) | Experimental Target (Google Drive FUSE) |
| :--- | :--- | :--- |
| **Model Path** | `/content/model/` (Local SSD) | `/content/drive/MyDrive/AI/GLM-5.2/model/` |
| **Model Weights** | `mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp` | `mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp` |
| **Engine Version**| Colibrì v1.4.0+ (`c/colibri`) | Colibrì v1.4.0+ (`c/colibri`) |
| **Test Prompts** | 5 standardized deterministic prompts | 5 standardized deterministic prompts |
| **Warmup Phase** | 2 unmeasured warmup prompts | 2 unmeasured warmup prompts |
| **Repetitions** | 3 runs per prompt (averaged) | 3 runs per prompt (averaged) |

---

## 3. Metrics Captured

1. **Initialization Time ($T_{\text{init}}$)**: Duration to load 9.9 GB dense resident weights and initialize Safetensors headers.
2. **Time to First Token (TTFT)**: Duration from prompt submission to first generated token emission.
3. **Generation Throughput ($\text{tok/s}$)**: Sustained tokens generated per second during the decode phase.
4. **I/O Latency ($T_{\text{read}}$)**: Average milliseconds elapsed per expert `pread()` request.
5. **System Resource Usage**: Peak RAM, resident working set, and CPU core utilization across OpenMP threads.
6. **I/O Errors / Timeouts**: Count of FUSE retries or transport disconnects.

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
