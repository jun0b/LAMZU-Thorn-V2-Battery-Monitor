"""LAMZU Thorn V2 低バッテリー通知管理モジュール

Windows 11における低残量トースト通知、重複防止、回復後の再アーム、
および設定・通知履歴の永続化を担当する。

通知仕様:
  - 20%以下 (11〜20%): 低残量警告 (1回のみ、25%超で再アーム)
  - 10%以下 (0〜10%) : 緊急警告 (1回のみ、15%超で再アーム)
  - テスト通知: 手動実行専用、通常の通知履歴に影響しない
"""

import datetime
import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Optional, List, Dict, Any

logger = logging.getLogger("notification")

APP_ID = "LAMZU Thorn V2 Battery Monitor"
DEFAULT_TITLE = "LAMZU Thorn V2"


class NotificationLevel(Enum):
    """通知レベルの定義"""
    NONE = "NONE"
    WARNING_20 = "WARNING_20"      # 20%以下 低残量警告
    CRITICAL_10 = "CRITICAL_10"    # 10%以下 緊急警告
    TEST = "TEST"                  # テスト通知


@dataclass
class NotificationConfig:
    """通知設定および発報履歴データモデル"""
    notifications_enabled: bool = True
    warned_20: bool = False
    warned_10: bool = False
    last_notified_at: Optional[str] = None
    last_known_percent: Optional[int] = None


class WindowsNotifier:
    """Windows 11 トースト通知送信クラス (winotify使用)"""

    def __init__(self, app_id: str = APP_ID):
        self.app_id = app_id

    def show(self, title: str, message: str) -> bool:
        """トースト通知を表示する (例外発生時もアプリ継続)"""
        try:
            import winotify
            toast = winotify.Notification(
                app_id=self.app_id,
                title=title,
                msg=message,
                duration="short"
            )
            toast.show()
            logger.info(f"Windowsトースト通知を送信しました: [{title}] {message}")
            return True
        except Exception as e:
            logger.error(f"Windowsトースト通知の送信に失敗しました: {e}", exc_info=True)
            return False


class MockNotifier:
    """自動テストおよび検証用のモック通知クラス"""

    def __init__(self):
        self.notifications: List[Dict[str, str]] = []
        self.should_fail: bool = False

    def show(self, title: str, message: str) -> bool:
        """モック通知を記録する"""
        if self.should_fail:
            raise RuntimeError("モック通知送信エラー（テスト用例外）")
        self.notifications.append({"title": title, "message": message})
        logger.debug(f"[MockNotifier] 通知記録: [{title}] {message}")
        return True

    def clear(self) -> None:
        """記録をクリア"""
        self.notifications.clear()


