"""LAMZU Thorn V2 Battery Monitor - HID通信検証プローブ

LAMZU 8K Dongle V2 (VID: 0x37B0, PID: 0x002E) とのHID通信を検証し、
公式WebドライバーなしでInput Report (Report ID: 0x04) から
バッテリー残量を読み取る。

注意: 本スクリプトは読み取り専用 (Read-Only) である。
いかなるデータ送信 (Output/Feature Report) も行わない。
"""

import argparse
import datetime
import os
import re
import sys
import time
from typing import Optional, Dict, Any, List

# Windows環境における文字化け防止
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import hid
from battery_protocol import parse_packet, format_hex, PacketType, ParsedPacket

# LAMZU 8K Dongle V2 のハードウェアID
TARGET_VID = 0x37B0
TARGET_PID = 0x002E

# 対象コレクションのUsage Page / Usage (WebHID Device #0 の設定値)
TARGET_USAGE_PAGE = 0xFFA0
TARGET_USAGE = 0x0001

# 除外対象 (キーボード等への誤アクセス防止)
KEYBOARD_VID = 0x19F5
KEYBOARD_PID = 0xFEF0


def mask_device_path(path: Any) -> str:
    """デバイスパスに含まれるシリアル番号やGUID等の識別情報をマスクする

    例: \\\\?\\HID#VID_37B0&PID_002E&MI_01&Col04#b&1708816b&0&0003#{4d1e55b2...}
    -> \\\\?\\HID#VID_37B0&PID_002E&MI_01&Col04#***#{***}
    """
    if isinstance(path, bytes):
        path_str = path.decode("utf-8", errors="replace")
    else:
        path_str = str(path)

    # インスタンスID部分とGUID部分をマスク
    parts = path_str.split("#")
    if len(parts) >= 4:
        header = parts[0]
        device_id = parts[1]  # VID_37B0&PID_002E&MI_01&Col04
        return f"{header}#{device_id}#***#{{***}}"
    return re.sub(r"\{[0-9a-fA-F\-]{36}\}", "{***}", path_str)


def enumerate_candidates(vid: int = TARGET_VID, pid: int = TARGET_PID) -> List[Dict[str, Any]]:
    """指定されたVID/PIDに一致するHIDデバイスを列挙し、オープン可否を診断する"""
    all_devices = hid.enumerate(vid, pid)
    candidates = []

    for d in all_devices:
        path = d.get("path")
        usage_page = d.get("usage_page", 0)
        usage = d.get("usage", 0)
        mi = d.get("interface_number", -1)
        product_name = d.get("product_string", "")
        manufacturer = d.get("manufacturer_string", "")

        # オープン可否の確認 (開いてすぐに閉じる)
        can_open = False
        open_error = None
        try:
            h = hid.device()
            h.open_path(path)
            h.close()
            can_open = True
        except Exception as e:
            open_error = str(e)

        is_target = (usage_page == TARGET_USAGE_PAGE and usage == TARGET_USAGE)

        candidates.append({
            "path": path,
            "masked_path": mask_device_path(path),
            "vendor_id": d.get("vendor_id"),
            "product_id": d.get("product_id"),
            "usage_page": usage_page,
            "usage": usage,
            "interface_number": mi,
            "product_name": product_name,
            "manufacturer": manufacturer,
            "can_open": can_open,
            "open_error": open_error,
            "is_target": is_target,
        })

    return candidates


def print_device_list(candidates: List[Dict[str, Any]]):
    """検出されたHID候補デバイスの一覧を表示する"""
    print("=" * 70)
    print("LAMZU Thorn V2 HID デバイス列挙結果")
    print(f"検索対象: VID=0x{TARGET_VID:04X}, PID=0x{TARGET_PID:04X}")
    print("=" * 70)

    if not candidates:
        print("[!] 対象デバイスが見つかりませんでした。")
        print("    ドングルがPCに接続されているか確認してください。")
        return

    print(f"検出件数: {len(candidates)} 件\n")

    for idx, c in enumerate(candidates):
        tag = " [推奨対象: バッテリーReport 0x04]" if c["is_target"] else ""
        open_status = "OK" if c["can_open"] else f"NG ({c['open_error']})"
        print(f"[{idx}] {c['product_name']} (MI_{c['interface_number']:02d}){tag}")
        print(f"    VID/PID       : 0x{c['vendor_id']:04X} / 0x{c['product_id']:04X}")
        print(f"    Usage Page/Usage: 0x{c['usage_page']:04X} / 0x{c['usage']:04X}")
        print(f"    Interface No. : {c['interface_number']}")
        print(f"    Open Status   : {open_status}")
        print(f"    Path (Masked) : {c['masked_path']}")
        print("-" * 70)


