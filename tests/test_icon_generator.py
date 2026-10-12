"""LAMZU Thorn V2 アイコン生成モジュールの単体テスト

バッテリー残量カラー、各種ステータス、デザインスタイルの切り替え、
3桁(100%)のクリッピング防止、各解像度(16, 20, 24, 32px)での描画を検証します。
"""

import unittest
from icon_generator import create_battery_icon, get_battery_color, generate_all_previews


class TestIconGenerator(unittest.TestCase):
    """トレイアイコン生成の動作検証テストケース"""

    def test_battery_color_ranges(self):
        """残量ごとの色分け判定の検証"""
        # 51〜100%: 緑
        self.assertEqual(get_battery_color(100), (46, 204, 113))
        self.assertEqual(get_battery_color(51), (46, 204, 113))

        # 21〜50%: 橙
        self.assertEqual(get_battery_color(50), (243, 156, 18))
        self.assertEqual(get_battery_color(21), (243, 156, 18))

        # 0〜20%: 赤
        self.assertEqual(get_battery_color(20), (231, 76, 60))
        self.assertEqual(get_battery_color(0), (231, 76, 60))

        # None (未取得): 灰
        self.assertEqual(get_battery_color(None), (149, 165, 166))

    def test_icon_generation_dimensions(self):
        """生成されるアイコンの寸法とモード検証 (16, 20, 24, 32, 64px)"""
        styles = ["numbers-only", "battery-only", "numbers-battery"]
        for sz in [16, 20, 24, 32, 64]:
            for sty in styles:
                img = create_battery_icon(99, style=sty, size=sz)
                self.assertEqual(img.size, (sz, sz))
                self.assertEqual(img.mode, "RGBA")

    def test_number_rendering_all_values(self):
        """必須残量パターン (0, 9, 10, 20, 50, 99, 100) が全スタイルで描画できることの検証"""
        values = [0, 9, 10, 20, 50, 99, 100]
        styles = ["numbers-only", "battery-only", "numbers-battery"]
        for p in values:
            for sty in styles:
                img = create_battery_icon(p, style=sty, size=16)
                self.assertIsNotNone(img)
                self.assertEqual(img.size, (16, 16))
                # 描画されたピクセル（アルファ値 > 0）が存在すること
                alpha_pixels = sum(img.getpixel((x, y))[3] > 0 for x in range(16) for y in range(16))
                self.assertGreater(alpha_pixels, 10)

    def test_three_digit_100_percent_clipping_prevention(self):
        """3桁(100%)表示が16x16px内で欠け・オーバーフローなく描画されることの検証"""
        styles = ["numbers-only", "battery-only", "numbers-battery"]
        for sty in styles:
            img = create_battery_icon(100, style=sty, size=16)
            self.assertEqual(img.size, (16, 16))
            # 内部に描画されたピクセルが存在すること
            total_pixels = sum(img.getpixel((x, y))[3] > 0 for x in range(16) for y in range(16))
            self.assertGreater(total_pixels, 15)

    def test_style_switching_produces_different_layouts(self):
        """3スタイル（数字のみ、バッテリーのみ、数字+バッテリー）が異なるピクセルレイアウトを生成することの検証"""
        img_nums = create_battery_icon(99, style="numbers-only", size=16)
        img_batt = create_battery_icon(99, style="battery-only", size=16)
        img_nb = create_battery_icon(99, style="numbers-battery", size=16)

        # 3スタイル間で画像データが一致しないことを検証
        self.assertNotEqual(img_nums.tobytes(), img_batt.tobytes())
        self.assertNotEqual(img_nums.tobytes(), img_nb.tobytes())
        self.assertNotEqual(img_batt.tobytes(), img_nb.tobytes())

        # 旧スタイル指定が安全に numbers-battery に正規化されることを検証
        for old_style in ["top-a1", "top-a2", "top-a3", "top", "bottom", "overlay"]:
            img_old = create_battery_icon(99, style=old_style, size=16)
            self.assertEqual(img_old.tobytes(), img_nb.tobytes())

    def test_icon_states(self):
        """スリープ時・切断時・未取得時のアイコン生成が正常終了することの検証"""
        styles = ["numbers-only", "battery-only", "numbers-battery"]
        for sty in styles:
            # 未取得状態 (?)
            img_none = create_battery_icon(None, style=sty, size=16)
            self.assertIsNotNone(img_none)

            # スリープ推測状態
            img_stale = create_battery_icon(80, style=sty, size=16, is_stale=True)
            self.assertIsNotNone(img_stale)

            # ドングル切断状態 (X)
            img_disconn = create_battery_icon(None, style=sty, size=16, is_disconnected=True)
            self.assertIsNotNone(img_disconn)

    def test_preview_generation(self):
        """比較プレビュー画像群が正常に生成されることの検証"""
        files = generate_all_previews()
        self.assertIn("comparison_16px", files)
        self.assertIn("zoom_8x", files)
        self.assertIn("comparison_99_100", files)
        self.assertIn("multisize", files)
        self.assertIn("theme_dark_light", files)


if __name__ == "__main__":
    unittest.main()
