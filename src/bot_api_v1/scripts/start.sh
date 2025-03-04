#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
export PYTHONPATH="$PWD/src:$PYTHONPATH"
uvicorn bot_api_v1.app.core.app:create_app --reload --host 0.0.0.0 --port 8000