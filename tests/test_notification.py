"""LAMZU Thorn V2 低バッテリー通知機能の単体テスト

要件に基づく全テスト項目を網羅:
 1. 20%到達で1回通知
 2. 19%、18%で重複通知しない
 3. 10%到達で緊急警告
 4. 9%、8%で重複通知しない
 5. 初回残量15%で20%通知
 6. 初回残量8%で10%通知のみ (20%と10%を同時表示しない)
 7. 25%を超えた後に20%通知を再アーム
 8. 15%を超えた後に10%通知を再アーム
 9. アプリ再起動後の重複防止
10. 通知設定OFF時に通知しない
11. 通知設定ONへの復帰
12. スリープ推測時に誤通知しない
13. ドングル切断時に誤通知しない
14. 不正なHIDパケットで誤通知しない
15. デモモードで実際の通知を発報しない
16. テスト通知が通常の通知履歴に影響しない
17. 保存ファイル破損時に復旧できる
18. 通知APIが例外を返してもアプリが継続する
19. メニューのチェック状態が設定と一致する
20. 全ての関連単体テストが成功する
"""

import os
import tempfile
import unittest

from battery_state import BatteryState
from notification_manager import (
    NotificationLevel,
    NotificationManager,
    MockNotifier,
    WindowsNotifier,
    DEFAULT_TITLE
)
from tray_ui import TrayUI


