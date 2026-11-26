"""The Machine — local face-classification visualization (Windows 11 / Python 3.14).

Network streams are *optional*, connect only after explicit user action, and are
subject to source permission. No Windows Hello or logon changes are made.
"""
from __future__ import annotations

import math

import json
import sqlite3
import sys
import time
import traceback
from pathlib import Path
from uuid import uuid4
from zoneinfo import available_timezones

import cv2
from PySide6.QtCore import Qt, QDateTime, QTimer, QEvent, QVariantAnimation, QEasingCurve
from PySide6.QtGui import QImage, QPixmap, QIcon, QColor, QPainter, QPen, QFont, QFontDatabase, QCursor
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDateTimeEdit,
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QMessageBox, QPushButton, QSpinBox, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QProgressBar, QInputDialog,
    QGraphicsOpacityEffect, QSizePolicy, QSlider,
)

from camera_sources import validate_stream_url
from classifications import CATEGORIES, CATEGORY_BY_KEY, CAPTION_TO_CATEGORY
from database import Database
from face_engine import FaceEngine, FaceMatcher, missing_models
from hud import render
from metadata import clock_text, coordinates_text
from mjpeg_capture import MjpegCapture, prefers_http_mjpeg, MJPEGStreamError
from tracking import FaceTracker
from standby import render_standby
from ui_effects import smooth_pulse_opacity
from video_sources import VideoSourceSpec, open_video_source, SourceOpenError

ROOT = Path(__file__).resolve().parent
SETTINGS_FILE = ROOT / "data" / "settings.json"


# The Fangzheng typeface must be installed/licensed by the user. We do NOT
# distribute fonts. Qt falls back cleanly if Fangzheng is unavailable.
def preferred_chinese_font():
    families = list(QFontDatabase.families())
    prioritized = [
        "方正黑体", "方正黑体_GBK", "方正黑体简体", "方正黑体简体_GBK",
        "FZHei-B01", "FZHei-B01S", "FZHei-B01T",
    ]
    for target in prioritized:
        for available in families:
            if available.casefold() == target.casefold():
                return available
    for available in families:
        if "方正黑体" in available or "fzhei" in available.lower():
            return available
    return "Microsoft YaHei UI"


LEGEND_HTML = (
    '<span style="color:#eeeeee">● IRRELEVANT</span> &nbsp;'
    '<span style="color:#ff5050">● THREAT</span><br>'
    '<span style="color:#ffe550">● ADMIN / PRIMARY ASSET / SECONDARY ASSET / CONTINGENCY</span><br>'
    '<span style="color:#3b9fff">● ASSET CATALYST</span><br>'
    '<span style="color:#ffe550">◩ ANALOG INTERFACE / ROOT</span><br>'
    '<span style="color:#eff3fb">◩ RELEVANT-ONE / RELEVANT-TWO / RELEVANT-THREE / RELEVANT-OTHER</span><br>'
    '<span style="color:#ff6868">◩ IRRELEVANT THREAT</span>'
)


def load_settings():
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(settings):
    SETTINGS_FILE.parent.mkdir(exist_ok=True, parents=True)
    temp = SETTINGS_FILE.with_suffix(".json.tmp")
    temp.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(SETTINGS_FILE)


def fill_categories(combo):
    for category in CATEGORIES:
        combo.addItem(category.name_zh, category.key)


def fill_captions(combo, category_key):
    combo.clear()
    for label in CATEGORY_BY_KEY[category_key].captions:
        combo.addItem(label, label)


class AddPersonDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("录入人物 · 本地资料库")
        self.resize(470, 235)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：我自己 / 人物A")
        form.addRow("人物名称", self.name_edit)
        self.group_combo = QComboBox()
        fill_categories(self.group_combo)
        self.group_combo.setCurrentIndex(self.group_combo.findData("YELLOW"))
        form.addRow("边框分类", self.group_combo)
        self.caption_combo = QComboBox()
        fill_captions(self.caption_combo, "YELLOW")
        form.addRow("身份文字", self.caption_combo)
        self.group_combo.currentIndexChanged.connect(self.on_group_changed)
        layout.addLayout(form)
        hint = QLabel("本人默认：黄色 ADMIN。每个人物只有一个身份文字，可随时修改。\n"
                      "下一步请选择一张只有该人物的 JPG / PNG 照片。")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def on_group_changed(self):
        key = self.group_combo.currentData()
        if key in CATEGORY_BY_KEY:
            fill_captions(self.caption_combo, key)

    @property
    def person_name(self):
        return self.name_edit.text().strip()

    @property
    def caption(self):
        return self.caption_combo.currentData()