def run_probe_read(
    seconds: int = 60,
    debug: bool = False,
    target_index: Optional[int] = None
) -> Dict[str, Any]:
    """HIDデバイスからInput Reportを受信し、バッテリー残量を解析する

    Args:
        seconds: 読み取り実行秒数
        debug: デバッグモード (全受信パケットのHEX出力)
        target_index: 列挙候補から特定のインデックスを指定する場合

    Returns:
        Dict[str, Any]: 検証統計・結果サマリー
    """
    candidates = enumerate_candidates(TARGET_VID, TARGET_PID)

    if not candidates:
        print("[ERROR] 対象デバイス (VID: 0x37B0, PID: 0x002E) が見つかりません。")
        return {"success": False, "error": "Device not found"}

    # 読み取り対象の決定
    target = None
    if target_index is not None:
        if 0 <= target_index < len(candidates):
            target = candidates[target_index]
        else:
            print(f"[ERROR] 指定されたインデックス {target_index} は無効です。")
            return {"success": False, "error": "Invalid index"}
    else:
        # デフォルト: Usage Page 0xFFA0, Usage 0x0001 を優先探索
        for c in candidates:
            if c["is_target"]:
                target = c
                break
        if target is None:
            # 見つからない場合はオープン可能な最初の候補
            for c in candidates:
                if c["can_open"]:
                    target = c
                    break

    if target is None:
        print("[ERROR] オープン可能な対象候補が見つかりませんでした。")
        return {"success": False, "error": "No openable candidate found"}

    # ログファイルの準備
    os.makedirs("logs", exist_ok=True)
    timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file_path = os.path.join("logs", f"probe_{timestamp_str}.log")

    print("LAMZU Thorn V2 Battery Probe\n")
    print(f"Device: {target['product_name']}")
    print(f"VID: 0x{target['vendor_id']:04X}")
    print(f"PID: 0x{target['product_id']:04X}")
    print(f"Usage Page: 0x{target['usage_page']:04X}")
    print(f"Usage: 0x{target['usage']:04X}")
    print(f"Target Interface: MI_{target['interface_number']:02d}")
    print(f"Log File: {log_file_path}")
    print(f"Monitor Duration: {seconds} seconds (Ctrl+C to stop)\n")

    device = hid.device()
    try:
        device.open_path(target["path"])
        print("HID device opened successfully.\n")
    except Exception as e:
        print(f"[ERROR] デバイスのオープンに失敗しました: {e}")
        return {"success": False, "error": str(e)}

    stats = {
        "success": True,
        "total_packets": 0,
        "format_a_count": 0,
        "format_b_count": 0,
        "unknown_count": 0,
        "invalid_count": 0,
        "last_battery": None,
        "last_status_code": None,
        "last_valid_time": None,
        "raw_samples": [],  # サンプルデータ保持用
    }

    start_time = time.time()
    last_reported_battery = None
    last_reported_status = None
    last_heartbeat_time = start_time

    with open(log_file_path, "w", encoding="utf-8") as log_file:
        log_file.write(f"# LAMZU Thorn V2 Probe Log - {datetime.datetime.now().isoformat()}\n")
        log_file.write(f"# VID: 0x{target['vendor_id']:04X}, PID: 0x{target['product_id']:04X}\n")
        log_file.write(f"# Interface: MI_{target['interface_number']:02d}, Path: {target['masked_path']}\n\n")

        try:
            while time.time() - start_time < seconds:
                # タイムアウト付きブロッキング読み取り (500ms)
                # CPU使用率を抑えつつスムーズにCtrl+Cを検知
                raw_data = device.read(64, timeout_ms=500)

                current_time_str = datetime.datetime.now().strftime("%H:%M:%S")

                if not raw_data:
                    # データが届いていない場合、10秒ごとにハートビートを表示
                    if time.time() - last_heartbeat_time >= 10.0:
                        elapsed = int(time.time() - start_time)
                        print(f"[{current_time_str}] [待機中] 経過時間: {elapsed}/{seconds}s (受信パケット数: {stats['total_packets']})")
                        last_heartbeat_time = time.time()
                    continue

                stats["total_packets"] += 1
                parsed: ParsedPacket = parse_packet(raw_data)
                raw_hex = format_hex(raw_data)
                payload_hex = format_hex(parsed.payload)

                # ログファイルへの記録 (全件)
                log_entry = (
                    f"[{current_time_str}] TYPE={parsed.packet_type.value} "
                    f"VALID={parsed.is_valid_battery} "
                    f"BATTERY={parsed.battery_level}% "
                    f"STATUS=0x{parsed.status_code:02X} "
                    f"RAW=[{raw_hex}] PAYLOAD=[{payload_hex}]\n"
                    if parsed.status_code is not None else
                    f"[{current_time_str}] TYPE={parsed.packet_type.value} "
                    f"VALID={parsed.is_valid_battery} "
                    f"RAW=[{raw_hex}] PAYLOAD=[{payload_hex}]\n"
                )
                log_file.write(log_entry)
                log_file.flush()

                # 統計集計
                if parsed.packet_type == PacketType.FORMAT_A:
                    stats["format_a_count"] += 1
                    stats["last_battery"] = parsed.battery_level
                    stats["last_status_code"] = parsed.status_code
                    stats["last_valid_time"] = current_time_str

                    if len(stats["raw_samples"]) < 10:
                        stats["raw_samples"].append({
                            "timestamp": current_time_str,
                            "raw_hex": raw_hex,
                            "payload_hex": payload_hex,
                            "battery": parsed.battery_level,
                            "status_code": parsed.status_code,
                            "report_id": parsed.report_id,
                        })

                    # コンソール出力: バッテリー残量または状態が変化した際に出力
                    should_print = (
                        debug or
                        (parsed.battery_level != last_reported_battery) or
                        (parsed.status_code != last_reported_status) or
                        (time.time() - last_heartbeat_time >= 10.0)
                    )

                    if should_print:
                        status_desc = parsed.get_status_description()
                        print(f"[{current_time_str}] Battery: {parsed.battery_level}% ({status_desc})")
                        print(f"             RAW: {raw_hex}")
                        last_reported_battery = parsed.battery_level
                        last_reported_status = parsed.status_code
                        last_heartbeat_time = time.time()

                elif parsed.packet_type == PacketType.FORMAT_B:
                    stats["format_b_count"] += 1
                    if debug:
                        print(f"[{current_time_str}] [FORMAT_B (未解析)] RAW: {raw_hex}")
                elif parsed.packet_type == PacketType.INVALID:
                    stats["invalid_count"] += 1
                    if debug:
                        print(f"[{current_time_str}] [INVALID: {parsed.error_message}] RAW: {raw_hex}")
                else:
                    stats["unknown_count"] += 1
                    if debug:
                        print(f"[{current_time_str}] [UNKNOWN HEADER] RAW: {raw_hex}")

        except KeyboardInterrupt:
            print("\n[!] ユーザー操作により監視を中断しました (Ctrl+C)")
        except Exception as e:
            print(f"\n[ERROR] 受信中にエラーが発生しました: {e}")
            stats["error"] = str(e)
        finally:
            device.close()
            print("\nHID device closed successfully.")

    # 終了サマリー表示
    print("\n" + "=" * 50)
    print("LAMZU Thorn V2 検証サマリー")
    print("=" * 50)
    print(f"受信パケット総数    : {stats['total_packets']}")
    print(f"形式A (残量有効)    : {stats['format_a_count']}")
    print(f"形式B (補助パケット): {stats['format_b_count']}")
    print(f"その他 / 不明       : {stats['unknown_count'] + stats['invalid_count']}")
    if stats["last_battery"] is not None:
        print(f"最終取得バッテリー  : {stats['last_battery']}%")
        print(f"最終状態コード      : 0x{stats['last_status_code']:02X}")
        print(f"最終受信時刻        : {stats['last_valid_time']}")
    else:
        print("バッテリー残量は取得できませんでした。")
    print(f"詳細ログファイル    : {log_file_path}")
    print("=" * 50)

    return stats


