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

// The fixed list of dispute reasons (FR-15). The server checks the same list.
const REASONS = {
  GATE_DENIED_WITH_RESERVATION: "The gate did not let me in although I had a reservation",
  WRONG_ENTRY_OR_EXIT_TIME: "The entry or exit time is wrong",
  RESERVED_SPOT_TAKEN: "My reserved bay was taken",
  RESERVATION_NOT_SHOWN: "My reservation does not show correctly",
};

const ROLES = { DRIVER: "Driver", ADMIN: "Admin", SUPPORT_AGENT: "Support agent" };

const STATUS = {
  FREE: ["Free", "badge-free"],
  OCCUPIED: ["Occupied", "badge-occupied"],
  DISABLED: ["Disabled", "badge-disabled"],
  OPEN: ["Open", "badge-open"],
  CLOSED: ["Closed", "badge-closed"],
};

// Audit log actions in plain words. "alert" marks events worth a second look.
const EVENTS = {
  LOGIN_SUCCESS: ["Logged in", ""],
  LOGIN_FAILED: ["Failed login", "alert"],
  ACCOUNT_CREATED: ["Account created", ""],
  ACCOUNT_DELETED: ["Account deleted", ""],
  INACTIVE_ACCOUNT_DELETED: ["Inactive account deleted", ""],
  DISPUTE_OPENED: ["Dispute opened", ""],
  DISPUTE_CLOSED: ["Dispute closed", ""],
  SUPPORT_ACCESS: ["Support viewed driver data", "support"],
  SUPPORT_ACCESS_DENIED: ["Support access refused", "alert"],
};

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
    const error = new Error(data.error || "Something went wrong. Try again.");
    error.status = response.status;
    throw error;
  }
  return data;
}

let toastTimer;
function toast(text, isError) {
  const box = $("toast");
  box.textContent = text;
  box.className = isError ? "toast is-error" : "toast";
  box.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.hidden = true; }, isError ? 7000 : 4000);
}

function showView(id) {
  views.forEach((v) => { $(v).hidden = v !== id; });
}

function formData(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = text;
  return node;
}

function cell(content, className) {
  const td = el("td", className);
  if (content instanceof Node) td.append(content);
  else td.textContent = content === undefined || content === null ? "" : content;
  return td;
}

function row(...cells) {
  const tr = document.createElement("tr");
  tr.append(...cells);
  return tr;
}

function button(label, onClick, className) {
  const b = el("button", "btn " + (className || "btn-secondary btn-small"), label);
  b.type = "button";
  b.addEventListener("click", onClick);
  return b;
}

function icon(name, className) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", className || "icon");
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", "#" + name);
  svg.append(use);
  return svg;
}

function badge(code, label) {
  const [name, className] = STATUS[code] || [code, "badge-closed"];
  return el("span", "badge " + className, label || name);
}

// "ABC1234" is shown as "ABC 1234", like on a real plate.
function plateText(text) {
  return (text || "").replace(/^([A-Z]+)(\d+)$/, "$1 $2");
}
function plate(text) {
  return el("span", "plate", plateText(text));
}

function shortId(id) {
  const span = el("span", "id-text", id ? id.slice(0, 8) : "–");
  if (id) span.title = id;
  return span;
}

const TIME_FORMAT = { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" };
function when(iso) {
  return iso ? new Date(iso).toLocaleString("en-GB", TIME_FORMAT) : "";
}
function whenExact(iso) {
  return iso ? new Date(iso).toLocaleString("en-GB", {
    day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", second: "2-digit",
  }) : "";
}

// datetime-local works in local time without a time zone; the API needs UTC.
function toUtcIso(localValue) {
  return new Date(localValue).toISOString();
}
function toLocalInput(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()) +
    "T" + pad(date.getHours()) + ":" + pad(date.getMinutes());
}

function fillTable(tbodyId, items, emptyText, columns, makeRow) {
  const tbody = $(tbodyId);
  tbody.replaceChildren();
  if (items.length === 0) {
    const td = cell(emptyText, "empty");
    td.colSpan = columns;
    tbody.append(row(td));
    return;
  }
  items.forEach((item) => tbody.append(makeRow(item)));
}

async function run(action) {
  try {
    await action();
  } catch (error) {
    if (error.status === 401) {
      $("session-bar").hidden = true;
      showView("auth-view");
    }
    toast(error.message, true);
  }
}

// ---------- Session ----------

async function loadSession() {
  let me;
  try {
    me = await api("GET", "/me");
  } catch (_) {
    $("session-bar").hidden = true;
    showView("auth-view");
    return;
  }
  $("who").textContent = me.email;
  $("role").textContent = ROLES[me.role] || me.role;
  $("session-bar").hidden = false;
  if (me.role === "DRIVER") { showView("driver-view"); await run(loadDriver); }
  else if (me.role === "ADMIN") { showView("admin-view"); await run(loadAdmin); }
  else { showView("support-view"); await run(loadSupport); }
}

