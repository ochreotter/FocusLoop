# FocusLoop 現行仕様・Issue回帰テスト対応表

この表は2026-11-23のIssue #5〜#45を検査した結果。**後続Issueで上書きされた古いUI要件を再検証しない**。それ以外の操作・保存・描画・CIを、PythonロジックテストとWindows Qtオフスクリーンテストで確認する。

## Issue別チェック一覧

| Issue | 現行の受け入れ条件・改訂 | 主な検証 |
| --- | --- | --- |
| #5 | 作業45分→休憩15分、一時停止・再開・スキップ・再スタート、monotonicな遅延復帰 | `tests/test_timer.py`, `tests/test_issue_regression.py` |
| #6 | 透明・クリック透過・フォーカス非取得。数字のみ表示は#16→#43のSimpleに変更 | `tests/ui/test_app_ui.py`, `tests/ui/test_issue_regression.py` |
| #7 | フェーズ追加削除・名前・時間・並べ替え・保存復元。テーブルは#45でカードに変更 | `tests/ui/test_app_ui.py`, `tests/ui/test_issue_regression.py` |
| #8 | 色・透過率。6色は#25でブラックを追加して7色 | `tests/test_timer.py`, `tests/test_issue_regression.py`, `tests/ui/test_app_ui.py` |
| #9 | トレイ左クリック設定表示・右クリックメニューと画面内配置 | `tests/test_geometry.py`, `tests/ui/test_app_ui.py` |
| #10 | 即時反映、QSettings保存、旧バージョン移行 | `tests/ui/test_app_ui.py`, `tests/ui/test_issue_regression.py` |
| #11 | 自動フェーズ切替と手動スキップの通知 | `tests/ui/test_app_ui.py`（通知APIの呼出し）。実通知は実機確認 |
| #12 | Clockトレイ/EXEアイコンとICO生成 | `tests/ui/test_app_ui.py` |
| #13 | Linuxロジック・Windows UI CI、mainでEXE生成 | `tests/test_issue_regression.py`（workflow静的検査） |
| #14 | 日本語UI・通知・デフォルトフェーズ名 | `tests/ui/test_app_ui.py`, `tests/ui/test_issue_regression.py` |
| #15 | 8〜300pt/フェーズ（#53で上限拡張）、表示域内への調整、旧font_size移行。スライダーは#21 | `tests/test_timer.py`, `tests/ui/test_app_ui.py` |
| #16 | 標準の円形UIとSimple数字表示。共通切替は#43でフェーズ別チェックへ変更 | `tests/ui/test_app_ui.py`, `tests/ui/test_issue_regression.py` |
| #17 | 進捗リング・背景トラック・透明度・一時停止との両立。回転方向は#28に従う | `tests/ui/test_app_ui.py`, `tests/ui/test_issue_regression.py` |
| #18 | LOOP表示・永続化・リセット・長時間経過の周回加算 | `tests/test_timer.py`, `tests/ui/test_app_ui.py` |
| #19 | グラデーションON/OFF、サブ色、Modernリング、透過率 | `tests/ui/test_app_ui.py`, `tests/ui/test_issue_regression.py` |
| #21 | 「サイズ」スライダー8〜300pt（#53）。横長テーブル列は#45でカード内の項目へ変更 | `tests/ui/test_app_ui.py` |
| #23 | メイン色とサブ色/グラデーション、チェック→色選択。列配置は#45でカード内へ変更 | `tests/ui/test_app_ui.py`, `tests/ui/test_issue_regression.py` |
| #24 | 白・黒を含むスウォッチ表示 | `tests/ui/test_app_ui.py` |
| #25 | 7色、ブラックの保存・反映 | `tests/test_timer.py`, `tests/test_issue_regression.py` |
| #26 | 設定から現在フェーズだけをリセット | `tests/ui/test_app_ui.py`, `tests/ui/test_issue_regression.py` |
| #27 | 中央表示。共通の表示位置は#43でフェーズ別に変更 | `tests/ui/test_app_ui.py` |
| #28 | 12時起点・時計回りに色が消えるリング | `tests/ui/test_app_ui.py` |
| #29 | 削除ボタンを識別可能にする。赤ベタ配色・旧サイズは#32が上書き | `tests/ui/test_app_ui.py` |
| #30 | 削除確認・キャンセル無変更・最後のフェーズは削除不可 | `tests/ui/test_app_ui.py`, `tests/ui/test_issue_regression.py` |
| #32 | 小さく淡い赤の削除ボタン | `tests/ui/test_app_ui.py` |
| #34 | Node.js 24対応のGitHub Actions v7 | `tests/test_issue_regression.py` |
| #36 | 色別の輪郭補助。輪郭方式は#42のドロップシャドウに上書き | `tests/ui/test_overlay_contrast.py` |
| #38 | 全設定初期化・確認ダイアログ・保存 | `tests/ui/test_app_ui.py`, `tests/ui/test_issue_regression.py` |
| #39 | 設定画面の操作ボタン・チェックをハンドカーソルに | `tests/ui/test_app_ui.py` |
| #41 | ソース全体の重複・責務点検とIssue回帰 | 本表、全テスト、CI |
| #42 | 全7色を色に応じた反対色の2pxドロップシャドウで描画 | `tests/ui/test_overlay_contrast.py` |
| #43 | Simpleチェック・表示位置をフェーズごとに保存/移行/切替 | `tests/ui/test_app_ui.py`, `tests/ui/test_issue_regression.py` |
| #44 | 最前面チェックをフェーズごとに保存/切替、透過維持 | `tests/ui/test_app_ui.py`, `tests/ui/test_issue_regression.py` |
| #45 | 2列のフェーズカード・アコーディオン、要約表示、追加削除・上下/ドラッグ並べ替え | `tests/ui/test_app_ui.py`, `tests/ui/test_issue_regression.py` |
| #53 | 8〜300pt・設定画面で一時停止/再開・Modernの上部にフェーズ名、下部にLOOP | `tests/test_timer.py`, `tests/test_issue_regression.py`, `tests/ui/test_app_ui.py`, `tests/ui/test_overlay_contrast.py` |
| #55 | フェーズ別非表示チェック、切替時の自動再表示、裏側のタイマー・トレイ継続、初期化/保存/旧設定との互換 | `tests/test_timer.py`, `tests/ui/test_app_ui.py` |
| #56 | LOOPと各リセット操作の設定画面フッターへの移動、「設定初期化」への名称変更 | `tests/ui/test_app_ui.py` |

