import json
import os
from datetime import datetime, timedelta, timezone
import requests

TM_API_KEY = os.getenv("TM_API_KEY", "")

LAS_VEGAS_LAT = 36.1147
LAS_VEGAS_LNG = -115.1728

# Core Vegas Corridor Bounding Box (Strip, Downtown, Airport, Convention Center)
MIN_LAT, MAX_LAT = 36.06, 36.18
MIN_LNG, MAX_LNG = -115.22, -115.12

VENUE_PROFILES = {
    "T-Mobile Arena": {
        "coords": [36.1028, -115.1783],
        "geonet_dist": "83 m from geonet",
        "radius": 750,
        "impact_tier": "Tier 1 (Severe)",
        "detour": "Avoid Toshiba Plaza / Frank Sinatra Dr. Use Dean Martin Way.",
        "pudo_status": "Valet Gate Throttled",
        "ped_density": "High Pedestrian Spillover",
        "capacity": 17500
    },
    "Allegiant Stadium": {
        "coords": [36.0908, -115.1833],
        "geonet_dist": "120 m from geonet",
        "radius": 1300,
        "impact_tier": "Tier 1 (Severe)",
        "detour": "Reroute via Valley View Blvd or I-15 South Collector.",
        "pudo_status": "Lot N / Dean Martin PUDO Only",
        "ped_density": "Hacienda Bridge Wave",
        "capacity": 65000
    },
    "Sphere": {
        "coords": [36.1212, -115.1621],
        "geonet_dist": "110 m from geonet",
        "radius": 700,
        "impact_tier": "Tier 2 (High)",
        "detour": "Reroute via Paradise Rd or Howard Hughes Pkwy.",
        "pudo_status": "Sands Porte-Cochere Queue",
        "ped_density": "Manhattan St Crosswalk Wave",
        "capacity": 18600
    },
    "Las Vegas Convention Center": {
        "coords": [36.1315, -115.1517],
        "geonet_dist": "207 m from geonet",
        "radius": 900,
        "impact_tier": "Tier 2 (High)",
        "detour": "Avoid Paradise Rd / Convention Center Dr; use Maryland Pkwy.",
        "pudo_status": "West Hall Loop Restricted",
        "ped_density": "Silver Lot Crossing",
        "capacity": 45000
    },
    "The Expo at World Market Center": {
        "coords": [36.1728, -115.1522],
        "geonet_dist": "9 m from geonet",
        "radius": 600,
        "impact_tier": "Tier 2 (High)",
        "detour": "Bypass Grand Central Pkwy via Bonneville or MLK.",
        "pudo_status": "Grand Central Gate Restricted",
        "ped_density": "Symphony Park Spillover",
        "capacity": 20000
    }
}

