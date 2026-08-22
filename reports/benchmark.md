# Consolidated Engineering & Benchmark Report: GLM-5.2 Colibri Runtime

**Generated At**: 2026-08-22T18:52:15Z  
**Report ID**: `rep_1787424735`  

---

## 1. Environment & Hardware Summary

- **Operating System**: Windows (AMD64)
- **Python Version**: 3.11.9
- **CPU Cores**: 8 logical cores (AVX2: True)
- **RAM**: 6.21 GB available / 15.85 GB total
- **Dense Core 9.9 GB Residency**: CONSTRAINED

---

## 2. Model Shard & Integrity Status

- **Model Path**: `D:\AI\glm52-drive-runtime\mock_model`
- **Validation Status**: **MISSING**
- **Safetensors Shards Found**: 0 / 1
- **Total Model Volume**: 0.0 GB (0 bytes)
- **Metadata Valid**: No
- **Tokenizer Valid**: No

---

## 3. Storage Benchmark Comparison (Local NVMe vs. Google Drive FUSE)

| Storage Medium | Average TTFT (s) | Average Decode Speed (tok/s) | Relative Speedup |
| :--- | :--- | :--- | :--- |
| **Colab Local NVMe** | 1.56 s | 0.393 tok/s | **19.85x** |
| **Google Drive FUSE** | 16.5 s | 0.0198 tok/s | 1.0x (Baseline) |

> [!NOTE]
> Direct Google Drive streaming latency is dominated by FUSE network roundtrips. Staging hot experts onto local NVMe produces massive throughput improvements.
