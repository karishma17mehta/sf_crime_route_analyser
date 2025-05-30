import openrouteservice
from openrouteservice import convert
import folium
import numpy as np

def create_ors_client(api_key):
    return openrouteservice.Client(key=api_key)

def geocode_address(address, api_key):
    client = create_ors_client(api_key)
    try:
        geocode = client.pelias_search(text=address)
        coords = geocode['features'][0]['geometry']['coordinates']
        return coords[0], coords[1]
    except Exception as e:
        print("Geocoding error:", e)
        return None

def get_route_coords(start, end, client):
    try:
        print(f"🧭 Getting route from {start} to {end}")
        route = client.directions(
            coordinates=[start, end],
            profile='driving-car',
            format='geojson'
        )
        coords = convert.decode_polyline(route['routes'][0]['geometry'])['coordinates']
        print(f"✅ Route found with {len(coords)} points.")
        return coords
    except Exception as e:
        print(f"❌ Routing error: {e}")
        return None


def assess_route(coords, hour, minute, day_str, clf, ohe, day_labels):
    day_encoded = ohe.transform([[day_str]])
    route_features = []
    for lat, lon in coords:
        row = {
            "hour": hour,
            "minute": minute,
            "latitude": lat,
            "longitude": lon
        }
        row_encoded = np.concatenate([np.array([[row['hour'], row['minute'], row['latitude'], row['longitude']]]), day_encoded], axis=1)
        route_features.append(row_encoded[0])
    preds = clf.predict_proba(route_features)[:, 1]
    return preds.mean(), preds.tolist()

def iterative_reroute_min_risk(coords, start, end, hour, minute, day_str, clf, ohe, day_labels, client, buffer=0.01):
    original_risk, original_scores = assess_route(coords, hour, minute, day_str, clf, ohe, day_labels)
    if original_risk <= 0.5:
        return {
            "coords": coords,
            "avg_risk": original_risk,
            "risk_per_point": original_scores,
            "was_rerouted": False
        }

    lat_offset = buffer
    reroute_coords = [(lat + lat_offset, lon) for lat, lon in coords]

    rerouted_risk, rerouted_scores = assess_route(reroute_coords, hour, minute, day_str, clf, ohe, day_labels)
    return {
        "coords": reroute_coords,
        "avg_risk": rerouted_risk,
        "risk_per_point": rerouted_scores,
        "was_rerouted": True,
        "buffer_used": buffer
    }

def plot_route_on_map(coords, start, end, avg_risk, risk_scores, rerouted=False):
    m = folium.Map(location=[start[1], start[0]], zoom_start=13)

    folium.Marker([start[1], start[0]], tooltip="Start", icon=folium.Icon(color="green")).add_to(m)
    folium.Marker([end[1], end[0]], tooltip="End", icon=folium.Icon(color="red")).add_to(m)

    route_line = [(lat, lon) for lon, lat in coords]
    color = "red" if avg_risk > 0.5 else "green"
    folium.PolyLine(route_line, color=color, weight=5, tooltip="Route").add_to(m)

    for (lon, lat), risk in zip(coords, risk_scores):
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
