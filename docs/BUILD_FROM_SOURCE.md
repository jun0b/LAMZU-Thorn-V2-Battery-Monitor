# ソースコードからのビルドおよび改変ライブラリ再結合手順

本書は、LAMZU Thorn V2 Battery Monitor のソースコードから Windows 用 OneFile 実行可能ファイル（EXE）をビルドする手順、および GNU LGPL-3.0 に基づき改変された `pystray` ライブラリを組み込んで再ビルド・再結合する手順を解説する。

---

## 1. 対象環境

本プロジェクトの公式バイナリは以下の環境でビルドおよび動作確認を行っている。

- **OS**: Windows 11 64-bit (Version 23H2 / 24H2)
- **Python**: Python 3.13.x 64-bit（公式推奨: Python 3.13.14）
  - ※ Microsoft Store版または python.org 配布のインストーラー版（64-bit）
- **ビルドツール**: PyInstaller 6.18.0

---

## 2. ビルド環境の構築

### 2.1 リポジトリの取得

Gitクローンまたは配布用ソースアーカイブ（ZIP）を展開し、作業ディレクトリへ移動する。

```powershell
cd "LAMZU Thorn V2 Battery Monitor"
```

### 2.2 仮想環境（venv）の作成と有効化

クリーンなPython仮想環境を作成して有効化する。

```powershell
# 仮想環境の作成
python -m venv .venv

# 仮想環境の有効化（PowerShell）
.\.venv\Scripts\Activate.ps1
```

※ PowerShellのスクリプト実行ポリシーでエラーが発生する場合は、`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` を実行して一時的に許可する。

### 2.3 依存ライブラリのインストール

リリース用にバージョンを固定した `requirements-release.txt` を使用して依存パッケージをインストールする。

```powershell
pip install --upgrade pip
pip install -r requirements-release.txt
```

### 2.4 単体テストによる動作確認

ビルド前に、すべての単体テストがパスすることを確認する。

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

すべてのテスト（141件）が `OK` と表示されれば準備完了である。

---

## 3. 通常のOneFile EXEビルド手順

本プロジェクトに同梱されている PyInstaller 仕様書（`LAMZU-Thorn-Battery-Monitor.spec`）を使用してビルドを実行する。

```powershell
# 既にEXEが実行中の場合は事前に終了させること
pyinstaller --noconfirm LAMZU-Thorn-Battery-Monitor.spec
```

ビルドが成功すると、`dist\` ディレクトリに実行ファイルが生成される。

- 出力先: `dist\LAMZU-Thorn-Battery-Monitor.exe`

---

## 4. 改変版 pystray を組み込んだ再ビルド手順（LGPL-3.0 対応）

本アプリケーションは、システムトレイ制御ライブラリとして GNU LGPL-3.0 が適用される `pystray`（バージョン 0.19.5）を使用している。
ユーザーが独自に修正・改変した `pystray` を本アプリケーションに適用し、再ビルド・再結合を行う手順は以下の通りである。

### 4.1 pystray ソースコードの確認・展開

配布用ソースアーカイブ（ZIP）には、LGPL-3.0 のソース提供要件を満たすため、公式の `pystray 0.19.5` ソースアーカイブが収録されている。

- **ファイル配置**: `docs/licenses/pystray-v0.19.5.tar.gz`
- **公式GitHub**: `https://github.com/moses-palmer/pystray/tree/v0.19.5`
- **アーカイブ SHA-256**: `2ab6bd15c14b400c9e8271a82c9de8adc0f1a0cacfc14080bdd4fb42bb88ec92`

ZIP を展開したプロジェクトルートディレクトリで、作業用ディレクトリを作成してアーカイブを展開する。

```powershell
# 改変作業用ディレクトリの作成
New-Item -ItemType Directory -Force -Path "pystray_custom"

# 同梱の公式ソースアーカイブを作業用ディレクトリへ展開
tar -xzf "docs\licenses\pystray-v0.19.5.tar.gz" -C "pystray_custom"
```

展開すると、`pystray_custom\pystray-0.19.5` ディレクトリ配下に完全なソースコード（`setup.py`、`lib/pystray/` など）が展開される。

### 4.2 ソースコードの改変

展開された `pystray` のソースコード（例: `pystray_custom\pystray-0.19.5\lib\pystray` 以下の各ファイル）に対して、目的の修正や拡張を加える。

### 4.3 仮想環境への改変版ライブラリのインストール

改変した `pystray` を、ビルド用仮想環境にインストールする。

```powershell
# 改変版ソースのルート（setup.py が存在するディレクトリ）を指定してインストール
pip install .\pystray_custom\pystray-0.19.5
```

インストール後、改変内容が反映されているか確認する。

```powershell
python -c "import pystray; print(pystray.__file__)"
```

### 4.4 再ビルドの実行

改変版ライブラリが仮想環境に導入された状態で、通常と同じ spec ファイルを用いて再ビルドを実行する。

```powershell
pyinstaller --noconfirm LAMZU-Thorn-Battery-Monitor.spec
```

### 4.5 再ビルドされたバイナリの検証

ビルドされた `dist\LAMZU-Thorn-Battery-Monitor.exe` を実行し、改変された `pystray` の動作が正しく反映されていることを確認する。

また、PyInstaller の内部アーカイブ検証ツールを用いて、バンドルされた `PYZ-00.pyz` 内の `pystray` バイトコードが改変後のものであることを直接検証することも可能である。

---

## 5. トラブルシューティング

### 5.1 PermissionError [WinError 5]（アクセス拒否）
- **原因**: 既存の `dist\LAMZU-Thorn-Battery-Monitor.exe` がタスクトレイで実行中のまま上書きビルドを試みた場合に発生する。
- **対処法**: タスクトレイアイコンを右クリックして「終了」を選択し、プロセス（`LAMZU-Thorn-Battery-Monitor.exe`）が完全に終了していることを確認してから再実行する。

### 5.2 PowerShell スクリプト実行エラー（PSSecurityException）
- **原因**: Windows の実行ポリシーにより、仮想環境の `Activate.ps1` の実行が制限されている。
- **対処法**: 一時的に実行ポリシーを緩和する。
  ```powershell
  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
  ```

### 5.3 アイコンやリソースの読み込みエラー
- **原因**: カレントディレクトリがプロジェクトルート以外になっている。
- **対処法**: 必ず `LAMZU-Thorn-Battery-Monitor.spec` が存在するディレクトリをカレントディレクトリにして PyInstaller を実行すること。
