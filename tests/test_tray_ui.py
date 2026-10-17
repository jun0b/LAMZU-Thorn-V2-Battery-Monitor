"""LAMZU Thorn V2 トレイUIモジュールの単体テスト

メニュー構造、コールバック、動的メニュー更新(update_menu)、
ホバー表示とメニューの同期、不必要な更新の抑制、終了後の安全性等を検証します。
"""

import unittest
from unittest.mock import MagicMock
from battery_state import BatteryState, ReceiveState, ChargingState
from tray_ui import TrayUI


class TestTrayUI(unittest.TestCase):
    """TrayUIクラスのテストケース"""

    def test_menu_structure(self):
        """右クリックメニュー構造（Phase 4.2仕様順序）と不要項目除外の検証"""
        state = BatteryState()
        state.update_battery(100)

        ui = TrayUI(state)
        menu = ui.build_menu()

        self.assertIsNotNone(menu)
        items = list(menu.items)

        # 各メニューテキストの取得
        texts = [item.text(item) if callable(item.text) else item.text for item in items if hasattr(item, "text")]

        # 右クリックメニューから撤去された項目の非存在検証
        self.assertFalse(any(t == "LAMZU Thorn V2" for t in texts), "無効化タイトルヘッダーが残存しています")
        self.assertFalse(any("バッテリー:" in str(t) for t in texts), "無効化バッテリー残量項目が残存しています")
        self.assertFalse(any("受信状態:" in str(t) for t in texts), "無効化受信状態項目が残存しています")
        self.assertFalse(any("最終更新:" in str(t) for t in texts), "無効化最終更新時刻項目が残存しています")
        self.assertFalse(any("ログフォルダを開く" in str(t) for t in texts), "撤去対象のログフォルダ項目が残存しています")

        # 要求される必須項目の存在検証
        self.assertIn("低残量通知を有効にする", texts)
        self.assertIn("テスト通知を送信", texts)
        self.assertIn("Windows起動時に自動起動", texts)
        self.assertIn("アイコンデザイン", texts)
        self.assertIn("LAMZU Auroraを開く", texts)
        self.assertIn("終了", texts)

    def test_demo_tooltip_title(self):
        """デモモード時にツールチップに[DEMO]が含まれることの検証"""
        state = BatteryState(is_demo_mode=True)
        ui = TrayUI(state)
        mock_icon = MagicMock()
        ui._icon = mock_icon
        ui._is_running = True
        ui.update_ui()
        self.assertIn("[DEMO] LAMZU Thorn V2", mock_icon.title)

    def test_battery_change_updates_status_panel_and_tooltip(self):
        """残量更新時にホバーツールチップとステータスパネルが更新されることの検証"""
        state = BatteryState()
        mock_panel = MagicMock()
        ui = TrayUI(state, status_panel=mock_panel)

        mock_icon = MagicMock()
        ui._icon = mock_icon
        ui._is_running = True

        # 99%を受信して更新
        state.update_battery(99, status_code=0x00)
        ui.update_ui()

        # ツールチップが99%に更新され、ステータスパネルのupdate_stateが呼ばれたこと
        self.assertIn("99%", mock_icon.title)
        mock_panel.update_state.assert_called_with(state)

    def test_hover_shows_correct_battery_text(self):
        """ホバー表示がBatteryStateの残量を正しく反映することの検証"""
        state = BatteryState()
        state.update_battery(95)
        ui = TrayUI(state)

        mock_icon = MagicMock()
        ui._icon = mock_icon
        ui._is_running = True
        ui.update_ui()

        self.assertEqual(mock_icon.title, "LAMZU Thorn V2 - Battery: 95%")

    def test_left_click_toggles_status_panel(self):
        """左クリックハンドラーがステータスパネルのtoggleを呼び出すことの検証"""
        state = BatteryState()
        mock_panel = MagicMock()
        ui = TrayUI(state, status_panel=mock_panel)

        ui._handle_left_click()
        mock_panel.toggle.assert_called_once_with(state)

    def test_safe_handling_after_ui_stopped(self):
        """アプリ終了(stop)後の更新要求がエラーなく安全に無視されることの検証"""
        state = BatteryState()
        ui = TrayUI(state)
        mock_icon = MagicMock()
        ui._icon = mock_icon
        ui._is_running = True

        # 終了実行
        ui.stop()
        self.assertFalse(ui._is_running)

        # 終了後にupdate_uiや_update_menu_safeを呼んでも例外が発生しないこと
        try:
            ui.update_ui()
            ui._update_menu_safe(reason="終了後テスト")
        except Exception as e:
            self.fail(f"終了後の呼び出しで例外が発生しました: {e}")

    def test_notification_menu_integration(self):
        """トレイメニューの通知ON/OFF切り替えとテスト通知呼び出しの検証"""
        mock_notif_manager = MagicMock()
        mock_notif_manager.notifications_enabled = True

        state = BatteryState()
        ui = TrayUI(state, notification_manager=mock_notif_manager)
        mock_icon = MagicMock()
        ui._icon = mock_icon
        ui._is_running = True

        menu = ui.build_menu()
        items = list(menu.items)

        # 1. メニュー項目の存在確認
        toggle_item = next((item for item in items if getattr(item, "text", None) == "低残量通知を有効にする"), None)
        test_item = next((item for item in items if getattr(item, "text", None) == "テスト通知を送信"), None)

        self.assertIsNotNone(toggle_item)
        self.assertIsNotNone(test_item)
        self.assertTrue(toggle_item.checked)

        # 2. トグル実行
        ui._handle_toggle_notifications(mock_icon, toggle_item)
        mock_notif_manager.set_enabled.assert_called_with(False)
        mock_icon.update_menu.assert_called()

        # 3. テスト通知実行
        ui._handle_send_test_notification(mock_icon, test_item)
        mock_notif_manager.send_test_notification.assert_called_once()

    def test_charging_state_change_triggers_icon_redraw(self):
        """残量が同一でも充電状態が変化した際にアイコンが再描画されることの検証"""
        state = BatteryState()
        state.set_dongle_available(True)
        state.update_battery(80, status_code=0x00, charging_state=ChargingState.NOT_CHARGING)  # 非充電 (80%)
        ui = TrayUI(state)

        mock_icon = MagicMock()
        icon_setter = unittest.mock.PropertyMock()
        type(mock_icon).icon = icon_setter
        ui._icon = mock_icon
        ui._is_running = True

        # 初回UI更新
        ui.update_ui()
        self.assertEqual(icon_setter.call_count, 1)
        self.assertFalse(ui._last_icon_charging)

        # 同一状態のまま再呼び出し（再描画されないことの検証）
        ui.update_ui()
        self.assertEqual(icon_setter.call_count, 1)

        # 残量は80%のまま充電中に変化 (status_code=0x04, charging_state=CHARGING)
        state.update_battery(80, status_code=0x04, charging_state=ChargingState.CHARGING)
        ui.update_ui()

        # 充電状態が変化したためアイコンが再描画されること
        self.assertEqual(icon_setter.call_count, 2)
        self.assertTrue(ui._last_icon_charging)

        # ケーブル取り外しで非充電 (status_code=0x00, charging_state=NOT_CHARGING) に戻った場合
        state.update_battery(80, status_code=0x00, charging_state=ChargingState.NOT_CHARGING)
        ui.update_ui()
        self.assertEqual(icon_setter.call_count, 3)
        self.assertFalse(ui._last_icon_charging)

    def test_unchanged_charging_state_suppresses_redraw(self):
        """充電状態および残量が変化しない場合は再描画が抑制されることの検証"""
        state = BatteryState()
        state.set_dongle_available(True)
        state.update_battery(100, status_code=0x04, charging_state=ChargingState.CHARGING)  # 充電中 (100%)
        ui = TrayUI(state)

        mock_icon = MagicMock()
        icon_setter = unittest.mock.PropertyMock()
        type(mock_icon).icon = icon_setter
        ui._icon = mock_icon
        ui._is_running = True

        # 1回目の更新
        ui.update_ui()
        self.assertEqual(icon_setter.call_count, 1)
        self.assertTrue(ui._last_icon_charging)

        # 2回目の更新（状態変化なし）
        ui.update_ui()
        self.assertEqual(icon_setter.call_count, 1)

    def test_demo_mode_charging_state(self):
        """デモモードでも充電状態が正常に反映されエラーなくトレイUIが更新されることの検証"""
        state = BatteryState(is_demo_mode=True)
        state.set_dongle_available(True)
        state.update_battery(75, status_code=0x04, charging_state=ChargingState.CHARGING)
        ui = TrayUI(state)
        mock_icon = MagicMock()
        ui._icon = mock_icon
        ui._is_running = True

        ui.update_ui()
        self.assertTrue(ui._last_icon_charging)
        self.assertIn("[DEMO]", mock_icon.title)

    def test_charging_complete_state_change_triggers_icon_redraw(self):
        """100%充電中(0x04)から100%充電完了(0x02)へ変化した際にアイコンが再描画されることの検証"""
        state = BatteryState()
        state.set_dongle_available(True)
        state.update_battery(100, status_code=0x04, charging_state=ChargingState.CHARGING)
        ui = TrayUI(state)

        mock_icon = MagicMock()
        icon_setter = unittest.mock.PropertyMock()
        type(mock_icon).icon = icon_setter
        ui._icon = mock_icon
        ui._is_running = True

        # 初回更新 (充電中 100%)
        ui.update_ui()
        self.assertEqual(icon_setter.call_count, 1)
        self.assertTrue(ui._last_icon_charging)
        self.assertFalse(ui._last_icon_charging_complete)

        # 残量100%のまま充電完了 (0x02) に遷移
        state.update_battery(100, status_code=0x02, charging_state=ChargingState.CHARGING_COMPLETE)
        ui.update_ui()
        self.assertEqual(icon_setter.call_count, 2)
        self.assertFalse(ui._last_icon_charging)
        self.assertTrue(ui._last_icon_charging_complete)


if __name__ == "__main__":
    unittest.main()
