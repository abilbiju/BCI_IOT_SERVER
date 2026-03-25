import os
import time
import threading
import socket
import http.server
import socketserver
import requests
from gtts import gTTS
import pychromecast
from flask import Flask, render_template_string, redirect, url_for, request
from dotenv import load_dotenv
import re

load_dotenv()

app = Flask(__name__)

# Load from .env
ACCESS_TOKEN = os.getenv("SINRIC_ACCESS_TOKEN")
DEVICE_1_ID = os.getenv("DEVICE_1_ID")
DEVICE_2_ID = os.getenv("DEVICE_2_ID")
DEVICE_1_NAME = os.getenv("DEVICE_1_NAME", "Device 1")
DEVICE_2_NAME = os.getenv("DEVICE_2_NAME", "Device 2")
CHROMECAST_NAME = os.getenv("CHROMECAST_NAME")

# Path to .env used for saving new devices and mappings
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")

# Map IDs to friendly names
DEVICE_NAMES = {
	DEVICE_1_ID: DEVICE_1_NAME,
	DEVICE_2_ID: DEVICE_2_NAME,
}

SINRIC_URL = "https://api.sinric.pro/api/v1/devices/{}/action"

# In-memory log
LOGS = []

_file_server_thread = None
FILE_SERVER_PORT = None

def add_log(message):
	timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
	LOGS.insert(0, f"[{timestamp}] {message}")
	if len(LOGS) > 50:
		LOGS.pop()

def get_local_ip():
	s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	try:
		s.connect(("8.8.8.8", 80))
		ip = s.getsockname()[0]
	except Exception:
		ip = "127.0.0.1"
	finally:
		s.close()
	return ip


def update_dotenv(changes: dict, env_path=ENV_PATH):
	"""Update or append key=value pairs in the .env file.
	"""
	# Read existing lines
	lines = []
	if os.path.exists(env_path):
		with open(env_path, "r") as f:
			lines = f.read().splitlines()

	updated_lines = []
	found = set()
	for line in lines:
		if not line or line.strip().startswith("#") or "=" not in line:
			updated_lines.append(line)
			continue
		k, v = line.split("=", 1)
		if k in changes:
			updated_lines.append(f"{k}={changes[k]}")
			found.add(k)
		else:
			updated_lines.append(line)

	# Append any new keys
	for k, v in changes.items():
		if k not in found:
			updated_lines.append(f"{k}={v}")

	# Write back
	with open(env_path, "w") as f:
		f.write("\n".join(updated_lines) + ("\n" if updated_lines and not updated_lines[-1].endswith("\n") else ""))


def get_devices():
	"""Return list of devices discovered from environment variables as dicts:
	Prefer `TOTAL_DEVICES` env var if present; otherwise fall back to scanning.
	Returns: [{index: int, id: str, name: str}, ...]
	"""
	devices = []
	total = os.getenv("TOTAL_DEVICES")
	try:
		if total is not None:
			t = int(total)
		else:
			t = 0
	except Exception:
		t = 0

	if t > 0:
		for idx in range(1, t + 1):
			did = os.getenv(f"DEVICE_{idx}_ID")
			if not did:
				continue
			name = os.getenv(f"DEVICE_{idx}_NAME", f"Device {idx}")
			devices.append({"index": idx, "id": did, "name": name})
		return devices

	# Fallback: discover by scanning env keys
	pattern = re.compile(r"DEVICE_(\d+)_ID")
	for k, v in os.environ.items():
		m = pattern.match(k)
		if m and v:
			idx = int(m.group(1))
			name = os.getenv(f"DEVICE_{idx}_NAME", f"Device {idx}")
			devices.append({"index": idx, "id": v, "name": name})
	devices.sort(key=lambda x: x["index"])
	return devices

def get_cast_friendly_name(cast_obj):
	# Try multiple attribute names across pychromecast versions
	try:
		if hasattr(cast_obj, 'device') and cast_obj.device:
			name = getattr(cast_obj.device, 'friendly_name', None)
			if name:
				return name
	except Exception:
		pass
	for attr in ('friendly_name', 'name'):
		if hasattr(cast_obj, attr):
			try:
				val = getattr(cast_obj, attr)
				if val:
					return val
			except Exception:
				pass
	# last resort
	try:
		return str(cast_obj)
	except Exception:
		return 'Unknown Chromecast'

