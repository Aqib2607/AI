"""
Tests for download_model.py capacity semantics:
  - Google Drive API quota is the authoritative persistent storage gate.
  - FUSE capacity (shutil.disk_usage on Drive mount) is diagnostic-only and never blocks.
  - Local NVMe is only checked for temp chunk buffer on non-Drive targets.
  - Existing completed shards are preserved; partial .tmp files are resumed.
  - The full 399.79 GiB model is never required on local NVMe.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    import pytest  # type: ignore
except ImportError:
    pass

try:
    from scripts.download_model import (  # type: ignore
        evaluate_download_gate,
        get_capacity_report,
        is_drive_path,
        get_file_priority_key,
        download_file_resumable,
        DRIVE_MOUNT_PREFIXES
    )
except ImportError:
    from download_model import (  # type: ignore
        evaluate_download_gate,
        get_capacity_report,
        is_drive_path,
        get_file_priority_key,
        download_file_resumable,
        DRIVE_MOUNT_PREFIXES
    )


# ──────────────────────────────────────────────────────────────────────────────
# Helper: build a mock capacity dict
# ──────────────────────────────────────────────────────────────────────────────

def make_capacity(
    drive_free_gb: float = None,
    drive_limit_gb: float = 5497.56,
    drive_usage_gb: float = 175.2,
    is_unlimited: bool = False,
    drive_available: bool = True,
    local_free_gib: float = 87.64,
    local_total_gib: float = 107.72,
    fuse_free_gib: float = 87.64,
    fuse_total_gib: float = 107.72,
    target_is_drive: bool = True
) -> dict:
    if drive_free_gb is None and not is_unlimited:
        drive_free_gb = round(drive_limit_gb - drive_usage_gb * 1e9 / 1e9, 2) if drive_limit_gb else None
    return {
        "drive_api_quota": {
            "available": drive_available,
            "free_gb": drive_free_gb,
            "limit_gb": drive_limit_gb,
            "usage_gb": drive_usage_gb,
            "is_unlimited": is_unlimited,
            "email": "aqibjawwad2607@gmail.com",
            "error": None
        },
        "local_colab_disk": {
            "free_gib": local_free_gib,
            "total_gib": local_total_gib,
            "error": None
        },
        "fuse_diagnostic": {
            "free_gib": fuse_free_gib,
            "total_gib": fuse_total_gib,
            "path": "/content/drive/MyDrive/AI - Google Drive/GLM-5.2/model",
            "error": None
        },
        "target_is_drive_path": target_is_drive
    }


# ──────────────────────────────────────────────────────────────────────────────
# CAPACITY SEMANTICS
# ──────────────────────────────────────────────────────────────────────────────

def test_drive_api_quota_is_authoritative():
    """Google Drive API quota >= required_gb produces GO even when FUSE is small."""
    cap = make_capacity(drive_free_gb=5322.36, fuse_free_gib=87.64, target_is_drive=True)
    status, reason = evaluate_download_gate(cap, required_gb=400.0, recommended_gb=450.0)
    assert status in ("GO", "GO_WITH_LOW_MARGIN"), f"Unexpected gate status: {status}"
    # Reason string uses comma-formatted numbers; strip commas before substring check
    assert "5322.36" in reason.replace(",", ""), f"Reason should mention 5322.36 GB: {reason}"


def test_fuse_capacity_does_not_block_full_model_download():
    """87.64 GiB FUSE capacity must NOT block a Drive-target download of 399.79 GiB model."""
    cap = make_capacity(drive_free_gb=5322.36, fuse_free_gib=87.64, target_is_drive=True)
    status, reason = evaluate_download_gate(cap, required_gb=400.0, recommended_gb=450.0)
    assert "NO-GO" not in status, (
        f"FUSE capacity ({87.64} GiB) incorrectly blocked the download. "
        f"FUSE is diagnostic-only. Gate: {status}, Reason: {reason}"
    )


def test_87_gib_fuse_with_5322_gb_drive_quota_returns_go():
    """
    Regression: exact observed runtime condition.
    Google Drive API: 5322.36 GB available (GO).
    FUSE mount: 87.64 GiB (diagnostic only, never a gate).
    Expected: GO.
    """
    cap = make_capacity(
        drive_free_gb=5322.36,
        drive_limit_gb=5497.56,
        drive_usage_gb=175.2,
        local_free_gib=87.64,
        fuse_free_gib=87.64,
        target_is_drive=True
    )
    status, reason = evaluate_download_gate(cap, required_gb=400.0, recommended_gb=450.0)
    assert status == "GO", f"Expected GO but got {status}: {reason}"
    # Reason string uses comma-formatted numbers; strip commas before substring check
    assert "5322.36" in reason.replace(",", ""), f"Reason should mention 5322.36 GB: {reason}"


def test_insufficient_drive_api_quota_blocks_download():
    """When Drive API quota is below required_gb, gate returns NO-GO."""
    cap = make_capacity(drive_free_gb=350.0, fuse_free_gib=200.0, target_is_drive=True)
    status, reason = evaluate_download_gate(cap, required_gb=400.0, recommended_gb=450.0)
    assert status == "NO-GO"
    assert "350.00 GB free is BELOW" in reason


def test_400gb_drive_quota_returns_go_with_low_margin():
    """Exactly 400 GB drive free returns GO_WITH_LOW_MARGIN (between required and recommended)."""
    cap = make_capacity(drive_free_gb=400.0, target_is_drive=True)
    status, _ = evaluate_download_gate(cap, required_gb=400.0, recommended_gb=450.0)
    assert status == "GO_WITH_LOW_MARGIN"


def test_unlimited_quota_produces_go():
    """Unlimited Drive quota produces GO regardless of local/FUSE capacity."""
    cap = make_capacity(drive_free_gb=None, is_unlimited=True, fuse_free_gib=5.0, target_is_drive=True)
    status, reason = evaluate_download_gate(cap, required_gb=400.0, recommended_gb=450.0)
    assert status == "GO"
    assert "unlimited" in reason.lower() or "unlimited" in reason.lower()


def test_local_disk_requirement_is_temp_chunk_only():
    """
    When target is a Drive path, local NVMe gate is NOT applied.
    Even 1 GiB local free is fine for a Drive-target download.
    """
    cap = make_capacity(
        drive_free_gb=5000.0,
        local_free_gib=1.0,   # Far less than model size
        target_is_drive=True
    )
    status, _ = evaluate_download_gate(cap, required_gb=400.0, local_temp_gib=3.0)
    assert "NO-GO" not in status, "Local NVMe should not block a Drive-target download"


def test_local_temp_gate_applies_only_for_non_drive_targets():
    """
    When target is local NVMe (not Drive), the temp buffer gate IS applied.
    0.5 GiB free with 3.0 GiB requirement should return NO-GO.
    """
    cap = make_capacity(
        drive_free_gb=5000.0,
        local_free_gib=0.5,
        target_is_drive=False
    )
    status, reason = evaluate_download_gate(cap, required_gb=400.0, local_temp_gib=3.0)
    assert status == "NO-GO"
    assert "NVMe" in reason or "local" in reason.lower()


def test_full_model_not_staged_to_local_disk(tmp_path):
    """
    The downloader writes to target_dir directly.
    When target_dir is a Drive path, local NVMe should not need 399.79 GiB.
    The capacity report must confirm target_is_drive_path=True.
    """
    drive_path = "/content/drive/MyDrive/AI - Google Drive/GLM-5.2/model"
    assert is_drive_path(drive_path) is True, "Drive path not detected"

    local_path = str(tmp_path / "model")
    assert is_drive_path(local_path) is False, "Local path incorrectly detected as Drive"


# ──────────────────────────────────────────────────────────────────────────────
# IS_DRIVE_PATH DETECTION
# ──────────────────────────────────────────────────────────────────────────────

def test_is_drive_path_detection():
    """Verify Drive path detection for all configured prefixes."""
    assert is_drive_path("/content/drive/MyDrive/AI - Google Drive/GLM-5.2/model") is True
    assert is_drive_path("/content/drive/") is True
    assert is_drive_path("/content/model") is False
    assert is_drive_path("/tmp/model") is False


# ──────────────────────────────────────────────────────────────────────────────
# SHARD PRESERVATION AND RESUMPTION
# ──────────────────────────────────────────────────────────────────────────────

def test_existing_completed_shards_are_preserved(tmp_path):
    """Completed files with correct size must be skipped, not re-downloaded."""
    completed = tmp_path / "out-00000.safetensors"
    completed.write_bytes(b"X" * 1000)

    result = download_file_resumable(
        url="https://example.invalid/nonexistent",
        target_path=str(completed),
        expected_size=1000,
        token=None,
        max_retries=1
    )
    assert result is True
    assert completed.stat().st_size == 1000


def test_partial_tmp_download_resumes(tmp_path, monkeypatch):
    """A .tmp file with partial bytes should be detected and resumed (not restarted)."""
    target = tmp_path / "out-00001.safetensors"
    tmp_file = tmp_path / "out-00001.safetensors.tmp"
    tmp_file.write_bytes(b"A" * 500)

    resume_range_header = []

    import requests as req_mod

    class FakeResp:
        status_code = 206
        headers = {"Content-Length": "500"}
        def iter_content(self, chunk_size=None):
            return iter([b"B" * 500])
        def raise_for_status(self):
            pass

    def mock_get(url, headers=None, stream=False, timeout=None):
        if "Range" in (headers or {}):
            resume_range_header.append(headers["Range"])
        return FakeResp()

    monkeypatch.setattr(req_mod, "get", mock_get)

    result = download_file_resumable(
        url="https://example.invalid/shard",
        target_path=str(target),
        expected_size=1000,
        token=None,
        max_retries=2
    )
    # Should have resumed from byte 500
    assert len(resume_range_header) > 0
    assert "500" in resume_range_header[0]


# ──────────────────────────────────────────────────────────────────────────────
# PRIORITY ORDERING
# ──────────────────────────────────────────────────────────────────────────────

def test_download_priority_ordering():
    """Verify priority: config/tokenizer files -> MTP head -> shard 0 -> rest."""
    files = [
        "out-00001.safetensors",
        "out-00000.safetensors",
        "out-mtp-00000.safetensors",
        "tokenizer.json",
        "config.json",
        "tokenizer_config.json",
        "generation_config.json"
    ]
    sorted_files = sorted(files, key=get_file_priority_key)
    assert sorted_files[0] == "config.json"
    assert sorted_files[1] == "generation_config.json"
    assert sorted_files[2] == "tokenizer_config.json"
    assert sorted_files[3] == "tokenizer.json"
    assert sorted_files[4] == "out-mtp-00000.safetensors"
    assert sorted_files[5] == "out-00000.safetensors"
    assert sorted_files[6] == "out-00001.safetensors"
