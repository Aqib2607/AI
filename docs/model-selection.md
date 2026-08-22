# Model Selection & Compatibility Rationale

**Date**: 2026-08-23  
**Selected Primary Target**: `mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp`  
**Reference Video Target**: `annelo/GLM-5.2-FP8-Uncensored-Colibri-Int4`  
**Alternative Fallback**: `jlnsrk/GLM-5.2-colibri-int4`

---

## 1. Candidate Comparison Matrix

| Evaluation Criterion | `mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp` (Primary) | `annelo/GLM-5.2-FP8-Uncensored-Colibri-Int4` (Reference Target) | `jlnsrk/GLM-5.2-colibri-int4` (Legacy) |
| :--- | :--- | :--- | :--- |
| **Model Type** | GLM-5.2 744B MoE Container | GLM-5.2 744B MoE Container (Uncensored) | GLM-5.2 744B MoE Container |
| **Quantization Scheme** | Grouped INT4 ($gs=64$) | Per-row INT4 / FP8 mixed | Per-row INT4 |
| **MTP Speculative Head**| Yes (INT8 calibrated) | Uncalibrated / Absent | Absent |
| **Repetition / Runaway Risk** | **Zero / Mitigated** (Grouped scales prevent dynamic range collapse) | Low to Moderate | High (documented runaway generation issues) |
| **Inference Engine** | Colibrì (`JustVugg/colibri`) | Colibrì (`JustVugg/colibri`) | Colibrì (`JustVugg/colibri`) |
| **Approximate Total Size** | ~380 GB | ~370 GB | ~370 GB |
| **Upstream Status** | **Official Recommended Standard** | Validated Community Variant | Deprecated |
| **Project Support Level** | **Primary Default (`.env.example`)** | Fully Compatible Fallback | Supported Fallback |

---

## 2. Technical Rationale for Primary Selection

### A. Grouped Quantization ($gs=64$) vs. Per-Row Quantization
Early Colibri containers utilized naive per-row INT4 quantization. Due to the high dynamic range and outlier activations present in 744B MoE layers, per-row scaling causes catastrophic precision loss in low-magnitude weights, leading to:
- Degradation of reasoning and code generation quality.
- Generation loops where the model endlessly repeats tokens without emitting stop tokens (`<|endoftext|>`).

The `mastouri` container applies **grouped INT4 scaling with a group size of 64 ($gs=64$)**. This partitions weight matrices into 64-element blocks with dedicated scale factors, preserving outlier fidelity and completely resolving repetition loops.

### B. Multi-Token Prediction (MTP) Speculation Support
The primary model includes pre-quantized INT8 Multi-Token Prediction heads. In Colibrì, MTP provides speculative drafting:
- Generates 2–3 draft tokens per step using the speculative head.
- Verifies draft tokens in a single forward batch pass.
- Yields up to a $1.8\times$ decoding speedup when expert caching is warm.

---

## 3. Required File Components & Shard Structure

A valid Colibri GLM-5.2 model distribution consists of the following mandatory components:

```
mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp/
├── config.json                       # Base architectural hyperparameters
├── generation_config.json            # Sampling, temperature, and EOS definitions
├── tokenizer.json                    # Full BPE tokenizer vocabulary and merges
├── tokenizer_config.json             # Chat template and special token handling
├── special_tokens_map.json           # BOS/EOS/PAD/MASK token mappings
├── model.safetensors.index.json      # Tensor-to-shard mapping manifest
└── model-00001-of-00038.safetensors  # Weight shards (~9.8 GB - ~10.2 GB each)
    ...
    model-00038-of-00038.safetensors  # Shard 38 of 38 (~380 GB total)
```

### Component Integrity Verification Rules
1. **Metadata & Tokenizer**: Must parse valid JSON and conform to GLM-5.2 vocabulary specifications.
2. **Dense Component Shards**: Attention and shared expert tensors must be verified for resident RAM loading.
3. **MoE Expert Shards**: All 19,456 routed expert tensors across 38 shards must be present. A missing or truncated shard results in immediate `INCOMPLETE` state.
4. **Header Validation**: Shard files are verified by reading the Safetensors JSON header (first 8 bytes for length, followed by metadata JSON) without loading multi-gigabyte tensors into memory.

---

## 4. Licensing and Upstream Provenance

- **Base Architecture**: GLM-5.2 by Zhipu AI (Z.ai).
- **Base License**: Permissive Open Weights (subject to Zhipu AI Model License Agreement).
- **Quantization & Distribution**: Publicly hosted on Hugging Face Hub under open research terms.
- **Git Tracking Policy**: In accordance with project non-negotiable rules, **no model weight files (`.safetensors`, `.bin`, `.pt`, `.gguf`) will ever be committed to the Git repository**. Weight management is managed purely through automated manifests and downloaders.
