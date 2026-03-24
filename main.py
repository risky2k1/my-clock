import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from typing import Callable
from zoneinfo import ZoneInfo

from PyQt6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QFont,
    QFontInfo,
    QIcon,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QShowEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QMenuBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

CONFIG_FILE = "alarm_config.json"
LOCALES_DIR = Path(__file__).resolve().parent / "locales"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"
TRASH_ICON_OUTLINE = ASSETS_DIR / "trash.png"
TRASH_ICON_SOLID = ASSETS_DIR / "trash-solid.png"
DAY_KEYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
WK_MAP = {0: "T2", 1: "T3", 2: "T4", 3: "T5", 4: "T6", 5: "T7", 6: "CN"}

MONO = (
    "'JetBrains Mono', 'JetBrainsMono NF', 'JetBrainsMono Nerd Font', "
    "'Fira Code', 'Cascadia Code', monospace"
)


def _tint_pixmap_mask(src: QPixmap, color: QColor) -> QPixmap:
    """Giữ alpha của src, đổi màu (icon đen / xám trên nền trong suốt)."""
    out = QPixmap(src.size())
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.fillRect(out.rect(), color)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
    p.drawPixmap(0, 0, src)
    p.end()
    return out


def _trash_icon_painted_fallback(is_dark: bool, size: int) -> QIcon:
    s = float(size)
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    col = QColor("#cbd5e1" if is_dark else "#5c6370")
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(col)
    pen.setWidthF(max(1.0, s * 0.09))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    m = s * 0.16
    bw = s - 2 * m
    bh = s * 0.52
    bx = m
    by = s * 0.36
    lid_y = s * 0.28
    p.drawLine(QPointF(bx + bw * 0.12, lid_y), QPointF(bx + bw * 0.88, lid_y))
    body = QRectF(bx, by, bw, bh)
    p.drawRoundedRect(body, s * 0.06, s * 0.06)
    iy1, iy2 = by + bh * 0.22, by + bh * 0.88
    p.drawLine(QPointF(bx + bw * 0.36, iy1), QPointF(bx + bw * 0.36, iy2))
    p.drawLine(QPointF(bx + bw * 0.64, iy1), QPointF(bx + bw * 0.64, iy2))
    p.end()
    return QIcon(pix)


def trash_icon_for_theme(is_dark: bool, size: int = 22) -> QIcon:
    """Light: assets/trash.png (outline). Dark: assets/trash-solid.png + tô sáng."""
    path = TRASH_ICON_SOLID if is_dark else TRASH_ICON_OUTLINE
    pm = QPixmap(str(path))
    if pm.isNull():
        return _trash_icon_painted_fallback(is_dark, size)
    pm = pm.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    tint = QColor("#cbd5e1" if is_dark else "#5c6370")
    pm = _tint_pixmap_mask(pm, tint)
    return QIcon(pm)


def load_strings() -> dict[str, dict[str, str]]:
    """Đọc bản dịch từ locales/vi.json và locales/en.json."""
    out: dict[str, dict[str, str]] = {}
    for code in ("vi", "en"):
        path = LOCALES_DIR / f"{code}.json"
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                out[code] = {str(k): str(v) for k, v in raw.items()}
            else:
                out[code] = {}
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            out[code] = {}
    return out


STRINGS = load_strings()

COMMON_TIMEZONE_SET = frozenset(
    {
        "UTC",
        "Etc/GMT",
        "Etc/GMT+12",
        "Europe/London",
        "Europe/Paris",
        "Europe/Berlin",
        "Asia/Ho_Chi_Minh",
        "Asia/Bangkok",
        "Asia/Singapore",
        "Asia/Tokyo",
        "Asia/Seoul",
        "Asia/Shanghai",
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Los_Angeles",
        "Australia/Sydney",
    }
)
COMMON_TIMEZONES = sorted(COMMON_TIMEZONE_SET)


def _parse_hh_mm(s: str) -> tuple[int, int]:
    parts = s.strip().replace(":", " ").split()
    try:
        h = int(parts[0]) if parts else 0
        m = int(parts[1]) if len(parts) > 1 else 0
        return max(0, min(23, h)), max(0, min(59, m))
    except (ValueError, IndexError):
        return 7, 0


def format_time_display(hhmm: str, time_format: str, t: Callable[[str], str]) -> str:
    h, m = _parse_hh_mm(hhmm)
    if time_format != "12h":
        return f"{h:02d}∶{m:02d}"
    am = h < 12
    h12 = h % 12
    if h12 == 0:
        h12 = 12
    suf = t("time.am") if am else t("time.pm")
    return f"{h12}∶{m:02d} {suf}"


def format_alarm_schedule_i18n(alarm: dict, t: Callable[[str], str]) -> str:
    days = alarm.get("days", {})
    labels = []
    for dk in DAY_KEYS:
        if days.get(dk):
            labels.append(t(f"day.{dk.lower()}"))
    if len(labels) == 7:
        return t("schedule.every_day")
    if not labels:
        return t("schedule.no_days")
    return " · ".join(labels)


def lighten_hex(hex_color: str, amount: float = 0.15) -> str:
    hex_color = hex_color.strip().lstrip("#")
    if len(hex_color) != 6:
        return "#34a853"
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    r = min(255, int(r + (255 - r) * amount))
    g = min(255, int(g + (255 - g) * amount))
    b = min(255, int(b + (255 - b) * amount))
    return f"#{r:02x}{g:02x}{b:02x}"


