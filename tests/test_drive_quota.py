"""
Unit and integration tests for Google Drive API v3 quota retrieval,
folder validation, FUSE diagnostic isolation, and storage gate decision logic.
"""

import os
import sys
# Ensure scripts and root directories are on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    import pytest  # type: ignore
except ImportError:
    pass

try:
    from scripts.drive_check import (  # type: ignore
        get_drive_storage_quota,
        validate_target_folder,
        get_fuse_usage,
        evaluate_storage_gate,
        check_drive_storage,
        EXPECTED_ACCOUNT,
        TARGET_FOLDER_ID,
        TARGET_FOLDER_NAME
    )
except ImportError:
    from drive_check import (  # type: ignore
        get_drive_storage_quota,
        validate_target_folder,
        get_fuse_usage,
        evaluate_storage_gate,
        check_drive_storage,
        EXPECTED_ACCOUNT,
        TARGET_FOLDER_ID,
        TARGET_FOLDER_NAME
    )


def test_drive_quota_calculation_5tb_user_plan():
    """
    Test user's reported 5 TB plan (5,000,000,000,000 bytes) with 163.17 GB used.
    Should calculate ~4836.83 GB available free space.
    """
    mock_about = {
        "user": {"emailAddress": "aqibjawwad2607@gmail.com"},
        "storageQuota": {
            "limit": "5000000000000",
            "usage": "163170000000",
            "usageInDrive": "160000000000",
            "usageInDriveTrash": "3170000000"
        }
    }
    quota = get_drive_storage_quota(mock_response=mock_about)
    assert quota["success"] is True
    assert quota["email"] == "aqibjawwad2607@gmail.com"
    assert quota["limit_gb"] == 5000.0
    assert quota["usage_gb"] == 163.17
    assert quota["free_gb"] == 4836.83
    assert quota["is_unlimited"] is False

    gate_status, reason = evaluate_storage_gate(quota["free_gb"], required_gb=400.0, recommended_gb=450.0)
    assert gate_status == "GO_WITH_RECOMMENDED_MARGIN"


def test_drive_quota_sufficient():
    """Test 450 GB quota with 0 used -> exactly 450 GB free (satisfies recommended threshold)."""
    mock_about = {
        "user": {"emailAddress": "aqibjawwad2607@gmail.com"},
        "storageQuota": {
            "limit": "450000000000",
            "usage": "0"
        }
    }
    quota = get_drive_storage_quota(mock_response=mock_about)
    assert quota["free_gb"] == 450.0
    gate_status, _ = evaluate_storage_gate(quota["free_gb"], required_gb=400.0, recommended_gb=450.0)
    assert gate_status == "GO"


def test_drive_quota_low_margin():
    """Test 400 GB free -> satisfies required 400 GB with low margin."""
    gate_status, _ = evaluate_storage_gate(400.0, required_gb=400.0, recommended_gb=450.0)
    assert gate_status == "GO_WITH_LOW_MARGIN"


def test_drive_quota_insufficient():
    """Test 399 GB free (< 400 GB required) -> NO-GO."""
    gate_status, reason = evaluate_storage_gate(399.0, required_gb=400.0, recommended_gb=450.0)
    assert gate_status == "NO-GO"
    assert "399.00 GB free is below the required 400.00 GB" in reason


def test_drive_quota_recommended_margin():
    """Test 500 GB free -> GO_WITH_RECOMMENDED_MARGIN."""
    gate_status, _ = evaluate_storage_gate(500.0, required_gb=400.0, recommended_gb=450.0)
    assert gate_status == "GO_WITH_RECOMMENDED_MARGIN"


def test_unlimited_drive_quota_handling():
    """Test unmetered or unlimited quota (storageQuota.limit is null/missing)."""
    mock_about = {
        "user": {"emailAddress": "aqibjawwad2607@gmail.com"},
        "storageQuota": {
            "usage": "1000000000"
        }
    }
    quota = get_drive_storage_quota(mock_response=mock_about)
    assert quota["success"] is True
    assert quota["is_unlimited"] is True
    assert quota["limit_bytes"] is None

    gate_status, _ = evaluate_storage_gate(quota["free_gb"], is_unlimited=True)
    assert gate_status == "GO_UNLIMITED_QUOTA"


