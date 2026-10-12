"""LAMZU Thorn V2 デバイス設定取得およびローディングアニメーション単体テスト

DPI・ポーリングレートの読み取り専用問い合わせ、ホワイトリスト制限、
3点ドットローディングアニメーション、左右2列カードレイアウトの検証を行います。
"""

import unittest
from unittest.mock import MagicMock, patch
import tkinter as tk
import time

import device_query
from battery_state import BatteryState
from status_panel import StatusPanel


class TestPhase51DeviceQuery(unittest.TestCase):
    """device_queryモジュールの検証"""

    def test_allowed_commands_whitelist(self):
        """許可コマンドのホワイトリストが0x80, 0x81, 0x82のみであることの検証"""
        expected_cmds = {0x80, 0x81, 0x82}
        self.assertEqual(set(device_query.ALLOWED_READ_COMMANDS.keys()), expected_cmds)
        # 設定変更コマンド(0x00系)がホワイトリストに存在しないこと
        self.assertNotIn(0x00, device_query.ALLOWED_READ_COMMANDS)
        self.assertNotIn(0x01, device_query.ALLOWED_READ_COMMANDS)
        self.assertNotIn(0x02, device_query.ALLOWED_READ_COMMANDS)

    def test_polling_rate_map_conversion(self):
        """ポーリングレートのコード値からHzへの変換検証 (Aurora準拠)"""
        self.assertEqual(device_query.POLLING_RATE_MAP[8], 125)
        self.assertEqual(device_query.POLLING_RATE_MAP[4], 250)
        self.assertEqual(device_query.POLLING_RATE_MAP[2], 500)
        self.assertEqual(device_query.POLLING_RATE_MAP[1], 1000)
        self.assertEqual(device_query.POLLING_RATE_MAP[32], 2000)
        self.assertEqual(device_query.POLLING_RATE_MAP[64], 4000)
        self.assertEqual(device_query.POLLING_RATE_MAP[128], 8000)
        # 未知のコード値はNoneとなること (推測値フォールバックの禁止)
        self.assertIsNone(device_query.POLLING_RATE_MAP.get(999))

    def test_session_cancellation(self):
        """DeviceQuerySessionのキャンセル動作検証"""
        session = device_query.DeviceQuerySession()
        self.assertFalse(session.is_cancelled)
        session.cancel()
        self.assertTrue(session.is_cancelled)

    @patch("device_query.hid.device")
    @patch("device_query.find_feature_device_path", return_value=b"\\\\?\\HID#VID_37B0&PID_002E&MI_02")
    def test_query_device_settings_success(self, mock_path, mock_hid_dev_cls):
        """正常なHIDレスポンス受信時のパーサー動作検証 (実機仕様: 1600 DPI, 2000 Hz, 3ステージ)"""
        mock_dev = MagicMock()
        mock_hid_dev_cls.return_value = mock_dev

        # 1. 0x82 (Active DPI): res[1]=161, res[6]=130, res[8]=3 (Stage 3, 1-based)
        res_active = [0, 161, 0, 2, 2, 1, 130, 1, 3] + [0] * 56
        # 2. 0x81 (DPI Stages): res[1]=161, res[6]=129, res[8]=3 (3ステージ), [400, 800, 1600]
        res_stages = [0, 161, 0, 2, 14, 1, 129, 1, 3,
                      1, 144, 1, 144,  # 400
                      3, 32, 3, 32,    # 800
                      6, 64, 6, 64]    # 1600
        res_stages += [0] * (65 - len(res_stages))
        # 3. 0x80 (Polling Rate): res[1]=161, res[6]=128, res[8]=32 (2000Hz)
        res_rate = [0, 161, 0, 2, 2, 1, 128, 1, 32] + [0] * 56

        mock_dev.get_feature_report.side_effect = [res_active, res_stages, res_rate]

        res = device_query.query_device_settings()
        self.assertTrue(res['success'])
        self.assertEqual(res['active_stage'], 3)
        self.assertEqual(res['dpi'], 1600)
        self.assertEqual(res['polling_rate'], 2000)
        self.assertEqual(res['stages'], [400, 800, 1600])
        self.assertIsNone(res['error'])
        mock_dev.close.assert_called_once()

    @patch("device_query.hid.device")
    @patch("device_query.find_feature_device_path", return_value=b"\\\\?\\HID#VID_37B0&PID_002E&MI_02")
    def test_query_device_settings_failure_no_fallback(self, mock_path, mock_hid_dev_cls):
        """パース失敗時に推測値(400や1000)へフォールバックせずNoneとなることの検証"""
        mock_dev = MagicMock()
        mock_hid_dev_cls.return_value = mock_dev

        # 不正な応答（全て0）
        invalid_res = [0] * 65
        mock_dev.get_feature_report.return_value = invalid_res

        res = device_query.query_device_settings()
        self.assertFalse(res['success'])
        self.assertIsNone(res['dpi'])
        self.assertIsNone(res['polling_rate'])
        self.assertIsNone(res['active_stage'])
        self.assertEqual(res['stages'], [])
        self.assertIsNotNone(res['error'])


