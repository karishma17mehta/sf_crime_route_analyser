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
st.markdown("Find the **safest walking route** in San Francisco by assessing crime risks in real time.")

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
    with st.spinner("Scoring your route for crime risk..."):

        try:
            coords = get_route_coords(start, end, ors_client)
            if coords is None:
                raise ValueError("Route coordinates could not be retrieved.")
            st.write("🧭 First few route points:", coords[:3])
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
            if not result or "coords" not in result:
                raise ValueError("No valid route returned.")
        except Exception as e:
            st.error(f"❌ Rerouting failed: {e}")
            st.stop()

        # Display rerouting logic
        if result["was_rerouted"]:
            st.warning("⚠️ High-risk areas detected. Route was adjusted to improve safety.")
            st.markdown(f"""
            ### 🔍 Reroute Details:
            - Original route risk: **{round(result['original_risk'], 2)}**
            - New route risk: **{round(result['avg_risk'], 2)}**
            - 🔁 Risk reduction: **{round(result['original_risk'] - result['avg_risk'], 2)}**
            - Buffer applied: `{result['buffer_used']}` degrees
            """)
        else:
            st.success(f"✅ Safe route! Risk score: **{round(result['avg_risk'], 2)}**")

        # Plot route and live crimes
        folium_map = plot_route_on_map(
            result["coords"],
            start,
            end,
            risk_score=result["avg_risk"],
            risk_per_point=result["risk_per_point"],
            rerouted=result["was_rerouted"]
        )
        crime_data = fetch_live_crimes(minutes_ago=2880)
        add_crime_markers(folium_map, crime_data)

        st.components.v1.html(folium_map.get_root().render(), height=520)

        with st.expander("📘 How does this work?"):
            st.markdown("""
            - Risk is predicted using a machine learning model trained on SF crime data.
            - Each route segment is scored by:
                - 🕐 Hour & minute
                - 📅 Day of the week
                - 📍 Location (lat/lon)
            - If route risk > 0.5, a reroute is triggered using a small lateral buffer.
            - Live crime reports are also shown for added transparency.
            """)
