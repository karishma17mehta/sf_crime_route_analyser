import numpy as np
import requests
import folium
from datetime import datetime, timedelta
from geopy.distance import geodesic

def fetch_live_crimes(minutes_ago=1440):
    since_time = (datetime.now() - timedelta(minutes=minutes_ago)).isoformat()
    url = "https://data.sfgov.org/resource/wg3w-h783.json"
    params = {
        "$where": f"incident_datetime > '{since_time}'",
        "$limit": 500,
        "$order": "incident_datetime DESC"
    }
    response = requests.get(url, params=params)
    return response.json() if response.status_code == 200 else []

def add_crime_markers(map_obj, crime_data):
    for c in crime_data:
        try:
            lat = float(c["latitude"])
            lon = float(c["longitude"])
            tooltip = f"{c.get('incident_category', 'Unknown')} ({c.get('incident_datetime', '')})"
            folium.CircleMarker(
                location=[lat, lon],
                radius=4,
                color="red",
                fill=True,
                fill_color="red",
                fill_opacity=0.7,
                tooltip=tooltip
            ).add_to(map_obj)
        except:
            continue

def get_route_coords(start, end, client):
    try:
        start_coords = client.pelias_search(start)["features"][0]["geometry"]["coordinates"]
        end_coords = client.pelias_search(end)["features"][0]["geometry"]["coordinates"]
        route = client.directions(
            coordinates=[start_coords, end_coords],
            profile='foot-walking',
            format='geojson'
        )
        return route['features'][0]['geometry']['coordinates']
    except Exception as e:
        print(f"❌ Routing error: {e}")
        return None

def is_near_crime(point, crimes, radius_meters=50):
    lat1, lon1 = point
    for c in crimes:
        try:
            lat2 = float(c["latitude"])
            lon2 = float(c["longitude"])
            if geodesic((lat1, lon1), (lat2, lon2)).meters <= radius_meters:
                return True
        except:
            continue
    return False

def assess_route(coords, hour, minute, day_str, clf, ohe, day_labels):
    day_encoded = ohe.transform([[day_str]])
    route_features = []
    for lon, lat in coords:
        row_encoded = np.concatenate(
            [np.array([[hour, minute, lat, lon]]), day_encoded],
            axis=1
        )
        route_features.append(row_encoded[0])
    preds = clf.predict_proba(route_features)[:, 1]
    return preds.mean(), preds.tolist()

def iterative_reroute_min_risk(coords, start, end, hour, minute, day_str, clf, ohe, day_labels, client, buffer=0.01):
    if coords is None:
        return None

    recent_crimes = fetch_live_crimes(minutes_ago=1440)
    original_risk, original_scores = assess_route(coords, hour, minute, day_str, clf, ohe, day_labels)

    near_crime = any(is_near_crime((lat, lon), recent_crimes) for lon, lat in coords)

    if original_risk <= 0.5 and not near_crime:
        return {
            "coords": coords,
            "avg_risk": original_risk,
            "risk_per_point": original_scores,
            "was_rerouted": False,
            "original_risk": original_risk
        }

    rerouted_coords = [(lon, lat + buffer) for lon, lat in coords]
    rerouted_risk, rerouted_scores = assess_route(rerouted_coords, hour, minute, day_str, clf, ohe, day_labels)

    return {
        "coords": rerouted_coords,
        "avg_risk": rerouted_risk,
        "risk_per_point": rerouted_scores,
        "was_rerouted": True,
        "original_risk": original_risk,
        "buffer_used": buffer
    }

def plot_route_on_map(coords, start, end, risk_score, risk_per_point, rerouted=False):
    if coords is None or len(coords) == 0:
        return folium.Map(location=[37.7749, -122.4194], zoom_start=12)

    lon, lat = coords[0]
    m = folium.Map(location=[lat, lon], zoom_start=13)

    folium.Marker([start[1], start[0]], tooltip="Start", icon=folium.Icon(color="green")).add_to(m)
    folium.Marker([end[1], end[0]], tooltip="End", icon=folium.Icon(color="red")).add_to(m)

    route_line = [(lat, lon) for lon, lat in coords]
    color = "red" if risk_score > 0.5 else "green"
    folium.PolyLine(route_line, color=color, weight=5, tooltip="Route").add_to(m)

    for (lon, lat), risk in zip(coords, risk_per_point):
        folium.CircleMarker(
            location=(lat, lon),
            radius=3,
            color="black",
            fill=True,
            fill_color="orange" if risk > 0.5 else "blue",
            fill_opacity=0.6,
            tooltip=f"Risk: {risk:.2f}"
        ).add_to(m)

    return m