def get_cast_host(cast_obj):
	# host may be available as attribute or inside cast_info
	host = getattr(cast_obj, 'host', None)
	if host:
		return host
	try:
		info = getattr(cast_obj, 'cast_info', None)
		if info and isinstance(info, dict):
			return info.get('host')
	except Exception:
		pass
	return 'unknown'

def start_file_server(port=8000):
	global _file_server_thread
	global FILE_SERVER_PORT
	if _file_server_thread and _file_server_thread.is_alive():
		return FILE_SERVER_PORT
	# Check if requested port is available; if not, pick an ephemeral free port
	test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	try:
		test_sock.bind(("", port))
		test_port = port
	except OSError:
		test_sock.close()
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.bind(("", 0))
		test_port = s.getsockname()[1]
		s.close()
	else:
		test_sock.close()

	FILE_SERVER_PORT = test_port

	class QuietHandler(http.server.SimpleHTTPRequestHandler):
		def log_message(self, format, *args):
			pass

	class ReuseThreadingTCPServer(socketserver.ThreadingTCPServer):
		allow_reuse_address = True

	def _serve():
		with ReuseThreadingTCPServer(("", FILE_SERVER_PORT), QuietHandler) as httpd:
			httpd.serve_forever()

	_file_server_thread = threading.Thread(target=_serve, daemon=True)
	_file_server_thread.start()
	add_log(f"Started file server on port {FILE_SERVER_PORT}")
	return FILE_SERVER_PORT

def make_tts(text, filename="speech.mp3"):
	tts = gTTS(text)
	tts.save(filename)

def get_audio_file(target: str, state: str) -> str:
	# prefer pre-generated files in ./audio, otherwise fallback to generated file
	out_dir = os.path.join(os.path.dirname(__file__), "audio")
	if target.lower().startswith("all"):
		base = "all_devices"
	else:
		base = "_".join(target.strip().lower().split())
	fname = f"{base}_{state.lower()}.mp3"
	path = os.path.join(out_dir, fname)
	if os.path.exists(path):
		return path
	# fallback: generate into audio dir
	os.makedirs(out_dir, exist_ok=True)
	make_tts(f"{target} turned {state}", path)
	return path

def play_on_chromecast(text):
	# legacy single-text version kept for compatibility; not used by callers
	try:
		# create temporary file and serve it
		path = os.path.join(os.path.dirname(__file__), "speech.mp3")
		make_tts(text, path)
		port = start_file_server(8000)
		local_ip = get_local_ip()
		rel = os.path.relpath(path, start=os.getcwd())
		rel_url = rel.replace(os.path.sep, '/')
		url = f"http://{local_ip}:{port}/{rel_url}"

		chromecasts, browser = pychromecast.get_chromecasts()
		cast = None
		if CHROMECAST_NAME:
			for c in chromecasts:
				if c.device.friendly_name == CHROMECAST_NAME:
					cast = c
					break
		if not cast and chromecasts:
			cast = chromecasts[0]

		if not cast:
			add_log("No Chromecast found to play TTS")
			return

		cast.wait()
		mc = cast.media_controller
		mc.play_media(url, "audio/mp3")
		mc.block_until_active()
		add_log(f"Played announcement on {get_cast_friendly_name(cast)}")
	except Exception as e:
		add_log(f"Chromecast TTS error: {e}")


def play_audio_file_on_chromecast(path: str):
	try:
		port = start_file_server(8000)
		local_ip = get_local_ip()
		rel = os.path.relpath(path, start=os.getcwd())
		rel_url = rel.replace(os.path.sep, '/')
		url = f"http://{local_ip}:{port}/{rel_url}"

		add_log(f"Playback URL: {url}")

		chromecasts, browser = pychromecast.get_chromecasts()
		add_log(f"Discovered {len(chromecasts)} chromecast(s)")
		for c in chromecasts:
			try:
				add_log(f" - {get_cast_friendly_name(c)} @ {get_cast_host(c)}")
			except Exception:
				pass

		cast = None
		if CHROMECAST_NAME:
			for c in chromecasts:
				if c.device.friendly_name == CHROMECAST_NAME:
					cast = c
					break
		if not cast and chromecasts:
			cast = chromecasts[0]

		if not cast:
			add_log("No Chromecast found to play TTS")
			return

		add_log(f"Using cast: {get_cast_friendly_name(cast)}")
		cast.wait()
		mc = cast.media_controller
		mc.play_media(url, "audio/mp3")
		mc.block_until_active()
		add_log(f"Played announcement on {cast.device.friendly_name}")
	except Exception as e:
		add_log(f"Chromecast playback error: {e}")