def test_fuse_usage_is_diagnostic_only(tmp_path):
    """
    Test that virtual FUSE capacity (e.g. 107.72 GB total, 83.25 GB free)
    is recorded as diagnostic information and does NOT cause a storage gate failure
    when the authoritative Google Drive API reports 4836.83 GB free.
    """
    mock_about = {
        "user": {"emailAddress": "aqibjawwad2607@gmail.com"},
        "storageQuota": {
            "limit": "5000000000000",
            "usage": "163170000000"
        }
    }
    mock_folder = {
        "id": TARGET_FOLDER_ID,
        "name": TARGET_FOLDER_NAME,
        "mimeType": "application/vnd.google-apps.folder",
        "trashed": False
    }

    report = check_drive_storage(
        path=str(tmp_path / "GLM-5.2" / "model"),
        required_gb=400.0,
        recommended_gb=450.0,
        mock_about=mock_about,
        mock_folder=mock_folder
    )

    # Assert Drive API is authoritative
    assert report["drive_account_quota_limit_gb"] == 5000.0
    assert report["drive_account_free_gb"] == 4836.83
    assert report["storage_gate_status"] == "GO_WITH_RECOMMENDED_MARGIN"
    assert report["status"] == "HEALTHY"

    # Assert FUSE diagnostics are captured separately
    assert "fuse_total_gb" in report
    assert "fuse_free_gb" in report
    assert "diagnostic" in report["fuse_diagnostic_note"].lower()


def test_target_folder_validation():
    """Test successful folder validation with expected ID, name, and folder mimeType."""
    mock_folder = {
        "id": TARGET_FOLDER_ID,
        "name": TARGET_FOLDER_NAME,
        "mimeType": "application/vnd.google-apps.folder",
        "trashed": False
    }
    res = validate_target_folder(mock_response=mock_folder)
    assert res["valid"] is True
    assert res["folder_id"] == TARGET_FOLDER_ID
    assert res["folder_name"] == TARGET_FOLDER_NAME
    assert res["is_folder"] is True


def test_wrong_target_folder_rejected():
    """
    Test folder validation with name mismatch vs wrong MIME type.
    - Name mismatch: informational only, does NOT fail validation (folder ID is authoritative).
    - Wrong MIME type: hard failure (the resource is not a folder at all).
    """
    # Name mismatch: valid because folder ID, MIME, and trashed checks all pass
    mock_wrong_name = {
        "id": TARGET_FOLDER_ID,
        "name": "Wrong Folder Name",
        "mimeType": "application/vnd.google-apps.folder",
        "trashed": False
    }
    res_wrong_name = validate_target_folder(mock_response=mock_wrong_name)
    assert res_wrong_name["valid"] is True  # ID+MIME+not-trashed passes
    assert res_wrong_name["name_matches"] is False
    assert res_wrong_name["name_mismatch_note"] is not None
    assert "INFORMATIONAL" in res_wrong_name["name_mismatch_note"]

    # Wrong MIME type: hard failure -- resource is not a Google Drive folder
    mock_not_a_folder = {
        "id": TARGET_FOLDER_ID,
        "name": TARGET_FOLDER_NAME,
        "mimeType": "text/plain",
        "trashed": False
    }
    res_not_folder = validate_target_folder(mock_response=mock_not_a_folder)
    assert res_not_folder["valid"] is False
    assert "MIME type" in res_not_folder["error"]


def test_authenticated_account_identity():
    """Test extracting user email from Drive API response."""
    mock_about = {
        "user": {"emailAddress": "aqibjawwad2607@gmail.com"},
        "storageQuota": {"limit": "5000000000000", "usage": "1000"}
    }
    quota = get_drive_storage_quota(mock_response=mock_about)
    assert quota["email"] == "aqibjawwad2607@gmail.com"
