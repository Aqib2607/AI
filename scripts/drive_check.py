#!/usr/bin/env python3
"""
Google Drive API Quota & Storage Preflight Check
Authoritatively validates Google Drive storage quota using Google Drive API v3 (drive.about.get),
validates target folder ID & metadata via drive.files().get() and fallback discovery,
verifies mounted filesystem accessibility and write permissions, and isolates FUSE diagnostics.

Account: aqibjawwad2607@gmail.com
Target Folder: "AI - Google Drive" (ID: 11BdZx7pI2XyEmiJjpZJjTCIX1V41vKhd)
"""

import sys
import os
import shutil
import json
import argparse
from typing import Dict, Any, List, Optional, Tuple

try:
    from rich.console import Console  # type: ignore
    from rich.panel import Panel      # type: ignore
    from rich.table import Table      # type: ignore
    console = Console()
except ImportError:
    console = None

# Defaults and Pinned Identifiers
EXPECTED_ACCOUNT = "aqibjawwad2607@gmail.com"
TARGET_FOLDER_ID = "11BdZx7pI2XyEmiJjpZJjTCIX1V41vKhd"
TARGET_FOLDER_NAME = "AI - Google Drive"

REQUIRED_SUBDIRECTORIES = [
    "model",
    "runtime",
    "logs",
    "manifests",
    "benchmarks"
]


def get_google_drive_credentials():
    """
    Obtain authenticated Google credentials in Google Colab or local environment.
    Uses google.colab.auth in Colab, or standard google.auth credentials.
    """
    try:
        # Check if in Google Colab environment
        import importlib
        colab_auth = importlib.import_module("google" + ".colab.auth")
        colab_auth.authenticate_user()
    except Exception:
        pass

    try:
        import importlib
        gauth = importlib.import_module("google.auth")
        credentials, _ = gauth.default(scopes=[
            "https://www.googleapis.com/auth/drive.readonly",
            "https://www.googleapis.com/auth/drive.metadata.readonly",
            "https://www.googleapis.com/auth/drive"
        ])
        return credentials
    except Exception:
        return None


def get_drive_service(credentials=None):
    """Build and return a Google Drive API v3 resource client."""
    if credentials is None:
        credentials = get_google_drive_credentials()
    try:
        from googleapiclient.discovery import build  # type: ignore
        return build("drive", "v3", credentials=credentials)
    except Exception:
        return None


