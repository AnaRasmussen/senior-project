from flask import Flask, jsonify, request, render_template
import RPi.GPIO as GPIO
import time
import threading
import sqlite3
from datetime import datetime

import busio
import digitalio
import board
from adafruit_mcp3xxx.mcp3008 import MCP3008
from adafruit_mcp3xxx.analog_in import AnalogIn

app = Flask(__name__)

SOIL_SENSOR_PIN = 21
PUMP_PIN = 17

spi = busio.SPI(clock=board.SCK, MISO=board.MISO, MOSI=board.MOSI)
cs = digitalio.DigitalInOut(board.D8)
mcp = MCP3008(spi, cs)
moisture_chan = AnalogIn(mcp, 0)

def voltage_to_moisture_percent(voltage, dry=2.8, wet=1.2):
    percent = (dry - voltage) / (dry - wet) * 100
    return max(0, min(100, round(percent)))

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
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY,
            dry_threshold INTEGER,
            wet_threshold INTEGER
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS water_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            amount_oz REAL
        )
    ''')

    if cursor.execute("SELECT COUNT(*) FROM reservoir").fetchone()[0] == 0:
        cursor.execute("INSERT INTO reservoir (timestamp, level_ml) VALUES (?, ?)", (datetime.now().isoformat(sep=' ', timespec='seconds'), 500))

    if cursor.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0:
        cursor.execute("INSERT INTO settings (id, dry_threshold, wet_threshold) VALUES (1, 30, 60)")

    conn.commit()
    conn.close()

def log_event(event, source="system"):
    conn = sqlite3.connect("plant_data.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO log (timestamp, event, source) VALUES (?, ?, ?)",
                   (datetime.now().isoformat(sep=' ', timespec='seconds'), event, source))
    conn.commit()
    conn.close()

def log_moisture(value):
    conn = sqlite3.connect("plant_data.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO moisture (timestamp, value) VALUES (?, ?)",
                   (datetime.now().isoformat(sep=' ', timespec='seconds'), value))
    conn.commit()
    conn.close()

def log_water(amount_oz):
    conn = sqlite3.connect("plant_data.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO water_log (timestamp, amount_oz) VALUES (?, ?)",
                   (datetime.now().isoformat(sep=' ', timespec='seconds'), amount_oz))
    conn.commit()
    conn.close()

GPIO.setmode(GPIO.BCM)
GPIO.setup(SOIL_SENSOR_PIN, GPIO.IN)
GPIO.setup(PUMP_PIN, GPIO.OUT)
GPIO.output(PUMP_PIN, GPIO.LOW)

def auto_watering_loop():
    try:
        pump_on = False

        while True:
            conn = sqlite3.connect("plant_data.db")
            cursor = conn.cursor()
            cursor.execute("SELECT dry_threshold, wet_threshold FROM settings WHERE id=1")
            dry_threshold, wet_threshold = cursor.fetchone()
            conn.close()

            moisture_value = voltage_to_moisture_percent(moisture_chan.voltage)
            log_moisture(moisture_value)

            print(f"Moisture: {moisture_value}% | ON <= {dry_threshold}% | OFF >= {wet_threshold}% | Pump: {pump_on}")

            if moisture_value <= dry_threshold and not pump_on:
                GPIO.output(PUMP_PIN, GPIO.HIGH)
                log_event("Pump ON (auto)", source="auto")
                log_water(2.5)
                pump_on = True

            elif moisture_value >= wet_threshold and pump_on:
                GPIO.output(PUMP_PIN, GPIO.LOW)
                log_event("Pump OFF (auto)", source="auto")
                pump_on = False

            time.sleep(1)

    except Exception as e:
        print(f"Auto-watering error: {e}")
        GPIO.cleanup()

@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/threshold', methods=['GET'])
def get_threshold():
    conn = sqlite3.connect("plant_data.db")
    cursor = conn.cursor()
    cursor.execute("SELECT dry_threshold, wet_threshold FROM settings WHERE id=1")
    dry, wet = cursor.fetchone()
    conn.close()
    return jsonify({"dry_threshold": dry, "wet_threshold": wet})

@app.route('/threshold', methods=['POST'])
def update_threshold():
    new_dry = request.json.get('dry_threshold', 30)
    new_wet = request.json.get('wet_threshold', 60)
    conn = sqlite3.connect("plant_data.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET dry_threshold = ?, wet_threshold = ? WHERE id=1", (new_dry, new_wet))
    conn.commit()
    conn.close()
    log_event(f"Thresholds updated: ON <= {new_dry}%, OFF >= {new_wet}%", source="user")
    return jsonify({"message": "Thresholds updated."})

@app.route('/water-usage')
def water_usage():
    conn = sqlite3.connect("plant_data.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT strftime('%w', timestamp), SUM(amount_oz)
        FROM water_log
        GROUP BY strftime('%w', timestamp)
    """)
    rows = cursor.fetchall()
    conn.close()

    day_names = ['Sun', 'Mon', 'Tues', 'Wed', 'Thur', 'Fri', 'Sat']

    return jsonify([
        {"day": day_names[int(r[0])], "amount": round(r[1], 2)} for r in rows
    ])

@app.route('/water', methods=['POST'])
def water_plant():
    duration = request.json.get("duration", 5) if request.is_json else 5
    duration = min(max(duration, 1), 30)
    oz_used = (duration / 4) * 2

    GPIO.output(PUMP_PIN, GPIO.HIGH)
    log_event(f"Pump ON (manual, {duration}s)", source="manual")
    log_water(oz_used)
    time.sleep(duration)
    GPIO.output(PUMP_PIN, GPIO.LOW)
    log_event("Pump OFF (manual)", source="manual")

    return jsonify({"message": f"Manually watered for {duration} seconds"})

@app.route('/dashboard-data')
def dashboard_data():
    conn = sqlite3.connect("plant_data.db")
    cursor = conn.cursor()

    cursor.execute("SELECT timestamp, value FROM moisture ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()
    moisture_data = {
        "timestamps": [r[0][-8:] for r in reversed(rows)],
        "values": [r[1] for r in reversed(rows)]
    }

    cursor.execute("SELECT timestamp, event FROM log WHERE event LIKE 'Pump ON%' ORDER BY id DESC LIMIT 7")
    history = [{"timestamp": r[0], "event": r[1]} for r in cursor.fetchall()]

    cursor.execute("SELECT level_ml FROM reservoir ORDER BY id DESC LIMIT 1")
    level_ml = cursor.fetchone()[0]
    reservoir_status = "HIGH" if level_ml > 100 else "LOW"

    cursor.execute("SELECT timestamp FROM log WHERE event LIKE 'Pump ON%' ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    last_watered = row[0].split(" ")[0] if row else None

    conn.close()
    return jsonify({
        "moisture": moisture_data,
        "history": history,
        "reservoir": {"status": reservoir_status},
        "last_watered": last_watered
    })

@app.route('/refill', methods=['POST'])
def refill():
    conn = sqlite3.connect("plant_data.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO reservoir (timestamp, level_ml) VALUES (?, ?)",
                   (datetime.now().isoformat(sep=' ', timespec='seconds'), 500))
    conn.commit()
    conn.close()
    log_event("Reservoir refilled", source="user")
    return jsonify({"message": "Reservoir refilled."})

if __name__ == '__main__':
    init_db()
    threading.Thread(target=auto_watering_loop, daemon=True).start()
    app.run(host='0.0.0.0', port=5000)

