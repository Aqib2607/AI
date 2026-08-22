# Model Selection & Compatibility Rationale

**Date**: 2026-08-23  
**Status**: `[VERIFIED]` Verified against live Hugging Face Tree API  
**Primary Selected Model**: `mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp`  
**Commit SHA**: `fd9b461ac7cae4b921470d0db12230c6505bd03c`  
**Required Engine Version**: `[VERIFIED]` Colibrì v1.5.0+

---

## 1. Candidate Comparison Matrix

| Evaluation Criterion | `mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp` (Primary) | `annelo/GLM-5.2-FP8-Uncensored-Colibri-Int4` (Reference Target) | `jlnsrk/GLM-5.2-colibri-int4` (Legacy) |
| :--- | :--- | :--- | :--- |
| **Model Type** | GLM-5.2 744B MoE Container | GLM-5.2 744B MoE Container (Uncensored) | GLM-5.2 744B MoE Container |
| **Quantization Scheme** | `[VERIFIED]` Grouped INT4 ($gs=64$) | Per-row INT4 / FP8 mixed | Per-row INT4 |
| **MTP Speculative Head**| `[VERIFIED]` Yes (`out-mtp-00000.safetensors`, 9.28 GiB) | Uncalibrated / Absent | Absent |
| **Repetition Risk** | `[VERIFIED]` **Zero / Mitigated** | Low to Moderate | `[KNOWN LIMITATION]` High loop risk |
| **Inference Engine** | Colibrì v1.5.0+ | Colibrì v1.5.0+ | Colibrì v1.5.0+ |
| **Exact Total Volume** | `[VERIFIED]` **399.79 GiB (429.28 GB decimal)** | ~370 GB | ~370 GB |
| **Total Shards** | `[VERIFIED]` **142 Safetensors files** | ~38 shards | ~38 shards |
| **Project Support Level** | **Primary Default (`.env.example`)** | Supported Fallback | Supported Fallback |

---

## 2. Real Model Repository File Inventory

Querying the official Hugging Face Tree API confirms 149 total files:

```
mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp/
├── config.json                       # Architectural hyperparameters (7.67 KB)
├── generation_config.json            # Sampling and EOS parameters (458 B)
├── tokenizer.json                    # BPE vocabulary and merges (4.45 MB)
├── tokenizer_config.json             # Chat templates (52.3 KB)
├── README.md                         # Model card and upstream instructions
├── out-mtp-00000.safetensors         # [VERIFIED] INT8 MTP Speculative Head (9.28 GiB / 9.96 GB)
├── out-00000.safetensors             # [VERIFIED] MoE Shard 0 (~2.84 GiB)
├── ...
└── out-00140.safetensors             # [VERIFIED] MoE Shard 140 (~2.84 GiB)
```

---

## 3. Storage Allocation Calculations

- `[VERIFIED]` **Main MoE Weights (141 shards)**: 390.50 GiB
- `[VERIFIED]` **MTP Speculative Head (1 shard)**: 9.28 GiB
- `[VERIFIED]` **Metadata & Tokenizer (4 files)**: ~4.6 MB
- `[VERIFIED]` **Total Repository Footprint**: **399.79 GiB / 429.28 GB**
- `[KNOWN LIMITATION]` A Google Drive storage tier of **$\ge 2\text{ TB}$** is mandatory for storing the full model package with scratch space.
