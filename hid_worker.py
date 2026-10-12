"""LAMZU Thorn V2 HID受信ワーカースレッドモジュール

UIスレッドをブロックしないよう、別スレッドでHIDデバイスの監視・受信を行い、
切断時の再接続バックオフおよびスリープ（受信途絶）の監視を行う。
"""

import logging
import threading
import time
from typing import Optional

import hid
from battery_protocol import parse_packet, PacketType, ChargingState
from battery_state import BatteryState

# ログ設定
logger = logging.getLogger("hid_worker")

# LAMZU 8K Dongle V2 のハードウェア識別子
TARGET_VID = 0x37B0
TARGET_PID = 0x002E
TARGET_USAGE_PAGE = 0xFFA0
TARGET_USAGE = 0x0001


def find_target_device_path() -> Optional[bytes]:
    """Usage Page 0xFFA0 / Usage 0x0001 の対象インターフェースパスを検索"""
    try:
        devices = hid.enumerate(TARGET_VID, TARGET_PID)
        for d in devices:
            if d.get("usage_page") == TARGET_USAGE_PAGE and d.get("usage") == TARGET_USAGE:
                return d.get("path")
    except Exception as e:
        logger.warning(f"HIDデバイス列挙エラー: {e}")
    return None


class HidWorker:
    """バックグラウンドでHID通信を監視・受信するワーカークラス"""

    def __init__(self, state: BatteryState):
        self.state = state
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._device: Optional[hid.device] = None
        self._device_lock = threading.Lock()

        # 再接続バックオフ設定（秒）
        self._initial_backoff: float = 2.0
        self._max_backoff: float = 30.0
        self._current_backoff: float = self._initial_backoff

        # 通信統計カウンタ
        self.packets_received: int = 0
        self.format_a_count: int = 0
        self.format_b_count: int = 0

    def start(self) -> None:
        """ワーカースレッドを開始"""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="HidWorkerThread", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """ワーカースレッドの停止要求および終了待機"""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._close_device()

    def is_alive(self) -> bool:
        """スレッドが稼働中か確認"""
        return self._thread is not None and self._thread.is_alive()

    def _close_device(self) -> None:
        """HIDデバイスハンドルを安全に閉じる"""
        with self._device_lock:
            if self._device is not None:
                try:
                    self._device.close()
                except Exception:
                    pass
                self._device = None

    def _run_loop(self) -> None:
        """ワーカースレッドのメインループ"""
        while not self._stop_event.is_set():
            # 1. デバイスが未オープンの場合: 検索と接続試行
            with self._device_lock:
                dev = self._device

            if dev is None:
                path = find_target_device_path()
                if path:
                    try:
                        new_dev = hid.device()
                        new_dev.open_path(path)
                        with self._device_lock:
                            self._device = new_dev
                        self._current_backoff = self._initial_backoff
                        self.state.set_dongle_available(True)
                        logger.info("対象HIDデバイスのオープンに成功しました")
                    except Exception as e:
                        logger.warning(f"デバイスオープン失敗: {e}")
                        self._close_device()
                        self.state.set_dongle_available(False)
                else:
                    self.state.set_dongle_available(False)

                with self._device_lock:
                    is_opened = self._device is not None

                # デバイスが見つからない、またはオープン失敗した場合はバックオフ待機
                if not is_opened:
                    self._stop_event.wait(self._current_backoff)
                    self._current_backoff = min(self._max_backoff, self._current_backoff * 1.5)
                    continue

            # 2. デバイス接続中: タイムアウト付きブロッキング読み取り (500ms)
            try:
                with self._device_lock:
                    active_dev = self._device
                if active_dev is None:
                    continue

                raw_data = active_dev.read(64, timeout_ms=500)

                if raw_data:
                    self.packets_received += 1
                    parsed = parse_packet(raw_data)

                    if parsed.packet_type == PacketType.FORMAT_A and parsed.is_valid_battery:
                        self.format_a_count += 1
                        if self.state.battery_percent != parsed.battery_level or self.state.charging_state != parsed.charging_state:
                            logger.info(f"バッテリー残量を受信・更新しました: {parsed.battery_level}% (状態コード: 0x{parsed.status_code:02X}, 充電: {parsed.charging_state.value})")
                        else:
                            logger.debug(f"バッテリー受信: {parsed.battery_level}% (状態コード: 0x{parsed.status_code:02X}, 充電: {parsed.charging_state.value})")
                        self.state.update_battery(
                            parsed.battery_level,
                            parsed.status_code,
                            parsed.state_value,
                            parsed.charging_state
                        )
                    elif parsed.packet_type == PacketType.FORMAT_B:
                        self.format_b_count += 1
                        # 形式Bは残量を上書きせず、充電状態とタイムスタンプのみ更新 (0%誤認防止)
                        self.state.update_non_battery_packet(charging_state=parsed.charging_state)
                    else:
                        # 未解析・その他パケット
                        pass
                else:
                    # 読み取りタイムアウト (データなし) -> スリープ判定のチェック
                    self.state.check_staleness()

            except Exception as e:
                # 読み取りエラー（ドングルの抜去等）が発生した場合
                logger.warning(f"HID読み取りエラー（ドングル切断の可能性）: {e}")
                self._close_device()
                self.state.set_dongle_available(False)
                self._current_backoff = self._initial_backoff
                self._stop_event.wait(self._current_backoff)

        # ループ終了後のクリーンアップ
        logger.info(f"HIDワーカー通信統計: 受信総数={self.packets_received}, 形式A={self.format_a_count}, 形式B={self.format_b_count}")
        self._close_device()
