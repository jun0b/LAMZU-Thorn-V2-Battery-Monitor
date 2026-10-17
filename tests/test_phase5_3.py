"""LAMZU Thorn V2 充電状態判定および⚡アイコン表示単体テスト

充電中・非充電中・不明状態のパケット解析、スレッドセーフな状態管理、
切断・スリープ時の安全性、およびCanvas上の稲妻アイコン描画を検証する。
"""

import unittest
from unittest.mock import MagicMock, patch
import tkinter as tk

from battery_protocol import parse_packet, PacketType, ChargingState
from battery_state import BatteryState, ReceiveState
from status_panel import StatusPanel


class TestPhase53ChargingProtocol(unittest.TestCase):
    """battery_protocolモジュールの充電状態判定検証"""

    def test_format_a_charging_detected(self):
        """形式Aパケットでstatus_code=0x04の時にCHARGINGと判定されること"""
        # 実機ログ: 04 38 03 04 54 5F 00 A5 D1 (残量95%)
        raw = [4, 56, 3, 4, 84, 95, 0, 165, 209]
        parsed = parse_packet(raw)
        self.assertEqual(parsed.packet_type, PacketType.FORMAT_A)
        self.assertTrue(parsed.is_valid_battery)
        self.assertEqual(parsed.battery_level, 95)
        self.assertEqual(parsed.status_code, 0x04)
        self.assertEqual(parsed.charging_state, ChargingState.CHARGING)
        self.assertIn("充電中", parsed.get_status_description())

    def test_format_a_charging_complete_detected(self):
        """形式Aパケットでstatus_code=0x02の時にCHARGING_COMPLETEと判定されること"""
        # 実機ログ: 04 38 02 02 58 64 00 A5 D1 (残量100%)
        raw = [4, 56, 2, 2, 88, 100, 0, 165, 209]
        parsed = parse_packet(raw)
        self.assertEqual(parsed.packet_type, PacketType.FORMAT_A)
        self.assertTrue(parsed.is_valid_battery)
        self.assertEqual(parsed.battery_level, 100)
        self.assertEqual(parsed.status_code, 0x02)
        self.assertEqual(parsed.charging_state, ChargingState.CHARGING_COMPLETE)
        self.assertIn("充電完了", parsed.get_status_description())

    def test_format_a_not_charging_detected(self):
        """形式Aパケットでstatus_code=0x00の時にNOT_CHARGINGと判定されること"""
        # 実機ログ: 04 38 03 00 54 5E 00 A5 D1 (残量94%)
        raw = [4, 56, 3, 0, 84, 94, 0, 165, 209]
        parsed = parse_packet(raw)
        self.assertEqual(parsed.packet_type, PacketType.FORMAT_A)
        self.assertTrue(parsed.is_valid_battery)
        self.assertEqual(parsed.battery_level, 94)
        self.assertEqual(parsed.status_code, 0x00)
        self.assertEqual(parsed.charging_state, ChargingState.NOT_CHARGING)

    def test_format_a_unknown_status_code(self):
        """形式Aパケットで未定義status_codeの時にUNKNOWNと判定されること"""
        raw = [4, 56, 3, 0x99, 84, 90, 0, 165, 209]
        parsed = parse_packet(raw)
        self.assertEqual(parsed.packet_type, PacketType.FORMAT_A)
        self.assertEqual(parsed.charging_state, ChargingState.UNKNOWN)

    def test_format_b_charging_detected(self):
        """形式Bパケット (Aurora公式仕様) でcharge_flag=0x01の時にCHARGINGと判定されること"""
        # 実機ログ: 04 03 60 01 00 00 00 00 00 (0%誤認防止のため残量はNoneを維持)
        raw = [4, 3, 96, 1, 0, 0, 0, 0, 0]
        parsed = parse_packet(raw)
        self.assertEqual(parsed.packet_type, PacketType.FORMAT_B)
        self.assertFalse(parsed.is_valid_battery)
        self.assertIsNone(parsed.battery_level)
        self.assertEqual(parsed.status_code, 0x01)
        self.assertEqual(parsed.charging_state, ChargingState.CHARGING)

    def test_format_b_not_charging_detected(self):
        """形式Bパケットでcharge_flag=0x00の時にNOT_CHARGINGと判定されること"""
        raw = [4, 3, 90, 0, 0, 0, 0, 0, 0]
        parsed = parse_packet(raw)
        self.assertEqual(parsed.packet_type, PacketType.FORMAT_B)
        self.assertFalse(parsed.is_valid_battery)
        self.assertIsNone(parsed.battery_level)
        self.assertEqual(parsed.status_code, 0x00)
        self.assertEqual(parsed.charging_state, ChargingState.NOT_CHARGING)

    def test_invalid_packet_length_handling(self):
        """データ長不足パケットが安全にINVALIDと処理されること"""
        short_raw = [4, 56, 3]
        parsed = parse_packet(short_raw)
        self.assertEqual(parsed.packet_type, PacketType.INVALID)
        self.assertFalse(parsed.is_valid_battery)
        self.assertEqual(parsed.charging_state, ChargingState.UNKNOWN)

    def test_out_of_range_battery_handling(self):
        """許容範囲外(>100%)の残量パケットが安全にINVALIDと処理されること"""
        invalid_bat = [4, 56, 3, 4, 84, 150, 0, 165, 209]
        parsed = parse_packet(invalid_bat)
        self.assertEqual(parsed.packet_type, PacketType.INVALID)
        self.assertFalse(parsed.is_valid_battery)


