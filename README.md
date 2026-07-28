# Product Page Creator — Local Edition (Cloud-Ready)

Local-first pipeline using **Ollama** on your laptop, now with a production path for managed cloud deployment.

## Models (recommended)

```powershell
ollama pull qwen2.5:7b-instruct
ollama pull qwen2.5vl:7b
```

## Quick start

**Double-click `run.bat`** in this folder.

Or manually:

```powershell
cd local-edition
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
playwright install chromium
cd frontend && npm install && cd ..
copy .env.example .env
.\run.bat
```

- UI: http://localhost:5174
- API: http://localhost:8001
- Worker: background process started by `run.bat`

## Private login + cloud mode

Set in `.env`:

- `AUTH_ENABLED=true`
- `ADMIN_EMAIL=...`
- `ADMIN_PASSWORD=...`
- `AUTH_JWT_SECRET=...`

Then restart API + worker. The UI will require sign-in.

## Deployment

Use:

- [DEPLOYMENT.md](DEPLOYMENT.md) for managed hosting setup
- [OPERATIONS.md](OPERATIONS.md) for backups, diagnostics, and incident checklist
- [STAGING_PROD_WORKFLOW.md](STAGING_PROD_WORKFLOW.md) for ongoing development flow after go-live

`render.yaml` is included for Render blueprint deployments.
Use `.env.production.example` as the production env template.

## Brand tone

Add Hebrew product copy examples to `brand-examples/` (`.docx`, `.txt`, `.md`, `.html`).
Edit `brand-examples/style-guide.txt` or `style-guide.docx` for voice rules.

## Training package export

Open the **Training** tab in the local app to build a style-training package:

1. Paste the full path to your existing Word product-copy folder.
2. Click **Scan Word folder**.
3. Review usable, duplicate, and issue files.
4. Click **Build dataset.jsonl**.
5. Click **Export Kaggle/Colab package**.

The ZIP is created under `data/training/` and includes:

- `train.jsonl`
- `validation.jsonl`
- `dataset.jsonl`
- `train_unsloth_colab.ipynb`
- `training-config.json`
- `README-training.md`

This is Phase 1 only: it prepares the corpus and export package. Training/importing
the resulting LoRA model is Phase 2.

## AMD GPU tuning

See [SETUP-AMD.md](SETUP-AMD.md) for Radeon 890M acceleration.

## vs parent folder

The parent `Product page creator` folder supports cloud AI (Gemini, Groq, etc.).
This `local-edition` subfolder is **Ollama-only** — no API keys required.
