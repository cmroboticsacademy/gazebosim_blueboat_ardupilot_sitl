const BOATS = ["blueboat", "blueboat2", "blueboat3", "blueboat4"];

const elements = {
  connection: document.querySelector("#connection"),
  modeSummary: document.querySelector("#modeSummary"),
  refresh: document.querySelector("#refreshButton"),
  selectAll: document.querySelector("#selectAllInput"),
  selector: document.querySelector("#cameraSelector"),
  selectedSummary: document.querySelector("#selectedSummary"),
  cards: document.querySelector("#cameraCards"),
  feeds: document.querySelector("#cameraFeeds"),
  feedsEmpty: document.querySelector("#cameraFeedsEmpty"),
  active: document.querySelector("#activeSelect"),
  fps: document.querySelector("#fpsSelect"),
  size: document.querySelector("#sizeSelect"),
  bitrate: document.querySelector("#bitrateSelect"),
  lag: document.querySelector("#lagSelect"),
  aspect: document.querySelector("#aspectSelect"),
  customSize: document.querySelector("#customSizeControls"),
  customLag: document.querySelector("#customLagControls"),
  width: document.querySelector("#widthInput"),
  height: document.querySelector("#heightInput"),
  lagInput: document.querySelector("#lagInput"),
  apply: document.querySelector("#applyButton"),
  feedback: document.querySelector("#feedback"),
};

let state = null;
let selectionInitialized = false;
const selectedCameras = new Set();
const selectorInputs = new Map();
const cards = new Map();
const feedCards = new Map();

function setFeedback(message, type = "") {
  elements.feedback.textContent = message;
  elements.feedback.className = type;
}

function formatNumber(value, digits = 1, suffix = "") {
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  return `${number.toFixed(digits)}${suffix}`;
}

function formatAge(value) {
  if (value === null || value === undefined) return "No frame yet";
  const number = Number(value);
  if (!Number.isFinite(number)) return "No frame yet";
  if (number < 1) return `${Math.round(number * 1000)} ms ago`;
  return `${number.toFixed(1)} s ago`;
}

function activeCameraNames() {
  if (!state) return [];
  return BOATS.filter((name) => state.cameras?.[name]?.active);
}

function enabledCameraNames() {
  if (!state) return [];
  return BOATS.filter((name) => {
    const camera = state.cameras?.[name];
    return Boolean(camera?.active && camera?.enabled);
  });
}

function selectedActiveNames() {
  return activeCameraNames().filter((name) => selectedCameras.has(name));
}

function updateSelectionSummary() {
  const selected = selectedActiveNames();
  elements.selectedSummary.textContent = selected.length
    ? `Applying changes to: ${selected.join(", ")}`
    : "No cameras selected.";

  const active = activeCameraNames();
  elements.selectAll.disabled = active.length === 0;
  elements.selectAll.checked = active.length > 0 && selected.length === active.length;
  elements.selectAll.indeterminate = selected.length > 0 && selected.length < active.length;
  elements.apply.disabled = selected.length === 0;
}

function ensureSelector(name) {
  if (selectorInputs.has(name)) return selectorInputs.get(name);
  const label = document.createElement("label");
  label.className = "camera-choice";

  const input = document.createElement("input");
  input.type = "checkbox";
  input.value = name;
  input.addEventListener("change", () => {
    if (input.checked) selectedCameras.add(name);
    else selectedCameras.delete(name);
    label.classList.toggle("selected", input.checked);
    updateSelectionSummary();
  });

  const text = document.createElement("span");
  text.textContent = name;
  const availability = document.createElement("small");
  availability.dataset.role = "availability";

  label.append(input, text, availability);
  elements.selector.appendChild(label);
  const result = { label, input, availability };
  selectorInputs.set(name, result);
  return result;
}

function updateSelector() {
  const active = activeCameraNames();
  if (!selectionInitialized && active.length) {
    active.forEach((name) => selectedCameras.add(name));
    selectionInitialized = true;
  }

  for (const name of BOATS) {
    const camera = state.cameras?.[name];
    const refs = ensureSelector(name);
    const isActive = Boolean(camera?.active);
    if (!isActive) selectedCameras.delete(name);
    refs.input.disabled = !isActive;
    refs.input.checked = isActive && selectedCameras.has(name);
    refs.label.classList.toggle("selected", refs.input.checked);
    refs.label.classList.toggle("unavailable", !isActive);
    refs.availability.textContent = isActive ? "Active mode" : "Outside mode";
  }
  updateSelectionSummary();
}

function statItem(label, role) {
  const item = document.createElement("div");
  item.className = "stat-item";
  const title = document.createElement("span");
  title.textContent = label;
  const value = document.createElement("strong");
  value.dataset.role = role;
  value.textContent = "—";
  item.append(title, value);
  return { item, value };
}