## リファクタリング判断

- **整理**: フェーズ設定のdict変換は `dataclasses.asdict` に統一し、色選択のスウォッチ付きコンボを共有。初期化・削除の確認ダイアログの重複を統合
- **削除**: Signalを転送するだけの中間メソッド、時計アイコンを返すだけのメソッド、スタイル/表示位置の全体共通UIを削除
- **必要な抽象化として維持**: `FocusTimer`（時刻計算）、`Overlay`（描画とウィンドウ属性）、`PhaseCard`（フェーズ入力）、`SettingsDialog`（カードの管理）、`FocusLoopApp`（設定永続化・トレイ）。責務を分離
- **意図的に維持**: `geometry.py`（メニュー位置の純関数）、`icons.py`（トレイ・EXEの共通図柄）、`scripts/generate_icon.py`（ICO書き出し）。単純だがテストやビルドで再利用するため無駄なメソッド化ではない
- **後方互換**: 従来の `phases_json` / `work_minutes` / `break_minutes` / `font_size` / `display_style` / `position` の読み込みを残す。フェーズに固有値がある場合は優先
- **後続Issueを優先**: 上記の旧方式は再導入しない

## CIでの確認方法

- Python構文とロジック: `python -m compileall -q main.py focusloop tests`; `python -m unittest discover -s tests -v`
- Windows Qtオフスクリーン: `QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests/ui -v`
- mainにマージ後はWindows EXEビルドを別途実行

## 実機での確認が必要な範囲

Windowsの実際のZオーダー（他の常駐ウィンドウ・ゲームとの重なり）、タスクバーとの相対配置、マルチモニター、実通知の表示、Windows EXEとSmartScreenの挙動、テーマ別の色の見え方、ドラッグ操作感はCIのオフスクリーンテストだけでは完全には再現できない。
