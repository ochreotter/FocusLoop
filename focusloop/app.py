"""FocusLoop: a number-only transparent overlay with editable phases."""

from __future__ import annotations

from dataclasses import asdict

from PySide6.QtCore import QPoint, QSize, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractButton,
    QComboBox,
    QCheckBox,
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
from .overlay import DISPLAY_STYLES, Overlay
from .timer import (
    COLOR_HEX,
    COLOR_PRESETS,
    DEFAULT_FONT_SIZE,
    MAX_FONT_SIZE,
    MIN_FONT_SIZE,
    FocusTimer,
    PhaseConfig,
    default_phases,
    phases_from_json,
    phases_to_json,
)

POSITIONS = (
    ("左下", "bottom_left"),
    ("右下", "bottom_right"),
    ("左上", "top_left"),
    ("右上", "top_right"),
    ("中央", "center"),
)


def _int_setting(settings: QSettings, key: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(settings.value(key, default))
    except (ValueError, TypeError):
        value = default
    return min(max(value, minimum), maximum)


def color_swatch_icon(hex_value: str) -> QIcon:
    """Keep both white and black color samples visible next to their names."""
    image = QPixmap(18, 18)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QColor("#7D8592"))
    painter.setBrush(QColor(hex_value))
    painter.drawRoundedRect(1, 1, 16, 16, 3, 3)
    painter.end()
    return QIcon(image)


def color_combo(parent: QWidget, selected: str) -> QComboBox:
    """Build identical main/secondary palettes with visible color swatches."""
    combo = QComboBox(parent)
    combo.setIconSize(QSize(18, 18))
    for key, label, hex_value in COLOR_PRESETS:
        combo.addItem(color_swatch_icon(hex_value), label, key)
    combo.setCurrentIndex(max(0, combo.findData(selected)))
    return combo


