"""LAMZU Thorn V2 アプリケーション設定永続化モジュール

%LOCALAPPDATA%\\LAMZUThornBatteryMonitor\\config.json の読み書きをスレッドセーフかつ
アトミックに管理する。

仕様:
  - 単一の設定ファイルでトレイアイコンスタイル、低残量通知設定、通知履歴を共存管理
  - 未知の既存キーを消失させずに保持 (前方互換性・将来拡張対応)
  - 一時ファイル経由のos.replaceによるアトミック書き込み
  - ファイル破損時の安全な復旧とバックアップ
  - 不正なスタイル名が指定された場合の自動フォールバック (numbers-battery)
  - 変更がない場合の不要なディスク書き込み抑制
"""

import json
import logging
import os
import shutil
import threading
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("config")

# プロセス内設定ファイル書き込み排他ロック
GLOBAL_CONFIG_LOCK = threading.RLock()

DEFAULT_STYLE = "numbers-battery"
SUPPORTED_STYLES: Tuple[str, ...] = (
    "numbers-only",       # 数字のみ
    "battery-only",       # バッテリーのみ
    "numbers-battery",    # 数字+バッテリー表示 (デフォルト)
)

STYLE_DISPLAY_NAMES: Dict[str, str] = {
    "numbers-only": "数字のみ",
    "battery-only": "バッテリーのみ",
    "numbers-battery": "数字+バッテリー表示",
}

# 既存設定の移行マッピングテーブル
STYLE_MIGRATION: Dict[str, str] = {
    "numbers-only": "numbers-only",
    "battery-only": "battery-only",
    "numbers-battery": "numbers-battery",
    # 旧スタイルの互換移行先
    "top-a3": "numbers-battery",
    "top-a1": "numbers-battery",
    "top-a2": "numbers-battery",
    "top": "numbers-battery",
    "bottom": "numbers-battery",
    "overlay": "numbers-battery",
}


def get_default_config_path() -> str:
    """デフォルトの設定ファイルパスを取得"""
    local_appdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
    return os.path.join(local_appdata, "LAMZUThornBatteryMonitor", "config.json")


