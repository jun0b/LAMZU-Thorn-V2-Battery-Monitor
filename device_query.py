# -*- coding: utf-8 -*-
"""LAMZU Thorn V2 デバイス設定（DPI・ポーリングレート）読み取り専用モジュール

LAMZU Auroraの公式Webドライバー仕様に基づく、読み取り専用のHID Feature Report通信。
許可リストに登録された取得コマンド (0x80, 0x81, 0x82) のみを安全に送信し、
現在のDPIおよびポーリングレートをオンデマンドで取得する。
設定変更コマンドや未知のHID書き込み操作は一切行わない。
"""

import threading
import time
from typing import Optional, Tuple, Dict, Any, Callable
import hid

# 対象デバイス識別情報
TARGET_VID = 0x37B0
TARGET_PID = 0x002E
TARGET_USAGE_PAGE = 0xFFFF
TARGET_USAGE = 0x0000

# 許可された読み取り専用コマンド一覧（厳格なホワイトリスト）
ALLOWED_READ_COMMANDS = {
    0x80: "GET_POLLING_RATE", # ポーリングレート取得
    0x81: "GET_DPI_STAGES",   # DPIステージ情報取得
    0x82: "GET_ACTIVE_DPI",   # アクティブDPI取得
}

# ポーリングレートコード変換マップ (LAMZU Aurora 公式Webドライバー準拠)
POLLING_RATE_MAP = {
    8: 125,
    4: 250,
    2: 500,
    1: 1000,
    32: 2000,
    64: 4000,
    128: 8000,
}

# 出荷時デフォルトDPIプリセット一覧 (参考用定数)
DEFAULT_DPI_STAGES = [400, 800, 1600, 3200, 6400]


def find_feature_device_path() -> Optional[bytes]:
    """Feature Report通信用のHIDエンドポイント (MI_02) のパスを探索する"""
    try:
        devices = hid.enumerate(TARGET_VID, TARGET_PID)
        for d in devices:
            up = d.get('usage_page', 0)
            u = d.get('usage', 0)
            path = d.get('path', b'')
            # UsagePage 0xFFFF, Usage 0x0000 がFeature Report管理インターフェース
            if up == TARGET_USAGE_PAGE and u == TARGET_USAGE:
                return path
            # パス文字列にmi_02が含まれる場合も対象
            if b'mi_02' in path.lower() and up == TARGET_USAGE_PAGE:
                return path
    except Exception:
        pass
    return None


class DeviceQuerySession:
    """オンデマンド問い合わせセッションの管理クラス"""

    def __init__(self):
        self._is_cancelled = False
        self._lock = threading.Lock()

    def cancel(self):
        """問い合わせをキャンセルする"""
        with self._lock:
            self._is_cancelled = True

    @property
    def is_cancelled(self) -> bool:
        with self._lock:
            return self._is_cancelled


def _send_and_receive(dev, cmd_buf: bytearray, expected_cmd: int, max_retries: int = 4) -> Optional[list]:
    """Feature Reportを送信し、一致するレスポンスを待機して取得する

    ホワイトリスト検証、バッファコマンド一致検証、およびレスポンス形式検証を実施する。
    """
    if expected_cmd not in ALLOWED_READ_COMMANDS:
        raise ValueError(f"許可されていないHIDコマンドです: 0x{expected_cmd:02X}")

    if len(cmd_buf) < 7 or cmd_buf[6] != expected_cmd:
        raise ValueError(
            f"送信バッファのコマンド位置 (0x{cmd_buf[6] if len(cmd_buf) > 6 else 0:02X}) が期待値 (0x{expected_cmd:02X}) と一致しません"
        )

    for _ in range(max_retries):
        try:
            dev.send_feature_report(list(cmd_buf))
            time.sleep(0.06)
            res = dev.get_feature_report(0, 65)
            if len(res) >= 9 and res[1] == 161 and res[6] == expected_cmd:
                return list(res)
        except Exception:
            pass
        time.sleep(0.04)
    return None


