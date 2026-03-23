import requests
import json

url = "https://homegraph.googleapis.com/v1/devices:requestSync"

headers = {
    "Authorization": "Bearer ACCESS_TOKEN",
    "Content-Type": "application/json"
}

data = {
    "agentUserId": "user123"
}

requests.post(url, headers=headers, json=data)