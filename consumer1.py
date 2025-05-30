from kafka import KafkaConsumer
import json
import joblib
import os
from datetime import datetime
from dotenv import load_dotenv
import numpy as np

# --- Load environment and model ---
load_dotenv("py.env")
clf = joblib.load("models/risk_model.joblib")
ohe = joblib.load("models/encoder.joblib")

# File path to save predictions for app.py to read
PREDICTION_FILE = "latest_prediction.json"

def save_prediction(prediction):
    with open(PREDICTION_FILE, "w") as f:
        json.dump(prediction, f)

def get_latest_predictions():
    if os.path.exists(PREDICTION_FILE):
        with open(PREDICTION_FILE, "r") as f:
            return json.load(f)
    return {}

# --- Start Kafka consumer ---
consumer = KafkaConsumer(
    'crime-events',
    bootstrap_servers='localhost:9092',
    auto_offset_reset='latest',
    value_deserializer=lambda m: json.loads(m.decode('utf-8'))
)

print("Listening for crime-events...")

segment_predictions = []

for msg in consumer:
    event = msg.value
    print("Received event:", event)

    try:
        # Step 1: Extract necessary fields
        hour = datetime.fromisoformat(event['incident_datetime']).hour
        day_of_week = datetime.fromisoformat(event['incident_datetime']).strftime("%A")

        # Step 2: Format into model input
        input_data = {
            'hour': hour,
            'minute': 0,  # assuming
            'day_of_week_encoded': day_of_week
        }

        df_input = ohe.transform(pd.DataFrame([input_data]))
        risk_score = clf.p_