def build_app_stylesheet(eff: str, accent: str) -> str:
    ah = lighten_hex(accent, 0.18)
    m = MONO
    if eff == "dark":
        return f"""
    QWidget {{ background-color: #1e2128; color: #e8eaed; font-family: {m}; }}
    QLabel {{ background-color: transparent; border: none; }}
    QLabel#page_title {{ font-size: 22px; font-weight: 600; color: #f1f3f4; margin-top: 4px; }}
    QLabel#page_subtitle {{ font-size: 12px; color: #9aa0a6; margin-bottom: 8px; }}
    QLabel#empty_hint {{ font-size: 14px; color: #9aa0a6; padding: 20px 16px; }}
    QPushButton {{ background-color: #3c4043; border-radius: 8px; padding: 8px 14px;
                  border: none; color: #e8eaed; }}
    QPushButton:hover {{ background-color: #5f6368; }}
    QPushButton:pressed {{ background-color: #44474c; }}
    QPushButton#btn_primary {{ background-color: {accent}; font-weight: 600; color: white; }}
    QPushButton#btn_primary:hover {{ background-color: {ah}; }}
    QPushButton#btn_secondary {{ background-color: transparent; border: 1px solid #5f6368;
                                 color: #bdc1c6; }}
    QPushButton#btn_secondary:hover {{ background-color: #3c4043; }}
    QPushButton#btn_danger {{ border: 1px solid #5f6368; color: #ea4335; }}
    QPushButton#btn_danger:hover {{ background-color: #c5221f; color: white; border-color: #c5221f; }}
    QPushButton#btn_new_alarm {{ background-color: transparent; border: 2px dashed {accent};
                                 color: #e8eaed; font-weight: 600; border-radius: 12px;
                                 padding: 12px 16px; margin-top: 8px; }}
    QPushButton#btn_new_alarm:hover {{ background-color: #2d3139; border-color: {ah}; color: #fff; }}
    QPushButton#alarm_delete_btn {{ background: transparent; border: none; padding: 6px;
                                   border-radius: 8px; min-width: 36px; min-height: 36px; }}
    QPushButton#alarm_delete_btn:hover {{ background-color: #3c4043; }}
    QWidget#alarm_row {{
        background-color: #222831;
        border-radius: 16px;
        border: 2px solid #6b7689;
    }}
    QWidget#alarm_row:hover {{
        border: 2px solid #8b97ab;
        background-color: #2a3140;
    }}
    QLabel#alarm_name_label {{ font-size: 13px; font-weight: 600; color: #bdc1c6;
                             background-color: transparent; }}
    QLabel#alarm_name_muted {{ font-size: 13px; font-weight: 500; color: #6d7580; font-style: italic;
                              background-color: transparent; }}
    QLabel#alarm_time_label {{ font-size: 24px; font-weight: 700; color: #f1f3f4;
                              background-color: transparent; }}
    QLabel#alarm_schedule_label {{ font-size: 12px; color: #9aa0a6;
                                  background-color: transparent; }}
    QListWidget#alarm_list_widget {{ background: transparent; border: none;
                                    outline: none; padding: 0 2px 4px 2px; }}
    QListWidget#alarm_list_widget::item {{ background: transparent; border: none;
                                          padding: 8px 2px; }}
    QListWidget#alarm_list_widget::item:selected {{ background: transparent; }}
    QListWidget#alarm_list_widget::item:hover {{ background: transparent; }}
    QListWidget#music_lib_list {{ background: #292d32; border: 1px solid #3c4043;
                                  border-radius: 8px; padding: 4px; color: #e8eaed; }}
    QFrame#list_panel {{ background: transparent; border: none; }}
    QLineEdit {{ background: #3c4043; border: 1px solid #5f6368; border-radius: 8px;
                 padding: 8px 10px; color: #e8eaed; selection-background-color: {accent}; }}
    QSpinBox, QComboBox {{ background: #3c4043; padding: 6px; border-radius: 8px;
                          border: 1px solid #5f6368; min-height: 28px; color: #e8eaed; }}
    QMenuBar {{ background: #25282e; border-bottom: 1px solid #3c4043; padding: 2px; }}
    QMenuBar::item:selected {{ background: #3c4043; }}
    QMenu {{ background: #292d32; border: 1px solid #3c4043; color: #e8eaed; }}
    QMenu::item:selected {{ background: #3c4043; }}
    QCheckBox {{ spacing: 8px; }}
"""
    return f"""
    QWidget {{ background-color: #f1f3f4; color: #202124; font-family: {m}; }}
    QLabel {{ background-color: transparent; border: none; }}
    QLabel#page_title {{ font-size: 22px; font-weight: 600; color: #202124; margin-top: 4px; }}
    QLabel#page_subtitle {{ font-size: 12px; color: #5f6368; margin-bottom: 8px; }}
    QLabel#empty_hint {{ font-size: 14px; color: #5f6368; padding: 20px 16px; }}
    QPushButton {{ background-color: #e8eaed; border-radius: 8px; padding: 8px 14px;
                  border: 1px solid #dadce0; color: #202124; }}
    QPushButton:hover {{ background-color: #f8f9fa; border-color: #bdc1c6; }}
    QPushButton:pressed {{ background-color: #dadce0; }}
    QPushButton#btn_primary {{ background-color: {accent}; font-weight: 600; color: white; border: none; }}
    QPushButton#btn_primary:hover {{ background-color: {ah}; }}
    QPushButton#btn_secondary {{ background-color: transparent; border: 1px solid #dadce0;
                                 color: #5f6368; }}
    QPushButton#btn_secondary:hover {{ background-color: #e8eaed; color: #202124; }}
    QPushButton#btn_danger {{ border: 1px solid #dadce0; color: #c5221f; }}
    QPushButton#btn_danger:hover {{ background-color: #fce8e6; color: #c5221f; border-color: #f9ab9d; }}
    QPushButton#btn_new_alarm {{ background-color: transparent; border: 2px dashed {accent};
                                 color: #202124; font-weight: 600; border-radius: 12px;
                                 padding: 12px 16px; margin-top: 8px; }}
    QPushButton#btn_new_alarm:hover {{ background-color: #e8f5e9; border-color: {ah}; }}
    QPushButton#alarm_delete_btn {{ background: transparent; border: none; padding: 6px;
                                   border-radius: 8px; min-width: 36px; min-height: 36px; }}
    QPushButton#alarm_delete_btn:hover {{ background-color: #e8eaed; }}
    QWidget#alarm_row {{
        background-color: #ffffff;
        border-radius: 16px;
        border: 2px solid #aeb8c9;
    }}
    QWidget#alarm_row:hover {{
        border: 2px solid #8ea0c0;
        background-color: #f6f8fc;
    }}
    QLabel#alarm_name_label {{ font-size: 13px; font-weight: 600; color: #3c4043;
                             background-color: transparent; }}
    QLabel#alarm_name_muted {{ font-size: 13px; font-weight: 500; color: #80868b; font-style: italic;
                              background-color: transparent; }}
    QLabel#alarm_time_label {{ font-size: 24px; font-weight: 700; color: #202124;
                              background-color: transparent; }}
    QLabel#alarm_schedule_label {{ font-size: 12px; color: #5f6368;
                                  background-color: transparent; }}
    QListWidget#alarm_list_widget {{ background: transparent; border: none;
                                    outline: none; padding: 0 2px 4px 2px; }}
    QListWidget#alarm_list_widget::item {{ background: transparent; border: none;
                                          padding: 8px 2px; }}
    QListWidget#alarm_list_widget::item:selected {{ background: transparent; }}
    QListWidget#alarm_list_widget::item:hover {{ background: transparent; }}
    QListWidget#music_lib_list {{ background: #fff; border: 1px solid #dadce0;
                                  border-radius: 8px; padding: 4px; color: #202124; }}
    QFrame#list_panel {{ background: transparent; border: none; }}
    QLineEdit {{ background: #fff; border: 1px solid #dadce0; border-radius: 8px;
                 padding: 8px 10px; color: #202124; selection-background-color: {accent};
                 selection-color: white; }}
    QSpinBox, QComboBox {{ background: #fff; padding: 6px; border-radius: 8px;
                          border: 1px solid #dadce0; min-height: 28px; color: #202124; }}
    QMenuBar {{ background: #fff; border-bottom: 1px solid #dadce0; padding: 2px; }}
    QMenuBar::item:selected {{ background: #e8eaed; }}
    QMenu {{ background: #fff; border: 1px solid #dadce0; color: #202124; }}
    QMenu::item:selected {{ background: #e8eaed; }}
    QCheckBox {{ spacing: 8px; }}
"""

