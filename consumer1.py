from confluent_kafka import Consumer
import os, json, joblib, requests
from dotenv import load_dotenv
from datetime import datetime
import pandas as pd

# Load env variables
load_dotenv()

# === Download model and encoder from GitHub ===
def download_from_github(raw_url, dest_path):
    print(f"📥 Downloading {dest_path} from GitHub...")
    response = requests.get(raw_url, stream=True)
    if response.status_code == 200:
        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        print(f"✅ Downloaded {dest_path}")
    else:
        raise Exception(f"❌ Failed to download {raw_url}")

# GitHub raw URLs
MODEL_URL = "https://raw.githubusercontent.com/karishma17mehta/sf_crime_route_analyser/main/models/risk_model.joblib"
ENCODER_URL = "https://raw.githubusercontent.com/karishma17mehta/sf_crime_route_analyser/main/models/encoder.joblib"


# Ensure models directory exists
os.makedirs("models", exist_ok=True)

# Download files if not present
if not os.path.exists("models/risk_model.joblib"):
    download_from_github(MODEL_URL, "models/risk_model.joblib")
if not os.path.exists("models/encoder.joblib"):
    download_from_github(ENCODER_URL, "models/encoder.joblib")

# Load model + encoder
clf = joblib.load("models/risk_model.joblib")
ohe = joblib.load("models/encoder.joblib")

# === Kafka Consumer Setup ===
conf = {
    'bootstrap.servers': os.getenv("BOOTSTRAP_SERVERS"),
    'security.protocol': 'SASL_SSL',
    'sasl.mechanisms': 'PLAIN',
    'sasl.username': os.getenv("API_KEY"),
    'sasl.password': os.getenv("API_SECRET"),
    'group.id': 'crime-risk-worker-v2',
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

try:
    while True:
        print("⏳ Polling Kafka...")
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
            print(f"❌ Error processing message: {e}")

except KeyboardInterrupt:
    print("🛑 Gracefully shutting down...")

finally:
    print("🧹 Closing Kafka consumer")
    consumer.close()
