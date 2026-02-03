import requests
import json

# --- COLE SUA CHAVE AQUI ---
API_KEY = "AIzaSyAIvhMiqvXUQPADJKEO6kZxDgOgLCYIi38"
# ---------------------------

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"

print("--- PERGUNTANDO AO GOOGLE QUAIS MODELOS ESTÃO DISPONÍVEIS ---")
try:
    response = requests.get(url)
    if response.status_code == 200:
        modelos = response.json().get('models', [])
        print(f"\n✅ SUCESSO! Sua chave tem acesso a {len(modelos)} modelos:\n")
        for m in modelos:
            # Filtra apenas os que geram conteúdo
            if "generateContent" in m['supportedGenerationMethods']:
                print(f" -> {m['name']}")
    else:
        print(f"\n❌ ERRO {response.status_code}: A chave não conseguiu listar modelos.")
        print("Detalhe:", response.text)
        print("\nSOLUÇÃO: Crie a chave pelo link: https://aistudio.google.com/app/apikey")
except Exception as e:
    print(f"Erro de conexão: {e}")