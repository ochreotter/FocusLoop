"""FocusLoop: a number-only transparent overlay with editable phases."""

from __future__ import annotations

from dataclasses import asdict

from PySide6.QtCore import QMimeData, QPoint, QSize, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QDrag, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QAbstractButton,
    QComboBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QScrollArea,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .geometry import tray_menu_position
from .icons import clock_icon
from .overlay import Overlay
from .timer import (
    COLOR_PRESETS,
    MAX_FONT_SIZE,
    MIN_FONT_SIZE,
    FocusTimer,
    PhaseConfig,
    POSITION_VALUES,
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


def confirm_change(
    parent: QWidget, title: str, question: str, details: str, confirm_label: str,
) -> bool:
    """Shared safe confirmation: cancel is the default, including Escape/close."""
    message = QMessageBox(parent)
    message.setWindowTitle(title)
    message.setIcon(QMessageBox.Icon.Warning)
    message.setText(question)
    message.setInformativeText(details)
    message.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
    )
    message.button(QMessageBox.StandardButton.Yes).setText(confirm_label)
    cancel = message.button(QMessageBox.StandardButton.Cancel)
    cancel.setText("キャンセル")
    message.setDefaultButton(cancel)
    for button in message.buttons():
        button.setCursor(Qt.CursorShape.PointingHandCursor)
    return message.exec() == QMessageBox.StandardButton.Yes


class PhaseDragHandle(QToolButton):
    """A dedicated drag target so editors remain clickable and selectable."""

    def __init__(self, card: "PhaseCard") -> None:
        super().__init__(card)
        self.card = card
        self.setText("⠿")
        self.setToolTip("ドラッグして順番を変更")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._press_point: QPoint | None = None

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_point = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        if (
            self._press_point is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and (event.position().toPoint() - self._press_point).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            self._press_point = None
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData("application/x-focusloop-phase", b"phase")
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.MoveAction)
        else:
            super().mouseMoveEvent(event)


