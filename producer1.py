# producer.py
import requests
import json
from kafka import KafkaProducer
from datetime import datetime, timedelta
import time

# Kafka setup
producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

# API endpoint
SF_CRIME_API = "https://data.sfgov.org/resource/wg3w-h783.json"

def fetch_recent_crimes(minutes_ago=10):
    """Fetch crimes in the last `minutes_ago` minutes from SF API."""
    since_time = (datetime.utcnow() - timedelta(minutes=minutes_ago)).isoformat()
    query = {
        "$where": f"incident_datetime > '{since_time}'",
        "$limit": 1000,
        "$order": "incident_datetime DESC"
    }
    response = requests.get(SF_CRIME_API, params=query)
    if response.status_code == 200:
        return response.json()
    else:
        print("Error fetching data:", response.status_code)
        return []

def stream_to_kafka():
    while True:
        crimes = fetch_recent_crimes()
        for crime in crimes:
            producer.send('crime_topic', crime)
        print(f"Streamed {len(crimes)} crimes at {datetime.now()}")
        time.sleep(60)  # Fetch every 1 minute

if __name__ == "__main__":
    stream_to_kafka()