function ensureCard(name) {
  if (cards.has(name)) return cards.get(name);
  const card = document.createElement("article");
  card.className = "camera-card panel";

  const heading = document.createElement("div");
  heading.className = "card-heading";
  const title = document.createElement("h3");
  title.textContent = name;
  const badges = document.createElement("div");
  badges.className = "badges";
  const activeBadge = document.createElement("span");
  activeBadge.className = "badge";
  const enabledBadge = document.createElement("span");
  enabledBadge.className = "badge";
  badges.append(activeBadge, enabledBadge);
  heading.append(title, badges);

  const statsGrid = document.createElement("div");
  statsGrid.className = "stats-grid";
  const stats = {
    size: statItem("Size", "size"),
    fps: statItem("FPS config / output", "fps"),
    inputFps: statItem("Raw input FPS", "inputFps"),
    bitrate: statItem("Preview target / actual", "bitrate"),
    lag: statItem("Lag / queued", "lag"),
    bridge: statItem("Gazebo bridge / rate", "bridge"),
    lastFrame: statItem("Last raw frame", "lastFrame"),
  };
  Object.values(stats).forEach(({ item }) => statsGrid.appendChild(item));

  const topics = document.createElement("div");
  topics.className = "card-topics";
  const imageTopic = document.createElement("code");
  imageTopic.dataset.role = "imageTopic";
  topics.append("ROS output: ", imageTopic);

  card.append(heading, statsGrid, topics);
  elements.cards.appendChild(card);
  const result = { card, activeBadge, enabledBadge, stats, imageTopic };
  cards.set(name, result);
  return result;
}

function updateCards() {
  for (const name of BOATS) {
    const camera = state.cameras?.[name] || {};
    const config = camera.config || {};
    const stats = camera.stats || {};
    const web = camera.web || {};
    const refs = ensureCard(name);

    refs.card.classList.toggle("inactive", !camera.active);
    refs.card.classList.toggle("disabled-camera", camera.active && !camera.enabled);
    refs.activeBadge.textContent = camera.active ? "In mode" : "Outside mode";
    refs.activeBadge.className = `badge ${camera.active ? "good" : "muted"}`;
    refs.enabledBadge.textContent = camera.enabled ? "Enabled" : "Disabled";
    refs.enabledBadge.className = `badge ${camera.enabled ? "good" : "warn"}`;

    refs.stats.size.value.textContent = config.width && config.height
      ? `${config.width} × ${config.height}`
      : "—";
    refs.stats.fps.value.textContent = `${formatNumber(config.fps, 1)} / ${formatNumber(stats.output_fps, 1)}`;
    refs.stats.inputFps.value.textContent = formatNumber(stats.input_fps, 1);
    refs.stats.bitrate.value.textContent = `${formatNumber(config.bitrate_kbps, 0, " kbps")} / ${formatNumber(web.actual_bitrate_kbps, 0, " kbps")}`;
    refs.stats.lag.value.textContent = `${formatNumber(camera.lag_seconds, 2, " s")} / ${Number(camera.queued_frames || 0)} frames`;
    const rate = camera.gazebo_sensor_rate_applied ?? camera.gazebo_sensor_rate_requested;
    refs.stats.bridge.value.textContent = `${camera.image_bridge_running ? "Running" : "Stopped"} / ${formatNumber(rate, 1, " Hz")}`;
    refs.stats.lastFrame.value.textContent = formatAge(stats.last_raw_age_seconds);
    refs.imageTopic.textContent = camera.image_topic || `/${name}/camera/image`;
  }
}

function createFeedCard(name) {
  const card = document.createElement("article");
  card.className = "feed-card panel";
  const heading = document.createElement("div");
  heading.className = "feed-heading";
  const title = document.createElement("h3");
  title.textContent = name;
  const rate = document.createElement("span");
  rate.className = "feed-rate";
  heading.append(title, rate);

  const imageWrap = document.createElement("div");
  imageWrap.className = "feed-image";
  const image = document.createElement("img");
  image.alt = `${name} active camera feed`;
  image.decoding = "async";
  imageWrap.appendChild(image);

  const topic = document.createElement("code");
  topic.textContent = `/${name}/camera/image`;
  card.append(heading, imageWrap, topic);
  elements.feeds.appendChild(card);

  const refs = { card, image, rate, topic };
  feedCards.set(name, refs);
  return refs;
}

function removeFeed(name) {
  const refs = feedCards.get(name);
  if (!refs) return;
  refs.image.removeAttribute("src");
  refs.card.remove();
  feedCards.delete(name);
}

