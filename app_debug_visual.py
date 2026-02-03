#!/usr/bin/env python3
"""
set_poppler_tesseract_env.py

Verifica presença do Poppler (pdftoppm) e do Tesseract no sistema (Windows).
Ajuda a definir as variáveis de ambiente de usuário POPPLER_PATH (pasta bin do Poppler)
e TESSERACT_CMD (caminho completo para tesseract.exe) usando `setx`.

Uso:
    py set_poppler_tesseract_env.py
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

COMMON_POPPLER_PATHS = [
    r"C:\poppler-23.07.0\Library\bin",
    r"C:\poppler\Library\bin",
    r"C:\Program Files\poppler\bin",
    r"C:\Program Files (x86)\poppler\bin",
    r"C:\poppler\bin",
]
COMMON_TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files\Tesseract\tesseract.exe",
]

def is_windows():
    return os.name == 'nt' or sys.platform.startswith('win')

def which(exe_name):
    return shutil.which(exe_name)

def find_in_common(paths, file_name=None):
    found = []
    for p in paths:
        p_path = Path(p)
        if file_name:
            candidate = p_path / file_name
            if candidate.exists():
                found.append(str(candidate))
        else:
            if p_path.exists():
                found.append(str(p_path))
    return found

def setx_env_var(varname, value):
    """Set user environment variable on Windows using setx. Returns True on success."""
    try:
        # use setx (persists for current user)
        subprocess.run(["setx", varname, value], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True, None
    except subprocess.CalledProcessError as e:
        return False, e.stderr.decode(errors='ignore') if e.stderr else str(e)

def prompt_choice(options, prompt_text):
    if not options:
        return None
    print(prompt_text)
    for i, opt in enumerate(options, start=1):
        print(f"  [{i}] {opt}")
    print("  [0] Cancelar / Nenhum")
    while True:
        choice = input("Escolha um número: ").strip()
        if not choice.isdigit():
            print("Entrada inválida — digite o número da opção.")
            continue
        n = int(choice)
        if n == 0:
            return None
        if 1 <= n <= len(options):
            return options[n-1]
        print("Opção fora do intervalo.")

def main():
    print("\n=== Verificador / Configurador Poppler & Tesseract (Windows) ===\n")
    if not is_windows():
        print("Aviso: este script foi desenhado para Windows. Para macOS/Linux, configure POPPLER_PATH/TESSERACT_CMD manualmente.")
        # ainda podemos procurar executáveis no PATH
    # 1) Verificar pdftoppm no PATH
    pdftoppm_path = which("pdftoppm")
    if pdftoppm_path:
        print(f"Poppler (pdftoppm) encontrado no PATH em: {pdftoppm_path}")
        default_poppler_bin = str(Path(pdftoppm_path).parent)
    else:
        print("Poppler (pdftoppm) NÃO encontrado no PATH.")
        # procurar em caminhos comuns
        poppler_candidates = find_in_common(COMMON_POPPLER_PATHS, file_name="pdftoppm.exe")
        poppler_candidates += find_in_common(COMMON_POPPLER_PATHS)  # se pastas listadas
        poppler_candidates = list(dict.fromkeys(poppler_candidates))  # dedupe
        if poppler_candidates:
            print("Foram encontrados possíveis caminhos do Poppler:")
            chosen = prompt_choice(poppler_candidates, "Selecione qual deseja usar como POPPLER_PATH:")
            if chosen:
                # se o usuário escolheu um executável, garantir que pegamos a pasta bin
                chosen_path = chosen
                if chosen.lower().endswith(".exe"):
                    chosen_path = str(Path(chosen).parent)
                # gravar
                ok, err = setx_env_var("POPPLER_PATH", chosen_path)
                if ok:
                    print(f"Variável POPPLER_PATH definida com sucesso: {chosen_path}")
                    print("Abra um novo terminal para que a variável passe a valer.")
                else:
                    print("Falha ao definir POPPLER_PATH:", err)
            else:
                print("Nenhum caminho escolhido para Poppler.")
        else:
            print("Nenhum candidato do Poppler encontrado em caminhos comuns.")
            print("Por favor, instale o Poppler e adicione a pasta 'Library\\bin' ao PATH, ou informe o caminho manualmente.")
            resp = input("Deseja inserir manualmente o caminho para a pasta 'bin' do Poppler agora? (s/N): ").strip().lower()
            if resp == 's':
                manual = input("Cole aqui o caminho completo para a pasta bin do Poppler (ex: C:\\poppler-23.07.0\\Library\\bin): ").strip()
                if manual and Path(manual).exists():
                    ok, err = setx_env_var("POPPLER_PATH", manual)
                    if ok:
                        print(f"Variável POPPLER_PATH definida: {manual}")
                        print("Abra um novo terminal para que a variável passe a valer.")
                    else:
                        print("Falha ao definir POPPLER_PATH:", err)
                else:
                    print("Caminho inválido ou não existe. Abortando configuração do Poppler.")
    # 2) Verificar tesseract.exe
    tesseract_path = which("tesseract")
    if tesseract_path:
        print(f"\nTesseract encontrado no PATH em: {tesseract_path}")
        default_tesseract = tesseract_path
    else:
        print("\nTesseract NÃO encontrado no PATH.")
        tess_candidates = find_in_common(COMMON_TESSERACT_PATHS, file_name=None)
        # also check for existence of the exact exe locations listed
        tess_candidates = [p for p in COMMON_TESSERACT_PATHS if Path(p).exists()] + tess_candidates
        tess_candidates = list(dict.fromkeys(tess_candidates))
        if tess_candidates:
            print("Foram encontrados possíveis caminhos do Tesseract:")
            chosen = prompt_choice(tess_candidates, "Selecione o executável tesseract.exe para definir TESSERACT_CMD:")
            if chosen:
                exe = chosen
                # if selected a folder, try to find tesseract.exe inside it
                if Path(exe).is_dir():
                    maybe = Path(exe) / "tesseract.exe"
                    if maybe.exists():
                        exe = str(maybe)
                    else:
                        print("Pasta selecionada não contém tesseract.exe — abortando.")
                        exe = None
                if exe:
                    ok, err = setx_env_var("TESSERACT_CMD", exe)
                    if ok:
                        print(f"TESSERACT_CMD definida com sucesso: {exe}")
                        print("Abra um novo terminal para que a variável passe a valer.")
                    else:
                        print("Falha ao definir TESSERACT_CMD:", err)
            else:
                print("Nenhum caminho escolhido para Tesseract.")
        else:
            print("Nenhum candidato ao Tesseract encontrado em caminhos comuns.")
            resp = input("Deseja inserir manualmente o caminho para tesseract.exe agora? (s/N): ").strip().lower()
            if resp == 's':
                manual = input("Caminho completo para tesseract.exe (ex: C:\\Program Files\\Tesseract-OCR\\tesseract.exe): ").strip()
                if manual and Path(manual).exists():
                    ok, err = setx_env_var("TESSERACT_CMD", manual)
                    if ok:
                        print(f"TESSERACT_CMD definida: {manual}")
                        print("Abra um novo terminal para que a variável passe a valer.")
                    else:
                        print("Falha ao definir TESSERACT_CMD:", err)
                else:
                    print("Caminho inválido ou não existe. Abortando configuração do Tesseract.")
    # 3) Recomendações / verificação final
    print("\n=== Verificação final (apenas leitura atual do PATH/variáveis de usuário) ===")
    print("Nota: setx grava variáveis do usuário; elas ficam disponíveis em novos terminais.")
    # print current effective values (may not reflect recent setx until new shell)
    pop_env = os.environ.get("POPPLER_PATH")
    tess_env = os.environ.get("TESSERACT_CMD")
    print(f"POPPLER_PATH (no ambiente atual): {pop_env}")
    print(f"TESSERACT_CMD  (no ambiente atual): {tess_env}")
    print("\nPara testar agora (após reabrir terminal):")
    print("  - No terminal, rode: pdftoppm -v   (deve imprimir versão do poppler)")
    print("  - No terminal, rode: tesseract -v   (deve imprimir versão do tesseract)")
    print("\nSe seu app ainda reportar erro, reinicie o computador ou faça logout/login para garantir que as variáveis sejam recarregadas.\n")
    print("Se quiser, re-execute este script para configurar outros caminhos ou corrigir.\n")
    print("Fim.\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAbortado pelo usuário.")
        sys.exit(1)