from __future__ import annotations

from PIL import Image
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent, QIcon, QImage, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QRadioButton,
    QSlider,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from image_processor import (
    detect_background,
    extract_frames,
    invert_image,
    remove_background,
    round_corners,
    to_grayscale,
    with_checkerboard,
)

Frame = tuple[Image.Image, int]
MIN_FRAME_MS = 50


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def pil_to_pixmap(img: Image.Image, max_size: int | None = None) -> QPixmap:
    if max_size:
        img = img.copy()
        img.thumbnail((max_size, max_size), Image.LANCZOS)
    img = img.convert('RGBA')
    data = img.tobytes('raw', 'RGBA')
    qimg = QImage(data, img.width, img.height, img.width * 4, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg)


def make_tray_icon(frame_img: Image.Image) -> QIcon:
    icon = QIcon()
    for height in (22, 44):
        img = frame_img.convert('RGBA')
        scale = height / img.height
        sized = img.resize((max(1, round(img.width * scale)), height), Image.LANCZOS)
        sized = round_corners(sized, radius=max(2, height // 5))
        icon.addPixmap(pil_to_pixmap(sized))
    return icon


# ---------------------------------------------------------------------------
# Drop zone
# ---------------------------------------------------------------------------

class DropZone(QLabel):
    file_dropped = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("Drop an image here\nor click to browse")
        self.setMinimumSize(560, 180)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("""
            QLabel {
                border: 2px dashed #444;
                border-radius: 14px;
                color: #666;
                font-size: 16px;
                background: #161618;
            }
            QLabel:hover { border-color: #777; color: #aaa; }
        """)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.tiff *.webp *.gif)"
        )
        if path:
            self.file_dropped.emit(path)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            self.file_dropped.emit(urls[0].toLocalFile())


# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------

DARK_BG     = "#111113"
CARD_BG     = "#1c1c1e"
ACCENT      = "#2d7d46"
ACCENT_HV   = "#389954"
BTN_GREY    = "#323234"
BTN_GREY_HV = "#424244"
TEXT_DIM    = "#777"
TEXT_LABEL  = "#aaa"

CHECKBOX_STYLE = f"color: {TEXT_LABEL}; font-size: 13px;"
RADIO_STYLE    = f"color: {TEXT_LABEL}; font-size: 13px;"

BTN_STYLE = """
    QPushButton {{
        background: {bg}; color: white; border-radius: 8px;
        padding: 9px 20px; font-size: 13px; font-weight: {weight}; border: none;
    }}
    QPushButton:hover {{ background: {hv}; }}
"""

