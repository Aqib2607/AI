# Local Development Setup Guide

This guide details setting up the local Windows workstation for repository development, test execution, configuration management, and synthetic validation.

---

## 1. Prerequisites

- **Host OS**: Windows 10/11 (64-bit)
- **Python**: Python 3.10+ (64-bit)
- **Git**: Git 2.40+
- **Google Account**: Access to Google Drive (with $\ge 380\text{ GB}$ storage quota) and Google Colab
- **Hugging Face Account**: (Optional) Personal User Access Token for authenticated Hugging Face downloads

---

## 2. Workspace Setup

```powershell
# 1. Clone the repository
git clone https://github.com/<your-org>/glm52-drive-runtime.git D:\AI\glm52-drive-runtime
cd D:\AI\glm52-drive-runtime

# 2. Create and activate Python virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install core and test dependencies
pip install --upgrade pip
pip install -r requirements.txt

# 4. Initialize environment file from template
cp .env.example .env
```

---

## 3. Environment Variable Configuration

Edit `.env` to configure your Hugging Face token and storage paths:

```ini
# Hugging Face Access Token
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx

# Model Repository Target
MODEL_REPO=mastouri/GLM-5.2-colibri-int4-g64-with-int8-mtp

# Colibri Server Security
COLI_API_KEY=your_generated_secret_key
COLI_HOST=127.0.0.1
COLI_PORT=8000
```

---

## 4. Running Local Automated Tests

To ensure configuration integrity and tool functionality without downloading real weights:

```powershell
# Execute the full pytest test suite
pytest tests/ -v

# Run local environment check
python scripts/environment_check.py --local
```
