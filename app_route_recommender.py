import streamlit as st
import joblib
from datetime import datetime
from dotenv import load_dotenv
import os
import openrouteservice
from utils import (
    get_route_coords,
    iterative_reroute_min_risk,
    plot_route_on_map
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
start = st.text_input("📍 Start location", "123 Market Street, San Francisco")
end = st.text_input("🏁 End location", "3250 16th Street, San Francisco")

col1, col2 = st.columns(2)
with col1:
    hour = st.slider("Hour", 0, 23, datetime.now().hour)
with col2:
    minute = st.slider("Minute", 0, 59, datetime.now().minute)

if st.button("🧭 Find Safest Route"):
    with st.spinner("Calculating route and assessing safety..."):
        try:
            # Convert start/end to route coordinates
            coords = get_route_coords(start, end, ors_client)
        except Exception as e:
            st.error(f"❌ Could not geocode route: {e}")
            st.stop()

        day_str = datetime.now().strftime("%A")

        try:
            result = iterative_reroute_min_risk(
                coords=coords,
                start=start,
                end=end,
                hour=hour,
                minute=minute,
                day_str=day_str,
                clf=clf,
                ohe=ohe,
                day_labels=day_labels,
                ors_client=ors_client
            )
        except Exception as e:
            st.error(f"❌ Rerouting failed: {e}")
            st.stop()

        # Plot the final route
        st.success(
            f"✅ Route risk score: {round(result['avg_risk'], 2)}"
            + (" — rerouted to avoid crime hotspots" if result["was_rerouted"] else " — original route is safe")
        )

        folium_map = plot_route_on_map(
            result["coords"],
            start,
            end,
            risk_score=result["avg_risk"],
            risk_per_point=result["risk_per_point"],
            rerouted=result["was_rerouted"]
        )
        st.components.v1.html(folium_map.get_root().render(), height=500)
