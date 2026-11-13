"""Night train lookup backed by the Open Night Train Database (Back-on-Track).

Data: https://github.com/Back-on-Track-eu/night-train-data (ODbL 1.0)
Attribution required: "Night train data © Back-on-Track Europe, Open Night Train
Database (ODbL 1.0), back-on-track.eu". The agent is told to credit it.

The database has no live prices or seat availability, only which trains exist,
where they stop, at what time, and on which days.
"""
import re, json, time, difflib, unicodedata
from datetime import date as Date, timedelta
from pathlib import Path
import requests

BASE = "https://back-on-track-eu.github.io/night-train-data/data/latest"
FILES = ["trips", "trip_stop", "agencies", "view_ontd_details"]   # ~1.6 MB; skip stops.json (11 MB)
CACHE_DIR = Path(__file__).parent / ".night_cache"
CACHE_TTL = 12 * 3600                                             # source refreshes twice a day
ATTRIBUTION = "Night train data © Back-on-Track Europe (ODbL 1.0), back-on-track.eu"

# Where else to look. Only generic pages: we can't verify that a given reseller
# sells a given train, so the agent must word these as "may also sell".
BOOKING_GUIDE = "https://back-on-track.eu/how-to-book-a-night-train/"
RESELLERS = [
    {"name": "Trainline", "url": "https://www.thetrainline.com/"},
    {"name": "Omio", "url": "https://www.omio.com/"},
]

NIGHT_TRAIN_TOOL = {
    "type": "custom",
    "name": "find_night_trains",
    "description": (
        "Find direct night trains between two European cities from the Open Night Train "
        "Database. Returns operator, train number, departure/arrival times, travel "
        "classes, whether it runs on the given date, and an operator booking link. "
        "No prices or availability. City names may be English or local; if nothing "
        "is found the result suggests similar station names and possible transfer "
        "cities."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "origin": {"type": "string", "description": "Origin city, e.g. Vienna or Wien"},
            "destination": {"type": "string", "description": "Destination city, e.g. Hamburg"},
            "date": {"type": "string", "description": "Optional travel date YYYY-MM-DD (the night of departure)."},
        },
        "required": ["origin", "destination"],
    },
}

# English exonym -> local name used in the database (accents are ignored in matching)
ALIASES = {
    "vienna": "wien", "munich": "munchen", "prague": "praha", "copenhagen": "kobenhavn",
    "brussels": "bruxelles", "cologne": "koln", "rome": "roma", "milan": "milano",
    "venice": "venezia", "florence": "firenze", "naples": "napoli", "turin": "torino",
    "warsaw": "warszawa", "krakow": "krakow", "bucharest": "bucuresti",
    "belgrade": "beograd", "lisbon": "lisboa", "zurich": "zurich", "geneva": "geneve",
    "athens": "athina", "moscow": "moskva", "kiev": "kyiv", "hanover": "hannover",
    "nuremberg": "nurnberg", "gothenburg": "goteborg", "bratislava": "bratislava",
    "cracow": "krakow", "gdansk": "gdansk", "luxemburg": "luxembourg",
    "the hague": "den haag", "basel": "basel", "bern": "bern",
}

_data: dict | None = None
_loaded_at = 0.0


# ---------- loading ----------

def _fetch(name: str) -> dict:
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / f"{name}.json"
    if path.exists() and time.time() - path.stat().st_mtime < CACHE_TTL:
        return json.loads(path.read_text())
    try:
        r = requests.get(f"{BASE}/{name}.json", timeout=20)
        r.raise_for_status()
        path.write_text(r.text)
        return r.json()
    except requests.RequestException:
        if path.exists():                            # stale cache beats no data
            return json.loads(path.read_text())
        raise


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def _hhmm(ts: str) -> str:
    # times are stored as "1899-12-30T19:28:00.000Z"; only HH:MM matters
    return ts[11:16] if ts else ""


def _minutes(ts: str) -> int | None:
    t = _hhmm(ts)
    return int(t[:2]) * 60 + int(t[3:]) if t else None


