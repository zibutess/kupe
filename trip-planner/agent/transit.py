import os
import requests

import db

CACHE_TTL = 60  # seconds; check Google's caching terms before raising this

TRANSIT_TOOL = {
    "type": "custom",
    "name": "plan_transit_trip",
    "description": (
        "Plan a city public transport trip (metro/bus/tram) between two places. "
        "Returns up to 3 itineraries with legs, lines, stops and times."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "origin": {"type": "string", "description": "Address or place name"},
            "destination": {"type": "string", "description": "Address or place name"},
            "depart_at": {
                "type": "string",
                "description": "RFC3339 time, e.g. 2026-12-20T09:00:00+02:00. Omit for now.",
            },
        },
        "required": ["origin", "destination"],
    },
}

_FIELDS = ",".join([
    "routes.duration",
    "routes.legs.steps.travelMode",
    "routes.legs.steps.staticDuration",
    "routes.legs.steps.transitDetails",
])


def plan_transit_trip(origin: str, destination: str, depart_at: str | None = None) -> dict:
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY not set"}

    # Saved answer in Supabase (shared by all users, survives restarts).
    # If the database is unreachable, just ask Google instead of failing.
    key = db.cache_key("transit", origin, destination, depart_at)
    try:
        hit = db.cache_get(key)
        if hit is not None:
            return hit
    except Exception as e:
        print(f"[cache] read failed: {e}")

    body = {
        "origin": {"address": origin},
        "destination": {"address": destination},
        "travelMode": "TRANSIT",
        "computeAlternativeRoutes": True,
    }
    if depart_at:
        body["departureTime"] = depart_at

    try:
        r = requests.post(
            "https://routes.googleapis.com/directions/v2:computeRoutes",
            headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": _FIELDS},
            json=body,
            timeout=10,
        )
    except requests.RequestException as e:
        return {"error": f"routing request failed: {e}"}
    if r.status_code != 200:
        return {"error": f"routing failed ({r.status_code})", "detail": r.text[:300]}

    itineraries = []
    for route in r.json().get("routes", [])[:3]:
        steps = []
        for s in route["legs"][0].get("steps", []):
            t = s.get("transitDetails")
            if t:
                line = t.get("transitLine", {})
                sd = t.get("stopDetails", {})
                steps.append({
                    "type": line.get("vehicle", {}).get("type"),
                    "line": line.get("nameShort") or line.get("name"),
                    "from": sd.get("departureStop", {}).get("name"),
                    "to": sd.get("arrivalStop", {}).get("name"),
                    "dep": sd.get("departureTime"),
                    "arr": sd.get("arrivalTime"),
                    "stops": t.get("stopCount"),
                })
            else:
                steps.append({"type": s.get("travelMode"), "duration": s.get("staticDuration")})
        itineraries.append({"duration": route.get("duration"), "steps": steps})

    result = {"itineraries": itineraries}
    if depart_at and depart_at[:10] > "2026-12-12":
        result["predicted"] = True
        result["predicted_note"] = ("Date is after the 13 Dec 2026 timetable change or beyond "
                                    "published data: these times are predicted and may differ. "
                                    "Show the plain time and start the Notes cell with 'predicted'.")
    try:
        db.cache_set(key, "transit", result, ttl_seconds=CACHE_TTL)
    except Exception as e:
        print(f"[cache] save failed: {e}")
    return result


# tool name -> function, used by planner.py
TOOL_HANDLERS = {"plan_transit_trip": plan_transit_trip}