def main():
    """コマンドライン引数の解析と実行振り分け"""
    parser = argparse.ArgumentParser(
        description="LAMZU Thorn V2 Battery Monitor - HID通信検証ツール"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="接続されているLAMZU HIDデバイス候補を列挙して診断表示する"
    )
    parser.add_argument(
        "--read",
        action="store_true",
        help="対象HIDデバイスからInput Reportを受信してバッテリー残量を表示する"
    )
    parser.add_argument(
        "--seconds",
        type=int,
        default=60,
        help="監視実行秒数 (デフォルト: 60秒)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="未解析・無効パケットを含むすべての受信生データを表示する"
    )
    parser.add_argument(
        "--index",
        type=int,
        default=None,
        help="列挙候補から特定のインデックス番号のデバイスを強制指定して開く"
    )

    args = parser.parse_args()

    if args.list:
        candidates = enumerate_candidates(TARGET_VID, TARGET_PID)
        print_device_list(candidates)
    elif args.read:
        run_probe_read(seconds=args.seconds, debug=args.debug, target_index=args.index)
    else:
        # 引数なしの場合はヘルプと--listの案内を表示
        parser.print_help()
        print("\n[使用例]")
        print("  python probe_hid.py --list")
        print("  python probe_hid.py --read --seconds 60")
        print("  python probe_hid.py --read --seconds 60 --debug")


if __name__ == "__main__":
    main()
