import os
import json
import re
import requests
import pdfplumber
import pytesseract
import platform
from pdf2image import convert_from_path
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename
from collections import Counter
from flask_cors import CORS

# --- CONFIGURAÇÃO ---
app = Flask(__name__)
CORS(app)  # Habilita CORS (útil para testes via browser)

# --- DETECÇÃO DE AMBIENTE (Windows vs Linux) ---
sistema_operacional = platform.system()

if sistema_operacional == "Windows":
    print(">>> Ambiente detectado: WINDOWS (Local)")
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    # Ajuste abaixo para o caminho real do poppler no seu PC se necessário
    poppler_dir = r"C:\poppler\Library\bin"
    if os.path.exists(poppler_dir) and poppler_dir not in os.environ.get('PATH', ''):
        os.environ['PATH'] += ";" + poppler_dir
    POPPLER_PATH = poppler_dir
else:
    print(">>> Ambiente detectado: LINUX (Servidor)")
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'  # padrão Linux
    POPPLER_PATH = None  # No Linux, normalmente não precisa informar o caminho

# --- CHAVE GROQ (LEIA DE VARIÁVEL DE AMBIENTE, COM FALLBACK SE VOCÊ JÁ A PASSOU) ---
# É fortemente recomendado setar GROQ_API_KEY como variável de ambiente no Render:
# Ex.: GROQ_API_KEY = 'gsk_...'
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "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")

# --- PASTAS ---
UPLOAD_FOLDER = 'uploads'
REPORT_FOLDER = 'relatorios'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPORT_FOLDER, exist_ok=True)

# ---------------- LEITURA (TENTA PDFPLUMBER ANTES DO OCR) ----------------
def extrair_texto(caminho_pdf):
    """
    Tenta extrair texto diretamente do PDF (pdfplumber). Se vazio ou pouca coisa,
    faz OCR página-a-página com pytesseract + pdf2image.
    """
    print(f"[INFO] Lendo PDF: {caminho_pdf}")
    texto = ""

    # 1) Tenta pdfplumber (funciona quando o PDF já tem texto)
    try:
        with pdfplumber.open(caminho_pdf) as pdf:
            paginas = []
            for p in pdf.pages:
                t = p.extract_text() or ""
                paginas.append(t)
            texto_plumber = "\n".join(paginas).strip()
            if texto_plumber and len(texto_plumber) > 50:
                print("[INFO] Texto extraído via pdfplumber (sem OCR).")
                return texto_plumber
    except Exception as e:
        print(f"[WARN] pdfplumber falhou: {e}")

    # 2) Fallback para OCR com pdf2image + pytesseract
    try:
        print("[INFO] Usando OCR (pytesseract) — isso pode demorar...")
        # DPI 300 costuma dar boa qualidade para OCR
        if POPPLER_PATH and sistema_operacional == "Windows":
            imagens = convert_from_path(caminho_pdf, dpi=300, poppler_path=POPPLER_PATH)
        else:
            imagens = convert_from_path(caminho_pdf, dpi=300)
        partes = []
        for img in imagens:
            # '--psm 4' funciona bem para textos com colunas simples; ajuste se necessário
            txt = pytesseract.image_to_string(img, lang='por', config='--psm 4')
            partes.append(txt)
        texto = "\n".join(partes)
        print(f"[INFO] OCR finalizado. {len(partes)} páginas processadas.")
    except Exception as e:
        print(f"[ERRO] Falha no OCR: {e}")
        return ""

    return texto

