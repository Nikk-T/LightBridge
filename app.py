"""
LightBridge Web Interface — Flask app
Serves the dashboard and proxies commands to the WebSocket bridge.
"""

from flask import Flask, render_template, jsonify, request
import asyncio, json, websockets, yaml
from pathlib import Path

app = Flask(__name__)

WS_URL = "ws://localhost:8765"
CONFIG_PATH = Path(__file__).resolve().parent / "config/maps.yaml"

# ── Load config ─────────────────────────────────────────────
def load_config():
    with open(CONFIG_PATH) as f:
        cfg = yaml.safe_load(f)
    return cfg

# ── Send a command to bridge_service via WebSocket ──────────
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
    cfg = load_config()
    units = list(cfg.get("unit_channel_map", {}).keys())
    floors = sorted(cfg.get("floor_channel_map", {}).keys())
    statuses = list(cfg.get("status_colour", {}).keys())
    return render_template("index.html", units=units, floors=floors, statuses=statuses)

@app.route("/api/ping")
def ping():
    result = send_command({"command": "ping", "payload": {}})
    return jsonify(result)

@app.route("/api/unit_status", methods=["POST"])
def unit_status():
    data = request.json
    result = send_command({
        "command": "unit_status",
        "payload": {"unit_id": data["unit_id"], "status": data["status"]}
    })
    return jsonify(result)

@app.route("/api/sync_all", methods=["POST"])
def sync_all():
    data = request.json
    result = send_command({
        "command": "sync_all",
        "payload": {"units": data.get("units", {})}
    })
    return jsonify(result)

@app.route("/api/floor_highlight", methods=["POST"])
def floor_highlight():
    data = request.json
    result = send_command({
        "command": "floor_highlight",
        "payload": {"floor": data["floor"], "colour": data.get("colour", [100, 150, 255])}
    })
    return jsonify(result)

@app.route("/api/scene", methods=["POST"])
def set_scene():
    data = request.json
    result = send_command({
        "command": "set_scene",
        "payload": {"scene": data["scene"]}
    })
    return jsonify(result)

@app.route("/api/blackout", methods=["POST"])
def blackout():
    result = send_command({"command": "blackout", "payload": {}})
    return jsonify(result)

@app.route("/api/set_colour", methods=["POST"])
def set_colour():
    data = request.json
    result = send_command({
        "command": "set_colour",
        "payload": {"channel": data["channel"], "r": data["r"], "g": data["g"], "b": data["b"]}
    })
    return jsonify(result)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)