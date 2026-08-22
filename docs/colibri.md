# Colibrì Inference Engine: Build & Configuration Guide

**Status**: `[VERIFIED]`

---

## 1. Engine Overview

`[VERIFIED]` **Colibrì** (`JustVugg/colibri`) is an open-source, pure-C inference engine engineered for running massive frontier Mixture-of-Experts (MoE) models on consumer and cloud hardware with zero external runtime dependencies.

- `[VERIFIED]` **Security Floor**: Requires Colibrì v1.5.0+ for safe Safetensors loader parsing and grouped INT4 ($gs=64$) support.

---

## 2. Compilation from Source

In the Linux/Colab environment:

```bash
# 1. Clone Colibri source
git clone https://github.com/JustVugg/colibri.git /content/colibri
cd /content/colibri

# 2. Build optimized GLM-5.2 engine
make glm ARCH=native

# 3. Verify build output
./coli doctor
```

### Verified Flags & Optimization Parameters
- `[VERIFIED]` `ARCH=native`: Instructs `gcc` to emit vector instructions (AVX2, AVX-512, FMA) tailored to host CPU.
- `[VERIFIED]` `CUDA=1`: (Optional) Builds CUDA kernel acceleration (`coli_cuda.so`) when an NVIDIA GPU is present.

---

## 3. Verified Environment Variables & Runtime Modes

| Variable | Type | Purpose | Verified Status |
| :--- | :--- | :--- | :--- |
| `COLI_MODEL` | Path | Target model directory containing Safetensors shards | `[VERIFIED]` |
| `COLI_MODEL_MIRROR` | Path | Secondary mirror directory for dual-SSD expert streaming | `[VERIFIED]` |
| `COLI_DISK_WEIGHTS`| Ratio | Bandwidth allocation ratio (e.g. `9,1` or `9,3`) | `[VERIFIED]` |
| `COLI_RAM` | Int | Total RAM budget (GB) for caching experts and dense weights | `[VERIFIED]` |
| `COLI_CAP` | Int | Expert capacity limit per layer | `[VERIFIED]` |
| `COLI_REPIN` | Bool | Learned expert re-pinning (`.coli_usage`) | `[VERIFIED]` |
| `COLI_HOST` | String | Server binding host (`127.0.0.1`) | `[VERIFIED]` |
| `COLI_PORT` | Int | Server port (`8000`) | `[VERIFIED]` |
| `COLI_API_KEY` | String | Bearer authentication secret token | `[VERIFIED]` |