SYSTEM_SOUND_CANDIDATES = [
    "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga",
    "/usr/share/sounds/freedesktop/stereo/complete.oga",
    "/usr/share/sounds/freedesktop/stereo/bell.oga",
    "/usr/share/sounds/freedesktop/stereo/message.oga",
]


def default_alarm():
    return {
        "id": str(uuid.uuid4()),
        "name": "",
        "time": "07:00",
        "enabled": True,
        "days": {d: True for d in DAY_KEYS},
        "sound_mode": "system",
        "sound_path": "",
        "ring_duration_sec": 120,
        "snooze_minutes": 5,
    }


def resolve_system_sound_path():
    for p in SYSTEM_SOUND_CANDIDATES:
        if os.path.isfile(p):
            return p
    return None


def play_sound_subprocess(sound_mode: str, sound_path: str):
    """Trả về Popen hoặc None nếu không phát được."""
    if sound_mode == "system":
        sys_path = resolve_system_sound_path()
        if not sys_path:
            return None
        for cmd in (
            ["paplay", sys_path],
            ["pw-play", sys_path],
            ["cvlc", "--play-and-exit", "--qt-start-minimized", sys_path],
        ):
            try:
                return subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                continue
        return None
    if sound_path and os.path.isfile(sound_path):
        for cmd in (
            ["cvlc", "--play-and-exit", "--qt-start-minimized", sound_path],
            ["mpv", "--no-video", sound_path],
        ):
            try:
                return subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                continue
    return None


def _lerp_qcolor(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
    )


