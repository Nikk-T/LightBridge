import asyncio, logging, serial, time

from mdp_protocol import *
log = logging.getLogger(__name__)

#class SLS960:

RECONNECT_DELAY = 3
MAX_RETRIES = 3

def __init__(self, port, baud):
    self.port = port
    self.baud = baud
    self.ser = None
    self.connect()

# -------------------------------------------------
# Serial connection
# -------------------------------------------------
def connect(self):

    while True:
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )

            log.info(f"SLS960 connected on {self.port} @ {self.baud}")
            return

        except serial.SerialException as e:
            log.error(f"Serial connect failed: {e}")
            log.info("Retrying serial connection...")
            time.sleep(self.RECONNECT_DELAY)

# -------------------------------------------------
# Send with auto-reconnect
# -------------------------------------------------
def send(self, data: bytes):

    for attempt in range(self.MAX_RETRIES):

        try:

            if not self.ser or not self.ser.is_open:
                raise serial.SerialException("Serial not connected")

            self.ser.write(data)
            self.ser.flush()
            return

        except (serial.SerialException, OSError) as e:

            log.error(f"Serial write failed: {e}")

            try:
                if self.ser:
                    self.ser.close()
            except:
                pass

            log.warning("Serial disconnected — reconnecting...")
            self.connect()

    log.error("Serial send failed after retries")

# -------------------------------------------------
# Hardware commands
# -------------------------------------------------

    def send(self, data: bytes):
        self.ser.write(data)
        self.ser.flush()

    def rgb(self, ch, r, g, b):
        self.send(cmd_rgb_fade(ch, r, 10, 5, g, 10, 5, b, 10, 5))
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


