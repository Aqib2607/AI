# Reference Video Workflow Reproduction & Improvements

---

## 1. Reference Workflow Trace

The reference video demonstrated:
1. Connecting to a Google Colab notebook environment.
2. Mounting Google Drive persistently.
3. Downloading the `annelo/GLM-5.2-FP8-Uncensored-Colibri-Int4` model directly to Google Drive.
4. Compiling the Colibrì inference engine.
5. Pointing Colibrì directly to `/content/drive/MyDrive/...` to execute prompt completions.

---

## 2. Architectural Comparison & Technical Enhancements

| Workflow Component | Reference Video Approach | Enhanced Project Implementation | Engineering Rationale |
| :--- | :--- | :--- | :--- |
| **Model Selection** | `annelo/GLM-5.2-FP8-Uncensored-Colibri-Int4` | `mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp` (with fallback to `annelo`) | Grouped INT4 ($gs=64$) prevents repetition loops and degradation found in earlier per-row conversions. |
| **Speculative Decoding** | None / Unconfigured | Native INT8 MTP Speculative Head | Accelerates token throughput up to 1.8x when cache is warm. |
| **Storage Architecture** | Direct Drive Streaming only | Multi-Tier Persistent Drive + Local NVMe Staging / Dual-Drive Mirroring | Google Drive FUSE latency causes 50–300s/tok generation; local NVMe staging achieves 0.05–0.5 tok/s. |
| **Integrity Validation** | Manual / Ad-hoc | Automated non-destructive Safetensors header validation (`scripts/model_verify.py`) | Prevents running corrupted or incomplete shard sets. |
| **API Exposure** | Manual CLI interaction | Full OpenAI-compatible REST server (`/v1/chat/completions` with SSE streaming) | Enables standard client SDKs, WebUIs, and automated evaluation harnesses. |
| **Benchmarking** | Visual observation | Systematic empirical benchmark suite (`scripts/benchmark.py`) | Captures empirical latency, TTFT, and throughput metrics across storage tiers. |