def _load() -> dict:
    global _data, _loaded_at
    if _data and time.time() - _loaded_at < CACHE_TTL:
        return _data
    raw = {n: _fetch(n) for n in FILES}
    stops: dict[str, list] = {}
    for row in raw["trip_stop"].values():
        if not row.get("trip_id") or not isinstance(row.get("stop_sequence"), int):
            continue                                 # blank/junk spreadsheet rows
        row["stop_id"] = str(row.get("stop_id") or "")
        stops.setdefault(row["trip_id"], []).append(row)
    for rows in stops.values():
        rows.sort(key=lambda r: r["stop_sequence"])
    # route_id -> operator booking page (the database's own "source" link)
    sources = {str(v["route_id"]): v["source"] for v in raw["view_ontd_details"].values()
               if str(v.get("source", "")).startswith("http")}
    names = sorted({r["stop_id"] for rows in stops.values() for r in rows})
    _data = {"trips": raw["trips"], "stops": stops, "agencies": raw["agencies"],
             "sources": sources, "names": names}
    _loaded_at = time.time()
    return _data


# ---------- which days does it run ----------

_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _runs_on(service: str, d: Date) -> bool | None:
    """Best-effort parse of strings like '2026: Mon, Wed, Fri', '2026/06/26-08/30: Daily',
    '2026: Daily, except Sat'. True/False if sure, None if the pattern is unclear."""
    if not service:
        return None
    head, _, pattern = service.partition(":")
    pattern = pattern.strip().lower()
    m = re.fullmatch(r"(\d{4})(?:/(\d\d)/(\d\d)-(?:(\d{4})/)?(\d\d)/(\d\d))?", head.strip())
    if not m or not pattern:
        return None
    year = int(m.group(1))
    if m.group(2):
        start = Date(year, int(m.group(2)), int(m.group(3)))
        end = Date(int(m.group(4) or year), int(m.group(5)), int(m.group(6)))
        if end < start:                              # range wraps over New Year
            end = Date(end.year + 1, end.month, end.day)
        if not start <= d <= end:
            return False
    elif d.year != year:
        return None                                  # plain "2026:" says nothing about 2027
    dow = _DAYS[d.weekday()]
    if pattern.startswith("daily"):
        exc = re.search(r"except\s+(\w{3})", pattern)
        return not (exc and exc.group(1) == dow)
    found = re.findall(r"\b(mon|tue|wed|thu|fri|sat|sun|son)\w*", pattern)
    if not found or re.search(r"times|every|week|day", pattern):
        return None                                  # "2-3 times per week", "every 2nd day"...
    return dow in {"sun" if f == "son" else f for f in found}


# ---------- search ----------

def _queries(city: str) -> list[str]:
    q = _norm(city)
    return [q] + ([ALIASES[q]] if q in ALIASES else [])


def _find(rows: list, queries: list[str]) -> list[int]:
    return [i for i, r in enumerate(rows)
            if any(q and q in _norm(r["stop_id"]) for q in queries)]


def _day_offsets(rows: list) -> list[int]:
    """Day number for each stop (0 = departure day), detected by the clock wrapping."""
    offsets, day, prev = [], 0, None
    for r in rows:
        for ts in (r["arrival_time"], r["departure_time"]):
            m = _minutes(ts)
            if m is None:
                continue
            if prev is not None and m < prev:
                day += 1
            prev = m
        offsets.append(day)
    return offsets


def _links(data: dict, trip: dict) -> dict:
    agency = data["agencies"].get(trip["agency_id"], {})
    book = data["sources"].get(str(trip.get("route_id"))) or agency.get("agency_url", "")
    return {"booking_url": book, "operator_site": agency.get("agency_url", "")}


def _suggest(data: dict, city: str) -> list[str]:
    q = _norm(city)
    norm = {_norm(n): n for n in data["names"]}
    q = ALIASES.get(q, q)
    prefix = [n for k, n in norm.items() if q and k.startswith(q)]
    close = difflib.get_close_matches(q, list(norm), n=5, cutoff=0.7)
    return list(dict.fromkeys(prefix + [norm[c] for c in close]))[:5]


