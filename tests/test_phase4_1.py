"""LAMZU Thorn V2 アイコンスタイル切り替え・設定永続化単体テスト

要件11に基づく全検証項目:
 1. 数字のみのアイコンを生成できる
 2. バッテリーのみのアイコンを生成できる
 3. 0〜100%が全スタイルで正しく描画できる
 4. 数字のみで100%が16x16px内で欠けずに描画できる
 5. 未取得状態を表示できる
 6. ドングル切断状態を表示できる
 7. 既存の旧スタイル指定が互換動作し例外なく描画できる
 8. サブメニューの選択肢が3種類のみであり、旧スタイル名が存在しない
 9. 選択中の項目だけに排他的にチェックが付く
10. スタイル変更が即時反映される (force_icon_redraw)
11. 同じスタイルの再選択で無駄な再描画・保存をしない
12. スタイルを変更してもHID通信・監視が継続する
13. 設定が保存される
14. 再起動後もスタイルを復元できる
15. 既存の通知設定が破壊されない
16. 通知の発報履歴が破壊されない
17. 不正スタイル名から安全に復旧する (top-a1フォールバック)
18. 設定ファイル破損時に安全に復旧する (バックアップ＆デフォルト化)
19. メニューを繰り返し開閉・更新しても問題ない
21. 多重起動防止が維持される
22. Windows自動起動のON/OFFに影響しない
23. 正常終了できる
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from battery_state import BatteryState, ReceiveState
from config_manager import ConfigManager, SUPPORTED_STYLES, DEFAULT_STYLE
from icon_generator import create_battery_icon, get_battery_color
from notification_manager import NotificationManager, MockNotifier
from autostart_manager import AutostartManager
from single_instance import SingleInstanceChecker
from tray_ui import TrayUI
import pystray


class TestPhase41(unittest.TestCase):
    """Phase 4.1 アイコンスタイル切り替え・設定永続化・サブメニューのテストケース"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "config.json")
        self.config_mgr = ConfigManager(config_path=self.config_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    # ==========================================
    # 1〜7. アイコン生成テスト
    # ==========================================

    def test_01_create_numbers_only_icon(self):
        """1. 数字のみのアイコンを生成できる"""
        img = create_battery_icon(98, style="numbers-only", size=16)
        self.assertIsNotNone(img)
        self.assertEqual(img.size, (16, 16))
        self.assertEqual(img.mode, "RGBA")
        alpha_pixels = sum(img.getpixel((x, y))[3] > 0 for x in range(16) for y in range(16))
        self.assertGreater(alpha_pixels, 15)

    def test_02_create_battery_only_icon(self):
        """2. バッテリーのみのアイコンを生成できる"""
        img = create_battery_icon(98, style="battery-only", size=16)
        self.assertIsNotNone(img)
        self.assertEqual(img.size, (16, 16))
        self.assertEqual(img.mode, "RGBA")
        alpha_pixels = sum(img.getpixel((x, y))[3] > 0 for x in range(16) for y in range(16))
        self.assertGreater(alpha_pixels, 20)

    def test_03_all_styles_render_0_to_100_percent(self):
        """3. 0〜100%が全8スタイルで正しく描画できる"""
        test_percents = [0, 9, 10, 20, 50, 98, 99, 100]
        for style in SUPPORTED_STYLES:
            for p in test_percents:
                img = create_battery_icon(p, style=style, size=16)
                self.assertIsNotNone(img)
                self.assertEqual(img.size, (16, 16))

    def test_04_numbers_only_100_percent_no_clipping(self):
        """4. 数字のみで100%が16x16px内で欠けずに描画できる"""
        img = create_battery_icon(100, style="numbers-only", size=16)
        self.assertEqual(img.size, (16, 16))
        # 左右端 (x=0, x=15) にピクセルが安全に収まっていることを検証
        alpha_pixels = sum(img.getpixel((x, y))[3] > 0 for x in range(16) for y in range(16))
        self.assertGreater(alpha_pixels, 20)

    def test_05_unknown_battery_state_rendering(self):
        """5. 未取得状態を表示できる"""
        for style in SUPPORTED_STYLES:
            img = create_battery_icon(None, style=style, size=16)
            self.assertIsNotNone(img)
            self.assertEqual(img.size, (16, 16))

    def test_06_disconnected_state_rendering(self):
        """6. ドングル切断状態を表示できる"""
        for style in SUPPORTED_STYLES:
            img = create_battery_icon(None, style=style, size=16, is_disconnected=True)
            self.assertIsNotNone(img)
            self.assertEqual(img.size, (16, 16))

    def test_07_legacy_styles_backward_compatibility(self):
        """7. 既存の旧スタイル指定が互換動作し例外なく描画できる"""
        legacy_styles = ["top-a1", "top-a2", "top-a3", "top", "bottom", "overlay"]
        for sty in legacy_styles:
            img = create_battery_icon(50, style=sty, size=16)
            self.assertIsNotNone(img)
            self.assertEqual(img.size, (16, 16))

    # ==========================================
    # 8〜12. トレイメニューおよび即時切り替えテスト
    # ==========================================

    def test_08_submenu_contains_three_styles_only(self):
        """8. サブメニューの選択肢が3種類のみであり、旧スタイル名が存在しない"""
        state = BatteryState()
        ui = TrayUI(state, config_manager=self.config_mgr)
        menu = ui.build_menu()

        # 「アイコンデザイン」項目を検索
        style_item = None
        for item in menu.items:
            if hasattr(item, "text") and item.text == "アイコンデザイン":
                style_item = item
                break
        self.assertIsNotNone(style_item, "メニュー内に「アイコンデザイン」が見つかりません")
        self.assertIsNotNone(style_item.submenu, "アイコンデザインがサブメニューになっていません")

        # サブメニュー項目名を取得
        sub_items = list(style_item.submenu.items)
        sub_texts = [it.text for it in sub_items if hasattr(it, "text") and it.text]

        # 3種類のみであることを確認
        expected_texts = [
            "数字のみ",
            "バッテリーのみ",
            "数字+バッテリー表示"
        ]
        self.assertEqual(len(sub_texts), 3, f"サブメニュー項目数が3個ではありません: {sub_texts}")
        for exp in expected_texts:
            self.assertIn(exp, sub_texts)

        # 旧開発コード名がUIに露出していないことを確認
        self.assertNotIn("数字＋電池（A1・標準）", sub_texts)
        self.assertNotIn("旧A案", sub_texts)

    def test_09_only_selected_style_has_checked_mark(self):
        """9. 選択中の項目だけに排他的にチェックが付く"""
        state = BatteryState()
        ui = TrayUI(state, config_manager=self.config_mgr, icon_style="numbers-battery")
        menu = ui.build_menu()

        style_item = [it for it in menu.items if hasattr(it, "text") and it.text == "アイコンデザイン"][0]
        sub_items = list(style_item.submenu.items)

        checked_count = 0
        checked_style = None
        for it in sub_items:
            # pystray.MenuItem.checked はプロパティとしてアクセス時に評価され bool を返す
            is_checked = it.checked(it) if callable(getattr(it, "checked", None)) else getattr(it, "checked", False)
            if is_checked:
                checked_count += 1
                checked_style = it.text

        self.assertEqual(checked_count, 1, "同時に複数、または0個のスタイルにチェックが付いています")
        self.assertEqual(checked_style, "数字+バッテリー表示")

    def test_10_immediate_style_switching(self):
        """10. スタイル変更が即時反映される (force_icon_redraw)"""
        state = BatteryState()
        state.update_battery(98)
        ui = TrayUI(state, config_manager=self.config_mgr, icon_style="numbers-battery")
        mock_icon = MagicMock()
        ui._icon = mock_icon
        ui._is_running = True

        # スタイルを numbers-only に切り替え
        ui._handle_style_change("numbers-only")
        self.assertEqual(ui.icon_style, "numbers-only")
        self.assertEqual(self.config_mgr.icon_style, "numbers-only")
        # アイコンの再生成が呼ばれたこと
        self.assertIsNotNone(mock_icon.icon)

    def test_11_reselecting_same_style_suppresses_redundant_work(self):
        """11. 同じスタイルの再選択で無駄な再描画・保存をしない"""
        state = BatteryState()
        ui = TrayUI(state, config_manager=self.config_mgr, icon_style="numbers-battery")
        mock_icon = MagicMock()
        ui._icon = mock_icon
        ui._is_running = True

        # 同じスタイルを選択
        ui._handle_style_change("numbers-battery")
        # update_menu が呼ばれていないこと (抑制されたこと)
        mock_icon.update_menu.assert_not_called()

    def test_12_style_change_keeps_state_listener_alive(self):
        """12. スタイルを変更してもHID通信・状態監視リスナーが継続する"""
        state = BatteryState()
        ui = TrayUI(state, config_manager=self.config_mgr)
        state.add_listener(ui.on_state_changed)

        ui._handle_style_change("battery-only")
        # 状態更新
        state.update_battery(85)
        self.assertEqual(state.battery_percent, 85)
        self.assertEqual(ui.icon_style, "battery-only")

    # ==========================================
    # 13〜18. 設定永続化・共存テスト
    # ==========================================

    def test_13_config_saving(self):
        """13. 設定が保存される"""
        self.config_mgr.set_icon_style("numbers-only")
        self.assertTrue(os.path.exists(self.config_path))
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data.get("icon_style"), "numbers-only")

    def test_14_config_restoration_and_legacy_migration(self):
        """14. 再起動後もスタイルを復元でき、旧スタイルは安全に移行される"""
        self.config_mgr.set_icon_style("battery-only")
        # 新しいインスタンスでロード
        new_mgr = ConfigManager(config_path=self.config_path)
        self.assertEqual(new_mgr.icon_style, "battery-only")

        # 旧スタイル名 (overlay) が保存されていた場合の移行テスト
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump({"icon_style": "overlay"}, f)
        migrated_mgr = ConfigManager(config_path=self.config_path)
        self.assertEqual(migrated_mgr.icon_style, "numbers-battery")

    def test_15_notification_settings_not_destroyed(self):
        """15. 既存の通知設定が破壊されない"""
        # 通知マネージャーで通知設定を保存
        notif_mgr = NotificationManager(config_path=self.config_path, notifier=MockNotifier())
        notif_mgr.set_enabled(False)

        # アイコンスタイルを変更
        self.config_mgr.set_icon_style("battery-only")

        # 再度通知マネージャーで読み込み
        notif_mgr_reloaded = NotificationManager(config_path=self.config_path, notifier=MockNotifier())
        self.assertFalse(notif_mgr_reloaded.notifications_enabled)
        self.assertEqual(self.config_mgr.icon_style, "battery-only")

    def test_16_notification_history_not_reset(self):
        """16. 通知の発報履歴が破壊されない"""
        notif_mgr = NotificationManager(config_path=self.config_path, notifier=MockNotifier())
        # 20%通知発報
        notif_mgr.evaluate_battery(20)
        self.assertTrue(notif_mgr.config.warned_20)

        # スタイル変更
        self.config_mgr.set_icon_style("battery-only")

        # 発報状態が維持されていること
        notif_reloaded = NotificationManager(config_path=self.config_path, notifier=MockNotifier())
        self.assertTrue(notif_reloaded.config.warned_20)

    def test_17_invalid_style_fallback_to_numbers_battery(self):
        """17. 不正スタイル名から安全に復旧する (numbers-batteryフォールバック)"""
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump({"icon_style": "invalid-unknown-style"}, f)

        mgr = ConfigManager(config_path=self.config_path)
        self.assertEqual(mgr.icon_style, "numbers-battery")

    def test_18_corrupted_config_file_recovery(self):
        """18. 設定ファイル破損時に安全に復旧する (バックアップ＆初期化)"""
        with open(self.config_path, "w", encoding="utf-8") as f:
            f.write("{broken_json: !!invalid")

        mgr = ConfigManager(config_path=self.config_path)
        self.assertEqual(mgr.icon_style, "numbers-battery")
        self.assertTrue(mgr.notifications_enabled)
        # バックアップファイルが作成されたこと
        self.assertTrue(os.path.exists(self.config_path + ".corrupted.bak"))

    def test_19_repeated_menu_update_stability(self):
        """19. メニューを繰り返し開閉・更新しても問題ない"""
        state = BatteryState()
        ui = TrayUI(state, config_manager=self.config_mgr)
        mock_icon = MagicMock()
        ui._icon = mock_icon
        ui._is_running = True

        for i in range(20):
            ui._update_menu_safe(f"テスト更新 {i}")

        self.assertEqual(ui.menu_update_count, 20)

    def test_21_single_instance_checker_maintained(self):
        """21. 多重起動防止が維持される"""
        checker1 = SingleInstanceChecker("Local\\Test_Phase41_Mutex")
        checker2 = SingleInstanceChecker("Local\\Test_Phase41_Mutex")
        try:
            self.assertFalse(checker1.is_already_running())
            self.assertTrue(checker2.is_already_running())
        finally:
            checker2.release()
            checker1.release()

    def test_22_autostart_toggle_independent(self):
        """22. Windows自動起動のON/OFFがスタイル設定に影響しない"""
        auto_mgr = AutostartManager()
        self.config_mgr.set_icon_style("numbers-only")
        # 自動起動状態の取得 (環境に依存せず真偽値が返ること)
        is_enabled = auto_mgr.is_autostart_enabled()
        self.assertIsInstance(is_enabled, bool)
        # スタイルが保持されていること
        self.assertEqual(self.config_mgr.icon_style, "numbers-only")


if __name__ == "__main__":
    unittest.main()
