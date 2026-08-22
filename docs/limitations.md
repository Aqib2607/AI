# System Limitations & Boundary Constraints

---

## 1. Storage & Bandwidth Boundaries

| Boundary | Impact | Operational Strategy |
| :--- | :--- | :--- |
| **Google Drive FUSE Latency** | Direct Drive streaming exhibits high latency (~50–300 ms/read). | Use local NVMe staging or Colibri dual-SSD mirror staging for interactive inference. |
| **Google Drive API Quotas** | Rapid burst reads can trigger rate limits. | Downloader uses backoff retries; runtime reads cached headers locally. |
| **Colab Ephemeral Storage** | Free tier local storage (~100 GB) cannot hold full 380 GB uncompressed model. | Use 150 GB partial mirror mode (`COLI_MODEL_MIRROR`) or Colab Pro High-Disk runtime. |

---

## 2. Compute & Token Generation Velocity

- **CPU Decode Speeds**: Disk-streamed 744B MoE inference on CPU generally ranges between **0.05 to 0.50 tokens/second** depending on CPU vector support (AVX-512/AVX2) and NVMe I/O throughput.
- **Hardware Profile**: Colibrì is designed for memory accessibility (running frontier models on affordable tiers), not for low-latency production serving clusters.

---

## 3. Supported Model Families

Colibrì is specifically optimized for sparse Mixture-of-Experts architectures (GLM-5.2, Inkling, Kimi K3, DeepSeek V4 Flash, OLMoE). Standard dense Hugging Face models should not be loaded through the Colibri engine.
