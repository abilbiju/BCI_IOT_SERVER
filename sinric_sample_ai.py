"""SinricPro — Web UI controller

Replaced the original command-line interface with a small Flask web app that:
- serves a single-page UI to control devices
- shows recent logs and last command status
- exposes simple JSON APIs for integration or automation

Run:
  pip install flask requests
  python3 sinric_sample_ai.py          # opens web UI on http://127.0.0.1:5000
  python3 sinric_sample_ai.py --cli    # run original CLI

"""

import json
import time
import threading
from datetime import datetime
from collections import deque

# SinricPro credentials - replace with your actual values or set via environment
APP_KEY = "your_app_key_here"
APP_SECRET = "your_app_secret_here"

# Device IDs - replace with your actual device IDs from SinricPro portal
DEVICES = {
    "device1": "698204b17e0883bc2697da71",
    "device2": "698202492c0599192aec6b43"

}

# In-memory log buffer (thread-safe)
LOG_CAPACITY = 1000
_logs = deque(maxlen=LOG_CAPACITY)
_log_lock = threading.Lock()


def _add_log(level, message):
    entry = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "level": level,
        "message": message
    }
    with _log_lock:
        _logs.append(entry)
    # keep console output for backward compatibility
    print(f"[{entry['ts']}] [{level}] {message}")


def get_logs(limit=200):
    with _log_lock:
        return list(_logs)[-limit:]


# --- Existing device-control logic (kept and extended) ---
import requests


def send_power_command(device_name, power_state):
    """Send power state command to a SinricPro device.

    Returns True on success, False on failure.  Also writes to the in-memory log.
    """
    if device_name not in DEVICES:
        _add_log("ERROR", f"Device '{device_name}' not found in device list")
        return False

    device_id = DEVICES[device_name]
    url = f"https://api.sinric.pro/v1/devices/{device_id}/events"
    headers = {
        "Authorization": f"Bearer {APP_KEY}:{APP_SECRET}",
        "Content-Type": "application/json"
    }
    payload = {
        "type": "event",
        "deviceId": device_id,
        "action": "setPowerState",
        "value": {"state": "ON" if power_state else "OFF"},
        "cause": {"type": "PHYSICAL_INTERACTION"},
        "createdAt": int(time.time())
    }

    _add_log("INFO", f"Sending {('ON' if power_state else 'OFF')} to {device_name} (id={device_id})")

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            _add_log("SUCCESS", f"{device_name} -> {('ON' if power_state else 'OFF')} (200)")
            return True
        else:
            _add_log("ERROR", f"Failed to send command to {device_name}: {response.status_code} - {response.text[:200]}")
            return False
    except Exception as e:
        _add_log("ERROR", f"Exception sending command to {device_name}: {e}")
        return False


# Keep the CLI helpers for backward compatibility

def interactive_control():
    print("=== SinricPro Device Controller ===")
    print("Available devices:", ", ".join(DEVICES.keys()))
    print("Commands: [device_name] [on/off] or 'quit' to exit")
    print("-" * 40)

    while True:
        try:
            user_input = input("Enter command: ").strip().lower()
            if user_input in ("quit", "exit"):
                print("Goodbye!")
                break

            parts = user_input.split()
            if len(parts) != 2:
                print("Invalid command format. Use: [device_name] [on/off]")
                continue

            device_name, state_command = parts[0], parts[1]
            if state_command not in ("on", "off"):
                print("Invalid state. Use 'on' or 'off'")
                continue

            power_state = (state_command == "on")
            send_power_command(device_name, power_state)

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")


def quick_commands():
    send_power_command("device1", True)
    time.sleep(2)
    send_power_command("device2", True)
    time.sleep(2)
    send_power_command("device1", False)
    time.sleep(2)
    send_power_command("device2", False)


# --- Web UI / API ---

