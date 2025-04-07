import RPi.GPIO as GPIO
import time

# Set up the GPIO pin
GPIO.setmode(GPIO.BCM)
GPIO.setup(21, GPIO.IN)  # LM393 output connected to GPIO21

# Set a reference threshold value (you can calibrate this based on your sensor)
reference_voltage = 2.0  # You can adjust this to a voltage you desire for the threshold

try:
    while True:
        # Read the state of the LM393 output pin
        signal = GPIO.input(21)
        
        if signal == GPIO.HIGH:
            # Soil is dry (below the threshold)
            print("Soil is dry. Signal HIGH")
        else:
            # Soil is wet (above the threshold)
            print("Soil is wet. Signal LOW")
        
        # Print approximate moisture level based on reference voltage
        # Here, we simulate reading an analog value by approximating it with a threshold range.
        moisture_level = (reference_voltage - 1.0)  # Example for demonstration, adjust as needed
        print(f"Moisture Level: {moisture_level} V (approximation)")
        
        time.sleep(1)

except KeyboardInterrupt:
    print("Exiting...")
    GPIO.cleanup()