class NotificationManager:
    """低バッテリー通知・重複防止・永続化マネージャー"""

    def __init__(
        self,
        config_path: Optional[str] = None,
        notifier: Optional[Any] = None,
        is_demo_mode: bool = False
    ):
        self.is_demo_mode = is_demo_mode
        self._lock = threading.Lock()

        # 保存先パスの決定: %LOCALAPPDATA%\LAMZUThornBatteryMonitor\config.json
        if config_path is None:
            local_appdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
            app_dir = os.path.join(local_appdata, "LAMZUThornBatteryMonitor")
            self.config_dir = app_dir
            self.config_path = os.path.join(app_dir, "config.json")
        else:
            self.config_path = config_path
            self.config_dir = os.path.dirname(config_path)

        # 送信エンジンの決定
        self.notifier = notifier if notifier is not None else WindowsNotifier()

        # 設定のロード
        self.config = NotificationConfig()
        self._load_config()

    @property
    def notifications_enabled(self) -> bool:
        """通知が有効かどうか"""
        with self._lock:
            return self.config.notifications_enabled

    def set_enabled(self, enabled: bool) -> None:
        """通知の有効/無効を切り替えて永続化"""
        with self._lock:
            if self.config.notifications_enabled != enabled:
                self.config.notifications_enabled = enabled
                logger.info(f"低残量通知の有効状態を変更しました: {enabled}")
                self._save_config_locked()

    def evaluate_battery(
        self,
        percent: Optional[int],
        is_stale: bool = False,
        is_disconnected: bool = False,
        receive_state: Optional[Any] = None
    ) -> NotificationLevel:
        """受信したバッテリー残量を評価し、必要に応じて通知を発報

        Args:
            percent: 現在のバッテリー残量 (0〜100 または None)
            is_stale: 受信途絶・スリープ推測状態か
            is_disconnected: ドングル切断状態か
            receive_state: 受信ステータス (ReceiveState または None)

        Returns:
            NotificationLevel: 発報した通知レベル (発報なしは NONE)
        """
        with self._lock:
            # 1. デモモードでは実際の通知を発報しない
            if self.is_demo_mode:
                return NotificationLevel.NONE

            # 2. 誤通知防止条件のチェック:
            # 未取得(None)、スリープ推測(is_stale)、ドングル切断(is_disconnected)、
            # またはNORMAL以外の状態（INITIALIZING, WAITING_DATA, SLEEP_SUSPECTED, DONGLE_DISCONNECTED）は除外
            if percent is None or is_stale or is_disconnected:
                return NotificationLevel.NONE

            if receive_state is not None:
                state_str = getattr(receive_state, "name", str(receive_state))
                if state_str != "NORMAL":
                    return NotificationLevel.NONE

            # 異常値の除外
            if not (0 <= percent <= 100):
                return NotificationLevel.NONE

            # 3. 再アーム判定 (回復時のヒステリシス)
            # 20%警告: 25%超で再アーム
            state_changed = False
            if percent > 25 and self.config.warned_20:
                logger.info(f"残量が25%を超えたため (現在: {percent}%)、20%警告を再アームしました")
                self.config.warned_20 = False
                state_changed = True

            # 10%警告: 15%超で再アーム
            if percent > 15 and self.config.warned_10:
                logger.info(f"残量が15%を超えたため (現在: {percent}%)、10%緊急警告を再アームしました")
                self.config.warned_10 = False
                state_changed = True

            self.config.last_known_percent = percent

            # 4. 通知無効時は発報判定を行わない (状態再アームは保持)
            if not self.config.notifications_enabled:
                if state_changed:
                    self._save_config_locked()
                return NotificationLevel.NONE

            # 5. しきい値評価と発報判定
            triggered_level = NotificationLevel.NONE

            # (A) 10%以下：緊急警告
            if percent <= 10:
                if not self.config.warned_10:
                    title = DEFAULT_TITLE
                    msg = f"バッテリー残量が10%以下です。充電をおすすめします。現在の残量：{percent}%"
                    triggered_level = NotificationLevel.CRITICAL_10

                    # 10%発報時は20%も抑止済みにする（同時重複防止）
                    self.config.warned_10 = True
                    self.config.warned_20 = True
                    self.config.last_notified_at = datetime.datetime.now().isoformat()
                    state_changed = True

                    logger.warning(f"10%緊急警告を発報します (残量: {percent}%)")
                    self._send_notification_safe(title, msg)

            # (B) 11〜20%：低残量警告
            elif percent <= 20:
                if not self.config.warned_20:
                    title = DEFAULT_TITLE
                    msg = f"バッテリー残量が20%以下になりました。現在の残量：{percent}%"
                    triggered_level = NotificationLevel.WARNING_20

                    self.config.warned_20 = True
                    self.config.last_notified_at = datetime.datetime.now().isoformat()
                    state_changed = True

                    logger.warning(f"20%低残量警告を発報します (残量: {percent}%)")
                    self._send_notification_safe(title, msg)

            # 状態変化があった場合は設定をアトミック保存
            if state_changed:
                self._save_config_locked()

            return triggered_level

    def send_test_notification(self) -> bool:
        """テスト通知を1回送信する (通常の20%/10%通知履歴に影響しない)"""
        title = DEFAULT_TITLE
        msg = "LAMZU Thorn V2 Battery Monitorのテスト通知です。"
        logger.info("ユーザー操作によるテスト通知を送信します")
        return self._send_notification_safe(title, msg)

    def _send_notification_safe(self, title: str, message: str) -> bool:
        """例外を安全に捕捉して通知を送信"""
        try:
            return self.notifier.show(title, message)
        except Exception as e:
            logger.error(f"通知送信処理中に例外が発生しました: {e}", exc_info=True)
            return False

    def _save_config_locked(self) -> None:
        """設定データをアトミックにファイル保存 (ロック保持前提)

        icon_styleなど他モジュールが書き込んだ未知の既存キーを消失させずに保持する。
        GLOBAL_CONFIG_LOCKによりConfigManagerとのプロセス内書き込み競合を防止する。
        """
        try:
            from config_manager import GLOBAL_CONFIG_LOCK
        except ImportError:
            GLOBAL_CONFIG_LOCK = threading.RLock()

        with GLOBAL_CONFIG_LOCK:
            if not self.config_path:
                return
            try:
                if self.config_dir:
                    os.makedirs(self.config_dir, exist_ok=True)

                merged_data = {}
                if os.path.exists(self.config_path):
                    try:
                        with open(self.config_path, "r", encoding="utf-8") as f:
                            loaded = json.load(f)
                            if isinstance(loaded, dict):
                                merged_data = loaded
                    except Exception:
                        pass

                merged_data.update(asdict(self.config))
                temp_path = self.config_path + ".tmp"
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(merged_data, f, ensure_ascii=False, indent=2)
                # アトミックな置き換え
                os.replace(temp_path, self.config_path)
                logger.debug(f"通知設定を永続化しました: {self.config_path}")
            except Exception as e:
                logger.error(f"通知設定の保存に失敗しました: {e}", exc_info=True)

    def _load_config(self) -> None:
        """設定ファイルから読み込み、存在しない・破損時は安全に初期化"""
        if not self.config_path or not os.path.exists(self.config_path):
            logger.info("通知設定ファイルが存在しないため、デフォルト値で初期化します")
            return

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.config = NotificationConfig(
                notifications_enabled=bool(data.get("notifications_enabled", True)),
                warned_20=bool(data.get("warned_20", False)),
                warned_10=bool(data.get("warned_10", False)),
                last_notified_at=data.get("last_notified_at"),
                last_known_percent=data.get("last_known_percent")
            )
            logger.info(f"通知設定を読み込みました (enabled={self.config.notifications_enabled}, warned_20={self.config.warned_20}, warned_10={self.config.warned_10})")
        except Exception as e:
            logger.warning(f"通知設定ファイルが破損しているか読み込めないため、安全なデフォルト値で復旧します ({e})")
            self.config = NotificationConfig()
            # 破損ファイルを上書き修復
            self._save_config_locked()
