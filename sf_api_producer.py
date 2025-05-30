#!/usr/bin/env python
# sf_gov_producer.py

from confluent_kafka import Producer
import requests, json, os
from dotenv import load_dotenv
from datetime import datetime, timedelta

# Load Confluent Cloud credentials
load_dotenv()

conf = {
    'bootstrap.servers': os.getenv("BOOTSTRAP_SERVERS"),
    'security.protocol': 'SASL_SSL',
    'sasl.mechanisms': 'PLAIN',
    'sasl.username': os.getenv("API_KEY"),
    'sasl.password': os.getenv("API_SECRET")
}

producer = Producer(conf)

def delivery_report(err, msg):
    if err is not None:
        print(f"❌ Delivery failed: {err}")
    else:
        print(f"✅ Delivered to {msg.topic()} [{msg.partition()}] @ offset {msg.offset()}")

def fetch_sf_crime_data():
    # Format timestamp properly
    one_hour_ago = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    
    url = "https://data.sfgov.org/resource/wg3w-h783.json"
    params = {
        "$where": f"incident_datetime > '{one_hour_ago}'",
        "$limit": 20
    }

    print("📡 Fetching from SF API...")
    response = requests.get(url, params=params)

    if response.status_code != 200:
        print(f"❌ Error: {response.status_code} - {response.text}")
        return

    data = response.json()
    count = 0

    for event in data:
        event_json = json.dumps(event)
        producer.produce("crime-events", value=event_json, callback=delivery_report)
        count += 1

    producer.flush()
    print(f"✅ Sent {count} events.")

if __name__ == "__main__":
    fetch_sf_crime_data()
