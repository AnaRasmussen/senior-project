import RPi.GPIO as GPIO
import time

GPIO.setmode(GPIO.BCM)
GPIO.setup(21, GPIO.IN)  # LM393 (soil moisture sensor)- GPIO21
GPIO.setup(17, GPIO.OUT)  # Pump - (GPIO17)

try:
    while True:
        # Read the state of the LM393 output pin
        signal = GPIO.input(21)
        
        if signal == GPIO.HIGH:
            # Soil is dry, turn on the pump
            print("Soil is dry. Signal HIGH. Turning on the pump.")
            GPIO.output(17, GPIO.HIGH)
        else:
            # Soil is wet, turn off the pump
            print("Soil is wet. Signal LOW. Turning off the pump.")
            GPIO.output(17, GPIO.LOW)
        
        time.sleep(1)

except KeyboardInterrupt:
    print("Exiting...")
    GPIO.cleanup()

