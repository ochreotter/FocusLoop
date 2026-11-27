# Windows版のQt/PySide6ライブラリ差し替え

FocusLoop Windows版は、PyInstallerの**フォルダー形式（onedir）**で配布しています。実行ファイルと同梱ライブラリの分離により、利用者は互換性のある改変版Qt/PySide6ライブラリを使用できます。

## 同梱ファイルの確認

1. `FocusLoop-Windows.zip` を展開し、`FocusLoop/FocusLoop.exe` が入っていることを確認します。
2. `FocusLoop` フォルダーの中には、`_internal` などの依存ライブラリの格納先があります。**EXEだけを別フォルダーへ移動しないでください。**
3. PowerShellでDLLの配置場所を確認できます。

```powershell
Get-ChildItem .\FocusLoop -Recurse -File -Filter 'Qt6*.dll' | Select-Object FullName
Get-ChildItem .\FocusLoop -Recurse -File -Filter 'PySide6*.pyd' | Select-Object FullName
```

実際の配置先はPyInstallerやPySide6のバージョンによって異なるため、上の検索結果を基準にしてください。

## 互換ライブラリに差し替える方法

1. FocusLoopを終了し、実行中のプロセスがないことを確認します。
2. `FocusLoop` フォルダー全体をバックアップします。
3. 同じアーキテクチャ・ABIを持つ改変済みのQt DLL、PySide6拡張モジュールなどを、**検索で確認した元のパスに置き換えます**。Qtプラグインも差し替える場合は、対応するプラグインをセットで変更します。
4. `FocusLoop.exe` を起動し、変更後のライブラリが使えることを確認します。起動に失敗する場合はバックアップを復元します。

ライブラリの互換性・組み合わせ・Windowsのセキュリティ設定によっては起動できない場合があります。元のライブラリファイルを保持し、必要に応じて同じメジャー・マイナーバージョンからビルドしてください。

ライブラリの変更や、その変更をデバッグするためのリバースエンジニアリングをライセンスが認める範囲で行う権利は、FocusLoopによって制限されません。

## ソースコード・ライセンス

Qt/PySide6の著作権表示とライセンスについては ソースツリーの [サードパーティーライセンス](../THIRD_PARTY_NOTICES.md)（配布ZIP内では同じフォルダーの `THIRD_PARTY_NOTICES.md`）を参照してください。使用バージョンは配布物の `DEPENDENCIES.txt` を参照し、対応するソースの提供方法は公開済みReleaseの説明をご確認ください。

- Qt for Pythonのソース: https://code.qt.io/pyside/pyside-setup.git
- Qtソースコード: https://code.qt.io/cgit/qt/
- QtのLGPL遵守条件: https://www.qt.io/development/open-source-lgpl-obligations

上記は技術参考情報です。**これらの第三者サイトへのリンクだけで、配布者が負う対応ソース提供義務を満たすものではありません。**
