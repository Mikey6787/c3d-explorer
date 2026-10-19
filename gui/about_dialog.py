"""About Dialog for C3D Explorer featuring Dr. Mohamadreza Kharazi."""

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QFont, QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QWidget
)


class AboutDialog(QDialog):
    """Modern, polished About Dialog highlighting Dr. Mohamadreza Kharazi and C3D Explorer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About C3D explorer")
        self.setFixedSize(580, 520)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self._setup_ui()

    def _setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 24, 24, 20)
        main_layout.setSpacing(16)

        # ---------------- 1. Header: App Name & Version ----------------
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        title_vbox = QVBoxLayout()
        title_vbox.setSpacing(3)

        app_title = QLabel("C3D explorer")
        app_title.setStyleSheet("font-size: 22px; font-weight: bold; color: #00E5FF; letter-spacing: 0.5px;")
        title_vbox.addWidget(app_title)

        app_sub = QLabel("Biomechanics Motion Capture Analysis & Visualization Workstation")
        app_sub.setStyleSheet("font-size: 12px; color: #94A3B8;")
        title_vbox.addWidget(app_sub)

        header_layout.addLayout(title_vbox)
        header_layout.addStretch()

        ver_badge = QLabel("v1.0.0")
        ver_badge.setStyleSheet(
            "background-color: #1E293B; color: #38BDF8; font-weight: bold; "
            "padding: 4px 10px; border-radius: 6px; border: 1px solid #334155; font-size: 11px;"
        )
        header_layout.addWidget(ver_badge, alignment=Qt.AlignTop)
        main_layout.addLayout(header_layout)

        # Divider line
        div1 = QFrame()
        div1.setFrameShape(QFrame.HLine)
        div1.setStyleSheet("color: #334155; margin: 0px;")
        main_layout.addWidget(div1)

        # ---------------- 2. Author Profile Card ----------------
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background-color: #161B26; border: 1px solid #28334E; border-radius: 10px; padding: 14px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(8)
        card_layout.setContentsMargins(12, 12, 12, 12)

        author_name = QLabel("Dr. Mohamadreza Kharazi")
        author_name.setStyleSheet("font-size: 16px; font-weight: bold; color: #FFFFFF;")
        card_layout.addWidget(author_name)

        author_role = QLabel(
            "<b>Senior Researcher / Academic Staff</b> (<i>Wissenschaftlicher Mitarbeiter</i>)<br>"
            "Working Group for Training and Movement Science (<i>AG Trainings- und Bewegungswissenschaft</i>)<br>"
            "Institute of Sport Science (<i>Institut für Sportwissenschaft</i>)<br>"
            "Faculty 3: Mathematics / Natural Sciences (<i>Fachbereich 3: Mathematik / Naturwissenschaften</i>)<br>"
            "<b>Universität Koblenz</b>, Germany"
        )
        author_role.setStyleSheet("font-size: 12px; color: #CBD5E1; line-height: 1.4;")
        author_role.setTextFormat(Qt.RichText)
        card_layout.addWidget(author_role)

        # Research Fields
        tags_layout = QHBoxLayout()
        tags_layout.setSpacing(6)
        tags = ["Biomechanics", "Motor Control", "OpenSim Modeling", "Gait & Tendon Mechanics"]
        for tag in tags:
            tag_lbl = QLabel(tag)
            tag_lbl.setStyleSheet(
                "background-color: #1E2738; color: #00ADB5; font-size: 10px; font-weight: bold; "
                "padding: 2px 7px; border-radius: 4px; border: 1px solid #00ADB5;"
            )
            tags_layout.addWidget(tag_lbl)
        tags_layout.addStretch()
        card_layout.addLayout(tags_layout)

        main_layout.addWidget(card)

        # ---------------- 3. Contact & Academic Links ----------------
        contact_layout = QVBoxLayout()
        contact_layout.setSpacing(5)

        info_lbl = QLabel(
            "<b>Office:</b> Room N 221, Universitätsstraße 1, 56070 Koblenz, Germany<br>"
            "<b>Email:</b> <a style='color: #00ADB5; text-decoration: none;' href='mailto:mkharazi@uni-koblenz.de'>mkharazi@uni-koblenz.de</a>  |  "
            "<b>Phone:</b> +49 261 287-2408<br>"
            "<b>Profiles:</b> "
            "<a style='color: #38BDF8;' href='https://www.uni-koblenz.de'>Universität Koblenz</a>  •  "
            "<a style='color: #38BDF8;' href='https://www.researchgate.net/profile/Mohamadreza-Kharazi'>ResearchGate</a>  •  "
            "<a style='color: #38BDF8;' href='https://scholar.google.com/citations?user=Mohamadreza+Kharazi'>Google Scholar</a>"
        )
        info_lbl.setOpenExternalLinks(True)
        info_lbl.setStyleSheet("font-size: 11px; color: #94A3B8; line-height: 1.5;")
        contact_layout.addWidget(info_lbl)
        main_layout.addLayout(contact_layout)

        main_layout.addStretch()

        # ---------------- 4. Bottom Close Button ----------------
        btn_layout = QHBoxLayout()
        tech_note = QLabel("Powered by <b>PySide6</b>, <b>PyQtGraph</b> & <b>ezc3d</b>")
        tech_note.setStyleSheet("font-size: 11px; color: #64748B;")
        btn_layout.addWidget(tech_note)
        btn_layout.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setDefault(True)
        btn_close.setFixedWidth(90)
        btn_close.setStyleSheet(
            "QPushButton { background-color: #00ADB5; color: white; font-weight: bold; "
            "padding: 6px 14px; border-radius: 5px; } "
            "QPushButton:hover { background-color: #00C4CC; }"
        )
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        main_layout.addLayout(btn_layout)
