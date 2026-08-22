# Google Drive Storage & Integration Guide

---

## 1. Directory Structure in Google Drive

Persistent model artifacts, manifests, runtime configurations, and benchmark logs are stored in Google Drive under `My Drive/AI/GLM-5.2/`:

```
My Drive/
└── AI/
    └── GLM-5.2/
        ├── model/                   # 380 GB model weights & tokenizer
        │   ├── config.json
        │   ├── tokenizer.json
        │   ├── tokenizer_config.json
        │   ├── special_tokens_map.json
        │   ├── model.safetensors.index.json
        │   └── model-00001-of-00038.safetensors ... model-00038-of-00038.safetensors
        ├── manifests/               # SHA-256 integrity checksums & download receipts
        │   └── download_manifest.json
        ├── runtime/                 # Optional persistent compiled binary & state
        │   └── .coli_usage          # Learned routing history for expert pinning
        ├── logs/                    # Colibri execution & API server logs
        └── benchmarks/              # Empirical raw performance test results (JSON/CSV)
```

---

## 2. Mounting Google Drive in Colab

In Google Colab, mount Google Drive using the official Colab integration:

```python
from google.colab import drive
import os

# Mount Google Drive
drive.mount('/content/drive', force_remount=False)

# Define project base directory
PROJECT_DIR = '/content/drive/MyDrive/AI/GLM-5.2'
MODEL_DIR = os.path.join(PROJECT_DIR, 'model')
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(os.path.join(PROJECT_DIR, 'manifests'), exist_ok=True)
os.makedirs(os.path.join(PROJECT_DIR, 'logs'), exist_ok=True)
os.makedirs(os.path.join(PROJECT_DIR, 'benchmarks'), exist_ok=True)

print(f"Mounted Google Drive at /content/drive. Base directory: {PROJECT_DIR}")
```

---

## 3. Storage Health & Quota Verification

Before initiating model downloads, verify available Drive quota using `scripts/drive_check.py`:

```python
import shutil

total, used, free = shutil.disk_usage('/content/drive/MyDrive')
print(f"Total: {total / (1024**3):.2f} GB | Used: {used / (1024**3):.2f} GB | Free: {free / (1024**3):.2f} GB")

if free / (1024**3) < 380:
    raise RuntimeError(f"Insufficient Google Drive space! Free: {free/(1024**3):.2f} GB, Required: >= 380 GB.")
```
