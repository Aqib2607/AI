# Model Architecture & Integrity Specification

---

## 1. Primary Model Specification

- **Hugging Face Model ID**: `mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp`
- **Base Architecture**: ChatGLM-MoE (744 Billion Total Parameters, ~40 Billion Active Parameters per Token)
- **Quantization Format**: Grouped INT4 (Group Size 64 / `gs64`) Safetensors
- **Multi-Token Prediction (MTP)**: Speculative Decoding Head (INT8)
- **Context Length**: Up to 131,072 tokens (128k supported)

---

## 2. Model File Inventory

The model directory must contain exactly 38 weight shards plus tokenizer and configuration metadata:

```
model/
├── config.json                       # Architectural hyperparameters
├── generation_config.json            # Sampling and EOS parameters
├── tokenizer.json                    # Full BPE tokenizer vocabulary
├── tokenizer_config.json             # Chat templates and special tokens
├── special_tokens_map.json           # Token mappings (<|endoftext|>, etc.)
├── model.safetensors.index.json      # Tensor-to-shard manifest
├── model-00001-of-00038.safetensors  # Shard 1 of 38 (~9.9 GB)
├── ...
└── model-00038-of-00038.safetensors  # Shard 38 of 38 (~9.9 GB)
```

---

## 3. Non-Destructive Integrity Verification Protocol

The verification script (`scripts/model_verify.py`) performs fast, non-destructive validation without loading multi-gigabyte matrices into system memory:

1. **Header Parsing**: Reads the 8-byte little-endian header length from each `.safetensors` file and parses the JSON metadata block.
2. **Shard Count**: Verifies that all 38 shards exist and have sizes exceeding 1 GB.
3. **Index Mapping**: Validates that all tensors declared in `model.safetensors.index.json` map to valid existing shards.
4. **Health Status Codes**:
   - `READY`: All metadata, tokenizers, and 38 shards are present and structurally valid.
   - `INCOMPLETE`: One or more shards are missing or truncated.
   - `CORRUPTED`: Header metadata cannot be parsed as valid JSON.
   - `MISSING`: Target directory does not exist or contains no `.safetensors` files.
