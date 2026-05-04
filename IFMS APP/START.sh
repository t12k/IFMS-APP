#!/bin/bash
echo "Installing dependencies..."
pip install -r requirements.txt
echo ""
echo "Starting IFMS..."
echo "Open Chrome and go to: http://localhost:8000"
echo ""
python -m uvicorn ifms.main:app --reload --port 8000
