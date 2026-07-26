import sys
import os
import threading
import time
import serial
import serial.tools.list_ports
import ctypes

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QComboBox, QTabWidget, QFrame, 
                             QLineEdit, QStackedWidget, QGridLayout, QTextBrowser, 
                             QGraphicsOpacityEffect, QDialog, QMessageBox, QScrollArea)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QPixmap, QFont, QIcon, QPainter, QPainterPath, QBrush, QColor

# ==========================================
# ASSET CONFIGURATION & FILE PATHS
# Edit these filenames if your files change
# ==========================================
ASSETS = {
    "ICON": "logo.png",
    "LOCK_LOGO": "logo.png",
    "PROFILE_PIC": "profile.jpg",
    "BANNER_PIC": "banner.jpg",
    "CKT_DIAGRAM": "ckt_diagram.png",
    "INO_FILE": "resistiveLoadwithShunt.ino",
    "GUI_FILE": "New_resistive Load.py",
    "README": "readme.txt"
}

# --- Helper for PyInstaller resource paths ---
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- Thread-Safe Serial Worker ---
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

# --- Main GUI Application ---
class BatteryRigGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Battery Rig Master Studio v4.0 (PyQt6)")
        self.setWindowIcon(QIcon(resource_path(ASSETS["ICON"])))
        self.resize(1050, 750)
        
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

        # Initialize hidden debug console FIRST so we can log setup events
        self.setup_debug_window()
        self.sys_log("Application Initialized. System Booting...")

        self.serial_worker = SerialWorker()
        self.serial_worker.log_received.connect(self.update_serial_log)
        self.serial_worker.telemetry_received.connect(self.update_telemetry)

        self.setup_ui()
        self.sys_log("UI Setup Complete. Ready for user interaction.")

    # ==========================================
    # GLOBAL SYSTEM LOGGER
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
        
        # Scroll area in case diagram is large
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background-color: transparent;")
        scroll_content = QWidget()
        scroll_lay = QVBoxLayout(scroll_content)
        
        # Circuit Diagram Image
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
        
        # Text mapping fallback
        txt = QTextBrowser()
        txt.setPlainText("Pin 47: Nominal Switch\nPin 48: Serial Mode Switch\nPin 49: Auto Mode Switch\n\nPin A0/A1: Shunt Differential\nPin A2: Voltage Divider\n\nRelays: Pins 13 down to 3")
        txt.setFixedHeight(150)
        scroll_lay.addWidget(txt)
        
        scroll.setWidget(scroll_content)
        lay.addWidget(scroll)
        self.tabs.addTab(tab, "Circuit & Pins")
        self.sys_log("Circuit & Pins Tab built.")

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
            
            # --- LOCK SCREEN ---
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
                self.sys_log(f"IMAGE SUCCESS: Loaded lock-screen logo '{logo_path}'")
                logo.setPixmap(logo_pix.scaled(170, 170, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            else:
                self.sys_log(f"IMAGE FAIL: Could not load logo '{logo_path}'")
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
            
            # --- SOURCE CODE SCREEN ---
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

        # 1. Load Arduino Code
        try:
            with open(resource_path(ASSETS["INO_FILE"]), "r", encoding="utf-8") as file:
                ard_content = file.read()
                self.sys_log(f"FILE SUCCESS: Loaded {ASSETS['INO_FILE']} into memory.")
        except Exception as e:
            ard_content = f"// Error loading file: {str(e)}"
            self.sys_log(f"FILE FAIL: {str(e)}")
            
        ard_tab, self.ard_stack, self.ard_pin = build_secure_tab("Arduino Source Code", "Rishav Anand", "rishav.anand@atherenergy.com", "8235", ard_content)
        
        # 2. Load GUI Code
        try:
            with open(resource_path(ASSETS["GUI_FILE"]), "r", encoding="utf-8") as file:
                gui_content = file.read()
                self.sys_log(f"FILE SUCCESS: Loaded {ASSETS['GUI_FILE']} into memory.")
        except Exception as e:
            gui_content = f"// Error loading Python script: {str(e)}"
            self.sys_log(f"FILE FAIL: {str(e)}")
                
        gui_tab, self.gui_stack, self.gui_pin = build_secure_tab("GUI Source Code", "Rishav Anand", "rishav.anand@atherenergy.com", "8235G", gui_content)

        self.code_tabs.addTab(ard_tab, "Arduino Code")
        self.code_tabs.addTab(gui_tab, "GUI Python Code")
        layout.addWidget(self.code_tabs)
        self.tabs.addTab(tab, "Source Code")

    # ==========================================
    # SECURITY & LOCK MECHANICS
    # ==========================================
    def unlock_code(self, entered_pin, correct_pin, stack_widget, input_widget, title):
        if entered_pin == correct_pin:
            stack_widget.setCurrentIndex(1)
            self.sys_log(f"SECURITY ALERT: Valid PIN entered. {title} unlocked.")
        else:
            input_widget.clear()
            self.sys_log(f"SECURITY ALERT: Failed unlock attempt for {title}. Incorrect PIN.")
            QMessageBox.warning(self, "Access Denied", "Incorrect Security PIN.")

    def lock_all_code_tabs(self, index=None):
        locked_something = False
        if hasattr(self, 'ard_stack') and self.ard_stack.currentIndex() != 0:
            self.ard_stack.setCurrentIndex(0)
            self.ard_pin.clear()
            locked_something = True
        
        if hasattr(self, 'gui_stack') and self.gui_stack.currentIndex() != 0:
            self.gui_stack.setCurrentIndex(0)
            self.gui_pin.clear()
            locked_something = True
            
        if locked_something:
            self.sys_log("UI EVENT: Tab focus changed. All source code screens auto-locked.")

    # ==========================================
    # CIRCULAR IMAGE HELPER (For About Tab)
    # ==========================================
    def create_circular_pixmap(self, image_path, size):
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return QPixmap()
        pixmap = pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
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

    # ==========================================
    # ABOUT WINDOW (Banner + Circular Pic)
    # ==========================================
    def show_about_window(self):
        self.sys_log("UI EVENT: About Developer window opened.")
        dlg = QDialog(self)
        dlg.setWindowTitle("About Developer")
        dlg.resize(550, 650)
        dlg.setStyleSheet("background-color: #161e2e;")
        
        # Absolute positioning container for banner + overlap
        header = QFrame(dlg)
        header.setGeometry(0, 0, 550, 180)
        
        # Banner Image
        banner_lbl = QLabel(header)
        banner_lbl.setGeometry(0, 0, 550, 120)
        banner_path = resource_path(ASSETS["BANNER_PIC"])
        banner_pix = QPixmap(banner_path)
        if not banner_pix.isNull():
            banner_lbl.setPixmap(banner_pix.scaled(550, 120, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.sys_log(f"IMAGE SUCCESS: Loaded banner '{banner_path}'")
        else:
            banner_lbl.setStyleSheet("background-color: #334155;")
            self.sys_log(f"IMAGE FAIL: Could not load banner '{banner_path}'")
            
        # Circular Profile Picture (overlapping banner)
        profile_lbl = QLabel(header)
        profile_lbl.setGeometry(215, 60, 120, 120) # Center X: (550-120)/2 = 215, Center Y: Overlaps edge
        prof_path = resource_path(ASSETS["PROFILE_PIC"])
        prof_pix = self.create_circular_pixmap(prof_path, 120)
        if not prof_pix.isNull():
            profile_lbl.setPixmap(prof_pix)
            self.sys_log(f"IMAGE SUCCESS: Loaded profile pic '{prof_path}'")
        else:
            profile_lbl.setStyleSheet("background-color: #ef4444; border-radius: 60px;")
            self.sys_log(f"IMAGE FAIL: Could not load profile '{prof_path}'")

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
            readme_path = resource_path(ASSETS["README"])
            with open(readme_path, "r", encoding="utf-8") as f:
                txt_readme.setPlainText(f.read())
                self.sys_log(f"FILE SUCCESS: Loaded {ASSETS['README']}")
        except Exception as e:
            txt_readme.setPlainText(f"Error loading {ASSETS['README']}: {str(e)}")
            self.sys_log(f"FILE FAIL: {str(e)}")
            
        lay.addWidget(txt_readme)
        dlg.exec()

    def show_contact_dev(self, name, email):
        self.sys_log(f"UI EVENT: User requested PIN via contact button.")
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

if __name__ == "__main__":
    try:
        myappid = 'ather.batteryrig.masterstudio.4' 
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception:
        pass 
        
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(resource_path(ASSETS["ICON"])))
    window = BatteryRigGUI()
    window.show()
    sys.exit(app.exec())