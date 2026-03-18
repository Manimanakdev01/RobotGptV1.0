from flask import Flask, request, jsonify
import serial
import serial.tools.list_ports
import threading
import time

app = Flask(__name__)
ser = None
board_name = None
port_name = None

# --- Serial Detection ---
def init_serial():
    global ser, board_name, port_name
    ports = serial.tools.list_ports.comports()
    for p in ports:
        if "Arduino" in p.description or "ESP32" in p.description:
            try:
                ser = serial.Serial(p.device, 9600, timeout=1)
                board_name = p.description
                port_name = p.device
                print(f"✅ Serial initialized: {board_name} on {port_name}")
                return
            except Exception as e:
                print(f"Serial init error: {e}")
    ser = None
    board_name = None
    port_name = None
    print("❌ No compatible board found")

# Run serial init in background
threading.Thread(target=init_serial, daemon=True).start()

# --- Routes ---
@app.route("/detect-board", methods=["GET"])
def detect_board():
    return jsonify({"board": board_name, "port": port_name})

@app.route("/upload", methods=["POST"])
def upload_code():
    global ser
    data = request.json
    code = data.get("code")
    if not ser:
        return jsonify({"status": "error", "log": "No board connected"})
    
    try:
        # For demo, just sending code as string
        # Replace with actual compile + upload logic
        ser.write(code.encode())
        return jsonify({"status": "success", "log": "Code uploaded"})
    except Exception as e:
        return jsonify({"status": "error", "log": str(e)})

if __name__ == "__main__":
    app.run(port=5050)
