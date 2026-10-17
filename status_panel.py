# -*- coding: utf-8 -*-
"""LAMZU Thorn V2 Tkinterステータスパネルモジュール

トレイアイコンの左クリックにより表示されるコンパクトでモダンなステータスパネル。
Tkinter + Canvas を採用し、ダークテーマでバッテリー残量・ゲージ・状態を描画するとともに、
パネル表示時にオンデマンドでDPIおよびポーリングレートをバックグラウンド取得し、
3点ドットローディングアニメーション（スレッドなし、afterタイマー駆動）を経て
取得完了後に左右2列のカード状エリアへ反映する。
"""

import ctypes
from ctypes import wintypes
import logging
import queue
import threading
import time
import tkinter as tk
from typing import Optional, Tuple, Callable, Dict, Any
from battery_state import BatteryState, ReceiveState
import device_query

logger = logging.getLogger("status_panel")

# Win32 API 構造体定義
class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG)
    ]

class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD)
    ]


def get_work_area_for_cursor(cx: int, cy: int) -> Tuple[int, int, int, int]:
    """カーソル位置のモニター作業領域 (left, top, right, bottom) を取得"""
    try:
        pt = wintypes.POINT(cx, cy)
        # MONITOR_DEFAULTTONEAREST = 2
        h_monitor = ctypes.windll.user32.MonitorFromPoint(pt, 2)
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if ctypes.windll.user32.GetMonitorInfoW(h_monitor, ctypes.byref(mi)):
            return (mi.rcWork.left, mi.rcWork.top, mi.rcWork.right, mi.rcWork.bottom)
    except Exception as e:
        logger.debug(f"作業領域の取得に失敗しました (フォールバック使用): {e}")

    # フォールバック: プライマリ作業領域
    try:
        rect = RECT()
        # SPI_GETWORKAREA = 0x0030
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
            return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        pass

    return (0, 0, 1920, 1040)


def get_current_cursor_pos() -> Tuple[int, int]:
    """現在のマウスカーソル座標 (x, y) を取得"""
    try:
        pt = wintypes.POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
            return (pt.x, pt.y)
    except Exception:
        pass
    return (100, 100)


