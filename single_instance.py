"""LAMZU Thorn V2 多重起動防止モジュール

Windowsの名前付きミューテックス (Named Mutex) を使用して、
同一ユーザーセッション内での多重起動を防止する。

仕様:
  - ミューテックス名: Local\\LAMZU_Thorn_Battery_Monitor_SingleInstance_Mutex
  - 管理者権限不要 (Local\\名前空間によるセッション限定)
  - 既にインスタンスが起動している場合は即座に安全終了 (コード0)
  - プロセス異常終了時もWindowsカーネルによりミューテックスが自動解放されるため安全
"""

import ctypes
import logging
import sys

logger = logging.getLogger("single_instance")

MUTEX_NAME = "Local\\LAMZU_Thorn_Battery_Monitor_SingleInstance_Mutex"
ERROR_ALREADY_EXISTS = 183


class SingleInstanceChecker:
    """Windows Named Mutex による多重起動防止クラス"""

    def __init__(self, mutex_name: str = MUTEX_NAME):
        self.mutex_name = mutex_name
        self.mutex_handle = None
        self._is_already_running = False

    def is_already_running(self) -> bool:
        """多重起動状態かどうかを判定し、ミューテックスを取得"""
        if sys.platform != "win32":
            return False

        try:
            kernel32 = ctypes.windll.kernel32
            # CreateMutexW(lpMutexAttributes, bInitialOwner, lpName)
            self.mutex_handle = kernel32.CreateMutexW(None, False, self.mutex_name)
            last_error = kernel32.GetLastError()

            if last_error == ERROR_ALREADY_EXISTS:
                logger.warning("別のインスタンスが既に起動していることを検知しました (多重起動防止)")
                self._is_already_running = True
                return True

            self._is_already_running = False
            return False
        except Exception as e:
            logger.error(f"ミューテックスの作成中にエラーが発生しました: {e}", exc_info=True)
            return False

    def release(self) -> None:
        """ミューテックスハンドルを安全に解放"""
        if self.mutex_handle and sys.platform == "win32":
            try:
                ctypes.windll.kernel32.CloseHandle(self.mutex_handle)
                self.mutex_handle = None
            except Exception as e:
                logger.debug(f"ミューテックスハンドルの解放エラー: {e}")
