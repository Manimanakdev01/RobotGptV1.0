from flask import Flask, request, jsonify
import serial.tools.list_ports
import subprocess
import os

app = Flask(__name__)

@app.route("/detect-board", methods=["GET"])
def detect_board():
    ports = serial.tools.list_ports.comports()
    for p in ports:
        desc = p.description.lower()
        if "cp210" in desc:
            return jsonify({"board": "ESP32", "port": p.device})
        if "ch340" in desc or "nano" in desc:
            return jsonify({"board": "Arduino Nano", "port": p.device})
        if "uno" in desc or "arduino" in desc:
            return jsonify({"board": "Arduino Uno", "port": p.device})
    return jsonify({"board": None, "port": None})


@app.route("/upload", methods=["POST"])
def upload():
    data = request.json
    code = data["code"]
    board = data["board"]
    port = data["port"]

    folder = "sketch_build"
    os.makedirs(folder, exist_ok=True)

    ino_path = os.path.join(folder, "sketch_build.ino")
    with open(ino_path, "w") as f:
        f.write(code)

    fqbn_map = {
        "Arduino Uno": "arduino:avr:uno",
        "Arduino Nano": "arduino:avr:nano:cpu=atmega328old",
        "ESP32": "esp32:esp32:esp32"
    }

    fqbn = fqbn_map.get(board)

    compile_cmd = ["arduino-cli.exe", "compile", "--fqbn", fqbn, folder]
    upload_cmd = ["arduino-cli.exe", "upload", "-p", port, "--fqbn", fqbn, folder]

    subprocess.run(compile_cmd, capture_output=True)
    res = subprocess.run(upload_cmd, capture_output=True, text=True)

    if res.returncode == 0:
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "log": res.stderr})


def run():
    app.run(port=5050, debug=False)


if __name__ == "__main__":
    run()
