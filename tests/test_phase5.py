"""LAMZU Thorn V2 DPI・ポーリングレートプロトコル解析単体テスト

公式Webドライバー (LAMZU Aurora) のフロントエンド解析により判明した
DPIテーブル (0x81)、アクティブDPI (0x82)、ポーリングレート (0x80) の
プロトコル仕様に基づくパーサーロジックおよび境界値・異常系検証を行います。
※デバイスへの送信テストではなく、純粋なデータ検証 (Mock/Unit Test) です。
"""

import unittest
from typing import Optional, List, Tuple, Dict, Any


def parse_dpi_stage_packet(data: bytes) -> Optional[Dict[str, Any]]:
    """LAMZU Aurora仕様に基づくDPIステージ情報パケット (コマンド 0x81) の解析

    フォーマット:
      バイト[0]: 0xA1 (ヘッダー)
      バイト[1]: 0x00
      バイト[2]: 0x02
      バイト[3]: 長さ
      バイト[4]: サブタイプ (0x01)
      バイト[5]: コマンドID (0x81 = DPIステージ情報)
      バイト[6]: 0x01
      バイト[7]: ステージ数
      バイト[8..]: 各ステージの X-DPI (2B Big-Endian), Y-DPI (2B Big-Endian)
    """
    if not isinstance(data, (bytes, bytearray)):
        return None
    if len(data) < 8:
        return None
    if data[0] != 0xA1 or data[5] != 0x81:
        return None

    stage_count = data[7]
    if stage_count <= 0 or stage_count > 8:
        return None

    expected_len = 8 + stage_count * 4
    if len(data) < expected_len:
        return None

    stages = []
    offset = 8
    for _ in range(stage_count):
        x_dpi = (data[offset] << 8) | data[offset + 1]
        y_dpi = (data[offset + 2] << 8) | data[offset + 3]
        stages.append((x_dpi, y_dpi))
        offset += 4

    return {
        "stage_count": stage_count,
        "stages": stages,
    }


def parse_active_dpi_packet(data: bytes) -> Optional[int]:
    """アクティブDPIステージ番号パケット (コマンド 0x82) の解析

    バイト[7] または バイト[8] に1-basedのステージ番号 (1, 2, 3...) が格納される
    """
    if not isinstance(data, (bytes, bytearray)) or len(data) < 9:
        return None
    if data[0] != 0xA1:
        return None
    stage = data[8]
    if 1 <= stage <= 8:
        return stage
    return None


def parse_polling_rate_packet(data: bytes) -> Optional[int]:
    """ポーリングレートパケット (コマンド 0x80) のコード値からHzへの変換

    コード値:
      1 -> 1000 Hz
      2 -> 2000 Hz
      4 -> 4000 Hz
      8 -> 8000 Hz
      16 -> 1000 Hz (Auroraの特別処理: 16 -> 1)
    """
    if not isinstance(data, (bytes, bytearray)) or len(data) < 9:
        return None
    if data[0] != 0xA1:
        return None
    code = data[8]
    if code == 16:
        code = 1

    rate_map = {
        1: 1000,
        2: 2000,
        4: 4000,
        8: 8000,
    }
    return rate_map.get(code)


class TestPhase5ProtocolAnalysis(unittest.TestCase):
    """Phase 5 DPI & ポーリングレート解析ロジックの検証"""

    def test_parse_reference_dpi_packet(self):
        """ユーザー提示の参考データパケットが正確に解析されることの検証"""
        # 参考データ:
        # a1 00 02 0e 01 81 01 03 01 90 01 90 03 20 03 20 06 40 06 40
        ref_data = bytes([
            0xA1, 0x00, 0x02, 0x0E, 0x01, 0x81, 0x01, 0x03,
            0x01, 0x90, 0x01, 0x90,  # Stage 1: 400, 400
            0x03, 0x20, 0x03, 0x20,  # Stage 2: 800, 800
            0x06, 0x40, 0x06, 0x40   # Stage 3: 1600, 1600
        ])
        result = parse_dpi_stage_packet(ref_data)
        self.assertIsNotNone(result)
        self.assertEqual(result["stage_count"], 3)
        self.assertEqual(len(result["stages"]), 3)
        self.assertEqual(result["stages"][0], (400, 400))
        self.assertEqual(result["stages"][1], (800, 800))
        self.assertEqual(result["stages"][2], (1600, 1600))

    def test_parse_invalid_or_truncated_dpi_packet(self):
        """不正なデータや長さ不足でNoneが返ることの検証"""
        # 長さ不足
        self.assertIsNone(parse_dpi_stage_packet(b"\xA1\x00\x02"))
        # ヘッダー不正
        self.assertIsNone(parse_dpi_stage_packet(b"\xFF\x00\x02\x0E\x01\x81\x01\x03\x01\x90\x01\x90"))
        # コマンドID不一致 (0x82 シリアル情報)
        serial_packet = bytes([0xA1, 0x00, 0x02, 0x16, 0x00, 0x82, 0x03, 0xFF] + [0x30]*20)
        self.assertIsNone(parse_dpi_stage_packet(serial_packet))
        # ステージデータ欠落
        truncated = bytes([0xA1, 0x00, 0x02, 0x0E, 0x01, 0x81, 0x01, 0x03, 0x01, 0x90])
        self.assertIsNone(parse_dpi_stage_packet(truncated))

    def test_parse_active_dpi_stage(self):
        """アクティブDPIステージ番号の解析検証"""
        # Stage 2 (800 DPI)
        active_packet = bytes([0xA1, 0x00, 0x02, 0x02, 0x01, 0x82, 0x00, 0x00, 0x02] + [0x00]*55)
        stage = parse_active_dpi_packet(active_packet)
        self.assertEqual(stage, 2)

        # 範囲外ステージ (0 や 99)
        invalid_active = bytes([0xA1, 0x00, 0x02, 0x02, 0x01, 0x82, 0x00, 0x00, 0x00] + [0x00]*55)
        self.assertIsNone(parse_active_dpi_packet(invalid_active))

    def test_parse_polling_rate(self):
        """ポーリングレートコード値の解析検証"""
        # 1000 Hz (code=1)
        pkt_1k = bytes([0xA1, 0x00, 0x02, 0x02, 0x01, 0x80, 0x00, 0x00, 0x01] + [0x00]*55)
        self.assertEqual(parse_polling_rate_packet(pkt_1k), 1000)

        # 4000 Hz (code=4)
        pkt_4k = bytes([0xA1, 0x00, 0x02, 0x02, 0x01, 0x80, 0x00, 0x00, 0x04] + [0x00]*55)
        self.assertEqual(parse_polling_rate_packet(pkt_4k), 4000)

        # 8000 Hz (code=8)
        pkt_8k = bytes([0xA1, 0x00, 0x02, 0x02, 0x01, 0x80, 0x00, 0x00, 0x08] + [0x00]*55)
        self.assertEqual(parse_polling_rate_packet(pkt_8k), 8000)

        # 特殊コード 16 (Aurora内部で1=1000Hzへマッピング)
        pkt_16 = bytes([0xA1, 0x00, 0x02, 0x02, 0x01, 0x80, 0x00, 0x00, 0x10] + [0x00]*55)
        self.assertEqual(parse_polling_rate_packet(pkt_16), 1000)

        # 未知のコード
        pkt_unknown = bytes([0xA1, 0x00, 0x02, 0x02, 0x01, 0x80, 0x00, 0x00, 0x99] + [0x00]*55)
        self.assertIsNone(parse_polling_rate_packet(pkt_unknown))


if __name__ == "__main__":
    unittest.main()
