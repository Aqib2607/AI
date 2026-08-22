"""
Unit tests for configuration parsing, schema validation, and environment variables.
"""

import os
import pytest
import yaml


def test_env_example_contains_all_required_variables():
    env_example_path = os.path.join(os.path.dirname(__file__), "..", ".env.example")
    assert os.path.exists(env_example_path), ".env.example must exist"
    
    with open(env_example_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    required_vars = [
        "HF_TOKEN",
        "MODEL_REPO",
        "MODEL_DIR",
        "DRIVE_MODEL_DIR",
        "LOCAL_MODEL_DIR",
        "COLI_MODEL",
        "COLI_MODEL_ID",
        "COLI_ENGINE",
        "COLI_HOST",
        "COLI_PORT",
        "COLI_API_KEY",
        "COLI_MAX_TOKENS",
        "COLI_MAX_QUEUE",
        "COLI_QUEUE_TIMEOUT"
    ]
    
    for var in required_vars:
        assert f"{var}=" in content, f"Variable {var} must be declared in .env.example"


def test_model_yaml_configuration():
    model_yaml_path = os.path.join(os.path.dirname(__file__), "..", "config", "model.example.yaml")
    assert os.path.exists(model_yaml_path), "config/model.example.yaml must exist"
    
    with open(model_yaml_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    assert "model" in config
    assert config["model"]["name"] == "GLM-5.2"
    assert config["model"]["quantization"]["scheme"] == "grouped-int4"
    assert config["model"]["quantization"]["group_size"] == 64
    assert config["model"]["files"]["shards"]["total_shards"] == 142
    assert config["model"]["files"]["shards"]["mtp_shards"] == 1
    assert config["model"]["quantization"]["minimum_colibri_version"] == "v1.5.0+"


def test_runtime_yaml_configuration():
    runtime_yaml_path = os.path.join(os.path.dirname(__file__), "..", "config", "runtime.example.yaml")
    assert os.path.exists(runtime_yaml_path), "config/runtime.example.yaml must exist"
    
    with open(runtime_yaml_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
        
    assert "runtime" in config
    assert config["runtime"]["memory"]["dense_resident_ram_gb"] == 9.9
    assert config["runtime"]["server"]["host"] == "127.0.0.1"
    assert config["runtime"]["server"]["port"] == 8000
    assert config["runtime"]["speculation"]["mtp_enabled"] is True
