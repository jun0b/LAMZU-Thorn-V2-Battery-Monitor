# サードパーティライブラリおよびライセンス情報

本プロジェクト（LAMZU Thorn V2 Battery Monitor）で使用している主要なサードパーティライブラリ、ランタイム、およびそのライセンス情報は以下のとおりである。

- **本体ライセンス**: MIT License (`Copyright (c) 2026 jun0b`)
- **アプリアイコン (`resources/app.ico`)**: 本プロジェクト独自作成（MIT Licenseに包含）

---

## 1. 依存ライブラリおよびバンドルランタイム一覧

PyInstaller による実行バイナリ（OneFile EXE）および開発環境に含まれる主要コンポーネントの実機確認バージョン、ライセンス種別、および原文リンクは以下のとおりである。

### 1.1 Python 依存ライブラリ（site-packages）

| ライブラリ名 | 実機バージョン | ライセンス種別 | 主な用途 | 原文ファイル |
|---|---|---|---|---|
| **pystray** | 0.19.5 | LGPL-3.0 / GPL-3.0 | Windowsタスクトレイ常駐・コンテキストメニュー | [LICENSE-pystray-LGPL-3.0.txt](licenses/LICENSE-pystray-LGPL-3.0.txt)<br>[LICENSE-pystray-GPL-3.0.txt](licenses/LICENSE-pystray-GPL-3.0.txt) |
| **hidapi** | 0.15.0 | Multi-license (BSD / GPL-3.0 / HIDAPI) | USB HID通信（パケット受信・設定読み取り） | [LICENSE-hidapi-bsd.txt](licenses/LICENSE-hidapi-bsd.txt)<br>[LICENSE-hidapi-summary.txt](licenses/LICENSE-hidapi-summary.txt) |
| **Pillow (PIL)** | 12.1.0 | HPND (Historical Permission Notice) | トレイアイコンの動的画像生成（数値・ゲージ描画） | [LICENSE-pillow.txt](licenses/LICENSE-pillow.txt) |
| **winotify** | 1.1.0 | MIT License | Windows 11 ネイティブトースト通知送信 | [LICENSE-winotify.txt](licenses/LICENSE-winotify.txt) |
| **psutil** | 7.2.1 | BSD 3-Clause License | プロセス管理・多重起動確認 | [LICENSE-psutil.txt](licenses/LICENSE-psutil.txt) |
| **pywin32** | 311 | BSD-style (Mark Hammond) | Windows API 連携・多重起動抑止 | [LICENSE-pywin32.txt](licenses/LICENSE-pywin32.txt) |
| **six** | 1.17.0 | MIT License | pystray内部依存ユーティリティ | [LICENSE-six.txt](licenses/LICENSE-six.txt) |

### 1.2 バンドルランタイム・ネイティブ DLL（EXE 内蔵）

| コンポーネント名 | ファイル例 | ライセンス種別 | 主な用途 | 原文ファイル |
|---|---|---|---|---|
| **Python Runtime** | `python313.dll`, `python3.dll` | Python Software Foundation License (PSF) | Python インタプリタ実行環境 | [LICENSE-python-psf.txt](licenses/LICENSE-python-psf.txt) |
| **Tcl/Tk Runtime** | `tcl86t.dll`, `tk86t.dll` | Tcl/Tk License (BSD-style) | GUI・ダイアログ補助ランタイム | [LICENSE-tcltk.txt](licenses/LICENSE-tcltk.txt) |
| **OpenSSL** | `libcrypto-3.dll`, `libssl-3.dll` | Apache License 2.0 | 暗号・ハッシュ・セキュア通信ランタイム | [LICENSE-openssl-apache2.txt](licenses/LICENSE-openssl-apache2.txt) |
| **zlib** | `zlib1.dll` | zlib License | データ圧縮・解凍ランタイム | [LICENSE-zlib.txt](licenses/LICENSE-zlib.txt) |
| **Microsoft VC++ Runtime** | `vcruntime140.dll`, `ucrtbase.dll` | Microsoft Visual Studio 再配布可能コードライセンス | C/C++ ランタイム基本ライブラリ | Microsoft Visual Studio ソフトウェア ライセンス条項に準拠 |

---

## 2. 配布およびライセンス条件に関する分析

### 2.1 pystray (LGPL-3.0) に関する留意事項と未解決の義務