class TestNotification(unittest.TestCase):
    """低バッテリー通知・重複防止・永続化の検証テストケース"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "test_config.json")
        self.notifier = MockNotifier()
        self.manager = NotificationManager(
            config_path=self.config_path,
            notifier=self.notifier,
            is_demo_mode=False
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_notify_once_at_20_percent(self):
        """1. 20%到達で1回通知"""
        lvl = self.manager.evaluate_battery(20)
        self.assertEqual(lvl, NotificationLevel.WARNING_20)
        self.assertEqual(len(self.notifier.notifications), 1)
        self.assertIn("20%以下", self.notifier.notifications[0]["message"])
        self.assertIn("20%", self.notifier.notifications[0]["message"])

    def test_02_no_duplicate_at_19_and_18_percent(self):
        """2. 19%、18%で重複通知しない"""
        # 初回20%で通知
        self.manager.evaluate_battery(20)
        self.assertEqual(len(self.notifier.notifications), 1)

        # 19%, 18%では重複発報しない
        lvl19 = self.manager.evaluate_battery(19)
        self.assertEqual(lvl19, NotificationLevel.NONE)
        self.assertEqual(len(self.notifier.notifications), 1)

        lvl18 = self.manager.evaluate_battery(18)
        self.assertEqual(lvl18, NotificationLevel.NONE)
        self.assertEqual(len(self.notifier.notifications), 1)

    def test_03_critical_alert_at_10_percent(self):
        """3. 10%到達で緊急警告"""
        lvl = self.manager.evaluate_battery(10)
        self.assertEqual(lvl, NotificationLevel.CRITICAL_10)
        self.assertEqual(len(self.notifier.notifications), 1)
        self.assertIn("10%以下", self.notifier.notifications[0]["message"])
        self.assertIn("充電をおすすめします", self.notifier.notifications[0]["message"])

    def test_04_no_duplicate_at_9_and_8_percent(self):
        """4. 9%、8%で重複通知しない"""
        self.manager.evaluate_battery(10)
        self.assertEqual(len(self.notifier.notifications), 1)

        lvl9 = self.manager.evaluate_battery(9)
        self.assertEqual(lvl9, NotificationLevel.NONE)
        self.assertEqual(len(self.notifier.notifications), 1)

        lvl8 = self.manager.evaluate_battery(8)
        self.assertEqual(lvl8, NotificationLevel.NONE)
        self.assertEqual(len(self.notifier.notifications), 1)

    def test_05_initial_15_percent_triggers_warning_20(self):
        """5. 初回残量15%で20%通知"""
        lvl = self.manager.evaluate_battery(15)
        self.assertEqual(lvl, NotificationLevel.WARNING_20)
        self.assertEqual(len(self.notifier.notifications), 1)
        self.assertIn("20%以下", self.notifier.notifications[0]["message"])

    def test_06_initial_8_percent_triggers_only_critical_10(self):
        """6. 初回残量8%で10%通知のみ (20%と10%を同時表示しない)"""
        lvl = self.manager.evaluate_battery(8)
        self.assertEqual(lvl, NotificationLevel.CRITICAL_10)
        # 1件のみ発報
        self.assertEqual(len(self.notifier.notifications), 1)
        self.assertIn("10%以下", self.notifier.notifications[0]["message"])
        # 20%側も抑止フラグが立っていること
        self.assertTrue(self.manager.config.warned_20)
        self.assertTrue(self.manager.config.warned_10)

    def test_07_rearm_20_percent_after_exceeding_25(self):
        """7. 25%を超えた後に20%通知を再アーム"""
        # 20%で通知
        self.manager.evaluate_battery(20)
        self.assertTrue(self.manager.config.warned_20)

        # 24%へ回復しても25%以下なので再アームされない
        self.manager.evaluate_battery(24)
        self.assertTrue(self.manager.config.warned_20)

        # 26%へ回復 (25%超) で再アーム
        self.manager.evaluate_battery(26)
        self.assertFalse(self.manager.config.warned_20)

        # 再度20%に低下した際に再通知される
        lvl = self.manager.evaluate_battery(20)
        self.assertEqual(lvl, NotificationLevel.WARNING_20)
        self.assertEqual(len(self.notifier.notifications), 2)

    def test_08_rearm_10_percent_after_exceeding_15(self):
        """8. 15%を超えた後に10%通知を再アーム (20%は25%超まで再アームされない)"""
        # 10%で通知
        self.manager.evaluate_battery(10)
        self.assertTrue(self.manager.config.warned_10)
        self.assertTrue(self.manager.config.warned_20)

        # 16%へ回復 (15%超) で10%のみ再アーム、20%は再アームされない
        self.manager.evaluate_battery(16)
        self.assertFalse(self.manager.config.warned_10)
        self.assertTrue(self.manager.config.warned_20)

        # 12%に低下しても20%は再アームされていないので通知なし
        lvl12 = self.manager.evaluate_battery(12)
        self.assertEqual(lvl12, NotificationLevel.NONE)

        # 9%に低下した際は10%警告が再発報される
        lvl9 = self.manager.evaluate_battery(9)
        self.assertEqual(lvl9, NotificationLevel.CRITICAL_10)
        self.assertEqual(len(self.notifier.notifications), 2)

    def test_09_persistence_prevents_duplicate_after_restart(self):
        """9. アプリ再起動後の重複防止"""
        # 20%で通知を発報しファイルに永続化
        self.manager.evaluate_battery(20)
        self.assertEqual(len(self.notifier.notifications), 1)

        # 新規インスタンスを同じ設定ファイルパスで初期化 (アプリ再起動のシミュレーション)
        notifier2 = MockNotifier()
        manager2 = NotificationManager(
            config_path=self.config_path,
            notifier=notifier2,
            is_demo_mode=False
        )
        self.assertTrue(manager2.config.warned_20)

        # 再起動直後の19%で重複通知されないこと
        lvl = manager2.evaluate_battery(19)
        self.assertEqual(lvl, NotificationLevel.NONE)
        self.assertEqual(len(notifier2.notifications), 0)

    def test_10_no_notification_when_disabled(self):
        """10. 通知設定OFF時に通知しない"""
        self.manager.set_enabled(False)
        self.assertFalse(self.manager.notifications_enabled)

        lvl20 = self.manager.evaluate_battery(20)
        self.assertEqual(lvl20, NotificationLevel.NONE)
        self.assertEqual(len(self.notifier.notifications), 0)

        lvl10 = self.manager.evaluate_battery(10)
        self.assertEqual(lvl10, NotificationLevel.NONE)
        self.assertEqual(len(self.notifier.notifications), 0)

    def test_11_resume_notification_when_enabled(self):
        """11. 通知設定ONへの復帰"""
        self.manager.set_enabled(False)
        self.manager.evaluate_battery(20)
        self.assertEqual(len(self.notifier.notifications), 0)

        # ONに戻す
        self.manager.set_enabled(True)
        self.assertTrue(self.manager.notifications_enabled)

        # 20%で通知が発報される
        lvl = self.manager.evaluate_battery(20)
        self.assertEqual(lvl, NotificationLevel.WARNING_20)
        self.assertEqual(len(self.notifier.notifications), 1)

    def test_12_no_notification_when_stale(self):
        """12. スリープ推測時に誤通知しない (is_stale=True)"""
        lvl = self.manager.evaluate_battery(10, is_stale=True)
        self.assertEqual(lvl, NotificationLevel.NONE)
        self.assertEqual(len(self.notifier.notifications), 0)

    def test_13_no_notification_when_disconnected(self):
        """13. ドングル切断時に誤通知しない (is_disconnected=True)"""
        lvl = self.manager.evaluate_battery(5, is_disconnected=True)
        self.assertEqual(lvl, NotificationLevel.NONE)
        self.assertEqual(len(self.notifier.notifications), 0)

    def test_14_no_notification_on_invalid_data(self):
        """14. 不正なHIDパケットで誤通知しない (Noneや範囲外)"""
        lvl_none = self.manager.evaluate_battery(None)
        self.assertEqual(lvl_none, NotificationLevel.NONE)

        lvl_neg = self.manager.evaluate_battery(-5)
        self.assertEqual(lvl_neg, NotificationLevel.NONE)

        lvl_over = self.manager.evaluate_battery(105)
        self.assertEqual(lvl_over, NotificationLevel.NONE)

        self.assertEqual(len(self.notifier.notifications), 0)

    def test_15_no_notification_in_demo_mode(self):
        """15. デモモードで実際の通知を発報しない"""
        demo_notifier = MockNotifier()
        demo_manager = NotificationManager(
            config_path=os.path.join(self.temp_dir.name, "demo_config.json"),
            notifier=demo_notifier,
            is_demo_mode=True
        )
        lvl = demo_manager.evaluate_battery(10)
        self.assertEqual(lvl, NotificationLevel.NONE)
        self.assertEqual(len(demo_notifier.notifications), 0)

    def test_16_test_notification_does_not_affect_history(self):
        """16. テスト通知が通常の通知履歴に影響しない"""
        res = self.manager.send_test_notification()
        self.assertTrue(res)
        self.assertEqual(len(self.notifier.notifications), 1)
        self.assertIn("テスト通知", self.notifier.notifications[0]["message"])

        # 通常の履歴フラグは未発報のままであること
        self.assertFalse(self.manager.config.warned_20)
        self.assertFalse(self.manager.config.warned_10)

        # その後20%に到達した際に正常に警告が出ること
        lvl = self.manager.evaluate_battery(20)
        self.assertEqual(lvl, NotificationLevel.WARNING_20)
        self.assertEqual(len(self.notifier.notifications), 2)

    def test_17_recover_from_corrupted_config(self):
        """17. 保存ファイル破損時に復旧できる"""
        # 不正なJSONデータをファイルに書き込み
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write("CORRUPTED_JSON_DATA{{{")

        # 破損ファイルから起動しても例外が出ずデフォルトで復旧
        broken_manager = NotificationManager(
            config_path=self.config_path,
            notifier=MockNotifier(),
            is_demo_mode=False
        )
        self.assertTrue(broken_manager.config.notifications_enabled)
        self.assertFalse(broken_manager.config.warned_20)

    def test_18_exception_in_notifier_does_not_crash_app(self):
        """18. 通知APIが例外を返してもアプリが継続する"""
        failing_notifier = MockNotifier()
        failing_notifier.should_fail = True
        failing_manager = NotificationManager(
            config_path=os.path.join(self.temp_dir.name, "fail_config.json"),
            notifier=failing_notifier,
            is_demo_mode=False
        )
        # 例外がスローされずに安全に処理されること
        lvl = failing_manager.evaluate_battery(20)
        self.assertEqual(lvl, NotificationLevel.WARNING_20)

    def test_19_tray_menu_checked_state_matches_config(self):
        """19. メニューのチェック状態が設定と一致する"""
        state = BatteryState(is_demo_mode=True)
        ui = TrayUI(state, notification_manager=self.manager)
        menu = ui.build_menu()

        # メニュー項目から「低残量通知を有効にする」を探す
        toggle_item = None
        for item in menu.items:
            if hasattr(item, "text") and item.text == "低残量通知を有効にする":
                toggle_item = item
                break

        self.assertIsNotNone(toggle_item)
        # 初期状態: 有効 (True)
        self.assertTrue(toggle_item.checked)

        # 無効に変更
        self.manager.set_enabled(False)
        self.assertFalse(toggle_item.checked)

        # 有効に戻す
        self.manager.set_enabled(True)
        self.assertTrue(toggle_item.checked)


if __name__ == "__main__":
    unittest.main()
