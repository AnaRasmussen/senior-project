from flask import Flask, jsonify, request, render_template
import RPi.GPIO as GPIO
import time
import threading
import sqlite3
import random
from datetime import datetime, timedelta

app = Flask(__name__)

# GPIO Pins
SOIL_SENSOR_PIN = 21
PUMP_PIN = 17

last_moisture = 50

def simulate_moisture():
    global last_moisture
    delta = random.randint(-5, 5)
    last_moisture = max(20, min(90, last_moisture + delta))
    return last_moisture


# ========== DATABASE SETUP ==========
def init_db():
    conn = sqlite3.connect("plant_data.db")
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            event TEXT,
            source TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS moisture (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            value INTEGER
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reservoir (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            level_ml INTEGER
        )
    ''')

    # Ensure at least one initial reservoir record
    cursor.execute("SELECT COUNT(*) FROM reservoir")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO reservoir (timestamp, level_ml) VALUES (?, ?)",
                       (datetime.now().isoformat(sep=' ', timespec='seconds'), 500))  # e.g. 500ml

    conn.commit()
    conn.close()


def log_event(event, source="system"):
    conn = sqlite3.connect("plant_data.db")
    cursor = conn.cursor()
    timestamp = datetime.now().isoformat(sep=' ', timespec='seconds')
    cursor.execute("INSERT INTO log (timestamp, event, source) VALUES (?, ?, ?)",
                   (timestamp, event, source))
    conn.commit()
    conn.close()

# ========== GPIO SETUP ==========

GPIO.setmode(GPIO.BCM)
GPIO.setup(SOIL_SENSOR_PIN, GPIO.IN)
GPIO.setup(PUMP_PIN, GPIO.OUT)
GPIO.output(PUMP_PIN, GPIO.LOW)

# ========== AUTO WATERING LOOP ==========

def auto_watering_loop():
    try:
        while True:
            signal = GPIO.input(SOIL_SENSOR_PIN)
            if signal == GPIO.HIGH:
                print("Soil is dry. Turning on pump.")
                GPIO.output(PUMP_PIN, GPIO.HIGH)
                log_event("Pump ON (auto)", source="auto")
            else:
                print("Soil is wet. Turning off pump.")
                GPIO.output(PUMP_PIN, GPIO.LOW)
                log_event("Pump OFF (auto)", source="auto")
            time.sleep(1)
    except Exception as e:
        print(f"Auto-watering error: {e}")
        GPIO.cleanup()

# ========== API ROUTES ==========

@app.route('/status', methods=['GET'])
def get_status():
    signal = GPIO.input(SOIL_SENSOR_PIN)
    status = "dry" if signal == GPIO.HIGH else "wet"
    return jsonify({"soil": status, "signal": signal})

@app.route('/water', methods=['POST'])
def water_plant():
    duration = request.json.get("duration", 5) if request.is_json else 5
    duration = min(max(duration, 1), 30)

    GPIO.output(PUMP_PIN, GPIO.HIGH)
    log_event(f"Pump ON (manual, {duration}s)", source="manual")
    update_reservoir_usage(duration * 10)  # Assume 10ml/sec
    time.sleep(duration)
    GPIO.output(PUMP_PIN, GPIO.LOW)
    log_event("Pump OFF (manual)", source="manual")

    return jsonify({"message": f"Manually watered for {duration} seconds"})

@app.route('/logs', methods=['GET'])
def get_logs():
    conn = sqlite3.connect("plant_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM log ORDER BY id DESC LIMIT 20")
    rows = cursor.fetchall()
    conn.close()
    return jsonify([{"id": r[0], "timestamp": r[1], "event": r[2], "source": r[3]} for r in rows])

@app.route('/cleanup', methods=['POST'])
def cleanup():
    GPIO.cleanup()
    log_event("GPIO cleanup", source="manual")
    return jsonify({"message": "GPIO cleaned up"})

@app.route('/')
def dashboard():
    return render_template('index.html')

def log_moisture(value):
    conn = sqlite3.connect("plant_data.db")
    cursor = conn.cursor()
    timestamp = datetime.now().isoformat(sep=' ', timespec='seconds')
    cursor.execute("INSERT INTO moisture (timestamp, value) VALUES (?, ?)", (timestamp, value))
    conn.commit()
    conn.close()

def auto_watering_loop():
    try:
        pump_on = False  # Track pump state to avoid duplicate logs

        while True:
            signal = GPIO.input(SOIL_SENSOR_PIN)

            # Simulated moisture percentage (for dashboard only)
            moisture_value = simulate_moisture()
            log_moisture(moisture_value)

            if signal == GPIO.HIGH:
                # Soil is dry
                if not pump_on:
                    print("Soil is dry. Signal HIGH. Turning ON pump.")
                    GPIO.output(PUMP_PIN, GPIO.HIGH)
                    log_event("Pump ON (auto)", source="auto")
                    update_reservoir_usage(50)  # Assume 50ml per dry event
                    pump_on = True
            else:
                # Soil is wet
                if pump_on:
                    print("Soil is wet. Signal LOW. Turning OFF pump.")
                    GPIO.output(PUMP_PIN, GPIO.LOW)
                    log_event("Pump OFF (auto)", source="auto")
                    pump_on = False

            time.sleep(1)
    except Exception as e:
        print(f"Auto-watering error: {e}")
        GPIO.cleanup()

@app.route('/refill', methods=['POST'])
def refill_reservoir():
    conn = sqlite3.connect("plant_data.db")
    cursor = conn.cursor()
    timestamp = datetime.now().isoformat(sep=' ', timespec='seconds')
    cursor.execute("INSERT INTO reservoir (timestamp, level_ml) VALUES (?, ?)", (timestamp, 500))
    conn.commit()
    conn.close()
    log_event("Reservoir refilled", source="user")
    return jsonify({"message": "Reservoir refilled."})

def update_reservoir_usage(ml_used):
    conn = sqlite3.connect("plant_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, level_ml FROM reservoir ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    if row:
        new_level = max(row[1] - ml_used, 0)
        cursor.execute("UPDATE reservoir SET level_ml = ? WHERE id = ?", (new_level, row[0]))
        conn.commit()
    conn.close()

@app.route('/dashboard-data')
def dashboard_data():
    conn = sqlite3.connect("plant_data.db")
    cursor = conn.cursor()

    # Get last 10 moisture readings
    cursor.execute("SELECT timestamp, value FROM moisture ORDER BY id DESC LIMIT 10")
    moisture_rows = cursor.fetchall()
    moisture_data = {
        "timestamps": [r[0][-8:] for r in reversed(moisture_rows)],
        "values": [r[1] for r in reversed(moisture_rows)]
    }

    # Get recent watering logs
    cursor.execute("SELECT timestamp, event FROM log WHERE event LIKE 'Pump ON%' ORDER BY id DESC LIMIT 7")
    history = [{"timestamp": r[0], "event": r[1]} for r in cursor.fetchall()]

    # Reservoir level
    cursor.execute("SELECT level_ml FROM reservoir ORDER BY id DESC LIMIT 1")
    level_ml = cursor.fetchone()[0]
    reservoir_status = "HIGH" if level_ml > 100 else "LOW"

    # Last watered
    cursor.execute("SELECT timestamp FROM log WHERE event LIKE 'Pump ON%' ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    last_watered = row[0].split(" ")[0] if row else None

    conn.close()

    return jsonify({
        "moisture": moisture_data,
        "history": history,
        "reservoir": { "status": reservoir_status },
        "last_watered": last_watered
    })


# ========== MAIN ==========

if __name__ == '__main__':
    init_db()
    threading.Thread(target=auto_watering_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)

