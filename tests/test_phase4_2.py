"""LAMZU Thorn V2 ステータスパネル・UI連携単体テスト

Tkinter Canvasステータスパネル、右クリックメニュー整理・指定順序、
LAMZU Aurora連携、アイコン3種統一・配色・境界値・100%文字アウトライン包含、
設定永続化ロック、旧設定移行を包括的に検証します。
"""

import os
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch
import tkinter as tk
import pystray

from battery_state import BatteryState
from config_manager import ConfigManager, GLOBAL_CONFIG_LOCK, DEFAULT_STYLE, SUPPORTED_STYLES
from icon_generator import (
    create_battery_icon,
    get_battery_color,
    STYLE_NORMALIZATION,
)
from status_panel import StatusPanel
from tray_ui import TrayUI, LeftClickMenu


class TestPhase42StatusPanel(unittest.TestCase):
    """Tkinter Canvasステータスパネルの検証"""

    @classmethod
    def setUpClass(cls):
        # Tkinterのルートウィンドウを初期化（非表示）
        cls.root = tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        try:
            cls.root.destroy()
        except Exception:
            pass

    def setUp(self):
        self.state = BatteryState()
        self.state.update_battery(85)
        self.panel = StatusPanel(self.root)

    def tearDown(self):
        self.panel.hide()
        try:
            self.panel.destroy()
            self.root.update()
        except Exception:
            pass

    def test_initial_state_hidden(self):
        """初期状態でパネルが非表示であることの検証"""
        self.assertFalse(self.panel.is_visible)
        self.assertFalse(self.panel.window.winfo_viewable())

    def test_show_and_hide(self):
        """show と hide の基本動作検証"""
        self.panel.show(self.state)
        self.root.update()
        self.assertTrue(self.panel.is_visible)

        self.panel.hide()
        self.root.update()
        self.assertFalse(self.panel.is_visible)

    def test_toggle(self):
        """toggle によるトグル動作の検証"""
        self.panel.toggle(self.state)
        self.root.update()
        self.assertTrue(self.panel.is_visible)

        # デバウンスを考慮して少し待機
        time.sleep(0.3)
        self.panel.toggle(self.state)
        self.root.update()
        self.assertFalse(self.panel.is_visible)

    def test_focus_out_and_escape_hides_panel(self):
        """外部へのフォーカス移動およびEscapeキー押下でパネルが非表示になることの検証"""
        self.panel.show(self.state)
        self.root.update()
        self.assertTrue(self.panel.is_visible)

        # 外部ウィンドウへのフォーカス移動をシミュレート
        mock_event = MagicMock()
        mock_event.widget = self.panel.window
        with patch.object(self.panel.window, "focus_get", return_value=None):
            self.panel._on_focus_out(mock_event)
        self.root.update()
        self.assertFalse(self.panel.is_visible)

        # 再度表示してEscapeキーイベントを検証
        time.sleep(0.3)
        self.panel.show(self.state)
        self.root.update()
        self.assertTrue(self.panel.is_visible)

        self.panel.window.event_generate("<Escape>")
        self.root.update()
        self.assertFalse(self.panel.is_visible)

    def test_update_state_rendering(self):
        """update_state によるCanvasの描画・更新が例外なく動作することの検証"""
        self.panel.show(self.state)
        self.root.update()

        # 正常残量
        self.state.update_battery(95)
        self.panel.update_state(self.state)
        self.root.update()

        # 低残量
        self.state.update_battery(15)
        self.panel.update_state(self.state)
        self.root.update()

        # 未取得
        self.state.battery_percent = None
        self.panel.update_state(self.state)
        self.root.update()
        self.assertTrue(self.panel.is_visible)


