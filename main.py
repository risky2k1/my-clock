import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta
from functools import partial

from PyQt6.QtCore import QEvent, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QFont, QMouseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
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
    QSlider,
    QSpinBox,
    QStyle,
    QVBoxLayout,
    QWidget,
)

CONFIG_FILE = "alarm_config.json"
DAY_KEYS = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
DAY_MAP = {"Mon": "T2", "Tue": "T3", "Wed": "T4", "Thu": "T5", "Fri": "T6", "Sat": "T7", "Sun": "CN"}

# stylesheet áp dụng cho toàn app (cửa sổ chính + hộp thoại)
STYLE_DARK = """
    QWidget { background-color: #1e2128; color: #e8eaed;
              font-family: 'Segoe UI', 'Ubuntu', 'Noto Sans', sans-serif; }
    QLabel#page_title { font-size: 22px; font-weight: 600; color: #f1f3f4;
                         margin-top: 4px; }
    QLabel#page_subtitle { font-size: 12px; color: #9aa0a6; margin-bottom: 8px; }
    QLabel#empty_hint { font-size: 14px; color: #9aa0a6; padding: 20px 16px; }
    QPushButton { background-color: #3c4043; border-radius: 8px; padding: 8px 14px;
                  border: none; color: #e8eaed; }
    QPushButton:hover { background-color: #5f6368; }
    QPushButton:pressed { background-color: #44474c; }
    QPushButton#btn_primary { background-color: #1e8e3e; font-weight: 600; color: white; }
    QPushButton#btn_primary:hover { background-color: #34a853; }
    QPushButton#btn_secondary { background-color: transparent; border: 1px solid #5f6368;
                                 color: #bdc1c6; }
    QPushButton#btn_secondary:hover { background-color: #3c4043; }
    QPushButton#btn_danger { border: 1px solid #5f6368; color: #ea4335; }
    QPushButton#btn_danger:hover { background-color: #c5221f; color: white;
                                  border-color: #c5221f; }
    QPushButton#alarm_delete_btn { background: transparent; border: none; padding: 6px;
                                   border-radius: 8px; min-width: 36px; min-height: 36px; }
    QPushButton#alarm_delete_btn:hover { background-color: #3c4043; }
    QSlider#alarm_switch { min-height: 28px; max-height: 28px; }
    QSlider#alarm_switch::groove:horizontal {
        height: 22px; background: #3c4043; border-radius: 11px; margin: 2px 0;
    }
    QSlider#alarm_switch::sub-page:horizontal {
        background: #1e8e3e; border-radius: 11px;
    }
    QSlider#alarm_switch::add-page:horizontal {
        background: #3c4043; border-radius: 11px;
    }
    QSlider#alarm_switch::handle:horizontal {
        background: #e8eaed; width: 18px; height: 18px; margin: -5px 0;
        border-radius: 9px; border: 1px solid #bdc1c6;
    }
    QSlider#alarm_switch::handle:horizontal:hover { background: #fff; }
    QWidget#alarm_row { background-color: #292d32; border-radius: 14px;
                        border: 1px solid #3c4043; }
    QWidget#alarm_row:hover { border-color: #5f6368; background-color: #2d3138; }
    QLabel#alarm_name_label { font-size: 14px; font-weight: 600; color: #e8eaed; }
    QLabel#alarm_name_muted { font-size: 14px; font-weight: 500; color: #80868b; font-style: italic; }
    QLabel#alarm_time_label { font-size: 17px; font-weight: 600; color: #f1f3f4; }
    QLabel#alarm_schedule_label { font-size: 12px; color: #9aa0a6; }
    QListWidget#alarm_list_widget { background: transparent; border: none;
                                    outline: none; padding: 0 2px 8px 2px; }
    QListWidget#alarm_list_widget::item { background: transparent; border: none;
                                          padding: 5px 2px; }
    QListWidget#alarm_list_widget::item:selected { background: transparent; }
    QListWidget#alarm_list_widget::item:hover { background: transparent; }
    QListWidget#music_lib_list { background: #292d32; border: 1px solid #3c4043;
                                  border-radius: 8px; padding: 4px; color: #e8eaed; }
    QFrame#list_panel { background: transparent; border: none; }
    QLineEdit { background: #3c4043; border: 1px solid #5f6368; border-radius: 8px;
                 padding: 8px 10px; color: #e8eaed; selection-background-color: #1e8e3e; }
    QSpinBox, QComboBox { background: #3c4043; padding: 6px; border-radius: 8px;
                          border: 1px solid #5f6368; min-height: 28px; color: #e8eaed; }
    QMenuBar { background: #25282e; border-bottom: 1px solid #3c4043; padding: 2px; }
    QMenuBar::item:selected { background: #3c4043; }
    QMenu { background: #292d32; border: 1px solid #3c4043; color: #e8eaed; }
    QMenu::item:selected { background: #3c4043; }
"""

