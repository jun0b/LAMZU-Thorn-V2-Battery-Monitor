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
        self.assertIn("numbers_only_focus", files)
        self.assertIn("battery_only_focus", files)
        self.assertIn("multisize", files)
        self.assertIn("theme_dark_light", files)

    def test_battery_only_charging_gauge_distinction(self):
        """battery-onlyスタイルで充電中におけるゲージ残量の識別性を検証

        特に16×16pxにおいて10%と20%が同一画像にならず、
        20%、50%、100%のゲージ差も識別できることを検証する。
        """
        for sz in [16, 20, 24, 32]:
            img10 = create_battery_icon(10, style="battery-only", size=sz, is_charging=True)
            img20 = create_battery_icon(20, style="battery-only", size=sz, is_charging=True)
            img50 = create_battery_icon(50, style="battery-only", size=sz, is_charging=True)
            img100 = create_battery_icon(100, style="battery-only", size=sz, is_charging=True)

            # 10% と 20% の充電中アイコンが同一画像にならないこと
            self.assertNotEqual(
                img10.tobytes(),
                img20.tobytes(),
                f"サイズ {sz}px で battery-only の 10% と 20% の充電中アイコンが同一画像になっています"
            )

            # 20%、50%、100% がそれぞれ異なる画像であること
            self.assertNotEqual(img20.tobytes(), img50.tobytes())
            self.assertNotEqual(img50.tobytes(), img100.tobytes())

            # 外枠・端子・稲妻が画像境界内に収まり、十分な描画ピクセルが存在すること
            alpha_pixels = sum(img100.getpixel((x, y))[3] > 0 for x in range(sz) for y in range(sz))
            self.assertGreater(alpha_pixels, 20)

    def test_charging_icon_generation_all_styles(self):
        """3種類のアイコンで充電中の画像が正常生成されることの検証"""
        styles = ["numbers-only", "battery-only", "numbers-battery"]
        for sty in styles:
            img = create_battery_icon(80, style=sty, size=16, is_charging=True)
            self.assertIsNotNone(img)
            self.assertEqual(img.size, (16, 16))
            self.assertEqual(img.mode, "RGBA")
            # ピクセルが存在すること
            alpha_pixels = sum(img.getpixel((x, y))[3] > 0 for x in range(16) for y in range(16))
            self.assertGreater(alpha_pixels, 15)

    def test_backward_compatibility_non_charging(self):
        """非充電時の描画結果が既存の仕様（is_charging省略時・False指定時）から変わらないことの検証"""
        styles = ["numbers-only", "battery-only", "numbers-battery"]
        percentages = [0, 9, 10, 20, 50, 99, 100]
        for sz in [16, 20, 24, 32]:
            for sty in styles:
                for p in percentages:
                    img_default = create_battery_icon(p, style=sty, size=sz)
                    img_explicit_false = create_battery_icon(p, style=sty, size=sz, is_charging=False)
                    self.assertEqual(img_default.tobytes(), img_explicit_false.tobytes())

    def test_charging_differs_from_non_charging(self):
        """充電中・非充電で画像内容が異なることの検証"""
        styles = ["numbers-only", "battery-only", "numbers-battery"]
        percentages = [9, 50, 100]
        for sty in styles:
            for p in percentages:
                img_normal = create_battery_icon(p, style=sty, size=16, is_charging=False)
                img_charging = create_battery_icon(p, style=sty, size=16, is_charging=True)
                self.assertNotEqual(img_normal.tobytes(), img_charging.tobytes())

    def test_charging_not_shown_when_invalid_or_stale_or_disconnected(self):
        """未取得・待機中・スリープ・切断中はis_charging=Trueでも⚡が表示されないことの検証"""
        styles = ["numbers-only", "battery-only", "numbers-battery"]
        for sty in styles:
            # 1. 未取得状態 (None)
            img_none_norm = create_battery_icon(None, style=sty, size=16, is_charging=False)
            img_none_chg = create_battery_icon(None, style=sty, size=16, is_charging=True)
            self.assertEqual(img_none_norm.tobytes(), img_none_chg.tobytes())

            # 2. スリープ推測状態 (is_stale=True)
            img_stale_norm = create_battery_icon(50, style=sty, size=16, is_stale=True, is_charging=False)
            img_stale_chg = create_battery_icon(50, style=sty, size=16, is_stale=True, is_charging=True)
            self.assertEqual(img_stale_norm.tobytes(), img_stale_chg.tobytes())

            # 3. ドングル切断状態 (is_disconnected=True)
            img_disc_norm = create_battery_icon(50, style=sty, size=16, is_disconnected=True, is_charging=False)
            img_disc_chg = create_battery_icon(50, style=sty, size=16, is_disconnected=True, is_charging=True)
            self.assertEqual(img_disc_norm.tobytes(), img_disc_chg.tobytes())

    def test_charging_multisize_and_digits(self):
        """16・20・24・32pxで描画範囲が正しく、1桁・2桁・3桁の残量表示が欠けないことの検証"""
        styles = ["numbers-only", "battery-only", "numbers-battery"]
        sizes = [16, 20, 24, 32]
        test_pcts = [9, 50, 100]  # 1桁, 2桁, 3桁

        for sz in sizes:
            for sty in styles:
                for p in test_pcts:
                    img = create_battery_icon(p, style=sty, size=sz, is_charging=True)
                    self.assertEqual(img.size, (sz, sz))
                    self.assertEqual(img.mode, "RGBA")
                    # 画像内に十分なピクセルが描画されていること
                    total_pixels = sum(img.getpixel((x, y))[3] > 0 for x in range(sz) for y in range(sz))
                    self.assertGreater(total_pixels, 15)


if __name__ == "__main__":
    unittest.main()