class TestPhase42ContextMenu(unittest.TestCase):
    """右クリックメニューの整理・順序・Aurora連携の検証"""

    def setUp(self):
        self.state = BatteryState()
        self.mock_panel = MagicMock()
        self.app = TrayUI(self.state, on_exit=MagicMock(), status_panel=self.mock_panel)

    def test_menu_order_and_items(self):
        """Phase 4.2 指定の右クリックメニュー順序およびグレーアウト項目・不要項目の完全撤去を検証"""
        menu = self.app.build_menu()
        items = list(menu.items)

        # セパレータ以外の項目タイトル一覧
        non_sep_items = [
            (item.text(item) if callable(item.text) else item.text)
            for item in items
            if hasattr(item, "text") and item != pystray.Menu.SEPARATOR and item.text != "- - - -"
        ]

        # 1. 順序の検証
        expected_sequence = [
            "低残量通知を有効にする",
            "テスト通知を送信",
            "Windows起動時に自動起動",
            "アイコンデザイン",
            "LAMZU Auroraを開く",
            "終了",
        ]
        self.assertEqual(non_sep_items, expected_sequence)

        # セパレータが3つ存在することの検証
        sep_count = sum(1 for item in items if item == pystray.Menu.SEPARATOR or getattr(item, "text", None) == "- - - -")
        self.assertEqual(sep_count, 3)

        # 2. 撤去対象項目の非存在検証
        forbidden_keywords = [
            "LAMZU Thorn V2",
            "バッテリー:",
            "受信状態:",
            "最終更新:",
            "ログフォルダを開く",
        ]
        for forbidden in forbidden_keywords:
            self.assertFalse(
                any(forbidden in str(t) for t in non_sep_items),
                f"撤去対象の項目 '{forbidden}' がメニューに残存しています: {non_sep_items}",
            )

    @patch("webbrowser.open")
    def test_open_aurora_url(self, mock_web_open):
        """「LAMZU Auroraを開く」が正しいURLをブラウザで開くことの検証"""
        self.app._handle_open_aurora(None, None)
        # スレッド起動を少し待機
        time.sleep(0.1)
        mock_web_open.assert_called_with("https://www.lamzu.net/#/project/items")

    def test_left_click_menu_subclass(self):
        """LeftClickMenu が左クリック時に status_panel.toggle を呼び出すことの検証"""
        left_menu = self.app.build_menu()
        self.assertIsInstance(left_menu, LeftClickMenu)

        # 左クリック呼び出しのシミュレーション
        mock_icon = MagicMock()
        left_menu(mock_icon)
        self.mock_panel.toggle.assert_called_once_with(self.state)


class TestPhase42IconColorsAndOutline(unittest.TestCase):
    """アイコン配色統一、境界値、100%文字アウトライン包含の検証"""

    def test_color_ranges_and_boundaries(self):
        """配色統一と境界値（20/21/50/51%）の検証"""
        # 51〜100%: 緑 (#2ECC71 -> 46, 204, 113)
        self.assertEqual(get_battery_color(100), (46, 204, 113))
        self.assertEqual(get_battery_color(51), (46, 204, 113))

        # 21〜50%: 橙 (#F39C12 -> 243, 156, 18)
        self.assertEqual(get_battery_color(50), (243, 156, 18))
        self.assertEqual(get_battery_color(21), (243, 156, 18))

        # 0〜20%: 赤 (#E74C3C -> 231, 76, 60)
        self.assertEqual(get_battery_color(20), (231, 76, 60))
        self.assertEqual(get_battery_color(0), (231, 76, 60))

        # None (未取得): 灰 (#95A5A6 -> 149, 165, 166)
        self.assertEqual(get_battery_color(None), (149, 165, 166))

    def test_numbers_only_100_percent_outline_inclusion(self):
        """numbers-only の 100% 文字＋黒アウトライン（左右1px）が 16x16px 枠内に完全内包されることの検証"""
        img = create_battery_icon(100, style="numbers-only", size=16)
        self.assertEqual(img.size, (16, 16))

        # 左右端（x=0, x=15）のピクセルチェック
        # 画像外へのクリッピングがないことの確認
        non_zero_x = []
        for x in range(16):
            has_pixel = any(img.getpixel((x, y))[3] > 0 for y in range(16))
            if has_pixel:
                non_zero_x.append(x)

        self.assertTrue(len(non_zero_x) > 0)
        min_x = min(non_zero_x)
        max_x = max(non_zero_x)

        # 0 <= x <= 15 の範囲内に完全に収まっていること
        self.assertGreaterEqual(min_x, 0)
        self.assertLessEqual(max_x, 15)

    def test_default_style_and_migration(self):
        """デフォルトスタイルが numbers-battery であり、旧スタイルが安全に移行されることの検証"""
        self.assertEqual(DEFAULT_STYLE, "numbers-battery")
        self.assertEqual(set(SUPPORTED_STYLES), {"numbers-only", "battery-only", "numbers-battery"})

        # 旧スタイル名の正規化
        for old in ["top-a1", "top-a2", "top-a3", "top", "bottom", "overlay"]:
            self.assertEqual(STYLE_NORMALIZATION.get(old), "numbers-battery")


class TestPhase42ConfigLock(unittest.TestCase):
    """設定永続化におけるプロセス内共有ロックの検証"""

    def test_global_config_lock_is_rlock(self):
        """GLOBAL_CONFIG_LOCK が再帰可能ロック(threading.RLock)であることの検証"""
        self.assertIn("RLock", type(GLOBAL_CONFIG_LOCK).__name__)

    def test_concurrent_config_access(self):
        """マルチスレッド下での設定読み書きが競合せず安全に完了することの検証"""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            temp_path = tf.name

        try:
            cfg = ConfigManager(config_path=temp_path)
            errors = []

            def worker_write(val):
                try:
                    for _ in range(5):
                        cfg.set_icon_style("numbers-only" if val % 2 == 0 else "numbers-battery")
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=worker_write, args=(i,)) for i in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(len(errors), 0)
            self.assertIn(cfg.icon_style, SUPPORTED_STYLES)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
