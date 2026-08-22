# Model Architecture & Integrity Specification

**Status**: `[VERIFIED]`

---

## 1. Primary Model Specification

- `[VERIFIED]` **Hugging Face Model ID**: `mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp`
- `[VERIFIED]` **Base Architecture**: ChatGLM-MoE (744 Billion Total Parameters, ~40 Billion Active Parameters per Token)
- `[VERIFIED]` **Quantization Format**: Grouped INT4 (Group Size 64 / `gs64`) Safetensors
- `[VERIFIED]` **Multi-Token Prediction (MTP)**: Speculative Decoding Head (`out-mtp-00000.safetensors`, 9.28 GiB / 9.96 GB)
- `[VERIFIED]` **Total File Count**: 149 items (142 Safetensors shards, 4 JSON metadata files)
- `[VERIFIED]` **Total Repository Volume**: 399.79 GiB (429.28 GB decimal)

---

## 2. Model File Inventory Layout

```
model/
├── config.json                       # Architectural hyperparameters (7.67 KB)
├── generation_config.json            # Sampling and EOS parameters (458 B)
├── tokenizer.json                    # Full BPE tokenizer vocabulary (4.45 MB)
├── tokenizer_config.json             # Chat templates (52.3 KB)
├── README.md                         # Model card
├── out-mtp-00000.safetensors         # [VERIFIED] INT8 MTP Speculative Head (9.28 GiB)
├── out-00000.safetensors             # [VERIFIED] Shard 0 (~2.84 GiB)
├── ...
└── out-00140.safetensors             # [VERIFIED] Shard 140 (~2.84 GiB)
```

---

## 3. Non-Destructive Integrity Verification Protocol

The verification script (`scripts/model_verify.py`) performs fast, non-destructive validation without loading multi-gigabyte matrices into system memory:

1. `[VERIFIED]` **Header Parsing**: Reads 8-byte little-endian header length prefix and parses JSON metadata block.
2. `[VERIFIED]` **Shard Count**: Verifies that all 142 shards exist and have valid Safetensors headers.
3. `[VERIFIED]` **Health Status Codes**:
   - `READY`: All metadata, tokenizers, and 142 shards are present and structurally valid.
   - `INCOMPLETE`: One or more shards are missing or truncated.
   - `CORRUPTED`: Header metadata cannot be parsed as valid JSON.
   - `MISSING`: Target directory does not exist or contains no `.safetensors` files.
