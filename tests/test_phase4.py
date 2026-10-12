"""LAMZU Thorn V2 自動起動・多重起動防止単体テスト

自動起動管理 (AutostartManager)、多重起動防止 (SingleInstanceChecker)、
ログ設定などの動作を検証します。
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from autostart_manager import AutostartManager, RUN_KEY_PATH, APP_NAME
from single_instance import SingleInstanceChecker


class TestAutostartManager(unittest.TestCase):
    """Windows自動起動設定マネージャーのテスト"""

    def setUp(self):
        self.manager = AutostartManager(app_name="TestApp")

    def test_is_packaged_exe_script_mode(self):
        """通常スクリプト実行時、is_packaged_exe()がFalseを返すことの検証"""
        with patch.object(sys, "frozen", False, create=True):
            self.assertFalse(self.manager.is_packaged_exe())

    def test_is_packaged_exe_frozen_mode(self):
        """EXE実行時 (sys.frozen=True)、is_packaged_exe()がTrueを返すことの検証"""
        with patch.object(sys, "frozen", True, create=True):
            self.assertTrue(self.manager.is_packaged_exe())

    def test_get_executable_path_script_mode(self):
        """スクリプト実行時はargv[0]の絶対パスが返ることの検証"""
        with patch.object(sys, "frozen", False, create=True):
            path = self.manager.get_executable_path()
            self.assertTrue(os.path.isabs(path))

    def test_get_executable_path_frozen_mode(self):
        """EXE実行時はsys.executableの絶対パスが返ることの検証"""
        dummy_exe = r"C:\Program Files\Test\app.exe"
        with patch.object(sys, "frozen", True, create=True):
            with patch.object(sys, "executable", dummy_exe):
                path = self.manager.get_executable_path()
                self.assertEqual(path, dummy_exe)

    def test_set_autostart_guarded_in_script_mode(self):
        """スクリプト実行時は安全ガードによりレジストリへの書き込みを行わずFalseを返すこと"""
        with patch.object(sys, "frozen", False, create=True):
            result = self.manager.set_autostart(True)
            self.assertFalse(result)

    def test_set_autostart_enable_in_frozen_mode(self):
        """EXE実行時、有効化処理でwinreg.SetValueExがクォート付きパスで正しく呼ばれること"""
        dummy_exe = r"C:\Test Path With Spaces\app.exe"
        with patch.object(sys, "frozen", True, create=True):
            with patch.object(sys, "executable", dummy_exe):
                with patch("os.path.exists", return_value=True):
                    mock_winreg = MagicMock()
                    mock_key = MagicMock()
                    mock_winreg.OpenKey.return_value.__enter__.return_value = mock_key

                    with patch.dict("sys.modules", {"winreg": mock_winreg}):
                        result = self.manager.set_autostart(True)
                        self.assertTrue(result)
                        mock_winreg.SetValueEx.assert_called_once_with(
                            mock_key,
                            "TestApp",
                            0,
                            mock_winreg.REG_SZ,
                            f'"{dummy_exe}"'
                        )

    def test_set_autostart_disable_in_frozen_mode(self):
        """EXE実行時、無効化処理でwinreg.DeleteValueが正しく呼ばれること"""
        dummy_exe = r"C:\Test\app.exe"
        with patch.object(sys, "frozen", True, create=True):
            with patch.object(sys, "executable", dummy_exe):
                with patch("os.path.exists", return_value=True):
                    mock_winreg = MagicMock()
                    mock_key = MagicMock()
                    mock_winreg.OpenKey.return_value.__enter__.return_value = mock_key

                    with patch.dict("sys.modules", {"winreg": mock_winreg}):
                        result = self.manager.set_autostart(False)
                        self.assertTrue(result)
                        mock_winreg.DeleteValue.assert_called_once_with(mock_key, "TestApp")

    def test_is_autostart_enabled_query(self):
        """is_autostart_enabled()がレジストリ値を正しく読み取ること"""
        mock_winreg = MagicMock()
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value.__enter__.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = ('"C:\\app.exe"', 1)

        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            self.assertTrue(self.manager.is_autostart_enabled())

        mock_winreg.QueryValueEx.side_effect = FileNotFoundError()
        with patch.dict("sys.modules", {"winreg": mock_winreg}):
            self.assertFalse(self.manager.is_autostart_enabled())


class TestSingleInstanceChecker(unittest.TestCase):
    """Windows Named Mutex による多重起動防止のテスト"""

    def test_single_instance_detection(self):
        """同一ミューテックス名で2回インスタンスを生成した際に多重起動が検知されること"""
        test_mutex_name = f"Local\\Test_Mutex_{os.getpid()}"
        checker1 = SingleInstanceChecker(test_mutex_name)
        checker2 = SingleInstanceChecker(test_mutex_name)

        try:
            # 1つ目の起動: 成功 (False)
            is_running1 = checker1.is_already_running()
            self.assertFalse(is_running1)

            # 2つ目の起動: 多重起動検知 (True)
            is_running2 = checker2.is_already_running()
            self.assertTrue(is_running2)

        finally:
            checker2.release()
            checker1.release()

        # ハンドル解放後は再度1つ目として起動可能
        checker3 = SingleInstanceChecker(test_mutex_name)
        try:
            self.assertFalse(checker3.is_already_running())
        finally:
            checker3.release()


if __name__ == "__main__":
    unittest.main()
