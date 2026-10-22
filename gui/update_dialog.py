"""
Interactive Check for Updates dialog and updater for C3D Explorer.
Queries GitHub Releases API, compares semantic versions, displays changelogs,
and downloads/executes platform-specific installers (Windows Setup EXE / macOS DMG).
"""

import sys
import os
import re
import json
import tempfile
import subprocess
from typing import Optional, Dict, Any, Tuple

from PySide6.QtCore import Qt, QUrl, Signal, Slot, QTimer
from PySide6.QtGui import QDesktopServices, QIcon, QPixmap, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QTextBrowser, QFrame, QStackedWidget, QWidget,
    QApplication, QMessageBox
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from core import __version__
from core.resource_utils import get_resource_path


GITHUB_REPO = "Mikey6787/c3d-explorer"
API_LATEST_RELEASE = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
HTML_RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"


def parse_version_tuple(v_str: str) -> Tuple[int, ...]:
    """Parse a semantic version string (e.g. 'v1.0.2', '1.0.1') into integer tuple."""
    if not v_str:
        return (0,)
    # Extract consecutive numeric digits
    numbers = [int(n) for n in re.findall(r"\d+", str(v_str))]
    return tuple(numbers) if numbers else (0,)


def is_remote_version_newer(remote_v: str, current_v: str = __version__) -> bool:
    """Compare remote version against current installed version."""
    r_tuple = parse_version_tuple(remote_v)
    c_tuple = parse_version_tuple(current_v)
    return r_tuple > c_tuple