class PhaseCard(QFrame):
    """An expandable, reorderable, two-column editor for a single phase."""

    def __init__(self, owner: "SettingsDialog", values: dict) -> None:
        super().__init__(owner.cards_container)
        self.owner = owner
        self.setObjectName("phase_card")
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setAcceptDrops(True)
        self.setStyleSheet(
            "QFrame#phase_card { border: 1px solid palette(mid); "
            "border-radius: 8px; margin: 2px; }"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 10)
        outer.setSpacing(8)

        header = QHBoxLayout()
        self.drag_handle = PhaseDragHandle(self)
        self.title = QLabel(self)
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.summary = QLabel(self)
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("color: palette(mid);")
        caption = QVBoxLayout()
        caption.setSpacing(2)
        caption.addWidget(self.title)
        caption.addWidget(self.summary)
        self.move_up = QToolButton(self)
        self.move_up.setText("↑")
        self.move_up.setToolTip("上へ移動")
        self.move_down = QToolButton(self)
        self.move_down.setText("↓")
        self.move_down.setToolTip("下へ移動")
        self.expand_button = QToolButton(self)
        self.expand_button.setText("設定を開く")
        self.expand_button.setCheckable(True)
        self.expand_button.toggled.connect(self._toggle_expanded)
        self.move_up.clicked.connect(lambda: owner._shift_card(self, -1))
        self.move_down.clicked.connect(lambda: owner._shift_card(self, 1))
        header.addWidget(self.drag_handle)
        header.addLayout(caption, 1)
        header.addWidget(self.move_up)
        header.addWidget(self.move_down)
        header.addWidget(self.expand_button)
        outer.addLayout(header)

        self.body = QWidget(self)
        fields = QGridLayout(self.body)
        fields.setContentsMargins(4, 4, 4, 4)
        fields.setHorizontalSpacing(18)
        fields.setVerticalSpacing(9)
        fields.setColumnStretch(0, 1)
        fields.setColumnStretch(1, 1)

        def field(row: int, col: int, label: str, editor: QWidget) -> None:
            area = QWidget(self.body)
            column = QVBoxLayout(area)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(3)
            column.addWidget(QLabel(label, area))
            column.addWidget(editor)
            fields.addWidget(area, row, col)

        self.name = QLineEdit(str(values["name"]), self.body)
        self.name.setMaxLength(40)
        self.name.setPlaceholderText("フェーズ名")
        field(0, 0, "フェーズ名", self.name)

        self.minutes = QSpinBox(self.body)
        self.minutes.setRange(1, 240)
        self.minutes.setSuffix(" 分")
        self.minutes.setValue(int(values["minutes"]))
        field(0, 1, "時間", self.minutes)

        self.color = color_combo(self.body, values["color"])
        field(1, 0, "メイン色", self.color)

        secondary = QWidget(self.body)
        secondary_layout = QHBoxLayout(secondary)
        secondary_layout.setContentsMargins(0, 0, 0, 0)
        self.gradient = QCheckBox("ON", secondary)
        self.gradient.setToolTip("グラデーション")
        self.gradient.setChecked(bool(values["gradient"]))
        self.gradient_end = color_combo(secondary, values["gradient_end"])
        self.gradient_end.setEnabled(self.gradient.isChecked())
        self.gradient.toggled.connect(self.gradient_end.setEnabled)
        secondary_layout.addWidget(self.gradient)
        secondary_layout.addWidget(self.gradient_end, 1)
        field(1, 1, "サブ色・グラデーション", secondary)

        self.size = QSlider(Qt.Orientation.Horizontal, self.body)
        self.size.setRange(MIN_FONT_SIZE, MAX_FONT_SIZE)
        self.size.setSingleStep(1)
        self.size.setPageStep(10)
        self.size.setValue(int(values["font_size"]))
        self.size_label = QLabel(f"{self.size.value()} pt", self.body)
        size_row = QWidget(self.body)
        size_layout = QHBoxLayout(size_row)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_layout.addWidget(self.size, 1)
        size_layout.addWidget(self.size_label)
        field(2, 0, "サイズ", size_row)

        self.opacity = QSlider(Qt.Orientation.Horizontal, self.body)
        self.opacity.setRange(0, 100)
        self.opacity.setSingleStep(1)
        self.opacity.setValue(int(values["opacity"]))
        self.opacity_label = QLabel(f"{self.opacity.value()}%", self.body)
        opacity_row = QWidget(self.body)
        opacity_layout = QHBoxLayout(opacity_row)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        opacity_layout.addWidget(self.opacity, 1)
        opacity_layout.addWidget(self.opacity_label)
        field(2, 1, "透過率", opacity_row)

        self.simple = QCheckBox("Simple（OFFで標準表示）", self.body)
        self.simple.setChecked(bool(values["simple"]))
        field(3, 0, "表示モード", self.simple)

        self.topmost = QCheckBox("最前面に表示", self.body)
        self.topmost.setChecked(bool(values["topmost"]))
        field(3, 1, "ウィンドウ", self.topmost)

        self.position = QComboBox(self.body)
        for label, value in POSITIONS:
            self.position.addItem(label, value)
        self.position.setCurrentIndex(max(0, self.position.findData(values["position"])))
        field(4, 0, "表示位置", self.position)

        delete_area = QWidget(self.body)
        delete_layout = QHBoxLayout(delete_area)
        delete_layout.setContentsMargins(0, 0, 0, 0)
        delete_layout.addStretch()
        self.delete_button = QPushButton("削除", delete_area)
        self.delete_button.setFixedSize(54, 26)
        self.delete_button.setStyleSheet(
            "QPushButton { background-color: #F9EAEC; color: #964650; "
            "border: 1px solid #DDB9BE; border-radius: 5px; "
            "padding: 0; font-weight: 500; } "
            "QPushButton:hover { background-color: #F3DBDF; color: #853942; } "
            "QPushButton:pressed { background-color: #EBC9CE; }"
        )
        self.delete_button.setToolTip("フェーズを削除（確認あり）")
        self.delete_button.clicked.connect(lambda: owner._confirm_delete_card(self))
        delete_layout.addWidget(self.delete_button)
        field(4, 1, "フェーズ操作", delete_area)

        outer.addWidget(self.body)
        self.body.hide()
        for widget in (
            self.name, self.minutes, self.color, self.gradient, self.gradient_end,
            self.size, self.opacity, self.simple, self.position, self.topmost,
        ):
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._changed)
            elif isinstance(widget, QCheckBox):
                widget.toggled.connect(self._changed)
            elif isinstance(widget, (QSlider, QSpinBox)):
                widget.valueChanged.connect(self._changed)
            else:
                widget.currentIndexChanged.connect(self._changed)
        self.size.valueChanged.connect(lambda v: self.size_label.setText(f"{v} pt"))
        self.opacity.valueChanged.connect(
            lambda v: self.opacity_label.setText(f"{v}%")
        )
        self._refresh_summary()

    def snapshot(self) -> dict:
        return {
            "name": self.name.text(),
            "minutes": self.minutes.value(),
            "color": self.color.currentData(),
            "gradient": self.gradient.isChecked(),
            "gradient_end": self.gradient_end.currentData(),
            "font_size": self.size.value(),
            "opacity": self.opacity.value(),
            "simple": self.simple.isChecked(),
            "position": self.position.currentData(),
            "topmost": self.topmost.isChecked(),
        }

    def _refresh_summary(self) -> None:
        self.title.setText(self.name.text() or "（名前未入力）")
        colors = dict((key, label) for key, label, _hex in COLOR_PRESETS)
        positions = dict((value, label) for label, value in POSITIONS)
        main = colors.get(self.color.currentData(), "?")
        secondary = (
            f" → {colors.get(self.gradient_end.currentData(), '?')}"
            if self.gradient.isChecked() else ""
        )
        mode = "Simple" if self.simple.isChecked() else "標準"
        front = "最前面ON" if self.topmost.isChecked() else "最前面OFF"
        self.summary.setText(
            f"{self.minutes.value()}分 · {main}{secondary} · "
            f"{mode} · {positions.get(self.position.currentData(), '?')} · {front}"
        )

    def _changed(self, *_args) -> None:
        self._refresh_summary()
        self.owner._notify_change()

    def _toggle_expanded(self, enabled: bool) -> None:
        self.body.setVisible(enabled)
        self.expand_button.setText("閉じる" if enabled else "設定を開く")
        if enabled:
            self.owner._expand_card(self)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt API
        if event.mimeData().hasFormat("application/x-focusloop-phase"):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 - Qt API
        self.dragEnterEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt API
        source = event.source()
        if isinstance(source, PhaseDragHandle) and source.card is not self:
            self.owner._reorder_cards(source.card, self)
            event.acceptProposedAction()
        else:
            event.ignore()


