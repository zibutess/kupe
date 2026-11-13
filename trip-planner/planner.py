import os, json, uuid, anthropic
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
from agent.transit import TOOL_HANDLERS

client = anthropic.Anthropic()
MAX_TOOL_CALLS = 4          # per user message, caps Google spend
CHAT_DIR = Path("chats")
CHAT_DIR.mkdir(exist_ok=True)
FIRST_QUESTION = "What is your next destination?"


# ---------- saved chats ----------

def chat_path(chat_id: str) -> Path:
    return CHAT_DIR / f"{chat_id}.json"

def save_chat(chat: dict) -> None:
    chat_path(chat["id"]).write_text(json.dumps(chat, indent=2, ensure_ascii=False))

def list_chats() -> list[dict]:
    chats = [json.loads(p.read_text()) for p in CHAT_DIR.glob("*.json")]
    return sorted(chats, key=lambda c: c["created"], reverse=True)

def new_chat() -> dict:
    session = client.beta.sessions.create(
        agent=os.environ["AGENT_ID"],
        environment_id=os.environ["ENVIRONMENT_ID"],
        vault_ids=[os.environ["VAULT_ID"]],
        title="Trip plan",
    )
    chat = {
        "id": uuid.uuid4().hex[:8],
        "session_id": session.id,
        "created": datetime.now().isoformat(timespec="seconds"),
        "messages": [],     # [{"role": "user"|"agent", "text": "..."}]
        "seen": [],         # event ids already handled (avoids replays on resume)
    }
    save_chat(chat)
    return chat


# ---------- talking to the agent ----------

def send_message(chat: dict, text: str) -> str:
    out, pending, calls = [], {}, 0
    seen = set(chat["seen"])

    with client.beta.sessions.events.stream(chat["session_id"]) as stream:
        client.beta.sessions.events.send(
            chat["session_id"],
            events=[{"type": "user.message",
                     "content": [{"type": "text", "text": text}]}],
        )
        for event in stream:
            eid_ = getattr(event, "id", None)
            if eid_ and eid_ in seen:
                continue            # old event replayed on a resumed session
            if eid_:
                seen.add(eid_)

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


# ---------- chat loop ----------

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

def show_history(chat: dict) -> None:
    for m in chat["messages"]:
        who = "You" if m["role"] == "user" else "Agent"
        print(f"\n{who}: {m['text']}")

def main() -> None:
    chat = choose_chat()
    if chat["messages"]:
        show_history(chat)
    else:
        print(f"\nAgent: {FIRST_QUESTION}")
        chat["messages"].append({"role": "agent", "text": FIRST_QUESTION})
        save_chat(chat)

    print("\n(type 'quit' to exit; your chat is saved)")
    while True:
        text = input("\nYou: ").strip()
        if text.lower() in ("quit", "exit"):
            break
        if not text:
            continue

        first_turn = not any(m["role"] == "user" for m in chat["messages"])
        chat["messages"].append({"role": "user", "text": text})
        # the first answer is the destination, so label it for the agent
        payload = f"My next destination: {text}" if first_turn else text

        reply = send_message(chat, payload)
        chat["messages"].append({"role": "agent", "text": reply})
        save_chat(chat)
        print(f"\nAgent: {reply}")

if __name__ == "__main__":
    main()