- **著作権**: Copyright (C) 2015-2023 Moses Palmér
- **適用ライセンス**: GNU Lesser General Public License v3.0 (LGPL-3.0)
- **ライセンス要件と本プロジェクトの対応方針**:
  1. **著作権表示およびライセンス条文の提供**:
     - LGPL-3.0 の公式原文（`docs/licenses/LICENSE-pystray-LGPL-3.0.txt`）および前提となる GNU GPL v3 の公式原文（`docs/licenses/LICENSE-pystray-GPL-3.0.txt`）を同梱・提供する。
  2. **ソースコードの提供**:
     - アプリケーション本体の全ソースコード、依存定義（`requirements-release.txt`）、ビルド定義（`LAMZU-Thorn-Battery-Monitor.spec`）、および公式 `pystray 0.19.5` ソースアーカイブ（`docs/licenses/pystray-v0.19.5.tar.gz`、公式GitHub: `https://github.com/moses-palmer/pystray/tree/v0.19.5`、SHA-256: `2ab6bd15c14b400c9e8271a82c9de8adc0f1a0cacfc14080bdd4fb42bb88ec92`）を提供する。
  3. **再結合（Relinking）および改変の権利保証（Section 4d(0)）に関する実証と技術的留意点**:
     - LGPL-3.0 Section 4d(0) では、利用者がライブラリ部分を修正・差し替えて再結合（または再リンク）できる仕組みを提供することを求めている。
     - PyInstaller による単一実行ファイル（OneFile EXE）配布では、Python インタプリタ、標準ライブラリ、サードパーティライブラリのバイトコードが単一バイナリ（CArchive / PYZ アーカイブ）内に一体化して格納される。そのため、動的リンクライブラリ（DLL）の差し替えのような外部ファイルの単純な置換による再結合は技術的に困難である。
     - 本プロジェクトでは、改変版 `pystray` を組み込んで OneFile EXE を再ビルドし、内部のバイトコードが確実に改変後のものに置き換わる実証検証（実機検証済み）を実施した。その手順を [`docs/BUILD_FROM_SOURCE.md`](BUILD_FROM_SOURCE.md) に完全公開している。
     - **未解決事項および法的解釈に関する断定の回避**: 単一バイナリ配布（OneFile EXE）＋完全ビルド手順・ソース提供の組み合わせをもって、LGPL-3.0 Section 4d(0) の再結合条件が形式上完全に満たされていると法的に断定することはできない（PyInstaller OneFile の構造に起因するオープンな議論が存在する）。完全なライブラリ差し替えやリバースエンジニアリングの自由度を重視する利用者に対しては、リポジトリからソースコードを直接実行する方式（`python app.py`）を正式な代替手段として案内する。

### 2.2 寛容型ライセンス (MIT / BSD / HPND / Apache-2.0 / zlib / PSF) の遵守状況

- **hidapi (BSD-style)**: 著作権表示および許諾条件を保持・提供。
- **Pillow (HPND)**: 著作権表示および許諾条件を保持・提供。
- **winotify (MIT)**: 著作権表示および許諾条件を保持・提供。
- **psutil (BSD 3-Clause)**: 著作権表示、条件リスト、免責事項を保持・提供。
- **pywin32 (BSD-style)**: 著作権表示（Mark Hammond）および許諾条件を保持・提供。
- **six (MIT)**: 著作権表示および許諾条件を保持・提供。
- **Python (PSF)**: Python Software Foundation License の条文を保持・提供。
- **OpenSSL (Apache-2.0)**: Apache License 2.0 の条文を保持・提供。
- **zlib (zlib License)**: zlib License の条文を保持・提供。
- **Tcl/Tk (BSD-style)**: Tcl/Tk License terms の条文を保持・提供。

---

## 3. ライセンス原文ファイル一覧

本リポジトリの `docs/licenses/` ディレクトリに保管されている無改変のライセンス原文一覧：

- [LICENSE-pystray-LGPL-3.0.txt](licenses/LICENSE-pystray-LGPL-3.0.txt) (GNU Lesser General Public License Version 3)
- [LICENSE-pystray-GPL-3.0.txt](licenses/LICENSE-pystray-GPL-3.0.txt) (GNU General Public License Version 3)
- [LICENSE-hidapi-bsd.txt](licenses/LICENSE-hidapi-bsd.txt) (HIDAPI BSD-style License)
- [LICENSE-hidapi-orig.txt](licenses/LICENSE-hidapi-orig.txt) (HIDAPI Original License)
- [LICENSE-hidapi-summary.txt](licenses/LICENSE-hidapi-summary.txt) (HIDAPI Multi-License Overview)
- [LICENSE-pillow.txt](licenses/LICENSE-pillow.txt) (Pillow HPND License)
- [LICENSE-winotify.txt](licenses/LICENSE-winotify.txt) (winotify MIT License)
- [LICENSE-psutil.txt](licenses/LICENSE-psutil.txt) (psutil BSD 3-Clause License)
- [LICENSE-pywin32.txt](licenses/LICENSE-pywin32.txt) (pywin32 BSD-style License)
- [LICENSE-six.txt](licenses/LICENSE-six.txt) (six MIT License)
- [LICENSE-python-psf.txt](licenses/LICENSE-python-psf.txt) (Python Software Foundation License Version 2)
- [LICENSE-openssl-apache2.txt](licenses/LICENSE-openssl-apache2.txt) (Apache License Version 2.0)
- [LICENSE-tcltk.txt](licenses/LICENSE-tcltk.txt) (Tcl/Tk License Terms)
- [LICENSE-zlib.txt](licenses/LICENSE-zlib.txt) (zlib License)