class TestPhase53BatteryStateTransitions(unittest.TestCase):
    """BatteryStateにおける充電状態のライフサイクル・状態遷移検証"""

    def setUp(self):
        self.state = BatteryState()
        self.state.set_dongle_available(True)

    def test_charging_state_update(self):
        """update_batteryによる充電状態の正常反映"""
        self.state.update_battery(95, status_code=0x04, charging_state=ChargingState.CHARGING)
        self.assertEqual(self.state.percent, 95)
        self.assertEqual(self.state.charging_state, ChargingState.CHARGING)
        self.assertTrue(self.state.is_charging)
        self.assertFalse(self.state.is_charging_complete)

    def test_charging_complete_state_update_and_format_b_preservation(self):
        """充電完了(CHARGING_COMPLETE)の反映と、形式B(CHARGING)受信時に上書きされないことの検証"""
        self.state.update_battery(100, status_code=0x02, charging_state=ChargingState.CHARGING_COMPLETE)
        self.assertEqual(self.state.percent, 100)
        self.assertEqual(self.state.charging_state, ChargingState.CHARGING_COMPLETE)
        self.assertTrue(self.state.is_charging_complete)
        self.assertFalse(self.state.is_charging)

        # 形式Bの充電フラグ(CHARGING)が届いてもCHARGING_COMPLETEが維持されること
        self.state.update_non_battery_packet(charging_state=ChargingState.CHARGING)
        self.assertTrue(self.state.is_charging_complete)
        self.assertEqual(self.state.charging_state, ChargingState.CHARGING_COMPLETE)

        # 形式Bの非充電フラグ(NOT_CHARGING)が届いた場合はNOT_CHARGINGへ遷移すること
        self.state.update_non_battery_packet(charging_state=ChargingState.NOT_CHARGING)
        self.assertFalse(self.state.is_charging_complete)
        self.assertEqual(self.state.charging_state, ChargingState.NOT_CHARGING)

    def test_not_charging_state_update(self):
        """非充電状態への更新とis_chargingがFalseになること"""
        self.state.update_battery(95, status_code=0x04, charging_state=ChargingState.CHARGING)
        self.assertTrue(self.state.is_charging)

        self.state.update_battery(95, status_code=0x00, charging_state=ChargingState.NOT_CHARGING)
        self.assertFalse(self.state.is_charging)
        self.assertEqual(self.state.charging_state, ChargingState.NOT_CHARGING)

    def test_dongle_disconnect_resets_charging(self):
        """ドングル切断時にis_chargingがFalseとなり充電状態がリセットされること"""
        self.state.update_battery(95, status_code=0x04, charging_state=ChargingState.CHARGING)
        self.assertTrue(self.state.is_charging)

        self.state.set_dongle_available(False)
        self.assertTrue(self.state.is_disconnected)
        self.assertFalse(self.state.is_charging)
        self.assertEqual(self.state.charging_state, ChargingState.UNKNOWN)

    def test_staleness_suppresses_charging(self):
        """通信途絶(スリープ推測)時にis_chargingがFalseとなること"""
        self.state.update_battery(95, status_code=0x04, charging_state=ChargingState.CHARGING)
        self.assertTrue(self.state.is_charging)

        # タイムアウト経過をシミュレート
        self.state.last_valid_battery_at -= 20.0
        self.state.check_staleness()
        self.assertTrue(self.state.is_stale)
        self.assertFalse(self.state.is_charging)


