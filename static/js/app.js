document.addEventListener("DOMContentLoaded", () => {
  const dropZone = document.getElementById("dropZone");
  const fileInput = document.getElementById("fileInput");
  const selectFileBtn = document.getElementById("selectFileBtn");
  const uploadBtn = document.getElementById("uploadBtn");
  const uploadForm = document.getElementById("uploadForm");
  const loading = document.getElementById("loading");
  const result = document.getElementById("result");
  const copyBtn = document.getElementById("copyBtn");
  const downloadLink = document.getElementById("downloadLink");

  let selectedFile = null;

  selectFileBtn.addEventListener("click", () => {
    fileInput.click();
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files.length > 0) {
      selectedFile = fileInput.files[0];
      uploadBtn.disabled = false;
      dropZone.querySelector("p").textContent = selectedFile.name;
    }
  });

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("dragover");
  });

  dropZone.addEventListener("dragleave", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
  });

  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      if (file.type === "application/pdf") {
        selectedFile = file;
        fileInput.files = e.dataTransfer.files;
        uploadBtn.disabled = false;
        dropZone.querySelector("p").textContent = selectedFile.name;
      } else {
        alert("Por favor, envie um arquivo PDF.");
      }
    }
  });

  uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!selectedFile) return;

    uploadBtn.disabled = true;
    loading.classList.remove("hidden");
    result.classList.add("hidden");

    const formData = new FormData();
    formData.append("file", selectedFile);

    try {
      const response = await fetch("/upload", {
        method: "POST",
        body: formData,
      });
      const data = await response.json();

      if (response.ok) {
        showResult(data.relatorio, data.arquivo_relatorio);
      } else {
        alert(data.error || "Erro ao processar o arquivo.");
      }
    } catch (err) {
      alert("Erro na comunicação com o servidor.");
    } finally {
      loading.classList.add("hidden");
      uploadBtn.disabled = false;
    }
  });

  function showResult(data, arquivo) {
    result.classList.remove("hidden");

    document.getElementById("cartorio").textContent = `Cartório: ${data["Cartório"] || ""}`;
    document.getElementById("dataBusca").textContent = `Data da Busca: ${data["Data da Busca"] || ""}`;
    document.getElementById("dataCertidao").textContent = `Data da Certidão: ${data["Data da Certidão"] || ""}`;
    document.getElementById("diagnostico").textContent = `Diagnóstico: ${data["Diagnóstico"] || ""}`;
    document.getElementById("endereco").textContent = `Endereço: ${data["Endereço"] || ""}`;
    document.getElementById("fracaoIdeal").textContent = `Fração Ideal: ${data["Fração Ideal"] || ""}`;
    document.getElementById("matricula").textContent = `Matrícula: ${data["Matrícula"] || ""}`;

    // Proprietários
    const propDiv = document.getElementById("proprietarios");
    if (Array.isArray(data["Proprietários"])) {
      propDiv.innerHTML = "Proprietários:\n" + data["Proprietários"].map(p => `- ${p.nome}`).join("\n");
    } else {
      propDiv.textContent = "Proprietários: Não encontrado";
    }

    // Ônus Reais
    const onusDiv = document.getElementById("onusReais");
    if (Array.isArray(data["Ônus Reais"])) {
      onusDiv.innerHTML = "Ônus Reais:\n" + data["Ônus Reais"].join("\n");
    } else {
      onusDiv.textContent = "Ônus Reais: Nenhum";
    }

    // Link para download
    downloadLink.href = `/download/${arquivo}`;
    downloadLink.download = arquivo;
  }

  copyBtn.addEventListener("click", () => {
    const cards = document.querySelectorAll(".grid .card");
    let textToCopy = "";
    cards.forEach(card => {
      textToCopy += card.textContent + "\n\n";
    });
    navigator.clipboard.writeText(textToCopy).then(() => {
      alert("Relatório copiado para a área de transferência!");
    });
  });
});