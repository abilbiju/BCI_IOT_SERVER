import os
from gtts import gTTS
from dotenv import load_dotenv

load_dotenv()

DEVICE_1_NAME = os.getenv("DEVICE_1_NAME", "Device 1")
DEVICE_2_NAME = os.getenv("DEVICE_2_NAME", "Device 2")

OUT_DIR = os.path.join(os.path.dirname(__file__), "audio")
os.makedirs(OUT_DIR, exist_ok=True)

def slug(s: str) -> str:
    return "_".join(s.strip().lower().split())

def build_path(target: str, state: str) -> str:
    name = "all_devices" if target.lower().startswith("all") else slug(target)
    fname = f"{name}_{state.lower()}.mp3"
    return os.path.join(OUT_DIR, fname)

def make(text: str, path: str):
    if os.path.exists(path):
        print(f"Exists: {path}")
        return
    tts = gTTS(text)
    tts.save(path)
    print(f"Saved: {path}")

def generate_all():
    pairs = [
        (DEVICE_1_NAME, "On"),
        (DEVICE_1_NAME, "Off"),
        (DEVICE_2_NAME, "On"),
        (DEVICE_2_NAME, "Off"),
        ("All devices", "On"),
        ("All devices", "Off"),
    ]
    for target, state in pairs:
        text = f"{target} turned {state}"
        path = build_path(target, state)
        make(text, path)

if __name__ == "__main__":
    generate_all()
    print("Audio generation complete. Files in:", OUT_DIR)
