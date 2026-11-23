"""FocusLoop: a number-only transparent overlay with editable phases."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QSystemTrayIcon,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from .geometry import tray_menu_position
from .timer import (
    COLOR_HEX,
    COLOR_PRESETS,
    FocusTimer,
    PhaseConfig,
    phases_from_json,
    phases_to_json,
)

POSITIONS = (
    ("左下", "bottom_left"),
    ("右下", "bottom_right"),
    ("左上", "top_left"),
    ("右上", "top_right"),
)


def _int_setting(settings: QSettings, key: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(settings.value(key, default))
    except (ValueError, TypeError):
        value = default
    return min(max(value, minimum), maximum)


class Overlay(QWidget):
    """Only the countdown digits are painted; mouse input passes through."""

    def __init__(self, font_size: int, position: str, phase: PhaseConfig) -> None:
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
        self.clock_text = f"{phase.minutes:02d}:00"
        self.phase_config = phase
        self.font_size = font_size
        self.position_name = position
        self._resize_and_reposition()

    def _resize_and_reposition(self) -> None:
        font = QFont("Consolas", self.font_size)
        font.setBold(True)
        metrics = QFontMetrics(font)
        self.setFixedSize(metrics.horizontalAdvance("000:00") + 30, metrics.height() + 26)
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

    def set_clock(self, text: str, phase: PhaseConfig) -> None:
        if (text, phase) != (self.clock_text, self.phase_config):
            self.clock_text = text
            self.phase_config = phase
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
        alpha = round(self.phase_config.opacity * 255 / 100)
        shadow = QColor(0, 0, 0, round(alpha * 0.65))
        painter.setPen(shadow)
        painter.drawText(self.rect().translated(2, 2), Qt.AlignmentFlag.AlignCenter, self.clock_text)
        foreground = QColor(COLOR_HEX[self.phase_config.color])
        foreground.setAlpha(alpha)
        painter.setPen(foreground)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.clock_text)


class SettingsDialog(QDialog):
    """Edit all phases, including order, text color and per-phase opacity."""

    applied = Signal(object)

    def __init__(self, parent, timer: FocusTimer, font_size: int, position: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("FocusLoop - 設定")
        self.setMinimumWidth(760)
        self.setMinimumHeight(450)
        self.result_phases: tuple[PhaseConfig, ...] | None = None

        self.font_spin = QSpinBox(self)
        self.font_spin.setRange(18, 96)
        self.font_spin.setSuffix(" pt")
        self.font_spin.setValue(font_size)

        self.position_combo = QComboBox(self)
        for label, value in POSITIONS:
            self.position_combo.addItem(label, value)
        self.position_combo.setCurrentIndex(max(0, self.position_combo.findData(position)))

        form = QFormLayout()
        form.addRow("文字サイズ", self.font_spin)
        form.addRow("表示位置", self.position_combo)

        self.table = QTableWidget(0, 5, self)
        self.table.setHorizontalHeaderLabels(("フェーズ名", "時間", "文字色", "透過率", "並べ替え・削除"))
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._render_rows([
            {
                "name": phase.name,
                "minutes": phase.minutes,
                "color": phase.color,
                "opacity": phase.opacity,
            }
            for phase in timer.phases
        ])

        add_button = QPushButton("＋ フェーズを追加", self)
        add_button.clicked.connect(self._add_phase)

        note = QLabel(
            "上から順に自動で繰り返します。"
            "フェーズの順番・名前・分数を変更すると、先頭から再スタートします。"
            "色・透過率・位置・文字サイズのみの変更では時間をリセットしません。"
            "「適用」を押すと画面を閉じずに変更を反映します。",
            self,
        )
        note.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self.apply_changes
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.table)
        layout.addWidget(add_button)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def _render_rows(self, rows: list[dict]) -> None:
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(0)
        for row in rows:
            self._add_row(row)
        self.table.setUpdatesEnabled(True)

    def _add_row(self, phase: dict) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 44)

        name = QLineEdit(str(phase["name"]), self.table)
        name.setMaxLength(40)
        name.setPlaceholderText("フェーズ名")
        self.table.setCellWidget(row, 0, name)

        minutes = QSpinBox(self.table)
        minutes.setRange(1, 240)
        minutes.setSuffix(" 分")
        minutes.setValue(int(phase["minutes"]))
        self.table.setCellWidget(row, 1, minutes)

        color = QComboBox(self.table)
        for key, label, hex_value in COLOR_PRESETS:
            color.addItem(label, key)
            color.setItemData(color.count() - 1, QColor(hex_value), Qt.ItemDataRole.DecorationRole)
        color.setCurrentIndex(max(0, color.findData(phase["color"])))
        self.table.setCellWidget(row, 2, color)

        opacity_cell = QWidget(self.table)
        opacity_layout = QHBoxLayout(opacity_cell)
        opacity_layout.setContentsMargins(4, 0, 4, 0)
        opacity = QSlider(Qt.Orientation.Horizontal, opacity_cell)
        opacity.setRange(0, 100)
        opacity.setSingleStep(1)
        opacity.setValue(int(phase["opacity"]))
        opacity_label = QLabel(f"{opacity.value()}%", opacity_cell)
        opacity_label.setMinimumWidth(38)
        opacity.valueChanged.connect(lambda value, label=opacity_label: label.setText(f"{value}%"))
        opacity_layout.addWidget(opacity)
        opacity_layout.addWidget(opacity_label)
        self.table.setCellWidget(row, 3, opacity_cell)

        buttons_cell = QWidget(self.table)
        buttons_layout = QHBoxLayout(buttons_cell)
        buttons_layout.setContentsMargins(2, 0, 2, 0)
        up = QPushButton("↑", buttons_cell)
        down = QPushButton("↓", buttons_cell)
        delete = QPushButton("×", buttons_cell)
        up.setToolTip("上へ")
        down.setToolTip("下へ")
        delete.setToolTip("削除（最低1フェーズは必要）")
        for button in (up, down, delete):
            button.setFixedWidth(30)
            buttons_layout.addWidget(button)
        up.clicked.connect(lambda checked=False, editor=name: self._move_row(editor, -1))
        down.clicked.connect(lambda checked=False, editor=name: self._move_row(editor, 1))
        delete.clicked.connect(lambda checked=False, editor=name: self._delete_row(editor))
        self.table.setCellWidget(row, 4, buttons_cell)

    def _snapshot(self) -> list[dict]:
        rows = []
        for index in range(self.table.rowCount()):
            opacity_cell = self.table.cellWidget(index, 3)
            rows.append({
                "name": self.table.cellWidget(index, 0).text(),
                "minutes": self.table.cellWidget(index, 1).value(),
                "color": self.table.cellWidget(index, 2).currentData(),
                "opacity": opacity_cell.findChild(QSlider).value(),
            })
        return rows

    def _row_for_editor(self, editor: QWidget) -> int:
        for index in range(self.table.rowCount()):
            if self.table.cellWidget(index, 0) is editor:
                return index
        return -1

    def _move_row(self, editor: QWidget, change: int) -> None:
        row = self._row_for_editor(editor)
        other = row + change
        if row < 0 or not 0 <= other < self.table.rowCount():
            return
        rows = self._snapshot()
        rows[row], rows[other] = rows[other], rows[row]
        self._render_rows(rows)

    def _delete_row(self, editor: QWidget) -> None:
        if self.table.rowCount() <= 1:
            QMessageBox.information(self, "FocusLoop", "フェーズは最低1つ必要です。")
            return
        row = self._row_for_editor(editor)
        if row >= 0:
            rows = self._snapshot()
            rows.pop(row)
            self._render_rows(rows)

    def _add_phase(self) -> None:
        rows = self._snapshot()
        rows.append({"name": "新しいフェーズ", "minutes": 5, "color": "sky", "opacity": 100})
        self._render_rows(rows)
        self.table.scrollToBottom()

    def _validate_changes(self) -> bool:
        try:
            self.result_phases = tuple(
                PhaseConfig(
                    name=row["name"].strip(),
                    minutes=row["minutes"],
                    color=row["color"],
                    opacity=row["opacity"],
                )
                for row in self._snapshot()
            )
        except ValueError as error:
            QMessageBox.warning(self, "FocusLoop", f"設定内容をご確認ください：{error}")
            return False
        return True

    def apply_changes(self) -> None:
        """Save and display changes immediately without closing this dialog."""
        if self._validate_changes():
            self.applied.emit(self)

    def accept(self) -> None:
        """OK applies pending changes and closes the dialog."""
        if self._validate_changes():
            self.applied.emit(self)
            super().accept()


class FocusLoopApp:
    def __init__(self, qt_app: QApplication) -> None:
        self.qt_app = qt_app
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.settings = QSettings("FocusLoop", "FocusLoop")
        old_work = _int_setting(self.settings, "work_minutes", 45, 1, 240)
        old_break = _int_setting(self.settings, "break_minutes", 15, 1, 240)
        phases = phases_from_json(
            self.settings.value("phases_json", None),
            legacy_work=old_work,
            legacy_break=old_break,
        )
        self.font_size = _int_setting(self.settings, "font_size", 42, 18, 96)
        self.position = str(self.settings.value("position", "bottom_left"))
        if self.position not in {value for _, value in POSITIONS}:
            self.position = "bottom_left"

        self.timer_model = FocusTimer(phases)
        self.overlay = Overlay(self.font_size, self.position, self.timer_model.current_phase)
        self.tray = QSystemTrayIcon(self._tray_icon(), qt_app)
        self.tray.setToolTip("FocusLoop")
        self.menu = QMenu()
        self.status_action = self.menu.addAction("")
        self.status_action.setEnabled(False)
        self.menu.addSeparator()

        self.pause_action = self.menu.addAction("一時停止")
        self.pause_action.triggered.connect(self.toggle_pause)
        self.skip_action = self.menu.addAction("次のフェーズへ")
        self.skip_action.triggered.connect(self.skip)
        self.reset_action = self.menu.addAction("現在のフェーズをリセット")
        self.reset_action.triggered.connect(self.reset)
        self.menu.addSeparator()

        settings_action = self.menu.addAction("フェーズ・表示の設定…")
        settings_action.triggered.connect(self.show_settings)
        self.menu.addSeparator()
        quit_action = self.menu.addAction("終了")
        quit_action.triggered.connect(self.close)

        # Handle context clicks ourselves to keep the entire menu above the taskbar.
        self.tray.activated.connect(self._tray_activated)
        self.settings_dialog: SettingsDialog | None = None
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
                None, "FocusLoop", "システムトレイを利用できないため、起動できません。"
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
        phase = self.timer_model.current_phase
        state = (display, phase, self.timer_model.paused)
        if state != self.last_display:
            self.overlay.set_clock(display, phase)
            title = phase.name
            if self.timer_model.paused:
                title += " (一時停止)"
            self.status_action.setText(f"{title}  {display}")
            self.pause_action.setText("再開" if self.timer_model.paused else "一時停止")
            self.tray.setToolTip(f"FocusLoop - {title} {display}")
            self.last_display = state
        if switched:
            self.tray.showMessage(
                "FocusLoop", f"「{phase.name}」の時間になりました。",
                QSystemTrayIcon.MessageIcon.Information, 4000
            )

    def _tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # One left-click opens the settings; pause/resume stays in the menu.
            self.show_settings()
        elif reason == QSystemTrayIcon.ActivationReason.Context:
            self._show_tray_menu()

    def _show_tray_menu(self) -> None:
        cursor = QCursor.pos()
        screen = QGuiApplication.screenAt(cursor) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        bounds = screen.availableGeometry()
        size = self.menu.sizeHint()
        x, y = tray_menu_position(
            cursor.x(),
            cursor.y(),
            bounds.x(),
            bounds.y(),
            bounds.width(),
            bounds.height(),
            size.width(),
            size.height(),
        )
        self.menu.popup(QPoint(x, y))

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
        """Show one modeless settings window, keeping the timer running."""
        if self.settings_dialog is not None:
            self.settings_dialog.show()
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return

        dialog = SettingsDialog(None, self.timer_model, self.font_size, self.position)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.applied.connect(self._apply_settings)
        dialog.finished.connect(self._settings_closed)
        self.settings_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _settings_closed(self, result: int) -> None:
        self.settings_dialog = None

    def _apply_settings(self, dialog: SettingsDialog) -> None:
        """Persist and preview settings without closing the settings window."""
        if dialog.result_phases is None:
            return
        self.timer_model.configure(dialog.result_phases)
        self.font_size = dialog.font_spin.value()
        self.position = str(dialog.position_combo.currentData())
        self.overlay.apply_appearance(self.font_size, self.position)
        self.settings.setValue("phases_json", phases_to_json(self.timer_model.phases))
        self.settings.setValue("font_size", self.font_size)
        self.settings.setValue("position", self.position)
        self.settings.sync()
        self.update()

    def close(self) -> None:
        self.qt_timer.stop()
        if self.settings_dialog is not None:
            self.settings_dialog.close()
        self.overlay.close()
        self.tray.hide()
        self.qt_app.quit()
