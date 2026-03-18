import streamlit as st
import pyrebase
import subprocess
import os
import time
import re
import requests
import json
from PIL import Image, ImageDraw
import zipfile
import urllib.request
from streamlit_ace import st_ace
import threading as td
from agent import run  # Flask agent

# --------------------- FIREBASE CONFIG ---------------------
firebaseConfig = {
    'apiKey': "AIzaSyBv-RR2MrpM-pwvhBxvMR8K1oYX074KQa8",
    'authDomain': "robotgpt-4a9a2.firebaseapp.com",
    'databaseURL': "https://robotgpt-4a9a2-default-rtdb.firebaseio.com",
    'projectId': "robotgpt-4a9a2",
    'storageBucket': "robotgpt-4a9a2.firebasestorage.app",
    'messagingSenderId': "186613664427",
    'appId': "1:186613664427:web:4db693e510e72c48a985ee",
    'measurementId': "G-EX23RWWJPX"
}

firebase = pyrebase.initialize_app(firebaseConfig)
auth = firebase.auth()
db = firebase.database()

# --------------------- UTILITY FUNCTIONS ---------------------

def setup_arduino_cli():
    """Install Arduino CLI if not exists"""
    if os.path.exists("arduino-cli.exe"):
        return "Arduino CLI 🟢"
    url = "https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Windows_64bit.zip"
    zip_path = "arduino-cli.zip"
    urllib.request.urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(".")
    os.remove(zip_path)
    return st.success("Arduino CLI downloaded successfully")

def call_ollama(prompt, model="qwen2.5-coder:3b", format_json=False, images=None):
    """Call local Ollama API"""
    url = "http://localhost:11434/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0}}
    if format_json: payload["format"] = "json"
    if images: payload["images"] = images
    try:
        res = requests.post(url, json=payload, timeout=180)
        if res.status_code != 200: return "Error: Ollama non-200 status"
        return res.json().get("response", "")
    except Exception as e:
        return f"Error: Ollama not reachable ({e})"

def detect_board(retry=5):
    """Detect board from Flask agent"""
    for _ in range(retry):
        try:
            r = requests.get("http://127.0.0.1:5050/detect-board", timeout=2)
            data = r.json()
            if data["board"] and data["port"]:
                return data["board"], data["port"]
        except: time.sleep(1)
    return None, None

def upload_code_via_agent(code, board, port):
    """Send firmware code to Flask agent for upload"""
    try:
        r = requests.post("http://127.0.0.1:5050/upload", json={"code": code, "board": board, "port": port}, timeout=300)
        return r.json()
    except Exception as e:
        return {"status": "error", "log": str(e)}

def auto_install_libraries(code):
    """Install Arduino libraries detected in code"""
    libs = re.findall(r'#include\s*[<"]([^">]+)[>"]', code)
    default_libs = ["Arduino.h", "Wire.h", "SPI.h", "EEPROM.h", "SoftwareSerial.h"]
    for lib in libs:
        if lib not in default_libs:
            subprocess.run(["arduino-cli.exe", "lib", "install", lib.replace(".h", "")], capture_output=True)

def save_project(email, project):
    db.child("projects").child(email.replace(".", "_")).push(project)

def get_projects(email):
    data = db.child("projects").child(email.replace(".", "_")).get().val()
    return data if data else {}

def generate_ai_code(task, board):
    prompt = f"You are a best Arduino and ESP32 professor. Generate Arduino code for: {task}. Board: {board}. Return ONLY code inside [code][/code] tags."
    raw = call_ollama(prompt)
    match = re.search(r"\[code\](.*?)\[/code\]", raw, re.DOTALL)
    return match.group(1).strip() if match else raw

def generate_wiring(task, board):
    prompt = f"Task: Explain wiring for {task} using {board}. Format: Bullet points. Constraint: MUST start with [diagram] and end with [/diagram]."
    raw = call_ollama(prompt)
    match = re.search(r"\[diagram\](.*?)\[/diagram\]", raw, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else raw

def draw_wiring(text):
    img = Image.new("RGB", (900, 600), "#0f172a")
    draw = ImageDraw.Draw(img)
    draw.text((30, 10), "WIRING BLUEPRINT", fill="#3b82f6")
    y = 40
    for line in text.split("\n")[:20]:
        draw.text((30, y), line, fill="#f8fafc")
        y += 25
    img.save("wiring.png")
    return "wiring.png"

# --------------------- STREAMLIT APP ---------------------

def run_st():
    st.set_page_config(page_title="Robot Brain OS", page_icon="🤖", layout="wide")

    if 'user' not in st.session_state: st.session_state['user'] = None
    if 'left_project' not in st.session_state: st.session_state['left_project'] = None
    if 'trial_active' not in st.session_state: st.session_state['trial_active'] = True

    # ----- AUTH -----
    if st.session_state['user'] is None:
        col1, col2, col3 = st.columns([1,2,1])
        with col2:
            st.markdown('<div style="background:#161b22;padding:40px;border-radius:8px;border-top:4px solid #238636;">', unsafe_allow_html=True)
            mode = st.radio("Portal", ["Login", "Sign Up"], horizontal=True)
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.button("Access Dashboard"):
                try:
                    if mode == "Login": st.session_state['user'] = auth.sign_in_with_email_and_password(email, password)
                    else: auth.create_user_with_email_and_password(email, password)
                    st.rerun()
                except: st.error("Authentication Error")
            st.markdown('</div>', unsafe_allow_html=True)
        return

    # ----- MAIN DASHBOARD -----
    email = st.session_state['user']['email']
    username = email.split("@")[0].capitalize()
    projects = get_projects(email)
    projects_left = max(0, 5 - len(projects))
    st.session_state['left_project'] = projects_left
    if len(projects) >= 5: st.session_state['trial_active'] = False

    board, port = detect_board()
    board_status = f"🟢 {board} Connected" if board else "🔴 No Board"

    st.markdown(f"<h3>Welcome, {username}</h3><p>{board_status}</p>", unsafe_allow_html=True)

    # ----- CODE STUDIO -----
    task = st.text_input("Mission Task", value=st.session_state.get('task', 'LED Blink'))
    if st.button("✨ Generate AI Firmware"):
        st.session_state['ai_code'] = generate_ai_code(task, board or "Arduino Uno")
    st.session_state['ai_code'] = st_ace(value=st.session_state.get("ai_code", "// Code here..."), language="c_cpp", theme="monokai", height=400)

    # ----- DEPLOYMENT -----
    if st.button("🔄 Detect Board"): board, port = detect_board()
    if board and st.session_state.get('ai_code'):
        if st.button("⚡ Flash Firmware"):
            with st.spinner("Uploading..."):
                auto_install_libraries(st.session_state['ai_code'])
                res = upload_code_via_agent(st.session_state['ai_code'], board, port)
                if res.get("status") == "success":
                    st.success("🚀 Firmware uploaded successfully!")
                    st.balloons()
                    save_project(email, {"task": task, "code": st.session_state['ai_code'], "board": board, "time_stamp": time.time()})
                else: st.error(f"❌ Upload failed: {res.get('log')}")

# --------------------- BACKGROUND FLASK AGENT ---------------------
def run_f():
    try: run()  # agent.py
    except Exception as e: print(f"Agent Error: {e}")

# --------------------- MAIN EXECUTION ---------------------
if __name__ == "__main__":
    if 'agent_started' not in st.session_state:
        td.Thread(target=run_f, daemon=True).start()
        st.session_state['agent_started'] = True
        time.sleep(2)  # wait for agent
        print("🚀 Flask Agent started")
    run_st()
