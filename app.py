import os
import json
import re
import requests
import pdfplumber
import pytesseract
import platform  # <--- NOVA IMPORTAÇÃO IMPORTANTE
from pdf2image import convert_from_path
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename
from collections import Counter

# --- CONFIGURAÇÃO ---
app = Flask(__name__)

# --- CONFIGURAÇÃO INTELIGENTE (DETECTA WINDOWS OU LINUX/CPANEL) ---
sistema_operacional = platform.system()

if sistema_operacional == "Windows":
    # Configurações do seu PC Local
    print(">>> Ambiente detectado: WINDOWS (Local)")
    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    poppler_dir = r"C:\poppler\Library\bin"
    
    # Adiciona Poppler ao PATH se não estiver
    if os.path.exists(poppler_dir) and poppler_dir not in os.environ.get('PATH', ''):
        os.environ['PATH'] += ";" + poppler_dir

else:
    # Configurações do Servidor Linux (cPanel)
    print(">>> Ambiente detectado: LINUX (Servidor)")
    # No Linux, o Tesseract geralmente está no caminho padrão
    pytesseract.pytesseract.tesseract_cmd = '/usr/bin/tesseract'
    # O Poppler já costuma vir instalado no sistema, não precisa de PATH extra

# Chave Groq 
# (Mantenha sua chave segura. Cole-a abaixo novamente)
GROQ_API_KEY = "COLE_SUA_CHAVE_GROQ_AQUI" 

UPLOAD_FOLDER = 'uploads'
REPORT_FOLDER = 'relatorios'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPORT_FOLDER, exist_ok=True)

# ---------------- LEITURA (OCR) ----------------
def extrair_texto(caminho_pdf):
    print(f"Lendo PDF: {caminho_pdf}")
    texto = ""
    try:
        # PSM 4: Assume texto de coluna única (ideal para RGI)
        paginas = convert_from_path(caminho_pdf, 300)
        for img in paginas:
            texto += pytesseract.image_to_string(img, lang='por', config='--psm 4') + "\n"
    except Exception as e:
        print(f"Erro OCR: {e}")
        return ""
    return texto

# ---------------- IA (GROQ) ----------------
def analisar_com_ia(texto):
    # Verifica se a chave é válida (não é o placeholder)
    if not GROQ_API_KEY or "COLE_SUA" in GROQ_API_KEY: 
        return None
        
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        # Enviamos apenas o começo e o fim do texto para a IA não se perder
        resumo_texto = texto[:5000] + "\n...[MEIO DO DOCUMENTO]...\n" + texto[-3000:]
        prompt = f"Extraia JSON exato: Cartório (ex: 5º Ofício), Data da Certidão (ex: 02/10/2024), Matrícula, Endereço, Proprietários, Ônus. Texto: {resumo_texto}"
        
        resp = requests.post(url, headers=headers, json={"model": "llama3-70b-8192", "messages": [{"role": "user", "content": prompt}]}, timeout=30)
        return resp.json()['choices'][0]['message']['content'] if resp.status_code == 200 else None
    except: return None

