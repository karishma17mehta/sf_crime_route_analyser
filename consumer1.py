from confluent_kafka import Consumer, Producer
import os, json, joblib, requests
from dotenv import load_dotenv
from datetime import datetime
import pandas as pd

# Load environment variables
load_dotenv("py11.env")

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

os.makedirs("models", exist_ok=True)

if not os.path.exists("models/risk_model.joblib"):
    download_from_github(MODEL_URL, "models/risk_model.joblib")
if not os.path.exists("models/encoder.joblib"):
    download_from_github(ENCODER_URL, "models/encoder.joblib")

# Load model + encoder
clf = joblib.load("models/risk_model.joblib")
ohe = joblib.load("models/encoder.joblib")

# Common Kafka config
common_conf = {
    'bootstrap.servers': os.getenv("KAFKA_BOOTSTRAP"),
    'security.protocol': 'SASL_SSL',
    'sasl.mechanisms': 'PLAIN',
    'sasl.username': os.getenv("KAFKA_API_KEY"),
    'sasl.password': os.getenv("KAFKA_API_SECRET")
}
# Consumer for crime-events
consumer_conf = common_conf.copy()
consumer_conf.update({
    'group.id': 'crime-risk-worker-v3',
    'auto.offset.reset': 'earliest'
})
consumer = Consumer(consumer_conf)
consumer.subscribe(['crime-events'])

# Producer for predictions
producer = Producer(common_conf)

print("✅ Connected to Confluent Cloud. Waiting for crime-events...")

try:
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
            latitude = float(event.get("latitude", 37.7749))
            longitude = float(event.get("longitude", -122.4194))

            row = {
                "incident_hour": hour,
                "incident_minute": 0,
                "latitude": latitude,
                "longitude": longitude,
                "day_of_week_encoded": day
            }

            df_input = pd.DataFrame([row])
            day_encoded = ohe.transform(df_input[['day_of_week_encoded']])
            day_encoded_df = pd.DataFrame(day_encoded, columns=ohe.get_feature_names_out(['day_of_week_encoded']))
            X_input = pd.concat([
                df_input.drop(columns=['day_of_week_encoded']).reset_index(drop=True),
                day_encoded_df.reset_index(drop=True)
            ], axis=1)

            risk = float(clf.predict_proba(X_input)[0][1])
            prediction = {
                "from": event.get("address", "unknown"),
                "to": "unknown",
                "risk_score": round(risk, 2),
                "timestamp": datetime.utcnow().isoformat()
            }

            # Send prediction to new topic
            producer.produce("predicted-risk", value=json.dumps(prediction))
            producer.flush()
            print("📤 Prediction sent to topic: predicted-risk")

        except Exception as e:
            print(f"❌ Error processing message: {e}")

except KeyboardInterrupt:
    print("🛑 Gracefully shutting down...")

finally:
    print("🧹 Closing Kafka consumer")
    consumer.close()