def send_all(state):
	# Send power state to each device without per-device announcements
	send_power(DEVICE_1_ID, state, announce=False)
	send_power(DEVICE_2_ID, state, announce=False)
	# Single announcement for all devices
	threading.Thread(target=play_on_chromecast, args=(f"All devices turned {state}",), daemon=True).start()

def send_power(device_id, state, announce=True):
	if not ACCESS_TOKEN or not device_id:
		add_log("Missing ACCESS_TOKEN or DEVICE_ID")
		return

	query = {
		"clientId": "android-app",
		"type": "request",
		"createdAt": int(time.time() * 1000),
		"action": "setPowerState",
		"value": f'{{"state":"{state}"}}'
	}

	headers = {
		"Authorization": f"Bearer {ACCESS_TOKEN}",
		"Content-Type": "application/x-www-form-urlencoded"
	}

	url = SINRIC_URL.format(device_id)

	try:
		r = requests.get(url, headers=headers, params=query, timeout=10)
		add_log(f"Device {device_id} → {state} | {r.status_code}")
	except Exception as e:
		add_log(f"Sinric request error for {device_id}: {e}")

	# Announce on Chromecast using friendly name when requested
	if announce:
		device_name = DEVICE_NAMES.get(device_id, device_id)
		audio_path = get_audio_file(device_name, state)
		threading.Thread(target=play_audio_file_on_chromecast, args=(audio_path,), daemon=True).start()


