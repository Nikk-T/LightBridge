"""
LightBridge Import Tool — Standalone app (port 5001)
Drag-and-drop XLS/XLSX/CSV → maps.yaml converter.
Runs independently; does not require bridge_service or the main dashboard.

Config files (one level up, shared with main app):
  maps.yaml     — unit_channel_map, floor_channel_map  (written by this app)
  settings.yaml — status_colour                         (read-only here)
"""

from flask import Flask, render_template, jsonify, request
import yaml, shutil
from pathlib import Path
from datetime import datetime

app = Flask(__name__, template_folder="templates")

BASE_DIR      = Path(__file__).resolve().parent.parent
MAPS_PATH     = BASE_DIR / "config" / "maps.yaml"
SETTINGS_PATH = BASE_DIR / "config" / "settings.yaml"

# ── Config helpers ───────────────────────────────────────────
def load_maps() -> dict:
    if not MAPS_PATH.exists():
        return {}
    with open(MAPS_PATH) as f:
        return yaml.safe_load(f) or {}

def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        return {}
    with open(SETTINGS_PATH) as f:
        return yaml.safe_load(f) or {}

# ── Routes ───────────────────────────────────────────────────
@app.route("/")
def index():
    maps     = load_maps()
    settings = load_settings()
    maps_yaml     = yaml.dump(maps,     default_flow_style=False, sort_keys=False) if maps     else ""
    settings_yaml = yaml.dump(settings, default_flow_style=False, sort_keys=False) if settings else ""
    return render_template("import.html",
                           current_maps_yaml=maps_yaml,
                           current_settings_yaml=settings_yaml)

@app.route("/api/current_maps")
def current_maps():
    try:
        return jsonify({"status": "ok", "config": load_maps()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route("/api/save_maps", methods=["POST"])
def save_maps():
    try:
        new_cfg = request.json.get("config", {})

        if not isinstance(new_cfg.get("unit_channel_map", {}), dict):
            return jsonify({"status": "error", "message": "unit_channel_map must be a dict"})
        if not isinstance(new_cfg.get("floor_channel_map", {}), dict):
            return jsonify({"status": "error", "message": "floor_channel_map must be a dict"})

        # Backup before overwriting
        if MAPS_PATH.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copy(MAPS_PATH, MAPS_PATH.parent / f"maps_backup_{ts}.yaml")

        MAPS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(MAPS_PATH, "w") as f:
            yaml.dump(new_cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

        return jsonify({"status": "ok", "message": "maps.yaml saved successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
