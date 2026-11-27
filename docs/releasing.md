# FocusLoopのリリース運用

この文書はリリース作業者向けです。利用方法は [README](../README.md) を参照してください。

## タグとドラフトRelease

アプリ側の `focusloop/updates.py` にある `VERSION` を次の公開バージョン（例：`1.0.1`）に更新し、対応するWindows UI・単体テストを通してください。Releaseのタグ名と`VERSION`が一致しない場合、GitHub Actionsはビルド前に失敗します。公開済みのタグは上書きせず、修正は新しいバージョンで公開してください。


`main`のCIと実機確認が終わったら、対象コミットへ`1.0.0`形式（`v`なし）のタグを付けます。

```bash
git switch main
git pull --ff-only
git tag -a 1.0.0 -m "FocusLoop 1.0.0"
git push origin 1.0.0
```

タグのpushにより`.github/workflows/release.yml`が動き、Windowsのフォルダー形式ZIPをビルドしてGitHubの**ドラフトRelease**に添付します。ライセンスの最終確認が終わるまで公開されません。既に使ったタグは上書きせず、修正は次のバージョンで行います。

## 配布前の必須チェック

- [ ] Pythonロジック・Windows Qt UIのCIに成功し、Windows実機で表示・通知・トレイ・マルチモニター・DLL差し替えを確認する
- [ ] 配布ZIPは`FocusLoop-Windows.zip`で、EXEとDLL・Qtプラグインが分離したフォルダー形式になっている
- [ ] `DEPENDENCIES.txt`にPython、PySide6 Essentials、Shiboken6、Qtのバージョンを正確に記録する
- [ ] 配布ファイルにFocusLoopのMIT全文、Qt/PySide6の著作権表示、LGPLv3・GPLv3の全文、CPythonのライセンスを同梱する
- [ ] **バンドルされたQt/PySide6のバージョンに完全に一致する対応ソース（未改変の部分も含む）を、管理できる配布先で利用者に提供**する。またはQt公式が認める条件を満たす書面による提供を整える。**Qt公式の外部リンクだけで代用しない**
- [ ] Qt内に同梱された第三者コードの対象バージョン別のライセンス・著作権表示を確認する。必要な表示・ライセンス文書をZIPに追加する（https://doc.qt.io/qt-6/licenses-used-in-qt.html）
- [ ] 互換Qt DLL・PySide6モジュールの差し替え方法が配布ZIPから読め、実際に試せることを確認する
- [ ] Releaseの説明に、Qt/PySide6の対応ソース提供先または適切な書面オファーを明示する
- [ ] ドラフトReleaseを確認した後、GitHub上で**Publish release**を実行する

**重要**: 本ワークフローは著作権表示・ライセンス文書の同梱とドラフトReleaseの作成を自動化するものです。対応ソース・個別のQt第三者ライセンス・実機での差し替えがすべて確認できるまで、自動的に公開Releaseにはしません。

## デバッグ用ビルド

`main`へのpushで動く`.github/workflows/build.yml`もフォルダー形式ZIPを生成します。ActionsのArtifactから開発用ZIPを取得できます。正式な公開物として配布する前に、上記のライセンスチェックを実施してください。

## 1.0.0 再リリースの確認

最新の機能修正は維持し、配布版の番号を 1.0.0 に戻す。バージョン番号が同じか大きい旧配布版は自動で移行できないため、改訂版の Windows ZIP を別フォルダーに展開して起動する手順を Release に明記する。旧番号の遺物を再配布しない。タグ付け替え・既存配布物取り下げの対象は、公開作業前に確認する。

- クリーンな Windows Python 3.12 環境へ `requirements.txt` を導入する。PySide6 メタパッケージと Addons は使わない。
- バンドル DLL／プラグインの許可リストは未調査の同梱物を検知するためのもの。使っていないものは減らし、実際の ZIP を調査して個別の第三者ライセンス・著作権表示を確認する。
- `python -m scripts.fetch_release_sources` でハッシュ確認済みの 6.12.0 アーカイブをステージし、Windows ZIP と同じ公開先で入手できる状態にする。案内文だけで配布したことにはしない。
- Windows で ZIP 展開後の起動、設定、タイマー、トレイ、通知、日本語IME、DLL置換、更新経路を確認してから公開する。
