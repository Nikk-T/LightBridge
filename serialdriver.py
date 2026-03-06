import asyncio, logging, serial, time

from mdp_protocol import *
log = logging.getLogger(__name__)

#TRY Later
""" # --------------------------------------------------
# Serial connection manager
# --------------------------------------------------
async def connect_serial():
    while True:
        try:
            ser = serial.Serial(SERIAL_PORT, SERIAL_BAUD, timeout=0.1)
            log.info(f"Serial connected {SERIAL_PORT}")
            return ser
        except Exception as e:
            log.error(f"Serial connect failed: {e}")
            await asyncio.sleep(RECONNECT_DELAY)
"""


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
        self.send(cmd_rgb_fade(ch, r, 10, 10, g, 10, 10, b, 10, 10))
    #    self.send(cmd_rgb_level(ch, r, g, b))

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


