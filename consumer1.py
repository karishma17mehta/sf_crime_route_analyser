# consumer.py
from confluent_kafka import Consumer
import os, json, joblib
from dotenv import load_dotenv
from datetime import datetime
import pandas as pd

# Load env variables
load_dotenv()

# Load model + encoder
clf = joblib.load("models/risk_model.joblib")
ohe = joblib.load("models/encoder.joblib")

# Config for Confluent Kafka
conf = {
    'bootstrap.servers': os.getenv("BOOTSTRAP_SERVERS"),
    'security.protocol': 'SASL_SSL',
    'sasl.mechanisms': 'PLAIN',
    'sasl.username': os.getenv("API_KEY"),
    'sasl.password': os.getenv("API_SECRET"),
    'group.id': 'crime-risk-worker',
    'auto.offset.reset': 'earliest'
}

consumer = Consumer(conf)
consumer.subscribe(['crime-events'])

PREDICTION_FILE = "latest_prediction.json"

def save_prediction(prediction):
    with open(PREDICTION_FILE, "w") as f:
        json.dump(prediction, f)

print("✅ Connected to Confluent Cloud. Waiting for messages...")

segments = []

while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        print("❌ Kafka error:", msg.error())
        continue

    try:
        event = json.loads(msg.value().decode('utf-8'))
        print("📥 Received:", event)

        incident_time = event.get("incident_datetime")
        hour = datetime.fromisoformat(incident_time).hour
        day = datetime.fromisoformat(incident_time).strftime("%A")

        row = {
            "hour": hour,
            "minute": 0,
            "day_of_week_encoded": day
        }

        X = ohe.transform(pd.DataFrame([row]))
        risk = float(clf.predict_proba(X)[0][1])

        segments.append({
            "from": event.get("address", "unknown"),
            "to": "unknown",
            "risk_score": round(risk, 2)
        })

        if len(segments) > 10:
            segments = segments[-10:]

        save_prediction({"segments": segments})

    except Exception as e:
        print(f"❌ Error handling message: {e}")
