# Sinric Web Controller

Simple Node.js + Express web app to control Sinric devices from a browser.

Setup

1. Install dependencies

```bash
npm install
```

2. Create a `.env` file in the project root (you can copy `.env.example`) and set your Sinric token:

```
SINRIC_TOKEN=your_token_here
PORT=3000
```

Run

```bash
npm start
```

Open http://localhost:3000, enter your two device IDs and use the buttons to send On/Off commands.

Notes

- The server forwards requests to `https://api.sinric.pro/api/v1/devices/:deviceId/action`. The token must be a valid Sinric API token.
- If you want HTTPS or remote access, run behind a reverse proxy or deploy to a host and enable TLS.