class SettingsDialog(QDialog):
    """Modeless settings with a scrollable accordion instead of a wide table."""

    changed = Signal(object, bool)
    loop_reset = Signal()
    timer_reset = Signal()
    initialize_requested = Signal()

    def __init__(self, parent, timer: FocusTimer) -> None:
        super().__init__(parent)
        self.setWindowTitle("FocusLoop - 設定")
        self.resize(850, 690)
        self.setMinimumSize(660, 440)
        self.result_phases: tuple[PhaseConfig, ...] | None = None
        self._rendering = False
        self.loop_label = QLabel(f"LOOP {timer.loop_number:02d}", self)
        loop_reset = QPushButton("ループ数をリセット", self)
        loop_reset.clicked.connect(lambda: self.loop_reset.emit())
        timer_reset = QPushButton("現在のフェーズをリセット", self)
        timer_reset.clicked.connect(lambda: self.timer_reset.emit())

        top = QHBoxLayout()
        top.addWidget(self.loop_label)
        top.addWidget(loop_reset)
        top.addStretch()
        top.addWidget(timer_reset)

        self.cards_container = QWidget(self)
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(5, 5, 5, 5)
        self.cards_layout.setSpacing(9)
        self.cards_layout.addStretch()
        self.cards: list[PhaseCard] = []
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.cards_container)
        self._render_cards([asdict(phase) for phase in timer.phases], timer.phase_index)

        add_button = QPushButton("＋ フェーズを追加", self)
        add_button.clicked.connect(self._add_phase)
        note = QLabel(
            "設定は即時反映・保存されます。⠿をドラッグ、または↑↓で並べ替え。"
            "順番・分数の変更時は先頭から再スタートします。",
            self,
        )
        note.setWordWrap(True)

        initialize = QPushButton("初期化", self)
        initialize.setObjectName("initialize_button")
        initialize.setToolTip("設定とタイマーをすべて初期値に戻す")
        initialize.clicked.connect(self._confirm_initialize)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("閉じる")
        buttons.rejected.connect(self.reject)
        footer = QHBoxLayout()
        footer.addWidget(initialize)
        footer.addStretch()
        footer.addWidget(buttons)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.scroll, 1)
        layout.addWidget(add_button)
        layout.addWidget(note)
        layout.addLayout(footer)
        self._set_button_cursors()

    def _render_cards(self, rows: list[dict], expanded_index: int = 0) -> None:
        self._rendering = True
        try:
            for card in self.cards:
                self.cards_layout.removeWidget(card)
                card.setParent(None)
                card.deleteLater()
            self.cards = []
            for i, row in enumerate(rows):
                card = PhaseCard(self, row)
                self.cards.append(card)
                self.cards_layout.insertWidget(i, card)
                card.show()
            if self.cards:
                self.cards[max(0, min(expanded_index, len(self.cards) - 1))].expand_button.setChecked(True)
            self._update_move_buttons()
        finally:
            self._rendering = False
            self._set_button_cursors()

    def _set_button_cursors(self) -> None:
        for button in self.findChildren(QAbstractButton):
            button.setCursor(Qt.CursorShape.PointingHandCursor)

    def _expand_card(self, selected: PhaseCard) -> None:
        for card in self.cards:
            if card is not selected and card.expand_button.isChecked():
                card.expand_button.setChecked(False)

    def _update_move_buttons(self) -> None:
        for i, card in enumerate(self.cards):
            card.move_up.setEnabled(i > 0)
            card.move_down.setEnabled(i < len(self.cards) - 1)

    def _reorder_cards(self, source: PhaseCard, target: PhaseCard) -> None:
        if source is target or source not in self.cards or target not in self.cards:
            return
        self.cards.remove(source)
        self.cards.insert(self.cards.index(target), source)
        self.cards_layout.removeWidget(source)
        self.cards_layout.insertWidget(self.cards.index(source), source)
        self._update_move_buttons()
        self._notify_change(force_restart=True)

    def _shift_card(self, card: PhaseCard, offset: int) -> None:
        index = self.cards.index(card)
        next_index = index + offset
        if 0 <= next_index < len(self.cards):
            self._reorder_cards(card, self.cards[next_index])

    def _notify_change(self, force_restart: bool = False) -> None:
        if self._rendering:
            return
        try:
            phases = tuple(
                PhaseConfig(**{**card.snapshot(), "name": card.name.text().strip()})
                for card in self.cards
            )
        except ValueError:
            return
        if force_restart or phases != self.result_phases:
            self.result_phases = phases
            self.changed.emit(self, force_restart)

    def _confirm_delete_card(self, card: PhaseCard) -> None:
        if len(self.cards) <= 1:
            QMessageBox.information(self, "FocusLoop", "フェーズは最低1つ必要です。")
            return
        if confirm_change(
            self, "FocusLoop - フェーズ削除",
            f"「{card.name.text()}」を削除しますか？",
            "この操作は取り消せません。", "削除する",
        ):
            rows = [other.snapshot() for other in self.cards if other is not card]
            self._render_cards(rows)
            self._notify_change(force_restart=True)

    def _add_phase(self) -> None:
        rows = [card.snapshot() for card in self.cards]
        rows.append(asdict(PhaseConfig("新しいフェーズ", 5, color="sky")))
        self._render_cards(rows, len(rows) - 1)
        self._notify_change(force_restart=True)
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())

    def _confirm_initialize(self) -> None:
        if confirm_change(
            self, "FocusLoop - 初期化", "すべての設定を初期化しますか？",
            "フェーズ・色・サイズ・表示位置・表示モード・最前面・ループ数を初期値に戻し、"
            "作業45:00からタイマーを再開します。この操作は取り消せません。",
            "初期化する",
        ):
            self.initialize_requested.emit()

    def restore_defaults(self, phases: tuple[PhaseConfig, ...], loop_number: int) -> None:
        self._render_cards([asdict(phase) for phase in phases])
        self.result_phases = phases
        self.set_loop_number(loop_number)

    def set_loop_number(self, number: int) -> None:
        self.loop_label.setText(f"LOOP {number:02d}")



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
        old_position = str(self.settings.value("position", "bottom_left"))
        if old_position not in POSITION_VALUES:
            old_position = "bottom_left"
        old_style = str(self.settings.value("display_style", "modern"))
        phases = phases_from_json(
            self.settings.value("phases_json", None),
            legacy_work=old_work,
            legacy_break=old_break,
            legacy_font_size=legacy_font_size,
            legacy_position=old_position,
            legacy_simple=(old_style == "simple"),
        )
        loop_number = _int_setting(self.settings, "loop_number", 1, 1, 2_147_483_647)

        self.timer_model = FocusTimer(phases, initial_loop=loop_number)
        self._last_loop_saved = loop_number
        self.overlay = Overlay(self.timer_model.current_phase)
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
        self._last_loop_saved = 1
        self.last_display = None

        # Clear the old compatibility keys too so they cannot reappear later.
        self.settings.clear()
        self.settings.setValue("phases_json", phases_to_json(phases))
        self.settings.setValue("loop_number", 1)
        self.settings.sync()

        if self.settings_dialog is not None:
            self.settings_dialog.restore_defaults(phases, 1)
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

        dialog = SettingsDialog(None, self.timer_model)
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
        self.settings.setValue("phases_json", phases_to_json(self.timer_model.phases))
        self.settings.sync()
        self.update()

    def close(self) -> None:
        self.qt_timer.stop()
        if self.settings_dialog is not None:
            self.settings_dialog.close()
        self.overlay.close()
        self.tray.hide()
        self.qt_app.quit()
