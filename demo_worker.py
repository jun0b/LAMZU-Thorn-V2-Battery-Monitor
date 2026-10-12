"""LAMZU Thorn V2 デモモード用ワーカースレッドモジュール

実機HIDデバイスを開かずに、バッテリー残量の変化、スリープ（受信途絶）、
ドングルの切断・再接続の各シナリオをシミュレーションする。
"""

import logging
import threading
import time
from typing import Optional

from battery_state import BatteryState

logger = logging.getLogger("demo_worker")


class DemoWorker:
    """実機なしでUIの動作を検証するためのシミュレーションワーカー"""

    def __init__(self, state: BatteryState, step_interval: float = 3.0):
        self.state = state
        self.step_interval = step_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """デモワーカースレッドを開始"""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="DemoWorkerThread", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """デモワーカースレッドの停止要求および終了待機"""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        """スレッド稼働中か確認"""
        return self._thread is not None and self._thread.is_alive()

    def _wait_interval(self, seconds: float) -> bool:
        """指定秒数待機 (stop_eventがセットされたら直ちにFalseを返す)"""
        return not self._stop_event.wait(seconds)

    def _run_loop(self) -> None:
        """シミュレーションシナリオをループ実行"""
        logger.info("デモモードのシミュレーションを開始します")

        while not self._stop_event.is_set():
            # シナリオ1: ドングル初期化・待機中
            self.state.set_dongle_available(True)
            if not self._wait_interval(self.step_interval):
                break

            # シナリオ2: 100% 受信 (通常色・緑)
            self.state.update_battery(100, status_code=0x00, state_value=0x58)
            if not self._wait_interval(self.step_interval):
                break

            # シナリオ3: 75% 受信 (通常色・緑)
            self.state.update_battery(75, status_code=0x00, state_value=0x59)
            if not self._wait_interval(self.step_interval):
                break

            # シナリオ4: 50% 受信 (注意色・橙)
            self.state.update_battery(50, status_code=0x00, state_value=0x5A)
            if not self._wait_interval(self.step_interval):
                break

            # シナリオ5: 20% 受信 (注意色・橙)
            self.state.update_battery(20, status_code=0x00, state_value=0x5B)
            if not self._wait_interval(self.step_interval):
                break

            # シナリオ6: 10% 受信 (警告色・赤)
            self.state.update_battery(10, status_code=0x00, state_value=0x5C)
            if not self._wait_interval(self.step_interval):
                break

            # シナリオ7: 受信データの一時停止 (スリープ推測のシミュレーション)
            # 閾値 (15秒) 経過をシミュレート
            # 内部のlast_valid_battery_atを16秒前に設定してcheck_staleness()を発火
            self.state.last_valid_battery_at = time.time() - 16.0
            self.state.check_staleness()
            if not self._wait_interval(self.step_interval):
                break

            # シナリオ8: データ受信再開 (スリープ復帰、80%で復帰)
            self.state.update_battery(80, status_code=0x00, state_value=0x5D)
            if not self._wait_interval(self.step_interval):
                break

            # シナリオ9: ドングル切断 (利用不可)
            self.state.set_dongle_available(False)
            if not self._wait_interval(self.step_interval):
                break

            # シナリオ10: ドングル再接続復帰
            self.state.set_dongle_available(True)
            self.state.update_battery(80, status_code=0x00, state_value=0x5E)
            if not self._wait_interval(self.step_interval):
                break
