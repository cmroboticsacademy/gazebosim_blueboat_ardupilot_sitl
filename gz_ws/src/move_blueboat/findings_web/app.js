(function () {
  "use strict";

  var COLORS = {
    blueboat: "#4ea5ff",
    blueboat2: "#ff9f43",
    blueboat3: "#55d68b",
    blueboat4: "#b184ff"
  };
  var selectedId = null;
  var latestSeenId = 0;
  var currentState = null;
  var markers = {};
  var paths = {};
  var map = null;

  var connectionStatus = document.getElementById("connectionStatus");
  var findingCount = document.getElementById("findingCount");
  var classifiedCount = document.getElementById("classifiedCount");
  var findingsList = document.getElementById("findingsList");
  var selectedCoordinates = document.getElementById("selectedCoordinates");
  var form = document.getElementById("findingForm");
  var classification = document.getElementById("classification");
  var objectGuess = document.getElementById("objectGuess");
  var confidence = document.getElementById("confidence");
  var confidenceValue = document.getElementById("confidenceValue");
  var notes = document.getElementById("notes");
  var saveButton = document.getElementById("saveButton");
  var deleteButton = document.getElementById("deleteButton");
  var clearButton = document.getElementById("clearButton");
  var formMessage = document.getElementById("formMessage");
  var followLatest = document.getElementById("followLatest");
  var mapMessage = document.getElementById("mapMessage");

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function initMap(origin) {
    if (!window.L) {
      mapMessage.textContent = "Leaflet could not load. Check internet access.";
      return;
    }
    map = L.map("map").setView([origin.latitude, origin.longitude], 18);

    var satellite = L.tileLayer(
      "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      {
        maxZoom: 20,
        attribution: "Tiles &copy; Esri"
      }
    ).addTo(map);

    var street = L.tileLayer(
      "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
      {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors"
      }
    );

    L.control.layers(
      {"Satellite": satellite, "Street": street},
      null,
      {collapsed: false}
    ).addTo(map);

    L.circleMarker([origin.latitude, origin.longitude], {
      radius: 5,
      color: "#ffffff",
      weight: 2,
      fillColor: "#10151c",
      fillOpacity: 1
    }).addTo(map).bindPopup("Mission 4 geographic origin");
  }

  function markerColor(item) {
    if (item.classification === "hazard") return "#ff5c5c";
    if (item.classification === "non-hazard") return "#55d68b";
    return "#f0c75e";
  }

  function popupText(item) {
    var guess = item.object_guess ? escapeHtml(item.object_guess) : "Not classified";
    return (
      '<div class="finding-popup">' +
      "<strong>Finding " + item.id + "</strong>" +
      escapeHtml(item.classification) + "<br>" +
      guess + "<br>" +
      item.latitude.toFixed(7) + ", " + item.longitude.toFixed(7) +
      "</div>"
    );
  }

  function renderPaths(state) {
    if (!map) return;
    Object.keys(state.paths).forEach(function (boat) {
      var points = state.paths[boat] || [];
      if (!paths[boat]) {
        paths[boat] = L.polyline(points, {
          color: COLORS[boat] || "#ffffff",
          weight: 3,
          opacity: 0.9
        }).addTo(map).bindTooltip(boat);
      } else {
        paths[boat].setLatLngs(points);
      }
    });
  }

  function renderMarkers(state) {
    if (!map) return;
    var present = {};
    state.findings.forEach(function (item) {
      present[item.id] = true;
      if (!markers[item.id]) {
        markers[item.id] = L.circleMarker(
          [item.latitude, item.longitude],
          {
            radius: 8,
            color: "#ffffff",
            weight: 2,
            fillColor: markerColor(item),
            fillOpacity: 0.95
          }
        ).addTo(map);
      } else {
        markers[item.id].setLatLng([item.latitude, item.longitude]);
        markers[item.id].setStyle({fillColor: markerColor(item)});
      }
      markers[item.id].bindPopup(popupText(item));
    });

    Object.keys(markers).forEach(function (id) {
      if (!present[id]) {
        map.removeLayer(markers[id]);
        delete markers[id];
      }
    });
  }

  function selectFinding(id, pan) {
    if (!currentState) return;
    var item = currentState.findings.find(function (candidate) {
      return candidate.id === id;
    });
    if (!item) {
      selectedId = null;
      updateEditor(null);
      return;
    }
    selectedId = id;
    updateEditor(item);
    renderList(currentState);
    if (pan && map) {
      map.panTo([item.latitude, item.longitude]);
      if (markers[item.id]) markers[item.id].openPopup();
    }
  }

  function updateEditor(item) {
    var disabled = !item;
    [classification, objectGuess, confidence, notes, saveButton, deleteButton]
      .forEach(function (control) { control.disabled = disabled; });

    if (!item) {
      selectedCoordinates.textContent = "Select a finding to classify it.";
      classification.value = "unclassified";
      objectGuess.value = "";
      confidence.value = 50;
      confidenceValue.textContent = "50%";
      notes.value = "";
      return;
    }

    selectedCoordinates.textContent =
      "X " + item.x.toFixed(2) + " m | Y " + item.y.toFixed(2) +
      " m | Z " + item.z.toFixed(2) + " m\n" +
      item.latitude.toFixed(7) + ", " + item.longitude.toFixed(7);
    classification.value = item.classification;
    objectGuess.value = item.object_guess || "";
    confidence.value = item.confidence;
    confidenceValue.textContent = item.confidence + "%";
    notes.value = item.notes || "";
  }

  function renderList(state) {
    findingsList.textContent = "";
    var reversed = state.findings.slice().reverse();
    if (!reversed.length) {
      var empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = "No findings yet.";
      findingsList.appendChild(empty);
      return;
    }

    reversed.forEach(function (item) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "finding-row" + (selectedId === item.id ? " selected" : "");

      var strong = document.createElement("strong");
      strong.textContent = "Finding " + item.id;
      var detail = document.createElement("span");
      var guess = item.object_guess ? " • " + item.object_guess : "";
      detail.textContent = item.classification + guess;

      button.appendChild(strong);
      button.appendChild(detail);
      button.addEventListener("click", function () {
        selectFinding(item.id, true);
      });
      findingsList.appendChild(button);
    });
  }

  function renderState(state) {
    currentState = state;
    if (!map) initMap(state.origin);

    findingCount.textContent = state.findings.length;
    classifiedCount.textContent = state.findings.filter(function (item) {
      return item.classification !== "unclassified";
    }).length;

    renderPaths(state);
    renderMarkers(state);
    renderList(state);

    if (selectedId !== null) {
      var selected = state.findings.find(function (item) {
        return item.id === selectedId;
      });
      updateEditor(selected || null);
    }

    var newest = state.findings.length ?
      state.findings[state.findings.length - 1] : null;
    if (newest && newest.id > latestSeenId) {
      latestSeenId = newest.id;
      mapMessage.textContent =
        "Finding " + newest.id + " received from RViz /clicked_point";
      if (followLatest.checked || selectedId === null) {
        selectFinding(newest.id, true);
      }
    } else if (!newest) {
      mapMessage.textContent = "Waiting for /clicked_point...";
    }
  }

  async function refresh() {
    try {
      var response = await fetch("/api/state", {cache: "no-store"});
      if (!response.ok) throw new Error("HTTP " + response.status);
      var state = await response.json();
      connectionStatus.textContent = "Listening";
      connectionStatus.className = "status connected";
      renderState(state);
    } catch (error) {
      connectionStatus.textContent = "Disconnected";
      connectionStatus.className = "status waiting";
      mapMessage.textContent = "Could not reach findings ROS node.";
    }
    window.setTimeout(refresh, 750);
  }

  async function postJson(url, body) {
    var response = await fetch(url, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body || {})
    });
    var payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Request failed");
    }
    return payload;
  }

  confidence.addEventListener("input", function () {
    confidenceValue.textContent = confidence.value + "%";
  });

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    if (selectedId === null) return;
    formMessage.textContent = "Saving...";
    try {
      await postJson("/api/findings/" + selectedId, {
        classification: classification.value,
        object_guess: objectGuess.value,
        confidence: Number(confidence.value),
        notes: notes.value
      });
      formMessage.textContent = "Saved.";
      await refreshOnce();
    } catch (error) {
      formMessage.textContent = error.message;
    }
  });

  deleteButton.addEventListener("click", async function () {
    if (selectedId === null) return;
    if (!window.confirm("Delete Finding " + selectedId + "?")) return;
    try {
      await postJson("/api/findings/" + selectedId + "/delete", {});
      selectedId = null;
      updateEditor(null);
      await refreshOnce();
    } catch (error) {
      formMessage.textContent = error.message;
    }
  });

  clearButton.addEventListener("click", async function () {
    if (!window.confirm("Clear all Mission 4 findings?")) return;
    try {
      await postJson("/api/clear", {});
      selectedId = null;
      latestSeenId = 0;
      updateEditor(null);
      await refreshOnce();
    } catch (error) {
      formMessage.textContent = error.message;
    }
  });

  async function refreshOnce() {
    var response = await fetch("/api/state", {cache: "no-store"});
    if (!response.ok) return;
    renderState(await response.json());
  }

  refresh();
}());