class QCheckBoxCustom(QCheckBox):
    """Nút gạt tròn kiểu Material / iOS (track bo tròn + núm trắng)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("alarm_switch")
        self.setText("")
        self.setTristate(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._accent = QColor("#1e8e3e")
        self._dark = True
        self._track_w = 52
        self._track_h = 30
        self._knob_margin = 3
        self._knob_pos = 0.0
        self._anim = QPropertyAnimation(self, b"knobPos", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._run_knob_animation)
        self.setFixedSize(self._track_w, self._track_h)

    def setAccent(self, hex_color: str):
        h = (hex_color or "#1e8e3e").strip()
        if not h.startswith("#"):
            h = "#" + h
        self._accent = QColor(h)
        if not self._accent.isValid():
            self._accent = QColor("#1e8e3e")
        self.update()

    def setDarkTheme(self, dark: bool):
        self._dark = dark
        self.update()

    def getKnobPos(self) -> float:
        return self._knob_pos

    def setKnobPos(self, v: float):
        self._knob_pos = max(0.0, min(1.0, v))
        self.update()

    knobPos = pyqtProperty(float, getKnobPos, setKnobPos)

    def _run_knob_animation(self, checked: bool):
        self._anim.stop()
        self._anim.setStartValue(self._knob_pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def setCheckedQuiet(self, checked: bool):
        self.blockSignals(True)
        self._anim.stop()
        super().setChecked(checked)
        self._knob_pos = 1.0 if checked else 0.0
        self.blockSignals(False)
        self.update()

    def sizeHint(self):
        return QSize(self._track_w, self._track_h)

    def minimumSizeHint(self):
        return self.sizeHint()

    def hitButton(self, pos: QPoint) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = float(self._track_w), float(self._track_h)
        r = h / 2
        off_c = QColor("#6b7280") if self._dark else QColor("#c4cad4")
        track_c = _lerp_qcolor(off_c, self._accent, self._knob_pos)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(track_c))
        painter.drawRoundedRect(QRectF(0, 0, w, h), r, r)

        knob_d = h - 2 * self._knob_margin
        x_min = self._knob_margin
        x_max = w - self._knob_margin - knob_d
        span = max(0.0, x_max - x_min)
        x = x_min + self._knob_pos * span
        y = self._knob_margin

        knob_rect = QRectF(x, y, knob_d, knob_d)
        shadow_alpha = 55 if self._dark else 42
        painter.setPen(QPen(QColor(0, 0, 0, shadow_alpha), 1))
        painter.setBrush(QBrush(QColor("#fafafa")))
        painter.drawEllipse(knob_rect)


@dataclass
class UiContext:
    t: Callable[[str], str]
    time_format: str
    accent_color: str
    is_dark: bool


class AlarmListRow(QWidget):
    """Tên, giờ, lịch — gạt + xóa; chạm nội dung để sửa."""

    toggle_changed = pyqtSignal(bool)
    edit_requested = pyqtSignal()
    delete_requested = pyqtSignal()

    def __init__(self, alarm: dict, list_widget: QListWidget, ctx: UiContext, parent=None):
        super().__init__(parent)
        self._list = list_widget
        self._ctx = ctx
        self.setObjectName("alarm_row")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(6)
        self.lbl_name = QLabel()
        self.lbl_name.setObjectName("alarm_name_label")
        self.lbl_name.setWordWrap(True)
        self.lbl_name.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        left.addWidget(self.lbl_name)

        self.lbl_time = QLabel()
        self.lbl_time.setObjectName("alarm_time_label")
        self.lbl_time.setWordWrap(True)
        self.lbl_time.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        left.addWidget(self.lbl_time)

        self.lbl_schedule = QLabel()
        self.lbl_schedule.setObjectName("alarm_schedule_label")
        self.lbl_schedule.setWordWrap(True)
        self.lbl_schedule.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        left.addWidget(self.lbl_schedule)

        outer.addLayout(left, stretch=1)

        self.switch = QCheckBoxCustom()
        self.switch.setAccent(ctx.accent_color)
        self.switch.setDarkTheme(ctx.is_dark)
        self.switch.toggled.connect(self.toggle_changed.emit)
        outer.addWidget(self.switch, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.btn_delete = QPushButton()
        self.btn_delete.setObjectName("alarm_delete_btn")
        self.btn_delete.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_delete.setToolTip(ctx.t("row.delete_tip"))
        self.btn_delete.setIcon(trash_icon_for_theme(ctx.is_dark, 22))
        self.btn_delete.setIconSize(QSize(22, 22))
        self.btn_delete.clicked.connect(self.delete_requested.emit)
        outer.addWidget(self.btn_delete, alignment=Qt.AlignmentFlag.AlignVCenter)

        for w in (self.lbl_name, self.lbl_time, self.lbl_schedule):
            w.setCursor(Qt.CursorShape.PointingHandCursor)
            w.installEventFilter(self)

        self.update_from_alarm(alarm)

    def _apply_name_object_name(self, has_name: bool):
        name = "alarm_name_label" if has_name else "alarm_name_muted"
        if self.lbl_name.objectName() != name:
            self.lbl_name.setObjectName(name)
            self.lbl_name.style().unpolish(self.lbl_name)
            self.lbl_name.style().polish(self.lbl_name)

    def update_from_alarm(self, alarm: dict):
        self.switch.setCheckedQuiet(bool(alarm.get("enabled", True)))

        tfn = self._ctx.t
        name = (alarm.get("name") or "").strip()
        if name:
            self.lbl_name.setText(name)
            self._apply_name_object_name(True)
        else:
            self.lbl_name.setText(tfn("name.unset"))
            self._apply_name_object_name(False)

        self.lbl_time.setText(
            format_time_display(
                alarm.get("time", "07:00"), self._ctx.time_format, tfn
            )
        )
        self.lbl_schedule.setText(format_alarm_schedule_i18n(alarm, tfn))

        enabled = alarm.get("enabled", True)
        self.lbl_name.setEnabled(enabled)
        self.lbl_time.setEnabled(enabled)
        self.lbl_schedule.setEnabled(enabled)
        self.switch.setEnabled(True)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.MouseButtonPress and isinstance(
            event, QMouseEvent
        ):
            if watched in (self.lbl_name, self.lbl_time, self.lbl_schedule):
                if event.button() == Qt.MouseButton.LeftButton:
                    self._select_self_in_list()
                    self.edit_requested.emit()
                    return True
        return super().eventFilter(watched, event)

    def mousePressEvent(self, event):
        self._select_self_in_list()
        if event.button() == Qt.MouseButton.LeftButton:
            w = self.childAt(event.pos())
            if w is None:
                self.edit_requested.emit()
        super().mousePressEvent(event)

    def _is_under_switch_or_delete(self, w):
        while w is not None:
            if w is self.switch or w is self.btn_delete:
                return True
            w = w.parentWidget()
            if w is self:
                break
        return False

    def _select_self_in_list(self):
        for i in range(self._list.count()):
            it = self._list.item(i)
            if self._list.itemWidget(it) == self:
                self._list.setCurrentRow(i)
                break


class MusicLibraryDialog(QDialog):
    def __init__(self, music_library: list, t: Callable[[str], str], parent=None):
        super().__init__(parent)
        self._t = t
        self.setWindowTitle(t("music_lib.title"))
        self.music_library = list(music_library)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(t("music_lib.hint")))
        self.list_w = QListWidget()
        self.list_w.setObjectName("music_lib_list")
        for p in self.music_library:
            self.list_w.addItem(os.path.basename(p))
        layout.addWidget(self.list_w)
        row = QHBoxLayout()
        btn_add = QPushButton(t("music_lib.add"))
        btn_add.clicked.connect(self._add)
        btn_rm = QPushButton(t("music_lib.rm"))
        btn_rm.clicked.connect(self._remove)
        row.addWidget(btn_add)
        row.addWidget(btn_rm)
        layout.addLayout(row)
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)
        self.resize(420, 320)

    def _add(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, self._t("editor.browse_mp3"), "", "Audio (*.mp3);;All (*.*)"
        )
        for f in files:
            if f not in self.music_library:
                self.music_library.append(f)
                self.list_w.addItem(os.path.basename(f))

    def _remove(self):
        row = self.list_w.currentRow()
        if row >= 0:
            self.music_library.pop(row)
            self.list_w.takeItem(row)

    def result_library(self):
        return self.music_library


class AlarmEditorDialog(QDialog):
    def __init__(
        self,
        alarm: dict,
        music_library: list,
        time_format: str,
        t: Callable[[str], str],
        parent=None,
    ):
        super().__init__(parent)
        self._t = t
        self._time_format = time_format if time_format in ("12h", "24h") else "24h"
        self.setWindowTitle(t("editor.title"))
        self.alarm = {**default_alarm(), **alarm}
        if "id" not in self.alarm:
            self.alarm["id"] = str(uuid.uuid4())
        self.music_library = music_library

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(t("editor.name")))
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText(t("editor.name_ph"))
        self.edit_name.setText(self.alarm.get("name", "") or "")
        layout.addWidget(self.edit_name)

        time_row = QHBoxLayout()
        time_row.addWidget(QLabel(t("editor.hour")))
        self.spin_hour = QSpinBox()
        self.spin_hour.setMinimumWidth(72)
        time_row.addWidget(self.spin_hour)
        time_row.addWidget(QLabel(t("editor.min")))
        self.spin_min = QSpinBox()
        self.spin_min.setRange(0, 59)
        self.spin_min.setSuffix(t("time.suffix_minute"))
        self.spin_min.setMinimumWidth(80)
        time_row.addWidget(self.spin_min)
        self.combo_ampm = QComboBox()
        self.combo_ampm.addItem(t("time.am"), True)
        self.combo_ampm.addItem(t("time.pm"), False)
        time_row.addWidget(self.combo_ampm)
        time_row.addStretch()
        layout.addLayout(time_row)

        self._apply_time_spin_mode()
        self._load_time_from_alarm()

        layout.addWidget(QLabel(t("editor.repeat")))
        days_wrap = QHBoxLayout()
        self.day_boxes = {}
        for d in DAY_KEYS:
            cb = QCheckBox(t(f"day.{d.lower()}"))
            cb.setChecked(self.alarm.get("days", {}).get(d, True))
            self.day_boxes[d] = cb
            days_wrap.addWidget(cb)
        layout.addLayout(days_wrap)

        form = QFormLayout()
        self.combo_sound = QComboBox()
        self._rebuild_sound_combo()
        form.addRow(t("editor.sound"), self.combo_sound)
        self.spin_ring = QSpinBox()
        self.spin_ring.setRange(10, 3600)
        self.spin_ring.setSuffix(t("editor.ring_suffix"))
        self.spin_ring.setValue(int(self.alarm.get("ring_duration_sec", 120)))
        form.addRow(t("editor.ring"), self.spin_ring)
        self.spin_snooze = QSpinBox()
        self.spin_snooze.setRange(1, 60)
        self.spin_snooze.setSuffix(t("editor.snooze_suffix"))
        self.spin_snooze.setValue(int(self.alarm.get("snooze_minutes", 5)))
        form.addRow(t("editor.snooze"), self.spin_snooze)
        layout.addLayout(form)

        btn_browse = QPushButton(t("editor.browse_mp3"))
        btn_browse.clicked.connect(self._browse_mp3)
        layout.addWidget(btn_browse)

        self.chk_enabled = QCheckBox(t("editor.enabled"))
        self.chk_enabled.setChecked(self.alarm.get("enabled", True))
        layout.addWidget(self.chk_enabled)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)
        self.resize(460, 420)

    def _apply_time_spin_mode(self):
        t = self._t
        if self._time_format == "12h":
            self.spin_hour.setRange(1, 12)
            self.spin_hour.setSuffix("")
            self.combo_ampm.setVisible(True)
        else:
            self.spin_hour.setRange(0, 23)
            self.spin_hour.setSuffix(t("time.suffix_hour"))
            self.combo_ampm.setVisible(False)

    def _load_time_from_alarm(self):
        h, m = _parse_hh_mm(self.alarm.get("time", "07:00"))
        self.spin_min.setValue(m)
        if self._time_format == "12h":
            am = h < 12
            h12 = h % 12
            if h12 == 0:
                h12 = 12
            self.spin_hour.setValue(h12)
            self.combo_ampm.setCurrentIndex(0 if am else 1)
        else:
            self.spin_hour.setValue(h)

    def _time_24_from_ui(self) -> str:
        m = self.spin_min.value()
        if self._time_format == "12h":
            h12 = self.spin_hour.value()
            is_am = self.combo_ampm.currentData()
            if is_am:
                h24 = 0 if h12 == 12 else h12
            else:
                h24 = 12 if h12 == 12 else h12 + 12
            return f"{h24:02d}:{m:02d}"
        return f"{self.spin_hour.value():02d}:{m:02d}"

    def _rebuild_sound_combo(self):
        t = self._t
        self.combo_sound.clear()
        self.combo_sound.addItem(t("editor.sound_system"), ("system", ""))
        for p in self.music_library:
            self.combo_sound.addItem(os.path.basename(p), ("file", p))
        mode = self.alarm.get("sound_mode", "system")
        path = self.alarm.get("sound_path", "")
        for i in range(self.combo_sound.count()):
            m, fp = self.combo_sound.itemData(i)
            if mode == m and (m == "system" or fp == path):
                self.combo_sound.setCurrentIndex(i)
                return
        self.combo_sound.setCurrentIndex(0)

    def _browse_mp3(self):
        f, _ = QFileDialog.getOpenFileName(
            self, self._t("editor.browse_mp3"), "", "Audio (*.mp3);;All (*.*)"
        )
        if not f:
            return
        self.combo_sound.addItem(os.path.basename(f), ("file", f))
        self.combo_sound.setCurrentIndex(self.combo_sound.count() - 1)

    def to_alarm_dict(self) -> dict:
        idx = self.combo_sound.currentIndex()
        mode, path = self.combo_sound.itemData(idx)
        return {
            "id": self.alarm["id"],
            "name": self.edit_name.text().strip(),
            "time": self._time_24_from_ui(),
            "enabled": self.chk_enabled.isChecked(),
            "days": {d: cb.isChecked() for d, cb in self.day_boxes.items()},
            "sound_mode": mode,
            "sound_path": path if mode == "file" else "",
            "ring_duration_sec": self.spin_ring.value(),
            "snooze_minutes": self.spin_snooze.value(),
        }


class SettingsDialog(QDialog):
    def __init__(
        self,
        theme_mode: str,
        music_library: list,
        language: str,
        timezone: str,
        time_format: str,
        accent: str,
        t: Callable[[str], str],
        parent=None,
    ):
        super().__init__(parent)
        self._t = t
        self.setWindowTitle(t("settings.title"))
        self._music_library = list(music_library)
        self._accent = accent if self._is_hex_color(accent) else "#1e8e3e"

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(t("settings.language")))
        self.combo_lang = QComboBox()
        self.combo_lang.addItem("Tiếng Việt", "vi")
        self.combo_lang.addItem("English", "en")
        for i in range(self.combo_lang.count()):
            if self.combo_lang.itemData(i) == language:
                self.combo_lang.setCurrentIndex(i)
                break
        layout.addWidget(self.combo_lang)

        layout.addWidget(QLabel(t("settings.theme")))
        self.combo_theme = QComboBox()
        self.combo_theme.addItem(t("settings.theme_dark"), "dark")
        self.combo_theme.addItem(t("settings.theme_light"), "light")
        self.combo_theme.addItem(t("settings.theme_system"), "system")
        for i in range(self.combo_theme.count()):
            if self.combo_theme.itemData(i) == theme_mode:
                self.combo_theme.setCurrentIndex(i)
                break
        else:
            self.combo_theme.setCurrentIndex(0)
        layout.addWidget(self.combo_theme)

        layout.addWidget(QLabel(t("settings.tz")))
        self.combo_tz = QComboBox()
        self.combo_tz.setEditable(True)
        tz_extra = {timezone.strip()} if (timezone and timezone.strip()) else set()
        tz_opts = sorted(COMMON_TIMEZONE_SET | tz_extra)
        for z in tz_opts:
            self.combo_tz.addItem(z, z)
        idx = self.combo_tz.findData(timezone)
        if idx >= 0:
            self.combo_tz.setCurrentIndex(idx)
        else:
            self.combo_tz.setCurrentText(timezone or "UTC")

        layout.addWidget(self.combo_tz)

        layout.addWidget(QLabel(t("settings.time_format")))
        self.combo_tf = QComboBox()
        self.combo_tf.addItem(t("settings.24h"), "24h")
        self.combo_tf.addItem(t("settings.12h"), "12h")
        for i in range(self.combo_tf.count()):
            if self.combo_tf.itemData(i) == time_format:
                self.combo_tf.setCurrentIndex(i)
                break
        else:
            self.combo_tf.setCurrentIndex(0)
        layout.addWidget(self.combo_tf)

        layout.addWidget(QLabel(t("settings.accent")))
        acc_row = QHBoxLayout()
        self.lbl_accent_hex = QLabel(self._accent)
        self.lbl_accent_hex.setMinimumWidth(100)
        btn_pick = QPushButton(t("settings.pick_color"))
        btn_pick.clicked.connect(self._pick_accent)
        acc_row.addWidget(self.lbl_accent_hex)
        acc_row.addWidget(btn_pick)
        acc_row.addStretch()
        layout.addLayout(acc_row)

        layout.addSpacing(8)
        layout.addWidget(QLabel(t("settings.music")))
        btn_music = QPushButton(t("settings.music_lib"))
        btn_music.clicked.connect(self._open_music_library)
        layout.addWidget(btn_music)

        layout.addStretch()
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)
        self.resize(400, 520)

    @staticmethod
    def _is_hex_color(s: str) -> bool:
        s = (s or "").strip().lstrip("#")
        return len(s) == 6 and all(c in "0123456789abcdefABCDEF" for c in s)

    def _pick_accent(self):
        c = QColorDialog.getColor(QColor(self._accent), self)
        if c.isValid():
            self._accent = c.name()
            self.lbl_accent_hex.setText(self._accent)

    def _open_music_library(self):
        dlg = MusicLibraryDialog(list(self._music_library), self._t, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._music_library = dlg.result_library()

    def language_result(self) -> str:
        return self.combo_lang.currentData()

    def timezone_result(self) -> str:
        return self.combo_tz.currentText().strip() or "UTC"

    def time_format_result(self) -> str:
        return self.combo_tf.currentData()

    def accent_result(self) -> str:
        return self._accent

    def theme_result(self) -> str:
        return self.combo_theme.currentData()

    def music_library_result(self) -> list:
        return self._music_library


class ModernAlarm(QMainWindow):
    def __init__(self):
        super().__init__()
        self.music_library: list = []
        self.alarms: list = []
        self.theme_mode: str = "dark"
        self.language: str = "vi"
        self.timezone: str = "Asia/Ho_Chi_Minh"
        self.time_format: str = "24h"
        self.accent_color: str = "#1e8e3e"
        self.alarm_process = None
        self._last_fire_key: dict = {}
        self._snooze_until: dict = {}

        self.setMinimumWidth(520)

        self._build_menu()
        self._build_central()

        self.load_settings()
        self._refresh_ui_texts()
        self._apply_theme()
        QApplication.styleHints().colorSchemeChanged.connect(self._on_system_color_scheme_changed)

        self.timer = QTimer()
        self.timer.timeout.connect(self.check_time)
        self.timer.start(1000)

        self._ring_timer = QTimer()
        self._ring_timer.setSingleShot(True)
        self._ring_timer.timeout.connect(self._stop_alarm_sound)

    def _effective_theme(self) -> str:
        if self.theme_mode == "light":
            return "light"
        if self.theme_mode == "dark":
            return "dark"
        hints = QApplication.styleHints()
        scheme = hints.colorScheme()
        if scheme == Qt.ColorScheme.Light:
            return "light"
        if scheme == Qt.ColorScheme.Dark:
            return "dark"
        return "dark"

    def t(self, key: str, **kwargs) -> str:
        lang = self.language if self.language in STRINGS else "vi"
        s = STRINGS[lang].get(key, STRINGS["vi"].get(key, key))
        return s.format(**kwargs) if kwargs else s

    def _ui_ctx(self) -> UiContext:
        acc = self.accent_color.strip() if self.accent_color else "#1e8e3e"
        if len(acc.lstrip("#")) != 6:
            acc = "#1e8e3e"
        return UiContext(
            t=self.t,
            time_format=self.time_format,
            accent_color=acc,
            is_dark=self._effective_theme() == "dark",
        )

    def _apply_theme(self):
        app = QApplication.instance()
        if app is None:
            return
        eff = self._effective_theme()
        acc = self.accent_color.strip() if self.accent_color else "#1e8e3e"
        if len(acc.lstrip("#")) != 6:
            acc = "#1e8e3e"
        app.setStyleSheet(build_app_stylesheet(eff, acc))

    def _on_system_color_scheme_changed(self, *_args):
        if self.theme_mode == "system":
            self._apply_theme()

    def _refresh_ui_texts(self):
        self.setWindowTitle(self.t("app.title"))
        self.lbl_page_title.setText(self.t("page.title"))
        self.lbl_page_sub.setText(self.t("page.subtitle"))
        self.lbl_empty.setText(self.t("empty.hint"))
        self.btn_new.setText(self.t("btn.new_alarm"))
        if hasattr(self, "_menu_settings"):
            self._menu_settings.setTitle(self.t("menu.settings"))
            self._act_settings.setText(self.t("menu.open_settings"))

    def _open_settings(self):
        dlg = SettingsDialog(
            self.theme_mode,
            list(self.music_library),
            self.language,
            self.timezone,
            self.time_format,
            self.accent_color,
            self.t,
            self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.theme_mode = dlg.theme_result()
        self.music_library = dlg.music_library_result()
        self.language = dlg.language_result()
        self.timezone = dlg.timezone_result()
        self.time_format = dlg.time_format_result()
        self.accent_color = dlg.accent_result()
        self.save_settings()
        self._refresh_ui_texts()
        self._apply_theme()
        self._reload_alarm_list()

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        QTimer.singleShot(0, self._sync_alarm_row_widths)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_alarm_row_widths()

    def _sync_alarm_row_widths(self):
        if self.list_alarms.count() == 0:
            return
        vw = self.list_alarms.viewport().width()
        if vw < 80:
            vw = max(self.list_alarms.width() - 24, 0)
        if vw < 80:
            vw = 420
        # Trừ lề: padding item list + an toàn thanh cuộn / khung
        w = max(300, vw - 18)
        for i in range(self.list_alarms.count()):
            it = self.list_alarms.item(i)
            rw = self.list_alarms.itemWidget(it)
            h = max(88, rw.sizeHint().height() + 4) if rw else 88
            it.setSizeHint(QSize(w, h))
            if rw is not None:
                rw.setMaximumWidth(w)
                rw.setMinimumWidth(1)
                rw.updateGeometry()
        self.list_alarms.viewport().update()

    def _build_menu(self):
        bar = QMenuBar(self)
        self.setMenuBar(bar)
        self._menu_settings = bar.addMenu(self.t("menu.settings"))
        self._act_settings = QAction(self.t("menu.open_settings"), self)
        self._act_settings.triggered.connect(self._open_settings)
        self._menu_settings.addAction(self._act_settings)

    def _build_central(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 16, 20, 14)
        layout.setSpacing(0)

        self.lbl_page_title = QLabel(self.t("page.title"))
        self.lbl_page_title.setObjectName("page_title")
        layout.addWidget(self.lbl_page_title)
        self.lbl_page_sub = QLabel(self.t("page.subtitle"))
        self.lbl_page_sub.setObjectName("page_subtitle")
        self.lbl_page_sub.setWordWrap(True)
        layout.addWidget(self.lbl_page_sub)

        self.stack_empty = QWidget()
        empty_l = QVBoxLayout(self.stack_empty)
        empty_l.setContentsMargins(0, 24, 0, 16)
        self.lbl_empty = QLabel(self.t("empty.hint"))
        self.lbl_empty.setObjectName("empty_hint")
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty.setWordWrap(True)
        empty_l.addStretch()
        empty_l.addWidget(self.lbl_empty)
        empty_l.addStretch()

        self.list_panel = QFrame()
        self.list_panel.setObjectName("list_panel")
        list_outer = QVBoxLayout(self.list_panel)
        list_outer.setContentsMargins(0, 8, 0, 0)

        self.list_alarms = QListWidget()
        self.list_alarms.setObjectName("alarm_list_widget")
        self.list_alarms.setMinimumHeight(200)
        self.list_alarms.setSpacing(4)
        self.list_alarms.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        list_outer.addWidget(self.list_alarms, stretch=1)

        layout.addWidget(self.stack_empty, stretch=1)
        layout.addWidget(self.list_panel, stretch=1)

        self.btn_new = QPushButton(self.t("btn.new_alarm"))
        self.btn_new.setObjectName("btn_new_alarm")
        self.btn_new.setMinimumHeight(48)
        self.btn_new.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.btn_new.clicked.connect(self._new_alarm)
        layout.addWidget(self.btn_new, stretch=0)

        self._refresh_list_visibility()

    def _refresh_list_visibility(self):
        has = len(self.alarms) > 0
        self.stack_empty.setVisible(not has)
        self.list_panel.setVisible(has)
        self.lbl_page_sub.setVisible(has)

    def _reload_alarm_list(self):
        self.list_alarms.clear()
        for a in self.alarms:
            aid = a.get("id")
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, aid)
            row = AlarmListRow(a, self.list_alarms, self._ui_ctx())
            row.toggle_changed.connect(partial(self._on_toggle_alarm, aid))
            row.edit_requested.connect(partial(self._edit_alarm_by_id, aid))
            row.delete_requested.connect(partial(self._delete_alarm_by_id, aid))
            self.list_alarms.addItem(item)
            self.list_alarms.setItemWidget(item, row)
            h = max(88, row.sizeHint().height() + 4)
            vw0 = self.list_alarms.viewport().width() or 420
            w0 = max(300, vw0 - 18)
            row.setMaximumWidth(w0)
            row.setMinimumWidth(1)
            item.setSizeHint(QSize(w0, h))
        self._refresh_list_visibility()
        self._sync_alarm_row_widths()

    def _on_toggle_alarm(self, alarm_id: str, checked: bool):
        for a in self.alarms:
            if a.get("id") == alarm_id:
                a["enabled"] = checked
                break
        self.save_settings()
        self._update_row_for_id(alarm_id)

    def _update_row_for_id(self, alarm_id: str):
        alarm = next((a for a in self.alarms if a.get("id") == alarm_id), None)
        if not alarm:
            return
        for i in range(self.list_alarms.count()):
            it = self.list_alarms.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == alarm_id:
                w = self.list_alarms.itemWidget(it)
                if isinstance(w, AlarmListRow):
                    w.update_from_alarm(alarm)
                break

    def _edit_alarm_by_id(self, alarm_id: str):
        for i, a in enumerate(self.alarms):
            if a.get("id") == alarm_id:
                self._edit_alarm_at(i)
                return

    def _migrate_old_config(self, data: dict) -> dict:
        if data.get("version") == 2 or "alarms" in data:
            return data
        alarm = default_alarm()
        alarm["time"] = data.get("time", "07:00")
        alarm["enabled"] = data.get("enabled", False)
        alarm["days"] = data.get("days", alarm["days"])
        sel = data.get("selected_music", "")
        if sel and os.path.isfile(sel):
            alarm["sound_mode"] = "file"
            alarm["sound_path"] = sel
        return {
            "version": 2,
            "music_library": data.get("music_list", []),
            "alarms": [alarm],
        }

    def load_settings(self):
        if not os.path.exists(CONFIG_FILE):
            self.alarms = []
            self.music_library = []
            self.theme_mode = "dark"
            self.language = "vi"
            self.timezone = "Asia/Ho_Chi_Minh"
            self.time_format = "24h"
            self.accent_color = "#1e8e3e"
            self._reload_alarm_list()
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            data = self._migrate_old_config(raw)
            self.music_library = data.get("music_library", [])
            self.alarms = data.get("alarms", [])
            self.theme_mode = data.get("theme", "dark")
            if self.theme_mode not in ("dark", "light", "system"):
                self.theme_mode = "dark"
            self.language = data.get("language", "vi")
            if self.language not in STRINGS:
                self.language = "vi"
            self.timezone = data.get("timezone", "Asia/Ho_Chi_Minh") or "UTC"
            self.time_format = data.get("time_format", "24h")
            if self.time_format not in ("12h", "24h"):
                self.time_format = "24h"
            self.accent_color = data.get("accent_color", "#1e8e3e") or "#1e8e3e"
            self._reload_alarm_list()
            if raw.get("version") != 2:
                self.save_settings()
        except (json.JSONDecodeError, OSError):
            self.alarms = []
            self.music_library = []
            self.theme_mode = "dark"
            self.language = "vi"
            self.timezone = "Asia/Ho_Chi_Minh"
            self.time_format = "24h"
            self.accent_color = "#1e8e3e"

    def save_settings(self):
        data = {
            "version": 2,
            "theme": self.theme_mode,
            "language": self.language,
            "timezone": self.timezone,
            "time_format": self.time_format,
            "accent_color": self.accent_color,
            "music_library": self.music_library,
            "alarms": self.alarms,
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _new_alarm(self):
        dlg = AlarmEditorDialog(
            default_alarm(), self.music_library, self.time_format, self.t, self
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.alarms.append(dlg.to_alarm_dict())
        self.save_settings()
        self._reload_alarm_list()
        self.list_alarms.setCurrentRow(self.list_alarms.count() - 1)

    def _edit_alarm_at(self, index: int):
        dlg = AlarmEditorDialog(
            self.alarms[index], self.music_library, self.time_format, self.t, self
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.alarms[index] = dlg.to_alarm_dict()
        self.save_settings()
        self._reload_alarm_list()
        self.list_alarms.setCurrentRow(index)

    def _delete_alarm_by_id(self, alarm_id: str):
        for i, a in enumerate(self.alarms):
            if a.get("id") == alarm_id:
                self.alarms.pop(i)
                self.save_settings()
                self._reload_alarm_list()
                return

    def _stop_alarm_sound(self):
        if self.alarm_process:
            self.alarm_process.terminate()
            try:
                self.alarm_process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.alarm_process.kill()
            self.alarm_process = None

    def _now_in_tz(self) -> datetime:
        try:
            tz = ZoneInfo((self.timezone or "UTC").strip())
            return datetime.now(tz)
        except Exception:
            return datetime.now(ZoneInfo("UTC"))

    def check_time(self):
        now_dt = self._now_in_tz()
        now_str = now_dt.strftime("%H:%M")
        today = WK_MAP[now_dt.weekday()]
        minute_key = now_dt.strftime("%Y-%m-%d %H:%M")

        for a in self.alarms:
            if not a.get("enabled"):
                continue
            aid = a.get("id")
            if not a.get("days", {}).get(today):
                continue

            snooze_key = aid
            until = self._snooze_until.get(snooze_key)
            if until and now_dt >= until:
                del self._snooze_until[snooze_key]
                self._fire_alarm(a)
                continue

            if a.get("time") != now_str:
                continue
            if self._last_fire_key.get(aid) == minute_key:
                continue
            self._last_fire_key[aid] = minute_key
            self._fire_alarm(a)

    def _fire_alarm(self, alarm: dict):
        if self.alarm_process:
            self._stop_alarm_sound()

        mode = alarm.get("sound_mode", "system")
        path = alarm.get("sound_path", "")
        proc = play_sound_subprocess(mode, path)
        self.alarm_process = proc

        ring_sec = int(alarm.get("ring_duration_sec", 120))
        self._ring_timer.stop()
        self._ring_timer.start(ring_sec * 1000)

        if mode == "system":
            label = self.t("sound.system")
        else:
            label = os.path.basename(path) if path else self.t("sound.mp3")

        aname = (alarm.get("name") or "").strip()
        title = aname if aname else self.t("alarm.default_title")
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(f"{self.t('alarm.time_up')}\n{label}")
        snooze_m = int(alarm.get("snooze_minutes", 5))
        btn_snooze = msg.addButton(
            self.t("dlg.snooze", n=snooze_m), QMessageBox.ButtonRole.ActionRole
        )
        msg.addButton(self.t("dlg.stop"), QMessageBox.ButtonRole.DestructiveRole)
        msg.exec()

        clicked = msg.clickedButton()
        self._ring_timer.stop()
        self._stop_alarm_sound()

        if clicked == btn_snooze:
            self._snooze_until[alarm["id"]] = self._now_in_tz() + timedelta(
                minutes=snooze_m
            )
        else:
            self._last_fire_key[alarm["id"]] = self._now_in_tz().strftime(
                "%Y-%m-%d %H:%M"
            )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    _app_font = QFont("JetBrains Mono", 10)
    if not QFontInfo(_app_font).exactMatch():
        _app_font = QFont("monospace", 10)
    app.setFont(_app_font)
    win = ModernAlarm()
    win.show()
    sys.exit(app.exec())
