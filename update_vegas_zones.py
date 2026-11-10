import json
import os
import sys
from datetime import datetime, timedelta, timezone
import requests

TM_API_KEY = os.getenv("TM_API_KEY", "")

# Center of the 15-mile Valley Operating Domain
LAS_VEGAS_LAT = 36.1200
LAS_VEGAS_LNG = -115.1700

# Full Valley Bounding Box matching Seeing Orange & Metro Domain
MIN_LAT, MAX_LAT = 35.95, 36.35
MIN_LNG, MAX_LNG = -115.38, -114.95

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*"
}

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
    },
    "Town Square Las Vegas": {
        "coords": [36.0675, -115.1785],
        "geonet_dist": "South Strip Geonet (I-15 / 215 Junction)",
        "radius": 600,
        "impact_tier": "Tier 3 (Moderate)",
        "detour": "Avoid main driveway off Las Vegas Blvd. Ingress via Sunset Rd or George Croft Pkwy.",
        "pudo_status": "Use Outer AMC / Whole Foods PUDO Lanes",
        "ped_density": "Town Square Green Park Foot Traffic",
        "capacity": 8000
    }
}

def fetch_weather_advisories():
    url = "https://api.weather.gov/alerts/active?zone=NVZ020"
    try:
        res = requests.get(url, headers={"User-Agent": "AV-Mission-Control/1.0"}, timeout=6)
        if res.status_code == 200:
            features = res.json().get("features", [])
            if features:
                return features[0].get("properties", {}).get("headline", "Active Advisory in Valley")
    except Exception as e:
        print(f"Weather alert notice: {e}")
    return "Normal Mojave Operations (No Active Alerts)"

def get_f1_strip_standing():
    """F1 Circuit and immediate Strip track restrictions."""
    now = datetime.now(timezone.utc)
    return [
        {
            "id": "f1-koval-lane",
            "title": "F1 Track: Koval Ln Barrier & Reduction",
            "venue": "Koval Ln (Flamingo to Harmon)",
            "source": "Clark County / F1 Permitting",
            "type": "F1_CLOSURE",
            "start_time": now.isoformat(),
            "duration": "24-Hr Circuit Work",
            "severity": "CRITICAL",
            "impact_tier": "F1 Circuit",
            "latitude": 36.1118,
            "longitude": -115.1639,
            "geonet_dist": "Inside Las Vegas Metro Geonet",
            "exclusion_radius": 500,
            "recommended_detour": "Koval restricted to 1 lane. Shift AV fleet to Paradise Rd."
        },
        {
            "id": "f1-sands-springmtn",
            "title": "F1 Track: Sands Ave & Koval Intersection",
            "venue": "Sands Ave @ Koval Ln",
            "source": "Clark County / F1 Permitting",
            "type": "F1_CLOSURE",
            "start_time": now.isoformat(),
            "duration": "24-Hr Circuit Work",
            "severity": "CRITICAL",
            "impact_tier": "F1 Circuit",
            "latitude": 36.1255,
            "longitude": -115.1635,
            "geonet_dist": "Inside Las Vegas Metro Geonet",
            "exclusion_radius": 450,
            "recommended_detour": "Severe turn throttling. Divert north fleet to Desert Inn Arterial."
        },
        {
            "id": "f1-harmon-strip",
            "title": "F1 Track: Harmon Ave Paddock Access",
            "venue": "East Harmon Ave @ Audrie St",
            "source": "Clark County / F1 Permitting",
            "type": "F1_CLOSURE",
            "start_time": now.isoformat(),
            "duration": "24-Hr Circuit Work",
            "severity": "CRITICAL",
            "impact_tier": "F1 Circuit",
            "latitude": 36.1082,
            "longitude": -115.1655,
            "geonet_dist": "Inside Las Vegas Metro Geonet",
            "exclusion_radius": 450,
            "recommended_detour": "Paddock logistics active. Use Tropicana Ave for cross-valley travel."
        }
    ]

