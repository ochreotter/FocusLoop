# サードパーティーの著作権・ライセンス情報

FocusLoopはMITライセンスのアプリケーションです。Windows配布版には、以下のサードパーティー製ソフトウェアが同梱されます。**FocusLoopのMITライセンスは、これらのライブラリをMITに変更するものではありません。**

## Qt / PySide6 / Shiboken6

- **Qt Framework**: Copyright © The Qt Company Ltd. and other contributors
- **Qt for Python (PySide6 / Shiboken6)**: Copyright © The Qt Company Ltd. and other contributors
- ライセンス: コミュニティ版のLGPLv3等。FocusLoopではLGPLv3に従う利用を想定しています（バンドルされた各モジュール固有の条件が優先します）。
- ライセンス全文: 配布ZIP内の `licenses/LGPL-3.0.txt` と `licenses/GPL-3.0.txt`
- Qt公式: https://www.qt.io/development/open-source-lgpl-obligations
- Qt for Python: https://doc.qt.io/qtforpython-6/
- Qtで使用される第三者コード: https://doc.qt.io/qt-6/licenses-used-in-qt.html

利用者には、LGPL対象のライブラリを改変して使用する権利があります。FocusLoopのWindows配布版は、ライブラリファイルを外部に配置したフォルダー形式で提供します。互換ライブラリへの変更方法は [ライブラリ差し替え手順](docs/library-replacement.md) を参照してください。

**対応するライブラリのソースコード**: Qt公式の条件では、使用したライブラリの対応する完全なソース（未改変でも必要）を提供するか、開発者が管理する提供経路と適切な書面オファーが必要です。第三者サイトのソースへのリンクのみではこの条件を満たしません。公開済みの各Releaseに記載される対応ソースの提供方法を確認してください。

バージョンごとの依存関係は、配布ZIPに同梱する `DEPENDENCIES.txt` を参照してください。Qt自体に取り込まれた第三者コードやDLLについても、対象バージョンの著作権表示および適用ライセンスが優先されます。

## Python

- **CPython**: Copyright © Python Software Foundation and other contributors
- ライセンス: Python Software Foundation License（PSF）
- 参照: https://docs.python.org/3/license.html
- Windows配布版にはPythonランタイムが含まれます。配布物のライセンス情報と依存関係一覧を確認してください。

## PyInstaller

- PyInstallerは配布物を作成するために使用しています。
- PyInstallerのブートローダー等には、GPLv2とブートローダー例外等のライセンスが適用されます。
- 公式ライセンス説明: https://pyinstaller.org/en/stable/license.html
- この例外により、PyInstallerを利用したという理由だけでFocusLoop本体のMITライセンスが変わることはありません。

## 注意事項

この文書はライセンスに関する情報提供であり、個々の配布物について法令・ライセンス上の要件がすべて履行されたことを保証するものではありません。ソフトウェアに含まれるライブラリの実際のバージョン、ライセンス文書、対応ソースの提供方法は、該当するReleaseの配布内容に従います。
