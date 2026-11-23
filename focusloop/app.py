"""FocusLoop: number-only, click-through Windows tray overlay."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QSettings, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QSpinBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .timer import FocusTimer, Phase

POSITIONS = (
    ("右上", "top_right"),
    ("左上", "top_left"),
    ("右下", "bottom_right"),
    ("左下", "bottom_left"),
)


def _int_setting(settings: QSettings, key: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(settings.value(key, default))
    except (ValueError, TypeError):
        value = default
    return min(max(value, minimum), maximum)


class Overlay(QWidget):
    def __init__(self, font_size: int, position: str) -> None:
        super().__init__()
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.clock_text = "45:00"
        self.phase = Phase.WORK
        self.font_size = font_size
        self.position_name = position
        self._resize_and_reposition()

    def _resize_and_reposition(self) -> None:
        font = QFont("Consolas", self.font_size)
        font.setBold(True)
        metrics = QFontMetrics(font)
        self.setFixedSize(metrics.horizontalAdvance("000:00") + 26, metrics.height() + 24)
        self.reposition()
        self.update()

    def reposition(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        rect = screen.availableGeometry()
        margin = 24
        is_right = self.position_name.endswith("right")
        is_bottom = self.position_name.startswith("bottom")
        x = rect.right() - self.width() - margin if is_right else rect.left() + margin
        y = rect.bottom() - self.height() - margin if is_bottom else rect.top() + margin
        self.move(QPoint(x, y))

    def set_clock(self, text: str, phase: Phase) -> None:
        if (text, phase) != (self.clock_text, self.phase):
            self.clock_text = text
            self.phase = phase
            self.update()

    def apply_appearance(self, font_size: int, position: str) -> None:
        self.font_size = font_size
        self.position_name = position
        self._resize_and_reposition()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = QFont("Consolas", self.font_size)
        font.setBold(True)
        painter.setFont(font)
        alignment = Qt.AlignmentFlag.AlignCenter
        painter.setPen(QColor(0, 0, 0, 175))
        painter.drawText(self.rect().translated(2, 2), alignment, self.clock_text)
        painter.setPen(QColor("#F5F7FC") if self.phase is Phase.WORK else QColor("#55E6B6"))
        painter.drawText(self.rect(), alignment, self.clock_text)


class SettingsDialog(QDialog):
    def __init__(self, parent, timer: FocusTimer, font_size: int, position: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("FocusLoop - 設定")
        self.setMinimumWidth(300)

        self.work_spin = QSpinBox(self)
        self.work_spin.setRange(FocusTimer.MIN_MINUTES, FocusTimer.MAX_MINUTES)
        self.work_spin.setSuffix(" 分")
        self.work_spin.setValue(timer.work_minutes)

        self.break_spin = QSpinBox(self)
        self.break_spin.setRange(FocusTimer.MIN_MINUTES, FocusTimer.MAX_MINUTES)
        self.break_spin.setSuffix(" 分")
        self.break_spin.setValue(timer.break_minutes)

        self.font_spin = QSpinBox(self)
        self.font_spin.setRange(18, 96)
        self.font_spin.setSuffix(" pt")
        self.font_spin.setValue(font_size)

        self.position_combo = QComboBox(self)
        for label, value in POSITIONS:
            self.position_combo.addItem(label, value)
        ix = self.position_combo.findData(position)
        self.position_combo.setCurrentIndex(max(ix, 0))

        form = QFormLayout()
        form.addRow("作業時間", self.work_spin)
        form.addRow("休憩時間", self.break_spin)
        form.addRow("文字サイズ", self.font_spin)
        form.addRow("表示位置", self.position_combo)

        note = QLabel("時間を変更すると、現在の作業／休憩を最初から数え直すよ。")
        note.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)


class FocusLoopApp:
    def __init__(self, qt_app: QApplication) -> None:
        self.qt_app = qt_app
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.settings = QSettings("FocusLoop", "FocusLoop")
        work = _int_setting(self.settings, "work_minutes", 45, 1, 240)
        rest = _int_setting(self.settings, "break_minutes", 15, 1, 240)
        self.font_size = _int_setting(self.settings, "font_size", 42, 18, 96)
        self.position = str(self.settings.value("position", "top_right"))
        if self.position not in {value for _, value in POSITIONS}:
            self.position = "top_right"

        self.timer_model = FocusTimer(work, rest)
        self.overlay = Overlay(self.font_size, self.position)
        self.tray = QSystemTrayIcon(self._tray_icon(), qt_app)
        self.tray.setToolTip("FocusLoop")
        self.menu = QMenu()
        self.status_action = self.menu.addAction("作業中 45:00")
        self.status_action.setEnabled(False)
        self.menu.addSeparator()

        self.pause_action = self.menu.addAction("一時停止")
        self.pause_action.triggered.connect(self.toggle_pause)
        self.skip_action = self.menu.addAction("次のフェーズへ")
        self.skip_action.triggered.connect(self.skip)
        self.reset_action = self.menu.addAction("現在のフェーズをリセット")
        self.reset_action.triggered.connect(self.reset)
        self.menu.addSeparator()

        settings_action = self.menu.addAction("時間・表示の設定…")
        settings_action.triggered.connect(self.show_settings)
        self.menu.addSeparator()
        quit_action = self.menu.addAction("終了")
        quit_action.triggered.connect(self.close)

        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._tray_activated)
        self.last_display = None

        self.qt_timer = QTimer(qt_app)
        self.qt_timer.setInterval(200)
        self.qt_timer.timeout.connect(self.update)

    @staticmethod
    def _tray_icon() -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#253B62"))
        painter.drawRoundedRect(3, 3, 58, 58, 14, 14)
        painter.setPen(QColor("#FFFFFF"))
        font = QFont("Segoe UI", 23)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "F")
        painter.end()
        return QIcon(pixmap)

    def start(self) -> bool:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(
                None,
                "FocusLoop",
                "システムトレイが利用できないため起動できないよ。",
            )
            return False
        self.tray.show()
        self.overlay.show()
        self.overlay.reposition()
        self.update()
        self.qt_timer.start()
        return True

    def update(self) -> None:
        switched = self.timer_model.tick()
        remaining = self.timer_model.remaining_seconds()
        display = f"{remaining // 60:02d}:{remaining % 60:02d}"
        state = (display, self.timer_model.phase, self.timer_model.paused)
        if state != self.last_display:
            self.overlay.set_clock(display, self.timer_model.phase)
            title = "作業中" if self.timer_model.phase is Phase.WORK else "休憩中"
            if self.timer_model.paused:
                title += " (一時停止)"
            self.status_action.setText(f"{title}  {display}")
            self.pause_action.setText("再開" if self.timer_model.paused else "一時停止")
            self.tray.setToolTip(f"FocusLoop - {title} {display}")
            self.last_display = state
        if switched:
            text = "作業時間だよ" if self.timer_model.phase is Phase.WORK else "休憩時間だよ"
            self.tray.showMessage("FocusLoop", text, QSystemTrayIcon.MessageIcon.Information, 4000)

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.toggle_pause()

    def toggle_pause(self) -> None:
        self.timer_model.toggle_pause()
        self.update()

    def skip(self) -> None:
        self.timer_model.skip()
        self.update()

    def reset(self) -> None:
        self.timer_model.restart()
        self.update()

    def show_settings(self) -> None:
        dialog = SettingsDialog(None, self.timer_model, self.font_size, self.position)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_work = dialog.work_spin.value()
        new_rest = dialog.break_spin.value()
        if (new_work, new_rest) != (self.timer_model.work_minutes, self.timer_model.break_minutes):
            self.timer_model.configure(new_work, new_rest)
        self.font_size = dialog.font_spin.value()
        self.position = str(dialog.position_combo.currentData())
        self.overlay.apply_appearance(self.font_size, self.position)
        self.settings.setValue("work_minutes", new_work)
        self.settings.setValue("break_minutes", new_rest)
        self.settings.setValue("font_size", self.font_size)
        self.settings.setValue("position", self.position)
        self.settings.sync()
        self.update()

    def close(self) -> None:
        self.qt_timer.stop()
        self.overlay.close()
        self.tray.hide()
        self.qt_app.quit()
