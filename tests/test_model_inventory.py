"""
Unit tests for model inventory scanning and shard cataloging using synthetic fixtures.
"""

import os
import sys
import json
import pytest

# Add scripts directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from model_inventory import scan_model_directory


def test_scan_nonexistent_directory():
    result = scan_model_directory("nonexistent_path_xyz_123")
    assert result["exists"] is False
    assert result["status"] == "MISSING"
    assert result["total_shards"] == 0


def test_scan_mock_model_directory(tmp_path):
    mock_dir = tmp_path / "mock_glm52"
    mock_dir.mkdir()
    
    # Create required metadata files
    (mock_dir / "config.json").write_text(json.dumps({"model_type": "glm_moe"}))
    (mock_dir / "generation_config.json").write_text(json.dumps({"max_length": 2048}))
    (mock_dir / "model.safetensors.index.json").write_text(json.dumps({"weight_map": {}}))
    
    # Create tokenizer files
    (mock_dir / "tokenizer.json").write_text(json.dumps({"vocab": {}}))
    (mock_dir / "tokenizer_config.json").write_text(json.dumps({"do_lower_case": False}))
    (mock_dir / "special_tokens_map.json").write_text(json.dumps({"eos_token": "<|endoftext|>"}))
    
    # Create synthetic shard files
    for i in range(1, 6):
        shard = mock_dir / f"model-{i:05d}-of-00038.safetensors"
        shard.write_bytes(b"\x00" * 1024)
        
    result = scan_model_directory(str(mock_dir))
    assert result["exists"] is True
    assert result["status"] == "PARTIAL"  # Partial because only 5 shards out of 38
    assert result["total_shards"] == 5
    assert len(result["missing_metadata"]) == 0
    assert len(result["missing_tokenizer"]) == 0
