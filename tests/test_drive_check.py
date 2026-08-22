"""
Unit tests for drive_check.py CLI arguments, Google Drive API v3 quota evaluation,
FUSE diagnostic metric isolation, folder metadata validation, and fallback discovery.
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
    from scripts.drive_check import (  # type: ignore
        build_parser,
        get_drive_storage_quota,
        validate_target_folder,
        get_fuse_usage,
        evaluate_storage_gate,
        check_drive_storage,
        TARGET_FOLDER_ID,
        TARGET_FOLDER_NAME,
        EXPECTED_ACCOUNT
    )
except ImportError:
    from drive_check import (  # type: ignore
        build_parser,
        get_drive_storage_quota,
        validate_target_folder,
        get_fuse_usage,
        evaluate_storage_gate,
        check_drive_storage,
        TARGET_FOLDER_ID,
        TARGET_FOLDER_NAME,
        EXPECTED_ACCOUNT
    )


def test_argparse_accepts_recommended_gb_and_folder_id():
    """Verify argparse accepts --recommended-gb and --folder-id without error."""
    parser = build_parser()
    args = parser.parse_args([
        "--path", "/content/drive/MyDrive/AI - Google Drive/GLM-5.2/model",
        "--required-gb", "400",
        "--recommended-gb", "450",
        "--folder-id", "11BdZx7pI2XyEmiJjpZJjTCIX1V41vKhd",
        "--json"
    ])
    assert args.path == "/content/drive/MyDrive/AI - Google Drive/GLM-5.2/model"
    assert args.required_gb == 400.0
    assert args.recommended_gb == 450.0
    assert args.folder_id == "11BdZx7pI2XyEmiJjpZJjTCIX1V41vKhd"
    assert args.json is True


def test_argparse_defaults():
    """Verify default values when arguments are omitted."""
    parser = build_parser()
    args = parser.parse_args([])
    assert args.required_gb == 400.0
    assert args.recommended_gb == 450.0
    assert args.folder_id == TARGET_FOLDER_ID
    assert args.json is False


def test_drive_quota_5tb_plan():
    """Verify 5 TB quota with 163.17 GB usage calculates ~4836.83 GB free."""
    mock_about = {
        "user": {"emailAddress": EXPECTED_ACCOUNT},
        "storageQuota": {
            "limit": "5000000000000",
            "usage": "163170000000"
        }
    }
    quota = get_drive_storage_quota(mock_response=mock_about)
    assert quota["success"] is True
    assert quota["limit_gb"] == 5000.0
    assert quota["usage_gb"] == 163.17
    assert quota["free_gb"] == 4836.83
    assert quota["is_unlimited"] is False

    status, reason = evaluate_storage_gate(quota["free_gb"], required_gb=400.0, recommended_gb=450.0)
    assert status == "GO_WITH_RECOMMENDED_MARGIN"


def test_drive_quota_450gb_available():
    """Verify 450 GB free returns GO."""
    status, _ = evaluate_storage_gate(450.0, required_gb=400.0, recommended_gb=450.0)
    assert status == "GO"


def test_drive_quota_400gb_available():
    """Verify 400 GB free returns GO_WITH_LOW_MARGIN."""
    status, _ = evaluate_storage_gate(400.0, required_gb=400.0, recommended_gb=450.0)
    assert status == "GO_WITH_LOW_MARGIN"


def test_drive_quota_399gb_insufficient():
    """Verify 399 GB free (< 400 GB) returns NO-GO."""
    status, reason = evaluate_storage_gate(399.0, required_gb=400.0, recommended_gb=450.0)
    assert status == "NO-GO"
    assert "399.00 GB free is below the required 400.00 GB" in reason


def test_fuse_diagnostic_metric_isolation(tmp_path):
    """
    Verify FUSE reporting ~107.72 GB total / 83.25 GB free is isolated
    and does not fail the gate when Google Drive API reports 4836.83 GB free.
    """
    mock_about = {
        "user": {"emailAddress": EXPECTED_ACCOUNT},
        "storageQuota": {
            "limit": "5000000000000",
            "usage": "163170000000"
        }
    }
    mock_folder = {
        "id": TARGET_FOLDER_ID,
        "name": TARGET_FOLDER_NAME,
        "mimeType": "application/vnd.google-apps.folder",
        "trashed": False,
        "owners": [{"emailAddress": EXPECTED_ACCOUNT}],
        "parents": ["root"]
    }
    report = check_drive_storage(
        path=str(tmp_path / "model"),
        required_gb=400.0,
        recommended_gb=450.0,
        folder_id=TARGET_FOLDER_ID,
        mock_about=mock_about,
        mock_folder=mock_folder
    )
    assert report["drive_account_free_gb"] == 4836.83
    assert report["storage_gate_status"] == "GO_WITH_RECOMMENDED_MARGIN"
    assert report["status"] in ("GO", "HEALTHY", "GO_WITH_FILESYSTEM_ACCESS")
    assert "diagnostic" in report["fuse_diagnostic_note"].lower()


def test_target_folder_valid_metadata():
    """Verify folder validation passes for correct ID, name, ownership, and mimeType."""
    mock_folder = {
        "id": TARGET_FOLDER_ID,
        "name": TARGET_FOLDER_NAME,
        "mimeType": "application/vnd.google-apps.folder",
        "trashed": False,
        "owners": [{"emailAddress": EXPECTED_ACCOUNT}],
        "parents": ["root"]
    }
    res = validate_target_folder(mock_response=mock_folder)
    assert res["valid"] is True
    assert res["folder_name"] == TARGET_FOLDER_NAME
    assert res["is_folder"] is True
    assert res["folder_id_match"] == "PASS"
    assert EXPECTED_ACCOUNT in res["owners"]


def test_target_folder_wrong_name_rejected():
    """Verify folder validation fails when folder name differs from expected."""
    mock_wrong_name = {
        "id": TARGET_FOLDER_ID,
        "name": "Different Folder",
        "mimeType": "application/vnd.google-apps.folder",
        "trashed": False
    }
    res = validate_target_folder(mock_response=mock_wrong_name)
    assert res["valid"] is False
    assert "Folder name 'Different Folder' != expected" in res["error"]


def test_target_folder_trashed_rejected():
    """Verify folder validation fails when folder is in trash."""
    mock_trashed = {
        "id": TARGET_FOLDER_ID,
        "name": TARGET_FOLDER_NAME,
        "mimeType": "application/vnd.google-apps.folder",
        "trashed": True
    }
    res = validate_target_folder(mock_response=mock_trashed)
    assert res["valid"] is False
    assert "Folder is in Drive Trash" in res["error"]


def test_target_folder_non_folder_mime_rejected():
    """Verify non-folder item (e.g. file) is rejected."""
    mock_file = {
        "id": TARGET_FOLDER_ID,
        "name": TARGET_FOLDER_NAME,
        "mimeType": "application/octet-stream",
        "trashed": False
    }
    res = validate_target_folder(mock_response=mock_file)
    assert res["valid"] is False
    assert "MIME type" in res["error"]


def test_target_folder_fallback_discovery():
    """Verify fallback discovery exposes exact folder candidate if direct query fails."""
    mock_list = {
        "files": [{
            "id": TARGET_FOLDER_ID,
            "name": TARGET_FOLDER_NAME,
            "mimeType": "application/vnd.google-apps.folder",
            "trashed": False,
            "owners": [{"emailAddress": EXPECTED_ACCOUNT}],
            "parents": ["root"]
        }]
    }
    res = validate_target_folder(mock_response=None, mock_list_response=mock_list)
    assert res["valid"] is False  # Direct lookup was None, but discovered candidate recorded
    assert res["discovered_candidate"] is not None
    assert res["discovered_candidate"]["id"] == TARGET_FOLDER_ID
    assert res["configured_folder_id"] == TARGET_FOLDER_ID


def test_target_folder_multiple_exact_name_candidates():
    """Verify ambiguity detection when multiple folders share the same name."""
    mock_list = {
        "files": [
            {"id": TARGET_FOLDER_ID, "name": TARGET_FOLDER_NAME},
            {"id": "duplicate_id_99999", "name": TARGET_FOLDER_NAME}
        ]
    }
    res = validate_target_folder(mock_response=None, mock_list_response=mock_list)
    assert res["discovery_error"] is not None
    assert "Multiple (2) folders named" in res["discovery_error"]
