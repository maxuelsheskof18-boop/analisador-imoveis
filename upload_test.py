import requests

url = "http://localhost:5000/analyze"
file_path = r"C:\Users\maxue\Documents\Certidao-de-onus-reais-EM.pdf"

with open(file_path, "rb") as f:
    files = {"file": (file_path, f, "application/pdf")}
    response = requests.post(url, files=files)

print(response.status_code)
print(response.text)