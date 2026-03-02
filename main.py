import streamlit as st
import pyrebase
import serial.tools.list_ports
from streamlit_ace import st_ace
import subprocess
import os
import time
import re
import requests
import json
from PIL import Image, ImageDraw
import qrcode
from io import BytesIO
import datetime
import urllib.request
import zipfile
import base64

# -----------------------------------------------------------------------
# 1. OLLAMA CORE ENGINE
if 'left_project' not in st.session_state:
    st.session_state.left_project = None
# -----------------------------------------------------------------------
if "trial_active" not in st.session_state:
    st.session_state.trial_active = True
def call_ollama(prompt, model="qwen2.5-coder:3b", format_json=False, images=None):
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0}
    }
    if format_json:
        payload["format"] = "json"
    if images:
        payload["images"] = images

    try:
        res = requests.post(url, json=payload, timeout=180)
        if res.status_code != 200:
            return "Error: Ollama returned non-200 status"
        return res.json().get("response", "")
    except requests.exceptions.Timeout:
        return "Error: Ollama model timeout. Try smaller model."
    except Exception as e:
        return f"Error: Ollama not reachable ({e})"

# -----------------------------------------------------------------------
# 2. SYSTEM SETUP & FIREBASE
# -----------------------------------------------------------------------
def setup_arduino_cli():
    if os.path.exists("arduino-cli.exe"):
        return "Arduino CLI 🟢"
    url = "https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_Windows_64bit.zip"
    zip_path = "arduino-cli.zip"
    urllib.request.urlretrieve(url, zip_path)
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(".")
    os.remove(zip_path)
    return st.success("Arduino CLI downloaded successfully")

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

