"""LAMZU Thorn V2 ワーカースレッドの単体テスト

HidWorkerおよびDemoWorkerのスレッド開始・停止ライフサイクル、
例外処理、デモモード状態遷移を検証します。
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from battery_state import BatteryState, ReceiveState
from demo_worker import DemoWorker
from hid_worker import HidWorker


class TestWorkers(unittest.TestCase):
    """ワーカースレッドの動作検証テストケース"""

    def test_demo_worker_lifecycle_and_transition(self):
        """DemoWorkerが指定インターバルで状態を更新し安全に停止することの検証"""
        state = BatteryState(is_demo_mode=True)
        # 高速ステップ間隔 (0.05秒) でテスト実行
        worker = DemoWorker(state, step_interval=0.05)

        self.assertFalse(worker.is_alive())
        worker.start()
        self.assertTrue(worker.is_alive())

        # 0.2秒待機してシナリオが進むことを確認
        time.sleep(0.2)
        self.assertIsNotNone(state.battery_percent)

        # 停止要求が迅速に完了すること
        t0 = time.time()
        worker.stop(timeout=1.0)
        t_stop = time.time() - t0

        self.assertFalse(worker.is_alive())
        self.assertLess(t_stop, 1.0)

    def test_hid_worker_stop_without_device(self):
        """対象デバイスが存在しない場合でもHidWorkerが安全に開始・停止できることの検証"""
        state = BatteryState()
        worker = HidWorker(state)

        # デバイスが見つからない環境をモック
        with patch("hid_worker.find_target_device_path", return_value=None):
            worker.start()
            self.assertTrue(worker.is_alive())

            # 停止要求
            t0 = time.time()
            worker.stop(timeout=1.0)
            t_stop = time.time() - t0

            self.assertFalse(worker.is_alive())
            self.assertLess(t_stop, 1.0)
            self.assertFalse(state.dongle_available)

    def test_hid_worker_read_exception_handling(self):
        """HID読み取り時に例外が発生した場合の切断検知と安全処理"""
        state = BatteryState()
        worker = HidWorker(state)

        mock_dev = MagicMock()
        # 1回目のreadで例外 (切断) を発生
        mock_dev.read.side_effect = Exception("Device disconnected")

        with patch("hid_worker.find_target_device_path", return_value=b"fake_path"), \
             patch("hid.device", return_value=mock_dev):
            worker.start()
            # 処理が走るのを待機
            time.sleep(0.1)

            # ドングル利用不可に遷移していること
            self.assertFalse(state.dongle_available)

            worker.stop(timeout=1.0)
            self.assertFalse(worker.is_alive())


if __name__ == "__main__":
    unittest.main()
