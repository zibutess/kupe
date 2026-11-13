import os, re, json, uuid, anthropic
from dotenv import load_dotenv

load_dotenv()
import db
from agent.transit import TOOL_HANDLERS as TRANSIT_HANDLERS
from agent.attractions import TOOL_HANDLERS as ATTRACTION_HANDLERS
from agent.night_trains import TOOL_HANDLERS as NIGHT_HANDLERS

TOOL_HANDLERS = {**TRANSIT_HANDLERS, **ATTRACTION_HANDLERS, **NIGHT_HANDLERS}

client = anthropic.Anthropic()
MAX_TOOL_CALLS = 8         # per user message, caps Google spend
FIRST_QUESTION = "What is your next destination?"
QUESTIONS_RE = re.compile(r"```questions\s*(.*?)```", re.S)
BOOKING_RE = re.compile(r"```booking\s*(.*?)```", re.S)
BOOKING_FIELDS = ("label", "operator", "train", "date", "depart", "note")


# ---------- helpers ----------

def split_questions(text: str):
    """Return (text without the questions block, list of questions)."""
    m = QUESTIONS_RE.search(text)
    if not m:
        return text, []
    try:
        questions = json.loads(m.group(1))
    except json.JSONDecodeError:
        return text, []
    return QUESTIONS_RE.sub("", text).strip(), questions


def collect_urls(data, out: set) -> None:
    """Every http(s) URL found anywhere in a tool result."""
    if isinstance(data, str):
        if data.startswith(("http://", "https://")):
            out.add(data)
    elif isinstance(data, dict):
        for v in data.values():
            collect_urls(v, out)
    elif isinstance(data, list):
        for v in data:
            collect_urls(v, out)


def split_booking(text: str, allowed_urls=()):
    """Return (text without the booking block, checklist items).

    A link is kept only if a tool returned that exact URL this chat, so the
    model can never put an invented link in front of someone about to pay.
    """
    m = BOOKING_RE.search(text)
    if not m:
        return text, []
    stripped = BOOKING_RE.sub("", text).strip()
    try:
        raw = json.loads(m.group(1))
    except json.JSONDecodeError:
        return stripped, []
    allowed = set(allowed_urls)
    items = []
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict):
            continue
        item = {k: str(r[k])[:120] for k in BOOKING_FIELDS if r.get(k)}
        url = r.get("url")
        item["url"] = url if isinstance(url, str) and url in allowed else ""
        if item.get("label"):
            items.append(item)
    return stripped, items


# ---------- saved chats (Supabase, see db.py) ----------
# Every chat belongs to one user. Until sign-in exists, the user is DEV_USER_ID
# from .env. Later server.py will pass the signed-in user's id instead.

def _user(user_id: str | None) -> str:
    return user_id or os.environ["DEV_USER_ID"]

def _shape(row: dict) -> dict:
    """Database row -> the chat dict the rest of the code expects."""
    row["created"] = row["created_at"][:19].replace("T", " ")
    return row

def save_chat(chat: dict) -> None:
    db.save_chat(chat)

def load_chat(chat_id: str, user_id: str | None = None):
    try:
        uuid.UUID(chat_id)
    except ValueError:
        return None
    row = db.get_chat(_user(user_id), chat_id)
    return _shape(row) if row else None

def list_chats(user_id: str | None = None) -> list[dict]:
    return [_shape(r) for r in db.list_chats(_user(user_id), with_messages=True)]

def new_chat(user_id: str | None = None) -> dict:
    """Instant: the agent session is created lazily on the first message."""
    row = db.new_chat(_user(user_id),
                      messages=[{"role": "agent", "text": FIRST_QUESTION}])
    return _shape(row)


# ---------- talking to the agent ----------

def ensure_session(chat: dict) -> None:
    if chat.get("session_id"):
        return
    session = client.beta.sessions.create(
        agent=os.environ["AGENT_ID"],
        environment_id=os.environ["ENVIRONMENT_ID"],
        vault_ids=[os.environ["VAULT_ID"]],
        title="Trip plan",
    )
    chat["session_id"] = session.id
    save_chat(chat)

