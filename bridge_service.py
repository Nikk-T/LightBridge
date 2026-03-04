import asyncio, json, logging, serial, time, websockets
from mdp_protocol import *

logging.basicConfig(level=logging.INFO,
 format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bridge")

SERIAL_PORT = "/dev/ttyUSB0" # Confirm name of port running ls /dev* command. Supposed to be /dev/ttyUSB0
SERIAL_BAUD = 115200         # Confirm DIP switch setting on unit

class SLS960:
 def __init__(self, port, baud):
  self.ser = serial.Serial(
   port=port, baudrate=baud,
   bytesize=serial.EIGHTBITS,
   parity=serial.PARITY_NONE,
   stopbits=serial.STOPBITS_ONE,
   timeout=1)
  log.info(f"SLS960 opened on {port} at {baud} baud")

 def send(self, data: bytes):
  self.ser.write(data)
  self.ser.flush()

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

# ── Channel mapping — update with actual wiring diagram ───────
# SLS960 addresses are 0-BASED
# Serial 0 = 0-119, Serial 1 = 120-239 ... Serial 7 = 840-959

UNIT_CHANNEL_MAP = {
 "A101": [0, 1, 2],
 "A102": [3, 4, 5],
 "A103": [6, 7, 8],
 "B201": [9, 10, 11],
 # Complete this map with integrator once model is wired
}

FLOOR_CHANNEL_MAP = {
 1: list(range(0, 30)),
 2: list(range(120, 150)),
 # Complete with integrator
}

STATUS_COLOUR = {
 "available": (50, 255, 100),
 "selected": (100, 150, 255),
 "reserved": (255, 200, 0),
 "sold": (255, 50, 50),
 "off": (0, 0, 0),
}

sls = SLS960(SERIAL_PORT, SERIAL_BAUD)
START_TIME = time.time()

async def keepalive_loop():
 """Send MDP_NOP every 10 min to prevent 30-min SLS960 idle timeout."""
 while True:
  await asyncio.sleep(600)
  sls.keepalive()
  log.debug("Keepalive NOP sent")

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
    r, g, b = STATUS_COLOUR.get(status, (255,255,255))
    for ch in UNIT_CHANNEL_MAP.get(uid, []):
     sls.rgb(ch, r, g, b)

   elif command == "sync_all":
    # SUSPEND first — all channels update simultaneously
    sls.suspend()
    for uid, status in payload.get("units", {}).items():
     r, g, b = STATUS_COLOUR.get(status, (255,255,255))
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
 log.info("Bridge starting — ws://0.0.0.0:8765")
 async with websockets.serve(handle, "0.0.0.0", 8765):
  await asyncio.gather(
   asyncio.Future(), # run forever
   keepalive_loop(), # prevent SLS960 idle timeout
  )

asyncio.run(main())
