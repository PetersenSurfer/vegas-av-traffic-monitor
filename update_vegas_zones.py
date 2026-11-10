import json
import os
from datetime import datetime, timedelta, timezone
import requests

# API Keys (Set under GitHub Repo -> Settings -> Secrets and variables -> Actions)
TM_API_KEY = os.getenv("TM_API_KEY", "")
SEATGEEK_CLIENT_ID = os.getenv("SEATGEEK_CLIENT_ID", "")

# Strip & Downtown Geo Bounding Box
LAS_VEGAS_LAT = 36.1147
LAS_VEGAS_LNG = -115.1728

VENUE_PROFILES = {
    "T-Mobile Arena": {
        "coords": [36.1028, -115.1783],
        "radius": 750,
        "detour": "Reroute to Frank Sinatra Dr or Dean Martin Way",
    },
    "Allegiant Stadium": {
        "coords": [36.0908, -115.1833],
        "radius": 1300,
        "detour": "Reroute to Valley View Blvd or I-15 South Collector",
    },
    "Sphere": {
        "coords": [36.1212, -115.1621],
        "radius": 700,
        "detour": "Reroute to Paradise Rd or Howard Hughes Pkwy",
    },
    "MGM Grand Garden Arena": {
        "coords": [36.1017, -115.1678],
        "radius": 600,
        "detour": "Bypass Tropicana Ave via Koval Ln",
    },
    "Michelob ULTRA Arena": {
        "coords": [36.0925, -115.1755],
        "radius": 600,
        "detour": "Bypass via Frank Sinatra Dr",
    },
    "Las Vegas Convention Center": {
        "coords": [36.1315, -115.1517],
        "radius": 900,
        "detour": "Avoid Paradise Rd / Desert Inn; use Maryland Pkwy",
    },
    "Fremont Street Experience": {
        "coords": [36.1699, -115.1438],
        "radius": 600,
        "detour": "Reroute to E Charleston Blvd or E Bonanza Rd",
    },
    "Las Vegas Festival Grounds": {
        "coords": [36.1415, -115.1610],
        "radius": 850,
        "detour": "Reroute to Industrial Rd or Rancho Dr",
    },
}

GREEN_CORRIDORS = [
    {
        "name": "West Strip Bypass (Frank Sinatra Dr)",
        "coordinates": [
            [-115.1798, 36.0945],
            [-115.1792, 36.1150],
            [-115.1805, 36.1250],
        ],
    },
    {
        "name": "East Strip Arterial (Paradise Rd)",
        "coordinates": [
            [-115.1541, 36.0910],
            [-115.1543, 36.1310],
            [-115.1545, 36.1510],
        ],
    },
]