SLIDER_STYLE = """
    QSlider::groove:horizontal { height: 3px; background: #3a3a3c; border-radius: 2px; }
    QSlider::handle:horizontal {
        background: #ddd; width: 13px; height: 13px;
        margin: -5px 0; border-radius: 7px;
    }
    QSlider::sub-page:horizontal { background: #3a9e5a; border-radius: 2px; }
"""


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Menu Bar Image Maker")
        self.setFixedSize(584, 520)
        self.setStyleSheet(f"background: {DARK_BG}; color: white;")

        self._raw_frames: list[Frame] = []
        self._processed_frames: list[Frame] = []
        self._is_animated: bool = False
        self._bg_hint: str = 'white'
        self._inverted: bool = False
        self._grayscale: bool = False
        self._remove_bg: bool = True

        self._preview_idx: int = 0
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._advance_preview)

        self._tray: QSystemTrayIcon | None = None
        self._tray_idx: int = 0
        self._tray_timer = QTimer(self)
        self._tray_timer.setSingleShot(True)
        self._tray_timer.timeout.connect(self._advance_tray)

        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header
        title = QLabel("Menu Bar Image Maker")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #eee;")
        layout.addWidget(title)

        # Drop zone
        self.drop_zone = DropZone()
        self.drop_zone.file_dropped.connect(self._load_image)
        layout.addWidget(self.drop_zone)

        # ---- Preview panel ----
        self.preview_panel = QWidget()
        preview_layout = QHBoxLayout(self.preview_panel)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.setSpacing(12)

        for attr, heading in (('orig_label', 'Original'), ('proc_label', 'Result')):
            col = QVBoxLayout()
            col.setSpacing(5)
            h = QLabel(heading)
            h.setStyleSheet(f"font-size: 11px; color: {TEXT_DIM}; font-weight: 600; letter-spacing: 0.5px;")
            lbl = QLabel()
            lbl.setFixedSize(256, 220)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet(f"background: {CARD_BG}; border-radius: 10px;")
            col.addWidget(h)
            col.addWidget(lbl)
            setattr(self, attr, lbl)
            preview_layout.addLayout(col)

        self.preview_panel.setVisible(False)
        layout.addWidget(self.preview_panel)

        # ---- Controls card ----
        self.controls = QWidget()
        self.controls.setStyleSheet(f"background: {CARD_BG}; border-radius: 10px;")
        ctrl_outer = QVBoxLayout(self.controls)
        ctrl_outer.setContentsMargins(14, 12, 14, 12)
        ctrl_outer.setSpacing(10)

        # Row 1: threshold slider
        row1 = QHBoxLayout()
        row1.setSpacing(10)
        thr_label = QLabel("Threshold")
        thr_label.setStyleSheet(f"color: {TEXT_LABEL}; font-size: 12px;")
        thr_label.setFixedWidth(62)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(100, 254)
        self.slider.setValue(220)
        self.slider.valueChanged.connect(self._reprocess)
        self.slider.setStyleSheet(SLIDER_STYLE)
        row1.addWidget(thr_label)
        row1.addWidget(self.slider)
        ctrl_outer.addLayout(row1)

        # Divider
        div = QWidget()
        div.setFixedHeight(1)
        div.setStyleSheet("background: #2a2a2c;")
        ctrl_outer.addWidget(div)

        # Row 2: toggles + background
        row2 = QHBoxLayout()
        row2.setSpacing(16)

        self.chk_bw = QCheckBox("B&W")
        self.chk_bw.setStyleSheet(CHECKBOX_STYLE)
        self.chk_bw.toggled.connect(self._on_grayscale_toggled)

        self.chk_invert = QCheckBox("Invert")
        self.chk_invert.setStyleSheet(CHECKBOX_STYLE)
        self.chk_invert.toggled.connect(self._on_invert_toggled)

        self.chk_remove_bg = QCheckBox("Remove bg")
        self.chk_remove_bg.setStyleSheet(CHECKBOX_STYLE)
        self.chk_remove_bg.setChecked(True)
        self.chk_remove_bg.toggled.connect(self._on_remove_bg_toggled)

        sep = QLabel("|")
        sep.setStyleSheet(f"color: #333; font-size: 16px;")

        self.radio_white = QRadioButton("White bg")
        self.radio_black = QRadioButton("Black bg")
        self.radio_white.setChecked(True)
        for r in (self.radio_white, self.radio_black):
            r.setStyleSheet(RADIO_STYLE)
            r.toggled.connect(self._on_bg_toggled)
        bg_group = QButtonGroup(self)
        bg_group.addButton(self.radio_white)
        bg_group.addButton(self.radio_black)

        row2.addWidget(self.chk_bw)
        row2.addWidget(self.chk_invert)
        row2.addWidget(self.chk_remove_bg)
        row2.addWidget(sep)
        row2.addWidget(self.radio_white)
        row2.addWidget(self.radio_black)
        row2.addStretch()
        ctrl_outer.addLayout(row2)

        self.controls.setVisible(False)
        layout.addWidget(self.controls)

        # ---- Buttons ----
        self.btn_row = QWidget()
        btn_layout = QHBoxLayout(self.btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(10)

        self.btn_confirm = QPushButton("Add to menu bar")
        self.btn_confirm.setStyleSheet(BTN_STYLE.format(bg=ACCENT, hv=ACCENT_HV, weight='600'))
        self.btn_confirm.clicked.connect(self._add_to_menu_bar)

        self.btn_reset = QPushButton("Choose different image")
        self.btn_reset.setStyleSheet(BTN_STYLE.format(bg=BTN_GREY, hv=BTN_GREY_HV, weight='400'))
        self.btn_reset.clicked.connect(self._reset)

        btn_layout.addWidget(self.btn_confirm)
        btn_layout.addWidget(self.btn_reset)
        btn_layout.addStretch()

        self.btn_row.setVisible(False)
        layout.addWidget(self.btn_row)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_image(self, path: str) -> None:
        try:
            self._raw_frames = extract_frames(path)
        except Exception as exc:
            self.drop_zone.setText(f"Could not open image:\n{exc}")
            return

        self._is_animated = len(self._raw_frames) > 1
        self._bg_hint = detect_background(self._raw_frames[0][0])
        (self.radio_white if self._bg_hint == 'white' else self.radio_black).setChecked(True)

        self._reprocess()
        self.drop_zone.setVisible(False)
        self.preview_panel.setVisible(True)
        self.controls.setVisible(True)
        self.btn_row.setVisible(True)
        self.setFixedSize(584, 620)

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def _on_bg_toggled(self) -> None:
        self._bg_hint = 'white' if self.radio_white.isChecked() else 'black'
        self._reprocess()

    def _on_grayscale_toggled(self, checked: bool) -> None:
        self._grayscale = checked
        self._reprocess()

    def _on_invert_toggled(self, checked: bool) -> None:
        self._inverted = checked
        self._reprocess()

    def _on_remove_bg_toggled(self, checked: bool) -> None:
        self._remove_bg = checked
        self.radio_white.setEnabled(checked)
        self.radio_black.setEnabled(checked)
        self.slider.setEnabled(checked)
        self._reprocess()

    def _reprocess(self) -> None:
        if not self._raw_frames:
            return
        threshold = self.slider.value()
        self._processed_frames = []
        for raw_img, duration in self._raw_frames:
            src = raw_img
            if self._grayscale:
                src = to_grayscale(src)
            if self._inverted:
                src = invert_image(src)
            out = remove_background(src, threshold, self._bg_hint) if self._remove_bg else src.convert('RGBA')
            self._processed_frames.append((out, duration))

        self._preview_timer.stop()
        self._preview_idx = 0
        self._show_preview_frame()
        if self._is_animated:
            self._schedule_preview()

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def _show_preview_frame(self) -> None:
        if not self._processed_frames:
            return
        orig_img, _ = self._raw_frames[self._preview_idx]
        proc_img, _ = self._processed_frames[self._preview_idx]
        self.orig_label.setPixmap(pil_to_pixmap(orig_img, 248))
        self.proc_label.setPixmap(pil_to_pixmap(with_checkerboard(round_corners(proc_img, 20)), 248))

    def _schedule_preview(self) -> None:
        _, duration = self._processed_frames[self._preview_idx]
        self._preview_timer.start(max(duration, MIN_FRAME_MS))

    def _advance_preview(self) -> None:
        self._preview_idx = (self._preview_idx + 1) % len(self._processed_frames)
        self._show_preview_frame()
        self._schedule_preview()

    # ------------------------------------------------------------------
    # Tray
    # ------------------------------------------------------------------

    def _add_to_menu_bar(self) -> None:
        if not self._processed_frames:
            return

        self._tray_idx = 0
        first_img, first_dur = self._processed_frames[0]

        if self._tray is not None:
            self._tray_timer.stop()
            self._tray.setIcon(make_tray_icon(first_img))
            self._tray.setVisible(True)
        else:
            self._tray = QSystemTrayIcon(make_tray_icon(first_img), self)
            menu = QMenu()
            show_act = QAction("Show window", self)
            show_act.triggered.connect(self._show_window)
            new_act = QAction("Load new image…", self)
            new_act.triggered.connect(self._show_and_reset)
            remove_act = QAction("Remove from menu bar", self)
            remove_act.triggered.connect(self._remove_from_menu_bar)
            quit_act = QAction("Quit", self)
            quit_act.triggered.connect(QApplication.quit)
            menu.addAction(show_act)
            menu.addAction(new_act)
            menu.addSeparator()
            menu.addAction(remove_act)
            menu.addSeparator()
            menu.addAction(quit_act)
            self._tray.setContextMenu(menu)
            self._tray.activated.connect(self._tray_activated)
            self._tray.setVisible(True)

        if self._is_animated:
            self._tray_timer.start(max(first_dur, MIN_FRAME_MS))

        self.hide()

    def _advance_tray(self) -> None:
        if not self._tray or not self._processed_frames:
            return
        self._tray_idx = (self._tray_idx + 1) % len(self._processed_frames)
        frame_img, duration = self._processed_frames[self._tray_idx]
        self._tray.setIcon(make_tray_icon(frame_img))
        self._tray_timer.start(max(duration, MIN_FRAME_MS))

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_window()

    # ------------------------------------------------------------------
    # Window
    # ------------------------------------------------------------------

    def _show_window(self) -> None:
        self.show()
        self.raise_()
        self.activateWindow()

    def _show_and_reset(self) -> None:
        self._reset()
        self._show_window()

    def _remove_from_menu_bar(self) -> None:
        self._tray_timer.stop()
        if self._tray:
            self._tray.setVisible(False)
        self._show_window()

    def _reset(self) -> None:
        self._preview_timer.stop()
        self._tray_timer.stop()
        self._raw_frames = []
        self._processed_frames = []
        self._is_animated = False
        self._inverted = False
        self._grayscale = False
        self.chk_invert.setChecked(False)
        self.chk_bw.setChecked(False)
        self.chk_remove_bg.setChecked(True)
        self._remove_bg = True
        self.radio_white.setEnabled(True)
        self.radio_black.setEnabled(True)
        self.slider.setEnabled(True)
        self.drop_zone.setText("Drop an image here\nor click to browse")
        self.drop_zone.setVisible(True)
        self.preview_panel.setVisible(False)
        self.controls.setVisible(False)
        self.btn_row.setVisible(False)
        self.setFixedSize(584, 520)
