"""LAMZU Thorn V2 Windows自動起動管理モジュール

ユーザーの明示的な操作に基づいて、Windowsログオン時の自動起動を管理する。

仕様:
  - レジストリキー: HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
  - 値名: LAMZUThornBatteryMonitor
  - 管理者権限不要 (HKCUのみ操作、HKLMには一切触れない)
  - 実行ファイルパスに空白・日本語が含まれていても動作するよう適切にクォート
  - 初期状態は無効 (ユーザーの操作なしに自動登録しない)
  - EXE実行時とスクリプト実行時を正しく識別
"""

import logging
import os
import sys
from typing import Optional

logger = logging.getLogger("autostart")

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "LAMZUThornBatteryMonitor"


class AutostartManager:
    """Windows自動起動設定マネージャー"""

    def __init__(self, app_name: str = APP_NAME):
        self.app_name = app_name

    def is_packaged_exe(self) -> bool:
        """PyInstallerまたはNuitkaによってEXE化された実行ファイルかどうか"""
        return getattr(sys, "frozen", False) or "__compiled__" in globals()

    def get_executable_path(self) -> str:
        """実行ファイルの絶対パスを取得"""
        if self.is_packaged_exe():
            return os.path.abspath(sys.executable)
        # 開発実行時 (python app.py)
        return os.path.abspath(sys.argv[0])

    def is_autostart_enabled(self) -> bool:
        """自動起動が現在有効化されているかレジストリを確認"""
        if sys.platform != "win32":
            return False

        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
                try:
                    val, _ = winreg.QueryValueEx(key, self.app_name)
                    return bool(val)
                except FileNotFoundError:
                    return False
        except Exception as e:
            logger.debug(f"自動起動状態の取得に失敗しました: {e}")
            return False

    def set_autostart(self, enable: bool) -> bool:
        """自動起動の有効/無効を切り替える

        Args:
            enable: Trueで自動起動登録、Falseで登録解除

        Returns:
            bool: 処理が成功したかどうか
        """
        if sys.platform != "win32":
            logger.warning("Windows以外のプラットフォームでは自動起動に対応していません")
            return False

        # 開発中のスクリプト実行時は誤登録防止のため警告して拒否
        if not self.is_packaged_exe():
            logger.warning("スクリプト直接実行モードでは誤登録防止のため自動起動の登録を行いません (EXEビルド後に有効化してください)")
            return False

        exe_path = self.get_executable_path()
        if not os.path.exists(exe_path):
            logger.error(f"実行可能ファイルが見つかりません: {exe_path}")
            return False

        # 空白や日本語を含むパスに対応するためダブルクォートで囲む
        cmd_value = f'"{exe_path}"'

        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                if enable:
                    winreg.SetValueEx(key, self.app_name, 0, winreg.REG_SZ, cmd_value)
                    logger.info(f"Windows自動起動を有効化しました: {cmd_value}")
                else:
                    try:
                        winreg.DeleteValue(key, self.app_name)
                        logger.info("Windows自動起動を無効化 (登録削除) しました")
                    except FileNotFoundError:
                        # 既に登録されていない場合は正常
                        pass
            return True
        except Exception as e:
            logger.error(f"自動起動設定の変更に失敗しました (enable={enable}): {e}", exc_info=True)
            return False
