"""LAMZU Thorn V2 Battery Monitor - アプリケーションエントリーポイント

Windowsシステムトレイに常駐し、LAMZU Thorn V2のバッテリー残量をリアルタイムで監視・表示する。

使用方法:
  python app.py          : 実機HID通信による通常監視モード
  python app.py --demo   : 各種状態変化をシミュレートするデモモード
  python app.py --debug  : 詳細デバッグログ出力
"""

import argparse
import datetime
import logging
import os
import signal
import sys
import threading
from typing import Optional

# Windows環境におけるUTF-8文字化け防止
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from logging.handlers import RotatingFileHandler
from battery_state import BatteryState, ReceiveState
from hid_worker import HidWorker
from demo_worker import DemoWorker
from notification_manager import NotificationManager
from autostart_manager import AutostartManager
import tkinter as tk
from single_instance import SingleInstanceChecker
from config_manager import ConfigManager, SUPPORTED_STYLES
from status_panel import StatusPanel
from tray_ui import TrayUI


def get_app_data_dir() -> str:
    """アプリケーションの永続データディレクトリ (%LOCALAPPDATA%\\LAMZUThornBatteryMonitor) を取得"""
    local_appdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
    app_dir = os.path.join(local_appdata, "LAMZUThornBatteryMonitor")
    os.makedirs(app_dir, exist_ok=True)
    return app_dir


