/* Seat Signal website. No build step. Hash routing, so links, refresh and the back button all work.
   Every figure comes from the API; the browser only formats. */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const view = $("#view");

const DAYS = { weekday: "Weekday", saturday: "Saturday", sunday: "Sunday or holiday" };
const LEVELS = ["Comfortable", "Moderate", "Busy", "Packed"];
const FILL = { Comfortable: "--c1-fill", Moderate: "--c2-fill", Busy: "--c3-fill", Packed: "--c4-fill" };
const state = { live: true, day: "weekday", minute: 540, prefer: "balanced", liveSlot: null };

/* ---------- helpers ---------- */
const api = async (path) => {
  let r;
  try { r = await fetch(path); } catch { throw new Error("You are offline. Check your connection and try again."); }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "Something went wrong on our side.");
  return r.json();
};
const clock = (m) => { m = ((m % 1440) + 1440) % 1440; const h = Math.floor(m / 60), mm = m % 60; return `${(h % 12) || 12}:${String(mm).padStart(2, "0")} ${h < 12 ? "am" : "pm"}`; };
const short = (m) => clock(m).replace(":00", "");
const hhmm = (m) => `${String(Math.floor(m / 60) % 24).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
const toMin = (s) => { const [h, m] = s.split(":").map(Number); return h * 60 + m; };
const level = (c) => (c < 35 ? "Comfortable" : c < 60 ? "Moderate" : c < 80 ? "Busy" : "Packed");
const fillOf = (c) => css(FILL[level(c)]);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const inr = (n) => Number(n).toLocaleString("en-IN");
const rupees = (n) => `₹${Number(n) % 1 ? Number(n).toFixed(2) : Number(n)}`;
const every = (l) => l.every ? `a bus every ${plural(l.every, "minute")}` : l.wait_source === "timetable" ? "few buses at this time" : "timetable not known";
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
const q = () => `time=${hhmm(state.minute)}&day=${state.day}`;
/* A trip can be planned for its own day and time (in its link: #/plan?...&time=09:00&day=weekday).
   That never changes the app's clock, so Home and the rest stay live. */
function planWhen() {
  const p = new URLSearchParams(location.hash.split("?")[1] || ""), t = p.get("time"), d = p.get("day");
  if (t && /^\d{1,2}:\d{2}$/.test(t)) return { fixed: true, minute: toMin(t), day: DAYS[d] ? d : state.day };
  return { fixed: false, minute: state.minute, day: state.day };
}
const planQ = () => { const w = planWhen(); return `time=${hhmm(w.minute)}&day=${w.day}`; };
const enc = encodeURIComponent;

function nowIST() {
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", weekday: "short", hour12: false })
    .formatToParts(new Date()).map((x) => [x.type, x.value]));
  const minute = (Number(p.hour) % 24) * 60 + Number(p.minute);
  const day = p.weekday === "Sun" ? "sunday" : p.weekday === "Sat" ? "saturday" : "weekday";
  return { minute, day, weekday: p.weekday };
}

const store = {
  get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
};

/* ---------- components ---------- */
const IC = {
  plan: `<svg viewBox="0 0 24 24"><circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="M8.5 6H15a3 3 0 0 1 0 6H9a3 3 0 0 0 0 6h6.5"/></svg>`,
  clock: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>`,
  pulse: `<svg viewBox="0 0 24 24"><path d="M3 12h4l3-7 4 14 3-7h4"/></svg>`,
  bus: `<svg viewBox="0 0 24 24"><rect x="5" y="3" width="14" height="14" rx="2"/><path d="M5 11h14M8 21l1-4M16 21l-1-4"/></svg>`,
  pin: `<svg viewBox="0 0 24 24"><path d="M12 21s-6-5.6-6-11a6 6 0 0 1 12 0c0 5.4-6 11-6 11z"/><circle cx="12" cy="10" r="2"/></svg>`,
  seat: `<svg viewBox="0 0 24 24"><path d="M7 4v9a2 2 0 0 0 2 2h8M9 15l-1 5M16 15l1 5M7 9h3"/></svg>`,
  history: `<svg viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/></svg>`,
  chart: `<svg viewBox="0 0 24 24"><path d="M18 20V10M12 20V4M6 20v-6"/></svg>`,
  info: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5v.5"/></svg>`,
  alert: `<svg viewBox="0 0 24 24"><path d="M12 3l10 18H2z"/><path d="M12 10v4M12 17v.5"/></svg>`,
  walk: `<svg viewBox="0 0 24 24"><circle cx="13" cy="4" r="1.8"/><path d="M10 21l2-6 3 3v3M9 12l2-4 4 1 2 3M12 15l-1-5"/></svg>`,
  search: `<svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="6.5"/><path d="M20 20l-4.2-4.2"/></svg>`,
  dot: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/></svg>`,
  swap: `<svg viewBox="0 0 24 24"><path d="M7 4v14m0 0l-3-3m3 3l3-3M17 20V6m0 0l-3 3m3-3l3 3"/></svg>`,
  back: `<svg viewBox="0 0 24 24"><path d="M15 18l-6-6 6-6"/></svg>`,
};
const chev = `<svg class="chev" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>`;
/* Some "route numbers" are service names (CENTRAL_SECRETARIAT_LINK_SERVICE_PM_SANGRAHALAYA).
   Show them as words on two short lines of the board; the full name is in the title and the row text. */
const routeName = (num) => String(num).replace(/[_]+/g, " ").replace(/\s+/g, " ").trim();
const isLongRoute = (num) => routeName(num).length > 7;
const plate = (rt, size = "") => {
  const name = routeName(rt.number), long = name.length > 7;
  return `<span class="plate ${rt.ac ? "gold" : "silver"} ${size} ${long ? "long" : ""}" title="Route ${esc(name)}, ${rt.ac ? "AC" : "non-AC"}"><span>${esc(name)}</span></span>`;
};
const hallmark = (rt) => `<span class="hallmark ${rt.ac ? "gold" : "silver"}">${rt.ac ? "AC" : "Non-AC"}</span>`;
const pill = (lv) => `<span class="pill lv-${lv}">${lv}</span>`;
const loading = `<div class="state" role="status"><span class="spinner dark"></span><p>Loading</p></div>`;
const errorBox = (msg) => /^Unknown (route|stop)/.test(msg)
  ? `<div class="state">${IC.search.replace("<svg", '<svg style="stroke:var(--muted)"')}<b class="t-strong">We don't know that ${msg.includes("stop") ? "stop" : "route"}</b><p>The link may be old, or the ${msg.includes("stop") ? "stop's name" : "route number"} may have changed.</p><a class="btn secondary" href="${msg.includes("stop") ? "#/stops" : "#/routes"}">${msg.includes("stop") ? "Find a stop" : "Find a route"}</a></div>`
  : `<div class="state"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16.5v.5"/></svg><b class="t-strong">That didn't load</b><p>${esc(msg)}</p><button class="btn secondary" onclick="render()">Try again</button></div>`;
const notice = (kind, title, text, icon = IC.info) => `<div class="notice ${kind}" role="status">${icon}<div>${title ? `<b>${title}</b>` : ""}<p>${text}</p></div></div>`;
const backBtn = (href) => `<a class="back" href="${href}" aria-label="Back" onclick="if(history.length>1){history.back();return false}">${IC.back}</a>`;
const field = (id, label, placeholder, icon, key = "search") => `<label class="field"><span class="t-small-strong">${label}</span>
  <span class="input">${icon}<input id="${id}" placeholder="${placeholder}" autocomplete="off" autocorrect="off" autocapitalize="words" spellcheck="false" enterkeyhint="${key}" /></span><span class="hint t-small muted"></span></label>`;

/* Seat meter: 12 blocks. More blocks lit = better chance of a seat when you board; their colour
   is the crowd level where you board (green comfortable, yellow moderate, orange busy, red packed). */
function seatMeter(o) {
  const board = o.legs[0].profile[0] ?? o.crowd;          // how full the bus is where you get on
  const n = 12, on = Math.max(1, Math.round((o.seat_chance / 100) * n)), c = fillOf(board);
  return `<div class="meter" role="img" aria-label="${level(board)} when you board, ${o.seat_chance}% chance of a seat">${Array.from({ length: n }, (_, i) => `<i style="${i < on ? `background:${c}` : ""}"></i>`).join("")}</div>`;
}

