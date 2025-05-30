import streamlit as st
import joblib
from datetime import datetime
from dotenv import load_dotenv
import os
import openrouteservice

from utils import (
    get_route_coords,
    iterative_reroute_min_risk,
    plot_route_on_map,
    fetch_live_crimes,
    add_crime_markers
)

# Load environment variables
load_dotenv("py11.env")
ORS_API_KEY = os.getenv("ORS_API_KEY") or st.secrets["ORS_API_KEY"]

# Load model + encoder
clf = joblib.load("models/risk_model.joblib")
ohe = joblib.load("models/encoder.joblib")
day_labels = list(ohe.categories_[0])

# Initialize ORS client
ors_client = openrouteservice.Client(key=ORS_API_KEY)

# Streamlit UI
st.title("🚦 Smart Crime-Aware Route Recommender")
st.markdown("Enter your start and end points to find a walking route optimized for **lower crime risk**.")

start = st.text_input("📍 Start location", "3250 16th Street, San Francisco")
end = st.text_input("🏁 End location", "123 Market Street, San Francisco")

col1, col2, col3 = st.columns(3)
with col1:
    hour = st.slider("🕐 Hour of travel", 0, 23, datetime.now().hour)
with col2:
    minute = st.slider("🕒 Minute of travel", 0, 59, datetime.now().minute)
with col3:
    day_str = st.selectbox("📅 Day of week", day_labels, index=day_labels.index(datetime.now().strftime("%A")))

if st.button("🧭 Find Safest Route"):
    with st.spinner("Calculating route and assessing safety..."):
        st.markdown(f"🔎 **Searching route:** `{start}` → `{end}`")

        try:
            coords = get_route_coords(start, end, ors_client)
            st.write("🧭 First few route points:", coords[:3] if coords else "None")
            if coords is None:
                raise ValueError("Route coordinates could not be retrieved.")
        except Exception as e:
            st.error(f"❌ Could not geocode or retrieve route: {e}")
            st.stop()

        try:
            result = iterative_reroute_min_risk(
                coords,
                start,
                end,
                hour,
                minute,
                day_str,
                clf,
                ohe,
                day_labels,
                ors_client
            )
            if result is None or "coords" not in result:
                raise ValueError("No valid route returned.")
        except Exception as e:
            st.error(f"❌ Rerouting failed: {e}")
            st.stop()

        # ✅ Display route risk results
        if result["was_rerouted"]:
            st.warning("⚠️ High-risk segments were detected on the original route. Rerouting was applied to avoid crime hotspots.")

            st.markdown(f"""
            ### 🔍 Why rerouted?
            - Original route risk: **{round(result['original_risk'], 2)}**
            - Rerouted path risk: **{round(result['avg_risk'], 2)}**
            - 🔁 **Risk reduced by:** `{round(result['original_risk'] - result['avg_risk'], 2)}`
            - Buffer offset used: `{result.get('buffer_used', 0)}` degrees
            """)
        else:
            st.success(f"✅ Original route is safe — risk score: **{round(result['avg_risk'], 2)}**")

        # 🗺️ Plot route
        folium_map = plot_route_on_map(
            result["coords"],
            start,
            end,
            risk_score=result["avg_risk"],
            risk_per_point=result["risk_per_point"],
            rerouted=result["was_rerouted"]
        )

        # ➕ Add live crime incident markers
        crime_data = fetch_live_crimes(minutes_ago=2880)
        add_crime_markers(folium_map, crime_data)

        st.components.v1.html(folium_map.get_root().render(), height=520)

        with st.expander("📘 How is crime risk calculated?"):
            st.markdown("""
            Risk scores are based on:
            - 📍 Location (latitude, longitude)
            - 🕒 Hour & minute of travel
            - 📅 Day of the week

            The model is trained on historical SF crime data.
            If risk > 0.5, the route is rerouted with a lateral buffer to reduce exposure to hotspots.
            """)
