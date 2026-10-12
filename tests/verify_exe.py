# -*- coding: utf-8 -*-
"""EXE単体検証スクリプト

1. EXEの起動と実起動時間計測 (起動開始ログおよび初期化完了ログの検知)
2. 起動したプロセスのPID追跡、メモリ使用量 (Working Set)、CPU使用率の計測
3. ログファイルの生成と内容確認 (%LOCALAPPDATA%\\LAMZUThornBatteryMonitor\\logs\\app.log)
4. 多重起動防止の検証 (2つ目のプロセスが即座にExitCode 0で終了するか)
5. --timeout 引数によるプロセスの自律的かつ正常な終了の検証 (ExitCode 0)
"""

import os
import subprocess
import time
from typing import Set
import psutil

EXE_CANDIDATES = [
    os.path.abspath(r"dist\LAMZU-Thorn-Battery-Monitor.exe"),
    os.path.abspath(r"dist\pyinstaller\LAMZU-Thorn-Battery-Monitor.exe"),
]
EXE_PATH = next((p for p in EXE_CANDIDATES if os.path.exists(p)), EXE_CANDIDATES[0])
LOG_PATH = os.path.expandvars(r"%LOCALAPPDATA%\LAMZUThornBatteryMonitor\logs\app.log")
TIMEOUT_SEC = 8


def run_verification() -> None:
    print(f"=== LAMZU Thorn V2 EXE 検証開始 ===")
    print(f"対象EXE: {EXE_PATH}")
    assert os.path.exists(EXE_PATH), f"EXEが存在しない: {EXE_PATH}"

    # 検証前のログファイル末尾位置を記録
    initial_log_size = 0
    if os.path.exists(LOG_PATH):
        initial_log_size = os.path.getsize(LOG_PATH)

    # 1. 起動と実起動時間計測
    start_time = time.perf_counter()
    proc1 = subprocess.Popen([EXE_PATH, "--timeout", str(TIMEOUT_SEC)])
    launch_pid = proc1.pid
    print(f"[1] プロセス起動: PID={launch_pid}")

    start_log_detected_time = None
    init_completed_time = None
    target_pids: Set[int] = {launch_pid}

    # ログに出現するキーワードをポーリング検知 (最大10秒)
    deadline = time.perf_counter() + 10.0
    while time.perf_counter() < deadline:
        # PyInstallerブートストラップによる子プロセスを追跡
        try:
            parent = psutil.Process(launch_pid)
            children = parent.children(recursive=True)
            for c in children:
                target_pids.add(c.pid)
        except Exception:
            pass

        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > initial_log_size:
            try:
                with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
                    f.seek(initial_log_size)
                    new_logs = f.read()

                    if start_log_detected_time is None and "Battery Monitor を起動しています" in new_logs:
                        start_log_detected_time = time.perf_counter() - start_time
                        print(f"    起動開始ログ検知: {start_log_detected_time:.2f} 秒")

                    if init_completed_time is None and "システムトレイおよびステータスパネルイベントループを開始します" in new_logs:
                        init_completed_time = time.perf_counter() - start_time
                        print(f"    初期化完了ログ検知: {init_completed_time:.2f} 秒")
                        break
            except Exception:
                pass
        time.sleep(0.1)

    assert init_completed_time is not None, "初期化完了ログが検出されなかった"
    print(f"[1] 実起動・初期化完了時間: {init_completed_time:.2f} 秒 (プロセス開始からイベントループ開始まで)")

    # 2. リソース計測 (追跡対象PIDのみ)
    total_rss_mb = 0.0
    tracked_procs = []
    for pid in target_pids:
        try:
            p = psutil.Process(pid)
            mem = p.memory_info().rss / (1024 * 1024)
            cpu = p.cpu_percent(interval=0.2)
            total_rss_mb += mem
            tracked_procs.append(p)
            print(f"    対象プロセス PID={pid} ({p.name()}): RSS={mem:.2f} MB, CPU={cpu:.1f}%")
        except Exception:
            pass
    print(f"[2] リソース使用量 (合計): メモリ(RSS)={total_rss_mb:.2f} MB")

    # 3. ログファイル確認
    print(f"[3] ログファイル確認: {LOG_PATH}")
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
            log_lines = f.readlines()
        print(f"    ログ総行数: {len(log_lines)} 行")
        print("    最新ログ抜粋:")
        for line in log_lines[-6:]:
            print(f"      {line.strip()}")
    else:
        print("    [警告] ログファイルが作成されていない")

    # 4. 多重起動防止の検証 (proc1 が動作中に2つ目を起動)
    print(f"[4] 多重起動防止 (2つ目のインスタンス起動) テスト...")
    proc2 = subprocess.Popen([EXE_PATH])
    try:
        exit_code2 = proc2.wait(timeout=5)
        print(f"    2つ目のインスタンスのExitCode: {exit_code2} (期待値: 0)")
        assert exit_code2 == 0, f"多重起動防止でExitCodeが0ではない: {exit_code2}"
    except subprocess.TimeoutExpired:
        proc2.kill()
        raise AssertionError("2つ目のインスタンスがタイムアウト内に終了しなかった")

    # 5. --timeout オプションによる自プロセスの自律的な正常終了の検証
    print(f"[5] --timeout によるプロセスの自律終了待機 (最大 {TIMEOUT_SEC + 5} 秒)...")
    try:
        exit_code1 = proc1.wait(timeout=TIMEOUT_SEC + 5)
        print(f"    プロセス終了コード: {exit_code1} (期待値: 0)")
        assert exit_code1 == 0, f"プロセスが正常終了しなかった (ExitCode: {exit_code1})"
        print("[5] プロセスの自律的正常終了を確認 (ExitCode 0)")
    except subprocess.TimeoutExpired:
        # タイムアウト超過時は強制終了してテスト失敗とする
        proc1.kill()
        for p in tracked_procs:
            try:
                p.kill()
            except Exception:
                pass
        raise AssertionError(f"--timeout 指定によるプロセスの自律終了がタイムアウトした")

    print("\n=== 全検証ステップが正常に完了した ===")


if __name__ == "__main__":
    run_verification()
