# LAMZU Thorn V2 Battery Monitor v1.0.2

LAMZU Thorn V2（LAMZU 8K Dongle V2 接続）向けの軽量システムトレイバッテリー監視ツール **v1.0.2** のリリースノートです。

本ソフトウェアは個人有志による非公式のオープンソースソフトウェアです（LAMZU社公式ツールではありません）。

---

## 🌟 主な変更点 (v1.0.2)

### 充電完了（0x02）ステータス表示対応およびドキュメント拡充
- **充電完了時の水色/シアン（`#00D2FF`）＋⚡マーク表示**:
  - デバイスから充電完了ステータス（HID Status Byte 3 == `0x02`）を受信した際、タスクトレイアイコン（全3種類のデザイン）および左クリックのステータスパネルにおいて、ゲージ・数値を水色/シアン（`#00D2FF`）で表示し、金色の⚡マークを併記するように対応しました。
- **ステータスパネルおよびツールチップの表記更新**:
  - 充電完了時のステータスパネル表示を「`● 接続中・充電完了`」、トレイアイコンのツールチップ表示を「`LAMZU Thorn V2: 100% (充電完了)`」に更新しました。
- **READMEプレビュー画像の追加**:
  - 3種類のトレイアイコンデザイン（通常時・充電中・充電完了）およびステータスパネルの表示比較プレビュー画像を `README.md` に追加しました。

---

## 💻 動作環境・導入方法

- **対応OS**: Windows 11 (64-bit 実機動作確認済み) / Windows 10 (64-bit 互換動作想定)
- **対象デバイス**: LAMZU Thorn V2（LAMZU 8K Dongle V2 経由での接続、VID: `0x37B0`, PID: `0x002E`）
- **導入手順**:
  1. 下記のアセット一覧より `LAMZU-Thorn-Battery-Monitor.exe` をダウンロードします。
  2. 任意のフォルダーに配置し、ダブルクリックして起動します（インストーラー不要）。
  3. タスクバー右下の通知領域（システムトレイ）にバッテリーアイコンが表示されます。

---

## 📦 配布ファイル一覧およびチェックサム (SHA-256)

| ファイル名 | 対象利用者 | サイズ | SHA-256 チェックサム | 説明 |
|---|---|---|---|---|
| `LAMZU-Thorn-Battery-Monitor.exe` | 一般利用者向け | 20,380,374 バイト<br>(約 19.44 MB) | `1b996593f9c49eddcf24704de69536e98c408283aeb3008238dd4b9a4b8ca917` | インストール不要の単一実行可能ファイル（OneFile EXE） |
| `LAMZU-Thorn-Battery-Monitor-source-and-licenses.zip` | 開発者・ライセンス検証者向け | 検証情報参照 | 本リリースの公開本文参照 | アプリケーション全ソースコード、ビルド仕様書、全ライセンス原文、pystray公式ソース一式<br>※ ソースZIP自体のSHA-256は、自己参照を回避するためGitHub Releases公開本文および検証情報に記載されます。 |

> [!NOTE]
> **Windows SmartScreen 警告について**  
> 本バイナリはオープンソースの個人開発ソフトウェアであり、商用コード署名を行っていません。  
> 初回起動時に「Windows によって PC が保護されました」という SmartScreen 警告画面が表示される場合があります。「詳細情報」をクリックし、「実行」ボタンを選択して起動してください。

---

## 📜 ライセンス・LGPL-3.0に関する重要事項

- アプリケーション本体は **MIT License**（Copyright (c) 2026 jun0b）です。詳細は [LICENSE](https://github.com/jun0b/LAMZU-Thorn-V2-Battery-Monitor/blob/main/LICENSE) をご覧ください。
- タスクトレイ制御ライブラリとして **pystray 0.19.5**（GNU LGPL-3.0）を使用しています。
- LGPL-3.0 Section 4(d)(0) に基づき、改変版 `pystray` を組み込んで OneFile EXE を再ビルド・再結合する手順および環境構築方法を [docs/BUILD_FROM_SOURCE.md](https://github.com/jun0b/LAMZU-Thorn-V2-Battery-Monitor/blob/main/docs/BUILD_FROM_SOURCE.md) に完全公開しています。
- 全第三者ライブラリのライセンス原文および法的留意事項については [docs/THIRD_PARTY_LICENSES.md](https://github.com/jun0b/LAMZU-Thorn-V2-Battery-Monitor/blob/main/docs/THIRD_PARTY_LICENSES.md) をご覧ください。
- プロジェクトの全体説明は [README.md](https://github.com/jun0b/LAMZU-Thorn-V2-Battery-Monitor/blob/main/README.md) を参照してください。

---

## ⚠️ 未検証事項・既知の制限

- **USB充電ケーブル抜去後の充電表示について**:
  - マウスのUSB給電ケーブルを取り外した後も、ステータスパネルやトレイアイコンに充電中表示（⚡マーク）が継続して残る場合があります。
  - 実機検証により、同様の状況において**LAMZU 8KドングルのLEDインジケーター**および**LAMZU公式Webドライバー（LAMZU Aurora）**上でも充電中表示のまま継続することが確認されています（マウスの移動やクリック操作を行っても即時には解除されない場合があります）。
  - 原因は現時点で未確定（ハードウェア・ドングル・ファームウェア側の挙動である可能性）であり、本アプリはデバイスから受信した最新のHIDステータスをそのまま表示する設計を維持しているため、推測による強制的な充電解除処理は行っていません。
- **接続形態**: マウス本体を有線接続した場合の動作は未検証です（LAMZU 8K Dongle V2 接続を推奨）。
- **他ドングル**: 標準1Kドングルや他モデル用ドングルでの動作は未検証です。
