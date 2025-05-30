import streamlit as st
import pandas as pd
import openrouteservice
import joblib
from datetime import datetime
import os
from dotenv import load_dotenv
import pydeck as pdk

# Load environment variables
load_dotenv("py11.env")  # For local testing
ORS_API_KEY = os.getenv("ORS_API_KEY") or st.secrets["ORS_API_KEY"]

# ORS client
ors = openrouteservice.Client(key=ORS_API_KEY)

# Load ML model and encoder
clf = joblib.load("models/risk_model.joblib")
ohe = joblib.load("models/encoder.joblib")

# Streamlit UI
st.title("🛣️ Safest Route Recommender")
start = st.text_input("Start location", "123 Market Street, San Francisco")
end = st.text_input("End location", "3250 16th Street, San Francisco")

if st.button("Get Safest Route"):
    with st.spinner("🧠 Calculating safest path..."):
        try:
            # Get coordinates
            start_coords = ors.pelias_search(start)["features"][0]["geometry"]["coordinates"]
            end_coords = ors.pelias_search(end)["features"][0]["geometry"]["coordinates"]
            coords = [start_coords, end_coords]
            st.info(f"📍 From: {start_coords}, To: {end_coords}")
        except Exception as e:
            st.error(f"❌ Failed to locate address: {e}")
            st.stop()

        try:
            route = ors.directions(coords, profile='foot-walking', format='geojson')['features'][0]
        except openrouteservice.exceptions.ApiError as e:
            st.error(f"❌ ORS API error: {e}")
            st.stop()

        points = route['geometry']['coordinates']
        if not points:
            st.error("❌ No route returned. Try a different location.")
            st.stop()

        # Score risk at sampled points
        risks = []
        for lon, lat in points[::10]:  # Sample every 10th point
            hour = datetime.now().hour
            day = datetime.now().strftime("%A")
            row = {
                "incident_hour": hour,
                "incident_minute": 0,
                "latitude": lat,
                "longitude": lon,
                "day_of_week_encoded": day
            }
            df = pd.DataFrame([row])
            encoded = ohe.transform(df[['day_of_week_encoded']])
            encoded_df = pd.DataFrame(encoded, columns=ohe.get_feature_names_out(['day_of_week_encoded']))
            X = pd.concat([df.drop(columns=['day_of_week_encoded']), encoded_df], axis=1)
            risk = clf.predict_proba(X)[0][1]
            risks.append(risk)

        total_risk = round(sum(risks), 2)
        st.success(f"✅ Total risk score: {total_risk}")

        # Prepare map data
        line = pd.DataFrame(points, columns=['lon', 'lat']).astype(float)

        st.pydeck_chart(pdk.Deck(
            initial_view_state=pdk.ViewState(
                latitude=line.lat.mean(),
                longitude=line.lon.mean(),
                zoom=13,
                pitch=0,
            ),
            layers=[
                pdk.Layer(
                    "LineLayer",
                    data=line,
                    get_source_position=["lon", "lat"],
                    get_target_position=["lon", "lat"],
                    get_width=5,
                    get_color=[0, 255, 0],
                    pickable=True
                )
            ],
        ))
