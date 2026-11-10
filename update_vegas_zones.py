import json
import os
from datetime import datetime, timedelta
import requests

TM_API_KEY = os.getenv("TM_API_KEY", "")

VENUE_PROFILES = {
    "T-Mobile Arena": {
        "coords": [36.1028, -115.1783],
        "radius_meters": 750,
        "detour": "Reroute to Frank Sinatra Dr or Dean Martin Way"
    },
    "Allegiant Stadium": {
        "coords": [36.0908, -115.1833],
        "radius_meters": 1300,
        "detour": "Reroute to Valley View Blvd or I-15 South Collector"
    },
    "Sphere": {
        "coords": [36.1212, -115.1621],
        "radius_meters": 700,
        "detour": "Reroute to Paradise Rd or Howard Hughes Pkwy"
    },
    "Fremont Street Experience": {
        "coords": [36.1699, -115.1438],
        "radius_meters": 600,
        "detour": "Reroute to E Charleston Blvd or E Bonanza Rd"
    },
    "Las Vegas Festival Grounds": {
        "coords": [36.1415, -115.1610],
        "radius_meters": 850,
        "detour": "Reroute to Industrial Rd or Rancho Dr"
    }
}

GREEN_CORRIDORS = [
    {
        "name": "West Strip Bypass (Frank Sinatra Dr)",
        "coordinates": [
            [-115.1798, 36.0945],
            [-115.1792, 36.1150],
            [-115.1805, 36.1250]
        ]
    },
    {
        "name": "East Strip Arterial (Paradise Rd)",
        "coordinates": [
            [-115.1541, 36.0910],
            [-115.1543, 36.1310],
            [-115.1545, 36.1510]
        ]
    }
]

def fetch_ticketmaster_events():
    if not TM_API_KEY:
        print("TM_API_KEY not set. Using baseline simulated events.")
        return get_fallback_events()

    now = datetime.utcnow()
    end_time = now + timedelta(days=7)
    url = (
        f"https://app.ticketmaster.com/discovery/v2/events.json"
        f"?apikey={TM_API_KEY}"
        f"&latlong=36.1147,-115.1728&radius=10&unit=miles"
        f"&startDateTime={now.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        f"&endDateTime={end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}"
        f"&size=100"
    )

    try:
        res = requests.get(url, timeout=12)
        res.raise_for_status()
        data = res.json()
        items = data.get("_embedded", {}).get("events", [])
        events = []

        for item in items:
            venues = item.get("_embedded", {}).get("venues", [])
            if not venues:
                continue

            venue_name = venues[0].get("name", "Unknown Venue")
            lat = float(venues[0].get("location", {}).get("latitude", 36.1147))
            lng = float(venues[0].get("location", {}).get("longitude", -115.1728))
            name = item.get("name", "Special Event")
            start_utc = item.get("dates", {}).get("start", {}).get("dateTime")

            profile = VENUE_PROFILES.get(venue_name, {
                "coords": [lat, lng],
                "radius_meters": 500,
                "detour": "Reroute around perimeter street grid"
            })

            severity = "MODERATE"
            if any(k in name.upper() for k in ["GOLDEN KNIGHTS", "RAIDERS", "UFC", "BOXING", "CONCERT"]):
                severity = "CRITICAL"
            elif "CHAMPIONSHIP" in name.upper() or "FESTIVAL" in name.upper():
                severity = "SEVERE"

            events.append({
                "id": item.get("id"),
                "title": name,
                "venue": venue_name,
                "start_time": start_utc or now.isoformat(),
                "severity": severity,
                "latitude": profile["coords"][0],
                "longitude": profile["coords"][1],
                "exclusion_radius": profile["radius_meters"],
                "recommended_detour": profile["detour"]
            })
        return events if events else get_fallback_events()
    except Exception as err:
        print(f"Fetch failed: {err}. Using fallback baseline.")
        return get_fallback_events()

def get_fallback_events():
    now = datetime.utcnow()
    return [
        {
            "id": "sim-vgk-01",
            "title": "Vegas Golden Knights Match",
            "venue": "T-Mobile Arena",
            "start_time": (now + timedelta(hours=3)).isoformat(),
            "severity": "CRITICAL",
            "latitude": 36.1028,
            "longitude": -115.1783,
            "exclusion_radius": 750,
            "recommended_detour": "Reroute to Frank Sinatra Dr or Dean Martin Way"
        },
        {
            "id": "sim-sphere-02",
            "title": "Sphere Live Production",
            "venue": "Sphere",
            "start_time": (now + timedelta(hours=5)).isoformat(),
            "severity": "MODERATE",
            "latitude": 36.1212,
            "longitude": -115.1621,
            "exclusion_radius": 700,
            "recommended_detour": "Reroute to Paradise Rd"
        },
        {
            "id": "sim-dtlv-03",
            "title": "Downtown Fremont Block Gathering",
            "venue": "Fremont Street Experience",
            "start_time": (now + timedelta(hours=6)).isoformat(),
            "severity": "SEVERE",
            "latitude": 36.1699,
            "longitude": -115.1438,
            "exclusion_radius": 600,
            "recommended_detour": "Reroute to E Charleston Blvd"
        }
    ]

def export_fleet_geojson(events):
    features = []
    for ev in events:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [ev["longitude"], ev["latitude"]]
            },
            "properties": {
                "id": ev["id"],
                "title": ev["title"],
                "venue": ev["venue"],
                "type": "exclusion_zone",
                "severity": ev["severity"],
                "buffer_radius_m": ev["exclusion_radius"],
                "detour_instructions": ev["recommended_detour"]
            }
        })

    for corridor in GREEN_CORRIDORS:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": corridor["coordinates"]
            },
            "properties": {
                "name": corridor["name"],
                "type": "av_green_corridor",
                "speed_limit_mph": 35
            }
        })

    return {"type": "FeatureCollection", "features": features}

if __name__ == "__main__":
    events = fetch_ticketmaster_events()
    payload = {
        "metadata": {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "active_events_count": len(events),
            "region": "Las Vegas Strip & Clark County"
        },
        "events": events
    }

    with open("vegas_events.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    with open("vegas_av_geofences.geojson", "w", encoding="utf-8") as f:
        json.dump(export_fleet_geojson(events), f, indent=2)

    print(f"Export complete: {len(events)} exclusion zones processed.")
