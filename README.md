
# 🚦 SF Crime-Aware Route Recommender

A real-time Streamlit web app that recommends **safer walking routes** in San Francisco by integrating:

- OpenRouteService API for route generation  
- Live crime data from SF Open Data Portal  
- A machine learning model to assess route risk  
- Interactive map visualizations with real-time rerouting

---

## What It Does

This app allows a user to:
- Enter **start and end locations**
- Specify **time of day** and **day of the week**
- View the safest walking route based on:
  - ML-predicted risk of crime
  - Recent (last 24–48 hrs) reported crime near the route
- See if rerouting was applied and why

---

## Live Demo

🔗 [Try it on Streamlit Cloud](https://msba-sf-crime-analyser.streamlit.app)


---

## 🤖 Machine Learning Model

- **Model**: Logistic Regression (`scikit-learn`)
- **Inputs per route point**:
  - `latitude`, `longitude`
  - `hour`, `minute`
  - `day_of_week` (one-hot encoded)
- **Output**: Probability score indicating risk of crime
- Route risk is the **average risk score** across all path points

---

## 🔄 Live Rerouting Logic

1. Crime incidents from the **last 24–48 hours** are pulled live from SF Open Data
2. The app checks if **any route point** is within ~50 meters of a recent crime
3. If:
   - Route passes near crime points
   - OR average risk score > 0.5  
   → Then rerouting is triggered
4. Rerouting:
   - Applies a **latitude shift** (buffer) to nudge the route
   - Recalculates risk on the rerouted path
   - Chooses the safer of the two paths

---

## 📍 Map Features

- Safe and unsafe routes are color-coded (`green` / `red`)
- Crime incidents are plotted as **red markers**
- Risk per route point is visualized via color-coded circles
- If rerouting occurred, an explanation is displayed

---

## ⚙️ Tech Stack

| Component        | Tool / API                                      |
|------------------|--------------------------------------------------|
| Frontend         | [Streamlit](https://streamlit.io/)               |
| Routing          | [OpenRouteService API](https://openrouteservice.org/) |
| Crime Data       | [SF Open Data API](https://data.sfgov.org/)     |
| ML Model         | `scikit-learn`, `joblib`                        |
| Visualization    | [Folium](https://python-visualization.github.io/folium/) |
| Hosting          | [Streamlit Cloud](https://streamlit.io/cloud)   |

---
**Key Features**

- Personalized safety recommendations
- Live crime overlays on walking routes
- Rerouting logic based on real-world data  
- Transparent model explanations
- Fully interactive map

---

**Future Enhancements**

- Smarter rerouting via alternative path search
- User-selected filters for crime type (e.g., avoid assaults only
- Travel modes: bike, driving, public transport
- Integration with Kafka for streaming backend
- User-specific safety preferences

---

**Acknowledgements**

- SF Open Data Portal for providing public crime incident reports
- OpenRouteService for open-source routing and geocoding
- Streamlit for rapid prototyping and deployment
