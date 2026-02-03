# app_gemini_new.py
"""
Flask API para analisar certidões com Google GenAI (google-genai).
Instalação:
  py -m pip install google-genai flask pdfplumber pytesseract pdf2image pillow
Defina a chave com a variável de ambiente GOOGLE_API_KEY (recomendado).
"""

import os
import re
import json
from datetime import datetime
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename

import pdfplumber
try:
    import pytesseract
    from pdf2image import convert_from_path
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

from google import genai

# ---------------- GenAI client (compatível com variações da lib) ----------------

API_KEY = os.environ.get("GOOGLE_API_KEY") or None

# Tentamos suportar diferentes versões da lib:
# - versões antigas tinham genai.configure(...) e genai.Model.get(...)
# - versões novas usam genai.Client() com métodos como generate_text(...)
genai_client = None
use_old_api = False

# Detecta e configura
if hasattr(genai, "configure"):
    # API antiga
    if API_KEY:
        try:
            genai.configure(api_key=API_KEY)
            use_old_api = True
        except Exception:
            # fallback para continuar
            use_old_api = True
    else:
        use_old_api = True
else:
    # API nova: genai.Client
    try:
        # some versions accept api_key on constructor, others read env var
        try:
            genai_client = genai.Client(api_key=API_KEY) if API_KEY else genai.Client()
        except TypeError:
            # fallback: constructor sem argumento (lê env)
            genai_client = genai.Client()
    except Exception as e:
        genai_client = None

def _extract_response_text(resp):
    """Extrai o conteúdo de texto de várias formas possíveis de resposta."""
    if resp is None:
        return ""
    if hasattr(resp, "text"):
        return getattr(resp, "text")
    if isinstance(resp, dict):
        if "candidates" in resp and isinstance(resp["candidates"], (list, tuple)) and resp["candidates"]:
            c = resp["candidates"][0]
            if isinstance(c, dict) and "content" in c:
                return c["content"]
            return str(c)
        if "output" in resp:
            out = resp["output"]
            if isinstance(out, (list, tuple)):
                parts = []
                for o in out:
                    if isinstance(o, dict):
                        parts.append(o.get("content", "") or o.get("text", ""))
                    else:
                        parts.append(str(o))
                return "\n".join(p for p in parts if p)
            return str(out)
    if hasattr(resp, "output"):
        out = getattr(resp, "output")
        try:
            parts = []
            for o in out:
                if isinstance(o, dict):
                    parts.append(o.get("content", "") or o.get("text", ""))
                else:
                    parts.append(str(o))
            return "\n".join(p for p in parts if p)
        except Exception:
            return str(out)
    return str(resp)

def call_gemini(prompt_text):
    """
    Chama o modelo usando a API disponível:
     - Se 'use_old_api' for True, tenta genai.Model.get(...).generate_text(...) (compatibilidade).
     - Senão, tenta genai_client.generate_text(...)
    Retorna string bruta da resposta (texto).
    """
    if use_old_api:
        try:
            model = genai.Model.get("models/text-bison-001") if hasattr(genai.Model, "get") else genai.Model("models/text-bison-001")
            if hasattr(model, "generate_text"):
                resp = model.generate_text(prompt_text, temperature=0.2, max_tokens=1500)
                return _extract_response_text(resp)
            if hasattr(model, "generate"):
                resp = model.generate(prompt_text)
                return _extract_response_text(resp)
        except Exception:
            pass

    if genai_client is not None:
        try:
            model_names = ["models/text-bison-001", "text-bison-001", "text-bison"]
            last_exc = None
            for model_name in model_names:
                try:
                    resp = genai_client.generate_text(model=model_name, input=prompt_text,
                                                      temperature=0.2, max_output_tokens=1500)
                    return _extract_response_text(resp)
                except Exception as e:
                    last_exc = e
                    continue
            raise last_exc
        except Exception as e_new:
            raise RuntimeError(f"Erro ao chamar GenAI (nova API): {e_new}")

    raise RuntimeError("Nenhuma API GenAI compatível encontrada (nenhum client inicializado). Verifique a biblioteca 'google-genai' ou 'google.generativeai'.")

# ---------------- Resto do código ----------------

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
REPORT_FOLDER = "relatorios"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPORT_FOLDER, exist_ok=True)

def normalize_text(t: str) -> str:
    if not t:
        return ""
    txt = t.replace('\r\n', '\n').replace('\r', '\n')
    txt = re.sub(r'\t+', ' ', txt)
    txt = re.sub(r'[ \u00A0]+', ' ', txt)
    txt = re.sub(r'\n{3,}', '\n\n', txt)
    return txt.strip()