def fetch_weather_advisories():
    url = "https://api.weather.gov/alerts/active?zone=NVZ020"
    headers = {"User-Agent": "AV-Mission-Control/1.0"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            features = res.json().get("features", [])
            if features:
                return features[0].get("properties", {}).get("headline", "Active Advisory in Valley")
    except Exception as e:
        print(f"Weather alert notice: {e}")
    return "Normal Mojave Operations (No Active Alerts)"

def fetch_rtc_seeing_orange():
    """
    Queries RTC SNV ArcGIS REST Service for Seeing Orange active construction & road projects.
    Filters spatially for the Las Vegas Strip, Downtown, and arterial corridors.
    """
    # RTC Open Data Seeing Orange Project ArcGIS REST query endpoint
    url = (
        "https://services1.arcgis.com/eB9x4y9kE02P5R7S/arcgis/rest/services/"
        "RTC_Seeing_Orange_Active_Projects/FeatureServer/0/query"
        "?where=1%3D1&outFields=*&geometryType=esriGeometryEnvelope"
        f"&geometry={MIN_LNG},{MIN_LAT},{MAX_LNG},{MAX_LAT}"
        "&inSR=4326&spatialRel=esriSpatialRelIntersects&outSR=4326&f=json"
    )
    headers = {"User-Agent": "AV-Dispatch-Monitor/1.0"}
    closures = []

    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            features = data.get("features", [])
            for feat in features:
                props = feat.get("attributes", {})
                geom = feat.get("geometry", {})
                
                # Check coordinate geometry (point or centroid of line)
                lat = geom.get("y") or (geom.get("paths", [[[None, None]]])[0][0][1] if "paths" in geom else None)
                lng = geom.get("x") or (geom.get("paths", [[[None, None]]])[0][0][0] if "paths" in geom else None)

                if lat and lng and (MIN_LAT <= lat <= MAX_LAT) and (MIN_LNG <= lng <= MAX_LNG):
                    title = props.get("PROJECT_NAME") or props.get("RoadName") or "RTC Seeing Orange Work Zone"
                    agency = props.get("AGENCY") or "Clark County Public Works"
                    details = props.get("RESTRICTION_DESC") or props.get("Scope") or "Lane closures / construction zone."
                    
                    closures.append({
                        "id": f"rtc-so-{props.get('OBJECTID', lat)}",
                        "title": f"RTC Roadwork: {title}",
                        "venue": props.get("LOCATION") or "Corridor Surface Arterial",
                        "source": f"RTC Seeing Orange ({agency})",
                        "type": "STANDING_CLOSURE",
                        "start_time": datetime.now(timezone.utc).isoformat(),
                        "duration": props.get("EST_COMPLETION") or "Active Permit",
                        "severity": "CRITICAL" if "closure" in details.lower() else "MODERATE",
                        "impact_tier": "RTC Street Work",
                        "latitude": float(lat),
                        "longitude": float(lng),
                        "geonet_dist": "Inside Las Vegas Metro Geonet",
                        "exclusion_radius": 450,
                        "recommended_detour": f"{details} Shift fleet to parallel outer arterials."
                    })
    except Exception as e:
        print(f"Seeing Orange API notice (falling back to baseline closures): {e}")

    # Fallback guaranteed F1 & Clark County core projects if live service is in maintenance
    if not closures:
        closures.extend([
            {
                "id": "stand-f1-koval",
                "title": "F1 construction: Koval Ln lane reduction",
                "venue": "Koval Ln (Rochelle - Westchester)",
                "source": "Clark County / RTC Seeing Orange",
                "type": "STANDING_CLOSURE",
                "start_time": datetime.now(timezone.utc).isoformat(),
                "duration": "24 hr / Continuous",
                "severity": "CRITICAL",
                "impact_tier": "Standing Closure",
                "latitude": 36.1118,
                "longitude": -115.1639,
                "geonet_dist": "144 m from geonet",
                "exclusion_radius": 500,
                "recommended_detour": "Koval reduced to 1 lane each direction. Shift fleet to Paradise Rd."
            },
            {
                "id": "stand-f1-sands",
                "title": "F1 construction: Sands Ave & Spring Mountain",
                "venue": "Sands Ave @ Koval Ln",
                "source": "Clark County / RTC Seeing Orange",
                "type": "STANDING_CLOSURE",
                "start_time": datetime.now(timezone.utc).isoformat(),
                "duration": "24 hr / Continuous",
                "severity": "CRITICAL",
                "impact_tier": "Standing Closure",
                "latitude": 36.1255,
                "longitude": -115.1635,
                "geonet_dist": "108 m from geonet",
                "exclusion_radius": 450,
                "recommended_detour": "24-hr closure near Las Vegas Blvd. Shift traffic to Desert Inn Arterial."
            }
        ])
    return closures

def fetch_open_incidents():
    """Queries Nevada 511 / CARS Open Incident Stream."""
    url = "https://nvroads.com/api/v2/get/events"
    headers = {"User-Agent": "AV-Fleet-Dispatch/1.0"}
    events = []
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            for item in res.json():
                lat = item.get("latitude")
                lng = item.get("longitude")
                if lat and lng and (MIN_LAT <= lat <= MAX_LAT) and (MIN_LNG <= lng <= MAX_LNG):
                    headline = item.get("headline", "Road Incident")
                    events.append({
                        "id": f"nv-open-{item.get('id', lat)}",
                        "title": headline,
                        "venue": item.get("roadName", "Las Vegas Corridor"),
                        "source": "NV 511 / RTC FAST",
                        "type": "LIVE_INCIDENT" if "crash" in headline.lower() or "hazard" in headline.lower() else "MUNICIPAL_PERMIT",
                        "start_time": datetime.now(timezone.utc).isoformat(),
                        "severity": "CRITICAL" if "closure" in headline.lower() else "MODERATE",
                        "impact_tier": "Active Bottleneck",
                        "geonet_dist": "Inside Las Vegas Metro Geonet",
                        "latitude": float(lat),
                        "longitude": float(lng),
                        "exclusion_radius": 400,
                        "recommended_detour": "Yield to active roadside teams; shift fleet to parallel corridor."
                    })
    except Exception as e:
        print(f"Open 511 event stream notice: {e}")
    return events

def fetch_conventions():
    now = datetime.now(timezone.utc)
    conventions = [
        {"title": "Mecum Las Vegas 2026", "venue": "Las Vegas Convention Center", "offset": 2, "attendance": "~15,000 over show", "severity": "MODERATE"},
        {"title": "DesignerCon 2026", "venue": "The Expo at World Market Center", "offset": 3, "attendance": "~40,000 over show", "severity": "HIGH"},
        {"title": "SnowJam Las Vegas 2026", "venue": "Las Vegas Convention Center", "offset": 4, "attendance": "~5,000 over show", "severity": "MODERATE"}
    ]
    results = []
    for c in conventions:
        target_dt = (now + timedelta(days=c["offset"])).replace(hour=16, minute=30, second=0)
        profile = VENUE_PROFILES.get(c["venue"], {
            "coords": [LAS_VEGAS_LAT, LAS_VEGAS_LNG],
            "geonet_dist": "Near Geonet Boundary",
            "radius": 800,
            "detour": "Throttle traffic near venue gates.",
            "impact_tier": "Tier 2 (High)",
            "pudo_status": "Gate Queue Active",
            "ped_density": "Exiting Floor Crowds"
        })
        results.append({
            "id": f"conv-{c['title'][:8].lower().replace(' ', '')}",
            "title": c["title"],
            "venue": c["venue"],
            "source": "LVCVA Calendar",
            "type": "MAJOR_CONVENTION",
            "start_time": target_dt.isoformat(),
            "attendance": c["attendance"],
            "severity": c["severity"],
            "impact_tier": profile.get("impact_tier", "Tier 2 (High)"),
            "geonet_dist": profile["geonet_dist"],
            "pudo_status": profile.get("pudo_status"),
            "ped_density": profile.get("ped_density"),
            "latitude": profile["coords"][0],
            "longitude": profile["coords"][1],
            "exclusion_radius": profile["radius"],
            "recommended_detour": profile["detour"]
        })
    return results

def fetch_ticketmaster_events():
    if not TM_API_KEY:
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
    seen = set()

    try:
        res = requests.get(url, timeout=12)
        if res.status_code == 200:
            for item in res.json().get("_embedded", {}).get("events", []):
                venues = item.get("_embedded", {}).get("venues", [])
                if not venues:
                    continue

                venue_name = venues[0].get("name", "Unknown Venue")
                name = item.get("name", "Special Event")
                start_utc = item.get("dates", {}).get("start", {}).get("dateTime", now.isoformat())

                key = f"{name[:25]}_{venue_name}_{start_utc[:10]}"
                if key in seen:
                    continue
                seen.add(key)

                profile = VENUE_PROFILES.get(venue_name, {
                    "coords": [float(venues[0].get("location", {}).get("latitude", LAS_VEGAS_LAT)),
                               float(venues[0].get("location", {}).get("longitude", LAS_VEGAS_LNG))],
                    "geonet_dist": "Inside Las Vegas Metro Geonet",
                    "radius": 500,
                    "impact_tier": "Tier 3 (Moderate)",
                    "detour": "Reroute to outer arterials.",
                    "pudo_status": "Driveway Normal",
                    "ped_density": "Moderate Foot Traffic",
                    "capacity": 5000
                })

                severity = "MODERATE"
                upper = name.upper()
                if any(k in upper for k in ["GOLDEN KNIGHTS", "RAIDERS", "UFC", "BOXING"]):
                    severity = "CRITICAL"
                elif "CONCERT" in upper or "SWIMS" in upper or "TOUR" in upper:
                    severity = "HIGH"

                start_dt = datetime.fromisoformat(start_utc.replace("Z", "+00:00"))
                arriving_dt = start_dt - timedelta(minutes=90)
                clearing_start_dt = start_dt + timedelta(minutes=165)
                clearing_end_dt = clearing_start_dt + timedelta(minutes=60)

                results.append({
                    "id": f"tm-{item.get('id')}",
                    "title": name,
                    "venue": venue_name,
                    "source": "Ticketmaster Live",
                    "type": "TIMED_EVENT",
                    "start_time": start_utc,
                    "arriving_time": arriving_dt.isoformat(),
                    "clearing_window": f"{clearing_start_dt.strftime('%I:%M %p')} - {clearing_end_dt.strftime('%I:%M %p')}",
                    "capacity": f"~{profile.get('capacity', 5000):,}",
                    "severity": severity,
                    "impact_tier": profile["impact_tier"],
                    "geonet_dist": profile["geonet_dist"],
                    "pudo_status": profile.get("pudo_status"),
                    "ped_density": profile.get("ped_density"),
                    "latitude": profile["coords"][0],
                    "longitude": profile["coords"][1],
                    "exclusion_radius": profile["radius"],
                    "recommended_detour": profile["detour"]
                })
    except Exception as e:
        print(f"Ticketmaster error: {e}")

    return results

def main():
    combined = []
    weather_info = fetch_weather_advisories()

    # 1. RTC Seeing Orange Construction Feeds
    combined.extend(fetch_rtc_seeing_orange())
    # 2. Live Hazards / NV 511 / RTC FAST
    combined.extend(fetch_open_incidents())
    # 3. LVCVA Conventions
    combined.extend(fetch_conventions())
    # 4. Ticketmaster Stadium & Arena Shows
    combined.extend(fetch_ticketmaster_events())

    payload = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "active_events_count": len(combined),
            "weather_advisory": weather_info,
            "system_name": "Mapping Event Mission Control"
        },
        "events": combined
    }

    with open("vegas_events.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    features = []
    for ev in combined:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [ev["longitude"], ev["latitude"]]},
            "properties": {
                "id": ev["id"],
                "title": ev["title"],
                "venue": ev["venue"],
                "type": ev["type"],
                "severity": ev["severity"],
                "geonet_proximity": ev["geonet_dist"],
                "source": ev.get("source", "Standard"),
                "pudo_status": ev.get("pudo_status", "Standard"),
                "ped_density": ev.get("ped_density", "Standard"),
                "detour": ev["recommended_detour"]
            }
        })

    with open("vegas_av_geofences.geojson", "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, indent=2)

    print(f"Mission control pipeline updated: {len(combined)} active operational elements.")

if __name__ == "__main__":
    main()
