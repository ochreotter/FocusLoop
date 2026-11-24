"""FocusLoop: a number-only transparent overlay with editable phases."""

from __future__ import annotations

from dataclasses import asdict
import threading

from PySide6.QtCore import QEvent, QMimeData, QObject, QPoint, QSize, QSettings, Qt, QTimer, Signal, Slot
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
from .i18n import LANGUAGES, translate as tr
from .icons import clock_icon
from .overlay import Overlay
from . import updates
from .timer import (
    COLOR_PRESETS,
    DEFAULT_FONT_SIZE,
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


class NoWheelComboBox(QComboBox):
    """Ignore accidental wheel selection changes; let the parent page scroll."""

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt API
        event.ignore()


class NoWheelSpinBox(QSpinBox):
    """Prevent accidental duration edits and timer restarts while scrolling."""

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt API
        event.ignore()


def color_combo(parent: QWidget, selected: str, language: str = "ja") -> QComboBox:
    """Build identical main/secondary palettes with visible color swatches."""
    combo = NoWheelComboBox(parent)
    combo.setIconSize(QSize(18, 18))
    for key, label, hex_value in COLOR_PRESETS:
        combo.addItem(color_swatch_icon(hex_value), tr(label, language), key)
    combo.setCurrentIndex(max(0, combo.findData(selected)))
    return combo


def confirm_change(
    parent: QWidget, title: str, question: str, details: str, confirm_label: str,
    language: str = "ja",
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
    cancel.setText(tr("キャンセル", language))
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
        self.setToolTip(tr("ドラッグしてフェーズの順番を変更できます。", card.owner.language))
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
            "background-color: palette(base); border-radius: 8px; margin: 2px; }"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._header_click_surfaces: list[QWidget] = []

        # The entire header is a toggle target; drag/reorder controls remain independent.
        self.header_widget = QWidget(self)
        self.header_widget.setObjectName("phase_header")
        self.header_widget.setStyleSheet(
            "QWidget#phase_header { background-color: palette(window); "
            "border-bottom: 1px solid palette(mid); "
            "border-top-left-radius: 7px; border-top-right-radius: 7px; }"
        )
        header = QHBoxLayout(self.header_widget)
        header.setContentsMargins(12, 10, 12, 10)
        header.setSpacing(9)
        self.drag_handle = PhaseDragHandle(self)
        # Dragging remains mouse-operated and is not part of the Tab sequence.
        self.drag_handle.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.title = QLabel(self.header_widget)
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        heading_font = self.title.font()
        heading_font.setBold(True)
        heading_font.setPointSize(max(13, heading_font.pointSize() + 3))
        self.title.setFont(heading_font)
        self.summary = QLabel(self.header_widget)
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet("color: palette(window-text); font-weight: 500;")
        caption = QVBoxLayout()
        caption.setSpacing(3)
        caption.addWidget(self.title)
        caption.addWidget(self.summary)
        self.move_up = QToolButton(self.header_widget)
        self.move_up.setText("↑")
        self.move_up.setToolTip(tr("フェーズを上に移動します。", owner.language))
        self.move_down = QToolButton(self.header_widget)
        self.move_down.setText("↓")
        self.move_down.setToolTip(tr("フェーズを下に移動します。", owner.language))
        self.expand_button = QToolButton(self.header_widget)
        self.expand_button.setText("∨")
        self.expand_button.setToolTip(tr("フェーズの設定欄を開閉します。", owner.language))
        self.expand_button.setAccessibleName(tr("フェーズ設定の開閉", owner.language))
        self.expand_button.setFixedSize(32, 32)
        self.expand_button.setCheckable(True)
        for control in (self.move_up, self.move_down, self.expand_button):
            control.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.expand_button.toggled.connect(self._toggle_expanded)
        self.move_up.clicked.connect(lambda: owner._shift_card(self, -1))
        self.move_down.clicked.connect(lambda: owner._shift_card(self, 1))
        header.addWidget(self.drag_handle)
        header.addLayout(caption, 1)
        header.addWidget(self.move_up)
        header.addWidget(self.move_down)
        header.addWidget(self.expand_button)
        outer.addWidget(self.header_widget)

        self.body = QWidget(self)
        self.body.setObjectName("phase_body")
        self.body.setStyleSheet(
            "QWidget#phase_body { background-color: palette(base); "
            "border-bottom-left-radius: 7px; border-bottom-right-radius: 7px; }"
        )
        fields = QGridLayout(self.body)
        fields.setContentsMargins(16, 12, 16, 14)
        fields.setHorizontalSpacing(18)
        fields.setVerticalSpacing(9)
        fields.setColumnStretch(0, 1)
        fields.setColumnStretch(1, 1)

        def field(row: int, col: int, label: str, editor: QWidget) -> None:
            area = QWidget(self.body)
            column = QVBoxLayout(area)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(3)
            label_widget = QLabel(tr(label, owner.language), area)
            column.addWidget(label_widget)
            column.addWidget(editor)
            fields.addWidget(area, row, col)


        self.name = QLineEdit(str(values["name"]), self.body)
        self.name.setMaxLength(40)
        self.name.setPlaceholderText(tr("フェーズ名", owner.language))
        field(0, 0, "フェーズ名", self.name)

        self.minutes = NoWheelSpinBox(self.body)
        self.minutes.setRange(1, 240)
        self.minutes.setSuffix(tr(" 分", owner.language))
        self.minutes.setValue(int(values["minutes"]))
        field(0, 1, "時間", self.minutes)

        self.color = color_combo(self.body, values["color"], owner.language)
        field(1, 0, "メイン色", self.color)

        secondary = QWidget(self.body)
        secondary_layout = QHBoxLayout(secondary)
        secondary_layout.setContentsMargins(0, 0, 0, 0)
        self.gradient = QCheckBox("ON", secondary)
        self.gradient.setToolTip(tr("グラデーション", owner.language))
        self.gradient.setChecked(bool(values["gradient"]))
        self.gradient_end = color_combo(secondary, values["gradient_end"], owner.language)
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
        field(2, 1, "不透明度", opacity_row)

        self.simple = QCheckBox("Simple", self.body)
        self.simple.setChecked(bool(values["simple"]))
        field(3, 0, "表示モード", self.simple)

        window_options = QWidget(self.body)
        window_layout = QHBoxLayout(window_options)
        window_layout.setContentsMargins(0, 0, 0, 0)
        window_layout.setSpacing(14)
        self.topmost = QCheckBox(tr("最前面に表示", owner.language), window_options)
        self.topmost.setChecked(bool(values["topmost"]))
        self.hidden = QCheckBox(tr("非表示", owner.language), window_options)
        self.hidden.setToolTip(tr("このフェーズ中はタイマー表示のみを非表示にします。", owner.language))
        self.hidden.setChecked(bool(values["hidden"]))
        window_layout.addWidget(self.topmost)
        window_layout.addWidget(self.hidden)
        window_layout.addStretch()
        field(3, 1, "ウィンドウ", window_options)

        self.position = NoWheelComboBox(self.body)
        for label, value in POSITIONS:
            self.position.addItem(tr(label, owner.language), value)
        self.position.setCurrentIndex(max(0, self.position.findData(values["position"])))
        field(4, 0, "表示位置", self.position)

        delete_area = QWidget(self.body)
        delete_layout = QHBoxLayout(delete_area)
        delete_layout.setContentsMargins(0, 0, 0, 0)
        delete_layout.addStretch()
        self.delete_button = QPushButton(tr("削除", owner.language), delete_area)
        self.delete_button.setFixedSize(54, 26)
        self.delete_button.setStyleSheet(
            "QPushButton { background-color: #F9EAEC; color: #964650; "
            "border: 1px solid #DDB9BE; border-radius: 5px; "
            "padding: 0; font-weight: 500; } "
            "QPushButton:hover { background-color: #F3DBDF; color: #853942; } "
            "QPushButton:pressed { background-color: #EBC9CE; }"
        )
        self.delete_button.setToolTip(tr("フェーズを削除します。確認画面が表示されます。", owner.language))
        self.delete_button.clicked.connect(lambda: owner._confirm_delete_card(self))
        delete_layout.addWidget(self.delete_button)
        fields.addWidget(delete_area, 4, 1)

        # Keep editing with the mouse and typing after a click, but let Tab
        # navigate between phase headers and the dialog's main controls only.
        for control in (
            self.name, self.minutes, self.color, self.gradient,
            self.gradient_end, self.size, self.opacity, self.simple,
            self.topmost, self.hidden, self.position, self.delete_button,
        ):
            control.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        outer.addWidget(self.body)
        self.body.hide()
        # Only the header toggles the accordion. The body stays a passive editor.
        self._header_click_surfaces.extend(
            (self.header_widget, self.title, self.summary)
        )
        for surface in self._header_click_surfaces:
            surface.setCursor(Qt.CursorShape.PointingHandCursor)
            surface.installEventFilter(self)
        for widget in (
            self.name, self.minutes, self.color, self.gradient, self.gradient_end,
            self.size, self.opacity, self.simple, self.position, self.topmost,
            self.hidden,
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
            "hidden": self.hidden.isChecked(),
        }

    def _refresh_summary(self) -> None:
        self.title.setText(self.name.text() or tr("（名前未入力）", self.owner.language))
        colors = dict((key, tr(label, self.owner.language)) for key, label, _hex in COLOR_PRESETS)
        positions = dict((value, tr(label, self.owner.language)) for label, value in POSITIONS)
        main = colors.get(self.color.currentData(), "?")
        secondary = (
            f" → {colors.get(self.gradient_end.currentData(), '?')}"
            if self.gradient.isChecked() else ""
        )
        mode = "Simple" if self.simple.isChecked() else tr("標準", self.owner.language)
        front = tr("最前面ON" if self.topmost.isChecked() else "最前面OFF", self.owner.language)
        visibility = f" · {tr('非表示', self.owner.language)}" if self.hidden.isChecked() else ""
        self.summary.setText(
            f"{self.minutes.value()}{tr(' 分', self.owner.language).strip() if self.owner.language == 'ja' else ' min'} · {main}{secondary} · "
            f"{mode} · {positions.get(self.position.currentData(), '?')} · "
            f"{front}{visibility}"
        )

    def _changed(self, *_args) -> None:
        self._refresh_summary()
        self.owner._notify_change()

    def _toggle_expanded(self, enabled: bool) -> None:
        self.body.setVisible(enabled)
        self.expand_button.setText("∧" if enabled else "∨")
        if hasattr(self.owner, "close_button"):
            self.owner._set_tab_order()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API
        # Limit toggling to header text/background; inputs remain independent.
        if (
            watched in self._header_click_surfaces
            and event.type() == QEvent.Type.MouseButtonRelease
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self.expand_button.toggle()
            return True
        return super().eventFilter(watched, event)

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
    skip_requested = Signal()
    previous_requested = Signal()
    pause_toggle = Signal()
    initialize_requested = Signal()
    language_changed = Signal(str)
    notifications_changed = Signal(bool)
    update_requested = Signal()

    def __init__(
        self, parent, timer: FocusTimer, language: str = "ja",
        notifications_enabled: bool = True,
    ) -> None:
        super().__init__(parent)
        self.language = language if language in LANGUAGES else "ja"
        self.setWindowTitle(f"FocusLoop - {tr('設定', self.language)}")
        self.resize(850, 690)
        self.setMinimumSize(660, 440)
        self.result_phases: tuple[PhaseConfig, ...] | None = None
        self._rendering = False
        self._paused = timer.paused
        self.language_label = QLabel(tr("言語", self.language), self)
        self.language_combo = NoWheelComboBox(self)
        self.language_combo.setObjectName("language_combo")
        self.language_combo.addItem("日本語", "ja")
        self.language_combo.addItem("English", "en")
        self.language_combo.setCurrentIndex(self.language_combo.findData(self.language))
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        language_row = QHBoxLayout()
        language_row.addWidget(self.language_label)
        language_row.addWidget(self.language_combo)
        self.notifications_checkbox = QCheckBox(tr("通知する", self.language), self)
        self.notifications_checkbox.setObjectName("notifications_checkbox")
        self.notifications_checkbox.setChecked(notifications_enabled)
        self.notifications_checkbox.toggled.connect(self.notifications_changed.emit)
        language_row.addWidget(self.notifications_checkbox)
        language_row.addStretch()
        self.version_label = QLabel(updates.VERSION, self)
        self.version_label.setObjectName("version_label")
        language_row.addWidget(self.version_label)
        self.update_button = QPushButton(tr("更新を確認", self.language), self)
        self.update_button.setObjectName("update_button")
        self.update_button.clicked.connect(self.update_requested.emit)
        language_row.addWidget(self.update_button)
        self.loop_label = QLabel(f"LOOP {timer.loop_number:02d}", self)
        self.pause_button = QPushButton(self)
        self.pause_button.setObjectName("pause_button")
        self.set_pause_state(timer.paused)
        self.pause_button.clicked.connect(lambda: self.pause_toggle.emit())
        loop_reset = QPushButton(tr("ループ数をリセット", self.language), self)
        loop_reset.setObjectName("loop_reset_button")
        self.loop_reset_button = loop_reset
        loop_reset.clicked.connect(lambda: self.loop_reset.emit())
        timer_reset = QPushButton(tr("現在のフェーズをリセット", self.language), self)
        timer_reset.setObjectName("timer_reset_button")
        self.timer_reset_button = timer_reset
        timer_reset.clicked.connect(lambda: self.timer_reset.emit())
        self.previous_button = QPushButton(tr("前のフェーズへ", self.language), self)
        self.previous_button.setObjectName("previous_button")
        self.previous_button.clicked.connect(lambda: self.previous_requested.emit())
        self.skip_button = QPushButton(tr("次のフェーズへ", self.language), self)
        self.skip_button.setObjectName("skip_button")
        self.skip_button.clicked.connect(lambda: self.skip_requested.emit())

        self.cards_container = QWidget(self)
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(5, 5, 5, 5)
        self.cards_layout.setSpacing(9)
        self.cards_layout.addStretch()
        self.cards: list[PhaseCard] = []
        self.scroll = QScrollArea(self)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setWidget(self.cards_container)
        self._render_cards([asdict(phase) for phase in timer.phases], timer.phase_index)

        add_button = QPushButton(tr("＋ フェーズを追加", self.language), self)
        self.add_button = add_button
        add_button.clicked.connect(self._add_phase)
        self.note_text = (
            "設定は即時反映・保存されます。⠿をドラッグするか、↑↓で並べ替えられます。"
            "順番・分数を変更すると、先頭から再スタートします。"
        )
        note = QLabel(tr(self.note_text, self.language), self)
        self.note_label = note
        note.setWordWrap(True)

        initialize = QPushButton(tr("設定初期化", self.language), self)
        self.initialize_button = initialize
        initialize.setObjectName("initialize_button")
        initialize.setToolTip(tr("設定とタイマーを初期値に戻します。", self.language))
        initialize.clicked.connect(self._confirm_initialize)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=self)
        self.close_button = buttons.button(QDialogButtonBox.StandardButton.Close)
        self.close_button.setText(tr("閉じる", self.language))
        buttons.rejected.connect(self.reject)
        footer = QHBoxLayout()
        footer.setSpacing(6)
        footer.addWidget(self.pause_button)
        footer.addWidget(self.previous_button)
        footer.addWidget(self.skip_button)
        footer.addWidget(timer_reset)
        footer.addWidget(loop_reset)
        footer.addWidget(self.loop_label)
        footer.addStretch(1)

        # Keep the final two buttons tightly grouped at the far right,
        # with the same spacing as the timer controls on the left.
        right_actions = QHBoxLayout()
        right_actions.setContentsMargins(0, 0, 0, 0)
        right_actions.setSpacing(6)
        right_actions.addWidget(initialize)
        right_actions.addWidget(buttons)
        footer.addLayout(right_actions)

        layout = QVBoxLayout(self)
        layout.addLayout(language_row)
        layout.addWidget(self.scroll, 1)
        layout.addWidget(add_button)
        layout.addWidget(note)
        layout.addLayout(footer)
        self._set_button_cursors()
        self._set_tab_order()

    def _set_tab_order(self) -> None:
        """Follow the visible top → phase headers → footer sequence.

        Reapply after cards are rebuilt or reordered. Qt automatically skips
        hidden or disabled controls; phase-body editors use ClickFocus.
        """
        controls = [
            self.language_combo,
            self.notifications_checkbox,
            self.update_button,
        ]
        for card in self.cards:
            controls.extend((card.move_up, card.move_down, card.expand_button))
        controls.extend((
            self.add_button,
            self.pause_button,
            self.previous_button,
            self.skip_button,
            self.timer_reset_button,
            self.loop_reset_button,
            self.initialize_button,
            self.close_button,
        ))
        for control in controls:
            control.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        for current, following in zip(controls, controls[1:]):
            QWidget.setTabOrder(current, following)

    def set_update_status(self, busy: bool, text: str | None = None) -> None:
        self.update_button.setEnabled(not busy)
        self.update_button.setText(text or tr("更新を確認", self.language))

    def _render_cards(
        self, rows: list[dict], expanded_index: int = 0,
        expanded_indices: set[int] | None = None,
    ) -> None:
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
            open_indices = (
                {expanded_index} if expanded_indices is None else expanded_indices
            )
            for index in open_indices:
                if 0 <= index < len(self.cards):
                    self.cards[index].expand_button.setChecked(True)
            self._update_move_buttons()
        finally:
            self._rendering = False
            self._set_button_cursors()
            if hasattr(self, "close_button"):
                self._set_tab_order()

    def _set_button_cursors(self) -> None:
        for button in self.findChildren(QAbstractButton):
            button.setCursor(Qt.CursorShape.PointingHandCursor)

    def _update_move_buttons(self) -> None:
        for i, card in enumerate(self.cards):
            card.move_up.setEnabled(i > 0)
            card.move_down.setEnabled(i < len(self.cards) - 1)

    def _reorder_cards(self, source: PhaseCard, target: PhaseCard) -> None:
        if source is target or source not in self.cards or target not in self.cards:
            return
        destination = self.cards.index(target)
        self.cards.remove(source)
        self.cards.insert(destination, source)
        self.cards_layout.removeWidget(source)
        self.cards_layout.insertWidget(self.cards.index(source), source)
        self._update_move_buttons()
        self._set_tab_order()
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
                PhaseConfig(**{**card.snapshot(), "name": card.snapshot()["name"].strip()})
                for card in self.cards
            )
        except ValueError:
            return
        if force_restart or phases != self.result_phases:
            self.result_phases = phases
            self.changed.emit(self, force_restart)

    def _confirm_delete_card(self, card: PhaseCard) -> None:
        if len(self.cards) <= 1:
            QMessageBox.information(self, "FocusLoop", tr("フェーズは最低1つ必要です。", self.language))
            return
        name = card.name.text()
        question = f"Delete \"{name}\"?" if self.language == "en" else f"「{name}」を削除しますか？"
        if confirm_change(
            self, f"FocusLoop - {'Delete phase' if self.language == 'en' else 'フェーズ削除'}",
            question, tr("この操作は取り消せません。", self.language),
            tr("削除する", self.language), self.language,
        ):
            remaining = [other for other in self.cards if other is not card]
            rows = [other.snapshot() for other in remaining]
            expanded = {
                i for i, other in enumerate(remaining)
                if other.expand_button.isChecked()
            }
            self._render_cards(rows, expanded_indices=expanded)
            self._notify_change(force_restart=True)

    def _add_phase(self) -> None:
        rows = [card.snapshot() for card in self.cards]
        expanded = {
            i for i, card in enumerate(self.cards) if card.expand_button.isChecked()
        }
        rows.append(asdict(PhaseConfig("新しいフェーズ", 5, color="sky")))
        expanded.add(len(rows) - 1)
        self._render_cards(rows, expanded_indices=expanded)
        self._notify_change(force_restart=True)
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())

    def _confirm_initialize(self) -> None:
        details = (
            "フェーズ・色・サイズ・表示位置・表示モード・最前面・ループ数を初期値に戻し、"
            "作業中45:00からタイマーを再開します。この操作は取り消せません。"
        )
        if confirm_change(
            self, f"FocusLoop - {tr('設定初期化', self.language)}",
            tr("すべての設定を初期化しますか？", self.language),
            tr(details, self.language),
            tr("設定初期化する", self.language), self.language,
        ):
            self.initialize_requested.emit()

    def restore_defaults(self, phases: tuple[PhaseConfig, ...], loop_number: int) -> None:
        self._render_cards([asdict(phase) for phase in phases])
        self.result_phases = phases
        self.set_loop_number(loop_number)
        self.set_pause_state(False)

    def set_loop_number(self, number: int) -> None:
        self.loop_label.setText(f"LOOP {number:02d}")

    def set_notifications_enabled(self, enabled: bool) -> None:
        """Refresh the checkbox without issuing another settings change."""
        if self.notifications_checkbox.isChecked() != enabled:
            self.notifications_checkbox.blockSignals(True)
            try:
                self.notifications_checkbox.setChecked(enabled)
            finally:
                self.notifications_checkbox.blockSignals(False)

    def set_pause_state(self, paused: bool) -> None:
        self._paused = paused
        self.pause_button.setText(tr("再開" if paused else "一時停止", self.language))

    def _on_language_changed(self, _index: int) -> None:
        language = self.language_combo.currentData()
        if language == self.language or language not in LANGUAGES:
            return
        rows = [card.snapshot() for card in self.cards]
        expanded = {i for i, card in enumerate(self.cards) if card.expand_button.isChecked()}
        self.language = language
        self.setWindowTitle(f"FocusLoop - {tr('設定', language)}")
        self.language_label.setText(tr("言語", language))
        self.notifications_checkbox.setText(tr("通知する", language))
        if self.update_button.isEnabled():
            self.update_button.setText(tr("更新を確認", language))
        self.loop_reset_button.setText(tr("ループ数をリセット", language))
        self.timer_reset_button.setText(tr("現在のフェーズをリセット", language))
        self.previous_button.setText(tr("前のフェーズへ", language))
        self.skip_button.setText(tr("次のフェーズへ", language))
        self.add_button.setText(tr("＋ フェーズを追加", language))
        self.note_label.setText(tr(self.note_text, language))
        self.initialize_button.setText(tr("設定初期化", language))
        self.initialize_button.setToolTip(tr("設定とタイマーを初期値に戻します。", language))
        self.close_button.setText(tr("閉じる", language))
        self.set_pause_state(self._paused)
        self._render_cards(rows, expanded_indices=expanded)
        self.language_changed.emit(language)



