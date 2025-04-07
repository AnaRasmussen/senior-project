import RPi.GPIO as GPIO
from time import sleep

# GPIO setup
IN1 = 17  # GPIO pin connected to IN1
IN2 = 18  # GPIO pin connected to IN2

GPIO.setmode(GPIO.BCM)
GPIO.setup(IN1, GPIO.OUT)
GPIO.setup(IN2, GPIO.OUT)

try:
    while True:
        # Turn the pump ON
        GPIO.output(IN1, GPIO.HIGH)
        GPIO.output(IN2, GPIO.LOW)
        print("Pump ON")
        sleep(5)  # Run pump for 5 seconds

        # Turn the pump OFF
        GPIO.output(IN1, GPIO.LOW)
        GPIO.output(IN2, GPIO.LOW)
        print("Pump OFF")
        sleep(5)  # Wait for 5 seconds

except KeyboardInterrupt:
    print("Exiting program.")

finally:
    GPIO.cleanup()  # Reset GPIO pins