def fetch_ticketmaster_events():
    """Queries Ticketmaster for high-capacity arena concerts and games."""
    if not TM_API_KEY:
        print("TM_API_KEY not found in environment secrets.")
        return []

    now = datetime.now(timezone.utc)
    end_time = now + timedelta(days=7)
    url = (
        f"https://app.ticketmaster.com/discovery/v2/events.json"
        f"?apikey={TM_API_KEY}"
        f"&latlong={LAS_VEGAS_LAT},{LAS_VEGAS_LNG}&radius=10&unit=miles"
        f"&startDateTime={now.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        f"&endDateTime={end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        f"&size=100"
    )

    results = []
    seen_keys = set()

    try:
        res = requests.get(url, timeout=12)
        if res.status_code != 200:
            print(f"Ticketmaster returned HTTP {res.status_code}")
            return []

        data = res.json()
        items = data.get("_embedded", {}).get("events", [])
        
        for item in items:
            venues = item.get("_embedded", {}).get("venues", [])
            if not venues:
                continue

            venue_name = venues[0].get("name", "Unknown Venue")
            lat = float(venues[0].get("location", {}).get("latitude", LAS_VEGAS_LAT))
            lng = float(venues[0].get("location", {}).get("longitude", LAS_VEGAS_LNG))
            name = item.get("name", "Special Event")
            start_utc = item.get("dates", {}).get("start", {}).get("dateTime", now.isoformat())

            # Skip duplicate suite/ticket tiers for the same main performance
            dedup_key = f"{name[:25]}_{venue_name}_{start_utc[:10]}"
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            profile = VENUE_PROFILES.get(
                venue_name,
                {
                    "coords": [lat, lng],
                    "radius": 500,
                    "detour": "Reroute around local corridor",
                },
            )

            severity = "MODERATE"
            upper_name = name.upper()
            if any(k in upper_name for k in ["GOLDEN KNIGHTS", "RAIDERS", "UFC", "BOXING", "CONCERT"]):
                severity = "CRITICAL"
            elif "CHAMPIONSHIP" in upper_name or "FESTIVAL" in upper_name:
                severity = "SEVERE"

            results.append({
                "id": f"tm-{item.get('id')}",
                "title": name,
                "venue": venue_name,
                "source": "Ticketmaster",
                "start_time": start_utc,
                "severity": severity,
                "latitude": profile["coords"][0],
                "longitude": profile["coords"][1],
                "exclusion_radius": profile["radius"],
                "recommended_detour": profile["detour"],
            })
    except Exception as e:
        print(f"Ticketmaster fetch error: {e}")

    return results


def fetch_seatgeek_events():
    """Queries SeatGeek for shows at additional venues."""
    if not SEATGEEK_CLIENT_ID:
        return []

    url = (
        f"https://api.seatgeek.com/2/events"
        f"?client_id={SEATGEEK_CLIENT_ID}"
        f"&lat={LAS_VEGAS_LAT}&lon={LAS_VEGAS_LNG}&range=8mi"
        f"&per_page=50"
    )

    results = []
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            data = res.json()
            for ev in data.get("events", []):
                v = ev.get("venue", {})
                venue_name = v.get("name", "Vegas Venue")
                lat = v.get("location", {}).get("lat", LAS_VEGAS_LAT)
                lon = v.get("location", {}).get("lon", LAS_VEGAS_LNG)
                title = ev.get("short_title") or ev.get("title")

                results.append({
                    "id": f"sg-{ev.get('id')}",
                    "title": title,
                    "venue": venue_name,
                    "source": "SeatGeek",
                    "start_time": ev.get("datetime_utc", datetime.now(timezone.utc).isoformat()),
                    "severity": "MODERATE",
                    "latitude": lat,
                    "longitude": lon,
                    "exclusion_radius": 500,
                    "recommended_detour": "Use outer bypass grid",
                })
    except Exception as e:
        print(f"SeatGeek fetch error: {e}")

    return results


def fetch_ndot_road_closures():
    """Queries Nevada 511 for active road closures in the Las Vegas Valley."""
    url = "https://www.nvroads.com/data/geojson/incidents.geojson"
    headers = {"User-Agent": "AV-Fleet-Traffic-Monitor/1.0"}
    closures = []

    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            for f in data.get("features", []):
                props = f.get("properties", {})
                coords = f.get("geometry", {}).get("coordinates", [])

                if coords and len(coords) >= 2:
                    lng, lat = coords[0], coords[1]
                    # Bounding box for Las Vegas Valley (Strip, Downtown, I-15)
                    if 36.00 <= lat <= 36.25 and -115.30 <= lng <= -115.10:
                        desc = props.get("description") or props.get("message") or "Road Closure / Incident"
                        name = props.get("name") or props.get("road") or "Transit Corridor"
                        closures.append({
                            "id": f"ndot-{props.get('id', lat)}",
                            "title": f"Road Closure: {name}",
                            "venue": desc[:50],
                            "source": "Nevada 511",
                            "start_time": datetime.now(timezone.utc).isoformat(),
                            "severity": "CRITICAL",
                            "latitude": lat,
                            "longitude": lng,
                            "exclusion_radius": 350,
                            "recommended_detour": "Avoid street segment; shift to green corridor",
                        })
    except Exception as e:
        print(f"Nevada 511 query notice (skipped): {e}")

    return closures


def get_default_baseline():
    """Fallback simulated data if external feeds return empty."""
    now = datetime.now(timezone.utc)
    return [
        {
            "id": "base-01",
            "title": "Vegas Golden Knights vs. Rivals",
            "venue": "T-Mobile Arena",
            "source": "Simulated Feed",
            "start_time": (now + timedelta(hours=3)).isoformat(),
            "severity": "CRITICAL",
            "latitude": 36.1028,
            "longitude": -115.1783,
            "exclusion_radius": 750,
            "recommended_detour": "Reroute to Frank Sinatra Dr or Dean Martin Way",
        },
        {
            "id": "base-02",
            "title": "Las Vegas Strip Maintenance Work",
            "venue": "Koval Ln / Harmon Ave",
            "source": "Clark County Permits",
            "start_time": now.isoformat(),
            "severity": "CRITICAL",
            "latitude": 36.1085,
            "longitude": -115.1638,
            "exclusion_radius": 450,
            "recommended_detour": "Detour via Paradise Rd",
        },
        {
            "id": "base-03",
            "title": "Sphere Immersive Production",
            "venue": "Sphere",
            "source": "Simulated Feed",
            "start_time": (now + timedelta(hours=5)).isoformat(),
            "severity": "MODERATE",
            "latitude": 36.1212,
            "longitude": -115.1621,
            "exclusion_radius": 700,
            "recommended_detour": "Reroute to Paradise Rd",
        },
        {
            "id": "base-04",
            "title": "Downtown Fremont Music Series",
            "venue": "Fremont Street Experience",
            "source": "City of LV Permits",
            "start_time": (now + timedelta(hours=6)).isoformat(),
            "severity": "SEVERE",
            "latitude": 36.1699,
            "longitude": -115.1438,
            "exclusion_radius": 600,
            "recommended_detour": "Reroute to E Charleston Blvd",
        },
    ]


def export_fleet_geojson(events):
    features = []
    for ev in events:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [ev["longitude"], ev["latitude"]],
            },
            "properties": {
                "id": ev["id"],
                "title": ev["title"],
                "venue": ev["venue"],
                "source": ev.get("source", "Unknown"),
                "severity": ev["severity"],
                "buffer_radius_m": ev["exclusion_radius"],
                "detour_instructions": ev["recommended_detour"],
            },
        })

    for c in GREEN_CORRIDORS:
        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": c["coordinates"]},
            "properties": {
                "name": c["name"],
                "type": "av_green_corridor",
                "speed_limit_mph": 35,
            },
        })

    return {"type": "FeatureCollection", "features": features}


def main():
    combined = []

    tm_events = fetch_ticketmaster_events()
    sg_events = fetch_seatgeek_events()
    dot_closures = fetch_ndot_road_closures()

    combined.extend(tm_events)
    combined.extend(sg_events)
    combined.extend(dot_closures)

    if not combined:
        print("No live API data returned; falling back to default baseline.")
        combined = get_default_baseline()

    payload = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "active_events_count": len(combined),
            "region": "Las Vegas Strip Corridor",
        },
        "events": combined,
    }

    with open("vegas_events.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    with open("vegas_av_geofences.geojson", "w", encoding="utf-8") as f:
        json.dump(export_fleet_geojson(combined), f, indent=2)

    print(f"Feed updated: aggregated {len(combined)} active traffic obstacles.")


if __name__ == "__main__":
    main()
