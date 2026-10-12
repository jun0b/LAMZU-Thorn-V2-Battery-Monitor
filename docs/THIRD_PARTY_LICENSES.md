# サードパーティライブラリおよびライセンス情報

本プロジェクト（LAMZU Thorn V2 Battery Monitor）で使用している主要なサードパーティライブラリおよびそのライセンス情報は以下のとおりである。

本体ライセンス: MIT License (`Copyright (c) 2026 jun0b`)

---

## 1. 依存ライブラリ一覧

実行バイナリ（EXE）および開発環境に含まれる主要なサードパーティライブラリの実機確認バージョンとライセンスは以下のとおりである。

| ライブラリ名 | 実機バージョン | ライセンス種別 | 主な用途 | 原文ファイル |
|---|---|---|---|---|
| **pystray** | 0.19.5 | LGPL-3.0 / GPL-3.0 | Windowsタスクトレイ常駐・コンテキストメニュー | [LICENSE-pystray-LGPL-3.0.txt](licenses/LICENSE-pystray-LGPL-3.0.txt)<br>[LICENSE-pystray-GPL-3.0.txt](licenses/LICENSE-pystray-GPL-3.0.txt) |
| **hidapi** | 0.15.0 | Multi-license (BSD / GPL-3.0 / HIDAPI) | USB HID通信（パケット受信・設定読み取り） | [LICENSE-hidapi-bsd.txt](licenses/LICENSE-hidapi-bsd.txt)<br>[LICENSE-hidapi-summary.txt](licenses/LICENSE-hidapi-summary.txt) |
| **Pillow (PIL)** | 12.1.0 | HPND (Historical Permission Notice) | トレイアイコンの動的画像生成（数値・ゲージ描画） | [LICENSE-pillow.txt](licenses/LICENSE-pillow.txt) |
| **winotify** | 1.1.0 | MIT License | Windows 11 ネイティブトースト通知送信 | [LICENSE-winotify.txt](licenses/LICENSE-winotify.txt) |
| **psutil** | 7.2.1 | BSD 3-Clause License | プロセス管理・リソース計測・多重起動確認 | [LICENSE-psutil.txt](licenses/LICENSE-psutil.txt) |
| **six** | 1.17.0 | MIT License | pystray内部依存ユーティリティ | [LICENSE-six.txt](licenses/LICENSE-six.txt) |

---

## 2. 配布およびライセンス条件に関する分析

### 2.1 pystray (LGPL-3.0) に関する留意事項と未解決の義務

- **著作権**: Copyright (C) 2015-2023 Moses Palmér
- **適用ライセンス**: GNU Lesser General Public License v3.0 (LGPL-3.0)
- **ライセンス要件と本プロジェクトの対応方針**:
  1. **著作権表示およびライセンス条文の提供**:
     - LGPL-3.0 の公式原文（`docs/licenses/LICENSE-pystray-LGPL-3.0.txt`）および前提となる GNU GPL v3 の公式原文（`docs/licenses/LICENSE-pystray-GPL-3.0.txt`）を同梱・提供する。
  2. **ソースコードの提供**:
     - アプリケーションの全ソースコード、依存定義（`requirements.txt`）、およびビルド定義（`LAMZU-Thorn-Battery-Monitor.spec`）を本リポジトリで公開・提供する。
  3. **再結合（Relinking）および改変の権利保証（Section 4d）に関する検討**:
     - LGPL-3.0 Section 4d では、利用者がライブラリ部分を修正・差し替えて再結合（または再リンク）できる仕組みを提供することを求めている。
     - PyInstaller による単一実行ファイル（OneFile EXE）配布では、Python インタプリタ、標準ライブラリ、サードパーティライブラリのバイトコードが単一バイナリ（CArchive / PYZ アーカイブ）内に一体化して格納される。そのため、動的リンクライブラリ（DLL）の差し替えのような外部ファイルの単純な置換による再結合は技術的に困難である。
     - 本プロジェクトでは、完全なソースコードおよびビルド手順書を提供することにより、ユーザー自身が改変版 `pystray` をインストールした Python 環境で再ビルド、あるいはソースコードから直接実行できる環境を整えている。
     - **未解決事項および断定の回避**: 単一バイナリ配布（OneFile EXE）の提供のみをもって LGPL-3.0 Section 4d の再結合条件が形式上完全に満たされていると法的に断定することはできない。完全なライブラリ差し替えやリバースエンジニアリングの自由度を重視する利用者に対しては、リポジトリからソースコードを直接実行する方式（`python app.py`）を正式な代替手段として案内する。

### 2.2 寛容型ライセンス (MIT / BSD / HPND) の遵守状況

- **hidapi (BSD-style)**:
  - 著作権表示および許諾条件を `docs/licenses/LICENSE-hidapi-bsd.txt` として保持・提供。
- **Pillow (HPND)**:
  - 著作権表示および許諾条件を `docs/licenses/LICENSE-pillow.txt` として保持・提供。
- **winotify (MIT)**:
  - 著作権表示および許諾条件を `docs/licenses/LICENSE-winotify.txt` として保持・提供。
- **psutil (BSD 3-Clause)**:
  - 著作権表示、条件リスト、免責事項を `docs/licenses/LICENSE-psutil.txt` として保持・提供。
- **six (MIT)**:
  - 著作権表示および許諾条件を `docs/licenses/LICENSE-six.txt` として保持・提供。

---

## 3. ライセンス原文ファイル一覧

公式パッケージ（site-packages）の配布元から無改変で取得したライセンス原文は、`docs/licenses/` ディレクトリに保管されている。

- `docs/licenses/LICENSE-pystray-LGPL-3.0.txt` (GNU Lesser General Public License Version 3)
- `docs/licenses/LICENSE-pystray-GPL-3.0.txt` (GNU General Public License Version 3)
- `docs/licenses/LICENSE-hidapi-bsd.txt` (HIDAPI BSD-style License)
- `docs/licenses/LICENSE-hidapi-orig.txt` (HIDAPI Original License)
- `docs/licenses/LICENSE-hidapi-summary.txt` (HIDAPI Multi-License Overview)
- `docs/licenses/LICENSE-pillow.txt` (Pillow HPND License)
- `docs/licenses/LICENSE-winotify.txt` (winotify MIT License)
- `docs/licenses/LICENSE-psutil.txt` (psutil BSD 3-Clause License)
- `docs/licenses/LICENSE-six.txt` (six MIT License)
