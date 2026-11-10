from datetime import datetime, timedelta
import json
import os
import requests

# API Keys (Set these under GitHub Repo -> Settings -> Secrets -> Actions)
TM_API_KEY = os.getenv("TM_API_KEY", "")
SEATGEEK_CLIENT_ID = os.getenv("SEATGEEK_CLIENT_ID", "")

# Strip & Downtown Geo Bounding Box
LAS_VEGAS_LAT = 36.1147
LAS_VEGAS_LNG = -115.1728

# Expanded Venue Registry
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
    return []

  now = datetime.utcnow()
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
  try:
    res = requests.get(url, timeout=10)
    data = res.json()
    items = data.get("_embedded", {}).get("events", [])
    for item in items:
      venues = item.get("_embedded", {}).get("venues", [])
      if not venues:
        continue

      venue_name = venues[0].get("name", "Unknown Venue")
      lat = float(venues[0].get("location", {}).get("latitude", LAS_VEGAS_LAT))
      lng = float(
          venues[0].get("location", {}).get("longitude", LAS_VEGAS_LNG)
      )
      name = item.get("name", "Special Event")

      profile = VENUE_PROFILES.get(
          venue_name,
          {
              "coords": [lat, lng],
              "radius": 500,
              "detour": "Reroute around local corridor",
          },
      )

      severity = "MODERATE"
      if any(
          k in name.upper()
          for k in ["GOLDEN KNIGHTS", "RAIDERS", "UFC", "BOXING", "CONCERT"]
      ):
        severity = "CRITICAL"
      elif "CHAMPIONSHIP" in name.upper() or "FESTIVAL" in name.upper():
        severity = "SEVERE"

      results.append({
          "id": f"tm-{item.get('id')}",
          "title": name,
          "venue": venue_name,
          "source": "Ticketmaster",
          "start_time": item.get("dates", {})
          .get("start", {})
          .get("dateTime", now.isoformat()),
          "severity": severity,
          "latitude": profile["coords"][0],
          "longitude": profile["coords"][1],
          "exclusion_radius": profile["radius"],
          "recommended_detour": profile["detour"],
      })
  except Exception as e:
    print(f"Ticketmaster error: {e}")
  return results


def fetch_seatgeek_events():
  """Queries SeatGeek to catch events at smaller Strip and Downtown venues."""
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
          "start_time": ev.get("datetime_utc", datetime.utcnow().isoformat()),
          "severity": "MODERATE",
          "latitude": lat,
          "longitude": lon,
          "exclusion_radius": 500,
          "recommended_detour": "Use outer bypass grid",
      })
  except Exception as e:
    print(f"SeatGeek error: {e}")
  return results


def fetch_ndot_road_closures():
  """Queries the Nevada 511 / NVroads live incident and roadwork feed."""
  # Nevada DOT public open incident endpoint
  url = "https://www.nvroads.com/data/geojson/incidents.geojson"
  closures = []

  try:
    res = requests.get(url, timeout=10)
    if res.status_code == 200:
      data = res.json()
      for f in data.get("features", []):
        props = f.get("properties", {})
        coords = f.get("geometry", {}).get("coordinates", [])

        # Filter strictly within the Strip / Downtown corridor bounding box
        # Latitude ~ 36.05 to 36.18, Longitude ~ -115.22 to -115.12
        if coords and len(coords) >= 2:
          lng, lat = coords[0], coords[1]
          if 36.05 <= lat <= 36.19 and -115.22 <= lng <= -115.12:
            desc = props.get("description", "Road Blockage / Construction")
            closures.append({
                "id": f"ndot-{props.get('id', lat)}",
                "title": f"🚧 Road Closure: {props.get('name', 'Active Work')}",
                "venue": desc[:45],
                "source": "Nevada DOT",
                "start_time": datetime.utcnow().isoformat(),
                "severity": "CRITICAL",
                "latitude": lat,
                "longitude": lng,
                "exclusion_radius": 350,
                "recommended_detour": "Avoid street segment; detour active",
            })
  except Exception as e:
    print(f"NVroads feed query failed or unavailable: {e}")

  return closures


def get_default_baseline():
  """Fallback simulated data if external APIs return empty."""
  now = datetime.utcnow()
  return [
      {
          "id": "base-01",
          "title": "Vegas Golden Knights vs. Edmonton",
          "venue": "T-Mobile Arena",
          "source": "Simulated Feed",
          "start_time": (now + timedelta(hours=3)).isoformat(),
          "severity": "CRITICAL",
          "latitude": 36.1028,
          "longitude": -115.1783,
          "exclusion_radius": 750,
          "recommended_detour": (
              "Reroute to Frank Sinatra Dr or Dean Martin Way"
          ),
      },
      {
          "id": "base-02",
          "title": "Las Vegas Grand Prix Strip Work",
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

  # Aggregate all open feeds
  tm_events = fetch_ticketmaster_events()
  sg_events = fetch_seatgeek_events()
  dot_closures = fetch_ndot_road_closures()

  combined.extend(tm_events)
  combined.extend(sg_events)
  combined.extend(dot_closures)

  # Fallback if no API keys are active
  if not combined:
    print("No external data returned; loading default Strip baseline.")
    combined = get_default_baseline()

  payload = {
      "metadata": {
          "generated_at": datetime.utcnow().isoformat() + "Z",
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
