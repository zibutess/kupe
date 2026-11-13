const API = "http://localhost:8000";
let chatId = null;
let busy = false;

const $ = (sel) => document.querySelector(sel);
const messagesEl = $("#messages");
const textEl = $("#text");

async function api(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

// "!" after a time = predicted timetable. Turn it into a badge and tint the row;
// a paragraph starting with "! =" is the legend and becomes a callout.
function markPredicted(el) {
  el.querySelectorAll("tbody tr").forEach((tr) => {
    const cell = tr.cells[tr.cells.length - 1];
    const m = cell && cell.textContent.match(/^\s*(?:\(?predicted\)?|!)\s*[·:,;-]?\s*(.*)$/i);
    if (!m) return;
    const badge = document.createElement("span");
    badge.className = "predicted-badge";
    badge.textContent = "predicted";
    badge.title = "Predicted timetable: may differ";
    cell.textContent = m[1] ? " " + m[1] : "";
    cell.prepend(badge);
    tr.classList.add("predicted");
  });
  el.querySelectorAll("p").forEach((p) => {
    if (/^\s*(!|predicted)\s*=/i.test(p.textContent)) p.classList.add("predicted-legend");
  });
}

function bubble(role, text) {
  const el = document.createElement("div");
  el.className = `bubble ${role}`;
  if (role === "agent") {
    el.innerHTML = DOMPurify.sanitize(marked.parse(text));
    markPredicted(el);
    el.querySelectorAll("table").forEach((t) => {
      const card = document.createElement("div");
      card.className = "table-card";
      t.replaceWith(card);
      card.append(t);
    });
    if (el.querySelector("table")) el.classList.add("wide");
  }
  else el.textContent = text;
  messagesEl.append(el);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return el;
}

// ---- booking checklist: ordered legs, deep link to the operator, tick off as booked ----
const bookKey = (id, i) => `kupe:booked:${id}:${i}`;
const loadBooked = (key) => { try { return new Set(JSON.parse(localStorage.getItem(key) || "[]")); } catch { return new Set(); } };

function bookingCard(items, id, msgIndex) {
  const key = bookKey(id, msgIndex);
  const done = loadBooked(key);
  const card = document.createElement("section");
  card.className = "booking";
  const head = document.createElement("div");
  head.className = "booking-head";
  const title = document.createElement("span");
  title.textContent = "Book your journey";
  const count = document.createElement("span");
  count.className = "booking-count";
  head.append(title, count);
  const ol = document.createElement("ol");

  const refresh = () => {
    count.textContent = `${done.size} of ${items.length} booked`;
    card.classList.toggle("all-done", done.size === items.length);
  };

  items.forEach((it, i) => {
    const li = document.createElement("li");
    li.classList.toggle("done", done.has(i));
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = done.has(i);
    box.setAttribute("aria-label", `Mark ${it.label} as booked`);
    box.onchange = () => {
      box.checked ? done.add(i) : done.delete(i);
      li.classList.toggle("done", box.checked);
      localStorage.setItem(key, JSON.stringify([...done]));
      refresh();
    };

    const body = document.createElement("div");
    body.className = "leg";
    const route = document.createElement("strong");
    route.textContent = it.label;
    const meta = document.createElement("span");
    meta.className = "leg-meta";
    meta.textContent = [it.date, it.depart, [it.operator, it.train].filter(Boolean).join(" ")]
      .filter(Boolean).join(" · ");
    body.append(route, meta);
    if (it.note) {
      const note = document.createElement("span");
      note.className = "leg-note";
      note.textContent = it.note;
      body.append(note);
    }

    const actions = document.createElement("div");
    actions.className = "leg-actions";
    if (/^https?:\/\//.test(it.url)) {
      const a = document.createElement("a");
      a.href = it.url; a.target = "_blank"; a.rel = "noopener noreferrer";
      a.textContent = "Open booking";
      actions.append(a);
    } else {
      const none = document.createElement("span");
      none.className = "leg-meta";
      none.textContent = "Check the operator";
      actions.append(none);
    }
    // operator pages don't take reliable prefilled params, so copy what to type in
    const copy = document.createElement("button");
    copy.type = "button";
    copy.textContent = "Copy details";
    copy.onclick = async () => {
      const text = `${it.label}${it.date ? ", " + it.date : ""}${it.depart ? " " + it.depart : ""}${it.train ? " (" + it.train + ")" : ""}`;
      try { await navigator.clipboard.writeText(text); copy.textContent = "Copied"; }
      catch { copy.textContent = text; }
      setTimeout(() => (copy.textContent = "Copy details"), 1600);
    };
    actions.append(copy);

    li.append(box, body, actions);
    ol.append(li);
  });
  refresh();
  card.append(head, ol);
  return card;
}

function questionForm(questions) {
  const form = document.createElement("form");
  form.className = "questions";
  for (const q of questions) {
    const label = document.createElement("label");
    label.textContent = q.label;
    const input = document.createElement("input");
    input.placeholder = q.placeholder || "";
    input.dataset.label = q.label;
    label.append(input);
    form.append(label);
  }
  const btn = document.createElement("button");
  btn.textContent = "Send answers";
  form.append(btn);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const lines = [...form.querySelectorAll("input")]
      .filter((i) => i.value.trim())
      .map((i) => `${i.dataset.label} ${i.value.trim()}`);
    if (lines.length) send(lines.join("\n"));
  });
  return form;
}