function updateFeeds() {
  const enabled = new Set(enabledCameraNames());
  for (const name of [...feedCards.keys()]) {
    if (!enabled.has(name)) removeFeed(name);
  }

  for (const name of BOATS) {
    if (!enabled.has(name)) continue;
    const camera = state.cameras?.[name] || {};
    const web = camera.web || {};
    const refs = feedCards.get(name) || createFeedCard(name);
    if (!refs.image.hasAttribute("src")) {
      // Set once when the camera becomes enabled. Status polling deliberately
      // does not replace this URL, so the browser keeps one continuous stream.
      refs.image.src = `/stream/${name}.mjpg?session=${Date.now()}`;
    }
    refs.rate.textContent = `${formatNumber(web.encoded_fps, 1, " FPS")} · full source rate`;
    refs.topic.textContent = camera.image_topic || `/${name}/camera/image`;
  }

  elements.feedsEmpty.classList.toggle("hidden", enabled.size > 0);
}

async function refreshState() {
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state = await response.json();
    elements.connection.textContent = "ROS connected";
    elements.connection.className = "status online";
    elements.modeSummary.textContent = `Mode ${state.mode}: ${state.active_cameras.join(", ")}`;
    updateSelector();
    updateCards();
    updateFeeds();
  } catch (error) {
    elements.connection.textContent = "Waiting for ROS";
    elements.connection.className = "status waiting";
    setFeedback(error.message, "error");
  }
}

function resetSettingsForm() {
  elements.active.value = "";
  elements.fps.value = "";
  elements.size.value = "";
  elements.bitrate.value = "";
  elements.lag.value = "";
  elements.aspect.value = "";
  elements.customSize.classList.add("hidden");
  elements.customLag.classList.add("hidden");
}

function settingsPayload() {
  const settings = {};
  if (elements.active.value !== "") settings.enabled = elements.active.value === "true";
  if (elements.fps.value !== "") settings.fps = Number(elements.fps.value);
  if (elements.bitrate.value !== "") settings.bitrate_kbps = Number(elements.bitrate.value);
  if (elements.aspect.value !== "") settings.preserve_aspect = elements.aspect.value === "true";

  if (elements.size.value === "custom") {
    settings.width = Number(elements.width.value);
    settings.height = Number(elements.height.value);
  } else if (elements.size.value !== "") {
    [settings.width, settings.height] = elements.size.value.split("x").map(Number);
  }

  if (elements.lag.value === "custom") settings.lag_seconds = Number(elements.lagInput.value);
  else if (elements.lag.value !== "") settings.lag_seconds = Number(elements.lag.value);

  if ("width" in settings) {
    if (!Number.isInteger(settings.width) || !Number.isInteger(settings.height) ||
        settings.width < 16 || settings.height < 16 ||
        settings.width % 2 || settings.height % 2) {
      throw new Error("Width and height must be even integers of at least 16.");
    }
  }
  if ("lag_seconds" in settings && (!Number.isFinite(settings.lag_seconds) || settings.lag_seconds < 0)) {
    throw new Error("Lag must be zero or greater.");
  }
  return settings;
}

async function applySettings() {
  const cameras = selectedActiveNames();
  if (!cameras.length) {
    setFeedback("Select at least one active BlueBoat.", "error");
    return;
  }

  let settings;
  try {
    settings = settingsPayload();
  } catch (error) {
    setFeedback(error.message, "error");
    return;
  }
  if (!Object.keys(settings).length) {
    setFeedback("Choose at least one setting to change.", "error");
    return;
  }

  elements.apply.disabled = true;
  setFeedback(`Applying settings to ${cameras.join(", ")}...`);
  try {
    const response = await fetch("/api/cameras", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cameras, settings }),
    });
    const result = await response.json();
    if (!response.ok || !result.success) {
      throw new Error(result.message || `HTTP ${response.status}`);
    }
    setFeedback(result.message, "success");
    resetSettingsForm();
    await refreshState();
  } catch (error) {
    setFeedback(error.message, "error");
  } finally {
    elements.apply.disabled = selectedActiveNames().length === 0;
  }
}

elements.selectAll.addEventListener("change", () => {
  const active = activeCameraNames();
  if (elements.selectAll.checked) active.forEach((name) => selectedCameras.add(name));
  else active.forEach((name) => selectedCameras.delete(name));
  updateSelector();
});

elements.size.addEventListener("change", () => {
  elements.customSize.classList.toggle("hidden", elements.size.value !== "custom");
});
elements.lag.addEventListener("change", () => {
  elements.customLag.classList.toggle("hidden", elements.lag.value !== "custom");
});
elements.apply.addEventListener("click", applySettings);
elements.refresh.addEventListener("click", refreshState);

refreshState();
setInterval(refreshState, 2000);
