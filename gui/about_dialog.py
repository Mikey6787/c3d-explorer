"""
Simple & Brief About Dialog for C3D Explorer.
Author: Dr. Kharazi (Universität Koblenz)
Includes LinkedIn, University profile, and 'Buy Me a Coffee' (PayPal donation).
"""

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QCursor
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
)


class AboutDialog(QDialog):
    """Simple, brief, and clean About Dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About C3D Explorer")
        self.setFixedSize(450, 290)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self.setStyleSheet("""
            QDialog {
                background-color: #0F141C;
                color: #ECEFF4;
            }
        """)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        # 1. Header: App Name & Version
        header = QHBoxLayout()
        app_title = QLabel("C3D Explorer")
        app_title.setStyleSheet("font-size: 19px; font-weight: bold; color: #00ADB5;")
        ver_lbl = QLabel("v1.0.0")
        ver_lbl.setStyleSheet(
            "font-size: 11px; color: #8F9BB3; font-weight: 600; "
            "padding: 2px 7px; background-color: #1A2230; border-radius: 4px; border: 1px solid #263346;"
        )
        header.addWidget(app_title)
        header.addWidget(ver_lbl)
        header.addStretch()
        layout.addLayout(header)

        # 2. Author Info
        author_box = QVBoxLayout()
        author_box.setSpacing(3)
        lbl_author = QLabel("Author: <b>Dr. Mohamadreza Kharazi</b>")
        lbl_author.setStyleSheet("font-size: 14px; color: #FFFFFF;")
        lbl_inst = QLabel("Universität Koblenz, Germany")
        lbl_inst.setStyleSheet("font-size: 12px; color: #8F9BB3;")
        author_box.addWidget(lbl_author)
        author_box.addWidget(lbl_inst)
        layout.addLayout(author_box)

        # 3. Links: LinkedIn & University
        links_layout = QHBoxLayout()
        links_layout.setSpacing(10)

        btn_linkedin = QPushButton("LinkedIn ↗")
        btn_linkedin.setCursor(QCursor(Qt.PointingHandCursor))
        btn_linkedin.setFixedHeight(34)
        btn_linkedin.setStyleSheet("""
            QPushButton {
                background-color: #18202E;
                color: #38BDF8;
                border: 1px solid #2B384E;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                padding: 0 12px;
            }
            QPushButton:hover {
                background-color: #212C3F;
                border-color: #0A66C2;
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: #131A26;
            }
        """)
        btn_linkedin.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://www.linkedin.com/in/mohamadreza-kharazi-23575285"))
        )

        btn_scholar = QPushButton("Google Scholar ↗")
        btn_scholar.setCursor(QCursor(Qt.PointingHandCursor))
        btn_scholar.setFixedHeight(34)
        btn_scholar.setStyleSheet("""
            QPushButton {
                background-color: #18202E;
                color: #ECEFF4;
                border: 1px solid #2B384E;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                padding: 0 12px;
            }
            QPushButton:hover {
                background-color: #212C3F;
                border-color: #4285F4;
                color: #4285F4;
            }
            QPushButton:pressed {
                background-color: #131A26;
            }
        """)
        btn_scholar.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl("https://scholar.google.com/citations?view_op=search_authors&mauthors=Mohamadreza+Kharazi")
            )
        )

        links_layout.addWidget(btn_linkedin)
        links_layout.addWidget(btn_scholar)
        layout.addLayout(links_layout)

        # 4. "Buy Me a Coffee" Donate Button (PayPal: mohamadreza.kharazi@live.com)
        # 4. "Buy Me a Coffee" Donate Button (Coffee Brown with default 5 Euro)
        btn_donate = QPushButton("☕  Buy Me a Coffee (€5)")
        btn_donate.setToolTip("Support C3D Explorer development via PayPal (€5.00)")
        btn_donate.setCursor(QCursor(Qt.PointingHandCursor))
        btn_donate.setFixedHeight(40)
        btn_donate.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #8D5B36, stop:1 #6F4220);
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 700;
                border-radius: 6px;
                border: 1px solid #A46D43;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #9E673E, stop:1 #7D4C27);
                border: 1px solid #C48555;
            }
            QPushButton:pressed {
                background-color: #593317;
                border: 1px solid #593317;
            }
        """)
        paypal_url = (
            "https://www.paypal.com/cgi-bin/webscr?cmd=_donations"
            "&business=mohamadreza.kharazi%40live.com"
            "&currency_code=EUR"
            "&amount=5.00"
            "&item_name=Buy+Me+a+Coffee+-+C3D+Explorer"
        )
        btn_donate.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(paypal_url)))
        layout.addWidget(btn_donate)

        # 5. Footer: Close Button
        footer = QHBoxLayout()
        footer.addStretch()
        btn_close = QPushButton("Close")
        btn_close.setDefault(True)
        btn_close.setFixedWidth(80)
        btn_close.setFixedHeight(30)
        btn_close.setStyleSheet("""
            QPushButton {
                background-color: #1E2636;
                color: #ECEFF4;
                font-size: 11px;
                font-weight: 600;
                border: 1px solid #2F3E56;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #283348;
                color: #FFFFFF;
            }
            QPushButton:pressed {
                background-color: #141B26;
            }
        """)
        btn_close.clicked.connect(self.accept)
        footer.addWidget(btn_close)
        layout.addLayout(footer)
