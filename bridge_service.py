import asyncio, json, logging, serial, time
import websockets
import yaml

from mdp_protocol import *
from pathlib import Path
from logging.handlers import RotatingFileHandler

# -----------------------------
# Create logs directory
# -----------------------------
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / "bridge.log"
ERROR_FILE = LOG_DIR / "bridge_error.log"

# -----------------------------
# Create logger
# -----------------------------
log = logging.getLogger("bridge")
log.setLevel(logging.INFO)

# Log format
formatter = logging.Formatter(
 "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)

# Rotating main log file
file_handler = RotatingFileHandler(
 LOG_FILE,
 maxBytes=5 * 1024 * 1024,   # 5 MB
 backupCount=3               # keep 3 old logs
)
file_handler.setFormatter(formatter)

# Error log file
error_handler = RotatingFileHandler(
 ERROR_FILE,
 maxBytes=2 * 1024 * 1024,
 backupCount=3
)
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(formatter)

# Console output
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# Add handlers
log.addHandler(file_handler)
log.addHandler(error_handler)
log.addHandler(console_handler)

# Global constants
CONFIG_PATH = Path("config/maps.yaml")
SERIAL_PORT = "/dev/ttyUSB0" # Confirm name of port running ls /dev* command. Supposed to be /dev/ttyUSB0
SERIAL_BAUD = 115200         # Confirm DIP switch setting on unit
WS_URL = "ws://0.0.0.0:8765"
RECONNECT_DELAY = 5

UNIT_CHANNEL_MAP = {}
FLOOR_CHANNEL_MAP = {}
STATUS_COLOUR = {}

# -------------------------------------------------
# Serial Device Wrapper
# -------------------------------------------------
class SLS960:

 def __init__(self,port,baud):
  self.port = port
  self.baud = baud
  self.ser = None

 async def connect(self):
  while True:
   try:
    self.ser = serial.Serial(
     port=self.port,
     baudrate=self.baud,
     bytesize=serial.EIGHTBITS,
     parity=serial.PARITY_NONE,
     stopbits=serial.STOPBITS_ONE,
     timeout=1)
    log.info(f"SLS960 connected {self.port}")
    return
   except Exception as e:
    log.error(f"Serial connect failed: {e}")
    await asyncio.sleep(RECONNECT_DELAY)

 def send(self,data:bytes):
  try:
   self.ser.write(data)
   self.ser.flush()
  except Exception as e:
   log.error(f"Serial write failed: {e}")
   raise

 def rgb(self, ch, r, g, b):
  self.send(cmd_rgb_level(ch, r, g, b))

 def off(self, ch):
  self.send(cmd_off(ch))

 def blackout(self):
  self.send(cmd_broadcast_off())

 def suspend(self):
  self.send(cmd_subcmd(0, SUBCMD_SUSPEND))

 def resume(self):
  self.send(cmd_subcmd(0, SUBCMD_RESUME))

 def keepalive(self):
  self.send(cmd_nop(0))

#----------------------------
# Config loader
#----------------------------
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
        f"Invalid floor_channel_map entry for florr {floor}. "
        f"Expected [start, end], got: {range_data}"
      )
     
    start, end = map(int, range_data)
    floor_channel_map[int(floor)] = list(range(start, end+1))
    
  #Convert colors to tuples
  status_colour = {
   key: tuple(value)
   for key, value in config.get("status_colour", {}).items()
  }
  return unit_channel_map, floor_channel_map, status_colour 
  
sls = SLS960(SERIAL_PORT, SERIAL_BAUD)
START_TIME = time.time()

# -------------------------------------------------
# Hardware command worker
# -------------------------------------------------
async def hardware_worker(queue: asyncio.Queue):
 """
 Async worker that executes hardware commands from a queue.
 Commands are tuples: (command_name:str, args:tuple)
 """
 while True:
  command_name, args = await queue.get()

  try:
   if command_name == "rgb":
    sls.rgb(*args)
   elif command_name == "blackout":
    sls.blackout()
   elif command_name == "suspend":
    sls.suspend()
   elif command_name == "resume":
    sls.resume()
   elif command_name == "keepalive":
    sls.keepalive()
   else:
    log.warning(f"Unknown hardware command: {command_name}")

  except Exception as e:
   log.error(f"Hardware command failed ({command_name}): {e}")
   raise


# -------------------------------------------------
# Serial watchdog
# -------------------------------------------------
async def serial_watchdog(queue: asyncio.Queue, interval: int = 600):
 """
 Periodically sends a keepalive command to prevent SLS960 idle timeout.
 """
 while True:
  await asyncio.sleep(interval)
  await queue.put(("keepalive", ()))
  log.debug("Keepalive sent")


