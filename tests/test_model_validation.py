"""
Unit tests for non-destructive Safetensors header parsing and model verification.
"""

import os
import sys
import json
import struct
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from model_verify import read_safetensors_header, verify_model_directory


def create_synthetic_safetensors(file_path: str, metadata: dict, tensor_bytes: bytes = b"\x00" * 64):
    """Helper to create a syntactically valid Safetensors file binary fixture."""
    header_json = json.dumps(metadata).encode("utf-8")
    header_len = len(header_json)
    header_len_bytes = struct.pack("<Q", header_len)
    with open(file_path, "wb") as f:
        f.write(header_len_bytes)
        f.write(header_json)
        f.write(tensor_bytes)


def test_read_valid_safetensors_header(tmp_path):
    shard_path = str(tmp_path / "model-00001-of-00001.safetensors")
    expected_meta = {"transformer.embed.weight": {"dtype": "I4", "shape": [100, 100], "data_offsets": [0, 64]}}
    create_synthetic_safetensors(shard_path, expected_meta)
    
    ok, header, err = read_safetensors_header(shard_path)
    assert ok is True
    assert err is None
    assert header == expected_meta


def test_read_corrupted_safetensors_header(tmp_path):
    shard_path = str(tmp_path / "corrupt.safetensors")
    # Write invalid header length exceeding file size
    with open(shard_path, "wb") as f:
        f.write(struct.pack("<Q", 99999999))
        f.write(b"too small")
        
    ok, header, err = read_safetensors_header(shard_path)
    assert ok is False
    assert header is None
    assert "Corrupted header length" in err


def test_verify_model_directory_complete(tmp_path):
    mock_dir = tmp_path / "complete_model"
    mock_dir.mkdir()
    
    # Metadata
    (mock_dir / "config.json").write_text(json.dumps({"model_type": "glm_moe"}))
    (mock_dir / "generation_config.json").write_text(json.dumps({"max_length": 2048}))
    (mock_dir / "model.safetensors.index.json").write_text(json.dumps({"weight_map": {}}))
    
    # Tokenizer
    (mock_dir / "tokenizer.json").write_text(json.dumps({"vocab": {}}))
    (mock_dir / "tokenizer_config.json").write_text(json.dumps({"do_lower_case": False}))
    (mock_dir / "special_tokens_map.json").write_text(json.dumps({"eos_token": "<|endoftext|>"}))
    
    # Create 3 valid shards with custom threshold for testing
    for i in range(1, 4):
        create_synthetic_safetensors(
            str(mock_dir / f"model-{i:05d}-of-00003.safetensors"),
            {"sample.tensor": {"dtype": "I4", "shape": [10, 10], "data_offsets": [0, 64]}}
        )
        
    report = verify_model_directory(str(mock_dir), min_expected_shards=3)
    assert report["status"] == "READY"
    assert report["metadata_valid"] is True
    assert report["tokenizer_valid"] is True
    assert report["shards_valid"] is True
