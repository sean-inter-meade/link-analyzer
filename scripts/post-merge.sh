#!/bin/bash
set -e

uv pip install --target .pythonlibs/lib/python3.11/site-packages -r requirements.txt

if ! python -c "import en_core_web_sm" 2>/dev/null; then
  echo "Installing en_core_web_sm spaCy model..."
  uv pip install --target .pythonlibs/lib/python3.11/site-packages \
    https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl
else
  echo "en_core_web_sm already installed."
fi
