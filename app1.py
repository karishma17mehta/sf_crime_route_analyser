import streamlit as st
import os, joblib, json, threading
from datetime import datetime
from dotenv import load_dotenv
from confluent_kafka import Consumer
import openrouteservice
import folium
from streamlit_folium import st_folium
from utils import (
    create_ors_client, geocode_address, get_route_coords,
    assess_route, iterative_reroute_min_risk, plot_route_on_map
)

# --- Load environment variables ---
load_dotenv("py.env")
api_key = os.getenv("ORS_API_KEY")

# --- Load models & client ---
clf = joblib.load("models/risk_model.joblib")
ohe = joblib.load("models/encoder.joblib")
day_labels = ohe.get_feature_names_out(['day_of_week_encoded'])
ors_client = create_ors_client(api_key)

# --- Real-time Kafka listener for sidebar updates ---
live_predictions = []

def kafka_listener():
    conf = {
        'bootstrap.servers': os.getenv("BOOTSTRAP_SERVERS"),
        'security.protocol': 'SASL_SSL',
        'sasl.mechanisms': 'PLAIN',
        'sasl.username': os.getenv("API_KEY"),
        'sasl.password': os.getenv("API_SECRET"),
        'group.id': 'streamlit-risk-display',
        'auto.offset.reset': 'latest'
    }
    consumer = Consumer(conf)
    consumer.subscribe(['predicted-risk'])

    while True:
        msg = consumer.poll(1.0)
        if msg is None:
            continue
        if msg.error():
            print("Kafka error:", msg.error())
            continue

        try:
            event = json.loads(msg.value().decode('utf-8'))
            print("📬 Kafka prediction received:", event)
            live_predictions.append(event)
            if len(live_predictions) > 20:
                live_predictions.pop(0)
        except Exception as e:
            print("Error parsing prediction:", e)

# --- Start background thread once ---
if "kafka_started" not in st.session_state:
    threading.Thread(target=kafka_listener, daemon=True).start()
    st.session_state["kafka_started"] = True

# --- Streamlit UI ---
st.set_page_config(layout="wide")
st.title("🛡️ SafeRoute: Real-Time Crime-Aware Navigation")

# --- Sidebar: Live Segment Predictions ---
st.sidebar.header("🚨 Segment-Level Predictions")
if live_predictions:
    for seg in reversed(live_predictions[-5:]):
        st.sidebar.markdown(f"""
        **{seg.get("from", "Unknown")}**  
        → `{seg.get("to", "Unknown")}`  
        🔥 Risk Score: `{seg.get("risk_score", "N/A")}`
        """)
else:
    st.sidebar.info("No predictions received yet.")

# --- UI Input ---
start_address = st.text_input("📍 Enter your starting address", "")
end_address = st.text_input("🏁 Enter your destination address", "")
hour = st.number_input("⏰ Hour of travel (0-23)", min_value=0, max_value=23, value=12)
minute = st.number_input("⏱️ Minute of travel (0-59)", min_value=0, max_value=59, value=0)
day_str = st.selectbox("📅 Day of the week", [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
])

# --- Run logic on button click ---
if 'route_result' not in st.session_state:
    st.session_state['route_result'] = None

if st.button("🚦 Check Route Safety"):
    start = geocode_address(start_address, api_key)
    end = geocode_address(end_address, api_key)

    if start is None or end is None:
        st.error("Could not geocode one or both addresses. Please try more specific locations.")
        st.stop()

    st.success(f"Valid addresses found: {start_address} → {end_address}")
    st.write(f"Start coordinates: {start}")
    st.write(f"End coordinates: {end}")

    coords = get_route_coords(start, end, ors_client)
    if coords is None:
        st.error("No route found between these locations.")
        st.stop()

    try:
        result = iterative_reroute_min_risk(
            coords, start, end, hour, minute, day_str,
            clf, ohe, day_labels, ors_client
        )
        st.session_state['route_result'] = (result, start, end)
    except Exception as e:
        st.error(f"Error during rerouting/risk calculation: {e}")
        st.stop()

# --- Display result ---
if st.session_state['route_result']:
    result, start, end = st.session_state['route_result']
    st.success(f"🧮 Route risk score: {result['avg_risk']:.2f}")

    if result["was_rerouted"]:
        if result["avg_risk"] <= 0.5:
            st.info(f"🔁 Rerouted to avoid risk. Buffer used: {result['buffer_used']}")
        else:
            st.warning("⚠️ Even rerouted route is high risk. Consider rescheduling.")
    else:
        if result["avg_risk"] <= 0.5:
            st.success("✅ Original route is safe. No rerouting required.")
        else:
            st.warning("⚠️ Original route is risky, and no safer path was found.")

    # --- Show Map ---
    st.subheader("🗺️ Route Map")
    if result.get("coords"):
        folium_map = plot_route_on_map(
            result["coords"], start, end, result["avg_risk"],
            result["risk_per_point"], rerouted=result["was_rerouted"]
        )
        st_folium(folium_map, width=700)
    else:
        st.error("Error rendering route on map.")
