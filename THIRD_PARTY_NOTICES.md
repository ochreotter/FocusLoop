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

利用者には、LGPL対象のライブラリを改変して使用する権利があります。FocusLoopのWindows配布版は、ライブラリファイルを外部に配置したフォルダー形式で提供します。互換ライブラリへの変更方法は [ライブラリ差し替え手順](https://github.com/ochreotter/FocusLoop/blob/main/docs/library-replacement.md)（配布ZIP内では `LIBRARY_REPLACEMENT.md`） を参照してください。

**対応するライブラリのソースコード**: Windows ZIP と同じ [FocusLoop Release](https://github.com/ochreotter/FocusLoop/releases) の Assets に、Qt 6.12.0 と Qt for Python 6.12.0（PySide6 Essentials と Shiboken6）のソースアーカイブを別ファイルで用意します。`qt-everywhere-src-6.12.0.tar.xz` と `pyside-setup-everywhere-src-6.12.0.tar.xz` を参照し、`Qt-PySide6-SHA256SUMS.txt` または同梱 `DEPENDENCIES.txt` でハッシュを照合してください。配布する同梱ライブラリには独自変更を加えていません。

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
