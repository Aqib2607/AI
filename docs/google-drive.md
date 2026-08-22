# Google Drive Persistent Storage Integration Specification

**Status**: `[VERIFIED]`  
**Target Account**: `aqibjawwad2607@gmail.com`  
**Target Folder**: `AI - Google Drive` (Folder ID: `11BdZx7pI2XyEmiJjpZJjTCIX1V41vKhd`)  
**Target URL**: [https://drive.google.com/drive/u/0/folders/11BdZx7pI2XyEmiJjpZJjTCIX1V41vKhd](https://drive.google.com/drive/u/0/folders/11BdZx7pI2XyEmiJjpZJjTCIX1V41vKhd)  
**Root Path Post-Mount**: `/content/drive/MyDrive/AI - Google Drive`

---

## 1. Authentication & Security Policy

1. **Authentication Rule**:
   - When Google authentication is required in Google Colab (`drive.mount('/content/drive')`), the user must interactively authenticate the account `aqibjawwad2607@gmail.com`.
   - **Zero Password Storage**: Never request, log, or store the user's Google account password or OAuth tokens in Git, scripts, or configuration files.

2. **Folder Access Rule**:
   - Operations must strictly use the existing folder identified by ID `11BdZx7pI2XyEmiJjpZJjTCIX1V41vKhd`.
   - Never create duplicate top-level folders named `AI`, `AI - Google Drive`, or `GLM-5.2` outside this designated target folder.

3. **Scope & Isolation Rule**:
   - The runtime and scripts are strictly restricted to create, read, modify, or delete files inside `/content/drive/MyDrive/AI - Google Drive/GLM-5.2/`.
   - **Never scan, list, modify, or delete unrelated Google Drive content**.

---

## 2. Dedicated Project Directory Structure

```
/content/drive/MyDrive/AI - Google Drive/
└── GLM-5.2/
    ├── model/               # 142 Safetensors shards (~399.79 GiB) + metadata configs
    ├── runtime/             # Compiled Colibri binary (optional backup) & .coli_usage
    ├── logs/                # Inference execution and health probe logs
    ├── manifests/           # Model manifests and SHA verification records
    └── benchmarks/          # Raw and summarized I/O benchmark outputs
```

---

## 3. Ten-Point Verification Protocol

The automated health probe ([`scripts/drive_check.py`](file:///d:/AI/glm52-drive-runtime/scripts/drive_check.py)) systematically validates:

1. `[VERIFIED]` **Account Association**: Confirms Drive mount belongs to `aqibjawwad2607@gmail.com`.
2. `[VERIFIED]` **Target Folder Existence**: Verifies `/content/drive/MyDrive/AI - Google Drive` is mounted.
3. `[VERIFIED]` **Folder ID Correlation**: References Folder ID `11BdZx7pI2XyEmiJjpZJjTCIX1V41vKhd`.
4. `[VERIFIED]` **Write Permissions**: Writes and removes a temporary non-destructive test probe `.drive_probe_test.tmp`.
5. `[VERIFIED]` **Storage Capacity**: Verifies available free storage meets the $\ge 400\text{ GB}$ threshold.
6. `[VERIFIED]` **`GLM-5.2` Root Directory**: Confirms project root exists.
7. `[VERIFIED]` **`model/` Directory**: Confirms model shard storage directory exists.
8. `[VERIFIED]` **`runtime/` Directory**: Confirms runtime cache directory exists.
9. `[VERIFIED]` **`logs/` Directory**: Confirms log output directory exists.
10. `[VERIFIED]` **`manifests/` & `benchmarks/` Directories**: Confirms reporting directories exist.

---

## 4. Mounting Execution in Google Colab

```python
from google.colab import drive  # type: ignore
import os

# 1. Interactive mount for aqibjawwad2607@gmail.com
drive.mount('/content/drive', force_remount=False)

# 2. Define isolated paths
BASE_DIR = '/content/drive/MyDrive/AI - Google Drive/GLM-5.2'
for sub in ['model', 'runtime', 'logs', 'manifests', 'benchmarks']:
    os.makedirs(os.path.join(BASE_DIR, sub), exist_ok=True)

# 3. Run validation probe
!python scripts/drive_check.py --path "/content/drive/MyDrive/AI - Google Drive/GLM-5.2/model" --required-gb 400
```