def fetch_seeing_orange_regional():
    """
    Ingests Seeing Orange capital projects, multi-corridor road work,
    and active work zones across the entire Las Vegas Valley.
    """
    regional_work = []
    seen = set()

    # 1. Ingest active roadwork and construction events from the open Nevada transportation feed
    try:
        url = "https://nvroads.com/api/v2/get/events"
        res = requests.get(url, headers=BROWSER_HEADERS, timeout=8)
        if res.status_code == 200:
            for item in res.json():
                lat = item.get("latitude")
                lng = item.get("longitude")
                headline = str(item.get("headline", "")).lower()
                event_type = str(item.get("type", "")).lower()

                if any(k in headline or k in event_type for k in ["construction", "work zone", "roadwork", "repaving", "maintenance", "lane closure"]):
                    if lat is not None and lng is not None and (MIN_LAT <= float(lat) <= MAX_LAT) and (MIN_LNG <= float(lng) <= MAX_LNG):
                        oid = f"nv-work-{item.get('id', lat)}"
                        if oid in seen:
                            continue
                        seen.add(oid)

                        regional_work.append({
                            "id": oid,
                            "title": item.get("headline", "Active Roadwork"),
                            "venue": str(item.get("roadName", "Valley Arterial")),
                            "source": "Seeing Orange (NV DOT / RTC FAST)",
                            "type": "RTC_SEEING_ORANGE",
                            "start_time": datetime.now(timezone.utc).isoformat(),
                            "duration": "Active Work Zone",
                            "severity": "MODERATE",
                            "impact_tier": "Active Roadwork",
                            "latitude": float(lat),
                            "longitude": float(lng),
                            "geonet_dist": "Valley Wide Regional Domain",
                            "exclusion_radius": 400,
                            "recommended_detour": "Active work zone. Reduce speed and watch for flaggers."
                        })
    except Exception as e:
        print(f"Live construction feed notice: {e}")

    # 2. Add RTC's Major Seeing Orange Capital Projects across the full valley
    active_rtc_corridors = [
        {
            "id": "so-i15-trop",
            "title": "I-15 / Tropicana Interchange Project",
            "venue": "I-15 at Tropicana Ave",
            "agency": "NDOT",
            "details": "Major bridge replacement and interchange reconfiguration.",
            "duration": "Multi-Year Phase",
            "lat": 36.1010, "lng": -115.1840
        },
        {
            "id": "so-henderson-215",
            "title": "Henderson 215 Widening & Green Valley DDI",
            "venue": "I-215 (Pecos Rd to Stephanie St)",
            "agency": "City of Henderson / RTC",
            "details": "Widening 215 by two lanes each direction and constructing Diverging Diamond Interchange.",
            "duration": "Active Construction",
            "lat": 36.0275, "lng": -115.0880
        },
        {
            "id": "so-summerlin-215",
            "title": "CC-215 Beltway & Summerlin Pkwy Interchange",
            "venue": "CC-215 at Summerlin Parkway",
            "agency": "Clark County Public Works",
            "details": "Ramp reconfigurations, new flyovers, and bridge widening.",
            "duration": "Active Construction",
            "lat": 36.1890, "lng": -115.2970
        },
        {
            "id": "so-maryland-brt",
            "title": "Maryland Parkway BRT Line",
            "venue": "Maryland Pkwy (Russell Rd to Downtown)",
            "agency": "RTC Southern Nevada",
            "details": "Utility relocation, dedicated transit lanes, and roadway reconstruction.",
            "duration": "Through Fall 2026",
            "lat": 36.1360, "lng": -115.1365
        },
        {
            "id": "so-lvblvd-south",
            "title": "Las Vegas Blvd Improvement (Phases C & D)",
            "venue": "Las Vegas Blvd (Russell Rd to Tropicana Ave)",
            "agency": "Clark County",
            "details": "Roadway resurfacing, smart traffic signals, bollards, and pedestrian lighting.",
            "duration": "Active Strip Work",
            "lat": 36.0960, "lng": -115.1725
        },
        {
            "id": "so-boulder-hwy",
            "title": "Reimagine Boulder Highway Transformation",
            "venue": "Boulder Highway (Tropicana to Wagonwheel)",
            "agency": "RTC / City of Henderson",
            "details": "Complete streets overhaul, center transit running, and access management.",
            "duration": "Multi-Phase Capital",
            "lat": 36.0820, "lng": -115.0450
        },
        {
            "id": "so-lake-mead-blvd",
            "title": "Lake Mead Blvd Complete Streets Project",
            "venue": "Lake Mead Blvd (Simmons St to Losee Rd)",
            "agency": "City of North Las Vegas",
            "details": "Pavement rehabilitation, new medians, ADA ramps, and bike lanes.",
            "duration": "Active Construction",
            "lat": 36.1965, "lng": -115.1480
        },
        {
            "id": "so-cc215-south-widening",
            "title": "CC-215 Southwest Beltway Widening",
            "venue": "CC-215 (Decatur Blvd to Jones Blvd)",
            "agency": "Clark County",
            "details": "Lane additions, auxiliary lanes, and sound wall construction.",
            "duration": "Active Widening",
            "lat": 36.0680, "lng": -115.2100
        },
        {
            "id": "so-charleston-west",
            "title": "West Charleston Blvd Utility Rehab",
            "venue": "Charleston Blvd (Rancho Dr to Martin L King)",
            "agency": "City of Las Vegas",
            "details": "Storm drain installation and arterial resurfacing.",
            "duration": "Through Summer 2026",
            "lat": 36.1585, "lng": -115.1630
        },
        {
            "id": "so-flamingo-cimarron",
            "title": "Flamingo Wash Bridge & Drainage Improvement",
            "venue": "Flamingo Rd at Cimarron Rd",
            "agency": "Clark County Regional Flood",
            "details": "Bridge reinforcement and channel expansion. Right lanes shifted.",
            "duration": "Active Project",
            "lat": 36.1150, "lng": -115.2680
        }
    ]

    for proj in active_rtc_corridors:
        if proj["id"] not in seen:
            seen.add(proj["id"])
            regional_work.append({
                "id": proj["id"],
                "title": proj["title"],
                "venue": proj["venue"],
                "source": f"Seeing Orange ({proj['agency']})",
                "type": "RTC_SEEING_ORANGE",
                "start_time": datetime.now(timezone.utc).isoformat(),
                "duration": proj["duration"],
                "severity": "CRITICAL" if "interchange" in proj["title"].lower() else "MODERATE",
                "impact_tier": "RTC Capital Project",
                "latitude": proj["lat"],
                "longitude": proj["lng"],
                "geonet_dist": "Valley Wide Regional Domain",
                "exclusion_radius": 500,
                "recommended_detour": f"{proj['details']} Plan alternate routes or reduce transit speeds."
            })

    return regional_work