function selectTab(name) {
  const login = name === "login";
  $("tab-login").setAttribute("aria-selected", String(login));
  $("tab-register").setAttribute("aria-selected", String(!login));
  $("login-form").hidden = !login;
  $("register-form").hidden = login;
}
$("tab-login").addEventListener("click", () => selectTab("login"));
$("tab-register").addEventListener("click", () => selectTab("register"));

$("login-form").addEventListener("submit", (event) => {
  event.preventDefault();
  run(async () => {
    await api("POST", "/login", formData(event.target));
    event.target.reset();
    await loadSession();
  });
});

$("register-form").addEventListener("submit", (event) => {
  event.preventDefault();
  run(async () => {
    const values = formData(event.target);
    const data = await api("POST", "/register", values);
    event.target.reset();
    selectTab("login");
    $("login-form").elements.email.value = values.email;
    $("login-form").elements.password.focus();
    toast(data.message, false);
  });
});

$("logout-button").addEventListener("click", () => {
  run(async () => {
    const data = await api("POST", "/logout", {});
    toast(data.message, false);
    await loadSession();
  });
});

// ---------- Driver ----------

let plates = {};

function setTicket(kind, bay, title, time, plateText) {
  const ticket = $("ticket");
  ticket.className = "ticket" + (kind ? " is-" + kind : "");
  $("ticket-bay").textContent = bay;
  $("ticket-title").textContent = title;
  $("ticket-time").textContent = time;
  $("ticket-plate").replaceChildren(plateText ? plate(plateText) : "");
}

function prefillTimes() {
  const start = new Date();
  start.setMinutes(0, 0, 0);
  start.setHours(start.getHours() + 1);
  const end = new Date(start.getTime() + 60 * 60 * 1000);
  if (!$("start-input").value) $("start-input").value = toLocalInput(start);
  if (!$("end-input").value) $("end-input").value = toLocalInput(end);
}

async function loadDriver() {
  const [{ vehicles }, { spots }, { reservations }, history, { disputes }] = await Promise.all([
    api("GET", "/vehicles"), api("GET", "/spots"), api("GET", "/reservations"),
    api("GET", "/parking-history"), api("GET", "/disputes"),
  ]);
  const sessions = history.parking_sessions;
  const now = Date.now();

  // Ticket: the car that is parked now, or the next reservation.
  const parked = sessions.find((s) => !s.exit);
  const next = reservations
    .filter((r) => new Date(r.end).getTime() > now)
    .sort((a, b) => new Date(a.start) - new Date(b.start))[0];
  plates = Object.fromEntries(vehicles.map((v) => [v.id, v.plate]));
  if (parked) {
    setTicket("parked", parked.spot, "Parked now", "Entered " + when(parked.entry), plates[parked.vehicle_id]);
  } else if (next) {
    const started = new Date(next.start).getTime() <= now;
    setTicket("", next.spot, started ? "Reservation in progress" : "Next reservation",
      when(next.start) + " to " + when(next.end), plates[next.vehicle_id]);
  } else {
    setTicket("empty", "–", "No upcoming reservations", "Reserve a bay below, and it will show here.", "");
  }

  // Vehicles
  const list = $("vehicle-list");
  list.replaceChildren();
  vehicles.forEach((v) => {
    const remove = el("button", "icon-btn");
    remove.type = "button";
    remove.setAttribute("aria-label", "Remove " + v.plate);
    remove.append(icon("i-close"));
    remove.addEventListener("click", () => run(async () => {
      const data = await api("DELETE", "/vehicles/" + v.id);
      toast(data.message, false);
      await loadDriver();
    }));
    const li = el("li");
    li.append(plate(v.plate), remove);
    list.append(li);
  });
  if (vehicles.length === 0) list.append(el("li", "muted", "No vehicles yet. Add your plate to reserve a bay."));

  const select = $("vehicle-select");
  select.replaceChildren(...vehicles.map((v) => new Option(plateText(v.plate), v.id)));

  // Free bays to choose from
  const picker = $("bay-picker");
  picker.replaceChildren();
  spots.forEach((s, i) => {
    const option = el("label", "bay-option");
    const input = el("input");
    input.type = "radio";
    input.name = "spot_id";
    input.value = s.id;
    input.required = true;
    if (i === 0) input.checked = true;
    option.append(input, el("span", "", s.label));
    picker.append(option);
  });
  if (spots.length === 0) picker.append(el("p", "empty", "No free bays right now."));
  prefillTimes();

  // Reservations: cancel is offered only while it is still allowed (FR-07).
  const cancelLimit = now + 30 * 60 * 1000;
  fillTable("reservation-rows", reservations, "No reservations yet.", 5, (r) => {
    const actions = cell("", "actions");
    if (new Date(r.start).getTime() > cancelLimit) {
      actions.append(button("Cancel", () => run(async () => {
        const data = await api("DELETE", "/reservations/" + r.id);
        toast(data.message, false);
        await loadDriver();
      })));
    }
    return row(cell(r.spot, "bay-cell"), cell(plate(plates[r.vehicle_id])),
               cell(when(r.start)), cell(when(r.end)), actions);
  });

  // Parking history: read only (SR-15).
  fillTable("history-rows", sessions, "No visits yet. The gate records each visit.", 4, (v) =>
    row(cell(v.spot, "bay-cell"), cell(plate(plates[v.vehicle_id])), cell(when(v.entry)),
        cell(v.exit ? when(v.exit) : badge("OCCUPIED", "Still parked"))));

  // Disputes (FR-15): only about this driver's own reservations and visits.
  const subjects = {};
  const subjectSelect = $("dispute-subject");
  subjectSelect.replaceChildren();
  reservations.forEach((r) => {
    subjects[r.id] = "Reservation, bay " + r.spot + ", " + when(r.start);
    subjectSelect.append(new Option(subjects[r.id], "reservation:" + r.id));
  });
  sessions.forEach((v) => {
    subjects[v.id] = "Visit, bay " + v.spot + ", " + when(v.entry);
    subjectSelect.append(new Option(subjects[v.id], "session:" + v.id));
  });
  const nothingToReport = subjectSelect.options.length === 0;
  if (nothingToReport) subjectSelect.append(new Option("No reservations or visits yet", ""));
  subjectSelect.disabled = nothingToReport;
  $("dispute-form").querySelector("button").disabled = nothingToReport;
  const reasonSelect = $("dispute-reason");
  if (reasonSelect.options.length === 0) {
    Object.entries(REASONS).forEach(([value, label]) => reasonSelect.append(new Option(label, value)));
  }
  fillTable("dispute-rows", disputes, "No disputes.", 5, (d) =>
    row(cell(subjects[d.record_id] || (d.about === "RESERVATION" ? "Reservation" : "Visit")),
        cell(REASONS[d.reason] || d.reason), cell(badge(d.status)),
        cell(when(d.opened)), cell(when(d.closed))));
}