def extract_text_pdf(path):
    try:
        with pdfplumber.open(path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception:
        return ""

def ocr_pdf(path, dpi=300):
    if not OCR_AVAILABLE:
        return ""
    pages = convert_from_path(path, dpi=dpi)
    text = ""
    for img in pages:
        text += pytesseract.image_to_string(img, lang="por") + "\n"
    return text

def extract_relevant_text(text, max_chars=70000, context_lines=3):
    if not text:
        return ""
    text = normalize_text(text)
    if len(text) <= max_chars:
        return text
    lines = text.splitlines()
    keywords = ['matrícula','matricula','propriet','ônus','onus','cartório','cartorio','data','endereço','endereco','fração','fracao','cpf','proprietário','proprietario']
    indices = set()
    for i, ln in enumerate(lines):
        low = ln.lower()
        if any(k in low for k in keywords):
            for j in range(max(0, i - context_lines), min(len(lines), i + context_lines + 1)):
                indices.add(j)
    top_chunk = "\n".join(lines[:120])
    bottom_chunk = "\n".join(lines[-80:])
    selected_lines = [lines[i] for i in sorted(indices)]
    reduced = "\n".join([top_chunk, "\n".join(selected_lines), bottom_chunk])
    if len(reduced) > max_chars:
        return reduced[:max_chars]
    return reduced

def build_prompt(text):
    return f"""
Analise a matrícula de imóvel abaixo e retorne um JSON estrito com os campos:
- identificacao: {{matricula, cartorio, endereco, data_certidao}}
- proprietarios: lista de {{nome, porcentagem, estado_civil}}
- diagnostico: {{pode_vender (bool), assinatura_conjuge (bool), motivo_venda (string)}}
- onus: lista de strings (ou ["Sem ônus identificados"])
- alerta_principal: string

Responda SOMENTE com o JSON (nenhum texto extra).
TEXTO:
{text}
"""

def parse_json_response(text):
    try:
        return json.loads(text)
    except Exception as e:
        raise ValueError(f"Erro ao parsear JSON da resposta: {e}\nResposta bruta: {text}")

def format_report(data):
    props = ", ".join([f"{p.get('nome','N/A')} ({p.get('porcentagem','N/A')})" for p in data.get('proprietarios', [])]) or "Não encontrado"
    diag = data.get('diagnostico', {})
    status = "✅ Pode vender" if diag.get('pode_vender') else "⚠️ Precisa de mais pessoas/atenção para vender"
    conjuge = "Sim" if diag.get('assinatura_conjuge') else "Não indicado ou N/A"
    onus = ", ".join(data.get('onus', [])) or "Nenhum ônus identificado"
    alerta = data.get('alerta_principal', 'Nenhum alerta')

    return f"""
📋 RELATÓRIO DE ANÁLISE IMOBILIÁRIA

1. Identificação do Imóvel
- Matrícula: {data.get('identificacao', {}).get('matricula', 'Não encontrada')}
- Cartório: {data.get('identificacao', {}).get('cartorio', 'Não encontrado')}
- Endereço: {data.get('identificacao', {}).get('endereco', 'Não encontrado')}
- Data da Certidão: {data.get('identificacao', {}).get('data_certidao', 'Não encontrada')}

2. Proprietários
- {props}

3. Diagnóstico Rápido
- Status: {status}
- Assinatura de cônjuge: {conjuge}
- Ônus: {onus}

4. Pendências / Alertas
- {alerta}

---
Gerado automaticamente pelo Analisador Inteligente com GenAI.
"""

app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "API: POST /analyze (form-data field 'file')"

@app.route("/analyze", methods=["POST"])
def analyze():
    if "file" not in request.files:
        return jsonify({"error": "Campo 'file' ausente"}), 400
    f = request.files["file"]
    filename = secure_filename(f.filename)
    if not filename:
        return jsonify({"error": "Nome de arquivo inválido"}), 400
    path = os.path.join(UPLOAD_FOLDER, filename)
    f.save(path)

    text = extract_text_pdf(path)
    if len(text.strip()) < 200 and OCR_AVAILABLE:
        try:
            text = ocr_pdf(path)
        except Exception as e:
            return jsonify({"error": f"OCR falhou: {e}"}), 500

    text = normalize_text(text)
    text = extract_relevant_text(text)

    prompt = build_prompt(text)
    try:
        raw_response = call_gemini(prompt)
        data = parse_json_response(raw_response)
    except Exception as e:
        return jsonify({"error": str(e), "raw_response": raw_response if 'raw_response' in locals() else None}), 500

    report = format_report(data)

    out_name = f"relatorio_{os.path.splitext(filename)[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    out_path = os.path.join(REPORT_FOLDER, out_name)
    with open(out_path, "w", encoding="utf-8") as f_out:
        f_out.write(report)

    return jsonify({
        "relatorio_texto": report,
        "arquivo_relatorio": out_name,
        "dados_estruturados": data
    })

if __name__ == "__main__":
    UPLOAD_FOLDER = "uploads"
    REPORT_FOLDER = "relatorios"
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(REPORT_FOLDER, exist_ok=True)
    app.run(host="0.0.0.0", port=5000, debug=True)