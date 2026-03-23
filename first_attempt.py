import requests
import time

DEVICE_ID = "698202492c0599192aec6b43"

# ✅ Access token you got from /api/v1/auth
ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjY5Nzc2OTIyMmMwNTk5MTkyYWU3M2FjYyIsInRpZCI6IjY5OWJkZmU1MTdiMzJjMDk0MWMzNmU2MiIsImlhdCI6MTc3MTgyMzA3NywiZXhwIjoxNzcyNDI3ODc3fQ.I6X3nLoeOy5kM-3j0gVB8H3HiVExUCBqiR0lpP6k2sg"

query = {
    "clientId": "android-app",
    "type": "request",
    "createdAt": int(time.time() * 1000),
    "action": "setPowerState",
    "value": '{"state":"On"}'   # change to Off if needed
}

url = f"https://api.sinric.pro/api/v1/devices/{DEVICE_ID}/action"

headers = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/x-www-form-urlencoded"
}

response = requests.get(url, headers=headers, params=query)

print("Status:", response.status_code)
print("Response:", response.text)