function renderChat(chat) {
  chatId = chat.id;
  messagesEl.innerHTML = "";
  messagesEl.append($("#hero").content.cloneNode(true));
  chat.messages.forEach((m, i) => {
    const el = bubble(m.role, m.text);
    if (i === 0 && m.role === "agent") el.classList.add("opening");
    if (m.role === "agent" && m.booking && m.booking.length) {
      el.append(bookingCard(m.booking, chat.id, i));
      el.classList.add("wide");
    }
    const isLast = i === chat.messages.length - 1;
    if (m.role === "agent" && m.questions.length && isLast) {
      el.append(questionForm(m.questions));
    }
  });
  const first = messagesEl.querySelector(".questions input");
  (first || textEl).focus();
}

function setBusy(value) {
  busy = value;
  $("#send").disabled = value;
  textEl.disabled = value;
  messagesEl.querySelectorAll(".questions button").forEach((b) => (b.disabled = value));
}

async function send(text) {
  if (busy || !chatId) return;
  setBusy(true);
  messagesEl.querySelectorAll(".questions").forEach((f) => f.remove());
  bubble("user", text);
  const thinking = bubble("agent", "Thinking");
  thinking.classList.add("thinking");
  const sentTo = chatId;
  try {
    const chat = await api(`/chats/${sentTo}/messages`, {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    if (chatId === sentTo) renderChat(chat); // user may have switched journeys meanwhile
    loadList();
  } catch (err) {
    thinking.classList.remove("thinking");
    thinking.textContent = "Something went wrong: " + err.message;
  }
  setBusy(false);
  textEl.focus();
}

async function loadList() {
  const chats = await api("/chats");
  const list = $("#chat-list");
  list.innerHTML = "";
  for (const c of chats) {
    const li = document.createElement("li");
    li.textContent = c.title;
    if (c.id === chatId) li.className = "active";
    li.onclick = async () => {
      renderChat(await api(`/chats/${c.id}`));
      closeDrawer();
      loadList();
    };
    list.append(li);
  }
}

async function newChat() {
  const btn = $("#new-chat");
  if (btn.disabled) return;
  btn.disabled = true;
  btn.textContent = "Boarding…";
  try {
    renderChat(await api("/chats", { method: "POST" }));
    closeDrawer();
    setBusy(false);
    loadList();
    btn.textContent = "+ New journey";
  } catch (err) {
    console.error(err);
    btn.textContent = "Couldn’t start — tap to retry";
  }
  btn.disabled = false;
}

const closeDrawer = () => document.body.classList.remove("open");
$("#menu").onclick = () => document.body.classList.add("open");
$("#scrim").onclick = closeDrawer;

$("#composer").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = textEl.value.trim();
  if (!text) return;
  textEl.value = "";
  send(text);
});
$("#new-chat").onclick = newChat;

(async () => {
  const chats = await api("/chats");
  if (chats.length) renderChat(await api(`/chats/${chats[0].id}`));
  else await newChat();
  loadList();
})();
