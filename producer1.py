import requests
import json
from confluent_kafka import Producer
from datetime import datetime, timedelta
import time
import certifi
import os
from dotenv import load_dotenv

load_dotenv("py.env")

conf = {
    'bootstrap.servers': os.getenv('KAFKA_BOOTSTRAP'),
    'security.protocol': 'SASL_SSL',
    'sasl.mechanisms': 'PLAIN',
    'sasl.username': os.getenv('KAFKA_API_KEY'),
    'sasl.password': os.getenv('KAFKA_API_SECRET'),
    'ssl.ca.location': certifi.where()
}
producer = Producer(conf)

# SF Crime API
SF_CRIME_API = "https://data.sfgov.org/resource/wg3w-h783.json"

def fetch_recent_crimes(minutes_ago=10):
    since_time = (datetime.utcnow() - timedelta(minutes=minutes_ago)).isoformat()
    query = {
        "$where": f"incident_datetime > '{since_time}'",
        "$limit": 1000,
        "$order": "incident_datetime DESC"
    }
    response = requests.get(SF_CRIME_API, params=query)
    return response.json() if response.status_code == 200 else []

def stream_to_kafka():
    while True:
        crimes = fetch_recent_crimes()
        for crime in crimes:
            producer.produce('crime-events', value=json.dumps(crime))
        producer.flush()
        print(f"✅ Streamed {len(crimes)} crimes at {datetime.now()}")
        time.sleep(60)

if __name__ == "__main__":
    stream_to_kafka()