def _transfers(data: dict, origin_q: list[str], dest_q: list[str]) -> list[str]:
    """Stations reachable by night train from origin AND from which a night train reaches destination."""
    after, before = set(), set()
    for trip_id, rows in data["stops"].items():
        if data["trips"].get(trip_id, {}).get("is_active") == "N":
            continue
        o, d = _find(rows, origin_q), _find(rows, dest_q)
        if o:
            after |= {r["stop_id"] for r in rows[o[0] + 1:] if not r["no_exit"]}
        if d:
            before |= {r["stop_id"] for r in rows[:d[-1]] if not r["no_entry"]}
    return sorted(after & before)[:8]


def find_night_trains(origin: str, destination: str, date: str | None = None) -> dict:
    try:
        data = _load()
    except (requests.RequestException, ValueError) as e:
        return {"error": f"night train data unavailable: {e}"}

    travel = None
    if date:
        try:
            travel = Date.fromisoformat(date)
        except ValueError:
            return {"error": "date must be YYYY-MM-DD"}

    oq, dq = _queries(origin), _queries(destination)
    results = []
    for trip_id, trip in data["trips"].items():
        if trip.get("is_active") == "N":
            continue
        rows = data["stops"].get(trip_id)
        if not rows:
            continue
        # a trip qualifies if origin comes before destination, and you can board/alight there
        for i in _find(rows, oq):
            hit = next(
                (j for j in _find(rows, dq) if j > i
                 and not rows[i]["no_entry"] and not rows[j]["no_exit"]),
                None,
            )
            if hit is None:
                continue
            offs = _day_offsets(rows)
            dep = rows[i]["departure_time"] or rows[i]["arrival_time"]
            arr = rows[hit]["arrival_time"] or rows[hit]["departure_time"]
            agency = data["agencies"].get(trip["agency_id"], {})
            item = {
                "train": trip["trip_short_name"] or trip_id,
                "operator": agency.get("agency_name") or trip["agency_id"],
                "from_station": rows[i]["stop_id"],
                "to_station": rows[hit]["stop_id"],
                "departs": _hhmm(dep),
                "arrives": _hhmm(arr),
                "arrives_days_later": offs[hit] - offs[i],
                "classes": trip.get("classes", ""),
                "runs": trip.get("service_id", ""),
                "notes": trip.get("irregularities", ""),
                **_links(data, trip),
            }
            if travel:
                # service pattern refers to the day the train leaves its first stop
                origin_day = travel - timedelta(days=offs[i])
                item["runs_on_date"] = _runs_on(trip.get("service_id", ""), origin_day)
            results.append(item)
            break

    if travel:   # runs first, then unclear, then trains that don't run on that date
        order = {True: 0, None: 1, False: 2}
        results.sort(key=lambda r: (order[r["runs_on_date"]], r["departs"]))
    else:
        results.sort(key=lambda r: r["departs"])

    out = {"attribution": ATTRIBUTION, "trains": results[:6],
           "more_booking_help": {"guide": BOOKING_GUIDE, "resellers_may_also_sell": RESELLERS}}
    if results:
        out["note"] = ("Schedule data only: no prices or availability. runs_on_date true/false is "
                       "a best-effort reading of 'runs'; null means unclear. Always confirm the "
                       "date on booking_url.")
        if travel and travel > Date(2026, 12, 12):
            out["note"] += " Date is after the 13 Dec 2026 timetable change; times may differ."
    else:
        out["note"] = "No direct night train found in the database for this pair."
        out["did_you_mean"] = {origin: _suggest(data, origin), destination: _suggest(data, destination)}
        out["possible_transfer_stations"] = _transfers(data, oq, dq)
        out["next_step"] = ("If a spelling suggestion looks right, retry with it. If transfer "
                            "stations are listed, call this tool twice: origin to a transfer, "
                            "then transfer to destination.")
    return out


# tool name -> function, used by planner.py
TOOL_HANDLERS = {"find_night_trains": find_night_trains}
