const elements = {
  connection: document.querySelector("#connection"),
  modeSummary: document.querySelector("#modeSummary"),
  camera: document.querySelector("#cameraSelect"),
  enabled: document.querySelector("#enabledSelect"),
  preset: document.querySelector("#presetSelect"),
  fps: document.querySelector("#fpsSelect"),
  lag: document.querySelector("#lagSelect"),
  aspect: document.querySelector("#aspectInput"),
  custom: document.querySelector("#customControls"),
  customLag: document.querySelector("#customLagControl"),
  width: document.querySelector("#widthInput"),
  height: document.querySelector("#heightInput"),
  lagInput: document.querySelector("#lagInput"),
  apply: document.querySelector("#applyButton"),
  refresh: document.querySelector("#refreshButton"),
  feedback: document.querySelector("#feedback"),
  streamGrid: document.querySelector("#streamGrid"),
  empty: document.querySelector("#emptyState"),
  imageTopic: document.querySelector("#imageTopic"),
  infoTopic: document.querySelector("#infoTopic"),
};

let state = null;
let selectedCamera = null;
let renderedStreams = "";

function setFeedback(message, type = "") {
  elements.feedback.textContent = message;
  elements.feedback.className = type;
}

function selectMatching(select, value, fallback = null) {
  const stringValue = String(value);
  if ([...select.options].some((option) => option.value === stringValue)) {
    select.value = stringValue;
  } else if (fallback !== null) {
    select.value = fallback;
  }
}

function populateCameraSelect(activeCameras) {
  const previous = selectedCamera || elements.camera.value;
  elements.camera.innerHTML = "";
  for (const name of activeCameras) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    elements.camera.appendChild(option);
  }
  selectedCamera = activeCameras.includes(previous) ? previous : activeCameras[0];
  elements.camera.value = selectedCamera || "";
}

function populateControls() {
  if (!state || !selectedCamera) return;
  const camera = state.cameras[selectedCamera];
  if (!camera) return;
  const config = camera.config;
  elements.enabled.value = String(camera.enabled);
  const preset = `${config.width}x${config.height}`;
  selectMatching(elements.preset, preset, "custom");
  selectMatching(elements.fps, config.fps, "16");
  selectMatching(elements.lag, camera.lag_seconds, "custom");
  elements.width.value = config.width;
  elements.height.value = config.height;
  elements.lagInput.value = camera.lag_seconds;
  elements.aspect.checked = config.preserve_aspect;
  elements.custom.classList.toggle("hidden", elements.preset.value !== "custom");
  elements.customLag.classList.toggle("hidden", elements.lag.value !== "custom");
  elements.imageTopic.textContent = camera.image_topic;
  elements.infoTopic.textContent = camera.camera_info_topic;
}

function renderStreams() {
  if (!state) return;
  const enabled = state.active_cameras.filter((name) => state.cameras[name].enabled);
  const signature = enabled.map((name) => {
    const config = state.cameras[name].config;
    return `${name}:${config.width}x${config.height}:${config.fps}:${state.cameras[name].lag_seconds}`;
  }).join("|");
  if (signature === renderedStreams) return;
  renderedStreams = signature;
  elements.streamGrid.innerHTML = "";
  elements.empty.classList.toggle("hidden", enabled.length !== 0);
  for (const name of enabled) {
    const camera = state.cameras[name];
    const card = document.createElement("article");
    card.className = "stream-card";
    const meta = document.createElement("div");
    meta.className = "stream-meta";
    meta.innerHTML = `<h3>${name}</h3><span>${camera.config.width}x${camera.config.height} · ${camera.config.fps} FPS · ${camera.lag_seconds}s lag</span>`;
    const image = document.createElement("img");
    image.alt = `${name} camera stream`;
    image.src = `/stream/${name}.mjpg?refresh=${Date.now()}`;
    card.append(meta, image);
    elements.streamGrid.appendChild(card);
  }
}

async function refreshState() {
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state = await response.json();
    elements.connection.textContent = "ROS connected";
    elements.connection.className = "status online";
    elements.modeSummary.textContent = `Mode ${state.mode}: ${state.active_cameras.join(", ")}`;
    populateCameraSelect(state.active_cameras);
    populateControls();
    renderStreams();
  } catch (error) {
    elements.connection.textContent = "Waiting for ROS";
    elements.connection.className = "status waiting";
    setFeedback(error.message, "error");
  }
}

function readDimensions() {
  if (elements.preset.value === "custom") {
    return [Number(elements.width.value), Number(elements.height.value)];
  }
  return elements.preset.value.split("x").map(Number);
}

async function applySettings() {
  if (!selectedCamera) return;
  const [width, height] = readDimensions();
  const lag = elements.lag.value === "custom" ? Number(elements.lagInput.value) : Number(elements.lag.value);
  const payload = {
    enabled: elements.enabled.value === "true",
    width,
    height,
    fps: Number(elements.fps.value),
    preserve_aspect: elements.aspect.checked,
    lag_seconds: lag,
  };
  elements.apply.disabled = true;
  setFeedback("Applying settings...");
  try {
    const response = await fetch(`/api/cameras/${selectedCamera}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok || !result.success) throw new Error(result.message || `HTTP ${response.status}`);
    setFeedback(result.message, "success");
    await refreshState();
  } catch (error) {
    setFeedback(error.message, "error");
  } finally {
    elements.apply.disabled = false;
  }
}

elements.camera.addEventListener("change", () => {
  selectedCamera = elements.camera.value;
  populateControls();
});
elements.preset.addEventListener("change", () => {
  elements.custom.classList.toggle("hidden", elements.preset.value !== "custom");
});
elements.lag.addEventListener("change", () => {
  elements.customLag.classList.toggle("hidden", elements.lag.value !== "custom");
});
elements.apply.addEventListener("click", applySettings);
elements.refresh.addEventListener("click", refreshState);

refreshState();
setInterval(refreshState, 1500);
