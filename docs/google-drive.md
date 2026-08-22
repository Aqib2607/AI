# Google Drive Persistent Storage Integration Specification

**Status**: `[VERIFIED]` Technical Specification & API v3 Integration  
**Target Account**: `aqibjawwad2607@gmail.com`  
**Target Folder**: `AI - Google Drive` (Folder ID: `11BdZx7pI2XyEmiJjpZJjTCIX1V41vKhd`)  
**Target URL**: [https://drive.google.com/drive/u/0/folders/11BdZx7pI2XyEmiJjpZJjTCIX1V41vKhd](https://drive.google.com/drive/u/0/folders/11BdZx7pI2XyEmiJjpZJjTCIX1V41vKhd)  
**Root Path Post-Mount**: `/content/drive/MyDrive/AI - Google Drive`  
**Authoritative Quota Metric**: Google Drive API v3 (`drive.about.get`)  
**Diagnostic Metric**: Linux FUSE Container Mount (`shutil.disk_usage`)

---

## 1. Authoritative Quota Discovery vs. FUSE Diagnostics

### Why FUSE `shutil.disk_usage()` is Diagnostic Only
When Google Drive is mounted in Google Colab via `drive.mount('/content/drive')`, Linux exposes it as an ephemeral userspace FUSE mount. Calling `shutil.disk_usage('/content/drive')` queries the virtual container's local overlay capacity (~107.72 GB total, ~83.25 GB free), **NOT** the user's actual Google Drive account quota.

### Authoritative Google Drive API v3 Protocol
The preflight probe ([`scripts/drive_check.py`](file:///d:/AI/glm52-drive-runtime/scripts/drive_check.py)) queries the authoritative account storage quota dynamically at runtime via:
```python
drive_service.about().get(fields="storageQuota,user").execute()
```
- `storageQuota.limit`: Total account plan limit (e.g. 5,000,000,000,000 bytes for 5 TB plan).
- `storageQuota.usage`: Current storage consumed across Drive, Trash, and Gmail.
- `free_bytes = limit - usage`: Exact available cloud storage (e.g. ~4,836.83 GB available).
- **Unlimited Quota Handling**: If `limit` is null/unmetered, marked as `GO_UNLIMITED_QUOTA`.

---

## 2. Authentication & Security Policy

1. **Authentication Rule**:
   - When Google authentication is required in Google Colab, the user interactively authenticates `aqibjawwad2607@gmail.com` via Colab's standard OAuth flow (`google.colab.auth.authenticate_user()`).
   - **Zero Secret Storage**: Never request, store, or commit OAuth tokens, refresh tokens, or passwords in Git or configuration files.

2. **Folder Access Rule**:
   - Operations strictly query and use the existing folder identified by Folder ID `11BdZx7pI2XyEmiJjpZJjTCIX1V41vKhd`.
   - Never create duplicate top-level folders outside the designated target directory.

3. **Scope & Isolation Rule**:
   - Operations are strictly restricted to `/content/drive/MyDrive/AI - Google Drive/GLM-5.2/`.
   - **Never scan, list, modify, or delete unrelated Google Drive files**.

---

## 3. Dedicated Project Directory Structure

```
/content/drive/MyDrive/AI - Google Drive/
└── GLM-5.2/
    ├── model/               # 142 Safetensors shards (~399.79 GiB) + metadata configs
    ├── runtime/             # Compiled Colibri binary & .coli_usage
    ├── logs/                # Inference execution and health probe logs
    ├── manifests/           # Model manifests and SHA verification records
    └── benchmarks/          # Raw and summarized I/O benchmark outputs
```

---

## 4. Preflight Verification Protocol & Decision Logic

| Threshold / Gate | Free Storage Level | Preflight Decision |
| :--- | :--- | :--- |
| **Minimum Required Safety Threshold** | $< 400.0\text{ GB}$ | **`NO-GO`** (Download Blocked) |
| **Low Margin Range** | $400.0\text{ GB} \le \text{Free} < 450.0\text{ GB}$ | **`GO_WITH_LOW_MARGIN`** |
| **Recommended Threshold** | $450.0\text{ GB} \le \text{Free} < 500.0\text{ GB}$ | **`GO`** |
| **Preferred Safety Margin** | $\ge 500.0\text{ GB}$ | **`GO_WITH_RECOMMENDED_MARGIN`** |
| **Unlimited / Unmetered Plan** | `limit` is null | **`GO_UNLIMITED_QUOTA`** |

*For the user's 5 TB account with ~163.17 GB used (~4,836.83 GB free), the gate evaluates dynamically to **`GO_WITH_RECOMMENDED_MARGIN`**.*

---

## 5. Mounting & Preflight Execution in Google Colab

```bash
# Execute preflight check via absolute repository path
!python /content/glm52-drive-runtime/scripts/drive_check.py \
  --path "/content/drive/MyDrive/AI - Google Drive/GLM-5.2/model" \
  --required-gb 400 \
  --recommended-gb 450 \
  --folder-id "11BdZx7pI2XyEmiJjpZJjTCIX1V41vKhd"
```
