# Troubleshooting & Diagnostic Runbook

---

## 1. Error Categories & Recovery Actions

### A. Environment & Hardware Errors
* **Error**: `Insufficient RAM for resident dense core`
  * **Cause**: Environment has less than 9.9 GB of free RAM.
  * **Remedy**: Switch Colab runtime to **High-RAM** instance or close memory-heavy background processes.
* **Error**: `OpenMP library not found / make failed`
  * **Cause**: Missing `libgomp1` or build-essential packages.
  * **Remedy**: Run `apt-get update && apt-get install -y build-essential libgomp1`.

### B. Google Drive & Storage Errors
* **Error**: `Google Drive Transport endpoint is not connected`
  * **Cause**: Colab Drive FUSE mount dropped due to session timeout or network blip.
  * **Remedy**: Unmount and remount:
    ```python
    from google.colab import drive
    drive.flush_and_unmount()
    drive.mount('/content/drive', force_remount=True)
    ```
* **Error**: `Insufficient Google Drive storage (Free < 380 GB)`
  * **Cause**: Target Google Drive account does not have sufficient quota for 38 shards.
  * **Remedy**: Upgrade to Google One 2 TB plan or clear unused files.

### C. Model & Downloader Errors
* **Error**: `Shard checksum mismatch / Header corrupted`
  * **Cause**: Incomplete or interrupted download.
  * **Remedy**: Run `python scripts/download_model.py --verify-only` followed by `python scripts/download_model.py --resume` to re-fetch corrupted shards atomically.

### D. Colibri Runtime Errors
* **Error**: `Repetition loop / Runaway token emission`
  * **Cause**: Using legacy per-row INT4 model rather than grouped INT4 ($gs=64$).
  * **Remedy**: Ensure `MODEL_REPO` is set to `mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp` in `.env`.
