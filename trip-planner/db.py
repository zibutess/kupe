"""Supabase access for the trip planner.

Uses the SECRET key, which skips the database access rules (RLS).
So every function that touches a user's data takes user_id and filters by it;
never call these with a user_id that the request didn't prove it owns.
"""
import os, json, hashlib
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()


@lru_cache(maxsize=1)
def db() -> Client:
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])


# ---------- chats ----------

def new_chat(user_id: str, session_id: str | None = None, messages: list | None = None) -> dict:
    row = {"user_id": user_id, "session_id": session_id, "messages": messages or [], "seen": []}
    return db().table("chats").insert(row).execute().data[0]

def get_chat(user_id: str, chat_id: str) -> dict | None:
    res = (db().table("chats").select("*")
           .eq("id", chat_id).eq("user_id", user_id).limit(1).execute())
    return res.data[0] if res.data else None

def list_chats(user_id: str, with_messages: bool = False) -> list[dict]:
    """Newest first; without messages unless asked, to keep it light."""
    cols = "id, title, created_at, updated_at" + (", messages" if with_messages else "")
    return (db().table("chats").select(cols)
            .eq("user_id", user_id).order("created_at", desc=True).execute().data)

def save_chat(chat: dict) -> None:
    """Saves session_id, messages, seen and title. Title = first user message, if not set."""
    if not chat.get("title"):
        first = next((m["text"] for m in chat["messages"] if m["role"] == "user"), None)
        chat["title"] = first[:80] if first else None
    (db().table("chats")
     .update({"session_id": chat.get("session_id"), "messages": chat["messages"],
              "seen": chat["seen"], "title": chat["title"]})
     .eq("id", chat["id"]).eq("user_id", chat["user_id"]).execute())


# ---------- trips ----------

def save_trip(user_id: str, title: str, plan: dict, chat_id: str | None = None) -> dict:
    row = {"user_id": user_id, "title": title, "plan": plan, "chat_id": chat_id}
    return db().table("trips").insert(row).execute().data[0]

def list_trips(user_id: str) -> list[dict]:
    return (db().table("trips").select("id, title, is_shared, share_id, created_at")
            .eq("user_id", user_id).order("created_at", desc=True).execute().data)

def set_trip_shared(user_id: str, trip_id: str, shared: bool) -> str | None:
    """Turns the share link on/off. Returns share_id (None if trip not found)."""
    res = (db().table("trips").update({"is_shared": shared})
           .eq("id", trip_id).eq("user_id", user_id).execute())
    return res.data[0]["share_id"] if res.data else None

def get_shared_trip(share_id: str) -> dict | None:
    res = db().rpc("get_shared_trip", {"p_share_id": share_id}).execute()
    return res.data[0] if res.data else None


# ---------- night trains ----------

def night_trains(from_city: str | None = None, to_city: str | None = None) -> list[dict]:
    q = db().table("night_trains").select("*")
    if from_city:
        q = q.ilike("from_city", from_city)
    if to_city:
        q = q.ilike("to_city", to_city)
    return q.execute().data


# ---------- cache (Firecrawl / transit results) ----------

def cache_key(*parts) -> str:
    """Same inputs -> same key. Usage: cache_key("transit", origin, destination, depart_at)."""
    return hashlib.sha1(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()

def cache_get(key: str):
    """Saved data, or None if missing or expired."""
    res = db().table("cache").select("data, expires_at").eq("key", key).limit(1).execute()
    if not res.data:
        return None
    row = res.data[0]
    if row["expires_at"] and datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
        return None
    return row["data"]

def cache_set(key: str, source: str, data, ttl_seconds: int | None = None) -> None:
    """source: 'firecrawl' or 'transit'. ttl_seconds=None keeps it forever."""
    now = datetime.now(timezone.utc)
    expires = (now + timedelta(seconds=ttl_seconds)).isoformat() if ttl_seconds else None
    # tidy up: remove expired saved answers so the table doesn't keep growing
    db().table("cache").delete().lt("expires_at", now.isoformat()).execute()
    db().table("cache").upsert({
        "key": key, "source": source, "data": data,
        "created_at": now.isoformat(), "expires_at": expires,
    }).execute()
