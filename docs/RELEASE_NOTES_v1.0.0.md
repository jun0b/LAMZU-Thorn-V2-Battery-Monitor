# LAMZU Thorn V2 Battery Monitor v1.0.0

LAMZU Thorn V2（LAMZU 8K Dongle V2 接続）向けの軽量システムトレイバッテリー監視ツール **v1.0.0** の初回公式リリースです。

本ソフトウェアは個人有志による非公式のオープンソースソフトウェアです（LAMZU社公式ツールではありません）。

---

## 🌟 主な機能

- **タスクトレイ常駐バッテリー監視**: 16x16px〜32x32pxの高DPI対応アイコンで残量をリアルタイム表示。
- **3種類のアイコンデザイン**: 「数字+バッテリー」「数字のみ」「バッテリーのみ」を右クリックメニューから即時切り替え。
- **左クリックで開くステータスパネル**:
  - 大きなバッテリー残量表示とバッテリーゲージ
  - 充電中⚡アイコン（USB給電時のステータス判定）
  - 現在の DPI および ポーリングレートのリアルタイム読み取り表示（左右2列カード）
- **低バッテリーWindowsトースト通知**: 残量20%（警告）および10%（緊急）で自動通知。重複通知防止および充電回復後の自動再アーム対応。
- **Windows自動起動**: 右クリックメニューからワンクリックで有効化（HKCU Runレジストリ登録、管理者権限不要）。
- **公式Webドライバー連携**: メニューから「LAMZU Aurora」を既定のブラウザーで直接オープン。
- **二重起動防止**: Windows Named Mutex による安全な単一プロセス制御。
- **完全読み取り専用設計**: マウス本体の設定変更やファームウェア書き換えは行いません。

---

## 💻 動作環境・導入方法

- **対応OS**: Windows 11 (64-bit 実機動作確認済み) / Windows 10 (64-bit 互換動作想定)
- **対象デバイス**: LAMZU Thorn V2（LAMZU 8K Dongle V2 経由での接続、VID: `0x37B0`, PID: `0x002E`）
- **導入手順**:
  1. 下記のアセット一覧より `LAMZU-Thorn-Battery-Monitor.exe` をダウンロードします。
  2. 任意のフォルダーに配置し、ダブルクリックして起動します（インストーラー不要）。
  3. タスクバー右下の通知領域（システムトレイ）にバッテリーアイコンが表示されます。

---

## 📦 配布ファイル一覧

| ファイル名 | 対象利用者 | 説明 |
|---|---|---|
| `LAMZU-Thorn-Battery-Monitor.exe` | 一般利用者向け | インストール不要の単一実行可能ファイル（OneFile EXE）<br>サイズ: 20,375,272 バイト (19.43 MB)<br>SHA-256: `6cebd9e42acc05611da7cf09188ecebf9b8bd1c2a749362a5e628926ff29f1ad` |
| `LAMZU-Thorn-Battery-Monitor-source-and-licenses.zip` | 開発者・ライセンス検証者向け | アプリケーション全ソースコード、ビルド仕様書、全ライセンス原文、pystray公式ソース一式<br>※ ソースZIP自体のSHA-256は、自己参照を回避するため本リリースの公開本文および検証情報に記載されます。 |

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

- マウス本体を有線接続した場合の動作は未検証です（LAMZU 8K Dongle V2 接続を推奨）。
- 標準1Kドングルや他モデル用ドングルでの動作は未検証です。
- USB充電ケーブルを抜いた直後、マウスを完全に静止させた状態ではドングルが一時的に前回の充電ステータスを保持する場合があります（マウスを動かすと最新の非充電ステータスに復帰します）。