$("vehicle-form").addEventListener("submit", (event) => {
  event.preventDefault();
  run(async () => {
    const data = await api("POST", "/vehicles", formData(event.target));
    event.target.reset();
    toast(data.message, false);
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
    toast(data.message + " A confirmation email is on its way.", false);   // NFR-03, FR-08
    await loadDriver();
  });
});

$("dispute-form").addEventListener("submit", (event) => {
  event.preventDefault();
  run(async () => {
    const values = formData(event.target);
    const [kind, id] = (values.subject || ":").split(":");
    const body = { reason: values.reason };
    if (kind === "reservation") body.reservation_id = id;
    else body.parking_session_id = id;
    const data = await api("POST", "/disputes", body);
    toast(data.message, false);
    await loadDriver();
  });
});

$("delete-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (!window.confirm("Delete your account and all its data? This cannot be undone.")) return;
  run(async () => {
    const data = await api("POST", "/account/delete", formData(event.target));
    event.target.reset();
    toast(data.message, false);
    await loadSession();
  });
});

// ---------- Admin ----------

let auditEntries = [];

function bayElement(s) {
  const status = s.status.toLowerCase();
  const bay = el("div", "bay bay-" + status);
  const space = el("div", "bay-space");
  if (s.status === "OCCUPIED") {
    space.append(icon("i-car", "bay-car"));
    space.setAttribute("aria-label", "Occupied");
  }
  const count = s.reserved_times.length;
  const meta = el("span", "bay-meta", count === 0 ? "No bookings" : count === 1 ? "1 booking" : count + " bookings");
  bay.append(el("span", "bay-label", s.label), space, meta);
  if (s.status !== "OCCUPIED") {
    const next = s.status === "FREE" ? "DISABLED" : "FREE";
    bay.append(button(next === "DISABLED" ? "Disable" : "Enable", () => run(async () => {
      await api("PATCH", "/admin/spots/" + s.id, { status: next });
      toast("Bay " + s.label + (next === "DISABLED" ? " disabled." : " enabled."), false);
      await loadAdmin();
    }), "btn-on-dark"));
  }
  return bay;
}