function lineChart(svg, series, { max, marker } = {}) {
  if (!svg) return;
  const { width: w, height: h } = svg.viewBox.baseVal, pad = 6;
  max = max || Math.max(...series.flatMap((s) => s.values), 1);
  let out = "";
  series.forEach((s) => {
    const n = s.values.length;
    const pts = s.values.map((v, i) => [(i / (n - 1)) * w, h - pad - (v / max) * (h - pad * 2)]);
    const d = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
    if (s.fill) out += `<path d="${d} L${w},${h} L0,${h} Z" fill="${s.color}" fill-opacity="${s.fill}"/>`;
    out += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="${s.width || 2}" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>`;
    if (s.marker && marker != null && marker >= 0 && marker < n) {
      const [mx, my] = pts[marker];
      out += `<line x1="${mx}" x2="${mx}" y1="0" y2="${h}" stroke="${css("--line")}" vector-effect="non-scaling-stroke"/>`;
      out += `<circle cx="${mx}" cy="${my}" r="5" fill="${css("--surface")}" stroke="${s.color}" stroke-width="2.5" vector-effect="non-scaling-stroke"/>`;
    }
  });
  svg.innerHTML = out;
}

/* Interactive line chart: a dot you can drag, hover or move with the arrow keys to read any
   time. Reading a chart never changes the app's time; only the time button does. */
function iChart(svg, series, { max, index, describe, onMove, hint } = {}) {
  if (!svg) return null;
  lineChart(svg, series, { max });
  const main = series.find((s) => s.marker) || series[series.length - 1];
  const n = main.values.length, { height: h } = svg.viewBox.baseVal, pad = 6;
  max = max || Math.max(...series.flatMap((s) => s.values), 1);
  const host = document.createElement("div"); host.className = "ichart";
  svg.parentNode.insertBefore(host, svg); host.appendChild(svg);
  host.insertAdjacentHTML("beforeend", `<span class="ic-line"></span><span class="ic-dot"></span><span class="ic-tip" role="status" aria-live="polite"></span>`);
  const line = $(".ic-line", host), dot = $(".ic-dot", host), tip = $(".ic-tip", host);
  host.tabIndex = 0; host.setAttribute("role", "slider");
  host.setAttribute("aria-label", hint || "Chart. Use the arrow keys to move through the day.");
  host.setAttribute("aria-valuemin", 0); host.setAttribute("aria-valuemax", n - 1);
  // home = the app's time; rest = where a tap, drag or arrow key left the dot (it stays there)
  let cur = Math.max(0, Math.min(n - 1, index ?? 0)), home = cur, rest = cur, dragging = false;
  const place = (i, showTip) => {
    cur = Math.max(0, Math.min(n - 1, i));
    const x = (cur / (n - 1)) * 100, y = ((h - pad - (main.values[cur] / max) * (h - pad * 2)) / h) * 100;
    line.style.left = dot.style.left = `${x}%`; dot.style.top = `${y}%`;
    tip.innerHTML = describe(cur);
    const W = host.clientWidth, tw = tip.offsetWidth, px = (x / 100) * W;
    tip.style.left = `${Math.max(0, Math.min(W - tw, px - tw / 2))}px`;
    tip.classList.toggle("show", !!showTip);
    host.setAttribute("aria-valuenow", cur); host.setAttribute("aria-valuetext", tip.textContent);
    host.classList.toggle("moved", cur !== home);
    onMove?.(cur, cur === home);
  };
  const fromEvent = (e) => { const r = host.getBoundingClientRect(); return Math.round(((e.clientX - r.left) / r.width) * (n - 1)); };
  host.addEventListener("pointerdown", (e) => { dragging = true; host.setPointerCapture(e.pointerId); place(fromEvent(e), true); });
  host.addEventListener("pointermove", (e) => { if (dragging || e.pointerType === "mouse") place(fromEvent(e), true); });
  host.addEventListener("pointerup", (e) => { if (!dragging) return; dragging = false; place(fromEvent(e), true); rest = cur; });
  host.addEventListener("pointercancel", () => { dragging = false; place(rest, false); });
  host.addEventListener("pointerleave", () => { if (!dragging) place(rest, false); });
  host.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") { place(cur + (e.key === "ArrowRight" ? 1 : -1), true); rest = cur; e.preventDefault(); }
    if (e.key === "Home" || e.key === "Escape") { rest = home; place(home, false); }
  });
  host.addEventListener("blur", () => place(rest, false));
  place(cur, false);
  return { reset: () => { rest = home; place(home, false); } };
}

/* The crowd index card: follows the chart, so tapping 7:30 am shows 7:30 am's number and level. */
function crowdIndexCard(root, p, { slot0 = 10 } = {}) {
  const curve = p.curve;
  const homeSlot = Math.floor(state.minute / 30);
  const trend = (s) => {
    const d = curve[s] - curve[(s + 47) % 48];
    return Math.abs(d) < 2 ? "About as busy as half an hour before." : d < 0 ? "Calmer than half an hour before." : "Busier than half an hour before.";
  };
  return (i, atHome) => {
    const s = atHome ? homeSlot : i + slot0, v = atHome ? p.network_index : curve[s];
    $(".ci-when", root).textContent = atHome ? (state.live ? "live" : clock(state.minute)) : clock(s * 30);
    $(".ci-num", root).textContent = v;
    $(".ci-pill", root).innerHTML = pill(level(v));
    $(".ci-line", root).textContent = `${trend(s)} Busiest at ${clock(toMin(p.peak_time))}.`;
    $(".ci-back", root).hidden = atHome;
  };
}

/* Set a planned time from any chart and refresh the page around it. */
function setTime(minute, day) {
  state.live = false; state.minute = ((minute % 1440) + 1440) % 1440; if (day) state.day = day;
  updateWhen(); render({ quiet: true });
}
const liveLink = () => state.live ? "" : `<button class="link t-small-strong" onclick="goLive();render({quiet:true})">Back to live time</button>`;

/* Heat strip of half hours: hover or tap to read a half hour. */
function heatStrip(values, { slot0 = 10, now, label = "crowding" } = {}) {
  return `<div class="heat" role="group" aria-label="Crowding through the day. Tap a half hour to read it.">${values.map((v, i) =>
    `<button type="button" class="${i === now ? "now" : ""}" data-m="${(i + slot0) * 30}" data-v="${v}" aria-label="${clock((i + slot0) * 30)}, ${label} ${v}" style="background:${fillOf(v)};opacity:${(0.3 + (v / 100) * 0.7).toFixed(2)}"></button>`).join("")}</div>
    <p class="heat-read t-small muted">Tap a half hour to read it.</p>`;
}
function wireHeat(root = view) {
  $$(".heat", root).forEach((hm) => {
    const read = hm.nextElementSibling;
    const say = (b) => { read.innerHTML = `<b class="tnum" style="color:var(--ink)">${clock(+b.dataset.m)}</b> · crowding ${b.dataset.v}, ${level(+b.dataset.v).toLowerCase()}`; };
    $$("button", hm).forEach((b) => {
      b.onmouseenter = b.onfocus = b.onclick = () => say(b);
    });
    hm.onmouseleave = () => (read.textContent = "Tap a half hour to read it.");
  });
}

const routeRow = (r, sub) => `<a class="row" href="#/route/${enc(r.id)}" style="text-decoration:none;color:inherit">${plate(r)}
  <span class="row-main"><b>Towards ${esc(r.towards)}</b><small>${sub ?? `${r.ac ? "AC" : "Non-AC"} · route ${esc(routeName(r.number))}`}</small></span>
  <span class="row-value"><b class="tnum">${r.crowd}</b>${pill(r.level)}</span>${chev}</a>`;

/* ---------- stop search (autocomplete) ---------- */
function autocomplete(input, onPick) {
  const fieldEl = input.closest(".field"), inputEl = input.closest(".input");
  const box = document.createElement("div"); box.className = "suggest card"; box.setAttribute("role", "listbox");
  box.id = `${input.id}-list`; box.setAttribute("aria-label", "Matching stops"); inputEl.appendChild(box);
  input.setAttribute("role", "combobox"); input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-controls", box.id); input.setAttribute("aria-expanded", "false");
  let items = [], hl = 0, timer;
  const close = () => { box.classList.remove("show"); input.setAttribute("aria-expanded", "false"); input.removeAttribute("aria-activedescendant"); };
  const pick = (s) => { input.value = s.name; input.dataset.key = s.key; fieldEl.classList.remove("error"); close(); onPick?.(s); };
  const draw = () => {
    box.innerHTML = items.length ? items.map((s, i) => `<button type="button" role="option" id="${box.id}-${i}" aria-selected="${i === hl}" tabindex="-1" class="row ${i === hl ? "hl" : ""}" data-i="${i}"><span class="pin">${IC.pin}</span><span class="row-main"><b>${esc(s.name)}</b><small>${plural(s.routes, "route")} · ${inr(s.volume)} trips in October</small></span></button>`).join("")
      : `<div class="row-empty">No stop by that name. Try part of it, such as "Saket".</div>`;
    $$("[data-i]", box).forEach((b) => (b.onmousedown = (e) => { e.preventDefault(); pick(items[+b.dataset.i]); }));
    box.classList.add("show"); input.setAttribute("aria-expanded", "true");
    if (items.length) input.setAttribute("aria-activedescendant", `${box.id}-${hl}`); else input.removeAttribute("aria-activedescendant");
  };
  input.addEventListener("input", () => {
    delete input.dataset.key; clearTimeout(timer);
    if (!input.value.trim()) return close();
    timer = setTimeout(async () => { try { items = await api(`/api/stops?q=${enc(input.value)}`); hl = 0; draw(); } catch { close(); } }, 140);
  });
  input.addEventListener("blur", () => setTimeout(close, 120));
  input.addEventListener("keydown", (e) => {
    if (!box.classList.contains("show")) return;
    if (e.key === "ArrowDown") { hl = Math.min(items.length - 1, hl + 1); draw(); e.preventDefault(); }
    if (e.key === "ArrowUp") { hl = Math.max(0, hl - 1); draw(); e.preventDefault(); }
    if (e.key === "Enter" && items[hl]) { pick(items[hl]); e.preventDefault(); e.stopPropagation(); }
    if (e.key === "Escape") close();
  });
}

async function stopFromInput(input) {
  if (input.dataset.key) return { key: input.dataset.key, name: input.value };
  if (!input.value.trim()) return null;
  const [s] = await api(`/api/stops?q=${enc(input.value)}&limit=1`);
  if (s) { input.value = s.name; input.dataset.key = s.key; }
  return s || null;
}
function setStop(input, s) { if (s) { input.value = s.name; input.dataset.key = s.key; } }
async function stopByKey(key) { if (!key) return null; const [s] = await api(`/api/stops?q=${enc(key)}&limit=1`); return s?.key === key ? s : s || null; }
function fieldError(input, msg) { const f = input.closest(".field"); f.classList.add("error"); f.querySelector(".hint").textContent = msg; input.focus(); }

/* form with From / Swap / To used on Home, Plan and Best time */
function odForm({ prefix, from, to }) {
  return `${field(`${prefix}-from`, "From", "Search a stop", IC.dot, "next")}
    <button type="button" class="swap quiet t-small-strong" id="${prefix}-swap">${IC.swap}Swap</button>
    ${field(`${prefix}-to`, "To", "Search a stop", IC.pin)}`;
}
function wireOD(prefix, { from, to } = {}) {
  const fi = $(`#${prefix}-from`), ti = $(`#${prefix}-to`);
  autocomplete(fi, () => !ti.dataset.key && ti.focus()); autocomplete(ti);
  setStop(fi, from); setStop(ti, to);
  $(`#${prefix}-swap`).onclick = () => {
    const a = { v: fi.value, k: fi.dataset.key }, b = { v: ti.value, k: ti.dataset.key };
    fi.value = b.v; ti.value = a.v;
    b.k ? (fi.dataset.key = b.k) : delete fi.dataset.key; a.k ? (ti.dataset.key = a.k) : delete ti.dataset.key;
  };
  return async () => {
    const [f, t] = [await stopFromInput(fi), await stopFromInput(ti)];
    if (!f) { fieldError(fi, "Choose where you are starting from."); return null; }
    if (!t) { fieldError(ti, "Choose where you are going."); return null; }
    if (f.key === t.key) { fieldError(ti, "Choose a different stop from where you start."); return null; }
    return { from: f, to: t };
  };
}

function saveRecent(from, to) {
  const list = store.get("ss-recent", []).filter((r) => !(r.from.key === from.key && r.to.key === to.key));
  list.unshift({ from: { key: from.key, name: from.name }, to: { key: to.key, name: to.name } });
  store.set("ss-recent", list.slice(0, 5));
}
function recentHTML(title = "Recent trips") {
  const list = store.get("ss-recent", []);
  if (!list.length) return "";
  return `<div class="section-title"><h3 class="t-heading">${title}</h3></div><div class="card rows">${list.map((r) => `<a class="row" style="text-decoration:none;color:inherit" href="#/plan?from=${enc(r.from.key)}&to=${enc(r.to.key)}"><span class="pin">${IC.history}</span><span class="row-main"><b>${esc(r.to.name)}</b><small>from ${esc(r.from.name)}</small></span>${chev}</a>`).join("")}</div>`;
}

/* ---------- live time ---------- */
function updateWhen() {
  const n = nowIST();
  $("#when-dot").classList.toggle("off", !state.live);
  $("#when-tag").classList.toggle("off", !state.live);
  $("#when-tag").textContent = state.live ? "Live" : "Planned";
  const dayWord = state.live ? n.weekday : state.day === "sunday" ? "Sun" : state.day === "saturday" ? "Sat" : "Weekday";
  $("#when-label").textContent = `${dayWord} ${clock(state.minute)}`;
}
function tick() {
  if (!state.live) return updateWhen();
  const n = nowIST();
  const slotChanged = Math.floor(n.minute / 30) !== state.liveSlot || n.day !== state.day;
  state.minute = n.minute; state.day = n.day; state.liveSlot = Math.floor(n.minute / 30);
  updateWhen();
  if (slotChanged) render({ quiet: true });   // new half hour: crowding has moved on
}
function goLive() { state.live = true; state.liveSlot = null; tick(); }

function setupWhen() {
  const range = $("#time-range"), big = $("#time-big");
  const paint = () => { big.textContent = clock(+range.value); range.style.setProperty("--p", `${((range.value - 300) / 1110) * 100}%`); };
  const close = () => { $("#scrim").classList.remove("show"); $("#dialog-when").classList.remove("show"); };
  $("#when").onclick = () => {
    range.value = Math.max(300, Math.min(1410, state.minute)); paint();
    $$("#seg-day button").forEach((b) => b.classList.toggle("on", b.dataset.v === state.day));
    $("#when-live").hidden = state.live;
    $("#scrim").classList.add("show"); $("#dialog-when").classList.add("show");
  };
  range.oninput = paint;
  $$("#seg-day button").forEach((b) => (b.onclick = () => $$("#seg-day button").forEach((x) => x.classList.toggle("on", x === b))));
  $("#when-cancel").onclick = close; $("#scrim").onclick = close;
  document.addEventListener("keydown", (e) => e.key === "Escape" && close());
  $("#when-done").onclick = () => {
    state.live = false; state.minute = +range.value; state.day = $("#seg-day button.on")?.dataset.v || state.day;
    close(); updateWhen(); render({ quiet: true });
  };
  $("#when-live").onclick = () => { close(); goLive(); render({ quiet: true }); };
}

/* ================================================================= maps
   Leaflet (bundled in /vendor/leaflet) on a light CARTO basemap of OpenStreetMap data.
   Lines are coloured stretch by stretch with the same crowd colours as everywhere else. */
const DELHI = [28.62, 77.2];
const liveMaps = [];
let stopsCache = null, configCache = null;
const mapConfig = () => (configCache ||= api("/api/config").catch(() => ({ carto_key: "" })));
/* Some stops share exactly the same spot under two names ("Nehru Place Terminal" and "Nehru Place Bus Terminal").
   Show one dot there, the busiest, so a tap opens the stop people mean. */
const allStops = () => (stopsCache ||= api("/api/stops/map").then((rows) => {
  const seen = new Set();
  return rows.map(([key, name, lat, lon, volume, routes]) => ({ key, name, lat, lon, volume, routes }))
    .sort((a, b) => b.volume - a.volume)
    .filter((s) => { const k = `${s.lat.toFixed(4)},${s.lon.toFixed(4)}`; return seen.has(k) ? false : seen.add(k); });
}));
const mapsReady = () => typeof L !== "undefined";

function makeMap(el, { center = DELHI, zoom = 11 } = {}) {
  if (!mapsReady() || !el) { if (el) el.innerHTML = `<div class="state"><b class="t-strong">Map unavailable</b><p>The map library didn't load.</p></div>`; return null; }
  const m = L.map(el, { center, zoom, zoomSnap: 0.5, scrollWheelZoom: false, attributionControl: true });   // lines as SVG: only the lines catch taps, stops below stay tappable
  mapConfig().then(({ carto_key: key }) => alive(m) && L.tileLayer(`https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png${key ? `?key=${encodeURIComponent(key)}` : ""}`, {
    subdomains: "abcd", maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
  }).addTo(m));
  m.attributionControl.setPrefix(false);
  // wheel zoom only once someone has clicked into the map, so the page still scrolls
  m.once("focus click", () => m.scrollWheelZoom.enable());
  liveMaps.push(m);
  return m;
}
const alive = (m) => liveMaps.includes(m);     // false once the page has moved on and the map is gone
function dropMaps() {
  while (liveMaps.length) {
    const m = liveMaps.pop();
    // a map removed mid zoom animation would finish the animation on nothing: mark it done first
    try { m.stop(); m._animatingZoom = false; m.remove(); } catch {}
  }
}

/* What a crowd level means for a rider, in words (the index alone, "0", reads like an error). */
const READ_HINT = "Hover over or tap the line to see how full each stretch is.";
const SEATS = { Comfortable: "seats likely", Moderate: "a seat is possible", Busy: "you may stand", Packed: "expect to stand" };
const stretchText = (a, b, v) => v == null ? `${esc(a)} to ${esc(b)}`
  : `<b>${esc(a)}</b> to <b>${esc(b)}</b><br><span style="color:${fillOf(v)};font-weight:600">${level(v)}</span> · ${SEATS[level(v)]} <span class="muted">(index ${Math.round(v)})</span>`;

/* Stop dots are DOM markers with a fixed size in CSS, so they stay the same size while zooming. */
const dotIcon = (kind = "stop") => L.divIcon({ className: `sdot sdot-${kind}`, iconSize: null, html: "" });

function stopPopup(s, { pick } = {}) {
  const box = document.createElement("div"); box.className = "map-pop";
  box.innerHTML = `<b>${esc(s.name)}</b>${s.routes ? `<small>${plural(s.routes, "route")}${s.volume ? ` · ${inr(s.volume)} trips in October` : ""}</small>` : ""}
    <div class="map-pop-btns">${pick
      ? `<button type="button" class="btn secondary" data-w="from">Start here</button><button type="button" class="btn primary" data-w="to">Go here</button>`
      : `<a class="btn secondary" href="#/plan?from=${enc(s.key)}">Plan from here</a><a class="btn secondary" href="#/plan?to=${enc(s.key)}">Plan to here</a>`}</div>
    <a class="link t-small-strong" href="#/stop/${enc(s.key)}">See every bus at this stop</a>`;
  if (pick) $$("button", box).forEach((b) => (b.onclick = () => pick(b.dataset.w, s)));
  return box;
}

/* Every known stop, drawn only where you are looking (keeps thousands of stops fast).
   Big stops from zoom 13, all stops from zoom 15. */
async function stopsLayer(m, { pick } = {}) {
  if (!m.getPane("stops")) { m.createPane("stops"); m.getPane("stops").style.zIndex = 590; }
  const list = await allStops();
  if (!alive(m)) return list;                    // the page changed while the stops were loading
  const group = L.layerGroup().addTo(m), shown = new Map();
  const sync = () => {
    if (!alive(m)) return;
    const z = m.getZoom(), bounds = m.getBounds().pad(0.15);
    const want = z < 13 ? [] : list.filter((s, i) => (z >= 15 || i < 400) && bounds.contains([s.lat, s.lon])).slice(0, 900);
    const keep = new Set(want.map((s) => s.key));
    for (const [k, mk] of shown) if (!keep.has(k)) { group.removeLayer(mk); shown.delete(k); }
    want.forEach((s) => {
      if (shown.has(s.key)) return;
      const mk = L.marker([s.lat, s.lon], { icon: dotIcon("bg"), pane: "stops", keyboard: false, riseOnHover: true })
        .bindTooltip(esc(s.name), { direction: "auto", offset: [0, -6] })
        .bindPopup(() => stopPopup(s, { pick }), { offset: [0, -4], maxWidth: 260 });
      group.addLayer(mk); shown.set(s.key, mk);
    });
  };
  m.on("moveend zoomend", sync); sync();
  return list;
}

/* Draw one ride (a leg, or a whole route): white casing, crowd-coloured stretches you can hover
   and tap, fixed-size stop dots. Returns handles to recolour it and to highlight a stop. */
function drawRide(layer, shape, profile, names, { ends = true, keys = [], map = null, stopInfo = null, readout = null } = {}) {
  const segs = shape.segments || [], dash = null, lines = [], dots = [];   // solid lines even where the path is approximate
  segs.forEach((pts) => pts.length > 1 && L.polyline(pts, { color: "#fff", weight: 10, opacity: 0.95, lineCap: "round", interactive: false }).addTo(layer));
  segs.forEach((pts, k) => {
    if (pts.length < 2) { lines.push(null); return; }
    const pl = L.polyline(pts, { color: profile[k] != null ? fillOf(profile[k]) : css("--brand"), weight: 6, opacity: 1, lineCap: "round", dashArray: dash, className: "ride-line" });
    const show = () => { if (readout) { readout.innerHTML = stretchText(names[k], names[k + 1], pl._v); readout.classList.add("on"); } };
    pl.on("mouseover", () => { pl.setStyle({ weight: 10 }); show(); })
      .on("mouseout", () => { pl.setStyle({ weight: 6 }); if (readout) { readout.textContent = READ_HINT; readout.classList.remove("on"); } })
      .on("click", show);                    // phones: tap a stretch to read it
    pl._v = profile[k];
    pl.addTo(layer); lines.push(pl);
  });
  const mids = L.featureGroup();
  (shape.stops || []).forEach((p, k) => {
    if (!p) { dots.push(null); return; }
    const end = k === 0 || k === shape.stops.length - 1;
    if (end && !ends) { dots.push(null); return; }
    const mk = L.marker(p, { icon: dotIcon(end ? "end" : "mid"), keyboard: false, riseOnHover: true, zIndexOffset: end ? 500 : 0 })
      .bindTooltip(esc(names[k]), { direction: "auto", offset: [0, -7] });
    if (keys[k]) mk.bindPopup(() => stopPopup(stopInfo?.(k) || { key: keys[k], name: names[k] }), { offset: [0, -6], maxWidth: 260 });
    mk.addTo(end ? layer : mids); dots.push(mk);
  });
  if (map) {   // stop dots along the line appear once zoomed in, so the overview stays a clean line
    const sync = () => (map.getZoom() >= 10 ? layer.addLayer(mids) : layer.removeLayer(mids));
    map.on("zoomend", sync); sync();
    (layer._syncs ||= []).push(() => map.off("zoomend", sync));
  } else layer.addLayer(mids);
  return {
    recolour(values) { lines.forEach((pl, k) => { if (pl && values[k] != null) { pl._v = values[k]; pl.setStyle({ color: fillOf(values[k]) }); } }); },
    highlight(k, on) {
      const mk = dots[k]; if (!mk || !map) return;
      if (on && !map.hasLayer(mk)) { map.addLayer(mk); mk._temp = true; }       // zoomed out: show just this one
      mk.getElement()?.classList.toggle("sdot-hl", on);
      if (on) { mk.openTooltip(); if (!map.getBounds().pad(-0.1).contains(mk.getLatLng())) map.panTo(mk.getLatLng()); }
      else { mk.closeTooltip(); if (mk._temp && !map.hasLayer(mids)) map.removeLayer(mk); mk._temp = false; }
    },
  };
}
function clearRides(layer) { (layer._syncs || []).forEach((off) => off()); layer._syncs = []; layer.clearLayers(); }
function fitTo(m, layer, pad = 28) {
  const b = layer.getBounds?.();
  if (b && b.isValid()) m.fitBounds(b, { padding: [pad, pad], maxZoom: 15 });
}
/* A small map button: "Show whole route", "Show whole trip". */
function fitControl(m, label, fn) {
  const C = L.Control.extend({ onAdd() { const b = L.DomUtil.create("button", "map-btn"); b.type = "button"; b.textContent = label; L.DomEvent.disableClickPropagation(b); b.onclick = fn; return b; } });
  const c = new C({ position: "topright" }); c.addTo(m); return c;
}
const mapKey = (extra = "") => `<div class="map-key t-caption">${LEVELS.map((l) => `<span><i style="background:${css(FILL[l])}"></i>${l}</span>`).join("")}${extra}</div>`;

/* ================================================================= pages */

/* What the citywide crowd level means for getting a seat, in plain words. */
function comfortLine(lvl) {
  const day = { weekday: "a weekday", saturday: "Saturday", sunday: "a Sunday or holiday" }[state.day];
  const when = state.live ? "right now" : `on ${day} at ${clock(state.minute)}`;
  return {
    Comfortable: `Buses are quiet ${when}, so you have a good chance of getting a seat.`,
    Moderate: `Buses are fairly busy ${when}. You'll often get a seat, but not on every route.`,
    Busy: `Buses are busy ${when}, so you may have to stand for part of the way.`,
    Packed: `Buses are packed ${when}. Expect to stand, or check a calmer time to travel.`,
  }[lvl] || "";
}

async function pageHome() {
  const n = nowIST();
  const greet = n.minute < 720 ? "Good morning" : n.minute < 1020 ? "Good afternoon" : "Good evening";
  view.innerHTML = `<div class="page">
    <p class="hello" id="hello">${greet}.</p>
    <div class="home-top">
      <form class="card plan-card" id="home-form" novalidate>
        <h1 class="t-title">Where are you going?</h1>
        <div class="plan-grid">${odForm({ prefix: "h" })}<button class="btn primary" type="submit">Show buses</button></div>
        <div class="chips-row try"><span class="t-small muted">Try</span>${TRY_TRIPS.map(([a, b, t]) => `<a class="chip" href="#/plan?from=${enc(a)}&to=${enc(b)}">${t}</a>`).join("")}</div>
      </form>
      <div class="card live-card" id="live-card">${loading}</div>
    </div>
    <div class="section-title"><h2 class="t-heading">What would you like to do?</h2></div>
    <div class="tiles">
      ${tile("#/plan", IC.plan, "Plan a trip", "Buses between two stops, with crowding")}
      ${tile("#/best", IC.clock, "Best time to travel", "When your trip is calmest")}
      ${tile("#/crowd", IC.pulse, "Crowd right now", "How busy Delhi's buses are")}
      ${tile("#/routes", IC.bus, "Find a route", "Look up any bus number")}
      ${tile("#/stops", IC.pin, "Stop information", "Every bus at a stop")}
      ${tile("#/crowd", IC.seat, "Seats free", "Big routes with room right now")}
      ${tile("#/plan", IC.history, "Recent trips", store.get("ss-recent", []).length ? "Trips you searched before" : "Your searches will appear here")}
      ${tile("#/about", IC.chart, "How we know", "The data behind every number")}
    </div>
    <div class="two-col" id="home-lists"></div>
  </div>`;
  const submit = wireOD("h");
  $("#home-form").onsubmit = async (e) => { e.preventDefault(); const r = await submit(); if (r) location.hash = `#/plan?from=${enc(r.from.key)}&to=${enc(r.to.key)}`; };
  try {
    const p = await api(`/api/pulse?${q()}`);
    const slot = Math.floor(state.minute / 30) - 10;
    $("#hello").textContent = `${greet}. ${comfortLine(p.level)}`;
    $("#live-card").innerHTML = `
      <div class="chart-head"><span class="t-small-strong muted">Delhi bus crowd index · <span class="ci-when"></span></span><span class="ci-pill"></span></div>
      <div class="figure"><span class="t-display tnum ci-num"></span><span class="t-body muted">out of 100</span></div>
      <p class="t-small muted ci-line"></p>
      <svg class="chart" id="home-chart" viewBox="0 0 340 84" preserveAspectRatio="none" role="img" aria-label="Crowd index through the day"></svg>
      <div class="live-foot"><span class="t-caption muted">Tap or drag the line to see any time</span><button type="button" class="link t-small-strong ci-back" hidden>Back to ${state.live ? "now" : clock(state.minute)}</button>${liveLink() || `<a class="link t-small-strong" href="#/crowd">See crowding now</a>`}</div>`;
    const curve = p.curve.slice(10, 47), card = $("#live-card");
    const ch = iChart($("#home-chart"), [{ values: curve, color: css("--brand"), fill: 0.07, marker: true }], { max: 100, index: slot,
      describe: (i) => `<b>${clock((i + 10) * 30)}</b> · ${curve[i]} · ${level(curve[i])}`, onMove: crowdIndexCard(card, p),
      hint: "Delhi bus crowd index through the day. Use the arrow keys to read any time." });
    $(".ci-back", card).onclick = () => ch.reset();
    $("#home-lists").innerHTML = `
      <div><div class="section-title"><h3 class="t-heading">${state.live ? "Busiest right now" : `Busiest at ${clock(state.minute)}`}</h3><a class="link t-small-strong" href="#/crowd">See all</a></div>
        <div class="card rows">${p.busiest.slice(0, 4).map((r) => routeRow(r)).join("")}</div></div>
      <div><div class="section-title"><h3 class="t-heading">Better chance of a seat</h3><a class="link t-small-strong" href="#/crowd">See all</a></div>
        <div class="card rows">${p.calmest.slice(0, 4).map((r) => routeRow(r)).join("")}</div></div>`;
  } catch (e) { $("#live-card").innerHTML = errorBox(e.message); }
}
const tile = (href, icon, title, sub) => `<a class="tile" href="${href}"><span class="tile-ic">${icon}</span><span><b>${title}</b><small>${sub}</small></span></a>`;

/* ---------- plan ---------- */
async function pagePlan(params) {
  view.innerHTML = `<div class="page">
    <div class="page-head"><div><h1 class="t-title">Plan a trip</h1><p class="t-small muted">Compare buses by travel time and how crowded they'll be.</p></div></div>
    <div class="split">
      <div class="side">
        <form class="card form-card" id="plan-form" novalidate>
          ${odForm({ prefix: "p" })}
          <p class="t-small-strong label">Leaving</p>
          <div class="segmented" id="seg-when"><button type="button" data-v="now">Now</button><button type="button" data-v="later">Later</button></div>
          <div class="when-pick" id="when-pick" hidden>
            <div class="segmented" id="seg-pday"><button type="button" data-v="weekday">Weekday</button><button type="button" data-v="saturday">Saturday</button><button type="button" data-v="sunday">Sunday or holiday</button></div>
            <label class="field"><span class="t-small-strong">Time</span><span class="input">${IC.clock}<input type="time" id="p-time" min="05:00" max="23:30" step="300" /></span></label>
          </div>
          <p class="t-small-strong label">Sort by</p>
          <div class="segmented" id="seg-prefer"><button type="button" data-v="balanced">Balanced</button><button type="button" data-v="fastest">Fastest</button><button type="button" data-v="comfort">Calmest</button><button type="button" data-v="cheapest">Cheapest</button></div>
          <button class="btn primary" type="submit" id="plan-btn">Show buses</button>
        </form>
        <div id="plan-map-home"><div class="card map-card" id="plan-map-card">
          <div class="map-head"><span class="t-small-strong" id="plan-map-title">Pick stops on the map</span><button type="button" class="link t-small-strong" id="near-me">Near me</button></div>
          <div class="map" id="plan-map" role="region" aria-label="Map for choosing stops and seeing your trip"></div>
          <p class="map-read t-small" id="plan-map-read" aria-live="polite">${READ_HINT}</p>
          <div id="plan-map-key"><p class="t-caption muted map-hint">Zoom in to see the stops, then tap one to start or end your trip there.</p></div>
        </div></div>
        <div id="plan-recent">${recentHTML()}</div>
      </div>
      <div id="results">${params.get("from") && params.get("to") ? loading : startHint()}</div>
    </div></div>`;
  $$("#seg-prefer button").forEach((b) => {
    b.classList.toggle("on", b.dataset.v === state.prefer);
    b.onclick = () => { state.prefer = b.dataset.v; $$("#seg-prefer button").forEach((x) => x.classList.toggle("on", x === b)); if (params.get("from")) runPlan(params.get("from"), params.get("to")); };
  });
  // leaving now, or at a chosen day and time
  const w = planWhen(), pick = $("#when-pick"), ti = $("#p-time");
  let whenMode = w.fixed ? "later" : "now", pday = w.day;
  ti.value = hhmm(w.fixed ? w.minute : Math.max(300, Math.min(1410, state.minute)));
  const paintWhen = () => {
    $$("#seg-when button").forEach((x) => x.classList.toggle("on", x.dataset.v === whenMode));
    $$("#seg-pday button").forEach((x) => x.classList.toggle("on", x.dataset.v === pday));
    pick.hidden = whenMode !== "later";
  };
  $$("#seg-when button").forEach((b) => (b.onclick = () => { whenMode = b.dataset.v; paintWhen(); if (whenMode === "later") ti.focus(); }));
  $$("#seg-pday button").forEach((b) => (b.onclick = () => { pday = b.dataset.v; paintWhen(); }));
  paintWhen();
  const [f, t] = await Promise.all([stopByKey(params.get("from")), stopByKey(params.get("to"))]);
  const submit = wireOD("p", { from: f, to: t });
  if (restoreFields) {          // coming back from an Undo: put the fields back as they were
    const r = restoreFields; restoreFields = null;
    [["#p-from", r.f], ["#p-to", r.t]].forEach(([sel, x]) => { const el = $(sel); el.value = x.v || ""; x.k ? (el.dataset.key = x.k) : delete el.dataset.key; });
  }
  setupPlanMap();
  stickSide($(".side"));
  $("#plan-form").onsubmit = async (e) => {
    e.preventDefault(); const r = await submit(); if (!r) return;
    let when = "";
    if (whenMode === "later") {
      if (!/^\d{1,2}:\d{2}$/.test(ti.value)) { fieldError(ti, "Choose a time."); return; }
      when = `&time=${ti.value}&day=${pday}`;
    }
    const target = `#/plan?from=${enc(r.from.key)}&to=${enc(r.to.key)}${when}`;
    if (location.hash === target) runPlan(r.from.key, r.to.key); else location.hash = target;
  };
  if (f && t) { saveRecent(f, t); runPlan(f.key, t.key); }
}
const TRY_TRIPS = [["badarpur border", "noida sector 37", "Badarpur Border to Noida Sector 37", "A busy morning commute"], ["kapashera border", "saket crossing", "Kapashera Border to Saket Crossing", "Across south Delhi"], ["mehrauli terminal", "dhaula kuan", "Mehrauli Terminal to Dhaula Kuan", "With one change"]];
const startHint = () => `<div class="card"><div class="state">${IC.plan.replace("<svg", '<svg style="stroke:var(--muted)"')}<b class="t-strong">Choose two stops</b><p>Pick where you're starting and where you're going. We'll show the buses, how long they take, and how full they're likely to be.</p></div></div>
  <div class="section-title"><h3 class="t-heading">Try a trip</h3></div><div class="card rows">
  ${TRY_TRIPS
    .map(([a, b, t, s]) => `<a class="row" style="text-decoration:none;color:inherit" href="#/plan?from=${enc(a)}&to=${enc(b)}"><span class="row-main"><b>${t}</b><small>${s}</small></span>${chev}</a>`).join("")}</div>`;

/* Plan map: pick From / To by tapping stops, "Near me", and the chosen trip drawn on top. */
let planMap = null, tripLayer = null, undoCtl = null, restoreFields = null, tripShown = -1, pendingUndo = null;
function setupPlanMap() {
  planMap = makeMap($("#plan-map"));
  if (!planMap) return;
  tripLayer = L.featureGroup().addTo(planMap);
  undoCtl = null;
  if (pendingUndo && pendingUndo.until > Date.now()) offerUndo(pendingUndo.text, pendingUndo.before, pendingUndo.until);
  const fi = $("#p-from"), ti = $("#p-to");
  const choose = (which, s) => {
    const before = { f: { v: fi.value, k: fi.dataset.key }, t: { v: ti.value, k: ti.dataset.key }, hash: location.hash };
    offerUndo(which === "from" ? `Start set to ${s.name}` : `Destination set to ${s.name}`, before);
    planMap.closePopup();
    setStop(which === "from" ? fi : ti, { key: s.key, name: s.name });
    (which === "from" ? fi : ti).closest(".field").classList.remove("error");
    if (fi.dataset.key && ti.dataset.key && fi.dataset.key !== ti.dataset.key) $("#plan-form").requestSubmit();
    else (which === "from" ? ti : fi).focus({ preventScroll: true });
  };
  fitControl(planMap, "Show whole trip", () => (tripLayer.getLayers().length ? fitTo(planMap, tripLayer, 24) : planMap.setView(DELHI, 11)));
  stopsLayer(planMap, { pick: choose }).then((list) => {
    $("#near-me").onclick = () => {
      const btn = $("#near-me");
      if (!navigator.geolocation) { btn.textContent = "Location not available"; return; }
      btn.textContent = "Finding you…";
      navigator.geolocation.getCurrentPosition((pos) => {
        if (!alive(planMap)) return;
        const { latitude: la, longitude: lo } = pos.coords;
        const d = (s) => (s.lat - la) ** 2 + ((s.lon - lo) * Math.cos((la * Math.PI) / 180)) ** 2;
        const near = list.reduce((a, b) => (d(b) < d(a) ? b : a));
        btn.textContent = "Near me";
        L.marker([la, lo], { icon: dotIcon("me"), interactive: false, keyboard: false }).addTo(planMap);   // "you are here"; taps pass through to stops
        planMap.setView([near.lat, near.lon], 15);
        if (!fi.dataset.key) setStop(fi, { key: near.key, name: near.name });
      }, () => { btn.textContent = "Location blocked"; setTimeout(() => (btn.textContent = "Near me"), 2500); }, { enableHighAccuracy: true, timeout: 8000 });
    };
  }).catch(() => {});
}
/* An Undo button on the map after "Start here" / "Go here". It travels with the map. */
function offerUndo(text, before, until = Date.now() + 15000) {
  pendingUndo = { text, before, until };        // survives the page re-rendering when the pick runs a search
  if (!planMap || !alive(planMap)) return;
  try { undoCtl?.remove(); } catch {}
  const C = L.Control.extend({ onAdd() {
    const box = L.DomUtil.create("div", "map-undo"); L.DomEvent.disableClickPropagation(box);
    box.innerHTML = `<span>${esc(text)}</span><button type="button" class="link t-small-strong">Undo</button>`;
    box.querySelector("button").onclick = () => undoPick(before);
    return box;
  } });
  undoCtl = new C({ position: "bottomleft" }).addTo(planMap);
  clearTimeout(offerUndo.t);
  offerUndo.t = setTimeout(() => { try { undoCtl?.remove(); } catch {} undoCtl = null; pendingUndo = null; }, Math.max(0, until - Date.now()));
}
function undoPick(before) {
  try { undoCtl?.remove(); } catch {} undoCtl = null; pendingUndo = null; clearTimeout(offerUndo.t);
  if (location.hash !== before.hash) { restoreFields = before; location.hash = before.hash || "#/plan"; return; }   // a search had run
  [["#p-from", before.f], ["#p-to", before.t]].forEach(([sel, x]) => { const el = $(sel); if (!el) return; el.value = x.v || ""; x.k ? (el.dataset.key = x.k) : delete el.dataset.key; });
}

/* A sticky side column taller than the window would hide its bottom. Stick it by its bottom instead,
   so scrolling the page reveals all of it and it then stays in view. */
function stickSide(side) {
  if (!side || !("ResizeObserver" in window)) return;
  const fit = () => { const room = innerHeight - 16 - side.offsetHeight; side.style.top = `${Math.min(96, room)}px`; };
  new ResizeObserver(fit).observe(side); addEventListener("resize", fit); fit();
}

/* Phones: the map sits under the trip it shows (Trip 1 first), not in a fixed place. */
const narrow = () => matchMedia("(max-width: 899px)").matches;
function placePlanMap(i) {
  const card = $("#plan-map-card"); if (!card) return;
  const slot = i >= 0 && narrow() ? $(`#results .opt:nth-child(${i + 1}) .opt-map-slot`) : $("#plan-map-home");
  if (slot && card.parentElement !== slot) { slot.appendChild(card); card.classList.toggle("in-trip", slot !== $("#plan-map-home")); planMap?.invalidateSize(); }
}
addEventListener("resize", () => { if (planMap && alive(planMap)) { placePlanMap(tripShown); planMap.invalidateSize(); } });

function showTripOnMap(o, i) {
  if (!planMap || !tripLayer || !alive(planMap)) return;
  tripShown = i; placePlanMap(i);
  clearRides(tripLayer);
  planMap.getPane("stops")?.classList.add("faded");
  o.legs.forEach((l, n) => {
    drawRide(tripLayer, l.shape, l.profile, l.stop_names, { ends: false, map: planMap, readout: $("#plan-map-read") });
    const a = l.shape.stops?.[0], b = l.shape.stops?.[l.shape.stops.length - 1];
    const dot = (p, kind, label) => p && L.marker(p, { icon: dotIcon(kind), keyboard: false, zIndexOffset: 800 })
      .bindTooltip(label, { direction: "auto", offset: [0, -9] }).addTo(tripLayer);
    if (n === 0) dot(a, "board", `Board ${esc(l.route.number)} at ${esc(l.board)}`);
    else dot(a, "xfer", `Change to ${esc(l.route.number)} at ${esc(l.board)}`);
    if (n === o.legs.length - 1) dot(b, "end", `Get off at ${esc(l.alight)}`);
    const next = o.legs[n + 1];
    if (next && b && next.shape.stops?.[0]) L.polyline([b, next.shape.stops[0]], { color: css("--muted"), weight: 2, dashArray: "2 5", interactive: false }).addTo(tripLayer);
  });
  fitTo(planMap, tripLayer, 24);
  $("#plan-map-title").textContent = `Trip ${i + 1}: ${o.legs.map((l) => l.route.number).join(" then ")}`;
  const approx = o.legs.some((l) => l.shape.approx);
  // V. the zoom hint only on Trip 1's map, where people meet the map first
  $("#plan-map-key").innerHTML = mapKey(approx ? `<span class="muted">Path approximate: straight between stops</span>` : "")
    + (i === 0 ? `<p class="t-caption muted map-hint">Tap a stop for details. Zoom in to see other stops nearby.</p>` : "");
  $$("#results .opt").forEach((el, j) => el.classList.toggle("on-map", j === i));
}

async function runPlan(from, to) {
  const res = $("#results"), btn = $("#plan-btn");
  tripShown = -1; placePlanMap(-1);            // take the map out of the old cards before replacing them
  res.innerHTML = loading;
  if (btn) { btn.disabled = true; btn.innerHTML = `<span class="spinner"></span>Finding buses`; }
  try {
    const p = await api(`/api/plan?from=${enc(from)}&to=${enc(to)}&${planQ()}&prefer=${state.prefer}`);
    renderPlan(p, from, to);
  } catch (e) { res.innerHTML = errorBox(e.message); }
  if (btn) { btn.disabled = false; btn.textContent = "Show buses"; }
}

/* Stops with the stretch to the next stop coloured by how full the bus usually is there.
   Where the level changes, the stop says so ("busy from here"). */
function stopsList(names, profile, keys, id) {
  const band = { Comfortable: [0, 35], Moderate: [35, 60], Busy: [60, 80], Packed: [80, 100] };
  return `<div class="stops"${id ? ` id="${id}"` : ""}>${names.map((s, i) => {
    const v = profile[i], lv = v != null ? level(v) : null;
    const changed = lv && (i === 0 || level(profile[i - 1]) !== lv);
    // a little darker within a level as it fills up, so differences show even when all one colour
    const [lo, hi] = lv ? band[lv] : [0, 1], shade = lv ? (0.55 + 0.45 * Math.min(1, (v - lo) / (hi - lo))).toFixed(2) : 1;
    const tag = changed ? `<span class="st-lvl" style="color:${css(FILL[lv])}">${lv.toLowerCase()} from here</span>` : "";
    const tagName = keys ? "a" : "div", href = keys ? ` href="#/stop/${enc(keys[i])}"` : "";
    return `<${tagName}${href} class="st ${i === 0 || i === names.length - 1 ? "end" : ""}" style="${lv ? `--seg:${fillOf(v)};--seg-o:${shade}` : ""}" ${lv ? `title="To the next stop: ${lv.toLowerCase()} (${Math.round(v)} of 100)"` : ""}><span>${esc(s)}</span>${tag}</${tagName}>`;
  }).join("")}</div>`;
}
const stopsKey = () => `<div class="stops-key t-caption">${LEVELS.map((l) => `<span><i style="background:${css(FILL[l])}"></i>${l}</span>`).join("")}</div>`;

function renderPlan(p, from, to) {
  const res = $("#results");
  if (tripLayer && alive(planMap)) { tripShown = -1; placePlanMap(-1); clearRides(tripLayer); planMap.getPane("stops")?.classList.remove("faded"); $("#plan-map-title").textContent = "Pick stops on the map"; }
  if (!p.options.length) {
    res.innerHTML = p.walk_m
      ? `<div class="card"><div class="state">${IC.walk}<b class="t-strong">Walk instead</b><p>${esc(p.origin)} and ${esc(p.destination)} are about ${p.walk_m} m apart. It's quicker to walk than to wait for a bus.</p></div></div>`
      : `<div class="card"><div class="state">${IC.search.replace("<svg", '<svg style="stroke:var(--muted)"')}<b class="t-strong">No buses found</b><p>We couldn't find a direct bus or a trip with one change between these stops in the October ticket data.</p></div></div>`;
    return;
  }
  const cards = p.options.map((o, i) => {
    const tags = (o.live ? `<span class="pill live">Live: bus ${o.live.stops_away ? `due in ${plural(o.live.eta, "minute")}` : "at the stop"}</span>` : "") + o.tags.map((t) => `<span class="pill brand">${t}</span>`).join("") + (o.confidence === "low" ? `<span class="pill warn">Limited data</span>` : "")
      + (o.time_source === "estimate" ? `<span class="pill warn">Time estimated</span>` : "");
    const chain = o.legs.map((l) => plate(l.route, "sm")).join(`<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>`);
    const legs = o.legs.map((l, n) => `${n ? `<div class="xfer">${IC.walk}Change buses at ${esc(l.board)}. Walk about 3 minutes, then wait about ${plural(l.wait, "minute")} (${every(l)}).</div>` : ""}
      <div class="leg"><div class="leg-head">${plate(l.route, "sm")}<span><b>${esc(l.board)} to ${esc(l.alight)}</b>
      <small>${n ? "" : `Wait about ${plural(l.wait, "minute")} (${every(l)}), then `}${clock(toMin(l.depart))} to ${clock(toMin(l.arrive))} · ${plural(l.stops, "stop")}${l.fare != null ? ` · ${rupees(l.fare)}` : ""} · ${l.level.toLowerCase()}, seat chance ${l.seat_chance}%</small></span></div>
      ${stopsList(l.stop_names, l.profile)}</div>`).join("") + stopsKey();
    return `<article class="card opt ${o.tags.includes("Best overall") ? "best" : ""} ${i === 0 ? "open" : ""}">
      ${tags ? `<div class="opt-tags">${tags}</div>` : ""}
      <div class="opt-head"><div><p class="t-title tnum">${o.minutes} min</p><p class="t-small muted">${o.transfers ? plural(o.transfers, "change") : "Direct"}${o.wait != null ? `, including about ${plural(o.wait, "minute")} waiting` : ""}</p></div><div class="opt-chain">${chain}</div></div>
      ${seatMeter(o)}
      ${o.live !== undefined ? `<div class="kv live-kv"><span><i class="live-dot"></i>Live</span><b>${o.live
        ? (o.live.stops_away ? `Next ${esc(routeName(o.legs[0].route.number))} is ${plural(o.live.stops_away, "stop")} away, due in about ${plural(o.live.eta, "minute")}` : `A ${esc(routeName(o.legs[0].route.number))} is at the stop now`)
        : "No bus seen coming yet"}</b></div>` : ""}
      <div class="kv"><span>Wait at ${esc(o.legs[0].board)}</span><b class="tnum">about ${plural(o.legs[0].wait, "minute")}</b></div>
      <div class="kv"><span>How often it comes</span><b>${every(o.legs[0]).replace(/^a bus/, "A bus").replace(/^few/, "Few").replace(/^timetable/, "Timetable")}</b></div>
      <div class="kv"><span>Arrives (expected)</span><b class="tnum">${clock(toMin(o.arrive))}</b></div>
      ${o.fare != null ? `<div class="kv"><span>Fare per person, e-ticket${o.legs.length > 1 ? `<br><small class="t-caption">one ticket per bus: ${o.legs.map((l) => rupees(l.fare)).join(" + ")}</small>` : ""}</span><b class="tnum">${rupees(o.fare)}</b></div>` : ""}
      ${o.km != null ? `<div class="kv"><span>Distance by bus</span><b class="tnum">${o.km} km</b></div>` : ""}
      <div class="kv"><span>Crowding</span><b class="tnum">${o.crowd} of 100 · ${o.level}</b></div>
      <div class="kv"><span>Chance of a seat when you board</span><b class="tnum">${o.seat_chance}%</b></div>
      <div class="opt-map-slot"></div>
      <div class="opt-actions"><button class="btn quiet t-small-strong opt-toggle" aria-expanded="${i === 0}">${i === 0 ? "Hide stops" : "Show stops"}</button><button type="button" class="btn quiet t-small-strong show-map">Show on map</button></div>
      <div class="legs">${legs}</div></article>`;
  }).join("");
  const curve = p.departure_curve.length ? `<div class="card chart-card"><h3 class="t-heading">Crowding at other times</h3><p class="t-small muted">For the best overall trip, if you leave earlier or later.</p>
    <div class="bars">${p.departure_curve.map((c) => `<button type="button" class="b ${c.offset === 0 ? "now" : ""}" data-m="${toMin(c.depart)}" aria-label="Leave at ${clock(toMin(c.depart))}, crowding ${c.crowd}" title="${clock(toMin(c.depart))} · crowding ${c.crowd}"><i style="height:${Math.max(6, c.crowd)}%;background:${c.offset === 0 ? css("--brand") : fillOf(c.crowd)}"></i><span>${short(toMin(c.depart))}</span></button>`).join("")}</div>
    <p class="t-small muted bars-read">Tap a time to see how crowded it is.</p>
    <a class="link t-small-strong" href="#/best?from=${enc(from)}&to=${enc(to)}">See the whole day</a></div>` : "";
  res.innerHTML = `<div class="page" style="margin:0">
    ${p.tip ? notice("ok", "A calmer time to leave", esc(p.tip.text), IC.clock) : ""}
    <div class="section-title" style="margin-top:0!important"><h2 class="t-heading">${plural(p.options.length, "way")} to ${esc(p.destination)}</h2><span class="t-small muted">${DAYS[p.day]}, ${clock(toMin(p.depart))}</span></div>
    ${p.only_low_data ? notice("warn", "Few tickets on these routes", "Every bus between these stops has thin or unclear ticket data for October, so these times and crowding levels are rough.", IC.alert) : ""}
    <div>${cards}</div>
    ${p.hidden_low_data ? `<p class="t-small muted" style="margin-top:12px">${p.hidden_low_data === 1 ? "1 more route also runs between these stops. It's hidden because its October ticket data is too thin to trust its times." : `${p.hidden_low_data} more routes also run between these stops. They're hidden because their October ticket data is too thin to trust their times.`}</p>` : ""}${curve}
    ${notice("info", "How these times are worked out", "Each ride uses the route's real distance (Delhi bus GTFS) and the speed buses actually moved at on that stretch of road at that time of day, measured by GPS on 14, 15, 16 and 18 October 2026. Waiting is the average wait for someone arriving at the stop around that time, from the DTC timetable. Crowding comes from October 2026 e-tickets. Fares are what October e-tickets cost for the same ride: the DTC fare less the 10% e-ticket discount.", IC.info)}</div>`;
  $$(".opt + .opt", res).forEach((el) => (el.style.marginTop = "12px"));
  const read = $(".bars-read", res);
  $$(".bars .b", res).forEach((b) => (b.onclick = b.onmouseenter = b.onfocus = () => {
    const c = p.departure_curve.find((x) => toMin(x.depart) === +b.dataset.m);
    if (c && read) read.innerHTML = `<b class="tnum" style="color:var(--ink)">${clock(toMin(c.depart))}</b> · crowding ${c.crowd}, ${c.level.toLowerCase()} · about ${c.minutes} min`;
  }));
  $$(".opt", res).forEach((card, i) => {
    const tog = $(".opt-toggle", card);
    tog.onclick = (e) => {
      e.stopPropagation();
      const open = card.classList.toggle("open"); tog.textContent = open ? "Hide stops" : "Show stops"; tog.setAttribute("aria-expanded", open);
      if (open) showTripOnMap(p.options[i], i);          // opening a trip's stops shows that trip on the map
    };
    // desktop: tapping a card shows it on the side map; phones move the map only with Show stops / Show on map
    card.onclick = (e) => { if (!narrow() && !e.target.closest("a, button, .leaflet-container")) showTripOnMap(p.options[i], i); };
    $(".show-map", card).onclick = (e) => { e.stopPropagation(); showTripOnMap(p.options[i], i); $("#plan-map").scrollIntoView({ behavior: "smooth", block: "nearest" }); };
  });
  showTripOnMap(p.options[0], 0);
  const rec = $("#plan-recent"); if (rec) rec.innerHTML = recentHTML();
}

/* ---------- best time ---------- */
async function pageBest(params) {
  view.innerHTML = `<div class="page">
    <div class="page-head"><div><h1 class="t-title">Best time to travel</h1><p class="t-small muted">See how crowded your trip is at every time of day, and when it's calmest.</p></div></div>
    <div class="split"><div class="side"><form class="card form-card" id="best-form" novalidate>${odForm({ prefix: "b" })}
      <p class="t-small-strong label">Day</p><div class="segmented" id="best-day"><button type="button" data-v="weekday">Weekday</button><button type="button" data-v="saturday">Saturday</button><button type="button" data-v="sunday">Sunday or holiday</button></div>
      <button class="btn primary" type="submit">Show the whole day</button></form></div>
      <div id="best-res">${params.get("from") && params.get("to") ? loading : `<div class="card"><div class="state">${IC.clock.replace("<svg", '<svg style="stroke:var(--muted)"')}<b class="t-strong">Choose two stops</b><p>We'll check your trip every half hour from 5:30 am to 11 pm and show when it's calmest.</p></div></div>`}</div></div></div>`;
  let day = params.get("day") || state.day;
  $$("#best-day button").forEach((b) => { b.classList.toggle("on", b.dataset.v === day); b.onclick = () => { day = b.dataset.v; $$("#best-day button").forEach((x) => x.classList.toggle("on", x === b)); }; });
  const [f, t] = await Promise.all([stopByKey(params.get("from")), stopByKey(params.get("to"))]);
  const submit = wireOD("b", { from: f, to: t });
  $("#best-form").onsubmit = async (e) => { e.preventDefault(); const r = await submit(); if (r) location.hash = `#/best?from=${enc(r.from.key)}&to=${enc(r.to.key)}&day=${day}`; };
  if (!f || !t) return;
  try {
    const b = await api(`/api/besttime?from=${enc(f.key)}&to=${enc(t.key)}&day=${day}`);
    const box = $("#best-res");
    if (!b.slots.length) { box.innerHTML = `<div class="card"><div class="state"><b class="t-strong">No buses found</b><p>There's no direct bus or one-change trip between these stops in the ticket data.</p></div></div>`; return; }
    const slotHTML = (s) => `<div class="kv"><span>Leaving at</span><b class="tnum">${clock(toMin(s.depart))}</b></div>
      <div class="kv"><span>Crowding</span><b class="tnum">${s.crowd} of 100 · ${s.level}</b></div>
      <div class="kv"><span>Trip time, including waiting</span><b class="tnum">${s.minutes} min</b></div>
      <div class="kv"><span>Buses</span><b>${s.routes.map((n) => esc(routeName(n))).join(" then ")}</b></div>
      <div class="kv"><span>Chance of a seat</span><b class="tnum">${s.seat_chance}%</b></div>
      ${s.fare != null ? `<div class="kv"><span>Fare per person, e-ticket</span><b class="tnum">${rupees(s.fare)}</b></div>` : ""}`;
    box.innerHTML = `<div class="page" style="margin:0">
      <div class="card list-card"><div class="kv"><span>Trip</span><b style="white-space:normal;text-align:right">${esc(b.origin)} to ${esc(b.destination)}</b></div><div class="kv"><span>Day</span><b>${DAYS[b.day]}</b></div></div>
      <div class="big-best">
        <div class="card chart-card"><p class="t-small-strong muted">Calmest time</p><p class="t-display tnum">${clock(toMin(b.best.depart))}</p><p class="t-small">${pill(b.best.level)} crowding ${b.best.crowd}</p></div>
        <div class="card chart-card"><p class="t-small-strong muted">Most crowded</p><p class="t-display tnum">${clock(toMin(b.worst.depart))}</p><p class="t-small">${pill(b.worst.level)} crowding ${b.worst.crowd}</p></div>
      </div>
      <div class="card chart-card"><h3 class="t-heading">Through the day</h3><p class="t-small muted">Hover over or tap a bar to see that departure.</p>
        <div class="day-bars" id="day-bars">${b.slots.map((s, i) => `<button type="button" data-i="${i}" aria-label="${clock(toMin(s.depart))}, crowding ${s.crowd}"><i style="height:${Math.max(4, s.crowd)}%;background:${fillOf(s.crowd)}"></i></button>`).join("")}</div>
        <div class="axis t-caption"><span>5:30 am</span><span>11 am</span><span>5 pm</span><span>11 pm</span></div>
        <div class="slot-detail" id="slot-detail"></div></div>
      <a class="btn secondary" href="#/plan?from=${enc(f.key)}&to=${enc(t.key)}">Plan this trip now</a></div>`;
    const pickSlot = (i) => { $$("#day-bars button").forEach((x, j) => x.classList.toggle("sel", i === j)); $("#slot-detail").innerHTML = slotHTML(b.slots[i]); };
    $$("#day-bars button").forEach((x) => { x.onclick = () => pickSlot(+x.dataset.i); x.onmouseenter = x.onfocus = () => pickSlot(+x.dataset.i); });
    pickSlot(b.slots.findIndex((s) => s.depart === b.best.depart));
  } catch (e) { $("#best-res").innerHTML = errorBox(e.message); }
}

/* ---------- crowd now ---------- */
async function pageCrowd() {
  view.innerHTML = `<div class="page"><div class="page-head"><div><h1 class="t-title">${state.live ? "Crowd right now" : `Crowd at ${clock(state.minute)}`}</h1><p class="t-small muted" id="crowd-sub"></p></div></div><div id="crowd-body">${loading}</div></div>`;
  try {
    const p = await api(`/api/pulse?${q()}`);
    const slot = Math.floor(state.minute / 30) - 10;
    $("#crowd-sub").textContent = `${state.live ? "Live" : "Planned"} · ${DAYS[state.day]}, ${clock(state.minute)}`;
    $("#crowd-body").innerHTML = `<div class="page" style="margin:0">
      <div class="two-col"><div>
        <div id="crowd-card"><p class="t-small-strong muted">Delhi bus crowd index · <span class="ci-when"></span></p>
        <div class="figure"><span class="t-display tnum ci-num"></span><span class="t-body muted">out of 100</span></div>
        <p class="figure-sub"><span class="ci-pill"></span><span class="t-small muted ci-line"></span></p>
        <button type="button" class="link t-small-strong ci-back" hidden>Back to ${state.live ? "now" : clock(state.minute)}</button></div>
        <p class="t-small muted" style="margin-top:12px">Tap or drag the line, or use the arrow keys, to see any time of day. To plan for another time, use the time button at the top. ${liveLink()}</p>
      </div><div class="card chart-card">
        <svg id="crowd-chart" class="chart" viewBox="0 0 340 120" preserveAspectRatio="none" role="img" aria-label="Crowd index through the day"></svg>
        <div class="axis t-caption"><span>5 am</span><span>9 am</span><span>1 pm</span><span>5 pm</span><span>9 pm</span></div>
        <div class="lowhigh t-small"><span>Peak <b class="tnum">${clock(toMin(p.peak_time))}</b></span><span>Tap or drag to see any time</span></div></div></div>
      <div class="two-col">
        <div><div class="section-title"><h3 class="t-heading">${state.live ? "Busiest right now" : `Busiest at ${clock(state.minute)}`}</h3></div><div class="card rows">${p.busiest.map((r) => routeRow(r)).join("")}</div></div>
        <div><div class="section-title"><h3 class="t-heading">Better chance of a seat</h3></div><div class="card rows">${p.calmest.map((r) => routeRow(r)).join("")}</div></div>
      </div>
      <div class="section-title"><h3 class="t-heading">Changing fastest</h3><span class="t-small muted">compared with half an hour earlier</span></div>
      <div class="card rows">${p.movers.slice(0, 8).map((r) => routeRow(r, `<span style="color:${r.change > 0 ? css("--c4") : css("--c1")}">${r.change > 0 ? "Getting busier" : "Getting calmer"}, ${r.change > 0 ? "up" : "down"} ${Math.abs(r.change).toFixed(1)}</span>`)).join("")}</div>
      <p class="t-small muted plates-note"><span class="plate gold xs" aria-hidden="true"><span>717</span></span> Blue strip under the number: AC bus <span class="plate silver xs" aria-hidden="true"><span>534</span></span> No strip: non-AC bus</p></div>`;
    const curve = p.curve.slice(10, 47);
    const card = $("#crowd-card");
    const ch = iChart($("#crowd-chart"), [{ values: curve, color: css("--brand"), fill: 0.07, marker: true }], { max: 100, index: slot,
      describe: (i) => `<b>${clock((i + 10) * 30)}</b> · ${curve[i]} · ${level(curve[i])}`, onMove: crowdIndexCard(card, p),
      hint: "Delhi bus crowd index through the day. Use the arrow keys to read any time." });
    $(".ci-back", card).onclick = () => ch.reset();
  } catch (e) { $("#crowd-body").innerHTML = errorBox(e.message); }
}

/* ---------- routes ---------- */
async function pageRoutes(params) {
  view.innerHTML = `<div class="page"><div class="page-head"><div><h1 class="t-title">Find a route</h1><p class="t-small muted">Type the number on the front of the bus.</p></div></div>
    <label class="field"><span class="t-small-strong">Route number</span><span class="input">${IC.search}<input id="route-q" placeholder="For example, 717A, 8 or 534" autocomplete="off" autocorrect="off" autocapitalize="characters" spellcheck="false" enterkeyhint="search" value="${esc(params.get("q") || "")}" /></span></label>
    <div class="card rows" id="route-list">${loading}</div></div>`;
  const inp = $("#route-q"); let t;
  const load = async () => {
    try {
      const rs = await api(`/api/routes?q=${enc(inp.value)}&${q()}`);
      $("#route-list").innerHTML = rs.length ? rs.map((r) => `<a class="row" href="#/route/${enc(r.id)}" style="text-decoration:none;color:inherit">${plate(r)}
        <span class="row-main"><b>${esc(r.origin)} to ${esc(r.towards)}</b><small>${isLongRoute(r.number) ? `${esc(routeName(r.number))} · ` : ""}${plural(r.stops, "stop")} · ${inr(r.tickets)} e-tickets${r.low_data ? " · limited data" : ""}</small></span>
        <span class="row-value"><b class="tnum">${r.crowd}</b>${pill(r.level)}</span>${chev}</a>`).join("")
        : `<div class="empty-hint">No route starts with "${esc(inp.value)}". Check the number on the front of the bus.</div>`;
    } catch (e) { $("#route-list").innerHTML = errorBox(e.message); }
  };
  inp.oninput = () => { clearTimeout(t); t = setTimeout(() => { history.replaceState(null, "", `#/routes${inp.value ? `?q=${enc(inp.value)}` : ""}`); load(); }, 160); };
  load();
}

async function pageRoute(id) {
  view.innerHTML = `<div class="page">${loading}</div>`;
  try {
    const r = await api(`/api/route/${enc(id)}?${q()}`);
    const heat = r.hourly.slice(10, 46), now = Math.floor(state.minute / 30) - 10;
    const dir = r.route.direction === "UP" ? "up" : r.route.direction === "DOWN" ? "down" : "";
    view.innerHTML = `<div class="page">
      <div class="page-head">${backBtn("#/routes")}<div><p class="crumb">Route ${esc(r.route.number)} ${dir}</p></div></div>
      <div class="rd-head">${plate(r.route, "lg")}<div><h1 class="t-heading">Towards ${esc(r.route.towards)}${hallmark(r.route)}</h1>
        <p class="t-small muted">From ${esc(r.stops[0].name)} · ${plural(r.stops.length, "stop")} · ${inr(r.tickets)} e-tickets in October</p></div></div>
      <div class="two-col"><div>
        <p class="t-small-strong muted">Crowding at ${clock(toMin(r.slot))}, ${DAYS[state.day].toLowerCase()}</p>
        <div class="figure"><span class="t-display tnum">${r.now_crowd}</span><span class="t-body muted">out of 100</span></div>
        <p class="figure-sub">${pill(r.level)}</p>
        <div class="card list-card">
          <div class="kv"><span>Calmest time</span><b class="tnum">${clock(toMin(r.best_time))} · ${r.best_crowd} of 100</b></div>
          <div class="kv"><span>Busiest time</span><b class="tnum">${clock(toMin(r.worst_time))} · ${r.worst_crowd} of 100</b></div>
          ${r.median_fare ? `<div class="kv"><span>Typical e-ticket fare</span><b class="tnum">₹${Number(r.median_fare).toFixed(2)}</b></div>` : ""}
          <div class="kv"><span>Tickets that agree with the stop order</span><b class="tnum">${(r.order_confidence * 100).toFixed(1)}%</b></div>
        </div>
        <div class="card chart-card"><h2 class="t-heading">Through the day</h2><p class="t-small muted">Each bar is half an hour; the outlined one is the time shown.</p>
          ${heatStrip(heat, { now })}
          <div class="axis t-caption"><span>5 am</span><span>9 am</span><span>1 pm</span><span>5 pm</span><span>9 pm</span></div></div>
        ${r.route.low_data ? notice("warn", "Limited data", "This route had fewer than 600 e-tickets in October, so its crowding is less certain.", IC.alert) : ""}
      </div><div class="card chart-card"><div class="map-head"><h2 class="t-heading">Along the route at <span id="route-at">${clock(toMin(r.slot))}</span></h2><button type="button" class="link t-small-strong" id="route-at-now" hidden>Back to ${state.live ? "now" : clock(state.minute)}</button></div>
        ${r.live ? `<p class="t-small live-line"><i class="live-dot"></i>${r.live.length ? `${r.live.length} ${r.live.length === 1 ? "bus" : "buses"} on this route right now, shown on the map` : "No buses on this route in the live feed right now"}</p>` : ""}
        <p class="t-small muted">The line is coloured by how full the bus usually is on each stretch. Hover or tap a stretch or a stop for details, or tap a half hour in "Through the day" to see the route at that time.</p>
        <div class="map" id="route-map" role="region" aria-label="Map of route ${esc(r.route.number)}"></div>
        <p class="map-read t-small" id="route-map-read" aria-live="polite">${READ_HINT}</p>
        ${mapKey(r.shape.approx ? `<span class="muted">Path approximate: straight between stops</span>` : "")}
        ${stopsList(r.stops.map((x) => x.name), r.segments, r.stops.map((x) => x.key), "route-stops")}</div></div></div>`;
    wireHeat();
    const m = makeMap($("#route-map"));
    if (m) {
      const lay = L.featureGroup().addTo(m);
      const ride = drawRide(lay, r.shape, r.segments, r.stops.map((x) => x.name), { keys: r.stops.map((x) => x.key), map: m, readout: $("#route-map-read") });
      fitTo(m, lay);
      fitControl(m, "Show whole route", () => fitTo(m, lay));
      if (r.live?.length) {                // buses on this route right now, from the live feed
        r.live.forEach((b) => L.marker([b.lat, b.lon], { icon: L.divIcon({ className: "bus-live", iconSize: null, html: IC.bus }), keyboard: false, zIndexOffset: 900 })
          .bindTooltip(`Bus ${esc(b.plate)}, at ${esc(r.stops[b.at].name)}<br><span class="muted">seen ${b.age < 60 ? `${b.age} s` : `${Math.round(b.age / 60)} min`} ago</span>`, { direction: "top", offset: [0, -12] }).addTo(m));
      }
      // the list and the map point at each other
      $$("#route-stops .st").forEach((el, k) => { el.onmouseenter = el.onfocus = () => ride.highlight(k, true); el.onmouseleave = el.onblur = () => ride.highlight(k, false); });
      // tapping a half hour in "Through the day" shows the route at that time (the app's time stays)
      const title = $("#route-at"), list = $("#route-stops"), back = $("#route-at-now");
      const showAt = (i) => {
        const vals = i == null ? r.segments : r.segments_by_slot[i];
        ride.recolour(vals);
        list.outerHTML = stopsList(r.stops.map((x) => x.name), vals, r.stops.map((x) => x.key), "route-stops");
        $$("#route-stops .st").forEach((el, k) => { el.onmouseenter = el.onfocus = () => ride.highlight(k, true); el.onmouseleave = el.onblur = () => ride.highlight(k, false); });
        title.textContent = clock(i == null ? toMin(r.slot) : (i + 10) * 30);
        back.hidden = i == null;
      };
      $$(".heat button").forEach((b, i) => b.addEventListener("click", () => showAt(i)));
      back.onclick = () => showAt(null);
    }
  } catch (e) { view.innerHTML = `<div class="page">${errorBox(e.message)}</div>`; }
}

/* ---------- stops ---------- */
async function pageStops() {
  view.innerHTML = `<div class="page"><div class="page-head"><div><h1 class="t-title">Stop information</h1><p class="t-small muted">Find a stop to see every bus that calls there and how full they are.</p></div></div>
    <label class="field"><span class="t-small-strong">Stop name</span><span class="input">${IC.search}<input id="stop-q" placeholder="For example, Dhaula Kuan" autocomplete="off" autocorrect="off" autocapitalize="words" spellcheck="false" enterkeyhint="search" /></span></label>
    <div class="section-title"><h2 class="t-heading" id="stops-title">Busiest stops</h2></div>
    <div class="card rows" id="stop-list">${loading}</div></div>`;
  const inp = $("#stop-q"); let t;
  const load = async () => {
    try {
      const rs = await api(`/api/stops?q=${enc(inp.value)}&limit=20`);
      $("#stops-title").textContent = inp.value.trim() ? "Matching stops" : "Busiest stops";
      $("#stop-list").innerHTML = rs.length ? rs.map((s) => `<a class="row" href="#/stop/${enc(s.key)}" style="text-decoration:none;color:inherit"><span class="pin">${IC.pin}</span>
        <span class="row-main"><b>${esc(s.name)}</b><small>${plural(s.routes, "route")} · ${inr(s.volume)} trips in October</small></span>${chev}</a>`).join("")
        : `<div class="empty-hint">No stop by that name. Try part of it, such as "Saket".</div>`;
    } catch (e) { $("#stop-list").innerHTML = errorBox(e.message); }
  };
  inp.oninput = () => { clearTimeout(t); t = setTimeout(load, 160); };
  load();
}

async function pageStop(key) {
  view.innerHTML = `<div class="page">${loading}</div>`;
  try {
    const s = await api(`/api/stop/${enc(key)}?${q()}`);
    const heat = s.hourly.slice(10, 46), now = Math.floor(state.minute / 30) - 10;
    view.innerHTML = `<div class="page">
      <div class="page-head">${backBtn("#/stops")}<div><p class="crumb">Stop</p></div></div>
      <div><h1 class="t-title">${esc(s.name)}</h1><p class="t-small muted">${plural(s.route_count, "route direction")} · ${inr(s.volume)} trips started or ended here in October</p></div>
      <div class="chips-row"><a class="chip" href="#/plan?from=${enc(s.key)}">Plan a trip from here</a><a class="chip" href="#/plan?to=${enc(s.key)}">Plan a trip to here</a></div>
      <div class="two-col"><div>
        <div class="card list-card"><div class="kv"><span>Buses usually calmest here</span><b class="tnum">${clock(toMin(s.best_time))}</b></div><div class="kv"><span>Buses usually busiest here</span><b class="tnum">${clock(toMin(s.worst_time))}</b></div></div>
        <div class="card chart-card"><h2 class="t-heading">Through the day</h2><p class="t-small muted">How full buses leaving this stop usually are.</p>
          ${heatStrip(heat, { now })}
          <div class="axis t-caption"><span>5 am</span><span>9 am</span><span>1 pm</span><span>5 pm</span><span>9 pm</span></div></div>
        ${s.lat != null ? `<div class="card map-card"><div class="map-head"><span class="t-small-strong">Where it is</span><a class="link t-small-strong" target="_blank" rel="noopener" href="https://www.openstreetmap.org/?mlat=${s.lat}&mlon=${s.lon}#map=17/${s.lat}/${s.lon}">Open in full map</a></div>
          <div class="map map-sm" id="stop-map" role="region" aria-label="Map around ${esc(s.name)}"></div>
          <p class="t-caption muted map-hint">Tap a nearby stop to see its buses or plan a trip from it.</p></div>` : ""}
      </div><div>
        <div class="section-title" style="margin-top:0!important"><h2 class="t-heading">Buses at this stop</h2><span class="t-small muted">${clock(toMin(s.slot))}</span></div>
        <div class="card rows">${s.routes.map((r) => routeRow(r, r.terminus ? "Ends here" : `${r.ac ? "AC" : "Non-AC"} · ${plural(r.stops_left, "more stop")}`)).join("")}</div>
      </div></div></div>`;
    wireHeat();
    const m = s.lat != null && makeMap($("#stop-map"), { center: [s.lat, s.lon], zoom: 15.5 });
    if (m) {
      stopsLayer(m).catch(() => {});
      L.marker([s.lat, s.lon], { icon: dotIcon("here"), keyboard: false, zIndexOffset: 1000 }).bindTooltip(esc(s.name), { permanent: true, direction: "top", offset: [0, -11], className: "map-label" })
        .bindPopup(() => stopPopup({ key: s.key, name: s.name, routes: s.route_count, volume: s.volume }), { offset: [0, -8], maxWidth: 260 }).addTo(m);
      fitControl(m, "Back to this stop", () => m.setView([s.lat, s.lon], 15.5));
    }
  } catch (e) { view.innerHTML = `<div class="page">${errorBox(e.message)}</div>`; }
}

/* ---------- about / how we know ---------- */
async function pageAbout() {
  view.innerHTML = `<div class="page"><div class="page-head"><div><h1 class="t-title">How we know</h1><p class="t-small muted">The data and checks behind every number in Seat Signal.</p></div></div><div id="about-body">${loading}</div></div>`;
  try {
    const v = await api("/api/validation"), m = v.meta, po = v.peak_offpeak, so = v.stop_order, dt = v.daytype_avg_daily_boardings;
    const date = (d) => new Date(d).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
    const tr = v.travel || {}, sp = tr.speeds || {}, geo = tr.geometry || {}, cov = tr.tickets_timed_by_route_geometry || {};
    const pct = (x, d = 1) => `${(x * 100).toFixed(d)}%`;
    const top = v.top_routes[0], topName = top.route.replace(/(UP|DOWN)\d*$/, "").replace(/^0+(?=\d)/, "");
    const gpsDays = Object.keys(sp.per_day || {}).map((k) => date(k.replace(/_/g, "-")));
    const gpsBuses = Math.max(0, ...Object.values(sp.per_day || {}).map((d) => d.buses));
    const kmh = sp.weekday_city_kmh_by_hour || [];
    $("#about-body").innerHTML = `<div class="page" style="margin:0">
      <p class="t-body muted">Crowding comes from ${inr(m.rows_used)} ONDC e-tickets on Delhi buses, 1 to 31 October 2026. Travel times come from the real length of each route and from bus GPS: about ${inr(gpsBuses)} buses tracked on ${gpsDays.join(", ")}. These checks show how far each part can be trusted.</p>
      <div class="two-col"><div>
        <div class="section-title"><h2 class="t-heading">Rush hours</h2></div>
        <div class="card list-card">
          <div class="kv"><span>Morning, 8 to 11 am, compared with midday</span><b class="tnum">${po.am_peak_ratio.toFixed(1)} times busier</b></div>
          <div class="kv"><span>Evening, 5 to 9 pm, compared with midday</span><b class="tnum">${po.pm_peak_ratio.toFixed(1)} times busier</b></div>
          <div class="kv"><span>Busiest half hour on a weekday</span><b class="tnum">${clock(po.busiest_slot_weekday * 30)}</b></div></div>
        <div class="card chart-card"><div class="chart-head"><span class="t-small-strong">Boardings per half hour · drag to explore</span><span class="legend t-caption"><i class="lg-a"></i>Weekday <i class="lg-b"></i>Sunday or holiday</span></div>
          <svg id="about-chart" class="chart" viewBox="0 0 340 120" preserveAspectRatio="none" role="img" aria-label="Boardings per half hour"></svg>
          <div class="axis t-caption"><span>5 am</span><span>9 am</span><span>1 pm</span><span>5 pm</span><span>9 pm</span></div></div>
      </div><div>
        <div class="section-title"><h2 class="t-heading">Days of the week</h2></div>
        <div class="card list-card">
          <div class="kv"><span>Average weekday</span><b class="tnum">${inr(Math.round(dt[0]))} e-tickets</b></div>
          <div class="kv"><span>Average Saturday</span><b class="tnum">${inr(Math.round(dt[1]))} e-tickets</b></div>
          <div class="kv"><span>Average Sunday or holiday</span><b class="tnum">${inr(Math.round(dt[2]))} e-tickets</b></div>
          <div class="kv"><span>Holidays found from the data alone</span><b class="tnum">${m.holidays.map(date).join(", ")}</b></div></div>
        <div class="section-title"><h2 class="t-heading">Stop order</h2></div>
        <div class="card list-card">
          <div class="kv"><span>Routes lined up with the Delhi bus timetable (GTFS)</span><b class="tnum">${inr(so.routes_gtfs_order)} · ${pct(so.tickets_gtfs_order, 0)} of tickets</b></div>
          ${so.gtfs_independent_forward_share != null ? `<div class="kv"><span>Tickets between timetable stops that ride forwards</span><b class="tnum">${pct(so.gtfs_independent_forward_share)}</b></div>` : ""}
          <div class="kv"><span>All tickets that ride forwards</span><b class="tnum">${pct(so.weighted_consistency)}</b></div>
          <div class="kv"><span>Busiest route, ${esc(topName)}</span><b class="tnum">${pct(top.consistency)}</b></div></div>
      </div></div>
      ${kmh.length ? `<div class="two-col"><div>
        <div class="section-title"><h2 class="t-heading">Travel times</h2></div>
        <div class="card list-card">
          <div class="kv"><span>Tickets on routes with a measured length</span><b class="tnum">${pct((cov.gtfs || 0) + (cov.stops || 0))}</b></div>
          <div class="kv"><span>Average bus speed, weekday 6 pm</span><b class="tnum">${kmh[18]} km/h</b></div>
          <div class="kv"><span>Average bus speed, weekday 3 am</span><b class="tnum">${kmh[3]} km/h</b></div>
          ${v.schedule ? `<div class="kv"><span>Tickets on routes with timetable waiting times</span><b class="tnum">${pct(v.schedule.tickets_share)}</b></div>
          <div class="kv"><span>Scheduled departures used for waiting times</span><b class="tnum">${inr(v.schedule.departures)}</b></div>` : ""}
          ${v.fares ? `<div class="kv"><span>E-tickets whose price our fare table matches exactly</span><b class="tnum">${pct(v.fares.exact_share)}</b></div>
          <div class="kv"><span>Fare table, typical error per ticket</span><b class="tnum">${rupees(v.fares.mean_abs_error_rs)}</b></div>` : ""}
          ${sp.holdout ? `<div class="kv"><span>Speeds on ${date(sp.holdout.test_day.replace(/_/g, "-"))} predicted from earlier days, typical error</span><b class="tnum">${sp.holdout.median_abs_pct_error}%</b></div>` : ""}</div>
      </div><div>
        <div class="section-title"><h2 class="t-heading">Bus speed through the day</h2></div>
        <div class="card chart-card"><div class="chart-head"><span class="t-small-strong">Average weekday speed, km/h · drag to explore</span></div>
          <svg id="speed-chart" class="chart" viewBox="0 0 340 120" preserveAspectRatio="none" role="img" aria-label="Average weekday bus speed by hour"></svg>
          <div class="axis t-caption"><span>12 am</span><span>6 am</span><span>12 pm</span><span>6 pm</span><span>11 pm</span></div></div>
      </div></div>` : ""}
      ${v.stability ? (() => { const st = v.stability, pk = Object.values(st.busiest_slot_by_week), am = Object.values(st.am_peak_vs_midday_by_week);
        return `<div class="section-title"><h2 class="t-heading">Week to week</h2><span class="t-small muted">${st.full_weeks.length} full weeks of October weekdays, compared with each other</span></div>
        <div class="card list-card">
          <div class="kv"><span>Riders by route and half hour, how closely one week matches another</span><b class="tnum">correlation ${st.corr_min.toFixed(2)} or higher</b></div>
          <div class="kv"><span>Typical change in one route's half hour from one week to the next</span><b class="tnum">${Math.round(Math.min(...st.median_rel_change) * 100)} to ${Math.round(Math.max(...st.median_rel_change) * 100)}%</b></div>
          <div class="kv"><span>Busiest weekday half hour, each week</span><b class="tnum">${[...new Set(pk)].map((x) => clock(x * 30)).join(" or ")}</b></div>
          <div class="kv"><span>Morning rush compared with midday, each week</span><b class="tnum">${Math.min(...am).toFixed(1)} to ${Math.max(...am).toFixed(1)} times</b></div>
          <div class="kv"><span>Of the 20 busiest routes, how many stay in the top 20 the next week</span><b class="tnum">${Math.round(Math.min(...st.top20_route_overlap) * 20)} to ${Math.round(Math.max(...st.top20_route_overlap) * 20)}</b></div></div>`; })() : ""}
      <div class="section-title"><h2 class="t-heading">How it works</h2></div>
      <div class="card method"><ol>
        <li><b>Stops in the right order.</b> Each route is lined up with the same route in the Delhi bus timetable (GTFS), matching stop names among that route's own stops. A stop the timetable doesn't list goes where its riders' tickets say it belongs. Routes the timetable doesn't know are ordered from millions of ticket start and end pairs, because people only ride forwards.</li>
        <li><b>Each ticket counts on every stretch it rides.</b> A ticket from stop A to stop F is one person on board from A all the way to F.</li>
        <li><b>Weekdays, Saturdays, and Sundays or holidays are kept apart.</b> Holidays are spotted as weekdays with much lower demand.</li>
        <li><b>A crowd index from 0 to 100.</b> It's calibrated across the whole network, so busy corridors and quiet hours both read clearly.</li>
        <li><b>Travel times from real roads and real buses.</b> Each ride is timed stretch by stretch: the stretch's length comes from the timetable's stop positions, and its speed from how fast GPS-tracked buses moved through that part of Delhi in that half hour, stops at signals and bus stops included. Buses parked at terminals are left out.</li>
        <li><b>Waiting from the timetable.</b> The DTC timetable lists every scheduled departure. Shifted to each stop by its scheduled running time, it gives how often a bus comes there at that hour and the average wait for someone who turns up then. That wait is part of every trip time, and a change of bus adds a 3-minute walk plus the wait for the next bus.</li>
        <li><b>Fares from what riders paid.</b> For each route, the fare for riding a given number of stops is the price most October e-tickets paid for that ride. Fares come in fixed steps (the DTC fare less the 10% e-ticket discount), and a longer ride never costs less. A trip with a change of bus needs one ticket per bus.</li>
        <li><b>Live by default.</b> The site follows the current time in Delhi and moves on every half hour. Crowding is what's typical for that time, learned from October tickets, not a live count.</li>
      </ol></div>
      ${notice("warn", "What this can't tell you yet", `E-tickets are only some of the riders, so the index compares crowding rather than counting people. Routes with fewer than 600 tickets are marked as limited data. A few routes (about 2% of tickets) aren't in the current timetable, so they are timed from their end stops only. Saturday speeds are the average of weekday and Sunday speeds, because no Saturday GPS was processed. Waiting times follow the DTC timetable; real buses can bunch up or run late.`, IC.alert)}
      <p class="t-small muted">Seat Signal is built for the Transport Stack Hackathon 2026, Delhi, Problem 2: crowdedness-aware journey planner. Data: ONDC bus e-ticketing from Transport Stack and IIIT Delhi. API documentation: <a class="link" href="/docs">/docs</a>.</p></div>`;
    const wkB = v.weekday_boardings_by_slot.slice(10, 47), suB = v.weekend_boardings_by_slot.slice(10, 47);
    iChart($("#about-chart"), [{ values: suB, color: css("--silver-edge"), width: 1.5 }, { values: wkB, color: css("--brand"), fill: 0.07, marker: true }], { max: Math.max(...wkB), index: 8,
      describe: (i) => `<b>${clock((i + 10) * 30)}</b> · weekday ${inr(Math.round(wkB[i]))} · Sunday ${inr(Math.round(suB[i]))}`,
      hint: "Boardings per half hour. Use the arrow keys to move through the day." });
    if (kmh.length && $("#speed-chart")) iChart($("#speed-chart"), [{ values: kmh, color: css("--brand"), fill: 0.07, marker: true }], { max: Math.max(...kmh) * 1.1, index: 18,
      describe: (i) => `<b>${clock(i * 60)}</b> · ${kmh[i]} km/h on average`,
      hint: "Average weekday bus speed by hour. Use the arrow keys to move through the day." });
  } catch (e) { $("#about-body").innerHTML = errorBox(e.message); }
}

/* ================================================================= router */
const ROUTES_TABLE = [
  [/^\/?$/, "home", () => pageHome()],
  [/^\/plan$/, "plan", (_, p) => pagePlan(p)],
  [/^\/best$/, "best", (_, p) => pageBest(p)],
  [/^\/crowd$/, "home", () => pageCrowd()],
  [/^\/routes$/, "routes", (_, p) => pageRoutes(p)],
  [/^\/route\/(.+)$/, "routes", (m) => pageRoute(decodeURIComponent(m[1]))],
  [/^\/stops$/, "stops", () => pageStops()],
  [/^\/stop\/(.+)$/, "stops", (m) => pageStop(decodeURIComponent(m[1]))],
  [/^\/about$/, "about", () => pageAbout()],
];
let lastPath = null;
function render({ quiet = false } = {}) {
  const raw = location.hash.replace(/^#/, "") || "/";
  const [path, qs] = raw.split("?");
  const params = new URLSearchParams(qs || "");
  const hit = ROUTES_TABLE.find(([re]) => re.test(path)) || ROUTES_TABLE[0];
  const m = path.match(hit[0]) || [];
  $$("[data-nav]").forEach((a) => a.classList.toggle("on", a.dataset.nav === hit[1]));
  // Keep typed input on quiet refreshes of the plan / best pages: just re-run results.
  if (quiet && path === "/plan" && params.get("from") && params.get("to") && $("#results")) return runPlan(params.get("from"), params.get("to"));
  if (quiet && !params.get("from") && ((path === "/plan" && $("#plan-form")) || (path === "/best" && $("#best-form")))) return;
  const y = window.scrollY;
  dropMaps();
  hit[2](m, params);
  if (!quiet && lastPath !== raw) { window.scrollTo(0, 0); view.focus({ preventScroll: true }); } else window.scrollTo(0, y);
  lastPath = raw;
}

window.addEventListener("hashchange", () => render());
setupWhen();
tick();                 // sets live time; renders once because the slot is new
setInterval(tick, 20000);
