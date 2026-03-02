from flask import Flask, request, jsonify
import serial.tools.list_ports
import subprocess
import os
import shutil

app = Flask(__name__)

ARDUINO_CLI = os.path.abspath("arduino-cli.exe")  # 🔥 absolute path recommended

# ---------------- BOARD DETECTION ----------------
@app.route("/detect-board", methods=["GET"])
def detect_board():
    ports = serial.tools.list_ports.comports()

    for p in ports:
        desc = (p.description or "").lower()
        hwid = (p.hwid or "").lower()

        if any(x in desc for x in ["cp210", "silicon labs", "usb serial"]):
            return jsonify({"board": "ESP32", "port": p.device})

        if "ch340" in desc or "ch341" in desc:
            return jsonify({"board": "Arduino Nano", "port": p.device})

        if "arduino" in desc or "uno" in desc:
            return jsonify({"board": "Arduino Uno", "port": p.device})

    return jsonify({"board": None, "port": None})


# ---------------- UPLOAD ----------------
@app.route("/upload", methods=["POST"])
def upload():
    data = request.json
    code = data["code"]
    board = data["board"]
    port = data["port"]

    build_dir = "sketch_build"
    os.makedirs(build_dir, exist_ok=True)

    ino_path = os.path.join(build_dir, "sketch_build.ino")
    with open(ino_path, "w", encoding="utf-8") as f:
        f.write(code)

    fqbn_map = {
        "Arduino Uno": "arduino:avr:uno",
        "Arduino Nano": "arduino:avr:nano",
        "ESP32": "esp32:esp32:esp32"
    }

    fqbn = fqbn_map.get(board)
    if not fqbn:
        return jsonify({"status": "error", "log": "Unknown board"})

    # ---------- COMPILE ----------
    compile_cmd = [
        ARDUINO_CLI, "compile",
        "--fqbn", fqbn,
        build_dir
    ]

    compile = subprocess.run(
        compile_cmd,
        capture_output=True,
        text=True
    )

    if compile.returncode != 0:
        return jsonify({
            "status": "compile_error",
            "log": compile.stderr
        })

    # ---------- UPLOAD ----------
    upload_cmd = [
        ARDUINO_CLI, "upload",
        "-p", port,
        "--fqbn", fqbn,
        build_dir
    ]

    upload = subprocess.run(
        upload_cmd,
        capture_output=True,
        text=True
    )

    if upload.returncode == 0:
        return jsonify({"status": "success"})

    # Nano old bootloader fallback
    if board == "Arduino Nano":
        fallback_fqbn = "arduino:avr:nano:cpu=atmega328old"
        upload_cmd[upload_cmd.index("--fqbn") + 1] = fallback_fqbn
        retry = subprocess.run(upload_cmd, capture_output=True, text=True)
        if retry.returncode == 0:
            return jsonify({"status": "success"})

    return jsonify({
        "status": "upload_error",
        "log": upload.stderr
    })


def run():
    app.run(port=5050, debug=False, threaded=True)


if __name__ == "__main__":
    run()