# ---------------- IA (GROQ) ----------------
def analisar_com_ia(texto):
    """
    Tenta enviar um prompt para a API Groq (OpenAI-compatible endpoint).
    Retorna string JSON produzida pela IA (ou None em caso de falha).
    """
    if not GROQ_API_KEY or GROQ_API_KEY.strip() == "":
        print("[INFO] Sem chave GROQ configurada.")
        return None

    try:
        # Endpoint compatível OpenAI (fornecido anteriormente); se necessário ajuste ao endpoint real da sua conta Groq
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json"
        }

        # Monta um prompt robusto e com limite de tamanho
        resumo_texto = (texto[:6000] + "\n...[MEIO DO DOCUMENTO]...\n" + texto[-3000:]) if len(texto) > 9000 else texto
        prompt = (
            "Você é um assistente especializado em matrículas e certidões imobiliárias do Rio de Janeiro. "
            "Extraia um JSON com as chaves: Cartório, Matrícula, Data da Certidão, Endereço, Proprietários (lista com nome e CPF se houver), Ônus (lista), Diagnóstico. "
            "Retorne apenas JSON válido. Aqui está o texto:\n\n" + resumo_texto
        )

        payload = {
            "model": "llama3-70b-8192",  # se esse modelo não existir na sua conta, ajuste conforme disponível
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1200,
            "temperature": 0.0
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=40)
        if resp.status_code != 200:
            print(f"[WARN] Groq retornou status {resp.status_code}: {resp.text}")
            return None

        j = resp.json()
        # Tenta navegar por formatos diferentes (compatível com OpenAI-like)
        text_resp = None
        if isinstance(j, dict):
            # OpenAI-like
            try:
                text_resp = j['choices'][0]['message']['content']
            except Exception:
                # Algumas APIs retornam em 'choices'[0]['text']
                try:
                    text_resp = j['choices'][0].get('text')
                except Exception:
                    text_resp = None

        if not text_resp:
            print("[WARN] Resposta da IA não contém conteúdo esperado.")
            return None

        # Retorna a string — quem chama deve tentar json.loads
        return text_resp.strip()

    except Exception as e:
        print(f"[ERRO] Falha ao chamar API Groq: {e}")
        return None

# ---------------- LÓGICA DE CARTORÁRIO (REGEX) ----------------
def analisar_inteligencia_registral(texto):
    print(">>> Iniciando Análise Lógica (Regex)...")
    texto_limpo = re.sub(r'\s+', ' ', texto).upper()

    # CARTÓRIO
    cabecalho = texto_limpo[:1000]
    cartorio = "Registro de Imóveis - RJ"
    match_cartorio = re.search(r'(\d+)[º°ª]\s*(?:OF[ÍI]CIO|REGISTRO)', cabecalho)
    if match_cartorio:
        numero = match_cartorio.group(1)
        cartorio = f"{numero}º Ofício de Registro de Imóveis - RJ"
    elif "5º OFÍCIO" in cabecalho:
        cartorio = "5º Ofício de Registro de Imóveis - RJ"
    elif "9º OFÍCIO" in cabecalho:
        cartorio = "9º Ofício de Registro de Imóveis - RJ"

    # DATA DA CERTIDÃO
    rodape = texto_limpo[-2000:]
    data_certidao = datetime.now().strftime('%d/%m/%Y')
    match_data_extenso = re.search(r'RIO DE JANEIRO,?\s*(\d{1,2})\s*DE\s*([A-ZÇ]+)\s*DE\s*(\d{4})', rodape)
    match_data_simples = re.findall(r'(\d{2}/\d{2}/\d{4})', rodape)
    if match_data_extenso:
        dia, mes, ano = match_data_extenso.groups()
        data_certidao = f"{dia} de {mes} de {ano}"
    elif match_data_simples:
        data_certidao = match_data_simples[-1]

    # MATRÍCULA
    matricula = "Não identificada"
    candidatos_matricula = re.findall(r'[RAV]\.?(\d{4,7})', texto_limpo)
    if candidatos_matricula:
        matricula = Counter(candidatos_matricula).most_common(1)[0][0]
    else:
        match_topo = re.search(r'MATR[ÍI]CULA.*?(\d{4,7})', texto_limpo)
        if match_topo:
            matricula = match_topo.group(1)

    # PROPRIETÁRIOS
    proprietarios = []
    # Busca padrões de "NOME, CPF nnn.nnn.nnn-nn"
    matches_cpf = re.findall(r'([A-Z\s\.\-]{6,200}?)\s+CPF[:\s]*([\d\.\-]{11,14})', texto_limpo)
    for nome, cpf in matches_cpf:
        n = nome.strip().title()
        proprietarios.append({"nome": n, "cpf": cpf})

    if not proprietarios:
        # tentativa genérica
        generic_matches = re.findall(r'(PROPRIET[ÁA]RIO|ADQUIRENTE|PROPRIETARIOS?).{0,40}([A-Z][A-Z\s,]{4,200})', texto_limpo)
        for gm in generic_matches:
            n = re.sub(r'CPF.*', '', gm[1]).strip().title()
            if len(n) > 4:
                proprietarios.append({"nome": n})

    # ENDEREÇO
    endereco = "Endereço não localizado"
    match_end = re.search(r'(?:ENDEREÇOS?|ENDEREÇO|LOCALIZADO EM|SITUADO EM).*?((?:RUA|AVENIDA|AV|TRAVESSA|ALAMEDA|PRAÇA).{1,200}?)\.', texto_limpo)
    if match_end:
        endereco = match_end.group(1).strip().title()
    else:
        match_end2 = re.search(r'(?:AV\.|RUA|AVENIDA|PRAÇA|TRAVESSA)\s+[A-Z0-9\.\-\/\s]{4,200}', texto_limpo)
        if match_end2:
            endereco = match_end2.group(0).strip().title()

    # ÔNUS
    termos_perigo = ["PENHORA", "HIPOTECA", "INDISPONIBILIDADE", "ARRESTO", "ARRESTOS", "AÇÃO DE EXECUÇÃO", "EXECUÇÃO"]
    onus_encontrados = []
    for termo in termos_perigo:
        if termo in texto_limpo:
            onus_encontrados.append(termo)

    diagnostico = "Pode Vender (Livre)" if not onus_encontrados else "Atenção (Possíveis Ônus)"

    if not onus_encontrados:
        onus_encontrados = ["Nada consta (Livre de Ônus Reais)"]

    return {
        "Cartório": cartorio,
        "Matrícula": matricula,
        "Data da Busca": datetime.now().strftime('%d/%m/%Y'),
        "Data da Certidão": data_certidao,
        "Endereço": endereco,
        "Proprietários": proprietarios if proprietarios else [{"nome": "Verificar R.1 na imagem"}],
        "Ônus Reais": onus_encontrados,
        "Diagnóstico": diagnostico
    }

