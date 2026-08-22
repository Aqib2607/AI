# GLM-5.2 Colibri Google Drive Runtime (`glm52-drive-runtime`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Engine: Colibri](https://img.shields.io/badge/Engine-Colibrì_v1.4.0+-green.svg)](https://github.com/JustVugg/colibri)
[![Model: GLM-5.2-744B](https://img.shields.io/badge/Model-GLM--5.2--744B--MoE-purple.svg)](https://huggingface.co/mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp)

A production-grade, reproducible infrastructure system to store the **744B-parameter GLM-5.2 Mixture-of-Experts (MoE)** model in Google Drive, provision Google Colab compute runtimes, execute dynamic disk-streamed inference using the pure-C **Colibrì** engine, benchmark Google Drive FUSE versus local NVMe storage, and expose OpenAI-compatible REST APIs.

---

## 🌟 Architectural Overview

```
+-------------------------------------------------------------------------------+
|                             System Architecture                               |
|                                                                               |
|  [Hugging Face Hub]                                                           |
|        │                                                                      |
|        ▼ (Resumable Atomic Downloader)                                        |
|  [Google Drive Storage: ~380 GB Golden Model Store]                           |
|        │                                                                      |
|        ▼ (FUSE Mount / Fast NVMe Staging / Dual-Drive Mirror)                 |
|  [Google Colab Runtime]                                                       |
|        ├── System RAM: 9.9 GB Dense Weights (Attention / Shared Experts)       |
|        ├── NVMe Local Disk: Dynamic Expert Streaming via pread() / O_DIRECT   |
|        └── Colibrì Engine (Pure C, OpenMP Parallelized, INT8 MTP Speculation)  |
|                    │                                                          |
|                    ▼                                                          |
|  [OpenAI-Compatible REST API Gateway] (/v1/models, /v1/chat/completions)     |
|                    │                                                          |
|                    ▼                                                          |
|  [Client Applications / Web Dashboard / Python SDK]                           |
+-------------------------------------------------------------------------------+
```

---

## 🚀 Key Features

1. **Persistent Cloud Storage**: Stores the full 380 GB model in Google Drive, ensuring zero re-downloads across ephemeral Colab session disconnects.
2. **AI Memory Multitiering**: Retains dense layers (~9.9 GB) in RAM while streaming 19,456 routed experts from disk on demand.
3. **Resumable Downloader**: Chunk-level resume with atomic `.tmp` to `.safetensors` finalization and SHA-256 integrity verification.
4. **Empirical Storage Benchmark**: Quantifies performance differences between direct Google Drive FUSE streaming and local NVMe staging.
5. **OpenAI-Compatible API**: High-throughput REST API supporting JSON completions, Server-Sent Events (SSE) streaming, and Bearer token authentication.
6. **Zero Model in Git**: Strict repository security policies preventing any weight or credential leaks into version control.

---

## 📂 Repository Structure

```
glm52-drive-runtime/
├── README.md                      # Primary project documentation
├── LICENSE                        # MIT License
├── .gitignore                     # Git ignore rules (weights, credentials, logs)
├── .env.example                   # Environment configuration template
├── requirements.txt               # Python package dependencies
├── config/
│   ├── model.example.yaml         # Model architecture & sharding specification
│   └── runtime.example.yaml       # Colibri runtime & tiering configuration
├── docs/                          # In-depth technical guides
│   ├── discovery.md               # Upstream research & engine discovery
│   ├── model-selection.md         # Model comparison & gs64 rationale
│   ├── storage-feasibility.md     # Google Drive vs NVMe I/O analysis
│   ├── architecture.md            # End-to-end data flow & tiering architecture
│   ├── setup.md                   # Local workstation setup instructions
│   ├── google-drive.md            # Drive structure & quota management
│   ├── colab.md                   # Colab provisioning & runtime configuration
│   ├── model.md                   # Model file hierarchy & integrity validation
│   ├── colibri.md                 # Colibri pure-C build & optimization guide
│   ├── runtime.md                 # Inference execution & prompt evaluation
│   ├── api.md                     # OpenAI-compatible API reference
│   ├── benchmark.md               # Storage benchmarking methodology & results
│   ├── troubleshooting.md         # Error catalog & diagnostic recovery
│   ├── security.md                # Credential management & network isolation
│   ├── limitations.md             # Hardware, bandwidth, & rate limit boundaries
│   └── video-workflow.md          # Reference video reproduction & improvements
├── colab/                         # Sequential executable Colab notebooks
│   ├── 01_environment_check.ipynb # Hardware, compiler, and RAM detection
│   ├── 02_drive_mount.ipynb       # Google Drive authentication & path creation
│   ├── 03_model_storage.ipynb     # Resumable model download to Google Drive
│   ├── 04_model_verification.ipynb# Non-destructive shard integrity validation
│   ├── 05_colibri_setup.ipynb     # Pure-C engine build with OpenMP flags
│   ├── 06_inference.ipynb         # Interactive & deterministic prompt execution
│   ├── 07_benchmark.ipynb         # Drive FUSE vs Local NVMe comparative benchmark
│   └── 08_api.ipynb               # API gateway launch & SSE client testing
├── scripts/                       # Reusable Python automation CLI tools
│   ├── environment_check.py       # Hardware and environment validator
│   ├── drive_check.py             # Google Drive mount and storage health check
│   ├── model_inventory.py         # Shard discovery and inventory report
│   ├── model_verify.py            # Non-destructive Safetensors header validation
│   ├── download_model.py          # Resumable Hugging Face shard downloader
│   ├── benchmark.py               # Latency, TTFT, and I/O benchmark runner
│   ├── health_check.py            # Runtime health and ready-state probe
│   ├── runtime_launcher.py        # End-to-end validated startup runner
│   └── generate_report.py         # Markdown and JSON summary report generator
├── api/                           # OpenAI-compatible API gateway
│   ├── README.md                  # API usage & endpoint specifications
│   ├── requirements.txt           # FastAPI & Uvicorn dependencies
│   └── app.py                     # FastAPI REST server & SSE streaming
└── tests/                         # Automated unit & integration tests
    ├── test_configuration.py      # Configuration schema and environment parsing
    ├── test_model_inventory.py    # Shard parsing and mock manifest discovery
    ├── test_model_validation.py   # Header validation and error states
    ├── test_runtime_configuration.py # Engine flags and OpenMP argument builders
    └── test_api.py                # REST endpoints and SSE stream contracts
```

---

## ⚡ Quickstart Guide

### 1. Local Development Setup
```bash
# Clone the repository
git clone https://github.com/your-username/glm52-drive-runtime.git
cd glm52-drive-runtime

# Configure environment variables
cp .env.example .env

# Install Python dependencies and run unit tests
pip install -r requirements.txt
pytest tests/ -v
```

### 2. Google Colab Execution Workflow
Open the notebooks in `colab/` in numerical order:
1. `colab/01_environment_check.ipynb` — Verifies system RAM, disk, and CPU flags.
2. `colab/02_drive_mount.ipynb` — Mounts Google Drive (`My Drive/AI/GLM-5.2/`).
3. `colab/03_model_storage.ipynb` — Downloads the verified GLM-5.2 model shards.
4. `colab/04_model_verification.ipynb` — Validates all 38 Safetensors headers.
5. `colab/05_colibri_setup.ipynb` — Compiles the pure-C Colibrì engine.
6. `colab/06_inference.ipynb` — Runs test prompts and evaluates generation latency.
7. `colab/07_benchmark.ipynb` — Compares Drive FUSE vs Local NVMe performance.
8. `colab/08_api.ipynb` — Exposes the OpenAI-compatible REST server.

---

## 🔒 Security & Provenance Policy

- **No Secrets in Git**: `.env` and all credential tokens are strictly ignored.
- **No Weights in Git**: Binary weights (`.safetensors`, `.gguf`, `.bin`) are explicitly excluded.
- **Localhost Default Binding**: All server endpoints bind to `127.0.0.1` by default.

---

## 📜 License

This project is licensed under the [MIT License](LICENSE).
