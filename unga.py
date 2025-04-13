import busio
import digitalio
import board
import time

from adafruit_mcp3xxx.mcp3008 import MCP3008
from adafruit_mcp3xxx.analog_in import AnalogIn

# Setup SPI bus and chip select (CS)
spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)
cs = digitalio.DigitalInOut(board.D8)  # CE0 = GPIO8
mcp = MCP3008(spi, cs)

# Use channel 0 (connected to AO from moisture sensor)
chan = AnalogIn(mcp, 0)  # CH0 = channel 0

def voltage_to_moisture_percent(voltage, dry=2.8, wet=1.2):
    percent = (dry - voltage) / (dry - wet) * 100
    return max(0, min(100, round(percent)))

while True:
    moisture = voltage_to_moisture_percent(chan.voltage)
    print(f"Moisture: {moisture}% (Voltage: {chan.voltage:.2f}V)")
    time.sleep(1)
