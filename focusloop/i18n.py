"""Small, dependency-free Japanese/English UI dictionary.

Persisted phase identifiers and user-authored names never depend on locale.
"""

LANGUAGES = ("ja", "en")

ENGLISH = {
    "言語": "Language",
    "通知する": "Notifications",
    "設定": "Settings",
    "システムトレイを利用できないため、起動できません。":
        "FocusLoop cannot start because the system tray is unavailable.",
    "一時停止": "Pause",
    "再開": "Resume",
    "次のフェーズへ": "Next phase",
    "現在のフェーズをリセット": "Reset current phase",
    "ループ数をリセット": "Reset loop count",
    "設定初期化": "Reset settings",
    "終了": "Quit",
    "閉じる": "Close",
    "キャンセル": "Cancel",
    "フェーズ名": "Phase name",
    "時間": "Duration",
    "メイン色": "Main color",
    "サブ色・グラデーション": "Secondary color / Gradient",
    "サイズ": "Size",
    "透過率": "Opacity",
    "表示モード": "Display mode",
    "ウィンドウ": "Window",
    "最前面に表示": "Always on top",
    "非表示": "Hidden",
    "表示位置": "Position",
    "削除": "Delete",
    "標準": "Standard",
    "最前面ON": "Topmost ON",
    "最前面OFF": "Topmost OFF",
    "（名前未入力）": "(Unnamed phase)",
    "＋ フェーズを追加": "+ Add phase",
    "設定は即時反映・保存されます。⠿をドラッグ、または↑↓で並べ替え。順番・分数の変更時は先頭から再スタートします。":
        "Changes are saved immediately. Drag ⠿ or use ↑↓ to reorder. "
        "Changing phase order or duration restarts from the first phase.",
    "ドラッグして順番を変更": "Drag to reorder phases",
    "上へ移動": "Move up",
    "下へ移動": "Move down",
    "カードを開く／閉じる": "Expand / collapse card",
    "フェーズ設定の開閉": "Toggle phase settings",
    "グラデーション": "Gradient",
    "このフェーズの間はタイマー表示だけを隠す":
        "Hide only the timer overlay during this phase",
    "フェーズを削除（確認あり）": "Delete phase (confirmation required)",
    "設定とタイマーをすべて初期値に戻す":
        "Restore all phase settings and reset the timer",
    "フェーズは最低1つ必要です。": "At least one phase is required.",
    "この操作は取り消せません。": "This action cannot be undone.",
    "削除する": "Delete",
    "すべての設定を初期化しますか？": "Reset all settings?",
    "フェーズ・色・サイズ・表示位置・表示モード・最前面・ループ数を初期値に戻し、作業中45:00からタイマーを再開します。この操作は取り消せません。":
        "Restore the default phases, colors, sizes, positions, display modes, "
        "topmost settings and loop count. The timer restarts at Working 45:00. "
        "This action cannot be undone.",
    "設定初期化する": "Reset settings",
    "ホワイト": "White",
    "ブラック": "Black",
    "ミント": "Mint",
    "スカイブルー": "Sky Blue",
    "アンバー": "Amber",
    "ローズ": "Rose",
    "バイオレット": "Violet",
    "左下": "Bottom left",
    "右下": "Bottom right",
    "左上": "Top left",
    "右上": "Top right",
    "中央": "Center",
    " 分": " min",
}

STANDARD_NAMES = {
    "作業中": "Working",
    "休憩中": "On Break",
    "作業": "Work",
    "休憩": "Break",
    "新しいフェーズ": "New phase",
}
JAPANESE_NAMES = {english: japanese for japanese, english in STANDARD_NAMES.items()}


def translate(text: str, language: str = "ja") -> str:
    """Translate a built-in UI string, leaving unsupported strings unchanged."""
    return ENGLISH.get(text, text) if language == "en" else text


def phase_name(name: str, language: str = "ja") -> str:
    """Only localize known built-in phase names; keep custom names untouched."""
    if language == "en":
        return STANDARD_NAMES.get(name, name)
    return JAPANESE_NAMES.get(name, name)
