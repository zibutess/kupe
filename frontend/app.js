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

function bubble(role, text) {
  const el = document.createElement("div");
  el.className = `bubble ${role}`;
  if (role === "agent") {
    el.innerHTML = DOMPurify.sanitize(marked.parse(text));
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
