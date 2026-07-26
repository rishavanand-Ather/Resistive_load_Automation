import os
import sys
import requests
import urllib3
from PyQt6.QtWidgets import QMessageBox, QProgressDialog, QFileDialog
from PyQt6.QtCore import QObject, QThread, pyqtSignal, Qt, QTimer

# Suppress the massive red SSL warnings when bypassing the corporate firewall
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class UpdateCheckerThread(QThread):
    update_available = pyqtSignal(str, str)
    no_update = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, repo, token, current_version, manual_check=False):
        super().__init__()
        self.repo = repo
        self.token = token
        self.current_version = current_version
        self.manual_check = manual_check

    def run(self):
        try:
            url = f"https://api.github.com/repos/{self.repo}/releases/latest"
            headers = {
                "Authorization": f"Bearer {self.token}", 
                "Accept": "application/vnd.github.v3+json"
            }
            
            # verify=False bypasses corporate firewall self-signed cert blocks
            response = requests.get(url, headers=headers, timeout=10, verify=False)
            
            if response.status_code == 200:
                data = response.json()
                latest_version = data.get("tag_name", "")
                
                if latest_version and latest_version != self.current_version:
                    asset_url = None
                    for asset in data.get("assets", []):
                        if asset.get("name", "").endswith(".exe"):
                            asset_url = asset.get("url") 
                            break
                    
                    if asset_url:
                        self.update_available.emit(latest_version, asset_url)
                        return
                        
                self.no_update.emit()
            else:
                self.error.emit(f"GitHub API Error: HTTP {response.status_code} - {response.text}")
        except Exception as e:
            self.error.emit(f"Network error: {str(e)}")


class DownloaderThread(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, download_url, token):
        super().__init__()
        self.download_url = download_url
        self.token = token
        self.temp_filename = "update_temp.exe"

    def run(self):
        try:
            headers = {
                "Authorization": f"Bearer {self.token}", 
                "Accept": "application/octet-stream"
            }
            response = requests.get(self.download_url, headers=headers, stream=True, timeout=15, verify=False)
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


class AutoUpdater(QObject):
    """
    A modular PyQt6 auto-updater for GitHub private repositories.
    """
    log_msg = pyqtSignal(str)

    def __init__(self, parent_widget, current_version, github_repo, github_token, exe_name):
        super().__init__(parent_widget)
        self.parent = parent_widget
        self.current_version = current_version
        self.github_repo = github_repo
        self.github_token = github_token
        self.exe_name = exe_name

    def prompt_local_update(self):
        self.log_msg.emit("SYSTEM ACTION: Prompting for local executable update...")
        file_path, _ = QFileDialog.getOpenFileName(self.parent, "Select New Executable Version", "", "Executables (*.exe)")
        
        if file_path:
            reply = QMessageBox.question(self.parent, "Confirm Local Update", 
                                         f"Are you sure you want to update the system using this file?\n\n{file_path}",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.apply_update(file_path, delete_temp=False)

    def check_for_updates(self, manual=False):
        if manual:
            self.log_msg.emit("SYSTEM ACTION: Manually checking for updates via GitHub API...")
            
        self.update_thread = UpdateCheckerThread(self.github_repo, self.github_token, self.current_version, manual)
        self.update_thread.update_available.connect(self.prompt_update)
        
        if manual:
            self.update_thread.no_update.connect(lambda: QMessageBox.information(self.parent, "Up to Date", f"You are running the latest version ({self.current_version})."))
            self.update_thread.error.connect(lambda msg: QMessageBox.warning(self.parent, "Update Error", msg))
            
        self.update_thread.start()

    def prompt_update(self, latest_version, asset_url):
        self.log_msg.emit(f"SYSTEM NOTIFICATION: Update {latest_version} is available.")
        # ---> ADD THIS LINE RIGHT HERE <---
        self.log_msg.emit(f"Version Check -> Current: {self.current_version} | Latest on GitHub: {latest_version}")
        msg_box = QMessageBox(self.parent)
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
            self.log_msg.emit("SYSTEM ACTION: Update snoozed for 5 hours.")
            QTimer.singleShot(18000000, lambda: self.check_for_updates(manual=False))

    def start_download(self, asset_url):
        self.log_msg.emit("SYSTEM ACTION: Downloading network update...")
        
        self.progress_dialog = QProgressDialog("Downloading update...", "Cancel", 0, 100, self.parent)
        self.progress_dialog.setWindowTitle("Updating System")
        self.progress_dialog.setStyleSheet("background-color: #0b0f19; color: white;")
        self.progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        self.progress_dialog.setAutoClose(True)
        self.progress_dialog.show()

        self.download_thread = DownloaderThread(asset_url, self.github_token)
        self.download_thread.progress.connect(self.progress_dialog.setValue)
        self.download_thread.finished.connect(lambda f: self.apply_update(f, delete_temp=True))
        self.download_thread.error.connect(lambda msg: QMessageBox.critical(self.parent, "Download Error", msg))
        
        self.progress_dialog.canceled.connect(self.download_thread.terminate)
        self.download_thread.start()

    def apply_update(self, temp_filename, delete_temp=True):
        self.log_msg.emit(f"SYSTEM ACTION: Preparing to hot-swap executable with {temp_filename}.")
        
        del_command = f'del "{temp_filename}"' if delete_temp else ""
        
        bat_content = f"""@echo off
echo Applying update... Please wait.
timeout /t 3 /nobreak > NUL
copy /Y "{self.exe_name}" "{self.exe_name}.backup"
copy /Y "{temp_filename}" "{self.exe_name}"
start "" "{self.exe_name}"
{del_command}
del "%~f0"
"""
        bat_filename = "updater.bat"
        try:
            with open(bat_filename, "w") as f:
                f.write(bat_content)
                
            os.startfile(bat_filename)
            sys.exit(0) 
            
        except Exception as e:
            self.log_msg.emit(f"SYSTEM CRASH: Failed to write or execute updater script: {str(e)}")
            QMessageBox.critical(self.parent, "Update Failed", f"Could not apply update: {str(e)}")