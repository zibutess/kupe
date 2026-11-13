"""Step 5: checks that db.py works against the real Supabase database.

Run:  python test_db.py
Creates a temporary test user, tries every db.py function, then deletes
everything it created (deleting the user also deletes their chats and trips).
"""
import uuid

import db

ok = lambda msg: print("  OK  ", msg)

email = f"test-{uuid.uuid4().hex[:8]}@example.com"
user = db.db().auth.admin.create_user(
    {"email": email, "password": uuid.uuid4().hex, "email_confirm": True}
).user
uid = user.id
ok(f"temporary user created ({email})")

cache_k = db.cache_key("test", uid)
cache_keys = [cache_k]
try:
    # chats
    chat = db.new_chat(uid, "test-session")
    chat["messages"].append({"role": "user", "text": "Vilnius to London by train"})
    chat["messages"].append({"role": "agent", "text": "Here is a plan..."})
    db.save_chat(chat)
    again = db.get_chat(uid, chat["id"])
    assert again and len(again["messages"]) == 2, "chat not saved"
    assert again["title"] == "Vilnius to London by train", "title not set"
    ok("chat saved and read back")

    other = str(uuid.uuid4())
    assert db.get_chat(other, chat["id"]) is None, "another user can see the chat!"
    ok("another user cannot read this chat")
    assert len(db.list_chats(uid)) == 1
    ok("chat list works")

    # a chat can start without a Claude session (the new planner creates it on the first message)
    lazy = db.new_chat(uid, messages=[{"role": "agent", "text": "What is your next destination?"}])
    lazy["session_id"] = "test-session-2"
    db.save_chat(lazy)
    assert db.get_chat(uid, lazy["id"])["session_id"] == "test-session-2", "session_id not saved"
    ok("chat without a session works, session_id saved later")

    # trips + share link
    trip = db.save_trip(uid, "Vilnius -> London", {"legs": []}, chat["id"])
    assert db.get_shared_trip(trip["share_id"]) is None, "trip visible before sharing!"
    ok("trip saved, hidden until shared")
    share_id = db.set_trip_shared(uid, trip["id"], True)
    assert db.get_shared_trip(share_id)["title"] == "Vilnius -> London"
    ok(f"share link works (share_id length {len(share_id)})")
    db.set_trip_shared(uid, trip["id"], False)
    assert db.get_shared_trip(share_id) is None
    ok("share link turned off again")

    # night trains (table is still empty, just check it answers)
    db.night_trains("Vienna")
    ok("night train lookup answers")

    # cache
    db.cache_set(cache_k, "transit", {"hello": "world"}, ttl_seconds=60)
    assert db.cache_get(cache_k) == {"hello": "world"}
    ok("cache save/read works")

    # transit tool uses the database cache (no Google call: answer is pre-saved)
    import os
    if not os.environ.get("GOOGLE_MAPS_API_KEY"):
        os.environ["GOOGLE_MAPS_API_KEY"] = "not-needed-for-this-check"
    from agent.transit import plan_transit_trip
    transit_k = db.cache_key("transit", "Test A", "Test B", None)
    cache_keys.append(transit_k)
    db.cache_set(transit_k, "transit", {"itineraries": ["from cache"]}, ttl_seconds=60)
    assert plan_transit_trip("Test A", "Test B") == {"itineraries": ["from cache"]}
    ok("transit tool reads from the database cache")

    print("\nALL CHECKS PASSED")
finally:
    db.db().table("cache").delete().in_("key", cache_keys).execute()
    db.db().auth.admin.delete_user(uid)
    print("cleaned up test data")
