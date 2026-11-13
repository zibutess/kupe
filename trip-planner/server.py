from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import planner

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],  # dev only
    allow_methods=["*"],
    allow_headers=["*"],
)

class Msg(BaseModel):
    text: str

def public(chat: dict) -> dict:
    msgs = []
    for m in chat["messages"]:
        if m["role"] == "agent":
            text, booking = planner.split_booking(m["text"], chat.get("urls", []))
            text, questions = planner.split_questions(text)
        else:
            text, questions, booking = m["text"], [], []
        msgs.append({"role": m["role"], "text": text, "questions": questions, "booking": booking})
    return {"id": chat["id"], "messages": msgs}

def get_or_404(chat_id: str) -> dict:
    chat = planner.load_chat(chat_id)
    if chat is None:
        raise HTTPException(404, "chat not found")
    return chat

@app.get("/chats")
def list_chats():
    out = []
    for c in planner.list_chats():
        first = next((m["text"] for m in c["messages"] if m["role"] == "user"), "New chat")
        out.append({"id": c["id"], "title": first[:40], "created": c["created"]})
    return out

@app.post("/chats")
def create_chat():
    return public(planner.new_chat())

@app.get("/chats/{chat_id}")
def get_chat(chat_id: str):
    return public(get_or_404(chat_id))

@app.post("/chats/{chat_id}/messages")
def post_message(chat_id: str, body: Msg):
    chat = get_or_404(chat_id)
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "empty message")
    planner.handle_user_text(chat, text)
    return public(chat)
