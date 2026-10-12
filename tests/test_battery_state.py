"""LAMZU Thorn V2 バッテリー状態管理の単体テスト

BatteryStateクラスの状態遷移、スリープ推測、ドングル切断・復帰、
テキスト生成およびリスナー通知の動作を検証します。
"""

import time
import unittest
from battery_state import BatteryState, ReceiveState, ChargingState


class TestBatteryState(unittest.TestCase):
    """バッテリー状態管理の動作検証テストケース"""

    def test_initial_state(self):
        """初期化直後の状態検証"""
        state = BatteryState()
        self.assertIsNone(state.battery_percent)
        self.assertFalse(state.dongle_available)
        self.assertEqual(state.receive_state, ReceiveState.INITIALIZING)
        self.assertIn("Dongle unavailable", state.get_tooltip_text())
        self.assertEqual(state.get_menu_battery_text(), "バッテリー: 未取得")
        self.assertEqual(state.get_menu_status_text(), "受信状態: 初期化中")

    def test_update_valid_battery(self):
        """有効なバッテリー残量の更新とテキスト生成"""
        state = BatteryState()
        notified = []
        state.add_listener(lambda s: notified.append(s.battery_percent))

        state.update_battery(100, status_code=0x00, state_value=0x58)

        self.assertEqual(state.battery_percent, 100)
        self.assertEqual(state.raw_status_code, 0x00)
        self.assertEqual(state.state_value, 0x58)
        self.assertTrue(state.dongle_available)
        self.assertEqual(state.receive_state, ReceiveState.NORMAL)
        self.assertEqual(state.get_tooltip_text(), "LAMZU Thorn V2 - Battery: 100%")
        self.assertEqual(state.get_menu_battery_text(), "バッテリー: 100%")
        self.assertEqual(state.get_menu_status_text(), "受信状態: 正常")
        self.assertIn(100, notified)

    def test_format_b_does_not_overwrite_battery(self):
        """形式Bパケットを受信しても残量が上書き（0%化）されないことの検証"""
        state = BatteryState()
        state.update_battery(99, status_code=0x00)
        self.assertEqual(state.battery_percent, 99)

        # 形式Bパケット受信 (残量なしタイムスタンプ更新のみ)
        state.update_non_battery_packet()
        self.assertEqual(state.battery_percent, 99)
        self.assertNotEqual(state.battery_percent, 0)

    def test_invalid_battery_ignored(self):
        """範囲外のバッテリー残量 (105%など) は無視されることの検証"""
        state = BatteryState()
        state.update_battery(80)
        state.update_battery(105)  # 不正値
        self.assertEqual(state.battery_percent, 80)

    def test_staleness_sleep_suspected(self):
        """15秒以上パケット受信がない場合、残量を保持したままスリープ推測へ遷移"""
        state = BatteryState()
        state.update_battery(85)
        self.assertEqual(state.receive_state, ReceiveState.NORMAL)

        # 最終受信時刻を16秒前に設定
        state.last_valid_battery_at = time.time() - 16.0
        changed = state.check_staleness()

        self.assertTrue(changed)
        self.assertEqual(state.receive_state, ReceiveState.SLEEP_SUSPECTED)
        # 残量は消失せず85%を維持していること
        self.assertEqual(state.battery_percent, 85)
        # ツールチップが Last known 表示になること
        self.assertEqual(state.get_tooltip_text(), "LAMZU Thorn V2 - Last known: 85%")
        self.assertEqual(state.get_menu_status_text(), "受信状態: スリープ推測 (データ途絶)")

    def test_recovery_from_sleep(self):
        """スリープ推測状態からパケット受信で正常復帰することの検証"""
        state = BatteryState()
        state.update_battery(85)
        state.last_valid_battery_at = time.time() - 16.0
        state.check_staleness()
        self.assertEqual(state.receive_state, ReceiveState.SLEEP_SUSPECTED)

        # マウス復帰パケットを受信
        state.update_battery(85)
        self.assertEqual(state.receive_state, ReceiveState.NORMAL)
        self.assertEqual(state.get_tooltip_text(), "LAMZU Thorn V2 - Battery: 85%")
        self.assertEqual(state.get_menu_status_text(), "受信状態: 正常")

    def test_dongle_disconnect_and_reconnect(self):
        """ドングルの切断と再接続、残量値の非表示および形式A受信による復帰検証"""
        state = BatteryState()
        state.update_battery(90)
        self.assertEqual(state.battery_percent, 90)
        self.assertEqual(state.percent, 90)

        # 1. 切断
        state.set_dongle_available(False)
        self.assertFalse(state.dongle_available)
        self.assertEqual(state.receive_state, ReceiveState.DONGLE_DISCONNECTED)
        self.assertEqual(state.get_tooltip_text(), "LAMZU Thorn V2 - Dongle unavailable")
        self.assertEqual(state.get_menu_status_text(), "受信状態: ドングル未検出")
        # 切断中は有効残量 percent は None
        self.assertIsNone(state.percent)
        # 内部の過去残量は保持されること
        self.assertEqual(state.battery_percent, 90)

        # 2. 再接続 (新規パケット受信までは WAITING_DATA を維持)
        state.set_dongle_available(True)
        self.assertTrue(state.dongle_available)
        self.assertEqual(state.receive_state, ReceiveState.WAITING_DATA)
        # WAITING_DATA中は有効残量 percent は None (未取得扱い)
        self.assertIsNone(state.percent)
        self.assertEqual(state.battery_percent, 90)
        self.assertEqual(state.get_tooltip_text(), "LAMZU Thorn V2 - Waiting for data")
        self.assertEqual(state.get_menu_battery_text(), "バッテリー: 未取得")
        self.assertEqual(state.get_menu_time_text(), "最終更新: なし")
        self.assertFalse(state.is_charging)

        # 3. 形式Bのみを受信した場合: WAITING_DATAを維持しNORMALへ戻らないこと
        state.update_non_battery_packet(charging_state=ChargingState.CHARGING)
        self.assertEqual(state.receive_state, ReceiveState.WAITING_DATA)
        self.assertIsNone(state.percent)
        self.assertFalse(state.is_charging)
        self.assertEqual(state.get_menu_battery_text(), "バッテリー: 未取得")

        # 4. 新規形式Aパケットを受信して初めて NORMAL へ復帰すること
        state.update_battery(92, charging_state=ChargingState.NOT_CHARGING)
        self.assertEqual(state.receive_state, ReceiveState.NORMAL)
        self.assertEqual(state.percent, 92)
        self.assertEqual(state.battery_percent, 92)
        self.assertEqual(state.get_menu_battery_text(), "バッテリー: 92%")
        self.assertFalse(state.is_charging)

    def test_demo_mode_tooltip_prefix(self):
        """デモモード時にツールチップに [DEMO] が付加されることの検証"""
        state = BatteryState(is_demo_mode=True)
        state.update_battery(70)
        self.assertTrue(state.get_tooltip_text().startswith("[DEMO] "))


if __name__ == "__main__":
    unittest.main()
