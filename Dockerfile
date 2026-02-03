# Usa uma imagem leve do Python no Linux
FROM python:3.9-slim

# INSTALA OS PACOTES DO SISTEMA (Tesseract e Poppler)
# É aqui que a mágica acontece. No cPanel isso era proibido.
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-por \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Define a pasta de trabalho
WORKDIR /app

# Copia seus arquivos para o servidor
COPY . .

# Instala as bibliotecas do Python (Flask, etc)
RUN pip install --no-cache-dir -r requirements.txt

# Expõe a porta que o Render usa
EXPOSE 10000

# Comando para rodar o site usando Gunicorn (mais robusto que 'python app.py')
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:10000", "--timeout", "120"]