import os, json, time, hashlib
import requests

CACHE_TTL = 60  # seconds; check Google's caching terms before raising this
_cache: dict[str, tuple[float, dict]] = {}

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

    key = hashlib.sha1(json.dumps([origin, destination, depart_at]).encode()).hexdigest()
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]

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
    _cache[key] = (time.time(), result)
    return result


# tool name -> function, used by planner.py
TOOL_HANDLERS = {"plan_transit_trip": plan_transit_trip}
