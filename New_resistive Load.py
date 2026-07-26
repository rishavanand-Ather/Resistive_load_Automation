import sys
import os
import threading
import time
import serial
import serial.tools.list_ports
import ctypes
import requests
import json

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QComboBox, QTabWidget, QFrame, 
                             QLineEdit, QStackedWidget, QGridLayout, QTextBrowser, 
                             QGraphicsOpacityEffect, QDialog, QMessageBox, QScrollArea,
                             QProgressDialog)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread, QTimer
from PyQt6.QtGui import QPixmap, QFont, QIcon, QPainter, QPainterPath, QBrush, QColor
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QThread, QTimer, QRect
# ==========================================
# ASSET CONFIGURATION & FILE PATHS
# ==========================================
ASSETS = {
    "ICON": "logo.png",
    "LOCK_LOGO": "logo.png",
    "PROFILE_PIC": "profile.jpg",
    "BANNER_PIC": "banner.jpg",
    "CKT_DIAGRAM": "circuit_diagram.png",
    "INO_FILE": "resistiveLoadwithShunt.ino",
    "GUI_FILE": "New_resistive Load.py",
    "README": "readme.txt"
}

# ==========================================
# AUTO-UPDATER CONFIGURATION
# ==========================================
CURRENT_VERSION = "v4.0"
GITHUB_REPO = "rishavanand-Ather/Resistive_load_Automation"  # <--- UPDATE THIS TO YOUR GITHUB REPO!
EXE_NAME = "Battery Discharger.exe"          # <--- The exact name of your compiled .exe

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# ==========================================
# BACKGROUND THREADS (Serial & Updater)
# ==========================================
class SerialWorker(QObject):
    log_received = pyqtSignal(str)
    telemetry_received = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self.ser = None
        self.running = False

    def connect_serial(self, port):
        try:
            self.ser = serial.Serial(port, 115200, timeout=1)
            self.running = True
            threading.Thread(target=self._read_loop, daemon=True).start()
            return True, f"Connected to {port} at 115200 baud."
        except Exception as e:
            return False, str(e)

    def disconnect_serial(self):
        self.running = False
        if self.ser and self.ser.is_open:
            self.ser.close()
        self.ser = None

    def send_cmd(self, cmd):
        if self.ser and self.ser.is_open:
            self.ser.write((cmd + "\n").encode())
            self.log_received.emit(f">>> SENT: {cmd}")

    def _read_loop(self):
        while self.running and self.ser and self.ser.is_open:
            try:
                line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                if line:
                    self.log_received.emit(line)
                    if line.startswith("[LOG]"):
                        self._parse_telemetry(line)
            except Exception as e:
                self.log_received.emit(f"SERIAL DISCONNECT/CRASH: {str(e)}")
                break
                
    def _parse_telemetry(self, line):
        try:
            parts = line.split("|")
            data = {
                "V": parts[0].split(":")[1].replace("V", "").strip(),
                "I": parts[1].split(":")[1].replace("A", "").strip(),
                "R": parts[2].split(":")[1].replace("Ohm", "").strip(),
                "Req": parts[3].split(":")[1].replace("A", "").strip(),
                "Mode": parts[4].split(":")[1].strip(),
                "Ah": parts[5].split(":")[1].replace("Ah", "").strip()
            }
            self.telemetry_received.emit(data)
        except Exception:
            pass

class UpdateCheckerThread(QThread):
    update_available = pyqtSignal(str, str) # version, asset_url
    no_update = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, manual_check=False):
        super().__init__()
        self.manual_check = manual_check

    def run(self):
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                latest_version = data.get("tag_name", "")
                
                if latest_version and latest_version != CURRENT_VERSION:
                    asset_url = None
                    for asset in data.get("assets", []):
                        if asset.get("name", "").endswith(".exe"):
                            asset_url = asset.get("browser_download_url")
                            break
                    
                    if asset_url:
                        self.update_available.emit(latest_version, asset_url)
                        return
                        
                self.no_update.emit()
            else:
                self.error.emit(f"GitHub API Error: HTTP {response.status_code}")
        except Exception as e:
            self.error.emit(f"Network error: {str(e)}")

class DownloaderThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, download_url):
        super().__init__()
        self.download_url = download_url
        self.temp_filename = "update_temp.exe"

    def run(self):
        try:
            response = requests.get(self.download_url, stream=True, timeout=15)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            
            with open(self.temp_filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if total_size > 0:
                            percent = int((downloaded_size / total_size) * 100)
                            self.progress.emit(percent)
                            
            self.finished.emit(self.temp_filename)
        except Exception as e:
            self.error.emit(f"Download failed: {str(e)}")


# ==========================================
# MAIN GUI APPLICATION
# ==========================================
class BatteryRigGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Battery Rig Master Studio {CURRENT_VERSION} (PyQt6)")
        self.setWindowIcon(QIcon(resource_path(ASSETS["ICON"])))
        self.resize(1100, 750)
        
        self.setStyleSheet("""
            QMainWindow { background-color: #0b0f19; }
            QWidget { color: #e2e8f0; font-family: 'Segoe UI', sans-serif; }
            QTabWidget::pane { border: 1px solid #334155; border-radius: 5px; background: #0b0f19; }
            QTabBar::tab { background: #1e293b; color: #94a3b8; padding: 10px 20px; font-weight: bold; border-top-left-radius: 4px; border-top-right-radius: 4px; }
            QTabBar::tab:selected { background: #10b981; color: #000000; }
            QFrame#Card { background-color: #161e2e; border: 1px solid #334155; border-radius: 10px; }
            QPushButton { background-color: #3b82f6; color: white; border-radius: 5px; padding: 8px 15px; font-weight: bold; border: none; }
            QPushButton:hover { background-color: #2563eb; }
            QPushButton#ConnectBtn { background-color: #10b981; color: black; }
            QPushButton#ConnectBtn:hover { background-color: #059669; }
            QPushButton#DisconnectBtn { background-color: #ef4444; color: white; }
            QLineEdit, QComboBox { background-color: #0f172a; border: 1px solid #334155; padding: 5px; border-radius: 4px; color: white; }
            QTextBrowser { background-color: #09090b; color: #38bdf8; border: 1px solid #334155; border-radius: 5px; font-family: 'Consolas'; }
        """)

        # Initialize hidden debug console
        self.setup_debug_window()
        self.sys_log("Application Initialized. System Booting...")

        self.serial_worker = SerialWorker()
        self.serial_worker.log_received.connect(self.update_serial_log)
        self.serial_worker.telemetry_received.connect(self.update_telemetry)

        self.setup_ui()
        self.sys_log("UI Setup Complete. Ready for user interaction.")
        
        # Trigger background check on boot (2-second delay so UI loads first)
        QTimer.singleShot(2000, lambda: self.check_for_updates(manual=False))

    # ==========================================
    # LOGGING & DEBUG WINDOW
    # ==========================================
    def sys_log(self, msg):
        timestamp = time.strftime("%H:%M:%S")
        full_msg = f"[{timestamp}] [SYSTEM] {msg}"
        self.txt_debug.append(full_msg)
        print(full_msg)

    def update_serial_log(self, text):
        timestamp = time.strftime("%H:%M:%S")
        self.txt_debug.append(f"[{timestamp}] [SERIAL] {text}")

    def setup_debug_window(self):
        self.debug_dialog = QDialog(self)
        self.debug_dialog.setWindowTitle("System Debug & Raw Data Console")
        self.debug_dialog.resize(750, 500)
        self.debug_dialog.setStyleSheet("background-color: #0b0f19;")
        lay = QVBoxLayout(self.debug_dialog)
        
        self.txt_debug = QTextBrowser()
        self.txt_debug.setStyleSheet("background-color: #000000; color: #00ff00; font-family: Consolas; font-size: 12px;")
        lay.addWidget(self.txt_debug)
        
        btn_clear = QPushButton("Clear Console")
        btn_clear.setStyleSheet("background-color: #ef4444; color: white; font-weight: bold;")
        btn_clear.clicked.connect(lambda: [self.txt_debug.clear(), self.sys_log("Console Cleared by User")])
        lay.addWidget(btn_clear)

    # ==========================================
    # UI CONSTRUCTION
    # ==========================================
    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(15, 15, 15, 15)

        # --- HEADER ---
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("COM Port:"))
        self.port_cb = QComboBox()
        self.port_cb.addItems([port.device for port in serial.tools.list_ports.comports()])
        self.port_cb.setFixedWidth(120)
        header_layout.addWidget(self.port_cb)
        
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setObjectName("ConnectBtn")
        self.btn_connect.clicked.connect(self.toggle_connection)
        header_layout.addWidget(self.btn_connect)
        
        header_layout.addStretch() 
        
        # New "Check for Updates" Button
        self.btn_update_check = QPushButton("Check Updates")
        self.btn_update_check.setStyleSheet("background-color: #27ae60; color: white;")
        self.btn_update_check.clicked.connect(lambda: self.check_for_updates(manual=True))
        header_layout.addWidget(self.btn_update_check)
        
        self.btn_debug = QPushButton("Debug Console")
        self.btn_debug.setStyleSheet("background-color: #f59e0b; color: black;")
        self.btn_debug.clicked.connect(self.debug_dialog.show)
        header_layout.addWidget(self.btn_debug)
        
        self.btn_about = QPushButton("About Me")
        self.btn_about.setStyleSheet("background-color: #8b5cf6; color: white;")
        self.btn_about.clicked.connect(self.show_about_window)
        header_layout.addWidget(self.btn_about)
        
        main_layout.addLayout(header_layout)

        # --- TABS ---
        self.tabs = QTabWidget()
        self.tabs.currentChanged.connect(self.lock_all_code_tabs)
        main_layout.addWidget(self.tabs)

        self.build_control_tab()
        self.build_calib_tab()
        self.build_pins_tab()
        self.build_source_code_tab()

    # ==========================================
    # TAB 1: CONTROL & MONITOR
    # ==========================================
    def build_control_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        card = QFrame()
        card.setObjectName("Card")
        card_layout = QHBoxLayout(card)
        self.lbl_v = self.create_metric_widget(card_layout, "Volts:", "0.00 V", "#10b981")
        self.lbl_i = self.create_metric_widget(card_layout, "Current:", "0.00 A", "#38bdf8")
        self.lbl_r = self.create_metric_widget(card_layout, "Resistance:", "0.000 Ω", "#f59e0b")
        self.lbl_req = self.create_metric_widget(card_layout, "Relay Req:", "0 A", "#ffffff")
        self.lbl_ah = self.create_metric_widget(card_layout, "Capacity:", "0.00 Ah", "#ef4444")
        layout.addWidget(card)

        ctrl_card = QFrame()
        ctrl_card.setObjectName("Card")
        ctrl_layout = QHBoxLayout(ctrl_card)
        ctrl_layout.addWidget(QLabel("Request Load (Amps):"))
        self.ent_load = QLineEdit("25")
        self.ent_load.setFixedWidth(100)
        ctrl_layout.addWidget(self.ent_load)
        btn_set = QPushButton("Set Amps (ireq)")
        btn_set.clicked.connect(lambda: self.serial_worker.send_cmd(f"ireq {self.ent_load.text()}"))
        ctrl_layout.addWidget(btn_set)
        ctrl_layout.addStretch()
        
        layout.addWidget(ctrl_card)
        layout.addStretch()
        self.tabs.addTab(tab, "Control & Monitor")

    def create_metric_widget(self, parent_layout, title, default_val, color):
        container = QWidget()
        lay = QVBoxLayout(container)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("color: #94a3b8; font-size: 12px;")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_val = QLabel(default_val)
        lbl_val.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: bold;")
        lbl_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl_title)
        lay.addWidget(lbl_val)
        parent_layout.addWidget(container)
        return lbl_val

    # ==========================================
    # TAB 2 & 3: CALIBRATION AND PINS
    # ==========================================
    def build_calib_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        card = QFrame()
        card.setObjectName("Card")
        c_lay = QGridLayout(card)
        c_lay.addWidget(QLabel("Hardware Calibration (Averaged 10-Sample)"), 0, 0, 1, 3)
        
        c_lay.addWidget(QLabel("Meter Volts:"), 1, 0)
        self.ent_v = QLineEdit()
        c_lay.addWidget(self.ent_v, 1, 1)
        btn_v = QPushButton("Calibrate V")
        btn_v.clicked.connect(lambda: self.serial_worker.send_cmd(f"calib_v {self.ent_v.text()}"))
        c_lay.addWidget(btn_v, 1, 2)

        c_lay.addWidget(QLabel("Meter Amps:"), 2, 0)
        self.ent_i = QLineEdit()
        c_lay.addWidget(self.ent_i, 2, 1)
        btn_i = QPushButton("Calibrate I")
        btn_i.clicked.connect(lambda: self.serial_worker.send_cmd(f"calib_i {self.ent_i.text()}"))
        c_lay.addWidget(btn_i, 2, 2)
        
        lay.addWidget(card)
        lay.addStretch()
        self.tabs.addTab(tab, "Calibration")

    def build_pins_tab(self):
        tab = QWidget()
        lay = QVBoxLayout(tab)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background-color: transparent;")
        scroll_content = QWidget()
        scroll_lay = QVBoxLayout(scroll_content)
        
        img_lbl = QLabel()
        ckt_path = resource_path(ASSETS["CKT_DIAGRAM"])
        pix = QPixmap(ckt_path)
        if not pix.isNull():
            img_lbl.setPixmap(pix.scaledToWidth(800, Qt.TransformationMode.SmoothTransformation))
            self.sys_log(f"IMAGE SUCCESS: Loaded circuit diagram '{ckt_path}'")
        else:
            self.sys_log(f"IMAGE FAIL: Could not load '{ckt_path}'")
            img_lbl.setText("[ Circuit Diagram Image Missing ]")
            img_lbl.setStyleSheet("color: #ef4444; font-size: 16px; font-weight: bold;")
            
        img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll_lay.addWidget(img_lbl)
        
        txt = QTextBrowser()
        txt.setPlainText("Pin 47: Nominal Switch\nPin 48: Serial Mode Switch\nPin 49: Auto Mode Switch\n\nPin A0/A1: Shunt Differential\nPin A2: Voltage Divider\n\nRelays: Pins 13 down to 3")
        txt.setFixedHeight(150)
        scroll_lay.addWidget(txt)
        
        scroll.setWidget(scroll_content)
        lay.addWidget(scroll)
        self.tabs.addTab(tab, "Circuit & Pins")

    # ==========================================
    # TAB 4: SECURE SOURCE CODE
    # ==========================================
    def build_source_code_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.code_tabs = QTabWidget()
        self.code_tabs.currentChanged.connect(self.lock_all_code_tabs)

        def build_secure_tab(title, dev_name, dev_email, correct_pin, code_content):
            main_widget = QWidget()
            main_lay = QVBoxLayout(main_widget)
            stack = QStackedWidget()
            
            lock_screen = QWidget()
            lock_lay = QVBoxLayout(lock_screen)
            lock_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            card = QFrame()
            card.setFixedSize(550, 300) 
            card.setStyleSheet("QFrame { border: 1px solid #7f8c8d; border-radius: 15px; background-color: #161e2e;}")
            card_lay = QHBoxLayout(card) 
            
            logo = QLabel()
            logo_path = resource_path(ASSETS["LOCK_LOGO"])
            logo_pix = QPixmap(logo_path)
            if not logo_pix.isNull():
                logo.setPixmap(logo_pix.scaled(170, 170, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            logo.setStyleSheet("border: none; background: transparent;")
            
            form_lay = QVBoxLayout()
            lbl_title = QLabel(f"<h2 style='margin:0;'>{title}</h2><p style='margin:0; color:#94a3b8;'>Restricted Access</p>")
            lbl_title.setStyleSheet("border: none; background: transparent;")
            lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            
            pin_input = QLineEdit()
            pin_input.setEchoMode(QLineEdit.EchoMode.Password)
            pin_input.setPlaceholderText("Enter PIN...")
            pin_input.setFixedSize(220, 45)
            pin_input.setStyleSheet("background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; font-size: 18px;")
            
            btn_lay = QHBoxLayout()
            btn_unlock = QPushButton("Unlock")
            btn_unlock.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 10px;")
            btn_get_pin = QPushButton("Get PIN")
            btn_get_pin.setStyleSheet("background-color: #2980b9; color: white; font-weight: bold; padding: 10px;")
            btn_lay.addWidget(btn_unlock)
            btn_lay.addWidget(btn_get_pin)
            
            form_lay.addWidget(lbl_title)
            form_lay.addWidget(pin_input)
            form_lay.addLayout(btn_lay)
            card_lay.addWidget(logo)
            card_lay.addLayout(form_lay)
            lock_lay.addWidget(card)
            
            code_screen = QWidget()
            code_grid = QGridLayout(code_screen)
            
            bg_logo = QLabel()
            if not logo_pix.isNull():
                bg_logo.setPixmap(logo_pix.scaled(400, 400, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            bg_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
            op = QGraphicsOpacityEffect()
            op.setOpacity(0.05) 
            bg_logo.setGraphicsEffect(op)
            code_grid.addWidget(bg_logo, 0, 0)
            
            code_text = QTextBrowser()
            code_text.setPlainText(code_content)
            code_text.setStyleSheet("background: transparent; font-family: Consolas; font-size: 14px; border: none; color: #38bdf8;")
            code_grid.addWidget(code_text, 0, 0)
            
            stack.addWidget(lock_screen)
            stack.addWidget(code_screen)
            main_lay.addWidget(stack)
            
            btn_unlock.clicked.connect(lambda: self.unlock_code(pin_input.text(), correct_pin, stack, pin_input, title))
            btn_get_pin.clicked.connect(lambda: self.show_contact_dev(dev_name, dev_email))
            
            return main_widget, stack, pin_input

        # Load Arduino Code
        try:
            with open(resource_path(ASSETS["INO_FILE"]), "r", encoding="utf-8") as file:
                ard_content = file.read()
                self.sys_log(f"FILE SUCCESS: Loaded {ASSETS['INO_FILE']} into memory.")
        except Exception as e:
            ard_content = f"// Error loading file: {str(e)}"
            
        ard_tab, self.ard_stack, self.ard_pin = build_secure_tab("Arduino Source Code", "Rishav Anand", "rishav.anand@atherenergy.com", "8235", ard_content)
        
        # Load GUI Code
        try:
            with open(resource_path(ASSETS["GUI_FILE"]), "r", encoding="utf-8") as file:
                gui_content = file.read()
                self.sys_log(f"FILE SUCCESS: Loaded {ASSETS['GUI_FILE']} into memory.")
        except Exception as e:
            gui_content = f"// Error loading Python script: {str(e)}"
                
        gui_tab, self.gui_stack, self.gui_pin = build_secure_tab("GUI Source Code", "Rishav Anand", "rishav.anand@atherenergy.com", "8235G", gui_content)

        self.code_tabs.addTab(ard_tab, "Arduino Code")
        self.code_tabs.addTab(gui_tab, "GUI Python Code")
        layout.addWidget(self.code_tabs)
        self.tabs.addTab(tab, "Source Code")

    def unlock_code(self, entered_pin, correct_pin, stack_widget, input_widget, title):
        if entered_pin == correct_pin:
            stack_widget.setCurrentIndex(1)
            self.sys_log(f"SECURITY ALERT: Valid PIN entered. {title} unlocked.")
        else:
            input_widget.clear()
            self.sys_log(f"SECURITY ALERT: Failed unlock attempt for {title}. Incorrect PIN.")
            QMessageBox.warning(self, "Access Denied", "Incorrect Security PIN.")

    def lock_all_code_tabs(self, index=None):
        locked = False
        if hasattr(self, 'ard_stack') and self.ard_stack.currentIndex() != 0:
            self.ard_stack.setCurrentIndex(0)
            self.ard_pin.clear()
            locked = True
        if hasattr(self, 'gui_stack') and self.gui_stack.currentIndex() != 0:
            self.gui_stack.setCurrentIndex(0)
            self.gui_pin.clear()
            locked = True
        if locked:
            self.sys_log("UI EVENT: Tab focus changed. All source code screens auto-locked.")

    # ==========================================
    # AUTO-UPDATE LOGIC
    # ==========================================
    def check_for_updates(self, manual=False):
        if manual:
            self.sys_log("SYSTEM ACTION: Manually checking for updates via GitHub API...")
            
        self.update_thread = UpdateCheckerThread(manual_check=manual)
        self.update_thread.update_available.connect(self.prompt_update)
        
        if manual:
            self.update_thread.no_update.connect(lambda: QMessageBox.information(self, "Up to Date", f"You are running the latest version ({CURRENT_VERSION})."))
            self.update_thread.error.connect(lambda msg: QMessageBox.warning(self, "Update Error", msg))
            
        self.update_thread.start()

    def prompt_update(self, latest_version, asset_url):
        self.sys_log(f"SYSTEM NOTIFICATION: Update {latest_version} is available.")
        
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Update Available")
        msg_box.setText(f"A new version ({latest_version}) is available!\n\nWould you like to update now?")
        msg_box.setStyleSheet("background-color: #161e2e; color: white;")
        
        btn_update = msg_box.addButton("Update Now", QMessageBox.ButtonRole.AcceptRole)
        btn_update.setStyleSheet("background-color: #10b981; color: black; font-weight: bold; padding: 5px;")
        
        btn_snooze = msg_box.addButton("Snooze (5 Hours)", QMessageBox.ButtonRole.RejectRole)
        btn_snooze.setStyleSheet("background-color: #ef4444; color: white; font-weight: bold; padding: 5px;")
        
        msg_box.exec()
        
        if msg_box.clickedButton() == btn_update:
            self.start_download(asset_url)
        elif msg_box.clickedButton() == btn_snooze:
            self.sys_log("SYSTEM ACTION: Update snoozed for 5 hours.")
            QTimer.singleShot(18000000, lambda: self.check_for_updates(manual=False))

    def start_download(self, asset_url):
        self.sys_log("SYSTEM ACTION: Downloading update...")
        
        self.progress_dialog = QProgressDialog("Downloading update...", "Cancel", 0, 100, self)
        self.progress_dialog.setWindowTitle("Updating System")
        self.progress_dialog.setStyleSheet("background-color: #0b0f19; color: white;")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setAutoClose(True)
        self.progress_dialog.show()

        self.download_thread = DownloaderThread(asset_url)
        self.download_thread.progress.connect(self.progress_dialog.setValue)
        self.download_thread.finished.connect(self.apply_update)
        self.download_thread.error.connect(lambda msg: QMessageBox.critical(self, "Download Error", msg))
        
        self.progress_dialog.canceled.connect(self.download_thread.terminate)
        self.download_thread.start()

    def apply_update(self, temp_filename):
        self.sys_log("SYSTEM ACTION: Download complete. Preparing to hot-swap executable.")
        
        bat_content = f"""@echo off
echo Applying update... Please wait.
timeout /t 3 /nobreak > NUL
move /Y "{temp_filename}" "{EXE_NAME}"
start "" "{EXE_NAME}"
del "%~f0"
"""
        bat_filename = "updater.bat"
        try:
            with open(bat_filename, "w") as f:
                f.write(bat_content)
                
            os.startfile(bat_filename)
            sys.exit(0) 
            
        except Exception as e:
            self.sys_log(f"SYSTEM CRASH: Failed to write or execute updater script: {str(e)}")
            QMessageBox.critical(self, "Update Failed", f"Could not apply update: {str(e)}")

    # ==========================================
    # ABOUT WINDOW (Circular Image / Banner)
    # ==========================================
    # ==========================================
    # ABOUT WINDOW (Circular Image / Banner)
    # ==========================================
    def create_circular_pixmap(self, image_path, size):
        pixmap = QPixmap(image_path)
        if pixmap.isNull(): return QPixmap()
        
        # Scale proportionally to fill the square
        pixmap = pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        
        # Crop exactly to the center so the circle draws perfectly
        crop_rect = QRect((pixmap.width() - size) // 2, (pixmap.height() - size) // 2, size, size)
        pixmap = pixmap.copy(crop_rect)
        
        out_pixmap = QPixmap(size, size)
        out_pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(out_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        return out_pixmap

    def show_about_window(self):
        self.sys_log("UI EVENT: About Developer window opened.")
        dlg = QDialog(self)
        dlg.setWindowTitle("About Developer")
        dlg.resize(550, 650)
        dlg.setStyleSheet("background-color: #161e2e;")
        
        header = QFrame(dlg)
        header.setGeometry(0, 0, 550, 180)
        
        # --- FIXED BANNER LOGIC ---
        banner_lbl = QLabel(header)
        banner_lbl.setGeometry(0, 0, 550, 120)
        banner_path = resource_path(ASSETS["BANNER_PIC"])
        banner_pix = QPixmap(banner_path)
        
        if not banner_pix.isNull():
            # Scale proportionally without squishing, then crop the overflow
            banner_pix = banner_pix.scaled(550, 120, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            crop_rect = QRect((banner_pix.width() - 550) // 2, (banner_pix.height() - 120) // 2, 550, 120)
            banner_pix = banner_pix.copy(crop_rect)
            banner_lbl.setPixmap(banner_pix)
        else:
            banner_lbl.setStyleSheet("background-color: #334155;")
            
        # --- FIXED PROFILE LOGIC ---
        profile_lbl = QLabel(header)
        profile_lbl.setGeometry(215, 60, 120, 120)
        
        # CRITICAL FIX: Make the label background transparent so it doesn't block the banner
        profile_lbl.setStyleSheet("background-color: transparent;") 
        
        prof_path = resource_path(ASSETS["PROFILE_PIC"])
        prof_pix = self.create_circular_pixmap(prof_path, 120)
        
        if not prof_pix.isNull():
            profile_lbl.setPixmap(prof_pix)
        else:
            # Fallback if image is missing
            profile_lbl.setStyleSheet("background-color: #ef4444; border-radius: 60px;")

        # Details Layout (Below Header)
        details = QWidget(dlg)
        details.setGeometry(20, 190, 510, 440)
        lay = QVBoxLayout(details)
        lay.setContentsMargins(0, 0, 0, 0)
        
        lay.addWidget(QLabel("<h2 align='center' style='margin:0;'>Rishav Anand</h2>"))
        email = QLabel("<div align='center'><a href='mailto:rishav.anand@atherenergy.com' style='color:#38bdf8; text-decoration:none;'>rishav.anand@atherenergy.com</a></div>")
        email.setOpenExternalLinks(True)
        lay.addWidget(email)
        
        txt_readme = QTextBrowser()
        txt_readme.setStyleSheet("background-color: #0b0f19; color: white; border: 1px solid #334155; padding: 10px; margin-top: 10px;")
        try:
            with open(resource_path(ASSETS["README"]), "r", encoding="utf-8") as f:
                txt_readme.setPlainText(f.read())
        except Exception as e:
            txt_readme.setPlainText(f"Error loading {ASSETS['README']}: {str(e)}")
            
        lay.addWidget(txt_readme)
        dlg.exec()
        
        
        
    # def show_about_window(self):
    #     self.sys_log("UI EVENT: About Developer window opened.")
    #     dlg = QDialog(self)
    #     dlg.setWindowTitle("About Developer")
    #     dlg.resize(550, 650)
    #     dlg.setStyleSheet("background-color: #161e2e;")
        
    #     header = QFrame(dlg)
    #     header.setGeometry(0, 0, 550, 180)
        
    #     banner_lbl = QLabel(header)
    #     banner_lbl.setGeometry(0, 0, 550, 120)
    #     banner_path = resource_path(ASSETS["BANNER_PIC"])
    #     banner_pix = QPixmap(banner_path)
    #     if not banner_pix.isNull():
    #         banner_lbl.setPixmap(banner_pix.scaled(550, 120, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation))
    #     else:
    #         banner_lbl.setStyleSheet("background-color: #334155;")
            
    #     profile_lbl = QLabel(header)
    #     profile_lbl.setGeometry(215, 60, 120, 120) 
    #     prof_path = resource_path(ASSETS["PROFILE_PIC"])
    #     prof_pix = self.create_circular_pixmap(prof_path, 120)
    #     if not prof_pix.isNull():
    #         profile_lbl.setPixmap(prof_pix)
    #     else:
    #         profile_lbl.setStyleSheet("background-color: #ef4444; border-radius: 60px;")

    #     details = QWidget(dlg)
    #     details.setGeometry(20, 190, 510, 440)
    #     lay = QVBoxLayout(details)
    #     lay.setContentsMargins(0, 0, 0, 0)
        
    #     lay.addWidget(QLabel("<h2 align='center' style='margin:0;'>Rishav Anand</h2>"))
    #     email = QLabel("<div align='center'><a href='mailto:rishav.anand@atherenergy.com' style='color:#38bdf8; text-decoration:none;'>rishav.anand@atherenergy.com</a></div>")
    #     email.setOpenExternalLinks(True)
    #     lay.addWidget(email)
        
    #     txt_readme = QTextBrowser()
    #     txt_readme.setStyleSheet("background-color: #0b0f19; color: white; border: 1px solid #334155; padding: 10px; margin-top: 10px;")
    #     try:
    #         with open(resource_path(ASSETS["README"]), "r", encoding="utf-8") as f:
    #             txt_readme.setPlainText(f.read())
    #     except Exception as e:
    #         txt_readme.setPlainText(f"Error loading {ASSETS['README']}: {str(e)}")
            
    #     lay.addWidget(txt_readme)
    #     dlg.exec()

    def show_contact_dev(self, name, email):
        msg = QMessageBox(self)
        msg.setWindowTitle("Developer Contact")
        msg.setText(f"Developer: {name}<br>Email: <a href='mailto:{email}' style='color:#38bdf8;'>{email}</a>")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setStyleSheet("background-color: #161e2e; color: white;")
        msg.exec()

    # ==========================================
    # SERIAL ACTIONS
    # ==========================================
    def toggle_connection(self):
        if not self.serial_worker.running:
            port = self.port_cb.currentText()
            if not port: return
            self.sys_log(f"SERIAL ACTION: Attempting connection to {port}...")
            success, msg = self.serial_worker.connect_serial(port)
            if success:
                self.sys_log(f"SERIAL SUCCESS: {msg}")
                self.btn_connect.setText("Disconnect")
                self.btn_connect.setObjectName("DisconnectBtn")
                self.btn_connect.style().unpolish(self.btn_connect)
                self.btn_connect.style().polish(self.btn_connect)
                time.sleep(0.5)
                self.serial_worker.send_cmd("logi")
            else:
                self.sys_log(f"SERIAL CRASH: {msg}")
                QMessageBox.critical(self, "Connection Error", msg)
        else:
            self.sys_log("SERIAL ACTION: Disconnecting from port.")
            self.serial_worker.disconnect_serial()
            self.btn_connect.setText("Connect")
            self.btn_connect.setObjectName("ConnectBtn")
            self.btn_connect.style().unpolish(self.btn_connect)
            self.btn_connect.style().polish(self.btn_connect)

    def update_telemetry(self, data):
        self.lbl_v.setText(f"{float(data.get('V', 0)):.2f} V")
        self.lbl_i.setText(f"{float(data.get('I', 0)):.2f} A")
        self.lbl_r.setText(f"{float(data.get('R', 0)):.3f} Ω")
        self.lbl_req.setText(f"{data.get('Req', 0)} A")
        self.lbl_ah.setText(f"{float(data.get('Ah', 0)):.2f} Ah")

# ==========================================
# EXECUTION ENTRY POINT
# ==========================================
if __name__ == "__main__":
    try:
        myappid = 'ather.batteryrig.masterstudio.5' 
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass 
        
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource_path(ASSETS["ICON"])))
    window = BatteryRigGUI()
    window.show()
    sys.exit(app.exec())