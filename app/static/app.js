const form = document.querySelector("#upload-form");
const fileInput = document.querySelector("#xml-file");
const statusEl = document.querySelector("#status");
const submitButton = document.querySelector("#submit-button");

const resultCard = document.querySelector("#result-card");
const resultMeta = document.querySelector("#result-meta");
const artifactList = document.querySelector("#artifact-list");
const warningBlock = document.querySelector("#warning-block");
const warningList = document.querySelector("#warning-list");


function setStatus(message, tone = "neutral") {
  statusEl.textContent = message;
  statusEl.dataset.tone = tone;
}


function selectedFormats() {
  return Array.from(document.querySelectorAll("input[name='format']:checked"))
    .map((item) => item.value);
}


function selectedDetailLevel() {
  const selected = document.querySelector("input[name='detail-level']:checked");
  return selected ? selected.value : "deep";
}


function includeDiagrams() {
  const selected = document.querySelector("input[name='include-diagrams']");
  return selected ? selected.checked : true;
}


function resetResult() {
  resultCard.classList.add("hidden");
  resultMeta.innerHTML = "";
  artifactList.innerHTML = "";
  warningList.innerHTML = "";
  warningBlock.classList.add("hidden");
}


function renderResult(payload) {
  resultMeta.innerHTML = "";
  artifactList.innerHTML = "";
  warningList.innerHTML = "";

  const confidence = typeof payload.purpose?.confidence === "number"
    ? payload.purpose.confidence.toFixed(2)
    : "0.00";

  const stats = payload.stats || {};
  const generationConfig = payload.generation_config || {};
  resultMeta.innerHTML = `
    <p><strong>Project:</strong> ${payload.project_name || "Unknown"}</p>
    <p><strong>Detected Purpose:</strong> ${payload.purpose?.purpose_label || "Unknown"} (confidence ${confidence})</p>
    <p><strong>Detail Level:</strong> ${payload.detail_level || "deep"}</p>
    <p><strong>Output Folder:</strong> ${payload.output_folder}</p>
    <p><strong>Tracked Nodes:</strong> ${stats.tracked_nodes ?? 0}</p>
    <p><strong>Overview Nodes Budget:</strong> ${generationConfig.overview_max_nodes ?? "n/a"}</p>
    <p><strong>Detailed Nodes Budget:</strong> ${generationConfig.detailed_max_nodes ?? "n/a"}</p>
    <p><strong>Diagrams Included:</strong> ${generationConfig.include_diagrams ? "Yes" : "No"}</p>
  `;

  for (const artifact of payload.artifacts || []) {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = artifact.download_url;
    link.textContent = `${artifact.file_name} (${artifact.format})`;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    item.appendChild(link);
    artifactList.appendChild(item);
  }

  const warnings = payload.warnings || [];
  if (warnings.length) {
    warningBlock.classList.remove("hidden");
    for (const warning of warnings) {
      const item = document.createElement("li");
      item.textContent = warning;
      warningList.appendChild(item);
    }
  } else {
    warningBlock.classList.add("hidden");
  }

  resultCard.classList.remove("hidden");
}


form.addEventListener("submit", async (event) => {
  event.preventDefault();
  resetResult();

  const file = fileInput.files?.[0];
  if (!file) {
    setStatus("Select an XML file before submitting.", "error");
    return;
  }

  const formats = selectedFormats();
  if (!formats.length) {
    setStatus("Select at least one output format.", "error");
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  formData.append("formats", formats.join(","));
  formData.append("detail_level", selectedDetailLevel());
  formData.append("include_diagrams", includeDiagrams() ? "true" : "false");

  submitButton.disabled = true;
  setStatus("Uploading and generating documentation...", "working");

  try {
    const response = await fetch("/api/generate", {
      method: "POST",
      body: formData,
    });

    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || "Generation failed.");
    }

    renderResult(payload);
    setStatus("Documentation generated successfully.", "success");
  } catch (error) {
    setStatus(error.message || "Unexpected error.", "error");
  } finally {
    submitButton.disabled = false;
  }
});