class ConfigManager:
    """スレッドセーフかつアトミックな設定マネージャー"""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = os.path.abspath(config_path) if config_path else get_default_config_path()
        self.config_dir = os.path.dirname(self.config_path)
        self._lock = threading.RLock()
        self._data: Dict[str, Any] = {}
        self._modified_keys: set = set()
        self.load()

    def load(self) -> None:
        """設定ファイルから読み込み、存在しないまたは破損時は安全に初期化"""
        with self._lock:
            if not os.path.exists(self.config_path):
                logger.info(f"設定ファイルが存在しないため、デフォルト設定で初期化します: {self.config_path}")
                self._data = self._get_default_dict()
                return

            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if not content:
                    logger.warning("設定ファイルが空のため、デフォルト設定を使用します")
                    self._data = self._get_default_dict()
                    return

                loaded = json.loads(content)
                if not isinstance(loaded, dict):
                    raise ValueError("設定ファイルのルートが辞書形式ではありません")

                self._data = loaded
                # 旧スタイルおよび無効値の移行
                raw_style = self._data.get("icon_style")
                migrated_style = STYLE_MIGRATION.get(raw_style, DEFAULT_STYLE)
                if migrated_style != raw_style:
                    logger.info(f"アイコンスタイル '{raw_style}' を '{migrated_style}' へ移行しました")
                self._data["icon_style"] = migrated_style

                logger.debug(f"設定ファイルを正常に読み込みました: {self.config_path}")

            except Exception as e:
                logger.warning(f"設定ファイルが破損しているか読み込めないため、安全なデフォルト値で復旧します: {e}")
                # 破損ファイルのバックアップ
                try:
                    backup_path = self.config_path + ".corrupted.bak"
                    shutil.copy2(self.config_path, backup_path)
                    logger.info(f"破損した設定ファイルをバックアップしました: {backup_path}")
                except Exception:
                    pass

                self._data = self._get_default_dict()
                self._save_locked()

    def _get_default_dict(self) -> Dict[str, Any]:
        """デフォルト設定辞書"""
        return {
            "icon_style": DEFAULT_STYLE,
            "notifications_enabled": True,
            "warned_20": False,
            "warned_10": False,
            "last_notified_at": None,
            "last_known_percent": None
        }

    def _save_locked(self) -> bool:
        """設定をアトミックに保存する (ロック保持前提)"""
        with GLOBAL_CONFIG_LOCK:
            try:
                if self.config_dir:
                    os.makedirs(self.config_dir, exist_ok=True)

                disk_data = {}
                if os.path.exists(self.config_path):
                    try:
                        with open(self.config_path, "r", encoding="utf-8") as f:
                            loaded = json.load(f)
                            if isinstance(loaded, dict):
                                disk_data = loaded
                    except Exception:
                        pass

                # ディスクが存在し、かつ本インスタンスでの変更キーがない場合は、
                # 他の管理処理が保存した最新のディスク設定を破壊しないよう、
                # メモリ上データをディスク内容と同期するのみで不要な上書きを回避する
                if disk_data and not self._modified_keys:
                    self._data = dict(disk_data)
                    return True

                merged_data = dict(disk_data)
                if self._modified_keys:
                    for k in self._modified_keys:
                        if k in self._data:
                            merged_data[k] = self._data[k]
                else:
                    # ディスクが空（新規作成時）のみ全フィールドを保存
                    merged_data = dict(self._data)

                temp_path = self.config_path + ".tmp"
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(merged_data, f, ensure_ascii=False, indent=2)
                os.replace(temp_path, self.config_path)

                # 保存成功後に初めて変更キーをクリアし、メモリ状態を更新する
                self._data = merged_data
                self._modified_keys.clear()

                logger.debug(f"設定ファイルをアトミックに保存した: {self.config_path}")
                return True
            except Exception as e:
                logger.error(f"設定ファイルの保存中にエラーが発生した: {e}", exc_info=True)
                return False

    # ==========================================
    # アイコンスタイル関連
    # ==========================================

    @property
    def icon_style(self) -> str:
        """現在のアイコンスタイル名を取得"""
        with self._lock:
            style = self._data.get("icon_style", DEFAULT_STYLE)
            if style not in SUPPORTED_STYLES:
                return DEFAULT_STYLE
            return style

    def set_icon_style(self, style: str) -> bool:
        """アイコンスタイルを変更して永続化

        Returns:
            bool: 実際に値が変更されて保存されたかどうか
        """
        norm_style = STYLE_MIGRATION.get(style)
        if not norm_style or norm_style not in SUPPORTED_STYLES:
            logger.warning(f"未対応のアイコンスタイル '{style}' が指定されたため無視します")
            return False
        style = norm_style

        with self._lock:
            current = self._data.get("icon_style")
            if current == style:
                return False  # 同一値の場合は不要な書き込みを抑制

            self._data["icon_style"] = style
            self._modified_keys.add("icon_style")
            logger.info(f"アイコンスタイルを '{current}' から '{style}' に変更しました")
            return self._save_locked()

    # ==========================================
    # 低残量通知関連
    # ==========================================

    @property
    def notifications_enabled(self) -> bool:
        with self._lock:
            return bool(self._data.get("notifications_enabled", True))

    def set_notifications_enabled(self, enabled: bool) -> bool:
        with self._lock:
            if self._data.get("notifications_enabled") == enabled:
                return False
            self._data["notifications_enabled"] = enabled
            self._modified_keys.add("notifications_enabled")
            logger.info(f"低残量通知の有効状態を変更しました: {enabled}")
            return self._save_locked()

    @property
    def warned_20(self) -> bool:
        with self._lock:
            return bool(self._data.get("warned_20", False))

    @warned_20.setter
    def warned_20(self, value: bool) -> None:
        with self._lock:
            self._data["warned_20"] = value
            self._modified_keys.add("warned_20")

    @property
    def warned_10(self) -> bool:
        with self._lock:
            return bool(self._data.get("warned_10", False))

    @warned_10.setter
    def warned_10(self, value: bool) -> None:
        with self._lock:
            self._data["warned_10"] = value
            self._modified_keys.add("warned_10")

    @property
    def last_notified_at(self) -> Optional[str]:
        with self._lock:
            return self._data.get("last_notified_at")

    @last_notified_at.setter
    def last_notified_at(self, value: Optional[str]) -> None:
        with self._lock:
            self._data["last_notified_at"] = value
            self._modified_keys.add("last_notified_at")

    @property
    def last_known_percent(self) -> Optional[int]:
        with self._lock:
            return self._data.get("last_known_percent")

    @last_known_percent.setter
    def last_known_percent(self, value: Optional[int]) -> None:
        with self._lock:
            self._data["last_known_percent"] = value
            self._modified_keys.add("last_known_percent")

    def save(self) -> bool:
        """現在のメモリ上データをファイルへ保存"""
        with self._lock:
            return self._save_locked()

    def get_raw_data(self) -> Dict[str, Any]:
        """内部データのコピーを取得 (検証・テスト用)"""
        with self._lock:
            return dict(self._data)
