import os, json, time, hashlib
import requests

CACHE_TTL = 300  # keep short; check Google's Places caching terms before raising
_cache: dict[str, tuple[float, dict]] = {}

ATTRACTIONS_TOOL = {
    "type": "custom",
    "name": "find_attractions",
    "description": "Find the most popular tourist attractions in a city.",
    "input_schema": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "City name, e.g. Prague"},
            "interest": {"type": "string", "description": "Optional, e.g. museums, old town, parks"},
        },
        "required": ["city"],
    },
}

# Rating fields (rating, userRatingCount) are billed under a more expensive Places tier,
# so they are left out on purpose. Google already ranks "top attractions" queries by prominence.
_FIELDS = ",".join([
    "places.displayName",
    "places.primaryTypeDisplayName",
    "places.formattedAddress",
    "places.googleMapsUri",
])


def find_attractions(city: str, interest: str | None = None, limit: int = 8) -> dict:
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY not set"}

    key = hashlib.sha1(json.dumps([city.lower(), interest]).encode()).hexdigest()
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_TTL:
        return hit[1]

    body = {"pageSize": min(limit, 10), "languageCode": "en"}
    if interest:
        body["textQuery"] = f"{interest} in {city}"
    else:
        body["textQuery"] = f"top tourist attractions in {city}"
        body["includedType"] = "tourist_attraction"

    try:
        r = requests.post(
            "https://places.googleapis.com/v1/places:searchText",
            headers={"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": _FIELDS},
            json=body, timeout=10,
        )
    except requests.RequestException as e:
        return {"error": f"places request failed: {e}"}
    if r.status_code != 200:
        return {"error": f"places failed ({r.status_code})", "detail": r.text[:300]}

    attractions = [{
        "name": p.get("displayName", {}).get("text"),
        "type": p.get("primaryTypeDisplayName", {}).get("text"),
        "address": p.get("formattedAddress"),
        "maps_url": p.get("googleMapsUri"),
    } for p in r.json().get("places", [])[:limit]]

    result = {"city": city, "attractions": attractions}
    _cache[key] = (time.time(), result)
    return result


TOOL_HANDLERS = {"find_attractions": find_attractions}
