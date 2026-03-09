import asyncio, json, logging, serial, time
import websockets
import yaml

from pathlib import Path
from logging.handlers import RotatingFileHandler
from serialdriver import SLS960

# -----------------------------
# Create logs directory
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent

LOG_DIR = BASE_DIR/"logs"
LOG_DIR.mkdir(exist_ok=True)
#LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / "bridge.log"
ERROR_FILE = LOG_DIR / "bridge_error.log"

# -----------------------------
# Create logger
# -----------------------------
log = logging.getLogger("bridge")
log.setLevel(logging.INFO)

# -----------------------------
# Log format
# -----------------------------
formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

# -----------------------------
# Rotating main log file
# -----------------------------
file_handler = RotatingFileHandler(
 LOG_FILE,
 maxBytes=5 * 1024 * 1024,   # 5 MB
 backupCount=3               # keep 3 old logs
)
file_handler.setFormatter(formatter)

# -----------------------------
# Error log file
# -----------------------------
error_handler = RotatingFileHandler(
 ERROR_FILE,
 maxBytes=2 * 1024 * 1024,
 backupCount=3
)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(formatter)

# -----------------------------
# Console output
# -----------------------------
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# -----------------------------
# Add handlers
# -----------------------------
log.addHandler(file_handler)
log.addHandler(error_handler)
log.addHandler(console_handler)


CONFIG_PATH = BASE_DIR / "config" / "maps.yaml"
#CONFIG_PATH = Path("config/maps.yaml")

SERIAL_PORT = "/dev/ttyUSB0" # Confirm name of port running ls /dev* command. Supposed to be /dev/ttyUSB0
SERIAL_BAUD = 115200         # Confirm DIP switch setting on unit
WS_URL = "ws://0.0.0.0:8765"

UNIT_CHANNEL_MAP = {}
FLOOR_CHANNEL_MAP = {}
STATUS_COLOUR = {}

RECONNECT_DELAY = 5
#---------------------------------------------------------
# Load config from YAML
#---------------------------------------------------------

def load_maps(config_path=CONFIG_PATH):
 if not config_path.exists():
  raise FileNotFoundError(f"Config file not found: {config_path}")

 with open(config_path, "r") as f:
  config = yaml.safe_load(f)

  #Unit map
  unit_channel_map = config.get("unit_channel_map", {})
  
  #Floor map
  floor_channel_map = {}
  for floor, range_data in config.get("floor_channel_map", {}).items():
    if not isinstance(range_data, list) or len(range_data) !=2:
      raise ValueError(
        f"Invalid floor_channel_map entry for floor {floor}. "
        f"Expected [start, end], got: {range_data}"
      )
    start, end = map(int, range_data)
    floor_channel_map[int(floor)] = list(range(start, end+1))
    
  #Convert colors to tuples
  status_colour = config.get("status_colour", {})
  return unit_channel_map, floor_channel_map, status_colour 
  
sls = SLS960(SERIAL_BAUD)
START_TIME = time.time()

#Send MDP_NOP every 10 min to prevent 30-min SLS960 idle timeout.
async def keepalive_loop():
 while True:
  await asyncio.sleep(600)
  sls.keepalive()
  log.debug("Keepalive NOP sent")

#WebSocket handling
async def handle(websocket):
 log.info(f"Client connected: {websocket.remote_address}")
 async for msg in websocket:
  try:
   data = json.loads(msg)
   command = data.get("command", "")
   payload = data.get("payload", {})
   log.info(f"CMD: {command} | {payload}")

   if command == "unit_status":
    uid = payload["unit_id"]
    status = payload.get("status", "off")
    r, g, b = STATUS_COLOUR.get(status, (0,0,0))
    for ch in UNIT_CHANNEL_MAP.get(uid, []):
     sls.rgb(ch, r, g, b)

   elif command == "sync_all":
    # SUSPEND first — all channels update simultaneously
    sls.suspend()
    for uid, status in payload.get("units", {}).items():
     r, g, b = STATUS_COLOUR.get(status, (0,0,0))
     for ch in UNIT_CHANNEL_MAP.get(uid, []):
      sls.rgb(ch, r, g, b)
    sls.resume() # All channels light at once — no flicker

   elif command == "floor_highlight":
    col = payload.get("colour", [100, 150, 255])
    sls.suspend()
    for ch in FLOOR_CHANNEL_MAP.get(payload.get("floor",0), []):
     sls.rgb(ch, *col)
    sls.resume()

   elif command == "set_scene":
    scene = payload.get("scene", "idle")
    if scene == "blackout":
     sls.blackout()
    elif scene == "idle":
     # Warm white across all channels
     sls.suspend()
     for ch in range(960):
      sls.rgb(ch, 255, 220, 160)
     sls.resume()
    elif scene == "presentation":
     # Integrator to define: trigger pseudo-address group
     # or run a pre-programmed sequence here
     pass

   elif command == "blackout":
    sls.blackout()

   elif command == "set_colour":
    sls.rgb(payload["channel"],
    payload["r"], payload["g"], payload["b"])

   elif command == "ping":
    uptime = int(time.time() - START_TIME)
    await websocket.send(json.dumps(
     {"status":"ok","command":"ping","uptime":uptime}))
    continue

   await websocket.send(json.dumps({"status": "ok", "command": command}))

  except Exception as e:
   log.error(f"Error: {e}")
   await websocket.send(json.dumps(
    {"status":"error","message":str(e)}))

async def main():
 global UNIT_CHANNEL_MAP, FLOOR_CHANNEL_MAP, STATUS_COLOUR
 
 log.info("Bridge starting — ws://0.0.0.0:8765")
 
 UNIT_CHANNEL_MAP, FLOOR_CHANNEL_MAP, STATUS_COLOUR = load_maps()
 
 log.info(f"Configuration loaded from file: {CONFIG_PATH}")
 log.info(f"{len(UNIT_CHANNEL_MAP)} units successfully loaded")
 log.info(f"{len(FLOOR_CHANNEL_MAP)} floors successfully loaded")
 log.info(f"{len(STATUS_COLOUR)} state color combinations successfully loaded")
 
 async with websockets.serve(handle, "0.0.0.0", 8765):
  await asyncio.gather(
   asyncio.Future(), # run forever
   keepalive_loop(), # prevent SLS960 idle timeout
  )
asyncio.run(main())
