#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import streamlit as st
import pandas as pd
import openrouteservice
from openrouteservice import convert
import joblib
from datetime import datetime, timezone
import os
from dotenv import load_dotenv
import pydeck as pdk

# Load secrets
load_dotenv("py11.env")  # or use st.secrets if on Streamlit Cloud

# ORS client
ors = openrouteservice.Client(key=os.getenv("ORS_API_KEY"))

# Load model + encoder
clf = joblib.load("models/risk_model.joblib")
ohe = joblib.load("models/encoder.joblib")

# Streamlit UI
st.title("🛣️ Safest Route Recommender")
start = st.text_input("Start location", "Union Square, San Francisco")
end = st.text_input("End location", "Golden Gate Park, San Francisco")

if st.button("Get Safest Route"):
    with st.spinner("🧠 Scoring route options..."):
        coords = ors.pelias_search(start)["features"][0]["geometry"]["coordinates"], \
                 ors.pelias_search(end)["features"][0]["geometry"]["coordinates"]

        routes = ors.directions(coords, profile='driving-car', format='geojson', optimize_waypoints=True)
        all_routes = routes['features']

        best_route = None
        lowest_risk = float('inf')

        for route in all_routes:
            points = convert.decode_polyline(route['geometry'])['coordinates']
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

            total_risk = sum(risks)
            if total_risk < lowest_risk:
                lowest_risk = total_risk
                best_route = route

        # Show best route on map
        st.success(f"✅ Lowest risk score: {round(lowest_risk, 2)}")
        line = pd.DataFrame(best_route['geometry']['coordinates'], columns=['lon', 'lat'])

        st.pydeck_chart(pdk.Deck(
            initial_view_state=pdk.ViewState(
                latitude=line.lat.mean(),
                longitude=line.lon.mean(),
                zoom=12,
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