def create_app():
    try:
        from flask import Flask, render_template_string, request, jsonify, abort
    except Exception:
        raise

    app = Flask(__name__)

    PAGE_HTML = r"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <title>SinricPro — Web Controller</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
      <style>
        body { padding: 1.5rem; }
        .log-area { height: 360px; overflow: auto; background:#0f1724; color:#e6edf3; padding:0.75rem; border-radius:6px; font-family:monospace; font-size:13px }
        .log-level-ERROR { color:#ffb4b4 }
        .log-level-SUCCESS { color:#b7f5c4 }
        .log-level-INFO { color:#9fc5ff }
      </style>
    </head>
    <body>
    <div class="container">
      <div class="d-flex justify-content-between align-items-center mb-3">
        <h3>SinricPro — Web Controller</h3>
        <div>
          <button id="refreshBtn" class="btn btn-sm btn-outline-secondary">Refresh</button>
          <button id="quickTestBtn" class="btn btn-sm btn-outline-primary">Quick test</button>
        </div>
      </div>

      <div class="row">
        <div class="col-md-6 mb-3">
          <div class="card">
            <div class="card-body">
              <h5 class="card-title">Devices</h5>
              <div id="devices" class="d-grid gap-2"></div>
            </div>
          </div>
        </div>

        <div class="col-md-6 mb-3">
          <div class="card">
            <div class="card-body">
              <h5 class="card-title">Logs</h5>
              <div id="logArea" class="log-area"></div>
            </div>
          </div>
        </div>
      </div>

      <footer class="text-muted small mt-3">Open <code>http://localhost:5000</code> to use the UI. Keys are not exposed in the browser.</footer>
    </div>

    <script>
      async function fetchDevices() {
        const res = await fetch('/api/devices');
        return res.json();
      }

      function makeDeviceCard(name, id) {
        const wrapper = document.createElement('div');
        wrapper.className = 'd-flex align-items-center justify-content-between p-2 border rounded';
        wrapper.innerHTML = `
          <div>
            <div class="fw-bold">${name}</div>
            <div class="text-muted small">id: ${id}</div>
          </div>
          <div class="btn-group" role="group">
            <button class="btn btn-success btn-sm" data-action="on">ON</button>
            <button class="btn btn-danger btn-sm" data-action="off">OFF</button>
          </div>
        `;
        wrapper.querySelectorAll('button').forEach(b => {
          b.addEventListener('click', async () => {
            const state = b.getAttribute('data-action');
            b.disabled = true;
            try {
              await sendCommand(name, state);
            } finally {
              b.disabled = false;
            }
          });
        });
        return wrapper;
      }

      async function renderDevices() {
        const data = await fetchDevices();
        const box = document.getElementById('devices');
        box.innerHTML = '';
        for (const [name, id] of Object.entries(data.devices)) {
          box.appendChild(makeDeviceCard(name, id));
        }
      }

      async function sendCommand(device, state) {
        const res = await fetch(`/api/device/${encodeURIComponent(device)}/power`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({state})
        });
        const body = await res.json();
        if (!res.ok) throw new Error(body.error || 'request failed');
        return body;
      }

      async function fetchLogs() {
        const res = await fetch('/api/logs');
        const data = await res.json();
        const area = document.getElementById('logArea');
        area.innerHTML = '';
        data.logs.reverse().forEach(l => {
          const div = document.createElement('div');
          div.className = 'log-' + l.level;
          div.innerHTML = `<span class="text-muted">[${l.ts}]</span> <span class="fw-bold log-level-${l.level}">${l.level}</span> - ${l.message}`;
          area.appendChild(div);
        });
      }

      document.getElementById('refreshBtn').addEventListener('click', async () => {
        await renderDevices();
        await fetchLogs();
      });

      document.getElementById('quickTestBtn').addEventListener('click', async () => {
        const b = document.getElementById('quickTestBtn');
        b.disabled = true;
        try {
          await fetch('/api/quick_test', {method: 'POST'});
        } catch (e) { console.error(e) }
        b.disabled = false;
      });

      // initial load + polling
      renderDevices();
      fetchLogs();
      setInterval(fetchLogs, 1500);
    </script>
    </body>
    </html>
    """

    @app.route('/')
    def index():
        return render_template_string(PAGE_HTML)

    @app.route('/api/devices')
    def api_devices():
        return jsonify({"devices": DEVICES})

    @app.route('/api/device/<device_name>/power', methods=['POST'])
    def api_device_power(device_name):
        if device_name not in DEVICES:
            return jsonify({"error": "device not found"}), 404
        data = request.get_json(force=True)
        state = data.get('state') if isinstance(data, dict) else None
        if state not in ('on', 'off'):
            return jsonify({"error": "state must be 'on' or 'off'"}), 400
        success = send_power_command(device_name, state == 'on')
        return jsonify({"ok": success, "device": device_name, "state": state}), (200 if success else 500)

    @app.route('/api/logs')
    def api_logs():
        return jsonify({"logs": get_logs(200)})

    @app.route('/api/quick_test', methods=['POST'])
    def api_quick_test():
        threading.Thread(target=quick_commands, daemon=True).start()
        return jsonify({"ok": True, "message": "quick test started"}), 202

    return app


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--cli', action='store_true', help='Run original CLI instead of web UI')
    parser.add_argument('--host', default='127.0.0.1', help='Host to bind the web UI to')
    parser.add_argument('--port', default=5000, type=int, help='Port for the web UI')
    args = parser.parse_args()

    if args.cli:
        # keep backward-compatible CLI
        try:
            import requests  # ensure dependency available
        except ImportError:
            print('Please install requests package: pip install requests')
            raise

        print("Select mode:")
        print("1. Interactive mode (command-line control)")
        print("2. Quick test (predefined commands)")
        choice = input("Enter choice (1 or 2): ").strip()
        if choice == '1':
            interactive_control()
        elif choice == '2':
            quick_commands()
        else:
            print('Invalid choice. Starting interactive mode...')
            interactive_control()
    else:
        try:
            app = create_app()
        except Exception:
            print('Flask is required for the web UI. Install it with: pip install flask')
            raise
        print(f"Starting web UI on http://{args.host}:{args.port} — press Ctrl-C to stop")
        app.run(host=args.host, port=args.port, debug=True)
