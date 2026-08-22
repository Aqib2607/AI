"""
Unit and functional tests for Colibri dual-drive mirroring semantics,
fallback resolution, and hybrid staging simulation.
"""

import os
import tempfile
import pytest


def resolve_model_file(filename: str, primary_dir: str, mirror_dir: str = None) -> tuple[str, str]:
    """
    Simulate Colibri dual-drive file resolution semantics:
    1. Check primary local directory first.
    2. Fall back to mirror directory if absent in primary.
    3. Raise FileNotFoundError if absent in both.
    """
    primary_file = os.path.join(primary_dir, filename)
    if os.path.exists(primary_file):
        return primary_file, "PRIMARY"
        
    if mirror_dir:
        mirror_file = os.path.join(mirror_dir, filename)
        if os.path.exists(mirror_file):
            return mirror_file, "MIRROR"
            
    raise FileNotFoundError(f"Model file '{filename}' not found in primary ({primary_dir}) or mirror ({mirror_dir})")


def parse_disk_weights(weights_str: str) -> tuple[float, float]:
    """Parse COLI_DISK_WEIGHTS ratio (e.g. '9,1' -> (0.9, 0.1))."""
    parts = [float(p.strip()) for p in weights_str.split(",")]
    if len(parts) != 2:
        raise ValueError("COLI_DISK_WEIGHTS must contain exactly two numeric components (e.g. '9,1')")
    total = sum(parts)
    if total <= 0:
        raise ValueError("Total disk weight must be positive")
    return parts[0] / total, parts[1] / total


def test_parse_valid_disk_weights():
    w1, w2 = parse_disk_weights("9,1")
    assert round(w1, 2) == 0.90
    assert round(w2, 2) == 0.10

    w_equal1, w_equal2 = parse_disk_weights("1,1")
    assert w_equal1 == 0.5
    assert w_equal2 == 0.5


def test_parse_invalid_disk_weights():
    with pytest.raises(ValueError):
        parse_disk_weights("9")
    with pytest.raises(ValueError):
        parse_disk_weights("0,0")


def test_hybrid_staging_resolution(tmp_path):
    # Setup mock primary (Colab local NVMe) and mock mirror (Google Drive)
    primary_dir = tmp_path / "colab_local_model"
    mirror_dir = tmp_path / "google_drive_model"
    primary_dir.mkdir()
    mirror_dir.mkdir()

    # 1. Place configs and MTP head on primary (warm staged)
    (primary_dir / "config.json").write_text('{"model": "GLM-5.2"}')
    (primary_dir / "out-mtp-00000.safetensors").write_bytes(b"MTP_HEAD_INT8_DATA")
    (primary_dir / "out-00000.safetensors").write_bytes(b"HOT_SHARD_0_DATA")

    # 2. Place full repository on mirror (Google Drive)
    (mirror_dir / "config.json").write_text('{"model": "GLM-5.2"}')
    (mirror_dir / "out-mtp-00000.safetensors").write_bytes(b"MTP_HEAD_INT8_DATA")
    (mirror_dir / "out-00000.safetensors").write_bytes(b"HOT_SHARD_0_DATA")
    (mirror_dir / "out-00001.safetensors").write_bytes(b"COLD_SHARD_1_DATA")
    (mirror_dir / "out-00140.safetensors").write_bytes(b"COLD_SHARD_140_DATA")

    # Test 1: Config resolved from primary
    path, source = resolve_model_file("config.json", str(primary_dir), str(mirror_dir))
    assert source == "PRIMARY"
    assert path == str(primary_dir / "config.json")

    # Test 2: MTP head resolved from fast primary NVMe
    path, source = resolve_model_file("out-mtp-00000.safetensors", str(primary_dir), str(mirror_dir))
    assert source == "PRIMARY"
    assert path == str(primary_dir / "out-mtp-00000.safetensors")

    # Test 3: Un-staged shard 1 falls back to mirror (Google Drive)
    path, source = resolve_model_file("out-00001.safetensors", str(primary_dir), str(mirror_dir))
    assert source == "MIRROR"
    assert path == str(mirror_dir / "out-00001.safetensors")

    # Test 4: Missing file raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        resolve_model_file("nonexistent_shard.safetensors", str(primary_dir), str(mirror_dir))
