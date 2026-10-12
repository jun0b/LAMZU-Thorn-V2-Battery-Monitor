# -*- coding: utf-8 -*-
"""受信状態遷移・パケット処理・設定永続化・デバイス問い合わせの機能整合性テスト

1. 形式B補助パケット受信時の充電状態更新および残量保護
2. ConfigManagerの設定値永続化および未知設定項目の保持
3. DeviceQueryの許可コマンド検証およびセッション即時キャンセル
4. StatusPanelの世代管理による非同期問い合わせ結果の整合性保持
5. ドングル切断・再接続およびスリープ推測・復帰時の状態遷移と通知制御
"""

import json
import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch

from battery_state import BatteryState, ReceiveState, ChargingState
import config_manager
from config_manager import ConfigManager
import device_query
from notification_manager import NotificationManager
from battery_protocol import parse_packet, PacketType


class TestFormatBFixes(unittest.TestCase):
    """形式Bパケット受信時の処理に関するテスト"""

    def setUp(self):
        self.state = BatteryState()

    def test_format_b_updates_charging_state_without_nameerror(self):
        """形式Bパケット受信時にChargingStateが正しく反映され例外が発生しないことを検証"""
        # 初期の通常パケットを受信させて残量95%・非充電にしておく
        self.state.update_battery(
            percent=95,
            charging_state=ChargingState.NOT_CHARGING
        )
        self.assertEqual(self.state.battery_percent, 95)
        self.assertEqual(self.state.charging_state, ChargingState.NOT_CHARGING)
        self.assertFalse(self.state.is_charging)

        # リスナーを登録
        listener_called = []
        self.state.add_listener(lambda s: listener_called.append(s.charging_state))

        # 形式Bパケット（充電中）を受信
        self.state.update_non_battery_packet(charging_state=ChargingState.CHARGING)

        # 残量が維持され、充電状態がCHARGINGに更新されていること
        self.assertEqual(self.state.battery_percent, 95)
        self.assertEqual(self.state.charging_state, ChargingState.CHARGING)
        self.assertTrue(self.state.is_charging)
        self.assertEqual(len(listener_called), 1)
        self.assertEqual(listener_called[0], ChargingState.CHARGING)

    def test_format_b_ignores_unknown_charging_state(self):
        """充電状態がUNKNOWNの形式Bパケットでは充電状態を更新しないことを検証"""
        self.state.update_battery(
            percent=80,
            charging_state=ChargingState.CHARGING
        )
        self.state.update_non_battery_packet(charging_state=ChargingState.UNKNOWN)
        self.assertEqual(self.state.charging_state, ChargingState.CHARGING)


