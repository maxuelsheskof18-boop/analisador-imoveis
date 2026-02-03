import requests
import sys

# --- COLE SUA CHAVE AQUI DENTRO DAS ASPAS ---
CHAVE_NOVA = "AIzaSyAIvhMiqvXUQPADJKEO6kZxDgOgLCYIi38"
# --------------------------------------------

print(f"--- INICIANDO TESTE DE CHAVE ---")
print(f"Chave usada (primeiros 10 digitos): {CHAVE_NOVA[:10]}...")

if "COLE_SUA" in CHAVE_NOVA or len(CHAVE_NOVA) < 20:
    print("ERRO: Você não colou a chave corretamente no código!")
    sys.exit()

url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={CHAVE_NOVA}"
headers = {"Content-Type": "application/json"}
data = {
    "contents": [{
        "parts": [{"text": "Responda apenas com a palavra: FUNCIONOU"}]
    }]
}

try:
    print("Enviando requisição para o Google...")
    response = requests.post(url, headers=headers, json=data, timeout=10)
    
    print(f"Status Code recebido: {response.status_code}")
    
    if response.status_code == 200:
        print("\n✅ SUCESSO! A CHAVE ESTÁ FUNCIONANDO PERFEITAMENTE!")
        print(f"Resposta da IA: {response.json()['candidates'][0]['content']['parts'][0]['text']}")
        print("\n>>> AGORA VOCÊ PODE COLOCAR ESSA CHAVE NO APP.PY <<<")
    else:
        print("\n❌ ERRO NA CHAVE OU NA CONTA GOOGLE:")
        print(response.text)
        print("\nDICA: Se o erro for 400 (API Key not valid), você copiou errado.")
        print("DICA: Se o erro for 429 (Quota), essa chave nova também está sem saldo.")

except Exception as e:
    print(f"Erro de conexão: {e}")