class ClockSettingsDialog(QDialog):
    """The labels on the video are clickable, no separate main-window controls."""
    def __init__(self, title: str, config: dict, remote=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(450, 235)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.show = QCheckBox("显示时间（取消勾选则隐藏）")
        self.show.setChecked(config.get("show", True))
        form.addRow("显示", self.show)
        self.timezone = QComboBox()
        self.timezone.setEditable(False)
        self.timezone.addItem("SYSTEM（Windows 当前时区）", "SYSTEM")
        if remote:
            self.timezone.addItem("UNSET（未知 / NO SIGNAL）", "UNSET")
        for name in sorted(available_timezones()):
            self.timezone.addItem(name, name)
        target_zone = config.get("timezone", "UNSET" if remote else "SYSTEM")
        index = self.timezone.findData(target_zone)
        if index >= 0:
            self.timezone.setCurrentIndex(index)
        else:
            self.timezone.setCurrentIndex(1 if remote else 0)
        form.addRow("所选时区", self.timezone)

        self.manual = QCheckBox("使用手动校正时间（持续按秒计时）")
        self.manual.setChecked(config.get("manual", False))
        form.addRow("手动校正", self.manual)
        self.datetime = QDateTimeEdit()
        self.datetime.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.datetime.setCalendarPopup(True)
        value = QDateTime.fromString(config.get("clock_base", ""), "yyyy-MM-ddTHH:mm:ss")
        self.datetime.setDateTime(value if value.isValid() else QDateTime.currentDateTime())
        form.addRow("当前显示时间", self.datetime)
        self.datetime.setEnabled(self.manual.isChecked())
        self.manual.toggled.connect(self.datetime.setEnabled)
        layout.addLayout(form)
        note = QLabel("普通网络摄像头不一定提供设备时钟。未设置远程时区且未手动校正时显示 NO SIGNAL。")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_config(self):
        zone = self.timezone.currentData()
        if zone is None:
            zone = self.timezone.currentText().strip()
        return {
            "show": self.show.isChecked(),
            "timezone": zone,
            "manual": self.manual.isChecked(),
            "clock_base": self.datetime.dateTime().toString("yyyy-MM-ddTHH:mm:ss"),
            "set_epoch": time.time(),
        }


class CoordinatesDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("摄像头经纬度 · 用户设置")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.show = QCheckBox("显示经纬度（取消勾选则隐藏）")
        self.show.setChecked(config.get("show", True))
        form.addRow("显示", self.show)
        self.available = QCheckBox("手动提供此摄像头的位置")
        self.available.setChecked(config.get("has_coordinates", False))
        form.addRow("位置来源", self.available)
        self.lat = QDoubleSpinBox()
        self.lat.setRange(-90.0, 90.0)
        self.lat.setDecimals(6)
        self.lat.setValue(float(config.get("lat", 0)))
        form.addRow("纬度（北正南负）", self.lat)
        self.lon = QDoubleSpinBox()
        self.lon.setRange(-180.0, 180.0)
        self.lon.setDecimals(6)
        self.lon.setValue(float(config.get("lon", 0)))
        form.addRow("经度（东正西负）", self.lon)
        self.lat.setEnabled(self.available.isChecked())
        self.lon.setEnabled(self.available.isChecked())
        self.available.toggled.connect(self.lat.setEnabled)
        self.available.toggled.connect(self.lon.setEnabled)
        layout.addLayout(form)
        note = QLabel("不会通过摄像头画面推断位置。未填写时显示 NO SIGNAL；显示保留两位小数。")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_config(self):
        return {"show": self.show.isChecked(), "has_coordinates": self.available.isChecked(),
                "lat": self.lat.value(), "lon": self.lon.value()}


class AppearanceSettingsDialog(QDialog):
    """Only user-owned local video assets are selected. Nothing is downloaded."""
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("The Machine · 界面设置")
        self.resize(560, 250)
        root = QVBoxLayout(self)
        form = QFormLayout()
        self.default_camera = QSpinBox()
        self.default_camera.setRange(0, 20)
        self.default_camera.setValue(int(settings.get("default_camera", 0)))
        form.addRow("默认摄像头编号", self.default_camera)
        self.enable_intro = QCheckBox("开启待启动循环动画")
        self.enable_intro.setChecked(bool(settings.get("intro_enabled", True)))
        form.addRow("待启动动画", self.enable_intro)
        self.video_path = QLineEdit(str(settings.get("intro_video_path", "")))
        self.video_path.setPlaceholderText("不指定时使用内置原创监控风格动态画面")
        source_row = QHBoxLayout()
        source_row.addWidget(self.video_path, 1)
        choose_btn = QPushButton("选择本地视频…")
        choose_btn.clicked.connect(self.browse_video)
        source_row.addWidget(choose_btn)
        clear_btn = QPushButton("清除")
        clear_btn.clicked.connect(self.video_path.clear)
        source_row.addWidget(clear_btn)
        form.addRow("启动视频", source_row)
        root.addLayout(form)
        # HUD category guide is available on demand instead of permanently
        # occupying screen space.
        self.legend_button = QPushButton("边框说明")
        self.legend_button.clicked.connect(self.show_border_legend)
        root.addWidget(self.legend_button)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def show_border_legend(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("The Machine · 边框说明")
        dialog.resize(600, 290)
        layout = QVBoxLayout(dialog)
        label = QLabel(LEGEND_HTML)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setWordWrap(True)
        label.setStyleSheet("font-size:14px; line-height:150%; padding:12px;")
        layout.addWidget(label)
        close_btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn.rejected.connect(dialog.reject)
        layout.addWidget(close_btn)
        dialog.exec()

    def browse_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择有权使用的本地启动视频", "",
                                              "Video Files (*.mp4 *.avi *.mov *.mkv);;All files (*)")
        if path:
            self.video_path.setText(path)

    def result_settings(self):
        return {"default_camera": self.default_camera.value(),
                "intro_enabled": self.enable_intro.isChecked(),
                "intro_video_path": self.video_path.text().strip()}


def settings_icon():
    """White gear/person icon matching the user-provided reference.

    Use a cleaned transparent icon asset (no checkerboard) in assets/ui. If
    it is missing, fall back to a simple built-in system icon.
    """
    icon_path = ROOT / "assets" / "ui" / "settings_person_gear_white.png"
    if icon_path.is_file():
        return QIcon(str(icon_path))
    return QIcon.fromTheme("preferences-system")


class MoreCamerasDialog(QDialog):
    """Authorized network streams plus Windows-exposed camera indices.

    Bluetooth video is device/protocol dependent: this UI does not pretend that
    pairing with a BLE accessory automatically gives a video stream.
    """
    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.setWindowTitle("连接更多摄像头")
        self.resize(600, 460)
        root = QVBoxLayout(self)
        tabs = QTabWidget()
        root.addWidget(tabs)

        network = QWidget()
        net_layout = QVBoxLayout(network)
        info = QLabel("添加你有权使用的公开/授权视频源。支持 RTSP、RTSPS、HTTP(S) 的直接视频流；"
                      "普通网页地址不保证可用。仅在点击“连接”后联网。")
        info.setWordWrap(True)
        net_layout.addWidget(info)
        self.consent = QCheckBox("我确认拥有该视频源的查看权限，并同意现在联网连接")
        net_layout.addWidget(self.consent)
        form = QFormLayout()
        self.source_name = QLineEdit()
        self.source_name.setPlaceholderText("例如：授权公共网络摄像头")
        form.addRow("名称", self.source_name)
        self.source_url = QLineEdit()
        self.source_url.setPlaceholderText("rtsp://camera.example/live  或  https://example/live.m3u8")
        form.addRow("视频流地址", self.source_url)
        net_layout.addLayout(form)
        self.add_source = QPushButton("＋ 保存到摄像头列表（不会立即连接）")
        self.add_source.clicked.connect(self.save_new_source)
        net_layout.addWidget(self.add_source)
        self.sources = QListWidget()
        net_layout.addWidget(self.sources, 1)
        row = QHBoxLayout()
        connect_btn = QPushButton("▶ 连接选中视频源")
        connect_btn.clicked.connect(self.connect_selected)
        remove_btn = QPushButton("删除选中源")
        remove_btn.clicked.connect(self.remove_selected)
        row.addWidget(connect_btn)
        row.addWidget(remove_btn)
        net_layout.addLayout(row)
        tabs.addTab(network, "公开/授权网络摄像头")

        bluetooth = QWidget()
        bt_layout = QVBoxLayout(bluetooth)
        bt_info = QLabel(
            "蓝牙设备的配对通常仅提供控制通道，不保证提供视频。\n\n"
            "请先在 Windows 11 设置中配对设备，并按照摄像头说明书开启 USB / Wi-Fi / UVC 视频模式。\n"
            "如果设备已作为 Windows 摄像头出现，可在下方输入其视频设备编号进行连接。\n"
            "此功能不会扫描或连接陌生的蓝牙设备，也不支持直接读取任意 BLE 设备的视频。"
        )
        bt_info.setWordWrap(True)
        bt_layout.addWidget(bt_info)
        bt_row = QHBoxLayout()
        bt_row.addWidget(QLabel("Windows 视频设备编号"))
        self.bt_index = QSpinBox()
        self.bt_index.setRange(0, 20)
        bt_row.addWidget(self.bt_index)
        bt_layout.addLayout(bt_row)
        switch_btn = QPushButton("▶ 连接此 Windows 摄像头")
        switch_btn.clicked.connect(self.connect_windows_device)
        bt_layout.addWidget(switch_btn)
        bt_layout.addStretch()
        tabs.addTab(bluetooth, "蓝牙设备 / Windows 摄像头")

        file_tab = QWidget()
        file_layout = QVBoxLayout(file_tab)
        file_info = QLabel("选择本地 MP4、AVI、MKV、MOV、M4V 或 WEBM 视频。\n"
                           "视频将在本机播放并执行人脸识别，不会上传至网络。")
        file_info.setWordWrap(True)
        file_layout.addWidget(file_info)
        open_file_btn = QPushButton("▶ 打开本地视频并开始识别")
        open_file_btn.clicked.connect(self.open_local_video)
        file_layout.addWidget(open_file_btn)
        file_layout.addStretch()
        tabs.addTab(file_tab, "本地视频文件")

        root.addWidget(QLabel("当前版本一次显示一路视频；选择另一来源会切换画面，不会自动联网。"))
        close_btn = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn.rejected.connect(self.reject)
        root.addWidget(close_btn)
        self.refresh_sources()

    def refresh_sources(self):
        self.sources.clear()
        for source in self.host.settings.get("network_sources", []):
            item = QListWidgetItem(source.get("name", "未命名视频源"))
            item.setData(Qt.ItemDataRole.UserRole, source["id"])
            item.setToolTip(source.get("url", ""))
            self.sources.addItem(item)

    def selected_source(self):
        item = self.sources.currentItem()
        if item is None:
            QMessageBox.information(self, "请选择", "请先选中一个已保存的网络视频源。")
            return None
        source_id = item.data(Qt.ItemDataRole.UserRole)
        for source in self.host.settings.get("network_sources", []):
            if source["id"] == source_id:
                return source
        return None

    def save_new_source(self):
        try:
            url = validate_stream_url(self.source_url.text())
        except ValueError as exc:
            QMessageBox.warning(self, "地址无效", str(exc))
            return
        name = self.source_name.text().strip() or "Network Camera"
        source = {"id": str(uuid4()), "name": name, "url": url}
        self.host.settings.setdefault("network_sources", []).append(source)
        self.host.persist_settings()
        self.refresh_sources()
        self.sources.setCurrentRow(self.sources.count()-1)
        self.source_url.clear()
        self.source_name.clear()

    def connect_selected(self):
        source = self.selected_source()
        if source is None:
            return
        if not self.consent.isChecked():
            QMessageBox.warning(self, "需要授权确认", "请先勾选已获得访问授权并同意联网连接。")
            return
        if self.host.activate_source("network", source["url"], source["id"], source["name"]):
            self.accept()

    def remove_selected(self):
        source = self.selected_source()
        if source is None:
            return
        self.host.settings["network_sources"] = [s for s in self.host.settings.get("network_sources", [])
                                                    if s["id"] != source["id"]]
        self.host.persist_settings()
        self.refresh_sources()

    def connect_windows_device(self):
        index = self.bt_index.value()
        if self.host.activate_source("local", index, f"local:{index}", f"摄像头 {index}"):
            self.host.camera_select.setValue(index)
            self.host.persist_settings()
            self.accept()

    def open_local_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择本地视频", "",
            "视频文件 (*.mp4 *.avi *.mkv *.mov *.m4v *.webm);;所有文件 (*)")
        if not path:
            return
        if self.host.activate_source("file", path, f"file:{path}", Path(path).name):
            self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("THE MACHINE | 本地人脸识别可视化 · 第一阶段")
        self.resize(1370, 840)
        self.setMinimumSize(1060, 710)
        self.chinese_font_family = preferred_chinese_font()
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#090d13; color:#e9edf4;
                                   font-family:"FZ_FONT_PLACEHOLDER", "Microsoft YaHei UI"; font-size:13px; }
            QLabel#Title { color:#f5f7fa; font-size:23px; font-weight:bold; letter-spacing:1px; }
            QLabel#SubTitle { color:#7e91a8; font-size:12px; }
            QFrame#MachineBanner { border:2px solid #d7dce2; border-radius:10px;
                                    background:#07090c; }
            QLabel#MachineName { font-family:"Bahnschrift", "Arial Narrow";
                                  font-size:22px; font-weight:bold; color:#a7abb1;
                                  border:none; background:transparent; }
            QLabel#MachineDot { background:#7f8389; border-radius:10px;
                                 min-width:20px; max-width:20px;
                                 min-height:20px; max-height:20px; }
            QLabel#BootState { font-family:"Bahnschrift", "Arial Narrow";
                                 font-size:20px; font-weight:bold; color:#e8eef3;
                                 background:transparent; border:none; }
            QProgressBar#BootProgress { background:#17212b; border:2px solid #b7c3ce;
                                         height:16px; text-align:center; }
            QProgressBar#BootProgress::chunk { background:#b3c2d0; }
            QPushButton#SettingsIcon { background:#16212d; border:1px solid #b9c4cf;
                                        border-radius:6px; padding:4px; }
            QLabel#StartPrompt { background:transparent; color:#f2f2f2;
                                 font-family:"FZ_FONT_PLACEHOLDER", "Microsoft YaHei UI";
                                 font-size:20px; font-weight:bold; letter-spacing:1px; }
            QLabel#Status { color:#e2df83; font-weight:bold; }
            QLabel#Camera { background:#020305; border:1px solid #263545; }
            QFrame#SidePanel { background:#0e1722; border:1px solid #203040; border-radius:6px; }
            QPushButton { background:#16283c; border:1px solid #35506b; color:#edf4ff;
                          border-radius:5px; padding:8px 10px; }
            QPushButton:hover { background:#1d3b58; }
            QPushButton:disabled { color:#657487; background:#121922; border-color:#1b2633; }
            QPushButton#Start { background:#184d39; border-color:#329a72; font-weight:bold; }
            QPushButton#Stop { background:#4d1c22; border-color:#a53b49; font-weight:bold; }
            QPushButton#VideoText { background:rgba(0,0,0,175); border:0;
                         border-radius:1px; color:#ffffff; text-align:right;
                         font-size:12px; padding:3px 6px; }
            QPushButton#VideoText:hover { background:rgba(28,49,67,220); }
            QTableWidget { background:#0a111a; alternate-background-color:#111d2b;
                           gridline-color:#223244; border:1px solid #243447; }
            QHeaderView::section { background:#1b2a3a; color:#e8eef5; padding:6px; border:none; }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateTimeEdit {
                background:#091521; color:#f0f5ff; border:1px solid #35506b;
                border-radius:4px; padding:4px; }
            QDialog, QTabWidget::pane { background:#0e1722; }
        """.replace("FZ_FONT_PLACEHOLDER", self.chinese_font_family))

        self.db = Database()
        self.settings = load_settings()
        if not isinstance(self.settings.get("camera_meta", {}), dict):
            self.settings["camera_meta"] = {}
        if not isinstance(self.settings.get("network_sources", []), list):
            self.settings["network_sources"] = []
        self.engine = None
        self.matcher = None
        self.tracker = FaceTracker()
        self.capture = None
        self.source_kind = "local"
        self.source_key = f"local:{self.settings.get('camera', 0)}"
        self.source_name = ""
        self.settings.setdefault("default_camera", 0)
        self.settings.setdefault("intro_enabled", True)
        self.settings.setdefault("intro_video_path", "")
        self.settings.setdefault("boot_seconds", 1.0)
        self.intro_capture = None
        self._intro_error_path = None
        self.boot_finished = False
        self.boot_started_at = time.perf_counter()
        self.frame_count = 0
        self.last_timestamp = None
        self.smoothed_fps = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.on_frame)

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setSpacing(11)
        outer.setContentsMargins(15, 14, 15, 14)
        # Single status strip replaces both lines of the previous header.
        header = QHBoxLayout()
        header.setSpacing(9)
        outer.addLayout(header)
        banner = QFrame()
        banner.setObjectName("MachineBanner")
        banner.setMinimumHeight(95)
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(22, 10, 18, 10)
        banner_layout.setSpacing(14)
        self.signal_dot = QLabel()
        self.signal_dot.setObjectName("MachineDot")
        self.signal_dot.setFixedSize(20, 20)
        banner_layout.addWidget(self.signal_dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.machine_name = QLabel("The Machine")
        self.machine_name.setObjectName("MachineName")
        banner_layout.addWidget(self.machine_name, 1)
        boot_section = QVBoxLayout()
        boot_section.setSpacing(2)
        self.boot_state = QLabel("PROCESSING...")
        self.boot_state.setObjectName("BootState")
        self.ready_fade = QGraphicsOpacityEffect(self.boot_state)
        self.boot_state.setGraphicsEffect(self.ready_fade)
        self.boot_state.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.boot_state.setMinimumWidth(235)
        self.boot_progress = QProgressBar()
        self.boot_progress.setObjectName("BootProgress")
        self.boot_progress.setMaximum(100)
        self.boot_progress.setTextVisible(False)
        self.boot_progress.setFixedWidth(235)
        for control in (self.boot_state, self.boot_progress):
            control.setToolTip("右键设置启动加载时间")
            control.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            control.customContextMenuRequested.connect(self.adjust_boot_duration)
        boot_section.addWidget(self.boot_state)
        boot_section.addWidget(self.boot_progress)
        banner_layout.addLayout(boot_section)
        header.addWidget(banner, 1)
        self.settings_button = QPushButton()
        self.settings_button.setObjectName("SettingsIcon")
        self.settings_button.setIcon(settings_icon())
        self.settings_button.setIconSize(QPixmap(36,36).size())
        self.settings_button.setToolTip("设置")
        self.settings_button.setAccessibleName("设置")
        self.settings_button.setFixedSize(48,48)
        self.settings_button.clicked.connect(self.open_appearance_settings)
        header.addWidget(self.settings_button, alignment=Qt.AlignmentFlag.AlignTop)

        row = QHBoxLayout()
        row.setSpacing(0)
        outer.addLayout(row, 1)
        left = QVBoxLayout()
        row.addLayout(left, 1)

        self.screen = QLabel()
        self.screen.setObjectName("Camera")
        self.screen.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.screen.setMinimumSize(620, 410)
        self.screen.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.screen.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.screen.customContextMenuRequested.connect(self.video_context_menu)
        left.addWidget(self.screen, 1)

        # Video text buttons are direct children of the video widget, not extra
        # toolbar buttons. Click the text itself to edit/hide the field.
        over = QVBoxLayout(self.screen)
        over.setContentsMargins(8, 8, 8, 36)
        top = QHBoxLayout()
        top.addStretch()
        clocks = QVBoxLayout()
        clocks.setSpacing(1)
        self.user_time_button = self.video_text_button(self.edit_user_time)
        self.camera_time_button = self.video_text_button(self.edit_camera_time)
        clocks.addWidget(self.user_time_button, alignment=Qt.AlignmentFlag.AlignRight)
        clocks.addWidget(self.camera_time_button, alignment=Qt.AlignmentFlag.AlignRight)
        top.addLayout(clocks)
        over.addLayout(top)
        over.addStretch()
        self.start_prompt = QLabel("按ENTER键启动")
        self.start_prompt.setObjectName("StartPrompt")
        self.start_prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.start_prompt.hide()
        self.prompt_fade = QGraphicsOpacityEffect(self.start_prompt)
        self.start_prompt.setGraphicsEffect(self.prompt_fade)
        over.addWidget(self.start_prompt, alignment=Qt.AlignmentFlag.AlignCenter)
        bottom = QHBoxLayout()
        bottom.addStretch()
        self.coordinates_button = self.video_text_button(self.edit_coordinates)
        bottom.addWidget(self.coordinates_button)
        over.addLayout(bottom)

        self.status = QLabel("状态：未开启；摄像头未被访问。")
        self.status.setObjectName("Status")
        left.addWidget(self.status)

        side = QFrame()
        side.setObjectName("SidePanel")
        self.side_panel = side
        self.sidebar_width = 369
        side.setMinimumWidth(0)
        side.setMaximumWidth(0)
        # A fixed horizontal size policy is important: when the main video
        # layout has stretch=1, an Ignored/zero-stretch panel may be allocated
        # 0 pixels even when maximumWidth is animated to a larger value.
        side.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        row.addWidget(side, 0)
        side_layout = QVBoxLayout(side)
        side_layout.setSpacing(7)
        side_layout.setContentsMargins(12, 12, 12, 12)
        side_layout.addWidget(self.heading("01  /  实时识别"))
        camrow = QHBoxLayout()
        camrow.addWidget(QLabel("摄像头编号"))
        self.camera_select = QSpinBox()
        self.camera_select.setRange(0, 20)
        self.camera_select.setValue(int(self.settings.get("default_camera", 0)))
        self.camera_select.valueChanged.connect(self.on_camera_number_changed)
        camrow.addWidget(self.camera_select)
        side_layout.addLayout(camrow)
        threshold_row = QHBoxLayout()
        threshold_row.addWidget(QLabel("相似度阈值"))
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(.30,.85)
        self.threshold.setDecimals(2)
        self.threshold.setSingleStep(.02)
        self.threshold.setValue(float(self.settings.get("threshold", .45)))
        self.threshold.setToolTip("越高越严格，默认为 0.45")
        self.threshold.valueChanged.connect(self.on_threshold_changed)
        threshold_row.addWidget(self.threshold)
        side_layout.addLayout(threshold_row)
        buttons = QHBoxLayout()
        self.start_button = QPushButton("▶ 开启可视化")
        self.start_button.setObjectName("Start")
        self.start_button.clicked.connect(self.start_camera)
        self.start_button.setEnabled(False)  # Wait until initialization progress reaches 100%.
        self.stop_button = QPushButton("■ 关闭可视化")
        self.stop_button.setObjectName("Stop")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_camera)
        buttons.addWidget(self.start_button)
        buttons.addWidget(self.stop_button)
        side_layout.addLayout(buttons)

        file_controls = QHBoxLayout()
        self.file_pause_button = QPushButton("⏸ 暂停视频")
        self.file_pause_button.clicked.connect(self.toggle_file_pause)
        self.file_pause_button.setVisible(False)
        self.file_seek = QSlider(Qt.Orientation.Horizontal)
        self.file_seek.setRange(0, 1000)
        self.file_seek.setVisible(False)
        self.file_seek.sliderReleased.connect(self.seek_file_video)
        file_controls.addWidget(self.file_pause_button)
        file_controls.addWidget(self.file_seek, 1)
        side_layout.addLayout(file_controls)
        self.file_paused = False

        side_layout.addSpacing(5)
        side_layout.addWidget(self.heading("02  /  人物资料库"))
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["人物", "身份", "照片数"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        side_layout.addWidget(self.table, 1)
        self.add_button = QPushButton("＋ 录入新人物（选择照片）")
        self.add_button.clicked.connect(self.add_person)
        side_layout.addWidget(self.add_button)
        self.photo_button = QPushButton("＋ 给选中人物添加照片")
        self.photo_button.clicked.connect(self.add_photo)
        side_layout.addWidget(self.photo_button)

        group_row = QHBoxLayout()
        self.group_combo = QComboBox()
        fill_categories(self.group_combo)
        group_row.addWidget(self.group_combo)
        self.caption_combo = QComboBox()
        fill_captions(self.caption_combo, "IRRELEVANT")
        group_row.addWidget(self.caption_combo, 1)
        side_layout.addLayout(group_row)
        self.group_combo.currentIndexChanged.connect(self.on_group_changed)
        change_button = QPushButton("修改选中人物的分类 / 身份")
        change_button.clicked.connect(self.change_category)
        side_layout.addWidget(change_button)
        delete_button = QPushButton("删除选中人物")
        delete_button.clicked.connect(self.delete_person)
        side_layout.addWidget(delete_button)

        self.more_cameras_button = QPushButton("＋ 连接更多摄像头")
        self.more_cameras_button.setMinimumHeight(42)
        self.more_cameras_button.clicked.connect(self.open_more_cameras)
        side_layout.addWidget(self.more_cameras_button)
        self.table.itemSelectionChanged.connect(self.sync_category)
        self.refresh_people()

        # The control panel is initially collapsed. A slim hover target is
        # anchored to the right edge; Qt animates the panel's actual width,
        # so the video area reflows at the same time instead of being covered.
        self._sidebar_open = False
        self._sidebar_pinned = False
        self._sidebar_last_hover = time.monotonic()
        # Animate the *allocated* width, not just maximumWidth.  With the
        # stretchable video on the left, changing maximumWidth alone may
        # leave the sidebar at width 0 indefinitely (Windows/Qt layouts).
        self.sidebar_anim = QVariantAnimation(self)
        self.sidebar_anim.setDuration(270)
        self.sidebar_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.sidebar_anim.valueChanged.connect(self._apply_sidebar_width)
        self.edge_trigger = QFrame(central)
        self.edge_trigger.setObjectName("EdgeTrigger")
        self.edge_trigger.setStyleSheet(
            "QFrame#EdgeTrigger {background:rgba(120,150,180,35); "
            "border-left:1px solid #54677c;}")
        self.edge_trigger.setToolTip("鼠标移动到右侧可展开控制栏 · F2 锁定/取消锁定")
        self.edge_trigger.installEventFilter(self)
        central.installEventFilter(self)
        self._place_edge_trigger()
        self.edge_trigger.raise_()
        self.sidebar_poll = QTimer(self)
        self.sidebar_poll.setInterval(80)
        self.sidebar_poll.timeout.connect(self._check_sidebar_hover)
        self.sidebar_poll.start()

        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.refresh_overlays)
        self.clock_timer.start(1000)
        self.refresh_overlays()
        self.standby_timer = QTimer(self)
        self.standby_timer.setInterval(40)
        self.standby_timer.timeout.connect(self.on_standby_tick)
        self.begin_boot_sequence()
        self.standby_timer.start()
        QApplication.instance().installEventFilter(self)
        self.screen.setFocus()

    @staticmethod
    def heading(text):
        heading = QLabel(text)
        heading.setStyleSheet("color:#aaccf2; font-size:15px; font-weight:bold; margin:3px 0 4px;")
        return heading

    def _place_edge_trigger(self):
        if not hasattr(self, "edge_trigger"):
            return
        target = self.centralWidget()
        if target is None:
            return
        self.edge_trigger.setGeometry(max(0, target.width()-14), 0,
                                      14, target.height())

    def _apply_sidebar_width(self, value):
        """Reserve real layout space on every animation frame.

        Changing only maximumWidth does not force a zero-stretch Qt widget
        to expand. Keeping both size constraints equal makes the video and
        controls resize smoothly together, while the end state remains 0 px.
        """
        width = max(0, int(round(float(value))))
        self.side_panel.setMinimumWidth(width)
        self.side_panel.setMaximumWidth(width)

    def _set_sidebar_open(self, opened: bool):
        if opened == self._sidebar_open:
            return
        self._sidebar_open = opened
        self.sidebar_anim.stop()
        # Taking the current constrained width allows reversing the motion
        # without jumping if the pointer moves during an animation.
        current = self.side_panel.minimumWidth()
        self.sidebar_anim.setStartValue(current)
        self.sidebar_anim.setEndValue(self.sidebar_width if opened else 0)
        self.sidebar_anim.start()
        if opened:
            self._sidebar_last_hover = time.monotonic()
            self.edge_trigger.hide()
        else:
            self.edge_trigger.show()
            self.edge_trigger.raise_()

    def _check_sidebar_hover(self):
        if not self.isVisible() or QApplication.activeModalWidget() is not None:
            return
        if self._sidebar_pinned:
            return

        cursor = QCursor.pos()
        central = self.centralWidget()
        location = central.mapFromGlobal(cursor)
        pointer_in_window = central.rect().contains(location)
        now = time.monotonic()
        near_right_edge = (pointer_in_window and
                           location.x() >= central.width() - 24)

        if not self._sidebar_open:
            # Reliable fallback for a missed Enter event on the narrow hover
            # strip (e.g. mouse was already there when the widget appeared).
            if self.isActiveWindow() and near_right_edge:
                self._set_sidebar_open(True)
            return

        on_sidebar = self.side_panel.rect().contains(
            self.side_panel.mapFromGlobal(cursor))
        if on_sidebar or near_right_edge:
            self._sidebar_last_hover = now
        elif now - self._sidebar_last_hover > 0.55:
            self._set_sidebar_open(False)

    def eventFilter(self, watched, event):
        if hasattr(self, "edge_trigger") and watched is self.edge_trigger:
            if event.type() in (QEvent.Type.Enter, QEvent.Type.MouseButtonPress):
                self._set_sidebar_open(True)
        if watched is self.centralWidget() and event.type() == QEvent.Type.Resize:
            self._place_edge_trigger()
        if event.type() == QEvent.Type.KeyPress and self.isActiveWindow():
            if event.key() == Qt.Key.Key_F2 and not event.isAutoRepeat():
                self._sidebar_pinned = not self._sidebar_pinned
                self._set_sidebar_open(self._sidebar_pinned)
                return True
            # Enter only, and never while a text field or control is being
            # edited (prevent accidental camera activation on dialog accept).
            if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                    and self.capture is None and self.boot_finished
                    and not event.isAutoRepeat()):
                focus = QApplication.focusWidget()
                if not isinstance(focus, (QLineEdit, QSpinBox, QDoubleSpinBox,
                                          QDateTimeEdit, QComboBox, QPushButton,
                                          QTableWidget)):
                    self.start_default_camera()
                    return True
        return super().eventFilter(watched, event)

    def begin_boot_sequence(self):
        self.boot_started_at = time.perf_counter()
        self.boot_finished = False
        self.boot_progress.setValue(0)
        self.boot_progress.show()
        self.boot_state.setText("PROCESSING...")
        self.ready_fade.setOpacity(1.0)
        self.prompt_fade.setOpacity(0.0)
        self.signal_dot.setStyleSheet("background:#797e85; border-radius:10px;")
        self.machine_name.setStyleSheet("color:#979da5;")
        self.start_prompt.hide()
        self.start_button.setEnabled(False)
        self.update_standby_frame()

    def adjust_boot_duration(self, _position):
        value, ok = QInputDialog.getDouble(self, "启动进度条", "加载时间（秒）",
                                           float(self.settings.get("boot_seconds", 1.0)),
                                           .2, 30.0, 1)
        if ok:
            self.settings["boot_seconds"] = value
            self.persist_settings()
            if self.capture is None:
                self.begin_boot_sequence()

    def open_appearance_settings(self):
        dialog = AppearanceSettingsDialog(self.settings, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        old_video = self.settings.get("intro_video_path", "")
        self.settings.update(dialog.result_settings())
        if self.capture is None:
            self.camera_select.setValue(int(self.settings["default_camera"]))
        if old_video != self.settings.get("intro_video_path", ""):
            self.release_intro_video()
            self._intro_error_path = None
        self.persist_settings()
        if self.capture is None:
            self.update_standby_frame()
            self.refresh_overlays()
            self.screen.setFocus()

    def start_default_camera(self):
        self.camera_select.setValue(int(self.settings.get("default_camera", 0)))
        self.start_camera()

    def release_intro_video(self):
        if self.intro_capture is not None:
            self.intro_capture.release()
            self.intro_capture = None

    def update_standby_frame(self):
        if self.capture is not None:
            return
        if not self.settings.get("intro_enabled", True):
            self.release_intro_video()
            self.screen.clear()
            return
        frame = None
        path = str(self.settings.get("intro_video_path", "")).strip()
        if path and path != self._intro_error_path and Path(path).is_file():
            if self.intro_capture is None:
                # Only locally selected user-owned videos. No network activity.
                self.intro_capture = cv2.VideoCapture(path)
                if not self.intro_capture.isOpened():
                    self._intro_error_path = path
                    self.release_intro_video()
            if self.intro_capture is not None:
                ok, frame = self.intro_capture.read()
                if not ok:
                    self.intro_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ok, frame = self.intro_capture.read()
                if not ok:
                    frame = None
                    self._intro_error_path = path
                    self.release_intro_video()
        if frame is None:
            frame = render_standby(time.perf_counter()-self.boot_started_at)
        elif frame.shape[1] > 960:
            scale = 960.0 / frame.shape[1]
            frame = cv2.resize(frame, (960, max(1, round(frame.shape[0] * scale))))
        self.show_video_frame(frame)

    def show_video_frame(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = QImage(rgb.data, rgb.shape[1], rgb.shape[0], rgb.strides[0],
                       QImage.Format.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(image)
        self.screen.setPixmap(pixmap.scaled(self.screen.size(),
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def on_standby_tick(self):
        if self.capture is not None:
            return
        self.update_standby_frame()
        elapsed = time.perf_counter()-self.boot_started_at
        if not self.boot_finished:
            duration = max(.2, float(self.settings.get("boot_seconds", 1.0)))
            progress = min(100, int(100*elapsed/duration))
            self.boot_progress.setValue(progress)
            if progress >= 100:
                self.boot_finished = True
                self.boot_completed_at = time.perf_counter()
                self.boot_progress.hide()
                self.boot_state.setText("READY")
                self.start_prompt.show()
                self.start_button.setEnabled(True)
                self.machine_name.setStyleSheet("color:#e9edf4;")
                self.signal_dot.setStyleSheet("background:#cd2424; border-radius:10px;")
                self.screen.setFocus()
        if self.boot_finished:
            phase = time.perf_counter() - self.boot_completed_at
            fade = smooth_pulse_opacity(phase, period=2.1)
            self.ready_fade.setOpacity(fade)
            self.prompt_fade.setOpacity(fade)

    def video_context_menu(self, position):
        """Right-click the video to restore a field previously set to hidden."""
        menu = QMenu(self)
        menu.addAction("设置本地时间 / 显示", self.edit_user_time)
        menu.addAction("设置摄像头时间 / 显示", self.edit_camera_time)
        menu.addAction("设置经纬度 / 显示", self.edit_coordinates)
        menu.exec(self.screen.mapToGlobal(position))

    def video_text_button(self, callback):
        button = QPushButton("NO SIGNAL", self.screen)
        button.setObjectName("VideoText")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(callback)
        return button

    def alert(self, title, message):
        QMessageBox.warning(self, title, str(message))

    def ensure_engine(self):
        if self.engine is None:
            self.engine = FaceEngine()
            self.matcher = FaceMatcher(self.db, self.threshold.value())
        return self.engine

    def persist_settings(self):
        self.settings["camera"] = self.camera_select.value()
        self.settings["threshold"] = self.threshold.value()
        save_settings(self.settings)

    def on_camera_number_changed(self):
        if self.capture is None:
            self.source_key = f"local:{self.camera_select.value()}"
            self.refresh_overlays()
        self.persist_settings()

    def source_metadata(self):
        return self.settings.setdefault("camera_meta", {}).setdefault(self.source_key, {})

    def refresh_overlays(self):
        user_config = self.settings.get("user_clock", {"timezone": "SYSTEM"})
        user = clock_text(user_config)
        self.user_time_button.setVisible(user is not None)
        if user is not None:
            self.user_time_button.setText("LOCAL  " + user)
        meta = self.source_metadata()
        cam_config = meta.get("clock", {"timezone": "UNSET" if self.source_kind == "network" else "SYSTEM"})
        camera = clock_text(cam_config, source_is_remote=(self.source_kind == "network"))
        self.camera_time_button.setVisible(camera is not None)
        if camera is not None:
            self.camera_time_button.setText("CAMERA  " + camera)
        geo = coordinates_text(meta.get("coordinates", {}))
        self.coordinates_button.setVisible(geo is not None)
        if geo is not None:
            self.coordinates_button.setText("GPS  " + geo)
        # A disabled intro leaves only the blinking start prompt in the
        # black video area; restore metadata as soon as a camera starts.
        if self.capture is None and not self.settings.get("intro_enabled", True):
            self.user_time_button.hide()
            self.camera_time_button.hide()
            self.coordinates_button.hide()

    def edit_user_time(self):
        dialog = ClockSettingsDialog("本地时间 · 时区 / 隐藏", self.settings.get("user_clock", {}), parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.settings["user_clock"] = dialog.result_config()
            self.persist_settings()
            self.refresh_overlays()

    def edit_camera_time(self):
        meta = self.source_metadata()
        dialog = ClockSettingsDialog("摄像头当地时间 · 时区 / 校正 / 隐藏", meta.get("clock", {}),
                                     remote=self.source_kind == "network", parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            meta["clock"] = dialog.result_config()
            self.persist_settings()
            self.refresh_overlays()

    def edit_coordinates(self):
        meta = self.source_metadata()
        dialog = CoordinatesDialog(meta.get("coordinates", {}), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            meta["coordinates"] = dialog.result_config()
            self.persist_settings()
            self.refresh_overlays()

    def open_more_cameras(self):
        MoreCamerasDialog(self).exec()

    def on_group_changed(self):
        key = self.group_combo.currentData()
        if key in CATEGORY_BY_KEY:
            fill_captions(self.caption_combo, key)

    def refresh_people(self):
        selected_id = self.selected_person_id()
        people = self.db.get_people()
        self.table.setRowCount(len(people))
        for row, (pid, name, label, count) in enumerate(people):
            name_item = QTableWidgetItem(name)
            name_item.setData(Qt.ItemDataRole.UserRole, pid)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(label))
            self.table.setItem(row, 2, QTableWidgetItem(str(count)))
            if selected_id == pid:
                self.table.selectRow(row)

    def selected_person_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def get_photo_path(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择一张单人人脸照片", str(Path.home()), "图片 (*.jpg *.jpeg *.png *.bmp)"
        )
        return path

    def add_person(self):
        dialog = AddPersonDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name = dialog.person_name
        if not name:
            self.alert("无法录入", "请填写人物名称。")
            return
        photo = self.get_photo_path()
        if not photo:
            return
        try:
            vector = self.ensure_engine().encode_photo(photo)
            self.db.add_person(name, dialog.caption, vector)
            self.on_database_changed()
            self.status.setText(f"已录入人物：{name}。")
        except sqlite3.IntegrityError:
            self.alert("人物已存在", "人物名称已存在。请使用“给选中人物添加照片”。")
        except Exception as exc:
            self.alert("录入失败", exc)

    def add_photo(self):
        person_id = self.selected_person_id()
        if person_id is None:
            self.alert("请先选择", "请先在人物列表里选中一个人物。")
            return
        photo = self.get_photo_path()
        if not photo:
            return
        try:
            vector = self.ensure_engine().encode_photo(photo)
            self.db.add_sample(person_id, vector)
            self.on_database_changed()
            self.status.setText("已添加人脸特征样本。")
        except Exception as exc:
            self.alert("添加照片失败", exc)

    def change_category(self):
        person_id = self.selected_person_id()
        if person_id is None:
            self.alert("请先选择", "请先选中需要修改分类的人物。")
            return
        self.db.update_label(person_id, self.caption_combo.currentData())
        self.on_database_changed()
        self.status.setText("人物分类 / 身份已更新。")

    def sync_category(self):
        row = self.table.currentRow()
        if row >= 0 and self.table.item(row, 1):
            label = self.table.item(row, 1).text()
            category = CAPTION_TO_CATEGORY.get(label)
            if category:
                i = self.group_combo.findData(category.key)
                if i >= 0:
                    self.group_combo.setCurrentIndex(i)
                j = self.caption_combo.findData(label)
                if j >= 0:
                    self.caption_combo.setCurrentIndex(j)

    def delete_person(self):
        person_id = self.selected_person_id()
        if person_id is None:
            self.alert("请先选择", "请先选中需要删除的人物。")
            return
        answer = QMessageBox.question(self, "确认删除", "确定删除这个人物及其全部人脸特征吗？")
        if answer == QMessageBox.StandardButton.Yes:
            self.db.remove(person_id)
            self.on_database_changed()
            self.status.setText("已删除选中人物及其人脸特征。")

    def on_database_changed(self):
        if self.matcher:
            self.matcher.reload()
        self.tracker.reset()
        self.refresh_people()

    def on_threshold_changed(self):
        if self.matcher:
            self.matcher.threshold = self.threshold.value()
        self.tracker.reset()
        self.persist_settings()

    def start_camera(self):
        self.activate_source("local", self.camera_select.value(),
                             f"local:{self.camera_select.value()}",
                             f"摄像头 {self.camera_select.value()}")

    def activate_source(self, kind, target, key, name):
        """Switch active view to ONE source; never auto-connect to a network URL."""
        if not self.boot_finished:
            return False
        try:
            self.ensure_engine()
        except Exception as exc:
            self.alert("模型尚未准备好", f"{exc}\n请先运行 01_install_environment.bat 和 02_download_models.bat。")
            return False
        try:
            new_capture = open_video_source(VideoSourceSpec(kind, target, str(key), str(name)))
        except (SourceOpenError, ValueError, TypeError, cv2.error) as exc:
            self.alert("无法打开视频源", f"请检查摄像头、文件或授权视频地址。\n详细信息：{exc}")
            return False
        if kind == "local":
            new_capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            new_capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        new_capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.timer.stop()
        self.release_intro_video()
        self.start_prompt.hide()
        self.ready_fade.setOpacity(1.0)
        self.boot_state.setText("ACTIVE")
        if self.capture is not None:
            self.capture.release()
        self.capture = new_capture
        self.file_paused = False
        self.file_pause_button.setVisible(kind == "file")
        self.file_seek.setVisible(kind == "file")
        self.file_pause_button.setText("⏸ 暂停视频")
        self.file_seek.setValue(0)
        self.source_kind = kind
        self.source_key = str(key)
        self.source_name = name
        self.frame_count = 0
        self.smoothed_fps = 0.0
        self.last_timestamp = None
        self.tracker.reset()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.camera_select.setEnabled(False)
        self.persist_settings()
        self.status.setText("状态：识别运行中 · " + name)
        self.refresh_overlays()
        # File playback uses the encoded frame rate rather than forcing 33 FPS.
        fps = new_capture.get(cv2.CAP_PROP_FPS) if kind == "file" else 0
        interval = max(20, min(100, round(1000 / fps))) if 1 <= fps <= 100 else 30
        self.timer.start(interval)
        return True

    def toggle_file_pause(self):
        if self.source_kind != "file" or self.capture is None:
            return
        self.file_paused = not self.file_paused
        self.file_pause_button.setText("▶ 继续视频" if self.file_paused else "⏸ 暂停视频")
        if self.file_paused:
            self.timer.stop()
        else:
            fps = self.capture.get(cv2.CAP_PROP_FPS)
            interval = max(20, min(100, round(1000 / fps))) if 1 <= fps <= 100 else 30
            self.timer.start(interval)

    def seek_file_video(self):
        if self.source_kind != "file" or self.capture is None:
            return
        length = self.capture.get(cv2.CAP_PROP_FRAME_COUNT)
        if length > 0:
            self.capture.set(cv2.CAP_PROP_POS_FRAMES, round(length * self.file_seek.value() / 1000))
            self.tracker.reset()

    def stop_camera(self):
        self.timer.stop()
        if self.capture is not None:
            self.capture.release()
            self.capture = None
        self.tracker.reset()
        self.file_paused = False
        self.file_pause_button.setVisible(False)
        self.file_seek.setVisible(False)
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.camera_select.setEnabled(True)
        self.source_kind = "local"
        self.source_key = f"local:{self.camera_select.value()}"
        self.source_name = ""
        self.screen.clear()
        self.boot_state.setText("READY")
        self.start_prompt.show()
        self.boot_completed_at = time.perf_counter()
        self.status.setText("状态：已关闭。摄像头已释放。")
        self.update_standby_frame()
        self.refresh_overlays()

    def on_frame(self):
        if self.capture is None:
            return
        try:
            ok, frame = self.capture.read()
            if not ok or frame is None:
                if self.source_kind == "file":
                    # Normal end-of-file is not a camera/network failure.
                    self.stop_camera()
                    self.status.setText("状态：本地视频播放结束；已释放文件。")
                    return
                extra_error = getattr(self.capture, "last_error", "")
                self.stop_camera()
                self.alert("视频读取失败", "视频源无法继续提供画面，请检查连接或网络状态。"
                           + ("\n详细信息：" + extra_error if extra_error else ""))
                return
            if self.source_kind == "file":
                length = self.capture.get(cv2.CAP_PROP_FRAME_COUNT)
                position = self.capture.get(cv2.CAP_PROP_POS_FRAMES)
                if length > 0 and not self.file_seek.isSliderDown():
                    self.file_seek.blockSignals(True)
                    self.file_seek.setValue(min(1000, round(1000 * position / length)))
                    self.file_seek.blockSignals(False)
            if self.source_kind == "local":
                frame = cv2.flip(frame, 1)
            h, w = frame.shape[:2]
            if w > 800:
                ratio = 800/w
                frame = cv2.resize(frame, (800, round(h*ratio)))
            faces = self.engine.detect(frame)
            tracks = self.tracker.update(faces)
            self.frame_count += 1
            for track in tracks:
                if self.frame_count - track.last_recognition < 9:
                    continue
                face = faces[track._face_idx]
                try:
                    embedding = self.engine.encode(frame, face)
                    matched, score = self.matcher.match(embedding)
                    track.last_score = score
                    if matched is None:
                        track.label, track.name, track.person_id = "IRRELEVANT", "", None
                    else:
                        track.person_id, track.name, track.label = matched
                except cv2.error:
                    track.label, track.name, track.person_id = "IRRELEVANT", "", None
                track.last_recognition = self.frame_count
            annotated = render(frame, tracks, self.smoothed_fps,
                               source_mode=("NETWORK" if self.source_kind == "network" else
                                             "FILE" if self.source_kind == "file" else "LOCAL"))
            self.show_video_frame(annotated)
            now = time.perf_counter()
            if self.last_timestamp is not None:
                delta = max(1e-6, now-self.last_timestamp)
                instant_fps = 1/delta
                self.smoothed_fps = instant_fps if self.smoothed_fps == 0 else .85*self.smoothed_fps + .15*instant_fps
            self.last_timestamp = now
        except Exception as exc:
            self.stop_camera()
            self.alert("运行错误", f"{type(exc).__name__}: {exc}\n完整错误可在命令行查看。")
            traceback.print_exc()

    def closeEvent(self, event):
        self.sidebar_poll.stop()
        self.sidebar_anim.stop()
        self.standby_timer.stop()
        self.stop_camera()
        self.release_intro_video()
        QApplication.instance().removeEventFilter(self)
        self.persist_settings()
        self.db.close()
        super().closeEvent(event)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("The Machine · Local Face Visualizer")
    window = MainWindow()
    window.show()
    QTimer.singleShot(0, window.screen.setFocus)
    if missing_models():
        QMessageBox.information(window, "还需要下载模型",
            "程序界面可以打开，但当前尚缺人脸识别模型。\n\n"
            "请先关闭程序，双击 02_download_models.bat，完成后重新启动。")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