def setup_logging(debug: bool = False) -> str:
    """ロギング設定の初期化 (永続ログフォルダーへのRotatingFileHandler出力)"""
    app_dir = get_app_data_dir()
    log_dir = os.path.join(app_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file_path = os.path.join(log_dir, "app.log")
    level = logging.DEBUG if debug else logging.INFO
    log_format = "%(asctime)s [%(levelname)s] (%(threadName)s) %(message)s"

    handlers = []
    # コンソールウィンドウが存在する場合のみStreamHandlerを追加 (noconsole対策)
    if sys.stdout is not None:
        try:
            handlers.append(logging.StreamHandler(sys.stdout))
        except Exception:
            pass

    # 最大1MB、バックアップ3世代のローテーションファイルハンドラー
    file_handler = RotatingFileHandler(
        log_file_path,
        maxBytes=1024 * 1024,
        backupCount=3,
        encoding="utf-8"
    )
    handlers.append(file_handler)

    # 開発環境ローカルの logs/ ディレクトリにも出力 (存在または作成可能な場合)
    try:
        os.makedirs("logs", exist_ok=True)
        local_log_path = os.path.join("logs", "app.log")
        handlers.append(RotatingFileHandler(local_log_path, maxBytes=1024 * 1024, backupCount=3, encoding="utf-8"))
    except Exception:
        pass

    # ルートロガー設定
    logging.basicConfig(level=level, format=log_format, handlers=handlers, force=True)
    return log_file_path


def main():
    """メイン実行関数"""
    # 0. 多重起動防止チェック (二重起動時は静かに終了)
    instance_checker = SingleInstanceChecker()
    if instance_checker.is_already_running():
        sys.exit(0)

    parser = argparse.ArgumentParser(
        description="LAMZU Thorn V2 Battery Monitor - システムトレイ常駐アプリ"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="実機を開かずに各種残量・状態変化をシミュレーションするデモモード"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="デバッグログを出力する"
    )
    parser.add_argument(
        "--step-interval",
        type=float,
        default=3.0,
        help="デモモード時の状態遷移間隔 (秒, デフォルト: 3.0)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="指定秒数後に自動終了する (自動テスト・検証用)"
    )
    parser.add_argument(
        "--icon-style",
        choices=list(SUPPORTED_STYLES),
        default=None,
        help="トレイアイコンのデザイン案 (指定時は設定ファイルを上書き更新)"
    )

    args = parser.parse_args()

    # 1. 設定永続化マネージャーの初期化
    config_mgr = ConfigManager()
    if args.icon_style:
        config_mgr.set_icon_style(args.icon_style)
    selected_style = config_mgr.icon_style

    log_path = setup_logging(debug=args.debug)
    logger = logging.getLogger("main")
    logger.info("LAMZU Thorn V2 Battery Monitor を起動しています...")
    logger.info(f"永続ログファイル: {log_path}")
    logger.info(f"選択デザイン案: {selected_style}")

    # 2. 状態管理オブジェクトの初期化
    state = BatteryState(is_demo_mode=args.demo)

    # 2.1 自動起動マネージャーの初期化
    autostart_mgr = AutostartManager()

    # 2.2 低バッテリー通知マネージャーの初期化 (同一config_pathで連携)
    notif_manager = NotificationManager(is_demo_mode=args.demo, config_path=config_mgr.config_path)

    # バッテリー状態更新時の通知判定リスナーを登録
    def on_battery_update_for_notification(updated_state: BatteryState) -> None:
        try:
            # 最新の有効なバッテリー情報を受信しているNORMAL状態のみ通知評価を実行 (誤通知防止)
            if updated_state.receive_state != ReceiveState.NORMAL:
                return
            notif_manager.evaluate_battery(
                percent=updated_state.percent,
                is_stale=updated_state.is_stale,
                is_disconnected=updated_state.is_disconnected,
                receive_state=updated_state.receive_state
            )
        except Exception as e:
            logger.error(f"通知評価リスナー実行中にエラーが発生しました: {e}", exc_info=True)

    state.add_listener(on_battery_update_for_notification)

    # 3. ワーカーの選定と初期化
    worker = None
    if args.demo:
        logger.info("【デモモード】で起動します (実機HIDデバイスは開きません)")
        worker = DemoWorker(state, step_interval=args.step_interval)
    else:
        logger.info("【実機監視モード】で起動します")
        worker = HidWorker(state)

    # 4. Tkinterルートおよびステータスパネルの初期化 (メインスレッド)
    root = tk.Tk()
    root.withdraw()
    status_panel = StatusPanel(root)

    ui: Optional[TrayUI] = None
    exit_lock = threading.Lock()
    is_shutting_down = False

    def handle_exit():
        nonlocal is_shutting_down
        with exit_lock:
            if is_shutting_down:
                return
            is_shutting_down = True

        logger.info("アプリケーション停止処理を実行中...")
        if worker is not None and worker.is_alive():
            worker.stop()
        if ui is not None:
            ui.stop()

        def _cleanup_gui():
            try:
                if status_panel is not None:
                    status_panel.destroy()
            except Exception as e:
                logger.debug(f"ステータスパネル破棄エラー: {e}")
            try:
                root.quit()
            except Exception as e:
                logger.debug(f"ルート終了エラー: {e}")

        # Tkinterウィジェット破棄とメインループ終了をメインスレッドで実行
        try:
            if threading.current_thread() is threading.main_thread():
                _cleanup_gui()
            else:
                root.after(0, _cleanup_gui)
        except Exception:
            pass

        logger.info("ワーカーおよびUI停止要求を完了しました")

    ui = TrayUI(
        state,
        on_exit=handle_exit,
        icon_style=selected_style,
        notification_manager=notif_manager,
        autostart_manager=autostart_mgr,
        config_manager=config_mgr,
        status_panel=status_panel
    )

    # Ctrl+C シグナルハンドラーの登録
    def sigint_handler(signum, frame):
        logger.info("Ctrl+C を検知しました。終了処理を開始します...")
        handle_exit()

    signal.signal(signal.SIGINT, sigint_handler)

    # 4. 検証用自動停止タイマーの設定
    if args.timeout is not None:
        root.after(int(args.timeout * 1000), handle_exit)

    # 5. ワーカーの起動
    worker.start()

    # 6. トレイUIを専用スレッドで起動、Tkinterメインループをメインスレッドで実行
    tray_thread = threading.Thread(target=ui.start, name="TrayUIThread", daemon=True)
    tray_thread.start()

    logger.info("システムトレイおよびステータスパネルイベントループを開始します")
    try:
        root.mainloop()
    except KeyboardInterrupt:
        handle_exit()
    finally:
        handle_exit()
        try:
            root.destroy()
        except Exception:
            pass
        instance_checker.release()
        logger.info("ミューテックスを解放しました")
        # リソース使用状況の測定
        try:
            import psutil
            proc = psutil.Process()
            cpu_usage = proc.cpu_percent(interval=0.1)
            mem_mb = proc.memory_info().rss / (1024 * 1024)
            logger.info(f"リソース使用状況: CPU={cpu_usage:.1f}%, メモリ={mem_mb:.1f}MB")
        except Exception:
            pass
        logger.info("LAMZU Thorn V2 Battery Monitor を正常終了しました")


if __name__ == "__main__":
    main()
