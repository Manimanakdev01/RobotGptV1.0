import serial.tools.list_ports
import subprocess
import os
from flask import Flask, request, jsonify

app = Flask(__name__)

def detect_board():
    ports = serial.tools.list_ports.comports()
    for p in ports:
        desc = p.description.lower()
        if "cp210" in desc:
            return "ESP32", p.device
        if "ch340" in desc:
            return "Arduino Nano", p.device
        if "arduino" in desc:
            return "Arduino Uno", p.device
    return None, None

@app.route("/detect", methods=["GET"])
def detect():
    board, port = detect_board()
    return jsonify({"board": board, "port": port})

@app.route("/flash", methods=["POST"])
def flash():
    data = request.json
    code = data["code"]
    board = data["board"]
    port = data["port"]

    os.makedirs("build", exist_ok=True)
    with open("build/sketch.ino", "w") as f:
        f.write(code)

    fqbn = {
        "Arduino Uno": "arduino:avr:uno",
        "Arduino Nano": "arduino:avr:nano",
        "ESP32": "esp32:esp32:esp32"
    }.get(board)

    compile_cmd = ["arduino-cli", "compile", "--fqbn", fqbn, "build"]
    upload_cmd = ["arduino-cli", "upload", "-p", port, "--fqbn", fqbn, "build"]

    subprocess.run(compile_cmd, check=True)
    subprocess.run(upload_cmd, check=True)

    return jsonify({"status": "success"})

app.run(port=5000)

