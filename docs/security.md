# Security, Secrets & Credential Management Policy

---

## 1. Zero Credential & Zero Weight Policy

This project strictly enforces:
1. **No Credentials in Git**: `.env`, API keys, Hugging Face tokens (`HF_TOKEN`), and private certificates are barred by `.gitignore` and verified by automated security tests.
2. **No Model Weights in Git**: Binary tensors (`.safetensors`, `.gguf`, `.bin`, `.pt`) are completely excluded.
3. **Synthetic Test Fixtures**: All automated tests generate lightweight synthetic JSON headers and mock binary structures in isolated temporary directories.

---

## 2. API Security Architecture

- **Localhost Default Binding**: The REST API gateway binds to `127.0.0.1:8000` by default to prevent exposure to untrusted networks.
- **Bearer Token Authentication**: Every non-health endpoint requires `Authorization: Bearer <COLI_API_KEY>`.
- **CORS Protection**: Cross-Origin Resource Sharing (CORS) is restricted to configured origins in `config/runtime.example.yaml`.

---

## 3. Google Drive Scope & Access Isolation

- **Scoped Access**: Scripts operate exclusively within `/content/drive/MyDrive/AI/GLM-5.2/` and never inspect, modify, or list personal user folders outside the project scope.
- **Atomic Operations**: All shard downloads write to `.tmp` files and are renamed only after full byte-length verification to prevent partial or damaged files from corrupting runtime execution.