class TestConfigPersistenceFixes(unittest.TestCase):
    """設定ファイルの永続化とマージ処理に関するテスト"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.config_path = os.path.join(self.test_dir, "config.json")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_save_preserves_memory_updates_and_unknown_disk_keys(self):
        """notifications_enabled等の値が古いディスク値で上書きされず、未知キーが保持されることを検証"""
        # 1. ディスクにあらかじめ未知キーと notifications_enabled: true を書き込んでおく
        initial_disk_data = {
            "icon_style": "numbers-battery",
            "notifications_enabled": True,
            "custom_user_key": "special_value_123"
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(initial_disk_data, f)

        # 2. ConfigManagerを起動
        mgr = ConfigManager(config_path=self.config_path)
        self.assertTrue(mgr.notifications_enabled)
        self.assertEqual(mgr.get_raw_data().get("custom_user_key"), "special_value_123")

        # 3. notifications_enabled を False に変更
        mgr.set_notifications_enabled(False)
        self.assertFalse(mgr.notifications_enabled)

        # 4. ディスク上の内容を確認
        with open(self.config_path, "r", encoding="utf-8") as f:
            saved_data = json.load(f)
        self.assertFalse(saved_data["notifications_enabled"])
        self.assertEqual(saved_data["custom_user_key"], "special_value_123")

        # 5. 再度 True に戻す
        mgr.set_notifications_enabled(True)
        with open(self.config_path, "r", encoding="utf-8") as f:
            saved_data2 = json.load(f)
        self.assertTrue(saved_data2["notifications_enabled"])
        self.assertEqual(saved_data2["custom_user_key"], "special_value_123")

    def test_save_without_modified_keys_syncs_from_disk_without_overwriting(self):
        """変更キーがない状態でsaveが呼ばれた場合、ディスク上の最新設定をメモリへ同期し上書きしないことを検証"""
        # 初期設定をディスクに用意
        initial_data = {
            "icon_style": "numbers-only",
            "notifications_enabled": True
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(initial_data, f)

        mgr = ConfigManager(config_path=self.config_path)
        self.assertEqual(mgr.icon_style, "numbers-only")
        self.assertEqual(len(mgr._modified_keys), 0)

        # 外部プロセス等によってディスク上の設定が書き換えられた状況を再現
        external_updated_data = {
            "icon_style": "battery-only",
            "notifications_enabled": False,
            "external_added_key": "updated_by_other_process"
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(external_updated_data, f)

        # 変更キーがない状態で save() を呼び出し
        save_result = mgr.save()
        self.assertTrue(save_result)

        # ディスク上の内容が古いメモリ値 ('numbers-only') で上書きされず保持されていること
        with open(self.config_path, "r", encoding="utf-8") as f:
            disk_after = json.load(f)
        self.assertEqual(disk_after["icon_style"], "battery-only")
        self.assertEqual(disk_after["external_added_key"], "updated_by_other_process")

        # メモリ上のデータもディスクの内容と同期されていること
        self.assertEqual(mgr.icon_style, "battery-only")
        self.assertFalse(mgr.notifications_enabled)

    def test_save_failure_retains_modified_keys(self):
        """設定保存が失敗した場合に変更キーが破棄されず保持されることを検証"""
        mgr = ConfigManager(config_path=self.config_path)
        # 変更を加える
        mgr._data["icon_style"] = "battery-only"
        mgr._modified_keys.add("icon_style")

        # os.replace で例外を発生させる
        with patch("os.replace", side_effect=OSError("ディスク書き込み権限エラー")):
            save_result = mgr._save_locked()
            self.assertFalse(save_result)

        # 保存が失敗したため変更キーが依然として残っていること
        self.assertIn("icon_style", mgr._modified_keys)



class TestDeviceQuerySecurity(unittest.TestCase):
    """HID問い合わせコマンドのセキュリティとキャンセル機能のテスト"""

    def test_allowed_commands_validation(self):
        """許可されていないコマンドを送信しようとした場合にValueErrorが発生することを検証"""
        unauthorized_cmd = 0x85  # 未許可
        mock_device = MagicMock()
        cmd_buf = bytearray(65)
        cmd_buf[6] = unauthorized_cmd

        with self.assertRaises(ValueError):
            device_query._send_and_receive(mock_device, cmd_buf, unauthorized_cmd)

    def test_session_cancel_aborts_immediately(self):
        """セッションがキャンセルされた場合、即座にクエリが中止されることを検証"""
        session = device_query.DeviceQuerySession()
        session.cancel()
        self.assertTrue(session.is_cancelled)

        with patch("device_query.find_feature_device_path", return_value=b"dummy_path"), \
             patch("hid.device") as mock_hid_class:
            mock_dev = MagicMock()
            mock_hid_class.return_value = mock_dev

            res = device_query.query_device_settings(session=session)
            self.assertEqual(res.get("error"), "キャンセルされました")
            mock_dev.send_feature_report.assert_not_called()


class TestStatusPanelGeneration(unittest.TestCase):
    """StatusPanelのクエリ世代管理とキュー処理のテスト"""

    def test_stale_generation_result_is_discarded(self):
        """古い世代の問い合わせ結果が破棄され、キャッシュやUIに反映されないことを検証"""
        from status_panel import StatusPanel
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        try:
            panel = StatusPanel(root=root)
            panel._is_visible = True
            panel._query_generation = 2  # 現在の世代を2に設定

            # 世代1 (古い世代) の結果をキューに投入
            old_result = {
                'success': True,
                'dpi': 3200,
                'polling_rate': 4000,
                'active_stage': 4
            }
            panel._result_queue.put((1, old_result))

            # キュー処理を実行
            panel._process_query_results()

            # 反映されていないことを確認
            self.assertIsNone(panel._cached_dpi)
            self.assertIsNone(panel._cached_polling_rate)

            # 世代2 (現行世代) の結果をキューに投入
            new_result = {
                'success': True,
                'dpi': 1600,
                'polling_rate': 2000,
                'active_stage': 3
            }
            panel._result_queue.put((2, new_result))
            panel._process_query_results()

            # 現行世代は正しく反映される
            self.assertEqual(panel._cached_dpi, 1600)
            self.assertEqual(panel._cached_polling_rate, 2000)
            self.assertEqual(panel._cached_active_stage, 3)
        finally:
            panel.destroy()
            root.destroy()

    def test_hidden_panel_discards_results(self):
        """パネルが非表示の場合は現行世代の結果であっても破棄されることを検証"""
        from status_panel import StatusPanel
        import tkinter as tk

        root = tk.Tk()
        root.withdraw()
        try:
            panel = StatusPanel(root=root)
            panel._is_visible = False
            panel._query_generation = 1

            result = {
                'success': True,
                'dpi': 800,
                'polling_rate': 1000,
                'active_stage': 2
            }
            panel._result_queue.put((1, result))
            panel._process_query_results()

            # 非表示のため反映されない
            self.assertIsNone(panel._cached_dpi)
        finally:
            panel.destroy()
            root.destroy()


class TestReconnectionAndNotificationFixes(unittest.TestCase):
    """再接続時の状態遷移・古い残量無効化・誤通知防止の検証テスト"""

    def setUp(self):
        self.state = BatteryState()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "test_config.json")
        self.mock_notifier = MagicMock()
        self.notif_manager = NotificationManager(
            config_path=self.config_path,
            notifier=self.mock_notifier,
            is_demo_mode=False
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_reconnection_flow_format_b_and_format_a(self):
        """切断→再接続→形式B受信でNORMALへ復帰せず、新しい形式Aで復帰することを検証"""
        # 1. 初期: 97%取得
        self.state.update_battery(97, status_code=0x02, charging_state=ChargingState.NOT_CHARGING)
        self.assertEqual(self.state.receive_state, ReceiveState.NORMAL)
        self.assertEqual(self.state.percent, 97)

        # 2. 切断
        self.state.set_dongle_available(False)
        self.assertEqual(self.state.receive_state, ReceiveState.DONGLE_DISCONNECTED)
        self.assertIsNone(self.state.percent)
        self.assertEqual(self.state.battery_percent, 97)

        # 3. 再接続 -> WAITING_DATA
        self.state.set_dongle_available(True)
        self.assertEqual(self.state.receive_state, ReceiveState.WAITING_DATA)
        self.assertIsNone(self.state.percent)  # WAITING_DATA中は未取得扱い

        # 4. 形式Bのみ受信 -> WAITING_DATAを維持しNORMALに戻らない
        self.state.update_non_battery_packet(charging_state=ChargingState.CHARGING)
        self.assertEqual(self.state.receive_state, ReceiveState.WAITING_DATA)
        self.assertIsNone(self.state.percent)
        self.assertFalse(self.state.is_charging)

        # 5. 新しい形式Aを受信 -> NORMALへ復帰
        self.state.update_battery(96, status_code=0x02, charging_state=ChargingState.NOT_CHARGING)
        self.assertEqual(self.state.receive_state, ReceiveState.NORMAL)
        self.assertEqual(self.state.percent, 96)
        self.assertEqual(self.state.battery_percent, 96)

    def test_no_false_notification_on_reconnection_with_old_low_battery(self):
        """過去残量10%の状態でドングル再接続しても誤通知が発報されないことを検証"""
        # app.pyと同様の通知リスナーを再現
        def on_battery_update(updated_state: BatteryState):
            if updated_state.receive_state != ReceiveState.NORMAL:
                return
            self.notif_manager.evaluate_battery(
                percent=updated_state.percent,
                is_stale=updated_state.is_stale,
                is_disconnected=updated_state.is_disconnected,
                receive_state=updated_state.receive_state
            )

        self.state.add_listener(on_battery_update)

        # 1. 以前の接続で10%を受信して緊急通知が1回発報されたと仮定
        self.state.update_battery(10, charging_state=ChargingState.NOT_CHARGING)
        self.assertEqual(self.mock_notifier.show.call_count, 1)

        # 2. ドングル切断
        self.state.set_dongle_available(False)
        self.assertEqual(self.mock_notifier.show.call_count, 1)

        # 3. ドングル再接続 -> WAITING_DATA
        self.state.set_dongle_available(True)
        # WAITING_DATA移行契機で誤通知が発生しないこと
        self.assertEqual(self.mock_notifier.show.call_count, 1)

        # 4. 形式B受信契機でも通知が発生しないこと
        self.state.update_non_battery_packet(charging_state=ChargingState.CHARGING)
        self.assertEqual(self.mock_notifier.show.call_count, 1)

        # 5. 最新の有効パケットが40%に充電された場合は再アームされる
        self.state.update_battery(40, charging_state=ChargingState.CHARGING)
        self.assertFalse(self.notif_manager.config.warned_10)
        self.assertFalse(self.notif_manager.config.warned_20)

        # 6. その後、再度10%へ低下した場合は正常条件として発報される
        self.state.update_battery(10, charging_state=ChargingState.NOT_CHARGING)
        self.assertEqual(self.mock_notifier.show.call_count, 2)

    def test_charging_bolt_visibility_lifecycle(self):
        """充電⚡アイコンの表示判定 (is_charging) がセッション単位で正しく制御されることを検証"""
        # 1. NORMAL + CHARGING -> is_charging == True
        self.state.set_dongle_available(True)
        self.state.update_battery(95, charging_state=ChargingState.CHARGING)
        self.assertTrue(self.state.is_charging)

        # 2. 切断 -> is_charging == False
        self.state.set_dongle_available(False)
        self.assertFalse(self.state.is_charging)

        # 3. 再接続 (WAITING_DATA) -> is_charging == False (形式Bが来てもFalse維持)
        self.state.set_dongle_available(True)
        self.assertFalse(self.state.is_charging)
        self.state.update_non_battery_packet(charging_state=ChargingState.CHARGING)
        self.assertFalse(self.state.is_charging)

        # 4. 新規有効形式Aで非充電 -> is_charging == False
        self.state.update_battery(95, charging_state=ChargingState.NOT_CHARGING)
        self.assertFalse(self.state.is_charging)

        # 5. 有効形式Aで充電中 -> is_charging == True
        self.state.update_battery(95, charging_state=ChargingState.CHARGING)
        self.assertTrue(self.state.is_charging)

    def test_sleep_recovery_format_b_and_notification(self):
        """スリープ推測状態からの復帰における形式Bの扱いと通知制御の検証

        1. NORMAL (残量10%) -> 10%通知発報
        2. 15秒経過でスリープ推測 (SLEEP_SUSPECTED) へ遷移
        3. 形式B受信 -> SLEEP_SUSPECTED維持 (NORMALへ復帰しない)
        4. 形式Bのみでは古い残量(10%)を最新値として扱わず、低残量通知を再発報しない
        5. 新しい形式A受信 (50%) -> NORMAL復帰
        6. 復帰後は新しい残量に基づいて通知が判定される (50%では通知なし、その後10%低下で通知)
        """
        # app.pyと同様の通知リスナーを登録
        def on_battery_update(updated_state: BatteryState):
            if updated_state.receive_state != ReceiveState.NORMAL:
                return
            self.notif_manager.evaluate_battery(
                percent=updated_state.percent,
                is_stale=updated_state.is_stale,
                is_disconnected=updated_state.is_disconnected,
                receive_state=updated_state.receive_state
            )

        self.state.add_listener(on_battery_update)

        # 1. NORMAL + 残量10% (通常運用で10%通知が発報)
        self.state.set_dongle_available(True)
        self.state.update_battery(10, charging_state=ChargingState.NOT_CHARGING)
        self.assertEqual(self.state.receive_state, ReceiveState.NORMAL)
        self.assertEqual(self.mock_notifier.show.call_count, 1)

        # 2. 15秒以上パケット途絶 -> check_staleness で SLEEP_SUSPECTED へ遷移
        self.state.last_valid_battery_at = time.time() - 16.0
        changed = self.state.check_staleness()
        self.assertTrue(changed)
        self.assertEqual(self.state.receive_state, ReceiveState.SLEEP_SUSPECTED)

        # 3. 形式B受信 -> SLEEP_SUSPECTEDを維持 (NORMALへ復帰しない)
        self.state.update_non_battery_packet(charging_state=ChargingState.NOT_CHARGING)
        self.assertEqual(self.state.receive_state, ReceiveState.SLEEP_SUSPECTED)

        # 4. 形式Bのみでは古い残量10%による低残量通知を発生させないこと
        # (モックの呼び出し回数が1回のまま増加していないこと)
        self.assertEqual(self.mock_notifier.show.call_count, 1)

        # 5. 新しい形式Aパケット (充電されて50%) を受信 -> NORMAL復帰
        self.state.update_battery(50, charging_state=ChargingState.NOT_CHARGING)
        self.assertEqual(self.state.receive_state, ReceiveState.NORMAL)
        self.assertEqual(self.state.percent, 50)
        # 50%なので通知は発報されない (call_countは1のまま)
        self.assertEqual(self.mock_notifier.show.call_count, 1)

        # 6. その後、再度10%へ低下した場合は正常な復帰後サイクルとして通知が発報される
        self.state.update_battery(10, charging_state=ChargingState.NOT_CHARGING)
        self.assertEqual(self.mock_notifier.show.call_count, 2)


if __name__ == "__main__":
    unittest.main()