class SettingsDialog(QDialog):
    """Edit all phases, including order, text color and per-phase opacity."""

    changed = Signal(object, bool)
    loop_reset = Signal()
    timer_reset = Signal()
    initialize_requested = Signal()

    def __init__(self, parent, timer: FocusTimer, position: str, style: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("FocusLoop - 設定")
        self.setMinimumWidth(1120)
        self.setMinimumHeight(450)
        self.result_phases: tuple[PhaseConfig, ...] | None = None
        self._last_emitted_appearance = (position, style)

        self.position_combo = QComboBox(self)
        for label, value in POSITIONS:
            self.position_combo.addItem(label, value)
        self.position_combo.setCurrentIndex(max(0, self.position_combo.findData(position)))

        self.style_combo = QComboBox(self)
        for label, value in DISPLAY_STYLES:
            self.style_combo.addItem(label, value)
        self.style_combo.setCurrentIndex(max(0, self.style_combo.findData(style)))

        self.loop_label = QLabel(f"LOOP {timer.loop_number:02d}", self)
        reset_loop_button = QPushButton("ループ数をリセット", self)
        reset_loop_button.clicked.connect(lambda _checked=False: self.loop_reset.emit())

        loop_row = QHBoxLayout()
        loop_row.addWidget(self.loop_label)
        loop_row.addWidget(reset_loop_button)
        loop_row.addStretch()

        form = QFormLayout()
        form.addRow("表示位置", self.position_combo)
        form.addRow("表示スタイル", self.style_combo)
        form.addRow("ループ数", loop_row)

        reset_timer_button = QPushButton("現在のフェーズをリセット", self)
        reset_timer_button.clicked.connect(lambda _checked=False: self.timer_reset.emit())
        form.addRow("タイマー", reset_timer_button)

        self.table = QTableWidget(0, 7, self)
        self.table.setHorizontalHeaderLabels(("フェーズ名", "時間", "メイン色", "サブ色・グラデーション", "サイズ", "透過率", "削除"))
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
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)
        self._render_rows([asdict(phase) for phase in timer.phases])
        self.position_combo.currentIndexChanged.connect(lambda _index: self._notify_change())
        self.style_combo.currentIndexChanged.connect(lambda _index: self._notify_change())

        add_button = QPushButton("＋ フェーズを追加", self)
        add_button.clicked.connect(self._add_phase)

        note = QLabel(
            "設定は変更と同時に反映・保存されます。"
            "左端の「⠿」をドラッグして順番を変更できます。"
            "フェーズの順番・分数を変更すると、先頭から再スタートします。"
            "名前・色・透過率・表示スタイル・グラデーション・位置・サイズの変更では時間をリセットしません。"
            "「閉じる」を押しても設定は保持されます。",
            self,
        )
        note.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("閉じる")
        buttons.rejected.connect(self.reject)

        initialize_button = QPushButton("初期化", self)
        initialize_button.setObjectName("initialize_button")
        initialize_button.setToolTip("設定とタイマーをすべて初期値に戻す")
        initialize_button.clicked.connect(self._confirm_initialize)
        footer = QHBoxLayout()
        footer.addWidget(initialize_button)
        footer.addStretch()
        footer.addWidget(buttons)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.table)
        layout.addWidget(add_button)
        layout.addWidget(note)
        layout.addLayout(footer)
        self._set_button_cursors()

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
            self._set_button_cursors()

    def _set_button_cursors(self) -> None:
        """Show that buttons and checkboxes are clickable, including dynamic rows."""
        for button in self.findChildren(QAbstractButton):
            button.setCursor(Qt.CursorShape.PointingHandCursor)

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

        color = color_combo(self.table, phase["color"])
        self.table.setCellWidget(row, 2, color)

        sub_cell = QWidget(self.table)
        sub_layout = QHBoxLayout(sub_cell)
        sub_layout.setContentsMargins(4, 0, 4, 0)
        gradient = QCheckBox("ON", sub_cell)
        gradient.setToolTip("グラデーション")
        gradient.setChecked(bool(phase["gradient"]))
        gradient_end = color_combo(sub_cell, phase["gradient_end"])
        gradient_end.setEnabled(gradient.isChecked())
        gradient.toggled.connect(gradient_end.setEnabled)
        sub_layout.addWidget(gradient)
        sub_layout.addWidget(gradient_end, 1)
        self.table.setCellWidget(row, 3, sub_cell)

        size_cell = QWidget(self.table)
        size_layout = QHBoxLayout(size_cell)
        size_layout.setContentsMargins(4, 0, 4, 0)
        font_size = QSlider(Qt.Orientation.Horizontal, size_cell)
        font_size.setRange(MIN_FONT_SIZE, MAX_FONT_SIZE)
        font_size.setSingleStep(1)
        font_size.setPageStep(10)
        font_size.setValue(int(phase["font_size"]))
        font_size_label = QLabel(f"{font_size.value()} pt", size_cell)
        font_size_label.setMinimumWidth(52)
        font_size.valueChanged.connect(
            lambda value, label=font_size_label: label.setText(f"{value} pt")
        )
        font_size.valueChanged.connect(lambda _value: self._notify_change())
        size_layout.addWidget(font_size)
        size_layout.addWidget(font_size_label)
        self.table.setCellWidget(row, 4, size_cell)

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
        self.table.setCellWidget(row, 5, opacity_cell)

        # Use an inner wrapper so the button never fills/overflows its table cell.
        delete_cell = QWidget(self.table)
        delete_layout = QHBoxLayout(delete_cell)
        delete_layout.setContentsMargins(5, 3, 5, 3)
        delete_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        delete = QPushButton("削除", delete_cell)
        delete.setToolTip("削除（最低1フェーズは必要）")
        delete.setFixedSize(54, 26)
        delete.setStyleSheet(
            "QPushButton { background-color: #F9EAEC; color: #964650; "
            "border: 1px solid #DDB9BE; border-radius: 5px; "
            "padding: 0; font-weight: 500; } "
            "QPushButton:hover { background-color: #F3DBDF; color: #853942; } "
            "QPushButton:pressed { background-color: #EBC9CE; }"
        )
        delete.clicked.connect(lambda checked=False, editor=name: self._confirm_delete_row(editor))
        delete_layout.addWidget(delete)
        self.table.setCellWidget(row, 6, delete_cell)

        name.textChanged.connect(lambda _text: self._notify_change())
        minutes.valueChanged.connect(lambda _value: self._notify_change())
        color.currentIndexChanged.connect(lambda _index: self._notify_change())
        gradient.toggled.connect(lambda _value: self._notify_change())
        gradient_end.currentIndexChanged.connect(lambda _value: self._notify_change())
        opacity.valueChanged.connect(lambda _value: self._notify_change())

    def _confirm_initialize(self) -> None:
        """Require explicit confirmation before discarding every saved setting."""
        message = QMessageBox(self)
        message.setWindowTitle("FocusLoop - 初期化")
        message.setIcon(QMessageBox.Icon.Warning)
        message.setText("すべての設定を初期化しますか？")
        message.setInformativeText(
            "フェーズ・色・サイズ・表示位置・表示スタイル・ループ数を初期値に戻し、"
            "作業45:00からタイマーを再開します。この操作は取り消せません。"
        )
        message.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )
        confirm = message.button(QMessageBox.StandardButton.Yes)
        confirm.setText("初期化する")
        cancel = message.button(QMessageBox.StandardButton.Cancel)
        cancel.setText("キャンセル")
        message.setDefaultButton(cancel)
        for button in message.buttons():
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        if message.exec() == QMessageBox.StandardButton.Yes:
            self.initialize_requested.emit()

    def restore_defaults(
        self, phases: tuple[PhaseConfig, ...], position: str, style: str, loop_number: int
    ) -> None:
        """Replace editor values without emitting partial/duplicate settings updates."""
        self._rendering = True
        try:
            self.position_combo.setCurrentIndex(self.position_combo.findData(position))
            self.style_combo.setCurrentIndex(self.style_combo.findData(style))
        finally:
            self._rendering = False
        self._render_rows([asdict(phase) for phase in phases])
        self.result_phases = phases
        self._last_emitted_appearance = (position, style)
        self.set_loop_number(loop_number)

     def set_loop_number(self, number: int) -> None:
        self.loop_label.setText(f"LOOP {number:02d}")

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
                    gradient=row["gradient"],
                    gradient_end=row["gradient_end"],
                )
                for row in self._snapshot()
            )
        except ValueError:
            # A name can temporarily be empty while typing. Resume as soon as
            # the input is valid, without interrupting the user with a dialog.
            return

        appearance = (self.position_combo.currentData(), self.style_combo.currentData())
        if (
            force_restart
            or phases != self.result_phases
            or appearance != self._last_emitted_appearance
        ):
            self.result_phases = phases
            self._last_emitted_appearance = appearance
            self.changed.emit(self, force_restart)

    def _snapshot(self) -> list[dict]:
        """Read phases in their current visible order (which may be dragged)."""
        rows = []
        header = self.table.verticalHeader()
        for visual in range(self.table.rowCount()):
            index = header.logicalIndex(visual)
            opacity_cell = self.table.cellWidget(index, 5)
            rows.append({
                "name": self.table.cellWidget(index, 0).text(),
                "minutes": self.table.cellWidget(index, 1).value(),
                "color": self.table.cellWidget(index, 2).currentData(),
                "font_size": self.table.cellWidget(index, 4).findChild(QSlider).value(),
                "opacity": opacity_cell.findChild(QSlider).value(),
                "gradient": self.table.cellWidget(index, 3).findChild(QCheckBox).isChecked(),
                "gradient_end": self.table.cellWidget(index, 3).findChild(QComboBox).currentData(),
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

    def _confirm_delete_row(self, editor: QWidget) -> None:
        """Ask before removing a phase; Cancel/escape leaves all settings intact."""
        row = self._row_for_editor(editor)
        if row < 0:
            return
        if self.table.rowCount() <= 1:
            QMessageBox.information(self, "FocusLoop", "フェーズは最低1つ必要です。")
            return

        phase_name = editor.text()
        message = QMessageBox(self)
        message.setWindowTitle("FocusLoop - フェーズ削除")
        message.setIcon(QMessageBox.Icon.Warning)
        message.setText(f"「{phase_name}」を削除しますか？")
        message.setInformativeText("この操作は取り消せません。")
        message.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )
        confirm = message.button(QMessageBox.StandardButton.Yes)
        confirm.setText("削除する")
        cancel = message.button(QMessageBox.StandardButton.Cancel)
        cancel.setText("キャンセル")
        message.setDefaultButton(cancel)
        for button in message.buttons():
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        if message.exec() == QMessageBox.StandardButton.Yes:
            self._delete_row(editor)

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
        rows.append(asdict(PhaseConfig("新しいフェーズ", 5, color="sky")))
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
        self.display_style = str(self.settings.value("display_style", "modern"))
        if self.display_style not in {value for _, value in DISPLAY_STYLES}:
            self.display_style = "modern"
        loop_number = _int_setting(self.settings, "loop_number", 1, 1, 2_147_483_647)

        self.timer_model = FocusTimer(phases, initial_loop=loop_number)
        self._last_loop_saved = loop_number
        self.overlay = Overlay(self.position, self.timer_model.current_phase, self.display_style)
        self.tray = QSystemTrayIcon(clock_icon(), qt_app)
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
        self.overlay.set_clock(
            display, phase, remaining / (phase.minutes * 60), self.timer_model.loop_number
        )
        if self.timer_model.loop_number != self._last_loop_saved:
            self._save_loop_number()
        state = (display, phase, self.timer_model.paused)
        if state != self.last_display:
            title = phase.name
            if self.timer_model.paused:
                title += " (一時停止)"
            self.status_action.setText(f"{title}  {display}")
            self.pause_action.setText("再開" if self.timer_model.paused else "一時停止")
            self.tray.setToolTip(f"FocusLoop - {title} {display}")
            self.last_display = state
        if switched:
            self._notify_phase_change()

    def _save_loop_number(self) -> None:
        number = self.timer_model.loop_number
        self.settings.setValue("loop_number", number)
        self.settings.sync()
        self._last_loop_saved = number
        if self.settings_dialog is not None:
            self.settings_dialog.set_loop_number(number)

    def _reset_loop_count(self) -> None:
        """Reset the visible loop number while preserving the countdown."""
        self.timer_model.reset_loop_count()
        self._save_loop_number()
        self.update()

    def _initialize_defaults(self) -> None:
        """Reset all saved settings and timer state to the app's real defaults."""
        phases = default_phases()
        self.timer_model = FocusTimer(phases)
        self.position = "bottom_left"
        self.display_style = "modern"
        self._last_loop_saved = 1
        self.last_display = None

        # Clear the old compatibility keys too so they cannot reappear later.
        self.settings.clear()
        self.settings.setValue("phases_json", phases_to_json(phases))
        self.settings.setValue("position", self.position)
        self.settings.setValue("display_style", self.display_style)
        self.settings.setValue("loop_number", 1)
        self.settings.sync()

        self.overlay.apply_appearance(self.position, self.display_style)
        if self.settings_dialog is not None:
            self.settings_dialog.restore_defaults(phases, self.position, self.display_style, 1)
        self.update()

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

        dialog = SettingsDialog(None, self.timer_model, self.position, self.display_style)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.changed.connect(self._apply_settings)
        dialog.loop_reset.connect(self._reset_loop_count)
        dialog.timer_reset.connect(self.reset)
        dialog.initialize_requested.connect(self._initialize_defaults)
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
        style = str(dialog.style_combo.currentData())
        if (position, style) != (self.position, self.display_style):
            self.position = position
            self.display_style = style
            self.overlay.apply_appearance(position, style)

        self.settings.setValue("phases_json", phases_to_json(self.timer_model.phases))
        self.settings.setValue("position", self.position)
        self.settings.setValue("display_style", self.display_style)
        self.settings.sync()
        self.update()

    def close(self) -> None:
        self.qt_timer.stop()
        if self.settings_dialog is not None:
            self.settings_dialog.close()
        self.overlay.close()
        self.tray.hide()
        self.qt_app.quit()