# ---------------- LÓGICA DE CARTORÁRIO (REGEX FINAL) ----------------
def analisar_inteligencia_registral(texto):
    print(">>> Iniciando Análise Lógica (Cartório e Data Reais)...")
    
    texto_limpo = re.sub(r'\s+', ' ', texto).upper()
    
    # 1. CARTÓRIO (Busca no cabeçalho - primeiros 1000 caracteres)
    cabecalho = texto_limpo[:1000]
    cartorio = "Registro de Imóveis - RJ" # Padrão
    
    # Procura "Xº OFÍCIO" ou "Xº REGISTRO"
    match_cartorio = re.search(r'(\d+)[º°ª]\s*(?:OF[ÍI]CIO|REGISTRO)', cabecalho)
    if match_cartorio:
        numero = match_cartorio.group(1)
        cartorio = f"{numero}º Ofício de Registro de Imóveis - RJ"
    elif "9º OFÍCIO" in cabecalho: cartorio = "9º Ofício de Registro de Imóveis"
    elif "5º OFÍCIO" in cabecalho: cartorio = "5º Ofício de Registro de Imóveis"

    # 2. DATA DA CERTIDÃO (Busca no rodapé - últimos 2000 caracteres)
    rodape = texto_limpo[-2000:]
    data_certidao = datetime.now().strftime('%d/%m/%Y') # Default hoje
    
    # Procura padrão "RIO DE JANEIRO, 02 DE OUTUBRO DE 2024" ou "EM 01/10/2024"
    match_data_extenso = re.search(r'RIO DE JANEIRO,?\s*(\d{1,2})\s*DE\s*([A-ZÇ]+)\s*DE\s*(\d{4})', rodape)
    match_data_simples = re.search(r'(\d{2}/\d{2}/\d{4})', rodape)
    
    if match_data_extenso:
        dia, mes, ano = match_data_extenso.groups()
        data_certidao = f"{dia} de {mes} de {ano}"
    elif match_data_simples:
        # Pega a última data encontrada no documento (geralmente é a da assinatura)
        todas_datas = re.findall(r'(\d{2}/\d{2}/\d{4})', rodape)
        if todas_datas:
            data_certidao = todas_datas[-1]

    # 3. MATRÍCULA (Lógica de contagem de repetições R.X/Num)
    matricula = "Não identificada"
    candidatos_matricula = re.findall(r'[R|AV]\.\d+/(\d+[\.\d]*)', texto_limpo)
    if candidatos_matricula:
        matricula = Counter(candidatos_matricula).most_common(1)[0][0].replace('.', '')
    else:
        match_topo = re.search(r'MATR[ÍI]CULA.*?(\d{4,7})', texto_limpo)
        if match_topo: matricula = match_topo.group(1)

    # 4. PROPRIETÁRIOS
    proprietarios = []
    matches_herdeiros = re.findall(r'(?:PARTILHADO [ÀA]|ADJUDICADO [ÀA]|TRANSFE[RI]+U PARA)\s*(.*?)(?:,|;|\.|\n)', texto_limpo)
    for bloco in matches_herdeiros:
        nomes_sujos = re.split(r'\d+\)', bloco)
        for n in nomes_sujos:
            n = re.sub(r'CPF.*?[\d\.\-]+', '', n).replace('BRASILEIRO', '').replace('SOLTEIRO', '').strip()
            if len(n) > 5 and "MATRÍCULA" not in n: proprietarios.append({"nome": n})
    
    if not proprietarios:
        match_prop = re.search(r'(?:PROPRIET[ÁA]RIO|ADQUIRENTE).*?[-–]\s*(.*?)(?:;|\.|DO QUE)', texto_limpo)
        if match_prop: proprietarios.append({"nome": match_prop.group(1).strip()})
    
    proprietarios = list({p['nome']: p for p in proprietarios}.values()) # Remove duplicatas

    # 5. ENDEREÇO
    endereco = "Endereço não localizado"
    match_end = re.search(r'(?:IM[ÓO]VEL|PR[ÉE]DIO).*?((?:RUA|AV|AVENIDA|ALAMEDA).*?)(?:;|\.|$)', texto_limpo)
    if match_end: endereco = match_end.group(1).strip()

    # 6. ÔNUS E DIAGNÓSTICO
    onus_encontrados = []
    termos_perigo = ["PENHORA", "HIPOTECA", "INDISPONIBILIDADE", "ARRESTO", "AÇÃO DE EXECUÇÃO"]
    eh_negativa = "NÃO CONSTAM" in rodape or "INEXISTEM" in rodape
    
    for termo in termos_perigo:
        if termo in texto_limpo:
            idx = texto_limpo.find(termo)
            contexto = texto_limpo[max(0, idx-50):min(len(texto_limpo), idx+50)]
            if "CANCELAD" in contexto or "BAIXA" in contexto: continue
            if eh_negativa and termo in ["AÇÕES REAIS", "REIPERSECUTÓRIAS"]: continue
            if not eh_negativa: onus_encontrados.append(termo)

    diagnostico = "Pode Vender (Livre)"
    if onus_encontrados: diagnostico = "Atenção (Possíveis Ônus)"
    elif not onus_encontrados: onus_encontrados = ["Nada consta (Livre de Ônus Reais)"]

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
    if 'file' not in request.files: return jsonify({"error": "Erro arquivo"}), 400
    file = request.files['file']
    filename = secure_filename(file.filename)
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)

    texto = extrair_texto(path)
    
    # Tenta IA (se tiver chave e não for placeholder) ou vai para Lógica Registral
    dados = analisar_com_ia(texto)
    if dados:
        try:
            dados = json.loads(dados.replace('```json', '').replace('```', ''))
        except:
            dados = analisar_inteligencia_registral(texto)
    else:
        dados = analisar_inteligencia_registral(texto)

    with open(os.path.join(REPORT_FOLDER, "analise.txt"), "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)

    return jsonify({"relatorio": dados, "arquivo_relatorio": "analise.txt"})

@app.route('/download/<filename>')
def download_file(filename):
    return send_from_directory(REPORT_FOLDER, filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)