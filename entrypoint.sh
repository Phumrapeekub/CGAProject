#!/bin/bash
echo "=== Starting CGA System on Hugging Face Spaces (Supabase Cloud DB) ==="
exec gunicorn -b 0.0.0.0:7860 app:app --timeout 120 --workers 2
