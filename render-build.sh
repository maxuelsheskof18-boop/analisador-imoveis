#!/usr/bin/env bash
# Instala o Tesseract e o Poppler no Linux do Render
apt-get update && apt-get install -y tesseract-ocr tesseract-ocr-por poppler-utils
# Instala as bibliotecas do Python
pip install -r requirements.txt
