import os
import requests
import time
from generate_sample_data import generate_trade_confirmation

# Get Lambda URL from environment variable
lambda_url = os.environ["LAMBDA_URL"]

# Prepare request body
body = {"template_id": "trade_confirmation.typ", "data": generate_trade_confirmation()}

# Send POST request and measure time
start_time = time.time()
response = requests.post(lambda_url, json=body)
end_time = time.time()

# Extract job_id and calculate duration
response_json = response.json()
job_id = response_json["job_id"]
duration_ms = (end_time - start_time) * 1000

print(f"Job ID: {job_id}")
print(f"Request took {duration_ms:.2f} ms")
