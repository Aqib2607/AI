# Google Colab Runtime Environment Guide

---

## 1. Colab Runtime Specifications

To execute the Colibri GLM-5.2 inference pipeline in Google Colab:

| Parameter | Minimum Requirement | Recommended Requirement |
| :--- | :--- | :--- |
| **Runtime Tier** | Standard CPU / High-RAM CPU | High-RAM CPU or GPU (T4 / A100) |
| **System RAM** | 12.7 GB (Colab Standard) | 25.5 GB (Colab High-RAM) |
| **Local Disk Space** | ~50 GB free (for staging hot shards) | ~200+ GB free (for full staging or 150 GB mirror) |
| **Linux OS** | Ubuntu 22.04 LTS / Debian 12 | Ubuntu 22.04 LTS |
| **Compiler** | `gcc` 11+ / `clang` 14+ | `gcc` with OpenMP (`libgomp1`) |

---

## 2. Fresh Session Bootstrapping Workflow

When launching a new Colab runtime session:

```bash
# 1. Clone the repository into Colab workspace
!git clone https://github.com/<your-org>/glm52-drive-runtime.git /content/glm52-drive-runtime
%cd /content/glm52-drive-runtime

# 2. Install required Python packages
!pip install -r requirements.txt

# 3. Mount Google Drive
from google.colab import drive
drive.mount('/content/drive')

# 4. Run environment & storage check
!python scripts/environment_check.py
!python scripts/drive_check.py
```

---

## 3. Persistent State Preservation

Because Colab runtime instances are ephemeral:
- All 38 model shards remain permanently in `/content/drive/MyDrive/AI/GLM-5.2/model/`.
- Router learning profiles (`.coli_usage`) are persisted to Google Drive after each session.
- Diagnostic benchmark runs output directly to `/content/drive/MyDrive/AI/GLM-5.2/benchmarks/`.
