# Runtime Startup, Health Checks & Inference

---

## 1. Runtime Startup Sequence

The runtime launcher script (`scripts/runtime_launcher.py`) automates the full pre-flight verification and execution pipeline:

```
[Step 1: Check Environment]   -> Validates Python, GCC, OpenMP, RAM >= 9.9 GB
[Step 2: Check Google Drive]  -> Verifies mount status and storage health
[Step 3: Verify Model Shards] -> Reads Safetensors headers (must be READY)
[Step 4: Verify Colibri Build]-> Checks executable binary and compiler flags
[Step 5: Launch Engine/API]   -> Starts background worker & initiates health probe
```

---

## 2. Deterministic Validation Prompts

To verify model correctness without hallucination or infinite loops:

1. **Sentence Constraint Test**:
   - Prompt: `"Hello. Respond with exactly one sentence."`
   - Expected Output: A single grammatically complete greeting sentence ending with punctuation.
2. **Technical Explanation Test**:
   - Prompt: `"Explain recursion in simple terms."`
   - Expected Output: Concise 2–3 sentence explanation emphasizing self-reference and base case.
3. **Code Generation Test**:
   - Prompt: `"Write a Python function that reverses a string."`
   - Expected Output: Valid `def reverse_string(s: str) -> str: return s[::-1]`.
4. **Structured JSON Output Test**:
   - Prompt: `"Return a JSON object with the keys name and status."`
   - Expected Output: Valid parseable JSON object `{"name": "...", "status": "..."}`.
