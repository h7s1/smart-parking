// Smart Parking web pages (Presentation layer, Figure 1).
//
// Security notes:
//  * This page makes no security decisions. Hiding a section here is only for
//    convenience; the server checks the login, role and ownership on every request.
//  * Text from the server is always shown with textContent, never innerHTML,
//    so data can never run as code in the page.
//  * The session cookie is HttpOnly, so this script cannot read it.
"use strict";

const views = ["auth-view", "driver-view", "admin-view", "support-view"];
const $ = (id) => document.getElementById(id);

// ---------- Helpers ----------

async function api(method, path, body) {
  const options = { method, credentials: "same-origin", headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch("/api" + path, options);
  let data = {};
  try { data = await response.json(); } catch (_) { /* empty body */ }
  if (!response.ok) {
    const error = new Error(data.error || "Something went wrong.");
    error.status = response.status;
    throw error;
  }
  return data;
}

function showMessage(text, isError) {
  const box = $("message");
  box.textContent = text;
  box.className = isError ? "error" : "ok";
  box.hidden = false;
}

function showView(id) {
  views.forEach((v) => { $(v).hidden = v !== id; });
}

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function cell(text) {
  const td = document.createElement("td");
  td.textContent = text;
  return td;
}

function button(label, onClick, className) {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = label;
  if (className) b.className = className;
  b.addEventListener("click", onClick);
  return b;
}

function localTime(iso) {
  return new Date(iso).toLocaleString();
}

// datetime-local gives local time without a time zone; the API needs UTC.
function toUtcIso(localValue) {
  return new Date(localValue).toISOString();
}

async function run(action) {
  try {
    await action();
  } catch (error) {
    if (error.status === 401) {
      showView("auth-view");
      $("session-bar").hidden = true;
    }
    showMessage(error.message, true);
  }
}

// ---------- Session ----------

async function loadSession() {
  try {
    const me = await api("GET", "/me");
    $("who").textContent = me.email + " (" + me.role.replace("_", " ").toLowerCase() + ")";
    $("session-bar").hidden = false;
    if (me.role === "DRIVER") { showView("driver-view"); await loadDriver(); }
    else if (me.role === "ADMIN") { showView("admin-view"); await loadAdmin(); }
    else { showView("support-view"); }
  } catch (_) {
    $("session-bar").hidden = true;
    showView("auth-view");
  }
}

$("login-form").addEventListener("submit", (event) => {
  event.preventDefault();
  run(async () => {
    const data = await api("POST", "/login", formData(event.target));
    event.target.reset();
    showMessage(data.message, false);
    await loadSession();
  });
});

$("register-form").addEventListener("submit", (event) => {
  event.preventDefault();
  run(async () => {
    const data = await api("POST", "/register", formData(event.target));
    event.target.reset();
    showMessage(data.message, false);
  });
});

$("logout-button").addEventListener("click", () => {
  run(async () => {
    const data = await api("POST", "/logout", {});
    showMessage(data.message, false);
    await loadSession();
  });
});

// ---------- Driver ----------

let vehiclePlates = {};

async function loadDriver() {
  const [{ vehicles }, { spots }, { reservations }] = await Promise.all([
    api("GET", "/vehicles"), api("GET", "/spots"), api("GET", "/reservations"),
  ]);

  vehiclePlates = {};
  const list = $("vehicle-list");
  const select = $("vehicle-select");
  list.replaceChildren();
  select.replaceChildren();
  vehicles.forEach((v) => {
    vehiclePlates[v.id] = v.plate;
    const li = document.createElement("li");
    const span = document.createElement("span");
    span.textContent = v.plate;
    li.append(span, button("Remove", () => run(async () => {
      const data = await api("DELETE", "/vehicles/" + v.id);
      showMessage(data.message, false);
      await loadDriver();
    }), "secondary"));
    list.append(li);
    select.append(new Option(v.plate, v.id));
  });
  if (vehicles.length === 0) {
    const li = document.createElement("li");
    li.textContent = "No vehicles yet.";
    list.append(li);
  }

  const spotSelect = $("spot-select");
  spotSelect.replaceChildren();
  spots.forEach((s) => spotSelect.append(new Option(s.label, s.id)));

  const rows = $("reservation-rows");
  rows.replaceChildren();
  reservations.forEach((r) => {
    const tr = document.createElement("tr");
    const actions = document.createElement("td");
    actions.append(button("Cancel", () => run(async () => {
      const data = await api("DELETE", "/reservations/" + r.id);
      showMessage(data.message, false);
      await loadDriver();
    }), "secondary"));
    tr.append(cell(r.spot), cell(vehiclePlates[r.vehicle_id] || ""),
              cell(localTime(r.start)), cell(localTime(r.end)), actions);
    rows.append(tr);
  });
}

$("vehicle-form").addEventListener("submit", (event) => {
  event.preventDefault();
  run(async () => {
    const data = await api("POST", "/vehicles", formData(event.target));
    event.target.reset();
    showMessage(data.message, false);
    await loadDriver();
  });
});

$("reservation-form").addEventListener("submit", (event) => {
  event.preventDefault();
  run(async () => {
    const values = formData(event.target);
    const data = await api("POST", "/reservations", {
      vehicle_id: values.vehicle_id,
      spot_id: values.spot_id,
      start: toUtcIso(values.start),
      end: toUtcIso(values.end),
    });
    showMessage(data.message, false);       // NFR-03: confirmation message
    await loadDriver();
  });
});

$("delete-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (!window.confirm("Delete your account and all its data? This cannot be undone.")) return;
  run(async () => {
    const data = await api("POST", "/account/delete", formData(event.target));
    event.target.reset();
    showMessage(data.message, false);
    await loadSession();
  });
});

// ---------- Admin ----------

async function loadAdmin() {
  const [{ spots }, { entries }] = await Promise.all([
    api("GET", "/admin/spots"), api("GET", "/admin/audit-log"),
  ]);

  const spotRows = $("spot-rows");
  spotRows.replaceChildren();
  spots.forEach((s) => {
    const tr = document.createElement("tr");
    const times = s.reserved_times.map((t) => localTime(t.start) + " to " + localTime(t.end));
    const actions = document.createElement("td");
    if (s.status === "FREE" || s.status === "DISABLED") {
      const next = s.status === "FREE" ? "DISABLED" : "FREE";
      actions.append(button(next === "DISABLED" ? "Disable" : "Enable", () => run(async () => {
        const data = await api("PATCH", "/admin/spots/" + s.id, { status: next });
        showMessage(data.message, false);
        await loadAdmin();
      }), "secondary"));
    }
    tr.append(cell(s.label), cell(s.status), cell(times.join("; ") || "None"), actions);
    spotRows.append(tr);
  });

  const auditRows = $("audit-rows");
  auditRows.replaceChildren();
  entries.forEach((e) => {
    const tr = document.createElement("tr");
    tr.append(cell(localTime(e.time)), cell(e.action), cell(e.user_id || "-"),
              cell(e.target_id || "-"), cell(e.ip_address || "-"));
    auditRows.append(tr);
  });
}

loadSession();
