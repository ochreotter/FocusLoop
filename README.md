# FocusLoop

Windows向けの、数字だけが画面に浮かぶ集中・休憩タイマー。

- **初期設定は作業45分・休憩15分**。交互に自動で繰り返す。
- **時間は起動中に変更可能**（作業・休憩それぞれ1〜240分）。
- 背景透明・最前面・クリック透過。
- タスクトレイから一時停止/再開、スキップ、リセット、設定、終了。
- 作業/休憩時間、文字サイズ、表示位置は自動保存。

## EXEを使う
GitHubの **Actions → Build Windows EXE → 最新の成功した実行 → Artifacts → FocusLoop-Windows** からZIPをダウンロードして展開、FocusLoop.exeを起動する。Pythonは不要。

## ソースから実行（Windows）
Python 3.11以降で以下を実行。

    python -m venv .venv
    .venv\Scripts\activate
    python -m pip install -r requirements.txt
    python main.py

テスト: `python -m unittest discover -s tests -v`

## 操作
- 作業中は白い数字、休憩中は緑の数字。
- 通知領域のFアイコンを左クリックすると一時停止/再開。
- 右クリックで各種操作と「時間・表示の設定…」を開ける。
- 作業/休憩の時間を変えると現在のフェーズを最初から数え直す。表示だけの変更ではカウントを維持。
- 設定はQtのQSettingsへ保存される。
- ダウンロードするEXEは署名されていないので、Windows SmartScreenで警告が出る場合がある。
- 最初のWindows実機動作は未検証。全画面アプリの一部では最前面表示されない可能性がある。
- 表示先はメインモニターの四隅。数字はクリック透過なので、ドラッグ移動せず設定から位置を変更する。
