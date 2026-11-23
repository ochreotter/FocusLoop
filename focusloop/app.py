"""FocusLoop: a number-only transparent overlay with editable phases."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QIcon, QPainter
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
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .geometry import tray_menu_position
from .icons import clock_icon
from .timer import (
    COLOR_HEX,
    COLOR_PRESETS,
    DEFAULT_FONT_SIZE,
    MAX_FONT_SIZE,
    MIN_FONT_SIZE,
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

    def __init__(self, position: str, phase: PhaseConfig) -> None:
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
        self._render_font_size = phase.font_size
        self.position_name = position
        self._resize_and_reposition()

    def _resize_and_reposition(self) -> None:
        """Keep large clock digits visible inside the usable screen area."""
        screen = QGuiApplication.primaryScreen()
        margin = 24
        area = screen.availableGeometry() if screen is not None else None
        max_width = max(1, area.width() - margin * 2) if area else None
        max_height = max(1, area.height() - margin * 2) if area else None

        size = self.phase_config.font_size
        while True:
            font = QFont("Consolas", size)
            font.setBold(True)
            metrics = QFontMetrics(font)
            width = metrics.horizontalAdvance("000:00") + 30
            height = metrics.height() + 26
            if (
                size <= MIN_FONT_SIZE
                or max_width is None
                or (width <= max_width and height <= max_height)
            ):
                break
            size -= 1

        self._render_font_size = size
        self.setFixedSize(
            min(width, max_width) if max_width is not None else width,
            min(height, max_height) if max_height is not None else height,
        )
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
            needs_resize = phase.font_size != self.phase_config.font_size
            self.clock_text = text
            self.phase_config = phase
            if needs_resize:
                self._resize_and_reposition()
            else:
                self.update()

    def apply_appearance(self, position: str) -> None:
        self.position_name = position
        self.reposition()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        font = QFont("Consolas", self._render_font_size)
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

    changed = Signal(object, bool)

    def __init__(self, parent, timer: FocusTimer, position: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("FocusLoop - 設定")
        self.setMinimumWidth(760)
        self.setMinimumHeight(450)
        self.result_phases: tuple[PhaseConfig, ...] | None = None
        self._last_emitted_position = position

        self.position_combo = QComboBox(self)
        for label, value in POSITIONS:
            self.position_combo.addItem(label, value)
        self.position_combo.setCurrentIndex(max(0, self.position_combo.findData(position)))

        form = QFormLayout()
        form.addRow("表示位置", self.position_combo)

        self.table = QTableWidget(0, 6, self)
        self.table.setHorizontalHeaderLabels(("フェーズ名", "時間", "文字色", "文字サイズ", "透過率", "削除"))
        handle = self.table.verticalHeader()
        handle.show()
        handle.setFixedWidth(44)
        handle.setSectionsMovable(True)
        handle.setHighlightSections(False)
        handle.sectionMoved.connect(self._on_row_reordered)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self._render_rows([
            {
                "name": phase.name,
                "minutes": phase.minutes,
                "color": phase.color,
                "font_size": phase.font_size,
                "opacity": phase.opacity,
            }
            for phase in timer.phases
        ])
        self.position_combo.currentIndexChanged.connect(lambda _index: self._notify_change())

        add_button = QPushButton("＋ フェーズを追加", self)
        add_button.clicked.connect(self._add_phase)

        note = QLabel(
            "設定は変更と同時に反映・保存されます。"
            "左端の「⠿」をドラッグして順番を変更できます。"
            "フェーズの順番・分数を変更すると、先頭から再スタートします。"
            "名前・色・透過率・位置・文字サイズの変更では時間をリセットしません。"
            "「閉じる」を押しても設定は保持されます。",
            self,
        )
        note.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("閉じる")
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.table)
        layout.addWidget(add_button)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def _render_rows(self, rows: list[dict]) -> None:
        # Row rebuilds initialize widgets and must not trigger partial saves.
        self._rendering = True
        self.table.setUpdatesEnabled(False)
        try:
            self.table.setRowCount(0)
            for row in rows:
                self._add_row(row)
        finally:
            self.table.setUpdatesEnabled(True)
            self._rendering = False

    def _add_row(self, phase: dict) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setRowHeight(row, 44)
        self.table.setVerticalHeaderItem(row, QTableWidgetItem("⠿"))

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

        font_size = QSpinBox(self.table)
        font_size.setRange(MIN_FONT_SIZE, MAX_FONT_SIZE)
        font_size.setSuffix(" pt")
        font_size.setValue(int(phase["font_size"]))
        self.table.setCellWidget(row, 3, font_size)

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
        self.table.setCellWidget(row, 4, opacity_cell)

        delete = QPushButton("削除", self.table)
        delete.setToolTip("削除（最低1フェーズは必要）")
        delete.clicked.connect(lambda checked=False, editor=name: self._delete_row(editor))
        self.table.setCellWidget(row, 5, delete)

        name.textChanged.connect(lambda _text: self._notify_change())
        minutes.valueChanged.connect(lambda _value: self._notify_change())
        color.currentIndexChanged.connect(lambda _index: self._notify_change())
        font_size.valueChanged.connect(lambda _value: self._notify_change())
        opacity.valueChanged.connect(
            lambda value, label=opacity_label: self._opacity_changed(label, value)
        )

    def _opacity_changed(self, label: QLabel, value: int) -> None:
        label.setText(f"{value}%")
        self._notify_change()

    def _notify_change(self, force_restart: bool = False) -> None:
        if self._rendering:
            return
        try:
            phases = tuple(
                PhaseConfig(
                    name=row["name"].strip(),
                    minutes=row["minutes"],
                    color=row["color"],
                    opacity=row["opacity"],
                    font_size=row["font_size"],
                )
                for row in self._snapshot()
            )
        except ValueError:
            # A name can temporarily be empty while typing. Resume as soon as
            # the input is valid, without interrupting the user with a dialog.
            return

        position = self.position_combo.currentData()
        if (
            force_restart
            or phases != self.result_phases
            or position != self._last_emitted_position
        ):
            self.result_phases = phases
            self._last_emitted_position = position
            self.changed.emit(self, force_restart)

    def _snapshot(self) -> list[dict]:
        """Read phases in their current visible order (which may be dragged)."""
        rows = []
        header = self.table.verticalHeader()
        for visual in range(self.table.rowCount()):
            index = header.logicalIndex(visual)
            opacity_cell = self.table.cellWidget(index, 4)
            rows.append({
                "name": self.table.cellWidget(index, 0).text(),
                "minutes": self.table.cellWidget(index, 1).value(),
                "color": self.table.cellWidget(index, 2).currentData(),
                "font_size": self.table.cellWidget(index, 3).value(),
                "opacity": opacity_cell.findChild(QSlider).value(),
            })
        return rows

    def _on_row_reordered(self, logical: int, old_visual: int, new_visual: int) -> None:
        if not self._rendering:
            self._notify_change(force_restart=True)

    def _row_for_editor(self, editor: QWidget) -> int:
        for index in range(self.table.rowCount()):
            if self.table.cellWidget(index, 0) is editor:
                return index
        return -1

    def _delete_row(self, editor: QWidget) -> None:
        if self.table.rowCount() <= 1:
            QMessageBox.information(self, "FocusLoop", "フェーズは最低1つ必要です。")
            return
        row = self._row_for_editor(editor)
        if row >= 0:
            rows = self._snapshot()
            visible_index = self.table.verticalHeader().visualIndex(row)
            rows.pop(visible_index)
            self._render_rows(rows)
            self._notify_change(force_restart=True)

    def _add_phase(self) -> None:
        rows = self._snapshot()
        rows.append({"name": "新しいフェーズ", "minutes": 5, "color": "sky", "font_size": DEFAULT_FONT_SIZE, "opacity": 100})
        self._render_rows(rows)
        self.table.scrollToBottom()
        self._notify_change(force_restart=True)


class FocusLoopApp:
    def __init__(self, qt_app: QApplication) -> None:
        self.qt_app = qt_app
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.settings = QSettings("FocusLoop", "FocusLoop")
        old_work = _int_setting(self.settings, "work_minutes", 45, 1, 240)
        old_break = _int_setting(self.settings, "break_minutes", 15, 1, 240)
        legacy_font_size = _int_setting(
            self.settings, "font_size", DEFAULT_FONT_SIZE, MIN_FONT_SIZE, MAX_FONT_SIZE
        )
        phases = phases_from_json(
            self.settings.value("phases_json", None),
            legacy_work=old_work,
            legacy_break=old_break,
            legacy_font_size=legacy_font_size,
        )
        self.position = str(self.settings.value("position", "bottom_left"))
        if self.position not in {value for _, value in POSITIONS}:
            self.position = "bottom_left"

        self.timer_model = FocusTimer(phases)
        self.overlay = Overlay(self.position, self.timer_model.current_phase)
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

        settings_action = self.menu.addAction("設定")
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
        return clock_icon()

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
            self._notify_phase_change()

    def _notify_phase_change(self) -> None:
        """Send a Windows system-tray notification at each phase transition."""
        phase = self.timer_model.current_phase
        self.tray.showMessage(
            "FocusLoop",
            f"「{phase.name}」を開始しました（{phase.minutes}分）。",
            QSystemTrayIcon.MessageIcon.Information,
            6000,
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
        self._notify_phase_change()

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

        dialog = SettingsDialog(None, self.timer_model, self.position)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.changed.connect(self._apply_settings)
        dialog.finished.connect(self._settings_closed)
        self.settings_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def _settings_closed(self, result: int) -> None:
        self.settings_dialog = None

    def _apply_settings(self, dialog: SettingsDialog, force_restart: bool) -> None:
        """Immediately preview and persist every valid settings change."""
        if dialog.result_phases is None:
            return
        self.timer_model.configure(dialog.result_phases, force_restart=force_restart)
        position = str(dialog.position_combo.currentData())
        if position != self.position:
            self.position = position
            self.overlay.apply_appearance(self.position)

        self.settings.setValue("phases_json", phases_to_json(self.timer_model.phases))
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
