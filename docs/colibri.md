# Colibrì Inference Engine: Build & Configuration Guide

---

## 1. Engine Overview

**Colibrì** (`JustVugg/colibri`) is an open-source, pure-C inference engine engineered for running massive frontier Mixture-of-Experts (MoE) models on consumer and cloud hardware with zero external dependencies.

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

### Compiler Optimization Flags
- `ARCH=native`: Instructs `gcc` to emit vector instructions (AVX2, AVX-512, FMA) tailored to the host CPU.
- `CUDA=1`: (Optional) Builds CUDA kernel acceleration (`coli_cuda.so`) when an NVIDIA GPU is present.

---

## 3. Runtime Modes

1. **Interactive TUI Chat**:
   ```bash
   ./coli chat --model /content/model
   ```
2. **OpenAI-Compatible REST Server**:
   ```bash
   ./coli serve --model /content/model --host 127.0.0.1 --port 8000
   ```
3. **Web Dashboard**:
   ```bash
   ./coli web --model /content/model --port 8000
   ```
4. **Dual-SSD Mirror Mode**:
   ```bash
   COLI_MODEL=/content/model COLI_MODEL_MIRROR=/content/drive/MyDrive/AI/GLM-5.2/model ./coli serve
   ```