class UpdateDialog(QDialog):
    """
    Modern, theme-aware dialog for checking GitHub releases and
    performing in-app automated updates.
    """

    def __init__(self, parent=None, is_dark: bool = True):
        super().__init__(parent)
        self.is_dark = is_dark
        self.setWindowTitle("Check for Updates — C3D Explorer")
        self.setFixedSize(540, 420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        # Window icon
        icon_file = "AppIcon-Dark.png" if self.is_dark else "AppIcon-Light.png"
        icon_path = get_resource_path(os.path.join("assets", "icons", icon_file))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.icon_path = icon_path

        # Network managers
        self.net_manager = QNetworkAccessManager(self)
        self.check_reply: Optional[QNetworkReply] = None
        self.download_reply: Optional[QNetworkReply] = None

        # Release data state
        self.release_data: Dict[str, Any] = {}
        self.downloaded_file_path: Optional[str] = None
        self.download_target_file = None

        self._apply_styling()
        self._setup_ui()

        # Start check automatically when dialog is shown
        QTimer.singleShot(150, self.start_check_for_updates)

    def _apply_styling(self):
        """Apply dark or light theme colors matching C3D Explorer design."""
        if self.is_dark:
            self.setStyleSheet("""
                QDialog {
                    background-color: #0F141C;
                    color: #ECEFF4;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                }
                QLabel {
                    color: #ECEFF4;
                }
                QFrame#card {
                    background-color: #171E2B;
                    border: 1px solid #28354A;
                    border-radius: 8px;
                }
                QTextBrowser {
                    background-color: #121722;
                    color: #D8DEE9;
                    border: 1px solid #232E40;
                    border-radius: 6px;
                    padding: 8px;
                    font-size: 12px;
                    line-height: 1.4;
                }
                QProgressBar {
                    background-color: #121722;
                    border: 1px solid #28354A;
                    border-radius: 5px;
                    height: 10px;
                    text-align: center;
                    color: #FFFFFF;
                    font-size: 10px;
                }
                QProgressBar::chunk {
                    background-color: #00ADB5;
                    border-radius: 4px;
                }
                QPushButton {
                    background-color: #1E2838;
                    color: #ECEFF4;
                    border: 1px solid #2D3C54;
                    border-radius: 6px;
                    padding: 7px 14px;
                    font-size: 12px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #273449;
                    border-color: #3B4E6D;
                    color: #FFFFFF;
                }
                QPushButton:pressed {
                    background-color: #18202E;
                }
                QPushButton#btnPrimary {
                    background-color: #00ADB5;
                    color: #FFFFFF;
                    border: 1px solid #00ADB5;
                }
                QPushButton#btnPrimary:hover {
                    background-color: #00C4CE;
                    border-color: #00C4CE;
                }
                QPushButton#btnPrimary:pressed {
                    background-color: #007982;
                }
            """)
        else:
            self.setStyleSheet("""
                QDialog {
                    background-color: #F8FAFC;
                    color: #1E293B;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                }
                QLabel {
                    color: #1E293B;
                }
                QFrame#card {
                    background-color: #FFFFFF;
                    border: 1px solid #E2E8F0;
                    border-radius: 8px;
                }
                QTextBrowser {
                    background-color: #FFFFFF;
                    color: #334155;
                    border: 1px solid #E2E8F0;
                    border-radius: 6px;
                    padding: 8px;
                    font-size: 12px;
                    line-height: 1.4;
                }
                QProgressBar {
                    background-color: #F1F5F9;
                    border: 1px solid #CBD5E1;
                    border-radius: 5px;
                    height: 10px;
                    text-align: center;
                    color: #1E293B;
                    font-size: 10px;
                }
                QProgressBar::chunk {
                    background-color: #0284C7;
                    border-radius: 4px;
                }
                QPushButton {
                    background-color: #F1F5F9;
                    color: #1E293B;
                    border: 1px solid #CBD5E1;
                    border-radius: 6px;
                    padding: 7px 14px;
                    font-size: 12px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background-color: #E2E8F0;
                    border-color: #94A3B8;
                }
                QPushButton:pressed {
                    background-color: #CBD5E1;
                }
                QPushButton#btnPrimary {
                    background-color: #0284C7;
                    color: #FFFFFF;
                    border: 1px solid #0284C7;
                }
                QPushButton#btnPrimary:hover {
                    background-color: #0369A1;
                    border-color: #0369A1;
                }
                QPushButton#btnPrimary:pressed {
                    background-color: #075985;
                }
            """)

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(22, 20, 22, 18)
        main_layout.setSpacing(14)

        # 1. Top Header: App Icon, Title, and Subtitle
        header = QHBoxLayout()
        header.setSpacing(12)

        if os.path.exists(self.icon_path):
            icon_lbl = QLabel()
            icon_lbl.setPixmap(QPixmap(self.icon_path).scaled(36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            header.addWidget(icon_lbl)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        lbl_title = QLabel("C3D Explorer Updater")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: 700;")
        self.lbl_subtitle = QLabel(f"Current version installed: v{__version__}")
        self.lbl_subtitle.setStyleSheet(f"font-size: 12px; color: {'#94A3B8' if self.is_dark else '#64748B'};")
        title_box.addWidget(lbl_title)
        title_box.addWidget(self.lbl_subtitle)
        header.addLayout(title_box)
        header.addStretch()

        main_layout.addLayout(header)

        # 2. Central Stacked Content Area for different states
        self.stack = QStackedWidget(self)
        main_layout.addWidget(self.stack, 1)

        # --- Page 0: Checking for Updates ---
        self.page_checking = self._create_page_checking()
        self.stack.addWidget(self.page_checking)

        # --- Page 1: Up to Date ---
        self.page_uptodate = self._create_page_uptodate()
        self.stack.addWidget(self.page_uptodate)

        # --- Page 2: Update Available ---
        self.page_available = self._create_page_available()
        self.stack.addWidget(self.page_available)

        # --- Page 3: Downloading Update ---
        self.page_downloading = self._create_page_downloading()
        self.stack.addWidget(self.page_downloading)

        # --- Page 4: Error / Offline ---
        self.page_error = self._create_page_error()
        self.stack.addWidget(self.page_error)

        self.stack.setCurrentIndex(0)

    # -------------------------------------------------------------
    # Pages creation
    # -------------------------------------------------------------
    def _create_page_checking(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(14)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 28)
        card_layout.setAlignment(Qt.AlignCenter)
        card_layout.setSpacing(12)

        lbl = QLabel("Checking GitHub for the latest release...")
        lbl.setStyleSheet("font-size: 13px; font-weight: 500;")
        lbl.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(lbl)

        pbar = QProgressBar()
        pbar.setRange(0, 0)  # Indeterminate animation
        pbar.setFixedWidth(280)
        card_layout.addWidget(pbar)

        layout.addWidget(card)
        return widget

    def _create_page_uptodate(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(14)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(10)

        badge_box = QHBoxLayout()
        badge = QLabel("✓  UP TO DATE")
        badge.setStyleSheet("""
            background-color: #10B981;
            color: #FFFFFF;
            font-size: 11px;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 12px;
        """)
        badge_box.addWidget(badge)
        badge_box.addStretch()
        card_layout.addLayout(badge_box)

        lbl_msg = QLabel(f"You are running the newest version of C3D Explorer (v{__version__}).")
        lbl_msg.setStyleSheet("font-size: 13px; font-weight: 600; margin-top: 4px;")
        lbl_desc = QLabel("No new updates are required. Your installation has all the latest signal filtering tools, 3D viewport improvements, and biomechanics measurement capabilities.")
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(f"font-size: 12px; color: {'#94A3B8' if self.is_dark else '#64748B'}; line-height: 1.4;")

        card_layout.addWidget(lbl_msg)
        card_layout.addWidget(lbl_desc)
        card_layout.addStretch()

        layout.addWidget(card, 1)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_github = QPushButton("View Release Notes ↗")
        btn_github.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(HTML_RELEASES_PAGE)))
        btn_close = QPushButton("Close")
        btn_close.setObjectName("btnPrimary")
        btn_close.clicked.connect(self.accept)

        btn_box.addWidget(btn_github)
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)

        return widget

    def _create_page_available(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(10)

        # Header info
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(6)

        top_row = QHBoxLayout()
        self.lbl_avail_badge = QLabel("NEW UPDATE AVAILABLE")
        self.lbl_avail_badge.setStyleSheet("""
            background-color: #0284C7;
            color: #FFFFFF;
            font-size: 10px;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 10px;
        """)
        self.lbl_avail_version = QLabel("v1.0.2")
        self.lbl_avail_version.setStyleSheet("font-size: 14px; font-weight: 700;")
        top_row.addWidget(self.lbl_avail_badge)
        top_row.addWidget(self.lbl_avail_version)
        top_row.addStretch()
        card_layout.addLayout(top_row)

        self.lbl_avail_details = QLabel("A new version is available for download.")
        self.lbl_avail_details.setStyleSheet(f"font-size: 11px; color: {'#94A3B8' if self.is_dark else '#64748B'};")
        card_layout.addWidget(self.lbl_avail_details)

        layout.addWidget(card)

        # Release Notes Browser
        lbl_notes_title = QLabel("What's New in this Release:")
        lbl_notes_title.setStyleSheet("font-size: 12px; font-weight: 600;")
        layout.addWidget(lbl_notes_title)

        self.browser_notes = QTextBrowser()
        self.browser_notes.setOpenExternalLinks(True)
        layout.addWidget(self.browser_notes, 1)

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)

        self.btn_github = QPushButton("View on GitHub ↗")
        self.btn_github.clicked.connect(self._open_release_url)
        btn_box.addWidget(self.btn_github)

        btn_box.addStretch()

        self.btn_later = QPushButton("Later")
        self.btn_later.clicked.connect(self.reject)
        btn_box.addWidget(self.btn_later)

        self.btn_update = QPushButton("Download & Update Now")
        self.btn_update.setObjectName("btnPrimary")
        self.btn_update.clicked.connect(self.start_download_update)
        btn_box.addWidget(self.btn_update)

        layout.addLayout(btn_box)

        return widget

    def _create_page_downloading(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(14)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 28, 28, 28)
        card_layout.setAlignment(Qt.AlignCenter)
        card_layout.setSpacing(10)

        self.lbl_dl_status = QLabel("Downloading update package...")
        self.lbl_dl_status.setStyleSheet("font-size: 13px; font-weight: 600;")
        self.lbl_dl_status.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.lbl_dl_status)

        self.prog_dl = QProgressBar()
        self.prog_dl.setRange(0, 100)
        self.prog_dl.setValue(0)
        self.prog_dl.setFixedWidth(320)
        card_layout.addWidget(self.prog_dl)

        self.lbl_dl_bytes = QLabel("Connecting...")
        self.lbl_dl_bytes.setStyleSheet(f"font-size: 11px; color: {'#94A3B8' if self.is_dark else '#64748B'};")
        self.lbl_dl_bytes.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(self.lbl_dl_bytes)

        btn_cancel_dl = QPushButton("Cancel Download")
        btn_cancel_dl.clicked.connect(self.cancel_download)
        card_layout.addWidget(btn_cancel_dl)

        layout.addWidget(card)
        return widget

    def _create_page_error(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(14)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 24, 24, 24)
        card_layout.setSpacing(10)

        lbl_err_title = QLabel("Unable to Check for Updates")
        lbl_err_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #EF4444;")
        card_layout.addWidget(lbl_err_title)

        self.lbl_err_msg = QLabel("Could not reach GitHub Releases server. Please verify your internet connection.")
        self.lbl_err_msg.setWordWrap(True)
        self.lbl_err_msg.setStyleSheet(f"font-size: 12px; color: {'#94A3B8' if self.is_dark else '#64748B'};")
        card_layout.addWidget(self.lbl_err_msg)
        card_layout.addStretch()

        layout.addWidget(card, 1)

        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_retry = QPushButton("Retry")
        btn_retry.clicked.connect(self.start_check_for_updates)
        btn_box.addWidget(btn_retry)

        btn_github = QPushButton("Open Releases Page ↗")
        btn_github.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(HTML_RELEASES_PAGE)))
        btn_box.addWidget(btn_github)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        btn_box.addWidget(btn_close)

        layout.addLayout(btn_box)
        return widget

    # -------------------------------------------------------------
    # Logic: Checking for Updates
    # -------------------------------------------------------------
    def start_check_for_updates(self):
        """Query GitHub Releases API for the latest release."""
        self.stack.setCurrentIndex(0)  # Page 0: Checking

        req = QNetworkRequest(QUrl(API_LATEST_RELEASE))
        req.setRawHeader(b"User-Agent", b"C3DExplorer-Updater")
        req.setRawHeader(b"Accept", b"application/vnd.github.v3+json")

        self.check_reply = self.net_manager.get(req)
        self.check_reply.finished.connect(self._on_check_finished)

    def _on_check_finished(self):
        if not self.check_reply:
            return

        reply = self.check_reply
        self.check_reply = None

        if reply.error() != QNetworkReply.NoError:
            err_text = reply.errorString()
            self.lbl_err_msg.setText(f"GitHub connection error: {err_text}\n\nYou can manually visit GitHub Releases to view and download new versions.")
            self.stack.setCurrentIndex(4)  # Page 4: Error
            reply.deleteLater()
            return

        try:
            raw_bytes = reply.readAll().data()
            data = json.loads(raw_bytes.decode("utf-8"))
        except Exception as e:
            self.lbl_err_msg.setText(f"Failed to parse release information: {e}")
            self.stack.setCurrentIndex(4)
            reply.deleteLater()
            return

        reply.deleteLater()
        self.release_data = data

        tag_name = data.get("tag_name", "")
        if not tag_name:
            self.lbl_err_msg.setText("No release tag was found in GitHub API response.")
            self.stack.setCurrentIndex(4)
            return

        # Check if remote version is newer than current installed version
        if is_remote_version_newer(tag_name, __version__):
            # Newer version available!
            self._display_update_available(data)
        else:
            # Already up to date!
            self.stack.setCurrentIndex(1)

    def _display_update_available(self, data: Dict[str, Any]):
        tag = data.get("tag_name", "New Version")
        name = data.get("name", tag)
        body = data.get("body", "").strip()
        pub_at = data.get("published_at", "")[:10]

        self.lbl_avail_version.setText(f"{name} (Current: v{__version__})")
        details_txt = f"Released on GitHub: {pub_at}" if pub_at else "Available on GitHub"

        # Check if platform asset is available
        asset_info = self._get_platform_asset(data)
        if asset_info:
            size_mb = asset_info.get("size", 0) / (1024 * 1024)
            details_txt += f" · Package: {asset_info.get('name')} ({size_mb:.1f} MB)"
            if sys.platform == "win32":
                self.btn_update.setText("Download & Install Update")
            elif sys.platform == "darwin":
                self.btn_update.setText("Download Update (.dmg)")
            else:
                self.btn_update.setText("Download Package")
            self.btn_update.setEnabled(True)
        else:
            details_txt += " · (No direct auto-installer for your OS; click 'View on GitHub')"
            self.btn_update.setText("Download from GitHub ↗")
            self.btn_update.clicked.disconnect()
            self.btn_update.clicked.connect(self._open_release_url)

        self.lbl_avail_details.setText(details_txt)

        # Populate release notes
        if body:
            self.browser_notes.setMarkdown(body)
        else:
            self.browser_notes.setText("No changelog description provided for this release.\nVisit the GitHub release page for full details.")

        self.stack.setCurrentIndex(2)

    def _get_platform_asset(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find the matching download asset for the current OS."""
        assets = data.get("assets", [])
        if not assets:
            return None

        if sys.platform == "win32":
            # Prefer Windows Setup Installer (.exe), fallback to portable .zip
            for a in assets:
                name = a.get("name", "").lower()
                if name.endswith("_setup.exe") or (name.endswith(".exe") and "portable" not in name):
                    return a
            for a in assets:
                if a.get("name", "").lower().endswith(".zip"):
                    return a

        elif sys.platform == "darwin":
            # Look for macOS .dmg
            for a in assets:
                if a.get("name", "").lower().endswith(".dmg"):
                    return a

        # Fallback to first available asset if any
        return assets[0] if assets else None

    def _open_release_url(self):
        url = self.release_data.get("html_url", HTML_RELEASES_PAGE)
        QDesktopServices.openUrl(QUrl(url))

    # -------------------------------------------------------------
    # Logic: Downloading & Updating
    # -------------------------------------------------------------
    def start_download_update(self):
        """Initiate background download of the selected asset."""
        asset = self._get_platform_asset(self.release_data)
        if not asset or not asset.get("browser_download_url"):
            self._open_release_url()
            return

        download_url = asset.get("browser_download_url")
        filename = asset.get("name", "C3D_Explorer_Update")

        # Destination path
        if sys.platform == "win32":
            dest_dir = tempfile.gettempdir()
        elif sys.platform == "darwin":
            dest_dir = os.path.expanduser("~/Downloads")
        else:
            dest_dir = tempfile.gettempdir()

        dest_path = os.path.join(dest_dir, filename)
        try:
            self.download_target_file = open(dest_path, "wb")
        except Exception as e:
            QMessageBox.critical(self, "Download Error", f"Unable to create destination file:\n{e}")
            return

        self.downloaded_file_path = dest_path
        self.stack.setCurrentIndex(3)  # Page 3: Downloading
        self.lbl_dl_status.setText(f"Downloading {filename}...")
        self.prog_dl.setValue(0)
        self.lbl_dl_bytes.setText("Connecting to GitHub...")

        req = QNetworkRequest(QUrl(download_url))
        req.setRawHeader(b"User-Agent", b"C3DExplorer-Updater")
        # Follow redirects (GitHub release downloads redirect to AWS S3)
        req.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.NoLessSafeRedirectPolicy)

        self.download_reply = self.net_manager.get(req)
        self.download_reply.downloadProgress.connect(self._on_download_progress)
        self.download_reply.readyRead.connect(self._on_download_ready_read)
        self.download_reply.finished.connect(self._on_download_finished)

    def _on_download_ready_read(self):
        if self.download_reply and self.download_target_file:
            data = self.download_reply.readAll().data()
            if data:
                self.download_target_file.write(data)

    def _on_download_progress(self, bytes_received: int, bytes_total: int):
        if bytes_total > 0:
            pct = int((bytes_received / bytes_total) * 100)
            self.prog_dl.setValue(pct)
            rec_mb = bytes_received / (1024 * 1024)
            tot_mb = bytes_total / (1024 * 1024)
            self.lbl_dl_bytes.setText(f"{rec_mb:.1f} MB / {tot_mb:.1f} MB ({pct}%)")
        else:
            rec_mb = bytes_received / (1024 * 1024)
            self.lbl_dl_bytes.setText(f"{rec_mb:.1f} MB downloaded")

    def _on_download_finished(self):
        if not self.download_reply:
            return

        reply = self.download_reply
        self.download_reply = None

        if self.download_target_file:
            try:
                self.download_target_file.flush()
                self.download_target_file.close()
            except Exception:
                pass
            self.download_target_file = None

        if reply.error() != QNetworkReply.NoError:
            err_msg = reply.errorString()
            reply.deleteLater()
            QMessageBox.critical(self, "Download Failed", f"Download failed with error:\n{err_msg}")
            self.stack.setCurrentIndex(2)  # Return to available
            return

        reply.deleteLater()

        # Handle completed download
        self._handle_completed_update(self.downloaded_file_path)

    def _handle_completed_update(self, file_path: str):
        """Execute or reveal the downloaded package depending on OS."""
        if not file_path or not os.path.exists(file_path):
            QMessageBox.warning(self, "Update", "Download finished but the target file could not be found.")
            return

        if sys.platform == "win32":
            # Windows installer (.exe)
            ret = QMessageBox.question(
                self,
                "Ready to Install Update",
                f"The update has been downloaded successfully!\n\n"
                f"C3D Explorer will now close and launch the installer:\n{os.path.basename(file_path)}\n\n"
                f"Proceed with installation now?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            if ret == QMessageBox.Yes:
                try:
                    subprocess.Popen([file_path], shell=True)
                    QApplication.instance().quit()
                except Exception as e:
                    QMessageBox.critical(self, "Launch Error", f"Failed to launch installer:\n{e}")
            else:
                self.accept()

        elif sys.platform == "darwin":
            # macOS .dmg
            ret = QMessageBox.information(
                self,
                "Download Complete",
                f"The new version disk image has been downloaded to your Downloads folder:\n\n"
                f"{file_path}\n\n"
                f"Would you like to open the disk image now to replace C3D Explorer in Applications?",
                QMessageBox.Open | QMessageBox.Close,
                QMessageBox.Open
            )
            if ret == QMessageBox.Open:
                try:
                    subprocess.Popen(["open", file_path])
                except Exception:
                    pass
            self.accept()

        else:
            QMessageBox.information(
                self,
                "Download Complete",
                f"Update downloaded successfully to:\n{file_path}"
            )
            self.accept()

    def cancel_download(self):
        """Cancel an in-progress download."""
        if self.download_reply:
            self.download_reply.abort()
            self.download_reply = None
        if self.download_target_file:
            try:
                self.download_target_file.close()
            except Exception:
                pass
            self.download_target_file = None
        if self.downloaded_file_path and os.path.exists(self.downloaded_file_path):
            try:
                os.remove(self.downloaded_file_path)
            except Exception:
                pass
        self.stack.setCurrentIndex(2)  # Return to available
