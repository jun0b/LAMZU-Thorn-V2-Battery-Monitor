"""LAMZU Thorn V2 バッテリープロトコル解析の単体テスト

実機HIDデバイスを必要とせず、既知のパケット生データを用いて
プロトコル解析エンジンの動作を検証します。
"""

import unittest
from battery_protocol import parse_packet, PacketType


class TestBatteryProtocol(unittest.TestCase):
    """バッテリーパケット解析の検証テストケース"""

    def test_battery_99_percent(self):
        """通常使用時 99% パケットの解析 (Payload単体)"""
        raw = bytes.fromhex("38 02 00 58 63 00 a5 d1")
        result = parse_packet(raw)
        self.assertEqual(result.packet_type, PacketType.FORMAT_A)
        self.assertTrue(result.is_valid_battery)
        self.assertEqual(result.battery_level, 99)
        self.assertEqual(result.status_code, 0x00)
        self.assertEqual(result.state_value, 0x58)

    def test_battery_100_percent(self):
        """通常使用時 100% パケットの解析 (Payload単体)"""
        raw = bytes.fromhex("38 02 00 59 64 00 a5 d1")
        result = parse_packet(raw)
        self.assertEqual(result.packet_type, PacketType.FORMAT_A)
        self.assertTrue(result.is_valid_battery)
        self.assertEqual(result.battery_level, 100)
        self.assertEqual(result.status_code, 0x00)

    def test_charging_status_code(self):
        """充電ケーブル接続時 100%・状態コード0x04の解析"""
        raw = bytes.fromhex("38 02 04 58 64 00 a5 d1")
        result = parse_packet(raw)
        self.assertEqual(result.packet_type, PacketType.FORMAT_A)
        self.assertTrue(result.is_valid_battery)
        self.assertEqual(result.battery_level, 100)
        self.assertEqual(result.status_code, 0x04)

    def test_format_b_not_zero_percent_packet1(self):
        """形式Bパケット (03 64 ...) で0%と誤認しないことの検証"""
        raw = bytes.fromhex("03 64 00 00 00 00 00 00")
        result = parse_packet(raw)
        self.assertEqual(result.packet_type, PacketType.FORMAT_B)
        self.assertFalse(result.is_valid_battery)
        self.assertIsNone(result.battery_level)
        self.assertNotEqual(result.battery_level, 0)

    def test_format_b_not_zero_percent_packet2(self):
        """形式Bパケット (03 63 ...) で0%と誤認しないことの検証"""
        raw = bytes.fromhex("03 63 01 00 00 00 00 00")
        result = parse_packet(raw)
        self.assertEqual(result.packet_type, PacketType.FORMAT_B)
        self.assertFalse(result.is_valid_battery)
        self.assertIsNone(result.battery_level)
        self.assertNotEqual(result.battery_level, 0)

    def test_report_id_offset_handling(self):
        """Report ID 0x04 が付与された9バイトデータの解析"""
        raw = bytes.fromhex("04 38 02 00 59 64 00 a5 d1")
        result = parse_packet(raw)
        self.assertEqual(result.report_id, 0x04)
        self.assertEqual(result.packet_type, PacketType.FORMAT_A)
        self.assertTrue(result.is_valid_battery)
        self.assertEqual(result.battery_level, 100)
        self.assertEqual(result.status_code, 0x00)

    def test_report_id_with_format_b(self):
        """Report ID 0x04 が付与された形式Bデータの解析"""
        raw = bytes.fromhex("04 03 64 00 00 00 00 00 00")
        result = parse_packet(raw)
        self.assertEqual(result.report_id, 0x04)
        self.assertEqual(result.packet_type, PacketType.FORMAT_B)
        self.assertFalse(result.is_valid_battery)
        self.assertIsNone(result.battery_level)

    def test_list_of_ints_input(self):
        """hidapiのlist[int]戻り値の互換性検証"""
        raw_list = [0x04, 0x38, 0x02, 0x00, 0x59, 0x64, 0x00, 0xA5, 0xD1]
        result = parse_packet(raw_list)
        self.assertEqual(result.packet_type, PacketType.FORMAT_A)
        self.assertTrue(result.is_valid_battery)
        self.assertEqual(result.battery_level, 100)

    def test_valid_zero_percent(self):
        """形式Aでの正当な0%パケットは0%として受け入れることの検証"""
        raw = bytes.fromhex("38 02 00 58 00 00 a5 d1")
        result = parse_packet(raw)
        self.assertEqual(result.packet_type, PacketType.FORMAT_A)
        self.assertTrue(result.is_valid_battery)
        self.assertEqual(result.battery_level, 0)

    def test_battery_out_of_range(self):
        """バッテリー残量が101%など範囲外の場合はINVALIDと判定"""
        raw = bytes.fromhex("38 02 00 58 65 00 a5 d1")  # 0x65 = 101%
        result = parse_packet(raw)
        self.assertEqual(result.packet_type, PacketType.INVALID)
        self.assertFalse(result.is_valid_battery)
        self.assertIsNone(result.battery_level)

    def test_short_payload(self):
        """8バイト未満の短いパケットの処理"""
        raw = bytes.fromhex("38 02 00")
        result = parse_packet(raw)
        self.assertEqual(result.packet_type, PacketType.INVALID)
        self.assertFalse(result.is_valid_battery)

    def test_unknown_header(self):
        """未知のヘッダーパケットの処理"""
        raw = bytes.fromhex("99 02 00 58 63 00 a5 d1")
        result = parse_packet(raw)
        self.assertEqual(result.packet_type, PacketType.UNKNOWN)
        self.assertFalse(result.is_valid_battery)

    def test_empty_input(self):
        """空データ入力の処理"""
        result = parse_packet(b"")
        self.assertEqual(result.packet_type, PacketType.INVALID)
        self.assertFalse(result.is_valid_battery)


if __name__ == "__main__":
    unittest.main()