STYLE_LIGHT = """
    QWidget { background-color: #f1f3f4; color: #202124;
              font-family: 'Segoe UI', 'Ubuntu', 'Noto Sans', sans-serif; }
    QLabel#page_title { font-size: 22px; font-weight: 600; color: #202124;
                         margin-top: 4px; }
    QLabel#page_subtitle { font-size: 12px; color: #5f6368; margin-bottom: 8px; }
    QLabel#empty_hint { font-size: 14px; color: #5f6368; padding: 20px 16px; }
    QPushButton { background-color: #e8eaed; border-radius: 8px; padding: 8px 14px;
                  border: 1px solid #dadce0; color: #202124; }
    QPushButton:hover { background-color: #f8f9fa; border-color: #bdc1c6; }
    QPushButton:pressed { background-color: #dadce0; }
    QPushButton#btn_primary { background-color: #1e8e3e; font-weight: 600; color: white;
                               border: none; }
    QPushButton#btn_primary:hover { background-color: #34a853; }
    QPushButton#btn_secondary { background-color: transparent; border: 1px solid #dadce0;
                                 color: #5f6368; }
    QPushButton#btn_secondary:hover { background-color: #e8eaed; color: #202124; }
    QPushButton#btn_danger { border: 1px solid #dadce0; color: #c5221f; }
    QPushButton#btn_danger:hover { background-color: #fce8e6; color: #c5221f;
                                    border-color: #f9ab9d; }
    QPushButton#alarm_delete_btn { background: transparent; border: none; padding: 6px;
                                   border-radius: 8px; min-width: 36px; min-height: 36px; }
    QPushButton#alarm_delete_btn:hover { background-color: #e8eaed; }
    QSlider#alarm_switch { min-height: 28px; max-height: 28px; }
    QSlider#alarm_switch::groove:horizontal {
        height: 22px; background: #dadce0; border-radius: 11px; margin: 2px 0;
    }
    QSlider#alarm_switch::sub-page:horizontal {
        background: #1e8e3e; border-radius: 11px;
    }
    QSlider#alarm_switch::add-page:horizontal {
        background: #dadce0; border-radius: 11px;
    }
    QSlider#alarm_switch::handle:horizontal {
        background: #fff; width: 18px; height: 18px; margin: -5px 0;
        border-radius: 9px; border: 1px solid #bdc1c6;
    }
    QWidget#alarm_row { background-color: #ffffff; border-radius: 14px;
                        border: 1px solid #dadce0; }
    QWidget#alarm_row:hover { border-color: #bdc1c6; background-color: #fafafa; }
    QLabel#alarm_name_label { font-size: 14px; font-weight: 600; color: #202124; }
    QLabel#alarm_name_muted { font-size: 14px; font-weight: 500; color: #80868b; font-style: italic; }
    QLabel#alarm_time_label { font-size: 17px; font-weight: 600; color: #202124; }
    QLabel#alarm_schedule_label { font-size: 12px; color: #5f6368; }
    QListWidget#alarm_list_widget { background: transparent; border: none;
                                    outline: none; padding: 0 2px 8px 2px; }
    QListWidget#alarm_list_widget::item { background: transparent; border: none;
                                          padding: 5px 2px; }
    QListWidget#alarm_list_widget::item:selected { background: transparent; }
    QListWidget#alarm_list_widget::item:hover { background: transparent; }
    QListWidget#music_lib_list { background: #fff; border: 1px solid #dadce0;
                                  border-radius: 8px; padding: 4px; color: #202124; }
    QFrame#list_panel { background: transparent; border: none; }
    QLineEdit { background: #fff; border: 1px solid #dadce0; border-radius: 8px;
                 padding: 8px 10px; color: #202124; selection-background-color: #1e8e3e;
                 selection-color: white; }
    QSpinBox, QComboBox { background: #fff; padding: 6px; border-radius: 8px;
                          border: 1px solid #dadce0; min-height: 28px; color: #202124; }
    QMenuBar { background: #fff; border-bottom: 1px solid #dadce0; padding: 2px; }
    QMenuBar::item:selected { background: #e8eaed; }
    QMenu { background: #fff; border: 1px solid #dadce0; color: #202124; }
    QMenu::item:selected { background: #e8eaed; }
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


def _format_alarm_schedule(alarm: dict) -> str:
    days = alarm.get("days", {})
    day_parts = [d for d in DAY_KEYS if days.get(d)]
    if len(day_parts) == 7:
        return "Mỗi ngày"
    if not day_parts:
        return "Chưa chọn ngày"
    return " · ".join(day_parts)


class AlarmListRow(QWidget):
    """Một dòng: tên, giờ, thời điểm (lặp) — gạt bật/tắt + xóa; chạm nội dung để sửa."""

    toggle_changed = pyqtSignal(bool)
    edit_requested = pyqtSignal()
    delete_requested = pyqtSignal()

    def __init__(self, alarm: dict, list_widget: QListWidget, parent=None):
        super().__init__(parent)
        self._list = list_widget
        self.setObjectName("alarm_row")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(14, 12, 14, 12)
        outer.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(6)
        self.lbl_name = QLabel()
        self.lbl_name.setObjectName("alarm_name_label")
        self.lbl_name.setWordWrap(True)
        left.addWidget(self.lbl_name)

        time_row = QHBoxLayout()
        time_row.setSpacing(8)
        self.lbl_time = QLabel()
        self.lbl_time.setObjectName("alarm_time_label")
        self.lbl_schedule = QLabel()
        self.lbl_schedule.setObjectName("alarm_schedule_label")
        self.lbl_schedule.setWordWrap(True)
        time_row.addWidget(self.lbl_time, 0, Qt.AlignmentFlag.AlignVCenter)
        time_row.addWidget(self.lbl_schedule, 1, Qt.AlignmentFlag.AlignVCenter)
        left.addLayout(time_row)
        outer.addLayout(left, stretch=1)

        self.switch = QSlider(Qt.Orientation.Horizontal)
        self.switch.setObjectName("alarm_switch")
        self.switch.setRange(0, 1)
        self.switch.setSingleStep(1)
        self.switch.setPageStep(1)
        self.switch.setFixedWidth(54)
        self.switch.setFixedHeight(28)
        self.switch.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.switch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.switch.sliderReleased.connect(self._on_slider_released)
        outer.addWidget(self.switch, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.btn_delete = QPushButton()
        self.btn_delete.setObjectName("alarm_delete_btn")
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_delete.setToolTip("Xóa báo thức")
        trash = self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon)
        if trash.isNull():
            self.btn_delete.setText("\U0001F5D1")
            f = QFont()
            f.setPointSize(14)
            self.btn_delete.setFont(f)
        else:
            self.btn_delete.setIcon(trash)
            self.btn_delete.setIconSize(QSize(22, 22))
        self.btn_delete.clicked.connect(self.delete_requested.emit)
        outer.addWidget(self.btn_delete, alignment=Qt.AlignmentFlag.AlignVCenter)

        for w in (self.lbl_name, self.lbl_time, self.lbl_schedule):
            w.setCursor(Qt.CursorShape.PointingHandCursor)
            w.installEventFilter(self)

        self.update_from_alarm(alarm)

    def _on_slider_released(self):
        self.toggle_changed.emit(bool(self.switch.value()))

    def _apply_name_object_name(self, has_name: bool):
        name = "alarm_name_label" if has_name else "alarm_name_muted"
        if self.lbl_name.objectName() != name:
            self.lbl_name.setObjectName(name)
            self.lbl_name.style().unpolish(self.lbl_name)
            self.lbl_name.style().polish(self.lbl_name)

    def update_from_alarm(self, alarm: dict):
        self.switch.blockSignals(True)
        self.switch.setValue(1 if alarm.get("enabled", True) else 0)
        self.switch.blockSignals(False)

        name = (alarm.get("name") or "").strip()
        if name:
            self.lbl_name.setText(name)
            self._apply_name_object_name(True)
        else:
            self.lbl_name.setText("Chưa đặt tên")
            self._apply_name_object_name(False)

        t = alarm.get("time", "??:??")
        self.lbl_time.setText(t.replace(":", "∶"))
        self.lbl_schedule.setText(_format_alarm_schedule(alarm))

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
    def __init__(self, music_library: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Thư viện nhạc MP3")
        self.music_library = list(music_library)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Các file MP3 dùng khi báo thức chọn từ thư viện:"))
        self.list_w = QListWidget()
        self.list_w.setObjectName("music_lib_list")
        for p in self.music_library:
            self.list_w.addItem(os.path.basename(p))
        layout.addWidget(self.list_w)
        row = QHBoxLayout()
        btn_add = QPushButton("➕ Thêm MP3")
        btn_add.clicked.connect(self._add)
        btn_rm = QPushButton("🗑 Xóa khỏi thư viện")
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
            self, "Chọn MP3", "", "Audio (*.mp3);;All (*.*)"
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
    def __init__(self, alarm: dict, music_library: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Báo thức")
        self.alarm = {**default_alarm(), **alarm}
        if "id" not in self.alarm:
            self.alarm["id"] = str(uuid.uuid4())
        self.music_library = music_library

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Tên (tuỳ chọn)"))
        self.edit_name = QLineEdit()
        self.edit_name.setPlaceholderText("Ví dụ: Dậy đi làm, Uống thuốc…")
        self.edit_name.setText(self.alarm.get("name", "") or "")
        layout.addWidget(self.edit_name)

        time_row = QHBoxLayout()
        time_row.addWidget(QLabel("Giờ"))
        self.spin_hour = QSpinBox()
        self.spin_hour.setRange(0, 23)
        self.spin_hour.setSuffix(" h")
        self.spin_hour.setMinimumWidth(90)
        time_row.addWidget(self.spin_hour)
        time_row.addWidget(QLabel("Phút"))
        self.spin_min = QSpinBox()
        self.spin_min.setRange(0, 59)
        self.spin_min.setSuffix(" ph")
        self.spin_min.setMinimumWidth(90)
        time_row.addWidget(self.spin_min)
        time_row.addStretch()
        layout.addLayout(time_row)

        h, m = self._parse_time(self.alarm.get("time", "07:00"))
        self.spin_hour.setValue(h)
        self.spin_min.setValue(m)

        layout.addWidget(QLabel("Lặp trong tuần"))
        days_wrap = QHBoxLayout()
        self.day_boxes = {}
        for d in DAY_KEYS:
            cb = QCheckBox(d)
            cb.setChecked(self.alarm.get("days", {}).get(d, True))
            self.day_boxes[d] = cb
            days_wrap.addWidget(cb)
        layout.addLayout(days_wrap)

        form = QFormLayout()
        self.combo_sound = QComboBox()
        self._rebuild_sound_combo()
        form.addRow("Âm báo:", self.combo_sound)
        self.spin_ring = QSpinBox()
        self.spin_ring.setRange(10, 3600)
        self.spin_ring.setSuffix(" giây")
        self.spin_ring.setValue(int(self.alarm.get("ring_duration_sec", 120)))
        form.addRow("Thời lượng kêu:", self.spin_ring)
        self.spin_snooze = QSpinBox()
        self.spin_snooze.setRange(1, 60)
        self.spin_snooze.setSuffix(" phút")
        self.spin_snooze.setValue(int(self.alarm.get("snooze_minutes", 5)))
        form.addRow("Snooze:", self.spin_snooze)
        layout.addLayout(form)

        btn_browse = QPushButton("Chọn file MP3 khác…")
        btn_browse.clicked.connect(self._browse_mp3)
        layout.addWidget(btn_browse)

        self.chk_enabled = QCheckBox("Bật báo thức này")
        self.chk_enabled.setChecked(self.alarm.get("enabled", True))
        layout.addWidget(self.chk_enabled)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)
        self.resize(440, 380)

    def _parse_time(self, s: str):
        parts = s.replace(":", " ").split()
        try:
            h = int(parts[0]) if parts else 7
            m = int(parts[1]) if len(parts) > 1 else 0
            return max(0, min(23, h)), max(0, min(59, m))
        except (ValueError, IndexError):
            return 7, 0

    def _rebuild_sound_combo(self):
        self.combo_sound.clear()
        self.combo_sound.addItem("Âm thanh hệ thống", ("system", ""))
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
            self, "Chọn MP3", "", "Audio (*.mp3);;All (*.*)"
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
            "time": f"{self.spin_hour.value():02d}:{self.spin_min.value():02d}",
            "enabled": self.chk_enabled.isChecked(),
            "days": {d: cb.isChecked() for d, cb in self.day_boxes.items()},
            "sound_mode": mode,
            "sound_path": path if mode == "file" else "",
            "ring_duration_sec": self.spin_ring.value(),
            "snooze_minutes": self.spin_snooze.value(),
        }


class SettingsDialog(QDialog):
    """Cài đặt: giao diện + mở quản lý thư viện nhạc."""

    def __init__(self, theme_mode: str, music_library: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cài đặt")
        self._music_library = list(music_library)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Giao diện"))
        self.combo_theme = QComboBox()
        self.combo_theme.addItem("Tối", "dark")
        self.combo_theme.addItem("Sáng", "light")
        self.combo_theme.addItem("Theo hệ thống", "system")
        for i in range(self.combo_theme.count()):
            if self.combo_theme.itemData(i) == theme_mode:
                self.combo_theme.setCurrentIndex(i)
                break
        else:
            self.combo_theme.setCurrentIndex(0)
        layout.addWidget(self.combo_theme)

        layout.addSpacing(12)
        layout.addWidget(QLabel("Nhạc báo thức"))
        btn_music = QPushButton("Quản lý thư viện MP3…")
        btn_music.clicked.connect(self._open_music_library)
        layout.addWidget(btn_music)

        layout.addStretch()
        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)
        self.resize(360, 240)

    def _open_music_library(self):
        dlg = MusicLibraryDialog(list(self._music_library), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._music_library = dlg.result_library()

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
        self.alarm_process = None
        self._last_fire_key: dict = {}
        self._snooze_until: dict = {}

        self.setWindowTitle("Linux Smart Alarm")
        self.setMinimumWidth(440)

        self._build_menu()
        self._build_central()

        self.load_settings()
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

    def _apply_theme(self):
        app = QApplication.instance()
        if app is None:
            return
        eff = self._effective_theme()
        app.setStyleSheet(STYLE_LIGHT if eff == "light" else STYLE_DARK)

    def _on_system_color_scheme_changed(self, *_args):
        if self.theme_mode == "system":
            self._apply_theme()

    def _open_settings(self):
        dlg = SettingsDialog(self.theme_mode, self.music_library, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.theme_mode = dlg.theme_result()
        self.music_library = dlg.music_library_result()
        self.save_settings()
        self._apply_theme()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_alarm_row_widths()

    def _sync_alarm_row_widths(self):
        if not self.list_alarms.isVisible():
            return
        vw = self.list_alarms.viewport().width()
        w = max(280, vw - 8)
        for i in range(self.list_alarms.count()):
            it = self.list_alarms.item(i)
            rw = self.list_alarms.itemWidget(it)
            h = max(88, rw.sizeHint().height() + 4) if rw else 88
            it.setSizeHint(QSize(w, h))

    def _build_menu(self):
        bar = QMenuBar(self)
        self.setMenuBar(bar)
        m = bar.addMenu("Cài đặt")
        act = QAction("Cài đặt…", self)
        act.triggered.connect(self._open_settings)
        m.addAction(act)

    def _build_central(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 16, 20, 18)
        layout.setSpacing(0)

        self.lbl_page_title = QLabel("Báo thức")
        self.lbl_page_title.setObjectName("page_title")
        layout.addWidget(self.lbl_page_title)
        self.lbl_page_sub = QLabel(
            "Chạm tên / giờ / lịch trên thẻ để sửa · gạt ngang để bật hoặc tắt"
        )
        self.lbl_page_sub.setObjectName("page_subtitle")
        self.lbl_page_sub.setWordWrap(True)
        layout.addWidget(self.lbl_page_sub)

        self.stack_empty = QWidget()
        empty_l = QVBoxLayout(self.stack_empty)
        empty_l.setContentsMargins(0, 32, 0, 24)
        self.lbl_empty = QLabel(
            "Chưa có báo thức nào.\nTạo báo thức đầu tiên để bắt đầu."
        )
        self.lbl_empty.setObjectName("empty_hint")
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty.setWordWrap(True)
        empty_l.addStretch()
        empty_l.addWidget(self.lbl_empty)
        btn_new_empty = QPushButton("➕ Tạo báo thức")
        btn_new_empty.setObjectName("btn_primary")
        btn_new_empty.setMinimumHeight(44)
        btn_new_empty.clicked.connect(self._new_alarm)
        empty_l.addWidget(btn_new_empty, alignment=Qt.AlignmentFlag.AlignHCenter)
        empty_l.addStretch()

        self.list_panel = QFrame()
        self.list_panel.setObjectName("list_panel")
        list_outer = QVBoxLayout(self.list_panel)
        list_outer.setContentsMargins(0, 8, 0, 0)

        self.list_alarms = QListWidget()
        self.list_alarms.setObjectName("alarm_list_widget")
        self.list_alarms.setMinimumHeight(300)
        self.list_alarms.setSpacing(2)
        list_outer.addWidget(self.list_alarms)

        self.btn_new = QPushButton("➕ Tạo báo thức mới")
        self.btn_new.setObjectName("btn_primary")
        self.btn_new.setMinimumHeight(42)
        self.btn_new.clicked.connect(self._new_alarm)

        layout.addWidget(self.stack_empty)
        layout.addWidget(self.list_panel)
        layout.addWidget(self.btn_new)

        self._refresh_list_visibility()

    def _refresh_list_visibility(self):
        has = len(self.alarms) > 0
        self.stack_empty.setVisible(not has)
        self.list_panel.setVisible(has)
        self.lbl_page_sub.setVisible(has)
        self.btn_new.setVisible(has)

    def _reload_alarm_list(self):
        self.list_alarms.clear()
        for a in self.alarms:
            aid = a.get("id")
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, aid)
            row = AlarmListRow(a, self.list_alarms)
            row.toggle_changed.connect(partial(self._on_toggle_alarm, aid))
            row.edit_requested.connect(partial(self._edit_alarm_by_id, aid))
            row.delete_requested.connect(partial(self._delete_alarm_by_id, aid))
            self.list_alarms.addItem(item)
            self.list_alarms.setItemWidget(item, row)
            h = max(88, row.sizeHint().height() + 4)
            item.setSizeHint(QSize(max(280, (self.list_alarms.viewport().width() or 400) - 8), h))
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
            self._reload_alarm_list()
            if raw.get("version") != 2:
                self.save_settings()
        except (json.JSONDecodeError, OSError):
            self.alarms = []
            self.music_library = []
            self.theme_mode = "dark"

    def save_settings(self):
        data = {
            "version": 2,
            "theme": self.theme_mode,
            "music_library": self.music_library,
            "alarms": self.alarms,
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _new_alarm(self):
        dlg = AlarmEditorDialog(default_alarm(), self.music_library, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self.alarms.append(dlg.to_alarm_dict())
        self.save_settings()
        self._reload_alarm_list()
        self.list_alarms.setCurrentRow(self.list_alarms.count() - 1)

    def _edit_alarm_at(self, index: int):
        dlg = AlarmEditorDialog(self.alarms[index], self.music_library, self)
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

    def check_time(self):
        now_dt = datetime.now()
        now_str = now_dt.strftime("%H:%M")
        today = DAY_MAP[now_dt.strftime("%a")]
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
            label = "Âm thanh hệ thống"
        else:
            label = os.path.basename(path) if path else "MP3"

        aname = (alarm.get("name") or "").strip()
        title = aname if aname else "Báo thức"
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(f"Đến giờ!\n{label}")
        snooze_m = int(alarm.get("snooze_minutes", 5))
        btn_snooze = msg.addButton(f"Snooze {snooze_m} phút", QMessageBox.ButtonRole.ActionRole)
        msg.addButton("Dừng", QMessageBox.ButtonRole.DestructiveRole)
        msg.exec()

        clicked = msg.clickedButton()
        self._ring_timer.stop()
        self._stop_alarm_sound()

        if clicked == btn_snooze:
            self._snooze_until[alarm["id"]] = datetime.now() + timedelta(minutes=snooze_m)
        else:
            self._last_fire_key[alarm["id"]] = datetime.now().strftime("%Y-%m-%d %H:%M")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = ModernAlarm()
    win.show()
    sys.exit(app.exec())
