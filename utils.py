import openrouteservice
import folium
import numpy as np

def create_ors_client(api_key):
    print("🔑 Creating ORS client...")
    return openrouteservice.Client(key=api_key)

def geocode_address(address, api_key):
    client = create_ors_client(api_key)
    try:
        print(f"📍 Geocoding address: {address}")
        geocode = client.pelias_search(text=address)
        coords = geocode['features'][0]['geometry']['coordinates']
        print(f"✅ Coordinates for '{address}': {coords[1]}, {coords[0]}")
        return coords[0], coords[1]  # (lon, lat)
    except Exception as e:
        print(f"❌ Geocoding error for '{address}':", e)
        return None

def get_route_coords(start, end, client):
    try:
        print(f"🛣️ Requesting route from {start} to {end}")
        route = client.directions(
            coordinates=[start, end],
            profile='foot-walking',
            format='geojson'
        )
        coords = route['features'][0]['geometry']['coordinates']
        if not coords:
            print("❌ No route geometry found.")
            return None
        print(f"✅ Route found with {len(coords)} points")
        return coords
    except Exception as e:
        print(f"❌ Routing error: {e}")
        return None

def assess_route(coords, hour, minute, day_str, clf, ohe, day_labels):
    day_encoded = ohe.transform([[day_str]])
    route_features = []
    for lon, lat in coords:
        row = {
            "hour": hour,
            "minute": minute,
            "latitude": lat,
            "longitude": lon
        }
        row_encoded = np.concatenate(
            [np.array([[row['hour'], row['minute'], row['latitude'], row['longitude']]]), day_encoded],
            axis=1
        )
        route_features.append(row_encoded[0])
    preds = clf.predict_proba(route_features)[:, 1]
    return preds.mean(), preds.tolist()

def iterative_reroute_min_risk(coords, start, end, hour, minute, day_str, clf, ohe, day_labels, client, buffer=0.01):
    if coords is None:
        print("❌ No original route available for risk assessment.")
        return None

    original_risk, original_scores = assess_route(coords, hour, minute, day_str, clf, ohe, day_labels)
    if original_risk <= 0.5:
        return {
            "coords": coords,
            "avg_risk": original_risk,
            "risk_per_point": original_scores,
            "was_rerouted": False
        }

    print("⚠️ High risk detected. Attempting reroute...")

    lat_offset = buffer
    reroute_coords = [(lon, lat + lat_offset) for lon, lat in coords]

    rerouted_risk, rerouted_scores = assess_route(reroute_coords, hour, minute, day_str, clf, ohe, day_labels)
    return {
        "coords": reroute_coords,
        "avg_risk": rerouted_risk,
        "risk_per_point": rerouted_scores,
        "was_rerouted": True,
        "buffer_used": buffer
    }

def plot_route_on_map(coords, start, end, risk_score, risk_per_point, rerouted=False):
    m = folium.Map(location=[start[1], start[0]], zoom_start=13)

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