class StatusPanel:
    """Tkinter Canvas製のバッテリー・デバイスステータスパネル"""

    WIDTH = 310
    HEIGHT = 285

    # ダークテーマカラーパレット
    BG_COLOR = "#1E1E1E"          # 背景色 (Windows 11 Dark)
    BORDER_COLOR = "#3A3A3C"      # 外枠色
    GAUGE_BG = "#2D2D30"          # ゲージ枠内背景
    GAUGE_BORDER = "#505054"      # ゲージ外枠
    DIVIDER_COLOR = "#333333"     # 区切り線
    TEXT_TITLE = "#FFFFFF"        # タイトル白
    TEXT_SUB = "#9E9E9E"          # サブタイトル淡灰
    TEXT_LABEL = "#808080"        # 項目ラベル灰
    TEXT_VALUE = "#D0D0D0"        # 項目値明灰

    # カードスタイル
    CARD_BG = "#252528"           # カード背景
    CARD_BORDER = "#3E3E42"       # カード枠線
    DOT_ACTIVE = "#4A90E2"        # アニメーション中のアクティブドット青
    DOT_INACTIVE = "#484848"      # 非アクティブドット灰

    # 残量カラー
    COLOR_CYAN = "#00D2FF"        # 充電完了 (水色/シアン)
    COLOR_GREEN = "#2ECC71"       # 51〜100%
    COLOR_ORANGE = "#F39C12"      # 21〜50%
    COLOR_RED = "#E74C3C"         # 0〜20% / 切断
    COLOR_GRAY = "#95A5A6"        # 未取得

    def __init__(self, root: Optional[tk.Tk] = None):
        """ステータスパネルを初期化

        Args:
            root: 既存のTkルート。未指定の場合は新規生成。
        """
        self._owns_root = (root is None)
        self.root = root if root is not None else tk.Tk()
        self.window = self.root if self._owns_root else tk.Toplevel(self.root)

        # ウィンドウ初期設定
        self.window.withdraw()  # 初期状態は非表示
        self.window.overrideredirect(True)  # タイトルバー・枠線を完全非表示
        self.window.attributes("-topmost", True)  # 常時最前面

        # 状態保持
        self._is_visible = False
        self._last_hide_time = 0.0
        self._last_show_time = 0.0
        self._lock = threading.Lock()
        self._current_state: Optional[BatteryState] = None

        # DPI・ポーリングレートキャッシュおよびローディング状態
        self._is_loading = False
        self._dot_frame = 0
        self._dot_timer_id: Optional[str] = None
        self._query_session: Optional[device_query.DeviceQuerySession] = None
        self._cached_dpi: Optional[int] = None
        self._cached_polling_rate: Optional[int] = None
        self._cached_active_stage: Optional[int] = None
        self._query_generation = 0
        self._result_queue: queue.Queue = queue.Queue()

        # Canvas UI構築
        self._build_ui()

        # イベントバインド
        self.window.bind("<FocusOut>", self._on_focus_out)
        self.window.bind("<Escape>", lambda e: self.hide())

    @property
    def is_visible(self) -> bool:
        """パネルが現在表示中かどうかを返却"""
        return self._is_visible

    def _build_ui(self) -> None:
        """Canvas UIの配置と初期描画"""
        self.canvas = tk.Canvas(
            self.window,
            width=self.WIDTH,
            height=self.HEIGHT,
            bg=self.BG_COLOR,
            highlightthickness=1,
            highlightbackground=self.BORDER_COLOR,
            highlightcolor=self.BORDER_COLOR
        )
        self.canvas.pack(fill="both", expand=True)

        # クリックイベント
        self.canvas.bind("<Button-1>", lambda e: self.canvas.focus_set())

    def _get_gauge_color(
        self,
        percent: Optional[int],
        is_disconnected: bool,
        is_charging_complete: bool = False
    ) -> str:
        """残量および充電完了状態に応じた色を返却 (統一しきい値)"""
        if is_disconnected:
            return self.COLOR_RED
        if percent is None:
            return self.COLOR_GRAY
        if is_charging_complete:
            return self.COLOR_CYAN
        if percent > 50:
            return self.COLOR_GREEN
        if percent > 20:
            return self.COLOR_ORANGE
        return self.COLOR_RED

    def _draw_dots(self, cx: int, cy: int, active_idx: int) -> None:
        """3点ドットローディングアニメーション（● ○ ○ -> ○ ● ○ -> ○ ○ ●）を描画"""
        spacing = 9
        dot_radius = 2.5
        start_x = cx - spacing
        for i in range(3):
            dx = start_x + (i * spacing)
            fill_color = self.DOT_ACTIVE if i == active_idx else self.DOT_INACTIVE
            self.canvas.create_oval(
                dx - dot_radius, cy - dot_radius,
                dx + dot_radius, cy + dot_radius,
                outline="",
                fill=fill_color
            )

    def render(self, state: Optional[BatteryState] = None) -> None:
        """Canvas上に現在の状態を描画 (GUIスレッドで実行)"""
        if state is not None:
            self._current_state = state
        cur = self._current_state

        self.canvas.delete("all")

        # 1. ヘッダー
        self.canvas.create_text(
            20, 18,
            anchor="nw",
            text="LAMZU Thorn V2",
            fill=self.TEXT_TITLE,
            font=("Segoe UI", 13, "bold")
        )
        self.canvas.create_text(
            20, 40,
            anchor="nw",
            text="Battery Monitor",
            fill=self.TEXT_SUB,
            font=("Segoe UI", 9)
        )

        # 状態の解析
        percent = cur.percent if cur else None
        is_disconnected = cur.is_disconnected if cur else False
        is_stale = cur.is_stale if cur else False
        is_charging = cur.is_charging if cur else False
        is_charging_complete = cur.is_charging_complete if cur else False
        if (
            cur
            and cur.last_valid_battery_at is not None
            and cur.receive_state in (ReceiveState.NORMAL, ReceiveState.SLEEP_SUSPECTED)
        ):
            from datetime import datetime
            dt = datetime.fromtimestamp(cur.last_valid_battery_at)
            last_updated_str = dt.strftime("%H:%M:%S")
        else:
            last_updated_str = "なし"

        # 2. バッテリー残量数値 (中央大文字) および 充電中/充電完了⚡アイコン
        gauge_color = self._get_gauge_color(percent, is_disconnected, is_charging_complete)
        if is_disconnected:
            percent_text = "切断"
            val_font = ("Segoe UI", 20, "bold")
        elif percent is None:
            percent_text = "--%"
            val_font = ("Segoe UI", 26, "bold")
        else:
            percent_text = f"{percent}%"
            val_font = ("Segoe UI", 26, "bold")

        text_id = self.canvas.create_text(
            self.WIDTH // 2, 70,
            anchor="center",
            text=percent_text,
            fill=gauge_color,
            font=val_font
        )

        # 充電中または充電完了時は⚡アイコンを配置（数字と合わせた領域を美しく中央配置）
        if (is_charging or is_charging_complete) and not is_disconnected:
            bbox = self.canvas.bbox(text_id)
            if bbox:
                text_w = bbox[2] - bbox[0]
                bolt_w = 10
                gap = 7
                total_w = text_w + gap + bolt_w
                start_x = (self.WIDTH - total_w) // 2
                new_text_x = start_x + (text_w // 2)
                bolt_x = start_x + text_w + gap + (bolt_w // 2)

                self.canvas.coords(text_id, new_text_x, 70)
                # 稲妻アイコン描画 (多角形ポリゴン: 高さ約18px, 幅約10px)
                points = [
                    bolt_x + 1, 70 - 9,
                    bolt_x - 5, 70 - 1,
                    bolt_x - 1, 70 - 1,
                    bolt_x - 3, 70 + 9,
                    bolt_x + 5, 70 + 1,
                    bolt_x + 1, 70 + 1,
                ]
                self.canvas.create_polygon(points, fill="#F1C40F", outline="", tags="lightning_bolt")

        # 3. 横長バッテリーゲージ
        gx0 = 35
        gy0 = 96
        gx1 = 265
        gy1 = 110
        # バッテリー外枠
        self.canvas.create_rectangle(
            gx0, gy0, gx1, gy1,
            outline=self.GAUGE_BORDER,
            fill=self.GAUGE_BG,
            width=1
        )
        # プラス極端子 (右端)
        self.canvas.create_rectangle(
            gx1 + 1, gy0 + 4, gx1 + 4, gy1 - 4,
            outline=self.GAUGE_BORDER,
            fill=self.GAUGE_BORDER,
            width=1
        )

        # 内部充填
        if percent is not None and percent > 0 and not is_disconnected:
            inner_w = (gx1 - gx0) - 4
            fill_w = max(2, int(inner_w * (min(100, percent) / 100.0)))
            self.canvas.create_rectangle(
                gx0 + 2, gy0 + 2, gx0 + 2 + fill_w, gy1 - 2,
                outline="",
                fill=gauge_color
            )

        # 4. 状態テキスト
        if is_disconnected:
            status_text = "● レシーバー切断中"
            status_color = self.COLOR_RED
        elif is_stale and percent is not None:
            status_text = "● スリープの可能性（通信途絶）"
            status_color = self.COLOR_ORANGE
        elif is_charging_complete:
            status_text = "● 接続中・充電完了"
            status_color = self.COLOR_CYAN
        elif is_charging:
            status_text = "● 接続中・充電中"
            status_color = self.COLOR_GREEN
        elif percent is not None:
            status_text = "● 接続中・受信正常"
            status_color = self.COLOR_GREEN
        else:
            status_text = "● 取得待機中..."
            status_color = self.COLOR_GRAY

        self.canvas.create_text(
            self.WIDTH // 2, 126,
            anchor="center",
            text=status_text,
            fill=status_color,
            font=("Segoe UI", 9)
        )

        # 5. 区切り線
        self.canvas.create_line(
            20, 144, self.WIDTH - 20, 144,
            fill=self.DIVIDER_COLOR,
            width=1
        )

        # 6. 詳細情報行 (2行)
        # 最終更新
        self.canvas.create_text(
            20, 156,
            anchor="nw",
            text="最終更新",
            fill=self.TEXT_LABEL,
            font=("Segoe UI", 9)
        )
        self.canvas.create_text(
            self.WIDTH - 20, 156,
            anchor="ne",
            text=last_updated_str,
            fill=self.TEXT_VALUE,
            font=("Segoe UI", 9)
        )

        # レシーバー
        self.canvas.create_text(
            20, 178,
            anchor="nw",
            text="レシーバー",
            fill=self.TEXT_LABEL,
            font=("Segoe UI", 9)
        )
        self.canvas.create_text(
            self.WIDTH - 20, 178,
            anchor="ne",
            text="LAMZU 8K Dongle V2",
            fill=self.TEXT_VALUE,
            font=("Segoe UI", 9)
        )

        # 7. 左右2列カード状エリア（現在のDPI / ポーリングレート）
        card_y0 = 205
        card_y1 = 265
        card_w = 125

        # 左カード: 現在のDPI
        c1_x0 = 20
        c1_x1 = c1_x0 + card_w
        self.canvas.create_rectangle(
            c1_x0, card_y0, c1_x1, card_y1,
            outline=self.CARD_BORDER,
            fill=self.CARD_BG,
            width=1
        )
        self.canvas.create_text(
            c1_x0 + 12, card_y0 + 10,
            anchor="nw",
            text="現在のDPI",
            fill=self.TEXT_LABEL,
            font=("Segoe UI", 8)
        )
        if self._is_loading:
            self._draw_dots((c1_x0 + c1_x1) // 2, card_y0 + 36, self._dot_frame)
        else:
            dpi_str = f"{self._cached_dpi}" if self._cached_dpi is not None else "—"
            self.canvas.create_text(
                (c1_x0 + c1_x1) // 2, card_y0 + 36,
                anchor="center",
                text=dpi_str,
                fill=self.TEXT_TITLE,
                font=("Segoe UI", 12, "bold")
            )

        # 右カード: ポーリングレート
        c2_x1 = self.WIDTH - 20
        c2_x0 = c2_x1 - card_w
        self.canvas.create_rectangle(
            c2_x0, card_y0, c2_x1, card_y1,
            outline=self.CARD_BORDER,
            fill=self.CARD_BG,
            width=1
        )
        self.canvas.create_text(
            c2_x0 + 12, card_y0 + 10,
            anchor="nw",
            text="ポーリングレート",
            fill=self.TEXT_LABEL,
            font=("Segoe UI", 8)
        )
        if self._is_loading:
            self._draw_dots((c2_x0 + c2_x1) // 2, card_y0 + 36, self._dot_frame)
        else:
            pr_str = f"{self._cached_polling_rate} Hz" if self._cached_polling_rate is not None else "—"
            self.canvas.create_text(
                (c2_x0 + c2_x1) // 2, card_y0 + 36,
                anchor="center",
                text=pr_str,
                fill=self.TEXT_TITLE,
                font=("Segoe UI", 12, "bold")
            )

    def _start_loading_animation(self) -> None:
        """ローディングアニメーションおよびオンデマンド問い合わせを開始"""
        self._stop_loading_animation()
        self._query_generation += 1
        current_gen = self._query_generation
        self._is_loading = True
        self._dot_frame = 0

        # アニメーションステップ (GUIスレッドで周期的に実行し、キュー結果を自律ポーリング)
        def _step():
            if not self._is_loading or not self._is_visible:
                return
            # キューに結果が届いていれば処理
            self._process_query_results()
            if not self._is_loading or not self._is_visible:
                return
            self._dot_frame = (self._dot_frame + 1) % 3
            self.render(self._current_state)
            self._dot_timer_id = self.window.after(200, _step)

        self._dot_timer_id = self.window.after(200, _step)

        # バックグラウンド問い合わせタスク完了コールバック
        def _on_complete(res: Dict[str, Any]):
            # バックグラウンドスレッドからはキューへの投入のみを行い、TkinterのUIスレッド操作は行わない
            self._result_queue.put((current_gen, res))

        self._query_session = device_query.query_device_settings_async(_on_complete)

    def _process_query_results(self) -> None:
        """キューから問い合わせ結果を取り出し、現行世代かつ表示中の場合のみUIへ反映 (GUIスレッドで実行)"""
        while not self._result_queue.empty():
            try:
                gen_id, res = self._result_queue.get_nowait()
            except queue.Empty:
                break

            # 世代が異なる（古いリクエスト）または既に非表示の場合は結果を破棄
            if gen_id != self._query_generation or not self._is_visible:
                logger.debug(f"古い世代または非表示中の問い合わせ結果を破棄: gen={gen_id}, current={self._query_generation}")
                continue

            if res.get('success'):
                self._cached_dpi = res.get('dpi')
                self._cached_polling_rate = res.get('polling_rate')
                self._cached_active_stage = res.get('active_stage')
            else:
                self._cached_dpi = None
                self._cached_polling_rate = None
                self._cached_active_stage = None

            self._stop_loading_animation()
            if self._is_visible:
                self.render(self._current_state)

    def _stop_loading_animation(self) -> None:
        """ローディングアニメーションおよび問い合わせを安全に停止"""
        self._is_loading = False
        self._query_generation += 1

        # キューに残存する未処理結果を破棄
        while not self._result_queue.empty():
            try:
                self._result_queue.get_nowait()
            except queue.Empty:
                break

        if self._dot_timer_id is not None:
            try:
                self.window.after_cancel(self._dot_timer_id)
            except Exception:
                pass
            self._dot_timer_id = None

        if self._query_session is not None:
            self._query_session.cancel()
            self._query_session = None

    def _calculate_position(self) -> Tuple[int, int]:
        """カーソル位置およびタスクバー位置から最適な表示座標を算出"""
        cx, cy = get_current_cursor_pos()
        work_l, work_t, work_r, work_b = get_work_area_for_cursor(cx, cy)

        # デフォルトはカーソル直上・中央
        px = cx - (self.WIDTH // 2)
        # タスクバーが画面下部にある場合 (標準)
        py = cy - self.HEIGHT - 12

        # タスクバーが画面上部にある場合の補正
        if cy < work_t + self.HEIGHT + 30:
            py = cy + 16

        # 作業領域内に収まるようクランプ (はみ出し防止)
        margin = 8
        px = max(work_l + margin, min(px, work_r - self.WIDTH - margin))
        py = max(work_t + margin, min(py, work_b - self.HEIGHT - margin))

        return (px, py)

    def show(self, state: Optional[BatteryState] = None) -> None:
        """パネルを表示 (スレッドセーフ)"""
        def _do_show():
            try:
                if not self.window.winfo_exists():
                    return
                if state is not None:
                    self._current_state = state
                px, py = self._calculate_position()
                self.window.geometry(f"{self.WIDTH}x{self.HEIGHT}+{px}+{py}")
                self._is_visible = True
                self._last_show_time = time.time()
                # オンデマンド問い合わせ & アニメーション開始
                self._start_loading_animation()
                self.render(self._current_state)
                self.window.deiconify()
                self.window.lift()
                self.window.focus_force()
                self.canvas.focus_set()
                logger.debug(f"ステータスパネルを表示しました: 座標=({px}, {py})")
            except Exception:
                pass

        try:
            if threading.current_thread() is threading.main_thread():
                _do_show()
            else:
                self.root.after(0, _do_show)
        except Exception:
            pass

    def hide(self) -> None:
        """パネルを非表示 (スレッドセーフ)"""
        def _do_hide():
            try:
                if self._is_visible:
                    self._stop_loading_animation()
                    if self.window.winfo_exists():
                        self.window.withdraw()
                    self._is_visible = False
                    self._last_hide_time = time.time()
                    logger.debug("ステータスパネルを非表示にしました")
            except Exception:
                pass

        try:
            if threading.current_thread() is threading.main_thread():
                _do_hide()
            else:
                self.root.after(0, _do_hide)
        except Exception:
            pass

    def toggle(self, state: Optional[BatteryState] = None) -> None:
        """表示/非表示をトグル (チャタリング・クリック重複防止)"""
        now = time.time()
        # 直近の非表示(FocusOut等)から250ms以内のトグル要求は同一クリックの残余とみなして無視
        if not self._is_visible and (now - self._last_hide_time < 0.25):
            logger.debug("チャタリング防止ガードによりトグル要求をスキップしました")
            return

        if self._is_visible:
            self.hide()
        else:
            self.show(state)

    def update_state(self, state: BatteryState) -> None:
        """外部からバッテリー状態を更新 (表示中の場合のみ再描画)"""
        def _do_update():
            self._current_state = state
            if self._is_visible:
                self.render(state)

        self.root.after(0, _do_update)

    def _on_focus_out(self, event) -> None:
        """ウィンドウ外クリック検知による自動非表示"""
        # フォーカスが自分自身または子ウィジェットにない場合に閉じる
        try:
            focus_widget = self.window.focus_get()
            if focus_widget is None or (focus_widget != self.window and focus_widget != self.canvas):
                self.hide()
        except Exception:
            self.hide()

    def destroy(self) -> None:
        """ウィンドウおよびリソースの解放"""
        self._stop_loading_animation()
        try:
            self.window.destroy()
        except Exception:
            pass


class StatusPanelManager:
    """StatusPanelをバックグラウンドスレッドで統括・管理するマネージャー"""

    def __init__(self, battery_state: BatteryState):
        self.battery_state = battery_state
        self.panel: Optional[StatusPanel] = None
        self._root: Optional[tk.Tk] = None
        self._thread: Optional[threading.Thread] = None
        self._is_ready = threading.Event()
        self._is_running = False

    def start(self) -> None:
        """Tkinterメインループを専用スレッドで起動"""
        if self._thread is not None and self._thread.is_alive():
            return

        self._is_running = True
        self._thread = threading.Thread(
            target=self._run_tk,
            name="StatusPanelThread",
            daemon=True
        )
        self._thread.start()
        # 初期化完了まで最大3秒待機
        self._is_ready.wait(timeout=3.0)
        logger.info("ステータスパネルマネージャーが起動しました")

    def _run_tk(self) -> None:
        """専用スレッド内でTkinterイベントループを実行"""
        try:
            self._root = tk.Tk()
            self._root.withdraw()
            self.panel = StatusPanel(root=self._root)
            self._is_ready.set()
            self._root.mainloop()
        except Exception as e:
            logger.error(f"ステータスパネルスレッドでエラーが発生しました: {e}")
        finally:
            self._is_running = False
            self._is_ready.set()

    def toggle(self) -> None:
        """トレイUIからの要求でパネル表示をトグル"""
        if self.panel and self._is_ready.is_set():
            self.panel.toggle(self.battery_state)

    def show(self) -> None:
        """パネルを明示的に表示"""
        if self.panel and self._is_ready.is_set():
            self.panel.show(self.battery_state)

    def hide(self) -> None:
        """パネルを明示的に非表示"""
        if self.panel and self._is_ready.is_set():
            self.panel.hide()

    def stop(self) -> None:
        """マネージャーおよびTkinterループを終了"""
        self._is_running = False
        if self.panel:
            try:
                self.panel.destroy()
            except Exception:
                pass
        if self._root:
            try:
                self._root.quit()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logger.info("ステータスパネルマネージャーを停止しました")
