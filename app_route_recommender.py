import streamlit as st
import pandas as pd
import openrouteservice
import joblib
from datetime import datetime
import os
from dotenv import load_dotenv
import pydeck as pdk

# Load environment variables (for local testing)
load_dotenv("py11.env")

# ORS client (switch between local or Streamlit Cloud secrets)
ORS_API_KEY = os.getenv("ORS_API_KEY") or st.secrets["ORS_API_KEY"]
ors = openrouteservice.Client(key=ORS_API_KEY)

# Load model and encoder
clf = joblib.load("models/risk_model.joblib")
ohe = joblib.load("models/encoder.joblib")

# Streamlit UI
st.title("🛣️ Safest Route Recommender")
start = st.text_input("Start location", "Union Square, San Francisco")
end = st.text_input("End location", "Golden Gate Park, San Francisco")

if st.button("Get Safest Route"):
    with st.spinner("🧠 Scoring your route..."):
        # Get coordinates
        start_coords = ors.pelias_search(start)["features"][0]["geometry"]["coordinates"]
        end_coords = ors.pelias_search(end)["features"][0]["geometry"]["coordinates"]
        coords = [start_coords, end_coords]

        # Get walking route as geojson
        routes = ors.directions(coords, profile='foot-walking', format='geojson')
        route = routes['features'][0]
        points = route['geometry']['coordinates']

        # Sample route and predict risk
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

        # Total risk
        total_risk = sum(risks)
        st.success(f"✅ Total risk score: {round(total_risk, 2)}")

        # Map route
        line = pd.DataFrame(points, columns=['lon', 'lat'])
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
