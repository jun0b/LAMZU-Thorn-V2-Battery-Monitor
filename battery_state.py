"""LAMZU Thorn V2 バッテリー状態管理モジュール

システムトレイUIとHID受信ワーカー間で共有される状態を
スレッドセーフに一元管理する。
スリープ状態（パケット途絶）の判定、残量値の保持、
表示用テキスト生成を担当する。
"""

import threading
import time
from datetime import datetime
from enum import Enum
from typing import Optional, Callable, List
from battery_protocol import ChargingState


class ReceiveState(Enum):
    """通信・受信状態の種別"""
    INITIALIZING = "INITIALIZING"              # 初期化中 / 起動直後
    WAITING_DATA = "WAITING_DATA"              # ドングル認識済み・初回データ受信待ち
    NORMAL = "NORMAL"                          # 正常受信中
    SLEEP_SUSPECTED = "SLEEP_SUSPECTED"        # 受信途絶 (15秒以上) / スリープ推測
    DONGLE_DISCONNECTED = "DONGLE_DISCONNECTED"# ドングル切断 / 利用不能


class BatteryState:
    """バッテリー残量およびデバイス通信状態をスレッドセーフに管理するクラス"""

    # 受信途絶とみなす閾値（秒）
    STALE_THRESHOLD_SECONDS: float = 15.0

    def __init__(self, is_demo_mode: bool = False):
        self._lock = threading.Lock()
        self.is_demo_mode = is_demo_mode

        # 内部状態フィールド
        self.battery_percent: Optional[int] = None
        self.last_received_at: Optional[float] = None
        self.last_valid_battery_at: Optional[float] = None
        self.raw_status_code: Optional[int] = None
        self.state_value: Optional[int] = None
        self.charging_state: ChargingState = ChargingState.UNKNOWN
        self.dongle_available: bool = False
        self.receive_state: ReceiveState = ReceiveState.INITIALIZING

        # 状態変更リスナー
        self._listeners: List[Callable[["BatteryState"], None]] = []

    @property
    def percent(self) -> Optional[int]:
        """最新の有効なバッテリー残量 (未取得または待機中・切断時はNone)"""
        with self._lock:
            if not self.dongle_available or self.receive_state in (
                ReceiveState.INITIALIZING,
                ReceiveState.WAITING_DATA,
                ReceiveState.DONGLE_DISCONNECTED,
            ):
                return None
            return self.battery_percent

    @property
    def display_percent(self) -> Optional[int]:
        """UI表示用の有効なバッテリー残量 (percent と同等)"""
        return self.percent

    @property
    def is_stale(self) -> bool:
        """スリープ推測 (受信途絶) 状態かどうか"""
        with self._lock:
            return self.receive_state == ReceiveState.SLEEP_SUSPECTED

    @property
    def is_disconnected(self) -> bool:
        """ドングル切断状態かどうか"""
        with self._lock:
            return not self.dongle_available or self.receive_state == ReceiveState.DONGLE_DISCONNECTED

    @property
    def is_charging(self) -> bool:
        """充電中かどうか (正常受信中かつCHARGINGの場合のみTrue)"""
        with self._lock:
            if not self.dongle_available or self.receive_state != ReceiveState.NORMAL:
                return False
            return self.charging_state == ChargingState.CHARGING

    @property
    def is_charging_complete(self) -> bool:
        """充電完了かどうか (正常受信中かつCHARGING_COMPLETEの場合のみTrue)"""
        with self._lock:
            if not self.dongle_available or self.receive_state != ReceiveState.NORMAL:
                return False
            return self.charging_state == ChargingState.CHARGING_COMPLETE

    def add_listener(self, listener: Callable[["BatteryState"], None]) -> None:
        """状態変更時に呼び出されるコールバックリスナーを登録"""
        with self._lock:
            self._listeners.append(listener)

    def _notify_listeners(self) -> None:
        """登録されたリスナーに変更を通知 (ロック外で実行)"""
        listeners_copy = []
        with self._lock:
            listeners_copy = list(self._listeners)
        for listener in listeners_copy:
            try:
                listener(self)
            except Exception:
                pass

    def update_battery(
        self,
        percent: int,
        status_code: Optional[int] = None,
        state_value: Optional[int] = None,
        charging_state: ChargingState = ChargingState.UNKNOWN
    ) -> None:
        """有効なパケットを受信した際の残量および充電状態更新

        Args:
            percent: バッテリー残量 (0〜100)
            status_code: 状態コード (0x00, 0x02, 0x04 など)
            state_value: 変動状態値 (Byte 3)
            charging_state: 充電状態 (CHARGING, CHARGING_COMPLETE, NOT_CHARGING, UNKNOWN)
        """
        now = time.time()
        changed = False
        with self._lock:
            if not (0 <= percent <= 100):
                return  # 範囲外の不正値は無視

            if (
                self.battery_percent != percent
                or self.charging_state != charging_state
                or self.receive_state != ReceiveState.NORMAL
            ):
                changed = True

            self.battery_percent = percent
            self.last_received_at = now
            self.last_valid_battery_at = now
            self.raw_status_code = status_code
            self.state_value = state_value
            self.charging_state = charging_state
            self.dongle_available = True
            self.receive_state = ReceiveState.NORMAL

        if changed:
            self._notify_listeners()

    def update_non_battery_packet(self, charging_state: ChargingState = ChargingState.UNKNOWN) -> None:
        """形式Bなど、残量を含まないパケットを受信した際のタイムスタンプおよび充電状態更新

        残量値は上書きせず、受信時刻を更新する。
        ドングル再接続直後のデータ待機中(WAITING_DATA)やスリープ推測(SLEEP_SUSPECTED)時は、
        新しい有効な形式Aパケットを受信するまでNORMAL状態への復帰や最新値としての通知判定を行わない。
        形式Bのみの受信ではNORMALへ復帰させず、既存の受信状態を維持する。
        """
        now = time.time()
        changed = False
        with self._lock:
            self.last_received_at = now
            self.dongle_available = True

            # セッション確立中(NORMAL状態)の場合のみ充電状態を更新
            if self.receive_state == ReceiveState.NORMAL:
                # 形式Bは2値(CHARGING / NOT_CHARGING)のみのため、既にCHARGING_COMPLETEの場合は
                # 形式BのCHARGINGで上書きしてチラつくのを防ぐ（NOT_CHARGINGへの遷移は反映する）
                if (
                    self.charging_state == ChargingState.CHARGING_COMPLETE
                    and charging_state == ChargingState.CHARGING
                ):
                    pass
                elif (
                    charging_state != ChargingState.UNKNOWN
                    and self.charging_state != charging_state
                ):
                    self.charging_state = charging_state
                    changed = True

        if changed:
            self._notify_listeners()

    def set_dongle_available(self, available: bool) -> None:
        """ドングルの接続・認識状態を設定"""
        changed = False
        with self._lock:
            if self.dongle_available != available:
                changed = True
                self.dongle_available = available
                if not available:
                    self.receive_state = ReceiveState.DONGLE_DISCONNECTED
                    self.charging_state = ChargingState.UNKNOWN
                else:
                    # ドングル再接続時は新規の有効パケットを受信するまで待機状態とする
                    self.receive_state = ReceiveState.WAITING_DATA
                    self.charging_state = ChargingState.UNKNOWN

        if changed:
            self._notify_listeners()

    def check_staleness(self) -> bool:
        """パケット受信の途絶（スリープ推測）を判定する

        15秒以上有効パケットがない場合、残量は保持したまま
        状態を SLEEP_SUSPECTED に遷移させる。

        Returns:
            bool: 状態が変化した場合はTrue
        """
        changed = False
        now = time.time()
        with self._lock:
            if self.dongle_available and self.receive_state == ReceiveState.NORMAL:
                if self.last_valid_battery_at is not None:
                    elapsed = now - self.last_valid_battery_at
                    if elapsed >= self.STALE_THRESHOLD_SECONDS:
                        self.receive_state = ReceiveState.SLEEP_SUSPECTED
                        changed = True

        if changed:
            self._notify_listeners()
        return changed

    def get_tooltip_text(self) -> str:
        """システムトレイのツールチップ用文字列を生成"""
        with self._lock:
            prefix = "[DEMO] " if self.is_demo_mode else ""
            if not self.dongle_available or self.receive_state == ReceiveState.DONGLE_DISCONNECTED:
                return f"{prefix}LAMZU Thorn V2 - Dongle unavailable"

            if self.battery_percent is None or self.receive_state == ReceiveState.WAITING_DATA:
                return f"{prefix}LAMZU Thorn V2 - Waiting for data"

            if self.receive_state == ReceiveState.SLEEP_SUSPECTED:
                return f"{prefix}LAMZU Thorn V2 - Last known: {self.battery_percent}%"

            return f"{prefix}LAMZU Thorn V2 - Battery: {self.battery_percent}%"

    def get_menu_battery_text(self) -> str:
        """右クリックメニュー表示用のバッテリー残量文字列"""
        with self._lock:
            if (
                self.dongle_available
                and self.receive_state in (ReceiveState.NORMAL, ReceiveState.SLEEP_SUSPECTED)
                and self.battery_percent is not None
            ):
                return f"バッテリー: {self.battery_percent}%"
            return "バッテリー: 未取得"

    def get_menu_status_text(self) -> str:
        """右クリックメニュー表示用の受信状態文字列"""
        with self._lock:
            match self.receive_state:
                case ReceiveState.NORMAL:
                    return "受信状態: 正常"
                case ReceiveState.SLEEP_SUSPECTED:
                    return "受信状態: スリープ推測 (データ途絶)"
                case ReceiveState.WAITING_DATA:
                    return "受信状態: データ待機中"
                case ReceiveState.DONGLE_DISCONNECTED:
                    return "受信状態: ドングル未検出"
                case ReceiveState.INITIALIZING:
                    return "受信状態: 初期化中"
                case _:
                    return "受信状態: 不明"

    def get_menu_time_text(self) -> str:
        """右クリックメニュー表示用の最終更新時刻文字列"""
        with self._lock:
            if (
                self.dongle_available
                and self.receive_state in (ReceiveState.NORMAL, ReceiveState.SLEEP_SUSPECTED)
                and self.last_valid_battery_at is not None
            ):
                dt = datetime.fromtimestamp(self.last_valid_battery_at)
                return f"最終更新: {dt.strftime('%H:%M:%S')}"
            return "最終更新: なし"