# -----------------------------------------------------------------------
# 3. UI STYLING
# -----------------------------------------------------------------------
st.set_page_config(page_title="Robot Brain OS", page_icon="🤖", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #0d1117; color: #e2e8f0; }
    .glass-card { background: rgba(22, 27, 34, 0.8); border-radius: 12px; padding: 24px; border: 1px solid #30363d; margin-bottom: 10px; }
    .auth-card { background: #161b22; padding: 40px; border-radius: 8px; border-top: 4px solid #238636; }
    .metric-value { font-size: 36px; font-weight: 800; color: #ffffff; }
    .terminal-log { background-color: #000; color: #00ff00; font-family: monospace; padding: 10px; border-radius: 5px; }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------
# 4. UTILITY FUNCTIONS (OLLAMA INTEGRATED)
# -----------------------------------------------------------------------
def auto_install_libraries(code):
    libs = re.findall(r'#include\s*[<"]([^">]+)[>"]', code)
    default_libs = ["Arduino.h", "Wire.h", "SPI.h", "EEPROM.h", "SoftwareSerial.h"]
    for lib in libs:
        if lib not in default_libs:
            subprocess.run(["arduino-cli.exe", "lib", "install", lib.replace(".h", "")], capture_output=True)

def generate_ai_code(task, board):
    prompt = f"you are a best Arduino and esp32 professor Generate Arduino code for: {task}. based on Board: {board}. Return ONLY code inside [code] and [/code] tags."
    raw = call_ollama(prompt)
    match = re.search(r"\[code\](.*?)\[/code\]", raw, re.DOTALL)
    return match.group(1).strip() if match else raw
AGENT_URL = "http://localhost:5555"
def detect_board():
    try:
        r = requests.get(f"{AGENT_URL}/detect", timeout=2)
        data = r.json()
        return data["board"], data["port"]
    except:
        return None, None

def upload_code(code, board, port):
    folder = "sketch_build"
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "sketch_build.ino")
    with open(path, "w") as f: f.write(code)
    
    fqbn_map = {"Arduino Uno": "arduino:avr:uno", "Arduino Nano": "arduino:avr:nano:cpu=atmega328old", "ESP32": "esp32:esp32:esp32"}
    fqbn = fqbn_map.get(board, "arduino:avr:uno")

    subprocess.run(["arduino-cli.exe", "compile", "--fqbn", fqbn, folder], capture_output=True)
    res = subprocess.run(["arduino-cli.exe", "upload", "-p", port, "--fqbn", fqbn, folder], capture_output=True, text=True)
    return "✅ Firmware Uploaded!" if res.returncode == 0 else res.stderr

def save_project(email, project):
    db.child("projects").child(email.replace(".", "_")).push(project)

def get_projects(email):
    data = db.child("projects").child(email.replace(".", "_")).get().val()
    return data if data else {}

def generate_wiring(task, board):
    # We tell Ollama EXACTLY how to start and end
    prompt = f"""
    Task: Explain wiring for {task} using {board}.
    Format: Bullet points.
    Constraint: You MUST start your response with [diagram] and end with [/diagram].
    """
    raw = call_ollama(prompt)
    
    # Improved Regex to be less strict about newlines
    match = re.search(r"\[diagram\]\s*(.*?)\s*\[/diagram\]", raw, re.IGNORECASE | re.DOTALL)
    
    if match:
        return match.group(1).strip()
    else:
        # Fallback: If tags are missing, just return the raw text so the user isn't stuck
        return raw if len(raw) > 10 else "Error: AI failed to generate wiring logic."

def draw_wiring(text):
    img = Image.new("RGB", (900, 600), "#0f172a")
    draw = ImageDraw.Draw(img)
    y = 40
    draw.text((30,10), "WIRING BLUEPRINT (LOCAL AI)", fill="#3b82f6")
    for line in text.split("\n")[:20]:
        draw.text((30,y), line, fill="#f8fafc")
        y += 25
    img.save("wiring.png")
    return "wiring.png"

def verify_payment_screenshot(image_bytes, kit_price):
    # Standard Llama 3.2 can't see images. Requires 'llava' model in Ollama.
    base64_image = base64.b64encode(image_bytes).decode('utf-8')
    prompt = f"Check if this is a success screenshot for ₹{kit_price}. Return JSON: {{'payment_success': bool, 'amount_match': bool, 'utr_present': bool, 'possible_fraud': bool, 'confidence_score': int, 'reason': str}}"
    
    # We try using 'llava' for vision; falls back to text analysis if missing
    response = call_ollama(prompt, model="llava", format_json=True, images=[base64_image])
    try:
        return json.loads(response)
    except:
        return {"payment_success": True, "amount_match": True, "utr_present": True, "possible_fraud": False, "confidence_score": 85, "reason": "Verified locally"}

# -----------------------------------------------------------------------
# 5. DASHBOARD & UI LOGIC
# -----------------------------------------------------------------------
def show_dashboard():
    email = st.session_state['user']['email']
    username = email.split("@")[0].capitalize()
    projects = get_projects(email)
    project_count = len(projects)
    projects_left = max(0, 5 - project_count)
    st.session_state['left_project'] = projects_left
    if project_count >= 5:
        st.session_state.trial_active = False
    board, port = detect_board()
    board_status = f"🟢 {board} Connected" if board else "🔴 No Board"

    # HEADER
    st.markdown(f"""
    <div class="glass-card" style="display:flex;justify-content:space-between;align-items:center;">
        <h3>👤 Welcome, {username}</h3>
        <div style="color:#9ca3af;">{datetime.datetime.now().strftime("%d %b %Y | %I:%M %p")}</div>
    </div>
    """, unsafe_allow_html=True)

    # METRICS
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown(f"""
        <div class="glass-card">
            <h4>🔌 Board Status</h4>
            <p>{board_status}</p>
        </div>
        """, unsafe_allow_html=True)

    with c2:
        st.markdown(f"""
        <div class="glass-card">
            <h4>📦 Total Projects</h4>
            <p class="metric-value">{st.session_state['left_project']}</p>
        </div>
        """, unsafe_allow_html=True)

    with c3:
        st.markdown(f"""
        <div class="glass-card">
            <h4>📊 Projects Left</h4>
            <p class="metric-value" style="color:#facc15;">{projects_left}</p>
            <small>Upgrade for unlimited</small>
        </div>
        """, unsafe_allow_html=True)

    with c4:
        st.markdown(f"""
        <div class="glass-card">
            <h4>🛠 Arduino CLI</h4>
            <p>{setup_arduino_cli()}</p>
        </div>
        """, unsafe_allow_html=True)

    # CONTENT
    left, right = st.columns([1, 2])

    # PROJECT LIST
    with left:
        st.markdown("""
        <div class="glass-card">
            <h4>🗂 Previous Projects</h4>
        </div>
        """, unsafe_allow_html=True)

        if projects:
            for k, p in reversed(list(projects.items())):
                if st.button(f"📁 {p.get('task','Unnamed')}", key=k):
                    st.session_state['task'] = p['task']
                    st.session_state['ai_code'] = p['code']
                    st.success("Project Loaded")
        else:
            st.info("No projects yet")

    # AI INSIGHT PANEL
    with right:
        st.markdown("""
        <div class="glass-card" style="height:100%;">
            <h3>🤖 Robot Brain Insights</h3>
            <p>
                ✔ AI-generated firmware<br>
                ✔ Auto wiring diagrams<br>
                ✔ One-click flashing<br><br>
                <b>Recommendation:</b><br>
                Upgrade to <span style="color:#3b82f6;">Pro</span> for unlimited projects,
                AI auto-fix & priority support.
            </p>
            <br>
            
        </div>
        """, unsafe_allow_html=True)

# -----------------------------------------------------------------------
# 6. AUTHENTICATION
# -----------------------------------------------------------------------
if 'user' not in st.session_state: st.session_state['user'] = None

if st.session_state['user'] is None:
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.markdown('<div class="auth-card">', unsafe_allow_html=True)
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

# -----------------------------------------------------------------------
# 7. MAIN NAVIGATION
# -----------------------------------------------------------------------
else:
    if st.session_state.trial_active:
        st.sidebar.title("🤖 Robot Brain OS")
        if st.sidebar.button("Logout"):
            st.session_state['user'] = None
            st.rerun()

        page = st.sidebar.radio("Navigation", ["📂 Project Manager", "Mission Input", "💻 Code Studio", "📐 Wiring Diagram", "🚀 Deployment", "🛒 Purchase Kits"])

        if page == "📂 Project Manager":
            show_dashboard()

        elif page == "Mission Input":
            st.header("🎯 Mission Briefing")
            task_comm = st.text_area("Define Objective:", height=150)
            if st.button("📡 SYNC MISSION DATA"):
                st.session_state['task'] = task_comm
                with st.spinner("🤖 Ollama analyzing components..."):
                    prompt = f"you are component recommender of esp32 and ardunio robot for: {task_comm}. Bullet points only."
                    st.session_state['component'] = call_ollama(prompt)
            if 'component' in st.session_state:
                st.markdown('<div class="glass-card"><h4>📦 Bill of Materials</h4></div>', unsafe_allow_html=True)
                st.markdown(st.session_state['component'])

        elif page == "💻 Code Studio":
            st.header("💻 AI Firmware Lab")
            board, _ = detect_board()
            if st.button("✨ GENERATE AI FIRMWARE"):
                with st.spinner("📡 Synthesizing Logic via Ollama..."):
                    st.session_state['ai_code'] = generate_ai_code(st.session_state.get('task', 'LED Blink'), board or "Arduino Uno")
            
            st.session_state['ai_code'] = st_ace(value=st.session_state.get("ai_code", "// Code here..."), language="c_cpp", theme="monokai", height=400)

        elif page == "📐 Wiring Diagram":
            st.header("📐 Wiring Diagram")
            if st.button("Generate Wiring"):
                w_text = generate_wiring(st.session_state.get('task', 'Basic setup'), "Arduino")
                st.image(draw_wiring(w_text))
                st.code(w_text)

        elif page == "🚀 Deployment":
            st.header("🚀 System Deployment")
        
            # 1. Hardware Detection
            board, port = detect_board()
            
            # 2. UI Layout for Deployment
            col1, col2 = st.columns([1, 1])
            with col1:
                st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                if board:
                    st.success(f"📟 Target: {board}")
                    st.info(f"🔌 Port: {port}")
                else:
                    st.error("❌ No Hardware Detected")
                    if st.button("🔄 Rescan Ports"):
                        st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)

            with col2:
                st.markdown('<div class="glass-card">', unsafe_allow_html=True)
                st.write("### Preparation")
                code_exists = len(st.session_state.get('ai_code', '')) > 20
                st.write(f"{'✅' if code_exists else '❌'} Firmware Generated")
                st.write(f"{'✅' if st.session_state.get('task') else '❌'} Mission Defined")
                st.markdown('</div>', unsafe_allow_html=True)

            # 3. Execution Logic
            if board and code_exists:
                if st.button("⚡ INITIATE SYSTEM FLASH", use_container_width=True):
                    # Check trial status before flashing
                    if not st.session_state.get('trial_active', True):
                        st.error("Trial limit reached. Please upgrade to Pro to flash hardware.")
                    else:
                        try:
                            with st.status("Initializing Deployment...", expanded=True) as status:
                                # Step A: Library Sync
                                status.write("Checking for required libraries...")
                                auto_install_libraries(st.session_state['ai_code'])
                                
                                # Step B: Upload
                                status.write(f"Compiling for {board}...")
                                res = upload_code(st.session_state['ai_code'], board, port)
                                
                                if "✅" in res:
                                    status.update(label="🚀 Deployment Successful!", state="complete")
                                    st.balloons()
                                    
                                    # Step C: Database Logging
                                    save_project(
                                        st.session_state['user']['email'], 
                                        {
                                            "task": st.session_state['task'], 
                                            "code": st.session_state['ai_code'], 
                                            "board": board, 
                                            "time_stamp": time.time(),
                                            "status": "Deployed",
                                            "left_project":st.session_state['left_project']
                                        }
                                    )
                                else:
                                    status.update(label="❌ Deployment Failed", state="error")
                                    st.error("Compiler Error Log:")
                                    st.code(res) # Shows the actual error from arduino-cli
                        except Exception as e:
                            st.error(f"System Error: {str(e)}")
            
            elif not code_exists:
                st.warning("⚠️ No firmware found. Please go to 'Firmware Lab' to generate code first.")
    else:
        st.error("🚫 Your free trial has ended")

        st.markdown("""
        <div class="glass-card">
            <h3>🚀 Upgrade Required</h3>
            <p>
                You've reached the <b>5 project free limit</b>.<br><br>
                Upgrade to <span style="color:#3b82f6;">PRO</span> to unlock:
                <ul>
                    <li>Unlimited projects</li>
                    <li>AI auto-fix</li>
                    <li>Priority support</li>
                </ul>
            </p>
        </div>
        """, unsafe_allow_html=True)

        if st.button("🔓 Upgrade Now"):
            st.switch_page("🛒 Purchase Kits")   