class FocusLoopApp(QObject):
    update_checked = Signal(object, object)
    update_progress = Signal(int, int)
    update_prepared = Signal(object, object)

    def __init__(self, qt_app: QApplication) -> None:
        super().__init__()
        self.qt_app = qt_app
        self.qt_app.setQuitOnLastWindowClosed(False)
        self.settings = QSettings("FocusLoop", "FocusLoop")
        self._update_busy = False
        self.update_checked.connect(self._on_update_checked)
        self.update_progress.connect(self._on_update_progress)
        self.update_prepared.connect(self._on_update_prepared)
        stored_language = str(self.settings.value("language", "ja"))
        self.language = stored_language if stored_language in LANGUAGES else "ja"
        self.notifications_enabled = self.settings.value(
            "notifications_enabled", True, type=bool
        )
        old_work = _int_setting(self.settings, "work_minutes", 45, 1, 240)
        old_break = _int_setting(self.settings, "break_minutes", 15, 1, 240)
        legacy_font_size = (
            _int_setting(self.settings, "font_size", DEFAULT_FONT_SIZE, MIN_FONT_SIZE, MAX_FONT_SIZE)
            if self.settings.contains("font_size") else None
        )
        old_position = (
            str(self.settings.value("position"))
            if self.settings.contains("position") else None
        )
        if old_position is not None and old_position not in POSITION_VALUES:
            old_position = None
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
        self._overlay_started = False
        self.tray = QSystemTrayIcon(clock_icon(), qt_app)
        self.tray.setToolTip("FocusLoop")
        self.menu = QMenu()
        self.status_action = self.menu.addAction("")
        self.status_action.setEnabled(False)
        self.menu.addSeparator()

        self.pause_action = self.menu.addAction(tr("一時停止", self.language))
        self.pause_action.triggered.connect(self.toggle_pause)
        self.previous_action = self.menu.addAction(tr("前のフェーズへ", self.language))
        self.previous_action.triggered.connect(self.previous)
        self.skip_action = self.menu.addAction(tr("次のフェーズへ", self.language))
        self.skip_action.triggered.connect(self.skip)
        self.reset_action = self.menu.addAction(tr("現在のフェーズをリセット", self.language))
        self.reset_action.triggered.connect(self.reset)
        self.loop_reset_action = self.menu.addAction(tr("ループ数をリセット", self.language))
        self.loop_reset_action.triggered.connect(self._reset_loop_count)
        self.menu.addSeparator()

        self.settings_action = self.menu.addAction(tr("設定", self.language))
        self.settings_action.triggered.connect(self.show_settings)
        self.menu.addSeparator()
        self.quit_action = self.menu.addAction(tr("終了", self.language))
        self.quit_action.triggered.connect(self.close)

        # Handle context clicks ourselves to keep the entire menu above the taskbar.
        self.tray.activated.connect(self._tray_activated)
        self.settings_dialog: SettingsDialog | None = None
        self.last_display = None
        self.qt_timer = QTimer(qt_app)
        self.qt_timer.setInterval(200)
        self.qt_timer.timeout.connect(self.update)
        # A separate light-weight timer animates only the Modern ring.
        self.ring_timer = QTimer(qt_app)
        self.ring_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.ring_timer.setInterval(33)  # <= 30fps; actual repaints are angle-gated.
        self.ring_timer.timeout.connect(self._animate_ring)

    def start(self) -> bool:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            QMessageBox.critical(
                None, "FocusLoop", tr("システムトレイを利用できないため、起動できません。", self.language)
            )
            return False
        self.tray.show()
        self._overlay_started = True
        self.update()
        self.qt_timer.start()
        return True

    def update(self) -> None:
        switched = self.timer_model.tick()
        remaining = self.timer_model.remaining_seconds()
        display = f"{remaining // 60:02d}:{remaining % 60:02d}"
        phase = self.timer_model.current_phase
        self.overlay.set_clock(
            display, phase, self.timer_model.remaining_ratio(), self.timer_model.loop_number
        )
        # Hidden is a phase display setting, not a timer pause: the model and
        # tray keep updating. Do not show a window before start() is called.
        if phase.hidden and self.overlay.isVisible():
            self.overlay.hide()
        elif not phase.hidden and self._overlay_started and not self.overlay.isVisible():
            self.overlay.show()
            self.overlay.reposition()
        if self.timer_model.loop_number != self._last_loop_saved:
            self._save_loop_number()
        state = (display, phase, self.timer_model.paused, self.language)
        if state != self.last_display:
            title = phase.name
            if self.timer_model.paused:
                title += f" ({tr('一時停止', self.language)})"
            self.status_action.setText(f"{title}  {display}")
            self.pause_action.setText(tr("再開" if self.timer_model.paused else "一時停止", self.language))
            if self.settings_dialog is not None:
                self.settings_dialog.set_pause_state(self.timer_model.paused)
            self.tray.setToolTip(f"FocusLoop - {title} {display}")
            self.last_display = state
        if switched:
            self._notify_phase_change()
        self._sync_ring_animation()

    def _sync_ring_animation(self) -> None:
        """Animate only while Modern is visible and counting down."""
        active = (
            self.overlay.isVisible()
            and not self.timer_model.paused
            and not self.timer_model.current_phase.simple
        )
        if active and not self.ring_timer.isActive():
            self.ring_timer.start()
        elif not active and self.ring_timer.isActive():
            self.ring_timer.stop()

    def _animate_ring(self) -> None:
        """Advance visual progress from the monotonic deadline, not frame counts."""
        if (
            self.timer_model.paused
            or self.timer_model.current_phase.simple
            or not self.overlay.isVisible()
        ):
            self.ring_timer.stop()
            return
        self.overlay.set_ring_progress(self.timer_model.remaining_ratio())

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
        self.settings.setValue("language", self.language)
        self.notifications_enabled = True
        self.settings.setValue("notifications_enabled", self.notifications_enabled)
        self.settings.setValue("phases_json", phases_to_json(phases))
        self.settings.setValue("loop_number", 1)
        self.settings.sync()

        if self.settings_dialog is not None:
            self.settings_dialog.restore_defaults(phases, 1)
            self.settings_dialog.set_notifications_enabled(self.notifications_enabled)
        self.update()

    def _notify_phase_change(self) -> None:
        """Send a Windows system-tray notification at each phase transition."""
        if not self.notifications_enabled:
            return
        phase = self.timer_model.current_phase
        name = phase.name
        message = (
            f'Started "{name}" ({phase.minutes} min).'
            if self.language == "en"
            else f"「{name}」を開始しました（{phase.minutes}分）。"
        )
        self.tray.showMessage(
            "FocusLoop",
            message,
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

    def previous(self) -> None:
        self.timer_model.previous()
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

        dialog = SettingsDialog(
            None, self.timer_model, self.language, self.notifications_enabled
        )
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        dialog.changed.connect(self._apply_settings)
        dialog.loop_reset.connect(self._reset_loop_count)
        dialog.timer_reset.connect(self.reset)
        dialog.skip_requested.connect(self.skip)
        dialog.previous_requested.connect(self.previous)
        dialog.pause_toggle.connect(self.toggle_pause)
        dialog.initialize_requested.connect(self._initialize_defaults)
        dialog.language_changed.connect(self._set_language)
        dialog.notifications_changed.connect(self._set_notifications_enabled)
        dialog.update_requested.connect(self.check_for_updates)
        dialog.finished.connect(self._settings_closed)
        self.settings_dialog = dialog
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def check_for_updates(self) -> None:
        """Check GitHub Releases without blocking the timer or the settings UI."""
        if self._update_busy:
            return
        self._update_busy = True
        if self.settings_dialog is not None:
            self.settings_dialog.set_update_status(True, tr("確認中...", self.language))

        def check() -> None:
            try:
                self.update_checked.emit(updates.check_latest_release(), None)
            except Exception as exc:
                self.update_checked.emit(None, str(exc))

        threading.Thread(target=check, name="FocusLoop-update-check", daemon=True).start()

    @Slot(object, object)
    def _on_update_checked(self, release: object, error: object) -> None:
        self._update_busy = False
        dialog = self.settings_dialog
        if dialog is None:
            return
        dialog.set_update_status(False)
        english = self.language == "en"
        if error is not None:
            QMessageBox.warning(
                dialog, "FocusLoop",
                f"Could not check for updates:\n{error}" if english
                else f"更新を確認できませんでした。\n{error}",
            )
            return
        if release is None:
            QMessageBox.information(
                dialog, "FocusLoop",
                "FocusLoop is up to date." if english else "FocusLoopは最新バージョンです。",
            )
            return
        if not updates.can_self_update():
            QMessageBox.information(
                dialog, "FocusLoop",
                (f"Version {release.version} is available. Self-updates require "
                 f"the packaged Windows app.\n{updates.RELEASES_PAGE}")
                if english else
                (f"新しいバージョン {release.version} を利用できます。自動更新はWindows配布版のみ対応しています。"
                 f"\n{updates.RELEASES_PAGE}"),
            )
            return
        confirmation = (
            f"Update FocusLoop {updates.VERSION} to {release.version}?\n"
            "The app will close and restart when the download is ready."
            if english else
            f"FocusLoop {updates.VERSION} から {release.version} に更新しますか？\n"
            "ダウンロード後、アプリを終了して自動的に再起動します。"
        )
        answer = QMessageBox.question(
            dialog, "FocusLoop", confirmation,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._update_busy = True
        dialog.set_update_status(True, tr("ダウンロード中...", self.language))

        def download() -> None:
            try:
                prepared = updates.prepare_update(
                    release, progress=lambda done, total: self.update_progress.emit(done, total)
                )
                self.update_prepared.emit(prepared, None)
            except Exception as exc:
                self.update_prepared.emit(None, str(exc))

        threading.Thread(target=download, name="FocusLoop-update-download", daemon=True).start()

    @Slot(int, int)
    def _on_update_progress(self, received: int, total: int) -> None:
        if self.settings_dialog is not None and total > 0:
            percent = min(100, int(received * 100 / total))
            self.settings_dialog.set_update_status(
                True, f"{tr('ダウンロード中...', self.language)} {percent}%"
            )

    @Slot(object, object)
    def _on_update_prepared(self, prepared: object, error: object) -> None:
        self._update_busy = False
        dialog = self.settings_dialog
        if dialog is None:
            if prepared is not None:
                updates.discard_prepared_update(prepared)
            return
        dialog.set_update_status(False)
        if error is not None:
            QMessageBox.warning(
                dialog, "FocusLoop",
                f"Update download failed:\n{error}" if self.language == "en"
                else f"更新ファイルを準備できませんでした。\n{error}",
            )
            return
        try:
            updates.launch_updater(prepared)
        except Exception as exc:
            updates.discard_prepared_update(prepared)
            QMessageBox.warning(
                dialog, "FocusLoop",
                f"Could not start update:\n{exc}" if self.language == "en"
                else f"更新処理を開始できませんでした。\n{exc}",
            )
            return
        self.settings.sync()
        self.close()

    def _set_notifications_enabled(self, enabled: bool) -> None:
        if enabled == self.notifications_enabled:
            return
        self.notifications_enabled = enabled
        self.settings.setValue("notifications_enabled", enabled)
        self.settings.sync()

    def _set_language(self, language: str) -> None:
        if language not in LANGUAGES or language == self.language:
            return
        self.language = language
        self.settings.setValue("language", language)
        self.settings.sync()
        self.previous_action.setText(tr("前のフェーズへ", language))
        self.skip_action.setText(tr("次のフェーズへ", language))
        self.reset_action.setText(tr("現在のフェーズをリセット", language))
        self.loop_reset_action.setText(tr("ループ数をリセット", language))
        self.settings_action.setText(tr("設定", language))
        self.quit_action.setText(tr("終了", language))
        self.last_display = None
        self.update()

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
        self.ring_timer.stop()
        self._overlay_started = False
        self.qt_timer.stop()
        if self.settings_dialog is not None:
            self.settings_dialog.close()
        self.overlay.close()
        self.tray.hide()
        self.qt_app.quit()