@app.route("/")
def index():
	devices = get_devices()
	# build mapping friendly labels by env index
	return render_template_string("""
	<html>
	<head>
		<title>Sinric Device Control</title>
		<meta name="viewport" content="width=device-width,initial-scale=1" />
		<style>
			:root{--bg:#f3f6f9;--card:#ffffff;--accent:#2b8cff;--danger:#ff6b6b;--muted:#6b7280}
			body{font-family:Inter,Arial,Helvetica,sans-serif;background:var(--bg);margin:0;padding:24px;}
			.container{max-width:1000px;margin:0 auto}
			head{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}
			h1{font-size:20px;margin:0}
			.grid{display:grid;grid-template-columns:1fr 320px;gap:18px}
			.panel{background:var(--card);padding:16px;border-radius:10px;box-shadow:0 1px 4px rgba(16,24,40,0.04)}
			.devices{display:flex;flex-direction:column;gap:12px}
			.card{border:1px solid #e6eefc;padding:12px;border-radius:8px}
			.row{display:flex;align-items:center;gap:8px}
			input[type=text]{flex:1;padding:8px;border:1px solid #e6eefc;border-radius:6px}
			.btn{padding:8px 12px;border:0;border-radius:6px;color:white;cursor:pointer}
			.btn.on{background:var(--accent)}
			.btn.off{background:var(--danger)}
			.small{font-size:13px;color:var(--muted)}
			.log{background:#0f1724;color:#e6f0ff;padding:12px;margin-top:6px;height:420px;overflow:auto;font-family:monospace;font-size:13px}
			.footer{margin-top:12px;text-align:right}
			@media(max-width:800px){.grid{grid-template-columns:1fr}}
		</style>
	</head>
	<body>
		<div class="container">
			<header>
				<h1>Sinric Device Control</h1>
			</header>
			<div class="grid">
				<div class="panel devices">
					{% for d in devices %}
						<div class="card">
							<div class="row"><strong>Device {{ d.index }}</strong><span class="small">({{ d.name }})</span></div>
							<div class="row" style="margin-top:8px">
								<a href="/device{{ d.index }}/on"><button class="btn on">ON</button></a>
								<a href="/device{{ d.index }}/off"><button class="btn off">OFF</button></a>
							</div>
							<!-- Actions dropdown to avoid accidental touches -->
							<div style="margin-top:8px;display:flex;gap:8px;justify-content:flex-end;align-items:flex-start;position:relative">
								<form id="update-form-{{ d.index }}" action="/update_device" method="post" style="flex:1">
									<input type="hidden" name="index" value="{{ d.index }}" />
									<!-- Edit panel is hidden by default to prevent accidental edits -->
									<div id="edit-panel-{{ d.index }}" style="display:none;flex-direction:column;gap:8px">
										<div style="display:flex;gap:8px">
											<input type="text" name="device_id" value="{{ d.id }}" placeholder="Device ID" style="flex:1;padding:8px;border:1px solid #e6eefc;border-radius:6px" />
											<input type="text" name="device_name" value="{{ d.name }}" placeholder="Friendly name" style="flex:1;padding:8px;border:1px solid #e6eefc;border-radius:6px" />
										</div>
										<div style="display:flex;gap:8px;justify-content:flex-end">
											<button class="btn on" type="submit">Save</button>
											<button class="btn" type="button" onclick="toggleEdit({{ d.index }})">Cancel</button>
										</div>
									</div>
								</form>
								<!-- Actions menu -->
								<div style="position:relative">
									<button class="btn" type="button" onclick="toggleMenu({{ d.index }})">Actions ▾</button>
									<div id="menu-{{ d.index }}" style="display:none;position:absolute;right:0;background:var(--card);border:1px solid #e6eefc;padding:8px;border-radius:6px;box-shadow:0 4px 10px rgba(2,6,23,0.08);z-index:50">
										<div style="margin-bottom:6px"><button class="btn" type="button" onclick="toggleEdit({{ d.index }});toggleMenu({{ d.index }})">Edit details</button></div>
										<div>
											<button class="btn off" type="button" onclick="confirmRemove({{ d.index }}, '{{ d.name }}')">Remove</button>
										</div>
									</div>
								</div>
							</div>
						</div>
					{% endfor %}
					<div class="card">
						<div class="row"><strong>All Devices</strong></div>
						<div class="row" style="margin-top:8px">
							<a href="/all/on"><button class="btn on">ALL ON</button></a>
							<a href="/all/off"><button class="btn off">ALL OFF</button></a>
						</div>
					</div>
                    
					<div class="card">
						<div class="row"><strong>Add Device</strong></div>
						<form action="/add_device" method="post" style="margin-top:8px">
							<div class="row" style="margin-bottom:8px">
								<input type="text" name="device_id" placeholder="Device ID" />
							</div>
							<div class="row" style="margin-bottom:8px">
								<input type="text" name="device_name" placeholder="Friendly name (optional)" />
							</div>
							<div class="row" style="justify-content:flex-end">
								<button class="btn on" type="submit">Add</button>
							</div>
						</form>
					</div>

					<!-- Logs moved here so they appear below the device list -->
					<div class="panel" style="margin-top:12px">
						<h3 style="margin-top:0">Logs</h3>
						<div class="log">
							{% for log in logs %}
								{{ log }}
							{% endfor %}
						</div>
						<div class="footer small">Local IP: {{ local_ip }}</div>
					</div>
				</div>
			</div>
		</div>

			</div>
			<script>
			function toggleMenu(idx){
			  var m=document.getElementById('menu-'+idx);
			  if(!m) return;
			  m.style.display = (m.style.display==='block') ? 'none' : 'block';
			}
			function toggleEdit(idx){
			  var p=document.getElementById('edit-panel-'+idx);
			  if(!p) return;
			  // use flex when visible to keep layout
			  p.style.display = (p.style.display==='flex' || p.style.display==='block') ? 'none' : 'flex';
			}
			function confirmRemove(idx, name){
			  if(!confirm('Remove device '+name+'? This cannot be undone.')) return;
			  var form = document.createElement('form');
			  form.method = 'post';
			  form.action = '/remove_device/' + idx;
			  document.body.appendChild(form);
			  form.submit();
			}
			// close open menus when clicking outside
			document.addEventListener('click', function(e){
			  var menus = document.querySelectorAll('[id^="menu-"]');
			  menus.forEach(function(menu){
				var btn = menu.previousElementSibling;
				if(!menu.contains(e.target) && !(btn && btn.contains(e.target))){
				  menu.style.display = 'none';
				}
			  });
			});
			</script>
	</body>
	</html>
	""", logs=LOGS, device1_name=DEVICE_1_NAME, device2_name=DEVICE_2_NAME, local_ip=get_local_ip(), devices=devices)

    


@app.route("/device1/<state>")
def device1(state):
	send_power(DEVICE_1_ID, state.capitalize())
	return redirect(url_for('index'))


@app.route("/device2/<state>")
def device2(state):
	send_power(DEVICE_2_ID, state.capitalize())
	return redirect(url_for('index'))


@app.route('/device/<int:idx>/<state>')
def device_by_index(idx, state):
	# Look up device id by index and send power
	dev_id = os.getenv(f"DEVICE_{idx}_ID")
	if not dev_id:
		add_log(f"Device {idx} not found")
		return redirect(url_for('index'))
	send_power(dev_id, state.capitalize())
	return redirect(url_for('index'))