# ---------------- ROTAS ----------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "Erro: arquivo não enviado"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "Erro: nome do arquivo inválido"}), 400

    filename = secure_filename(file.filename)
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)
    print(f"[INFO] Arquivo salvo em: {path}")

    # Extrai texto (pdfplumber -> OCR)
    texto = extrair_texto(path)
    if not texto or len(texto.strip()) < 20:
        print("[WARN] Texto extraído muito curto ou vazio; retornando análise padrão.")
        dados = analisar_inteligencia_registral(texto)
    else:
        # Tenta IA primeiro
        resposta_ia = analisar_com_ia(texto)
        if resposta_ia:
            try:
                # Remove possíveis blocos de código e tenta carregar JSON
                cleaned = resposta_ia.strip().replace('```json', '').replace('```', '').strip()
                dados = json.loads(cleaned)
                print("[INFO] Dados extraídos via IA (JSON).")
            except Exception as e:
                print(f"[WARN] IA retornou mas não é JSON válido: {e}")
                dados = analisar_inteligencia_registral(texto)
        else:
            dados = analisar_inteligencia_registral(texto)

    # Salva relatório
    nome_relatorio = f"analise_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    caminho_relatorio = os.path.join(REPORT_FOLDER, nome_relatorio)
    with open(caminho_relatorio, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)

    return jsonify({"relatorio": dados, "arquivo_relatorio": nome_relatorio})

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(REPORT_FOLDER, filename, as_attachment=True)

# ---------------- RUN ----------------
if __name__ == '__main__':
    # Porta e host compatíveis com Render e execução local
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "False").lower() in ("1", "true", "yes")
    app.run(host='0.0.0.0', port=port, debug=debug)
