"""LAMZU Thorn V2 バッテリープロトコル解析モジュール

USB HID Input Report (Report ID: 0x04) のPayloadを解析し、
バッテリー残量および接続・充電状態コードを抽出する。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Union, List


class PacketType(Enum):
    """HIDパケットの種別定義"""
    FORMAT_A = "FORMAT_A"  # 先頭 0x38: バッテリー残量を含む正式パケット候補
    FORMAT_B = "FORMAT_B"  # 先頭 0x03: ケーブル抜き差し時等に観測される補助パケット（0%誤認防止対象）
    UNKNOWN = "UNKNOWN"    # 未知のパケットヘッダー
    INVALID = "INVALID"    # 長さ不足や異常値を含む不正パケット


class ChargingState(Enum):
    """充電状態の定義"""
    UNKNOWN = "UNKNOWN"          # 不明・判定不能
    NOT_CHARGING = "NOT_CHARGING"# 非充電（通常使用中）
    CHARGING = "CHARGING"        # 充電中


@dataclass
class ParsedPacket:
    """パケット解析結果オブジェクト"""
    packet_type: PacketType
    is_valid_battery: bool
    battery_level: Optional[int]
    status_code: Optional[int]
    state_value: Optional[int]
    report_id: Optional[int]
    raw_data: bytes
    payload: bytes
    charging_state: ChargingState = ChargingState.UNKNOWN
    error_message: Optional[str] = None

    def get_status_description(self) -> str:
        """状態コードの日本語説明を取得"""
        if self.status_code is None:
            return "不明"
        match self.status_code:
            case 0x00:
                return "通常動作 / 非充電 (0x00)"
            case 0x02:
                return "遷移・未確定状態 (0x02)"
            case 0x04:
                return "充電中 (0x04)"
            case _:
                return f"未確定状態コード (0x{self.status_code:02X})"


def format_hex(data: Union[bytes, bytearray, List[int]]) -> str:
    """バイト列を16進数スペース区切り文字列に変換"""
    if isinstance(data, (list, tuple)):
        data = bytes(data)
    return " ".join(f"{b:02x}" for b in data)


def parse_packet(raw_input: Union[bytes, bytearray, List[int]]) -> ParsedPacket:
    """Input Reportの生データを解析する

    Windows HIDAPIなどのライブラリによって、先頭にReport IDが付与される場合と
    付与されない場合の両方に対応する。

    Args:
        raw_input: HIDデバイスから読み取った生データ (bytes または intのリスト)

    Returns:
        ParsedPacket: 解析結果
    """
    if isinstance(raw_input, (list, tuple)):
        raw_bytes = bytes(raw_input)
    elif isinstance(raw_input, bytearray):
        raw_bytes = bytes(raw_input)
    elif isinstance(raw_input, bytes):
        raw_bytes = raw_input
    else:
        return ParsedPacket(
            packet_type=PacketType.INVALID,
            is_valid_battery=False,
            battery_level=None,
            status_code=None,
            state_value=None,
            report_id=None,
            raw_data=b"",
            payload=b"",
            error_message="入力データ形式が不正です (bytesまたはlist[int]が必要)"
        )

    if len(raw_bytes) == 0:
        return ParsedPacket(
            packet_type=PacketType.INVALID,
            is_valid_battery=False,
            battery_level=None,
            status_code=None,
            state_value=None,
            report_id=None,
            raw_data=raw_bytes,
            payload=b"",
            error_message="データ長が0です"
        )

    # Report IDの分離処理
    # Report ID 0x04 または 0x03 が先頭に付与されている場合 (長さ9バイト以上で先頭が0x04等)
    report_id = None
    payload = raw_bytes

    if len(raw_bytes) >= 9 and raw_bytes[0] in (0x04, 0x03, 0x05):
        report_id = raw_bytes[0]
        payload = raw_bytes[1:]
    elif len(raw_bytes) == 8:
        # Report IDが含まれていない純粋なPayload (WebHIDのイベントと同様)
        report_id = None
        payload = raw_bytes

    # Payload長の検証 (最低8バイト必要)
    if len(payload) < 8:
        return ParsedPacket(
            packet_type=PacketType.INVALID,
            is_valid_battery=False,
            battery_level=None,
            status_code=None,
            state_value=None,
            report_id=report_id,
            raw_data=raw_bytes,
            payload=payload,
            error_message=f"Payload長が不足しています (必要: 8バイト, 実際: {len(payload)}バイト)"
        )

    header = payload[0]

    # 形式A: 先頭が 0x38 のパケット (バッテリー残量取得対象)
    if header == 0x38:
        status_code = payload[2]
        state_value = payload[3]
        battery_candidate = payload[4]

        # 充電状態の判定 (実機通信検証に基づく)
        if status_code == 0x04:
            charging_state = ChargingState.CHARGING
        elif status_code == 0x00:
            charging_state = ChargingState.NOT_CHARGING
        else:
            charging_state = ChargingState.UNKNOWN

        # 残量値の範囲チェック (0〜100%)
        if not (0 <= battery_candidate <= 100):
            return ParsedPacket(
                packet_type=PacketType.INVALID,
                is_valid_battery=False,
                battery_level=None,
                status_code=status_code,
                state_value=state_value,
                report_id=report_id,
                raw_data=raw_bytes,
                payload=payload,
                charging_state=charging_state,
                error_message=f"バッテリー残量が許容範囲外です: {battery_candidate}% (0〜100%が必要)"
            )

        return ParsedPacket(
            packet_type=PacketType.FORMAT_A,
            is_valid_battery=True,
            battery_level=battery_candidate,
            status_code=status_code,
            state_value=state_value,
            report_id=report_id,
            raw_data=raw_bytes,
            payload=payload,
            charging_state=charging_state,
            error_message=None
        )

    # 形式B: 先頭が 0x03 のパケット (0%誤認防止対象・充電状態通知補助)
    if header == 0x03:
        charge_flag = payload[2] if len(payload) > 2 else None

        if charge_flag == 0x01:
            charging_state = ChargingState.CHARGING
        elif charge_flag == 0x00:
            charging_state = ChargingState.NOT_CHARGING
        else:
            charging_state = ChargingState.UNKNOWN

        return ParsedPacket(
            packet_type=PacketType.FORMAT_B,
            is_valid_battery=False,
            battery_level=None,
            status_code=charge_flag,
            state_value=None,
            report_id=report_id,
            raw_data=raw_bytes,
            payload=payload,
            charging_state=charging_state,
            error_message=None
        )

    # その他の未知パケット
    return ParsedPacket(
        packet_type=PacketType.UNKNOWN,
        is_valid_battery=False,
        battery_level=None,
        status_code=None,
        state_value=None,
        report_id=report_id,
        raw_data=raw_bytes,
        payload=payload,
        error_message=f"未知のパケットヘッダーです: 0x{header:02X}"
    )