def query_device_settings(session: Optional[DeviceQuerySession] = None) -> Dict[str, Any]:
    """デバイスからDPIおよびポーリングレートを読み取る（ブロッキング実行）

    Returns:
        Dict[str, Any]: {
            'success': bool,
            'dpi': Optional[int],
            'polling_rate': Optional[int],
            'active_stage': Optional[int],
            'stages': list,
            'error': Optional[str]
        }
    """
    result: Dict[str, Any] = {
        'success': False,
        'dpi': None,
        'polling_rate': None,
        'active_stage': None,
        'stages': [],
        'error': None
    }

    path = find_feature_device_path()
    if not path:
        result['error'] = "デバイスが見つかりません"
        return result

    dev = hid.device()
    try:
        dev.open_path(path)

        if session and session.is_cancelled:
            result['error'] = "キャンセルされました"
            return result

        # 1. アクティブDPIステージ取得 (0x82)
        if 0x82 not in ALLOWED_READ_COMMANDS:
            raise ValueError("コマンド 0x82 は許可されていません")

        cmd_active = bytearray(65)
        cmd_active[0] = 0x00  # Report ID
        cmd_active[3] = 2     # Device ID: Mouse
        cmd_active[4] = 2     # Length
        cmd_active[5] = 1     # Sub ID: 1
        cmd_active[6] = 130   # Cmd 0x82
        cmd_active[7] = 1     # Profile 1

        res_active = _send_and_receive(dev, cmd_active, 130)
        active_stage = None
        if res_active is not None and len(res_active) >= 9:
            raw_stage = res_active[8]
            if 1 <= raw_stage <= 8:
                active_stage = raw_stage
                result['active_stage'] = active_stage

        if session and session.is_cancelled:
            result['error'] = "キャンセルされました"
            return result

        # 2. DPIステージ情報取得 (0x81)
        if 0x81 not in ALLOWED_READ_COMMANDS:
            raise ValueError("コマンド 0x81 は許可されていません")

        cmd_stages = bytearray(65)
        cmd_stages[0] = 0x00  # Report ID
        cmd_stages[3] = 2     # Device ID: Mouse
        cmd_stages[4] = 10    # Length
        cmd_stages[5] = 1     # Sub ID: 1
        cmd_stages[6] = 129   # Cmd 0x81
        cmd_stages[7] = 1     # Profile 1
        cmd_stages[8] = 6     # Max stages: 6 (Aurora準拠)

        res_stages = _send_and_receive(dev, cmd_stages, 129)
        parsed_stages = []
        parsed_dpi = None
        if res_stages is not None and len(res_stages) >= 9:
            stage_count = res_stages[8]
            if 1 <= stage_count <= 8:
                for p in range(stage_count):
                    idx = 9 + p * 4
                    if idx + 1 < len(res_stages):
                        x_val = (res_stages[idx] << 8) | res_stages[idx + 1]
                        if 50 <= x_val <= 50000:
                            parsed_stages.append(x_val)

                if parsed_stages:
                    result['stages'] = parsed_stages
                    if active_stage is not None and 1 <= active_stage <= len(parsed_stages):
                        parsed_dpi = parsed_stages[active_stage - 1]

        result['dpi'] = parsed_dpi

        if session and session.is_cancelled:
            result['error'] = "キャンセルされました"
            return result

        # 3. ポーリングレート取得 (0x80)
        if 0x80 not in ALLOWED_READ_COMMANDS:
            raise ValueError("コマンド 0x80 は許可されていません")

        cmd_rate = bytearray(65)
        cmd_rate[0] = 0x00  # Report ID
        cmd_rate[3] = 2     # Device ID: Mouse
        cmd_rate[4] = 2     # Length: 2
        cmd_rate[5] = 1     # Sub ID: 1
        cmd_rate[6] = 128   # Cmd 0x80
        cmd_rate[7] = 1     # Profile 1

        res_rate = _send_and_receive(dev, cmd_rate, 128)
        rate_hz = None
        if res_rate is not None and len(res_rate) >= 9:
            code = res_rate[8]
            rate_hz = POLLING_RATE_MAP.get(code, None)

        result['polling_rate'] = rate_hz

        # 取得成否の判定: DPIまたはポーリングレートの少なくとも一方が取得できたこと
        if parsed_dpi is not None or rate_hz is not None:
            result['success'] = True
        else:
            result['error'] = "デバイス設定値の解釈に失敗しました"

    except Exception as e:
        result['error'] = str(e)
    finally:
        try:
            dev.close()
        except Exception:
            pass

    return result


def query_device_settings_async(callback: Callable[[Dict[str, Any]], None]) -> DeviceQuerySession:
    """バックグラウンドスレッドで設定を取得し、完了時にコールバックを呼び出す

    Args:
        callback: 取得結果 (Dict[str, Any]) を受け取る関数

    Returns:
        DeviceQuerySession: キャンセル可能なセッションオブジェクト
    """
    session = DeviceQuerySession()

    def _worker():
        res = query_device_settings(session)
        if not session.is_cancelled:
            try:
                callback(res)
            except Exception:
                pass

    t = threading.Thread(target=_worker, name="DeviceQueryThread", daemon=True)
    t.start()
    return session