@app.route('/device<int:idx>/<state>')
def device_by_compact(idx, state):
	# Support URLs like /device1/on
	dev_id = os.getenv(f"DEVICE_{idx}_ID")
	if not dev_id:
		add_log(f"Device {idx} not found")
		return redirect(url_for('index'))
	send_power(dev_id, state.capitalize())
	return redirect(url_for('index'))


@app.route('/update_device', methods=['POST'])
def update_device():
	try:
		idx = int(request.form.get('index'))
	except Exception:
		add_log('Update device failed: invalid index')
		return redirect(url_for('index'))
	new_id = request.form.get('device_id', '').strip()
	new_name = request.form.get('device_name', '').strip() or f"Device {idx}"

	old_id = os.getenv(f"DEVICE_{idx}_ID")
	changes = {
		f"DEVICE_{idx}_ID": new_id,
		f"DEVICE_{idx}_NAME": new_name,
	}
	try:
		update_dotenv(changes)
		os.environ.update(changes)
		# update DEVICE_NAMES mapping
		if old_id and old_id in DEVICE_NAMES:
			DEVICE_NAMES.pop(old_id, None)
		DEVICE_NAMES[new_id] = new_name
		add_log(f"Updated device {idx}: {new_name} ({new_id})")
	except Exception as e:
		add_log(f"Failed updating device {idx}: {e}")
	return redirect(url_for('index'))


@app.route('/remove_device/<int:idx>', methods=['POST'])
def remove_device(idx):
	total = 0
	try:
		total = int(os.getenv('TOTAL_DEVICES') or '0')
	except Exception:
		total = 0
	if total == 0 or idx < 1 or idx > total:
		add_log(f"Remove device failed: invalid index {idx}")
		return redirect(url_for('index'))

	changes = {}
	# shift subsequent devices down
	for i in range(idx, total):
		next_id = os.getenv(f"DEVICE_{i+1}_ID") or ""
		next_name = os.getenv(f"DEVICE_{i+1}_NAME") or ""
		changes[f"DEVICE_{i}_ID"] = next_id
		changes[f"DEVICE_{i}_NAME"] = next_name

	# clear last slot
	changes[f"DEVICE_{total}_ID"] = ""
	changes[f"DEVICE_{total}_NAME"] = ""
	changes['TOTAL_DEVICES'] = str(total - 1)

	try:
		update_dotenv(changes)
		os.environ.update(changes)
		add_log(f"Removed device {idx}")
	except Exception as e:
		add_log(f"Failed removing device {idx}: {e}")
	return redirect(url_for('index'))


@app.route("/all/on")
def all_on():
	send_all("On")
	return redirect(url_for('index'))


@app.route("/all/off")
def all_off():
	send_all("Off")
	return redirect(url_for('index'))


@app.route("/add_device", methods=["POST"])
def add_device():
	device_id = request.form.get("device_id", "").strip()
	device_name = request.form.get("device_name", "").strip()
	if not device_id:
		add_log("Add device failed: missing id")
		return redirect(url_for('index'))
	devices = get_devices()
	next_idx = 1
	if devices:
		next_idx = max(d['index'] for d in devices) + 1

	# If TOTAL_DEVICES exists and is less than next_idx, we'll set it accordingly
	total = os.getenv("TOTAL_DEVICES")
	try:
		total_i = int(total) if total is not None else 0
	except Exception:
		total_i = 0

	changes = {
		f"DEVICE_{next_idx}_ID": device_id,
		f"DEVICE_{next_idx}_NAME": device_name or f"Device {next_idx}",
		"TOTAL_DEVICES": str(max(total_i, next_idx))
	}
	try:
		update_dotenv(changes)
		os.environ.update(changes)
		# update in-memory map as well
		DEVICE_NAMES[device_id] = changes[f"DEVICE_{next_idx}_NAME"]
		add_log(f"Added device {next_idx}: {changes[f'DEVICE_{next_idx}_NAME']} ({device_id})")
	except Exception as e:
		add_log(f"Failed adding device: {e}")
	return redirect(url_for('index'))


if __name__ == "__main__":
	start_file_server(8000)
	local_ip = get_local_ip()
	add_log(f"Local IP: {local_ip}")
	app.run(host="0.0.0.0", port=5200, debug=True)