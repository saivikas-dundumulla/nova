#!/usr/bin/env bash
# Azure App Service (Linux) startup: run the FastAPI backend and the Streamlit UI
# in a single container. Streamlit is public (port 8501, routed via WEBSITES_PORT);
# FastAPI is internal-only on 127.0.0.1:8000 and reached by the UI over localhost.
set -e

# Dependencies are shipped by CI into .python_packages (see .github/workflows/ci-cd.yml),
# so make them importable regardless of whether an Oryx build ran.
export PYTHONPATH="/home/site/wwwroot/.python_packages/lib/site-packages:${PYTHONPATH:-}"

# /home is the ONLY persistent path on App Service — keep the JSON store + logs there.
mkdir -p /home/data/conversations /home/data/logs

# Backend (internal). Single worker so the JSON store's in-process lock is effective.
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --workers 1 &

# Frontend (public). Bind to 8501; set WEBSITES_PORT=8501 in App Settings so Azure routes here.
exec python -m streamlit run app/ui/streamlit_app.py \
  --server.port 8501 \
  --server.address 0.0.0.0 \
  --server.headless true \
  --server.enableCORS false \
  --server.enableXsrfProtection false
