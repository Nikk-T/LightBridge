"""
LightBridge Web Interface — bridge_service_GUI.py — Dashboard app (port 5000)
Serves the unit control dashboard and proxies commands to bridge_service via WebSocket.

Config files (both in same directory as this script):
  maps.yaml     — unit_channel_map, floor_channel_map
  settings.yaml — status_colour
"""

from flask import Flask, render_template, jsonify, request
import asyncio, json, websockets, yaml
from pathlib import Path

app = Flask(__name__)

WS_URL        = "ws://localhost:8765"
BASE_DIR      = Path(__file__).resolve().parent
MAPS_PATH     = BASE_DIR / "config" / "maps.yaml"
SETTINGS_PATH = BASE_DIR / "config" / "settings.yaml"

# ── Config ───────────────────────────────────────────────────
def load_maps() -> dict:
    with open(MAPS_PATH) as f:
        return yaml.safe_load(f) or {}

def load_settings() -> dict:
    with open(SETTINGS_PATH) as f:
        return yaml.safe_load(f) or {}

# ── WebSocket proxy ──────────────────────────────────────────
async def ws_send(payload: dict) -> dict:
    try:
        async with websockets.connect(WS_URL, open_timeout=3) as ws:
            await ws.send(json.dumps(payload))
            reply = await asyncio.wait_for(ws.recv(), timeout=3)
            return json.loads(reply)
    except Exception as e:
        return {"status": "error", "message": str(e)}

def send_command(payload: dict) -> dict:
    return asyncio.run(ws_send(payload))

# ── Routes ───────────────────────────────────────────────────
@app.route("/")
def index():
    maps     = load_maps()
    settings = load_settings()
    units    = list(maps.get("unit_channel_map", {}).keys())
    floors   = sorted(maps.get("floor_channel_map", {}).keys())
    statuses = list(settings.get("status_colour", {}).keys())
    return render_template("index.html", units=units, floors=floors, statuses=statuses)

@app.route("/api/ping")
def ping():
    return jsonify(send_command({"command": "ping", "payload": {}}))

@app.route("/api/unit_status", methods=["POST"])
def unit_status():
    data = request.json
    return jsonify(send_command({
        "command": "unit_status",
        "payload": {"unit_id": data["unit_id"], "status": data["status"]}
    }))

@app.route("/api/sync_all", methods=["POST"])
def sync_all():
    data = request.json
    return jsonify(send_command({
        "command": "sync_all",
        "payload": {"units": data.get("units", {})}
    }))

@app.route("/api/floor_highlight", methods=["POST"])
def floor_highlight():
    data = request.json
    return jsonify(send_command({
        "command": "floor_highlight",
        "payload": {"floor": data["floor"], "colour": data.get("colour", [100, 150, 255])}
    }))

@app.route("/api/scene", methods=["POST"])
def set_scene():
    data = request.json
    return jsonify(send_command({
        "command": "set_scene",
        "payload": {"scene": data["scene"]}
    }))

@app.route("/api/blackout", methods=["POST"])
def blackout():
    return jsonify(send_command({"command": "blackout", "payload": {}}))

@app.route("/api/set_colour", methods=["POST"])
def set_colour():
    data = request.json
    return jsonify(send_command({
        "command": "set_colour",
        "payload": {"channel": data["channel"], "r": data["r"], "g": data["g"], "b": data["b"]}
    }))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