function renderLot(spots) {
  const counts = { FREE: 0, OCCUPIED: 0, DISABLED: 0 };
  spots.forEach((s) => { counts[s.status] = (counts[s.status] || 0) + 1; });
  const legend = $("lot-legend");
  legend.replaceChildren();
  [["FREE", "free"], ["OCCUPIED", "occupied"], ["DISABLED", "disabled"]].forEach(([code, name]) => {
    const li = el("li");
    li.append(el("span", "swatch swatch-" + name), counts[code] + " " + STATUS[code][0].toLowerCase());
    legend.append(li);
  });

  // Two rows of bays facing each other across the driving lane.
  const half = Math.ceil(spots.length / 2);
  const top = el("div", "lot-row lot-row-top");
  const bottom = el("div", "lot-row lot-row-bottom");
  top.style.setProperty("--bays", half);
  bottom.style.setProperty("--bays", half);
  spots.slice(0, half).forEach((s) => top.append(bayElement(s)));
  spots.slice(half).forEach((s) => bottom.append(bayElement(s)));
  $("lot-map").replaceChildren(top, el("div", "lot-lane"), bottom);
}

function renderAudit() {
  const filter = $("audit-filter").value;
  const entries = filter ? auditEntries.filter((e) => e.action === filter) : auditEntries;
  fillTable("audit-rows", entries, "No events.", 5, (e) => {
    const [label, kind] = EVENTS[e.action] || [e.action, ""];
    const event = el("span", "event");
    event.title = e.action;
    event.append(el("span", "dot" + (kind ? " dot-" + kind : "")), label);
    return row(cell(whenExact(e.time)), cell(event), cell(shortId(e.user_id)),
               cell(shortId(e.target_id)), cell(e.ip_address || "–"));
  });
}

async function loadAdmin() {
  const [{ spots }, { entries }] = await Promise.all([
    api("GET", "/admin/spots"), api("GET", "/admin/audit-log"),
  ]);
  renderLot(spots);

  fillTable("spot-rows", spots, "No bays.", 3, (s) => {
    const times = s.reserved_times.map((t) => when(t.start) + " to " + when(t.end));
    return row(cell(s.label, "bay-cell"), cell(badge(s.status)), cell(times.join("; ") || "None"));
  });

  auditEntries = entries;
  const filter = $("audit-filter");
  if (filter.options.length === 1) {
    Object.entries(EVENTS).forEach(([code, [label]]) => filter.append(new Option(label, code)));
  }
  renderAudit();
}

$("audit-filter").addEventListener("change", renderAudit);

// ---------- Support agent ----------

async function loadSupport() {
  const { disputes } = await api("GET", "/support/disputes");
  fillTable("open-dispute-rows", disputes, "No open disputes. Nothing to do right now.", 5, (d) => {
    const actions = cell("", "actions");
    actions.append(
      button("View driver data", () => run(() => showDriverData(d.driver_id))),
      button("Close dispute", () => run(async () => {
        const data = await api("POST", "/support/disputes/" + d.id + "/close", {});
        toast(data.message, false);
        $("driver-data").hidden = true;
        await loadSupport();
      }), "btn-primary btn-small"),
    );
    return row(cell(when(d.opened)), cell(shortId(d.driver_id)),
               cell(d.about === "RESERVATION" ? "Reservation" : "Visit"),
               cell(REASONS[d.reason] || d.reason), actions);
  });
}

// SR-09: the server answers only while the driver has an open dispute, and
// records every request in the audit log (NFR-08).
async function showDriverData(driverId) {
  $("driver-data").hidden = true;
  const data = await api("GET", "/support/drivers/" + encodeURIComponent(driverId));
  $("driver-data-id").textContent = data.driver_id.slice(0, 8);
  $("driver-data-id").title = data.driver_id;

  const owned = Object.fromEntries(data.vehicles.map((v) => [v.id, v.plate]));
  const list = $("driver-data-vehicles");
  list.replaceChildren(...data.vehicles.map((v) => { const li = el("li"); li.append(plate(v.plate)); return li; }));
  if (data.vehicles.length === 0) list.append(el("li", "muted", "No vehicles."));

  fillTable("driver-data-reservations", data.reservations, "No reservations.", 4, (r) =>
    row(cell(r.spot, "bay-cell"), cell(plate(owned[r.vehicle_id])), cell(when(r.start)), cell(when(r.end))));
  fillTable("driver-data-sessions", data.parking_sessions, "No visits.", 4, (v) =>
    row(cell(v.spot, "bay-cell"), cell(plate(owned[v.vehicle_id])), cell(when(v.entry)),
        cell(v.exit ? when(v.exit) : badge("OCCUPIED", "Still parked"))));
  $("driver-data").hidden = false;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  $("driver-data").scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
}

loadSession();