def send_message(chat: dict, text: str) -> str:
    ensure_session(chat)
    out, pending, calls = [], {}, 0
    seen = set(chat["seen"])

    with client.beta.sessions.events.stream(chat["session_id"]) as stream:
        client.beta.sessions.events.send(
            chat["session_id"],
            events=[{"type": "user.message",
                     "content": [{"type": "text", "text": text}]}],
        )
        for event in stream:
            event_id = getattr(event, "id", None)
            if event_id and event_id in seen:
                continue
            if event_id:
                seen.add(event_id)

            if event.type == "agent.message":
                out += [b.text for b in event.content if b.type == "text"]

            elif event.type == "agent.custom_tool_use":
                pending[event.id] = event

            elif event.type == "session.status_idle":
                if event.stop_reason.type == "requires_action":
                    results = []
                    for eid in event.stop_reason.event_ids:
                        ev = pending.get(eid)
                        if ev is None:
                            continue
                        calls += 1
                        handler = TOOL_HANDLERS.get(ev.name)
                        if calls > MAX_TOOL_CALLS:
                            data = {"error": "tool call budget reached"}
                        elif handler:
                            data = handler(**ev.input)
                            urls = set(chat.get("urls", []))
                            collect_urls(data, urls)
                            chat["urls"] = sorted(urls)
                        else:
                            data = {"error": f"unknown tool {ev.name}"}
                        results.append({
                            "type": "user.custom_tool_result",
                            "custom_tool_use_id": eid,
                            "content": [{"type": "text", "text": json.dumps(data)}],
                        })
                    if results:
                        client.beta.sessions.events.send(chat["session_id"], events=results)
                    continue
                break

    chat["seen"] = list(seen)
    return "".join(out)


def handle_user_text(chat: dict, text: str) -> str:
    """One user turn: send to agent, store both sides, save."""
    first_turn = not any(m["role"] == "user" for m in chat["messages"])
    chat["messages"].append({"role": "user", "text": text})
    payload = f"My next destination: {text}" if first_turn else text
    reply = send_message(chat, payload)
    chat["messages"].append({"role": "agent", "text": reply})
    save_chat(chat)
    return reply


# ---------- terminal chat (for testing without the frontend) ----------

def choose_chat() -> dict:
    chats = list_chats()
    if not chats:
        return new_chat()
    print("Saved chats:")
    for i, c in enumerate(chats, 1):
        first = next((m["text"] for m in c["messages"] if m["role"] == "user"), "(empty)")
        print(f"  {i}. {c['created']}  {first[:50]}")
    print("  n. New chat")
    pick = input("Open which? ").strip().lower()
    if pick.isdigit() and 1 <= int(pick) <= len(chats):
        return chats[int(pick) - 1]
    return new_chat()

def ask_questions(questions: list[dict]) -> str:
    print("\nThe agent has a few questions (leave blank to skip):")
    lines = []
    for q in questions:
        hint = f" ({q['placeholder']})" if q.get("placeholder") else ""
        ans = input(f"  [ ______ ] {q['label']}{hint}: ").strip()
        if ans:
            lines.append(f"{q['label']} {ans}")
    return "\n".join(lines)

def main() -> None:
    chat = choose_chat()
    questions = []
    for m in chat["messages"]:
        who = "You" if m["role"] == "user" else "Agent"
        shown, questions = split_questions(split_booking(m["text"])[0]) if m["role"] == "agent" else (m["text"], [])
        print(f"\n{who}: {shown}")

    print("\n(type 'quit' to exit; your chat is saved)")
    while True:
        text = ask_questions(questions) if questions else ""
        if not text:
            text = input("\nYou: ").strip()
        if text.lower() in ("quit", "exit"):
            break
        if not text:
            continue
        reply = handle_user_text(chat, text)
        shown, questions = split_questions(split_booking(reply)[0])
        print(f"\nAgent: {shown}")

if __name__ == "__main__":
    main()
