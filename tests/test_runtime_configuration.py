"""
Unit tests for runtime pre-flight checks, environment diagnostics, and drive validation.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from environment_check import check_cpu_features, check_memory, check_disk
from drive_check import check_drive_storage


def test_cpu_feature_detection():
    cpu = check_cpu_features()
    assert "logical_cores" in cpu
    assert isinstance(cpu["logical_cores"], int)
    assert "avx2_supported" in cpu


def test_memory_inspection():
    mem = check_memory()
    assert "total_ram_gb" in mem
    assert "available_ram_gb" in mem
    assert "required_dense_ram_gb" in mem
    assert mem["required_dense_ram_gb"] == 9.9


def test_disk_inspection(tmp_path):
    disk = check_disk(str(tmp_path))
    assert "free_gb" in disk
    assert "total_gb" in disk
    assert "can_host_full_model_locally" in disk


def test_drive_storage_check_directory_creation(tmp_path):
    target_drive = tmp_path / "google_drive_mock"
    report = check_drive_storage(str(target_drive), required_free_gb=0.1)
    assert report["exists"] is True
    assert report["is_writable"] is True
    assert report["is_quota_sufficient"] is True
    assert report["status"] == "HEALTHY"