# -------------------------------------------------
# Helper: suspend -> execute -> resume pattern
# -------------------------------------------------
async def execute_with_suspend(queue: asyncio.Queue, commands: list[tuple]):
 """
 Suspend hardware, execute multiple commands, then resume.
 """
 await queue.put(("suspend", ()))
 for cmd_name, args in commands:
  await queue.put((cmd_name, args))
 await queue.put(("resume", ()))


# -------------------------------------------------
# Command processor
# -------------------------------------------------
async def process_command(data: dict, queue: asyncio.Queue):
 """
 Convert websocket JSON commands into hardware queue commands.
 """
 command = data.get("command", "")
 payload = data.get("payload", {})

 if command == "unit_status":
  unit_id = payload["unit_id"]
  status = payload.get("status", "off")
  r, g, b = STATUS_COLOUR.get(status, (255, 255, 255))

  commands = [("rgb", (ch, r, g, b)) for ch in UNIT_CHANNEL_MAP.get(unit_id, [])]
  await execute_with_suspend(queue, commands)

 elif command == "sync_all":
  commands = []
  for uid, status in payload.get("units", {}).items():
   r, g, b = STATUS_COLOUR.get(status, (255, 255, 255))
   for ch in UNIT_CHANNEL_MAP.get(uid, []):
    commands.append(("rgb", (ch, r, g, b)))
  await execute_with_suspend(queue, commands)

 elif command == "floor_highlight":
  floor = payload.get("floor", 0)
  col = payload.get("colour", [100, 150, 255])
  commands = [("rgb", (ch, *col)) for ch in FLOOR_CHANNEL_MAP.get(floor, [])]
  await execute_with_suspend(queue, commands)

 elif command == "blackout":
  await queue.put(("blackout", ()))

 else:
  log.warning(f"Received unknown command: {command}")


# -------------------------------------------------
# WebSocket handler
# -------------------------------------------------
async def handle(ws, queue: asyncio.Queue):
 """
 Handles a single websocket client connection.
 """
 log.info(f"Client connected: {ws.remote_address}")

 async for msg in ws:
  try:
   data = json.loads(msg)

   # Handle ping separately
   if data.get("command") == "ping":
    uptime = int(time.time() - START_TIME)
    await ws.send(json.dumps({"status": "ok", "command": "ping", "uptime": uptime}))
    continue

   # Process hardware command
   await process_command(data, queue)
   await ws.send(json.dumps({"status": "ok"}))

  except Exception as e:
   log.error(f"Command processing error: {e}")
   await ws.send(json.dumps({"status": "error", "message": str(e)}))



# -------------------------------------------------
# Bridge supervisor
# -------------------------------------------------
async def bridge():
 """
 Main supervisor: loads config, starts hardware worker, watchdog, and websocket server.
 """
 global UNIT_CHANNEL_MAP, FLOOR_CHANNEL_MAP, STATUS_COLOUR

 UNIT_CHANNEL_MAP, FLOOR_CHANNEL_MAP, STATUS_COLOUR = load_maps()
 log.info(f"Configuration loaded from file: {CONFIG_PATH}")
 log.info(f"{len(UNIT_CHANNEL_MAP)} units successfully loaded")
 log.info(f"{len(FLOOR_CHANNEL_MAP)} floors successfully loaded")
 log.info(f"{len(STATUS_COLOUR)} state color combinations successfully loaded")

 queue = asyncio.Queue()

 while True:
  try:
   # Connect hardware
   await sls.connect()

   # Start worker tasks
   worker_task = asyncio.create_task(hardware_worker(queue))
   watchdog_task = asyncio.create_task(serial_watchdog(queue))

   # Start websocket server
   server = await websockets.serve(lambda ws: handle(ws, queue), "0.0.0.0", 8765)
   log.info("WebSocket server started")

   # Run forever
   await asyncio.Future()

  except Exception as e:
   log.error(f"Bridge failure: {e}")

  finally:
   log.warning("Restarting bridge in {RECONNECT_DELAY}s...")
   await asyncio.sleep(RECONNECT_DELAY)


# -------------------------------------------------
# Main entry
# -------------------------------------------------
async def main():
 log.info("Bridge starting")
 await bridge()


if __name__ == "__main__":
 try:
  asyncio.run(main())
 except KeyboardInterrupt:
  log.info("Bridge stopped")