class TestPhase53StatusPanelLightningUI(unittest.TestCase):
    """ステータスパネルにおける⚡アイコン描画検証"""

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
        self.state.set_dongle_available(True)

    def tearDown(self):
        self.panel.hide()
        self.panel.destroy()
        try:
            self.root.update()
        except Exception:
            pass

    def test_lightning_bolt_rendered_when_charging(self):
        """充電中(CHARGING)のとき⚡ポリゴンアイコンがCanvasに描画されること"""
        self.state.update_battery(95, status_code=0x04, charging_state=ChargingState.CHARGING)
        self.panel.show(self.state)
        self.root.update()

        bolts = self.panel.canvas.find_withtag("lightning_bolt")
        self.assertEqual(len(bolts), 1)

        # 状態テキストが「接続中・充電中」であること
        items = self.panel.canvas.find_all()
        texts = [self.panel.canvas.itemcget(i, "text") for i in items if self.panel.canvas.type(i) == "text"]
        self.assertIn("● 接続中・充電中", texts)

    def test_cyan_and_lightning_bolt_rendered_when_charging_complete(self):
        """充電完了(CHARGING_COMPLETE)のとき水色/シアン表示と⚡アイコンが両立すること"""
        self.state.update_battery(100, status_code=0x02, charging_state=ChargingState.CHARGING_COMPLETE)
        self.panel.show(self.state)
        self.root.update()

        # ⚡アイコンが描画されていること
        bolts = self.panel.canvas.find_withtag("lightning_bolt")
        self.assertEqual(len(bolts), 1)

        # 状態テキストが「● 接続中・充電完了」であり、色がCOLOR_CYAN (#00D2FF) であること
        items = self.panel.canvas.find_all()
        text_items = {
            self.panel.canvas.itemcget(i, "text"): self.panel.canvas.itemcget(i, "fill")
            for i in items if self.panel.canvas.type(i) == "text"
        }
        self.assertIn("● 接続中・充電完了", text_items)
        self.assertEqual(text_items["● 接続中・充電完了"], StatusPanel.COLOR_CYAN)
        self.assertEqual(text_items["100%"], StatusPanel.COLOR_CYAN)

    def test_no_lightning_bolt_when_not_charging(self):
        """非充電(NOT_CHARGING)のとき⚡アイコンが描画されないこと"""
        self.state.update_battery(95, status_code=0x00, charging_state=ChargingState.NOT_CHARGING)
        self.panel.show(self.state)
        self.root.update()

        bolts = self.panel.canvas.find_withtag("lightning_bolt")
        self.assertEqual(len(bolts), 0)

        items = self.panel.canvas.find_all()
        texts = [self.panel.canvas.itemcget(i, "text") for i in items if self.panel.canvas.type(i) == "text"]
        self.assertIn("● 接続中・受信正常", texts)
        self.assertNotIn("● 接続中・充電中", texts)

    def test_no_lightning_bolt_when_unknown(self):
        """充電状態不明(UNKNOWN)のとき⚡アイコンが描画されないこと"""
        self.state.update_battery(95, status_code=0x99, charging_state=ChargingState.UNKNOWN)
        self.panel.show(self.state)
        self.root.update()

        bolts = self.panel.canvas.find_withtag("lightning_bolt")
        self.assertEqual(len(bolts), 0)

    def test_no_lightning_bolt_when_disconnected(self):
        """切断時は充電フラグがあっても⚡アイコンが描画されないこと"""
        self.state.update_battery(95, status_code=0x04, charging_state=ChargingState.CHARGING)
        self.state.set_dongle_available(False)
        self.panel.show(self.state)
        self.root.update()

        bolts = self.panel.canvas.find_withtag("lightning_bolt")
        self.assertEqual(len(bolts), 0)


if __name__ == '__main__':
    unittest.main()