def fetch_open_incidents():
    url = "https://nvroads.com/api/v2/get/events"
    events = []
    try:
        res = requests.get(url, headers=BROWSER_HEADERS, timeout=8)
        if res.status_code == 200:
            for item in res.json():
                lat = item.get("latitude")
                lng = item.get("longitude")
                headline = str(item.get("headline", "Road Incident"))
                ev_type = str(item.get("type", "")).lower()

                # Filter for unplanned live traffic hazards and crashes
                if any(k in headline.lower() or k in ev_type for k in ["crash", "stall", "hazard", "debris", "emergency", "incident"]):
                    if lat is not None and lng is not None and (MIN_LAT <= float(lat) <= MAX_LAT) and (MIN_LNG <= float(lng) <= MAX_LNG):
                        events.append({
                            "id": f"nv-open-{item.get('id', lat)}",
                            "title": headline,
                            "venue": str(item.get("roadName", "Las Vegas Corridor")),
                            "source": "NV 511 / RTC FAST",
                            "type": "LIVE_INCIDENT",
                            "start_time": datetime.now(timezone.utc).isoformat(),
                            "severity": "CRITICAL" if "closure" in headline.lower() else "MODERATE",
                            "impact_tier": "Active Bottleneck",
                            "geonet_dist": "Live Incident",
                            "latitude": float(lat),
                            "longitude": float(lng),
                            "exclusion_radius": 400,
                            "recommended_detour": "Yield to roadside responders; utilize outer lanes."
                        })
    except Exception as e:
        print(f"Open 511 notice: {e}")
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
    """Expanded 15-mile radius and 2-page pagination covering the metro circle."""
    if not TM_API_KEY:
        return []

    now = datetime.now(timezone.utc)
    end_time = now + timedelta(days=7)
    results = []
    seen = set()

    for page in range(2):
        url = (
            f"https://app.ticketmaster.com/discovery/v2/events.json"
            f"?apikey={TM_API_KEY}"
            f"&latlong={LAS_VEGAS_LAT},{LAS_VEGAS_LNG}&radius=15&unit=miles"
            f"&startDateTime={now.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            f"&endDateTime={end_time.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            f"&size=100&page={page}&sort=date,asc"
        )
        try:
            res = requests.get(url, timeout=12)
            if res.status_code != 200:
                break
            events = res.json().get("_embedded", {}).get("events", [])
            if not events:
                break

            for item in events:
                venues = item.get("_embedded", {}).get("venues", [])
                if not venues:
                    continue

                venue_info = venues[0]
                venue_name = venue_info.get("name", "Unknown Venue")
                name = item.get("name", "Special Event")
                start_utc = item.get("dates", {}).get("start", {}).get("dateTime", now.isoformat())

                key = f"{name[:25]}_{venue_name}_{start_utc[:10]}"
                if key in seen:
                    continue
                seen.add(key)

                v_lat = float(venue_info.get("location", {}).get("latitude", LAS_VEGAS_LAT))
                v_lng = float(venue_info.get("location", {}).get("longitude", LAS_VEGAS_LNG))

                profile = VENUE_PROFILES.get(venue_name, {
                    "coords": [v_lat, v_lng],
                    "geonet_dist": "Valley Metro Corridor",
                    "radius": 500,
                    "impact_tier": "Tier 3 (Moderate)",
                    "detour": "Reroute to outer arterials.",
                    "pudo_status": "Standard Curbside PUDO",
                    "ped_density": "Local Foot Traffic",
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
                    "latitude": v_lat,
                    "longitude": v_lng,
                    "exclusion_radius": profile["radius"],
                    "recommended_detour": profile["detour"]
                })
        except Exception as e:
            print(f"Ticketmaster page {page} fetch notice: {e}")
            break

    return results

def fetch_community_events():
    """Ingests off-Strip, Town Square, and community festivals across the valley."""
    url = "https://www.vegascalendar.org/wp-json/vegascal/v1/events?days=7&per_page=30"
    community_items = []
    try:
        res = requests.get(url, headers=BROWSER_HEADERS, timeout=8)
        if res.status_code == 200:
            events = res.json().get("data", [])
            for ev in events:
                venue_data = ev.get("venue", {}) or {}
                v_lat = venue_data.get("lat")
                v_lng = venue_data.get("lng")
                v_name = venue_data.get("name", "Community Gathering")

                if v_lat and v_lng and (MIN_LAT <= float(v_lat) <= MAX_LAT) and (MIN_LNG <= float(v_lng) <= MAX_LNG):
                    community_items.append({
                        "id": f"comm-{ev.get('id', v_lat)}",
                        "title": f"Community: {ev.get('title', 'Public Festival')}",
                        "venue": v_name,
                        "source": "Local Community Feed",
                        "type": "TIMED_EVENT",
                        "start_time": ev.get("start_utc", datetime.now(timezone.utc).isoformat()),
                        "severity": "MODERATE",
                        "impact_tier": "Community Gathering",
                        "geonet_dist": "Inside Valley Operating Domain",
                        "latitude": float(v_lat),
                        "longitude": float(v_lng),
                        "exclusion_radius": 350,
                        "recommended_detour": "Local curbside congestion. Monitor pedestrian crossings."
                    })
    except Exception as e:
        print(f"Community event scraper notice: {e}")
    return community_items

def main():
    combined = []
    weather_info = fetch_weather_advisories()

    # 1. Dedicated F1 Strip Core Work
    combined.extend(get_f1_strip_standing())
    # 2. Regional Seeing Orange Valley-Wide Capital Projects
    combined.extend(fetch_seeing_orange_regional())
    # 3. Live Hazards & Open 511 Incidents
    combined.extend(fetch_open_incidents())
    # 4. Conventions & Ticketmaster Events (15-mile Valley Extent)
    combined.extend(fetch_conventions())
    combined.extend(fetch_ticketmaster_events())
    # 5. Local Community & Town Square Events
    combined.extend(fetch_community_events())

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

    print(f"Pipeline successfully generated {len(combined)} active operational elements.")

if __name__ == "__main__":
    main()
