import streamlit as st
import os, joblib, json
from datetime import datetime
from dotenv import load_dotenv
from kafka import KafkaConsumer
import threading

import pandas as pd
import numpy as np
import openrouteservice
import folium
from streamlit_folium import st_folium
from utils import (
    create_ors_client, geocode_address, get_route_coords, assess_route,
    iterative_reroute_min_risk, plot_route_on_map
)

# --- Load environment variables ---
load_dotenv("py.env")
api_key = os.getenv("ORS_API_KEY")

# --- Kafka listener setup ---
live_events = []

def kafka_listener():
    print("Kafka listener thread starting!")
    consumer = KafkaConsumer(
        'crime-events',
        bootstrap_servers='localhost:9092',
        auto_offset_reset='earliest',
        group_id='crime-risk-app',
        value_deserializer=lambda m: json.loads(m.decode('utf-8'))
    )
    print("Kafka consumer created, waiting for events...")
    for msg in consumer:
        live_events.append(msg.value)
        if len(live_events) > 100:
            del live_events[0:len(live_events)-100]

# Launch the Kafka listener once
if "kafka_started" not in st.session_state:
    threading.Thread(target=kafka_listener, daemon=True).start()
    st.session_state["kafka_started"] = True

# --- Display sidebar live incidents ---
st.sidebar.header("🚨 Live Crime Incidents")
st.sidebar.write("Current number of incidents:", len(live_events))
if live_events:
    for event in reversed(live_events[-10:]):
        t = event.get("datetime", "")
        desc = event.get("description", "")
        cat = event.get("category", "")
        st.sidebar.write(f"**[{t}]**: {cat} - {desc}")
else:
    st.sidebar.write("No incidents yet. Waiting for Kafka events...")

if st.sidebar.button("🔄 Refresh incidents"):
    pass  # Just forces rerun

# --- Load models & client ---
clf = joblib.load("models/risk_model.joblib")
ohe = joblib.load("models/encoder.joblib")
day_labels = ohe.get_feature_names_out(['day_of_week_encoded'])
ors_client = create_ors_client(api_key)

st.set_page_config(layout="wide")
st.title("🛡️ SafeRoute: Real-Time Crime-Aware Navigation")

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

    if not (start and end):
        st.error("Could not geocode one or both addresses. Try again with more specific inputs.")
        st.stop()

    st.success(f"Valid addresses found: {start_address} → {end_address}")

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

    # --- Segment-level Prediction Chatbot Style ---
    st.subheader("🧠 Segment-Level Risk Breakdown")
    from consumer import get_latest_predictions

    try:
        segment_preds = get_latest_predictions()
        if segment_preds:
            for idx, seg in enumerate(segment_preds.get("segments", [])):
                st.markdown(f"""
                **Segment {idx+1}**
                - 🧭 From: `{seg.get('from')}`
                - 🧭 To: `{seg.get('to')}`
                - 🚨 Predicted Risk: `{seg.get('risk_score', 'N/A'):.2f}`
                """)
        else:
            st.info("No segment-level predictions available yet.")
    except Exception as e:
        st.warning(f"Error loading predictions: {e}")