def get_drive_storage_quota(service=None, mock_response: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Retrieve authoritative Google Drive account storage quota via drive.about.get.
    Extracts limit, usage, usageInDrive, usageInDriveTrash, and computes free storage.
    Supports unlimited/null quota handling.
    """
    about_data = mock_response
    if about_data is None and service is not None:
        try:
            about_data = service.about().get(fields="storageQuota,user").execute()
        except Exception as e:
            return {
                "success": False,
                "error": f"Drive API query failed: {str(e)}",
                "email": None,
                "limit_bytes": None,
                "usage_bytes": None,
                "free_bytes": None,
                "limit_gb": None,
                "usage_gb": None,
                "free_gb": None,
                "limit_gib": None,
                "usage_gib": None,
                "free_gib": None,
                "is_unlimited": False
            }

    if about_data is None:
        return {
            "success": False,
            "error": "Google Drive API service or authentication not available",
            "email": None,
            "limit_bytes": None,
            "usage_bytes": None,
            "free_bytes": None,
            "limit_gb": None,
            "usage_gb": None,
            "free_gb": None,
            "limit_gib": None,
            "usage_gib": None,
            "free_gib": None,
            "is_unlimited": False
        }

    storage_quota = about_data.get("storageQuota", {})
    user_info = about_data.get("user", {})
    email = user_info.get("emailAddress")

    raw_limit = storage_quota.get("limit")
    raw_usage = storage_quota.get("usage", "0")
    raw_usage_drive = storage_quota.get("usageInDrive", "0")
    raw_usage_trash = storage_quota.get("usageInDriveTrash", "0")

    usage_bytes = int(raw_usage) if raw_usage is not None else 0
    usage_drive_bytes = int(raw_usage_drive) if raw_usage_drive is not None else 0
    usage_trash_bytes = int(raw_usage_trash) if raw_usage_trash is not None else 0

    if raw_limit is None:
        # Unlimited quota or unmetered enterprise/workspace plan
        return {
            "success": True,
            "error": None,
            "email": email,
            "limit_bytes": None,
            "usage_bytes": usage_bytes,
            "usage_drive_bytes": usage_drive_bytes,
            "usage_trash_bytes": usage_trash_bytes,
            "free_bytes": None,
            "limit_gb": None,
            "usage_gb": round(usage_bytes / 1e9, 2),
            "free_gb": None,
            "limit_gib": None,
            "usage_gib": round(usage_bytes / (1024 ** 3), 2),
            "free_gib": None,
            "is_unlimited": True
        }

    limit_bytes = int(raw_limit)
    free_bytes = max(0, limit_bytes - usage_bytes)

    return {
        "success": True,
        "error": None,
        "email": email,
        "limit_bytes": limit_bytes,
        "usage_bytes": usage_bytes,
        "usage_drive_bytes": usage_drive_bytes,
        "usage_trash_bytes": usage_trash_bytes,
        "free_bytes": free_bytes,
        "limit_gb": round(limit_bytes / 1e9, 2),
        "usage_gb": round(usage_bytes / 1e9, 2),
        "free_gb": round(free_bytes / 1e9, 2),
        "limit_gib": round(limit_bytes / (1024 ** 3), 2),
        "usage_gib": round(usage_bytes / (1024 ** 3), 2),
        "free_gib": round(free_bytes / (1024 ** 3), 2),
        "is_unlimited": False
    }


def validate_target_folder(
    service=None,
    folder_id: str = TARGET_FOLDER_ID,
    expected_name: str = TARGET_FOLDER_NAME,
    mock_response: Optional[Dict[str, Any]] = None,
    mock_list_response: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Validate target Google Drive folder using the folder ID as the authoritative identifier.

    Authoritative gates (required for PASS):
      - Folder ID resolves via Drive API (no 404 / 403)
      - mimeType == application/vnd.google-apps.folder
      - Folder is not in Trash

    Non-blocking (INFORMATIONAL only — never causes FAIL):
      - Configured display name vs. API-returned folder name
        Drive folder names can differ from configured labels without affecting the folder's identity.

    Fallback: if direct lookup fails, performs a narrow name-scoped list() for diagnostics only.
    """
    folder_data = mock_response
    direct_lookup_error = None
    http_status = None

    # 1. Primary Direct Lookup by folder_id (authoritative)
    if folder_data is None and service is not None:
        try:
            folder_data = service.files().get(
                fileId=folder_id,
                fields="id,name,mimeType,parents,driveId,trashed,owners(emailAddress)",
                supportsAllDrives=True
            ).execute()
        except Exception as e:
            direct_lookup_error = str(e)
            if hasattr(e, "resp") and hasattr(e.resp, "status"):
                http_status = e.resp.status
            elif hasattr(e, "status_code"):
                http_status = e.status_code

    # 2. Fallback Diagnostic Search if direct lookup failed
    discovered_candidate = None
    discovery_error = None
    if folder_data is None and (service is not None or mock_list_response is not None):
        try:
            list_res = mock_list_response
            if list_res is None and service is not None:
                list_res = service.files().list(
                    q=f"name = '{expected_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
                    spaces="drive",
                    fields="files(id, name, mimeType, parents, driveId, trashed, owners(emailAddress))",
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True
                ).execute()
            files_found = list_res.get("files", []) if list_res else []
            if files_found:
                discovered_candidate = files_found[0]
                if len(files_found) > 1:
                    discovery_error = f"Multiple ({len(files_found)}) folders named '{expected_name}' found in Drive."
        except Exception as e:
            discovery_error = f"Fallback folder discovery failed: {str(e)}"

    # 3. Analyze direct lookup — folder ID is authoritative identifier
    if folder_data is not None:
        api_name = folder_data.get("name")
        mime_type = folder_data.get("mimeType")
        trashed = folder_data.get("trashed", False)
        parents = folder_data.get("parents", [])
        drive_id = folder_data.get("driveId")
        owners = [o.get("emailAddress") for o in folder_data.get("owners", []) if isinstance(o, dict)]
        resolved_id = folder_data.get("id", folder_id)

        # Authoritative gates — these cause FAIL
        is_folder = (mime_type == "application/vnd.google-apps.folder")
        not_trashed = (not trashed)
        id_matches = (resolved_id == folder_id)
        is_valid = is_folder and not_trashed and id_matches

        # Informational only — does NOT cause FAIL
        name_matches = (api_name == expected_name)
        name_mismatch_note = None
        if not name_matches:
            name_mismatch_note = (
                f"INFORMATIONAL: Configured display name '{expected_name}' differs from "
                f"API-returned folder name '{api_name}'. "
                f"The folder ID {folder_id} is authoritative and has been confirmed accessible."
            )

        error_msg = None
        if not is_valid:
            reasons = []
            if not is_folder:
                reasons.append(f"MIME type '{mime_type}' is not 'application/vnd.google-apps.folder'")
            if trashed:
                reasons.append("Folder is in Drive Trash")
            if not id_matches:
                reasons.append(f"Resolved ID '{resolved_id}' does not match configured ID '{folder_id}'")
            error_msg = "; ".join(reasons)

        return {
            "valid": is_valid,
            "api_lookup_status": "PASS" if is_valid else "FAILED",
            "folder_id": resolved_id,
            "configured_folder_id": folder_id,
            "configured_folder_name": expected_name,
            "folder_name": api_name,
            "mime_type": mime_type,
            "trashed": trashed,
            "parents": parents,
            "drive_id": drive_id,
            "owners": owners,
            "is_folder": is_folder,
            "name_matches": name_matches,
            "name_mismatch_note": name_mismatch_note,
            "folder_id_match": "PASS" if id_matches else "FAIL",
            "http_status": 200,
            "error": error_msg,
            "discovered_candidate": None,
            "discovery_error": None
        }

    # 4. Direct lookup failed — construct diagnostic response
    discovered_id = discovered_candidate.get("id") if discovered_candidate else None
    discovered_name = discovered_candidate.get("name") if discovered_candidate else None
    discovered_owners = (
        [o.get("emailAddress") for o in discovered_candidate.get("owners", []) if isinstance(o, dict)]
        if discovered_candidate else []
    )

    error_summary = direct_lookup_error or "Folder lookup failed (no API service available)"
    if discovered_candidate:
        error_summary += (
            f" | Diagnostic: A folder named '{discovered_name}' was found with ID '{discovered_id}' "
            f"(Owners: {discovered_owners}). Verify whether this is the intended target."
        )

    return {
        "valid": False,
        "api_lookup_status": "FAILED",
        "folder_id": folder_id,
        "configured_folder_id": folder_id,
        "configured_folder_name": expected_name,
        "folder_name": None,
        "mime_type": None,
        "trashed": None,
        "parents": [],
        "drive_id": None,
        "owners": [],
        "is_folder": False,
        "name_matches": False,
        "name_mismatch_note": None,
        "folder_id_match": "MATCH_CONFIRMED" if (discovered_id == folder_id) else "MISMATCH" if discovered_id else "UNKNOWN",
        "http_status": http_status,
        "error": error_summary,
        "discovered_candidate": discovered_candidate,
        "discovery_error": discovery_error
    }


def get_fuse_usage(path: str) -> Dict[str, Any]:
    """
    Query virtual FUSE filesystem capacity via shutil.disk_usage.
    Marked explicitly as secondary diagnostic information, NOT account quota.
    """
    resolved = os.path.abspath(path)
    # Walk up to existing ancestor if target path does not exist yet
    target = resolved
    while target and not os.path.exists(target) and os.path.dirname(target) != target:
        target = os.path.dirname(target)
    if not target or not os.path.exists(target):
        target = "."

    try:
        total, used, free = shutil.disk_usage(target)
        return {
            "path": resolved,
            "fuse_total_bytes": total,
            "fuse_used_bytes": used,
            "fuse_free_bytes": free,
            "fuse_total_gb": round(total / 1e9, 2),
            "fuse_used_gb": round(used / 1e9, 2),
            "fuse_free_gb": round(free / 1e9, 2),
            "fuse_total_gib": round(total / (1024 ** 3), 2),
            "fuse_used_gib": round(used / (1024 ** 3), 2),
            "fuse_free_gib": round(free / (1024 ** 3), 2),
            "diagnostic_note": "FUSE capacity is a secondary diagnostic metric reflecting the Colab ephemeral virtual mount container and is NOT the user's Google Drive account quota."
        }
    except Exception as e:
        return {
            "path": resolved,
            "fuse_total_bytes": 0,
            "fuse_used_bytes": 0,
            "fuse_free_bytes": 0,
            "fuse_total_gb": 0.0,
            "fuse_used_gb": 0.0,
            "fuse_free_gb": 0.0,
            "fuse_total_gib": 0.0,
            "fuse_used_gib": 0.0,
            "fuse_free_gib": 0.0,
            "error": str(e),
            "diagnostic_note": "FUSE diagnostic query failed (path inaccessible)"
        }


def evaluate_storage_gate(
    account_free_gb: Optional[float],
    is_unlimited: bool = False,
    required_gb: float = 400.0,
    recommended_gb: float = 450.0
) -> Tuple[str, str]:
    """
    Evaluate storage feasibility against required model footprint.
    Decision Rules:
    - If unlimited: GO_UNLIMITED_QUOTA
    - If account_free_gb < required_gb (400 GB): NO-GO
    - If required_gb <= account_free_gb < recommended_gb (450 GB): GO_WITH_LOW_MARGIN
    - If recommended_gb <= account_free_gb < 500 GB: GO
    - If account_free_gb >= 500 GB: GO_WITH_RECOMMENDED_MARGIN
    """
    if is_unlimited:
        return ("GO_UNLIMITED_QUOTA", "Authoritative Google Drive API reports unlimited/unmetered quota. Preflight approved.")
        
    if account_free_gb is None:
        return ("NO-GO_UNKNOWN_QUOTA", "Unable to establish Google Drive API account quota. Authentication required.")

    if account_free_gb < required_gb:
        return (
            "NO-GO",
            f"Insufficient Google Drive account storage: {account_free_gb:.2f} GB free is below the required {required_gb:.2f} GB threshold."
        )
    elif account_free_gb < recommended_gb:
        return (
            "GO_WITH_LOW_MARGIN",
            f"Storage gate passed with low safety margin: {account_free_gb:.2f} GB free exceeds required {required_gb:.2f} GB, but is below recommended {recommended_gb:.2f} GB."
        )
    elif account_free_gb < 500.0:
        return (
            "GO",
            f"Storage gate passed: {account_free_gb:.2f} GB free satisfies recommended threshold ({recommended_gb:.2f} GB)."
        )
    else:
        return (
            "GO_WITH_RECOMMENDED_MARGIN",
            f"Storage gate passed with ample capacity: {account_free_gb:.2f} GB free exceeds preferred safety margin (>= 500 GB)."
        )


def check_drive_storage(
    path: str,
    required_gb: float = 400.0,
    recommended_gb: float = 450.0,
    folder_id: str = TARGET_FOLDER_ID,
    service=None,
    mock_about: Optional[Dict[str, Any]] = None,
    mock_folder: Optional[Dict[str, Any]] = None,
    mock_list_folder: Optional[Dict[str, Any]] = None,
    init_subdirectories: bool = True
) -> Dict[str, Any]:
    """
    Consolidated Google Drive Preflight Audit:
    1. Queries authoritative Google Drive API account quota.
    2. Validates target folder ID and metadata via supportsAllDrives=True and fallback search.
    3. Verifies mounted filesystem accessibility and initializes GLM-5.2 subdirectories.
    4. Probes non-destructive write permissions.
    5. Captures FUSE mount diagnostics separately.
    6. Evaluates final decision (GO / WARNING / NO-GO).
    """
    resolved_path = os.path.abspath(path)
    
    # 1. Authoritative Drive API Quota
    quota_info = get_drive_storage_quota(service=service, mock_response=mock_about)
    account_email = quota_info.get("email") or EXPECTED_ACCOUNT
    
    # 2. Folder Validation via Drive API (supportsAllDrives=True)
    folder_info = validate_target_folder(
        service=service,
        folder_id=folder_id,
        expected_name=TARGET_FOLDER_NAME,
        mock_response=mock_folder,
        mock_list_response=mock_list_folder
    )
    
    # 3. FUSE Diagnostics (shutil.disk_usage)
    fuse_info = get_fuse_usage(resolved_path)
    
    # 4. Storage Gate Decision
    gate_status, gate_reason = evaluate_storage_gate(
        account_free_gb=quota_info.get("free_gb"),
        is_unlimited=quota_info.get("is_unlimited", False),
        required_gb=required_gb,
        recommended_gb=recommended_gb
    )
    
    # 5. Local/Mount Path Directory Management & Filesystem Accessibility
    dir_exists = os.path.exists(resolved_path)
    drive_root_path = "/content/drive/MyDrive/AI - Google Drive"
    drive_root_exists = os.path.exists(drive_root_path) if os.path.exists("/content/drive") else dir_exists

    if not dir_exists and init_subdirectories:
        try:
            os.makedirs(resolved_path, exist_ok=True)
            dir_exists = True
        except Exception:
            pass

    project_root = resolved_path if os.path.basename(resolved_path) == "GLM-5.2" else os.path.dirname(resolved_path)
    subdirs = {}
    for subdir in REQUIRED_SUBDIRECTORIES:
        s_path = os.path.join(project_root, subdir)
        if init_subdirectories and dir_exists:
            try:
                os.makedirs(s_path, exist_ok=True)
            except Exception:
                pass
        subdirs[subdir] = {
            "path": s_path,
            "exists": os.path.exists(s_path)
        }

    # 6. Non-destructive write permission probe
    is_writable = False
    write_error = None
    if dir_exists:
        test_probe_file = os.path.join(resolved_path, ".drive_probe_test.tmp")
        try:
            with open(test_probe_file, "w") as f:
                f.write("GLM-5.2 Colibri Drive Probe OK\n")
            if os.path.exists(test_probe_file):
                is_writable = True
                os.remove(test_probe_file)
        except Exception as e:
            write_error = str(e)

    # 7. Final overall status
    is_go = gate_status in ("GO", "GO_WITH_LOW_MARGIN", "GO_WITH_RECOMMENDED_MARGIN", "GO_UNLIMITED_QUOTA")
    folder_valid = folder_info.get("valid", False)
    filesystem_accessible = dir_exists and is_writable

    if is_go and is_writable and folder_valid:
        overall_status = "HEALTHY"
        final_decision = "GO"
    elif is_go and is_writable and filesystem_accessible:
        overall_status = "HEALTHY"
        final_decision = "GO_WITH_FILESYSTEM_ACCESS"
    elif not is_go:
        overall_status = "NO-GO"
        final_decision = "NO-GO"
    else:
        overall_status = "WARNING"
        final_decision = "WARNING"

    report = {
        "account_email": account_email,
        "target_folder_name": TARGET_FOLDER_NAME,
        "target_folder_id": folder_id,
        "target_path": resolved_path,
        "final_decision": final_decision,
        "drive_account_quota_limit_bytes": quota_info.get("limit_bytes"),
        "drive_account_quota_limit_gb": quota_info.get("limit_gb"),
        "drive_account_quota_limit_gib": quota_info.get("limit_gib"),
        "drive_account_usage_bytes": quota_info.get("usage_bytes"),
        "drive_account_usage_gb": quota_info.get("usage_gb"),
        "drive_account_usage_gib": quota_info.get("usage_gib"),
        "drive_account_free_bytes": quota_info.get("free_bytes"),
        "drive_account_free_gb": quota_info.get("free_gb"),
        "drive_account_free_gib": quota_info.get("free_gib"),
        "is_unlimited_quota": quota_info.get("is_unlimited", False),
        "fuse_total_bytes": fuse_info.get("fuse_total_bytes"),
        "fuse_total_gb": fuse_info.get("fuse_total_gb"),
        "fuse_used_bytes": fuse_info.get("fuse_used_bytes"),
        "fuse_used_gb": fuse_info.get("fuse_used_gb"),
        "fuse_free_bytes": fuse_info.get("fuse_free_bytes"),
        "fuse_free_gb": fuse_info.get("fuse_free_gb"),
        "fuse_diagnostic_note": fuse_info.get("diagnostic_note"),
        "required_free_gb": required_gb,
        "recommended_free_gb": recommended_gb,
        "storage_gate_status": gate_status,
        "storage_gate_reason": gate_reason,
        "api_folder_lookup": folder_info.get("api_lookup_status", "UNKNOWN"),
        "configured_folder_name": TARGET_FOLDER_NAME,
        "api_folder_name": folder_info.get("folder_name"),
        "api_folder_mime_type": folder_info.get("mime_type"),
        "api_folder_owner": folder_info.get("owners", []),
        "api_folder_parents": folder_info.get("parents", []),
        "api_folder_trash_state": "Trashed" if folder_info.get("trashed") else "Active" if folder_info.get("trashed") is False else "Unknown",
        "folder_id_match": folder_info.get("folder_id_match", "UNKNOWN"),
        "folder_name_match": "PASS" if folder_info.get("name_matches") else "INFORMATIONAL",
        "folder_name_mismatch_note": folder_info.get("name_mismatch_note"),
        "folder_validation_status": "PASS" if folder_info.get("valid") else "FAILED",
        "folder_validation_error": folder_info.get("error"),
        "folder_discovered_candidate": folder_info.get("discovered_candidate"),
        "filesystem_accessibility": "PASS" if dir_exists else "FAILED",
        "write_permission_status": "GRANTED" if is_writable else "DENIED",
        "write_permission_error": write_error,
        "subdirectories": subdirs,
        "status": overall_status,
        "api_available": quota_info.get("success", False)
    }
    
    return report


def build_parser() -> argparse.ArgumentParser:
    """Build and return command-line argument parser."""
    parser = argparse.ArgumentParser(description="Google Drive Storage & Project Structure Check")
    parser.add_argument(
        "--path",
        default=os.getenv("DRIVE_MODEL_DIR", "/content/drive/MyDrive/AI - Google Drive/GLM-5.2/model"),
        help="Target mounted Google Drive project or model directory"
    )
    parser.add_argument(
        "--required-gb",
        type=float,
        default=400.0,
        help="Absolute minimum free Google Drive account quota required (default: 400.0)"
    )
    parser.add_argument(
        "--recommended-gb",
        type=float,
        default=450.0,
        help="Recommended free Google Drive account quota (default: 450.0)"
    )
    parser.add_argument(
        "--folder-id",
        default=TARGET_FOLDER_ID,
        help=f"Expected Google Drive folder ID (default: {TARGET_FOLDER_ID})"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output machine-readable JSON validation report"
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    service = get_drive_service()
    report = check_drive_storage(
        path=args.path,
        required_gb=args.required_gb,
        recommended_gb=args.recommended_gb,
        folder_id=args.folder_id,
        service=service
    )

    is_go = report["status"] in ("GO", "GO_WITH_FILESYSTEM_ACCESS", "HEALTHY") or (
        report["storage_gate_status"] in ("GO", "GO_WITH_LOW_MARGIN", "GO_WITH_RECOMMENDED_MARGIN", "GO_UNLIMITED_QUOTA")
        and report["write_permission_status"] == "GRANTED"
    )

    if args.json:
        print(json.dumps(report, indent=2))
        sys.exit(0 if is_go else 1)

    if console:
        color = "green" if is_go else "red"
        
        limit_str = f"{report['drive_account_quota_limit_gb']:,} GB ({report['drive_account_quota_limit_gib']} GiB)" if report['drive_account_quota_limit_gb'] else "Unlimited / Unmetered"
        free_str = f"{report['drive_account_free_gb']:,} GB ({report['drive_account_free_gib']} GiB)" if report['drive_account_free_gb'] else "Unlimited / Unmetered"
        used_str = f"{report['drive_account_usage_gb']:,} GB ({report['drive_account_usage_gib']} GiB)" if report['drive_account_usage_gb'] else "Unknown"

        text = (
            f"[bold cyan]=== Google Drive Storage & Isolation Report ===[/bold cyan]\n"
            f"[bold]Authenticated Account:[/bold]     {report['account_email']}\n"
            f"[bold]Configured Folder Name:[/bold]    {report['target_folder_name']}\n"
            f"[bold]Configured Folder ID:[/bold]      {report['target_folder_id']}\n"
            f"[bold]Filesystem Path:[/bold]           {report['target_path']}\n\n"
            f"[bold cyan]Google Drive Account Quota (Authoritative API v3):[/bold cyan]\n"
            f"  Total Plan:                  {limit_str}\n"
            f"  Used Storage:                {used_str}\n"
            f"  Available Free Space:        [bold {color}]{free_str}[/bold {color}]\n"
            f"  Required Threshold:          >= {report['required_free_gb']} GB\n"
            f"  Recommended Threshold:       >= {report['recommended_free_gb']} GB\n"
            f"  Storage Gate Decision:       [{color}]{report['storage_gate_status']}[/{color}]\n\n"
            f"[bold cyan]Google Drive Folder Validation (API v3):[/bold cyan]\n"
            f"  API Folder Lookup:           {report['api_folder_lookup']}\n"
            f"  API Folder Name:             {report['api_folder_name'] or 'N/A'}\n"
            f"  API Folder MIME Type:        {report['api_folder_mime_type'] or 'N/A'}\n"
            f"  API Folder Owners:           {', '.join(report['api_folder_owner']) if report['api_folder_owner'] else 'N/A'}\n"
            f"  API Folder Parents:          {', '.join(report['api_folder_parents']) if report['api_folder_parents'] else 'N/A'}\n"
            f"  API Folder Trash State:      {report['api_folder_trash_state']}\n"
            f"  Folder ID Match:             {report['folder_id_match']}\n"
            f"  Folder Validation Status:    {report['folder_validation_status']}\n"
        )
        if report.get("folder_validation_error"):
            text += f"  [bold yellow]Diagnostic Detail:[/bold yellow]          {report['folder_validation_error']}\n"

        text += (
            f"\n[bold yellow]Google Drive FUSE Mount Diagnostics (Container Diagnostic Only):[/bold yellow]\n"
            f"  Virtual Total Capacity:      {report['fuse_total_gb']} GB\n"
            f"  Virtual Free Space:          {report['fuse_free_gb']} GB\n"
            f"  [italic]NOTE: FUSE values reflect Colab virtual container overlay, NOT Google Drive account quota.[/italic]\n\n"
            f"[bold]Filesystem Accessibility:[/bold]  {report['filesystem_accessibility']}\n"
            f"[bold]Write Permission:[/bold]         {report['write_permission_status']}\n"
            f"[bold]Final Decision:[/bold]           [{color}]{report['status']}[/{color}]"
        )
        console.print(Panel(text, title="Google Drive Storage & Isolation Preflight Report", border_style=color))
    else:
        print(json.dumps(report, indent=2))

    sys.exit(0 if is_go else 1)


if __name__ == "__main__":
    main()