class TestPhase51StatusPanelUI(unittest.TestCase):
    """ステータスパネルのUI描画およびアニメーション検証"""

    @classmethod
    def setUpClass(cls):
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        self.panel = StatusPanel(root=self.root)
        self.state = BatteryState()
        self.state.update_battery(85)

    def tearDown(self):
        self.panel.hide()
        self.panel.destroy()
        try:
            self.root.update()
        except Exception:
            pass

    def test_dimensions_updated(self):
        """パネルのサイズがPhase 5.1仕様 (310x285) であることの検証"""
        self.assertEqual(self.panel.WIDTH, 310)
        self.assertEqual(self.panel.HEIGHT, 285)

    def test_loading_animation_lifecycle(self):
        """3点ドットローディングアニメーションの開始・ステップ・停止検証"""
        with patch("device_query.query_device_settings_async") as mock_async:
            mock_session = MagicMock()
            mock_async.return_value = mock_session

            self.panel.show(self.state)
            self.root.update()

            self.assertTrue(self.panel.is_visible)
            self.assertTrue(self.panel._is_loading)
            self.assertIsNotNone(self.panel._dot_timer_id)

            # アニメーションステップ
            initial_frame = self.panel._dot_frame
            time.sleep(0.35)
            self.root.update()
            # フレームが進んでいること
            self.assertNotEqual(self.panel._dot_frame, initial_frame)

            # hideでアニメーションが安全に停止すること
            self.panel.hide()
            self.root.update()
            self.assertFalse(self.panel.is_visible)
            self.assertFalse(self.panel._is_loading)
            self.assertIsNone(self.panel._dot_timer_id)
            mock_session.cancel.assert_called()

    def test_cached_values_rendering(self):
        """DPIおよびポーリングレートの数値反映描画検証"""
        with patch("device_query.query_device_settings_async"):
            self.panel.show(self.state)
            self.root.update()

            # 取得完了をシミュレート
            self.panel._cached_dpi = 1600
            self.panel._cached_polling_rate = 4000
            self.panel._cached_active_stage = 3
            self.panel._stop_loading_animation()
            self.panel.render(self.state)
            self.root.update()

            # Canvas内に数値が描画されていることをテキスト検索で確認
            items = self.panel.canvas.find_all()
            texts = [self.panel.canvas.itemcget(i, "text") for i in items if self.panel.canvas.type(i) == "text"]
            self.assertIn("1600", texts)
            self.assertIn("4000 Hz", texts)
            self.assertIn("現在のDPI", texts)
            self.assertIn("ポーリングレート", texts)

    def test_cached_values_rendering_dash_when_none(self):
        """DPIおよびポーリングレートが未取得(None)の場合に全角ダッシュ「—」が描画されることの検証"""
        with patch("device_query.query_device_settings_async"):
            self.panel.show(self.state)
            self.root.update()

            self.panel._cached_dpi = None
            self.panel._cached_polling_rate = None
            self.panel._stop_loading_animation()
            self.panel.render(self.state)
            self.root.update()

            items = self.panel.canvas.find_all()
            texts = [self.panel.canvas.itemcget(i, "text") for i in items if self.panel.canvas.type(i) == "text"]
            self.assertIn("—", texts)
            # 400や1000等の推測値が描画されていないこと
            self.assertNotIn("400", texts)
            self.assertNotIn("1000 Hz", texts)


if __name__ == '__main__':
    unittest.main()
