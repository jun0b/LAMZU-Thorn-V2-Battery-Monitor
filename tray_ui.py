"""LAMZU Thorn V2 システムトレイUIモジュール

pystrayライブラリを使用してWindowsタスクトレイに常駐し、
ツールチップ、動的メニュー、バッテリーアイコンの更新および終了処理を管理する。

pystrayのWin32バックエンドにおいて外部状態変更時に右クリックメニューが
自動更新されない問題に対処するため、状態変更時のIcon.update_menu()明示的呼び出し
およびWM_RBUTTONUP直前更新フックを実装している。
"""

import logging
import threading
from typing import Optional, Callable, Any

import pystray
from battery_state import BatteryState, ReceiveState
from icon_generator import create_battery_icon

logger = logging.getLogger("tray_ui")

# Win32 メッセージ定数
WM_NOTIFY = 0x004E
WM_RBUTTONUP = 0x0205
WM_LBUTTONUP = 0x0202


class LeftClickMenu(pystray.Menu):
    """左クリックを安全に捕捉するpystray.Menuサブクラス

    pystrayのWin32バックエンドでは、左クリック(WM_LBUTTONUP)時に
    icon() -> menu(icon) が呼び出される。本クラスでこれをフックし、
    ステータスパネル表示などのコールバックを実行する。
    """
    def __init__(self, *items, on_left_click: Optional[Callable[[], None]] = None):
        super().__init__(*items)
        self.on_left_click = on_left_click

    def __call__(self, icon):
        if self.on_left_click is not None:
            try:
                self.on_left_click()
            except Exception as e:
                logger.error(f"左クリックハンドラー実行エラー: {e}", exc_info=True)
            return
        super().__call__(icon)


class TrayUI:
    """Windowsシステムトレイ常駐UIクラス"""

    def __init__(
        self,
        state: BatteryState,
        on_exit: Optional[Callable[[], None]] = None,
        icon_style: str = "numbers-battery",
        notification_manager: Optional[Any] = None,
        autostart_manager: Optional[Any] = None,
        config_manager: Optional[Any] = None,
        status_panel: Optional[Any] = None,
        on_left_click: Optional[Callable[[], None]] = None
    ):
        self.state = state
        self.on_exit_callback = on_exit
        self.config_manager = config_manager
        # config_managerが指定されている場合は設定を使用。ただし引数で明示指定された場合はそれを優先
        if self.config_manager is not None:
            if icon_style != "numbers-battery":
                self.icon_style = icon_style
                self.config_manager.set_icon_style(icon_style)
            else:
                self.icon_style = self.config_manager.icon_style
        else:
            self.icon_style = icon_style
        self.notification_manager = notification_manager
        self.autostart_manager = autostart_manager
        self.status_panel = status_panel
        self.on_left_click = on_left_click
        self._icon: Optional[pystray.Icon] = None
        self._lock = threading.Lock()
        self._menu_lock = threading.Lock()
        self._is_running = False

        # アイコン再描画抑制用キャッシュ
        self._last_icon_percent: Optional[int] = None
        self._last_icon_style: str = self.icon_style
        self._last_stale_state: bool = False
        self._last_disconn_state: bool = False

        # メニュー更新抑制用キャッシュ
        self._last_menu_percent: Optional[int] = None
        self._last_menu_state: Optional[ReceiveState] = None

        # 動作検証・テスト用カウンタ
        self.menu_update_count: int = 0

    def _handle_style_change(self, new_style: str) -> None:
        """アイコンスタイル切り替えハンドラー

        同一スタイルの場合は不要な処理を抑制し、変更時はトレイアイコンを即時再描画し、
        設定を永続化してメニューのチェックマークを更新する。
        """
        if self.icon_style == new_style:
            return

        logger.info(f"アイコンデザインを切り替えます: '{self.icon_style}' -> '{new_style}'")
        self.icon_style = new_style
        if self.config_manager is not None:
            self.config_manager.set_icon_style(new_style)

        # 残量が変わっていなくてもトレイアイコンを即時強制再描画
        self.update_ui(force_icon_redraw=True)
        # メニューのチェックマークを更新
        self._update_menu_safe(reason=f"スタイル変更: {new_style}")

    def _get_icon_size(self) -> int:
        """Windows環境のシステムトレイアイコン推奨解像度を取得 (通常16, 高DPIで20, 24, 32等)"""
        try:
            import ctypes
            cx = ctypes.windll.user32.GetSystemMetrics(49)  # SM_CXSMICON
            return max(16, cx)
        except Exception:
            return 16

    def _is_autostart_enabled(self) -> bool:
        """自動起動が有効かどうかを取得"""
        if self.autostart_manager is not None:
            return self.autostart_manager.is_autostart_enabled()
        return False

    def _handle_toggle_autostart(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """「Windows起動時に自動起動」切り替えハンドラー"""
        if self.autostart_manager is not None:
            current = self.autostart_manager.is_autostart_enabled()
            self.autostart_manager.set_autostart(not current)
            logger.info(f"自動起動設定を切り替えました: 有効={not current}")
            self._update_menu_safe(reason="自動起動トグル切り替え")

    def _is_notifications_enabled(self) -> bool:
        """通知が有効かどうかを取得"""
        if self.notification_manager is not None:
            return self.notification_manager.notifications_enabled
        return False

    def _handle_toggle_notifications(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """「低残量通知を有効にする」切り替えハンドラー"""
        if self.notification_manager is not None:
            new_state = not self.notification_manager.notifications_enabled
            self.notification_manager.set_enabled(new_state)
            logger.info(f"通知設定を切り替えました: 有効={new_state}")
            self._update_menu_safe(reason="通知トグル切り替え")

    def _handle_send_test_notification(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """「テスト通知を送信」ハンドラー"""
        if self.notification_manager is not None:
            logger.info("ユーザーが「テスト通知を送信」を選択しました")
            self.notification_manager.send_test_notification()

    def _handle_open_aurora(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """「LAMZU Auroraを開く」ハンドラー (公式WebドライバーURLを既定ブラウザーで開く)"""
        url = "https://www.lamzu.net/#/project/items"
        logger.info(f"ユーザーが「LAMZU Auroraを開く」を選択しました: {url}")

        def _open_async():
            try:
                import webbrowser
                webbrowser.open(url)
            except Exception as e:
                logger.error(f"LAMZU Auroraのブラウザー起動に失敗しました: {e}", exc_info=True)

        threading.Thread(target=_open_async, daemon=True).start()

    def _handle_left_click(self) -> None:
        """トレイアイコン左クリック時のハンドラー (ステータスパネル表示/非表示トグル)"""
        if self.on_left_click:
            try:
                self.on_left_click()
            except Exception as e:
                logger.error(f"左クリックコールバック実行エラー: {e}")
        elif self.status_panel:
            try:
                self.status_panel.toggle(self.state)
            except Exception as e:
                logger.error(f"ステータスパネルトグルエラー: {e}")

    def build_menu(self) -> pystray.Menu:
        """右クリックメニュー構造を構築"""
        # アイコンデザインサブメニュー (3種類・排他選択ラジオボタン)
        style_menu_items = [
            pystray.MenuItem(
                text="数字のみ",
                action=lambda icon, item: self._handle_style_change("numbers-only"),
                checked=lambda item: self.icon_style == "numbers-only",
                radio=True
            ),
            pystray.MenuItem(
                text="バッテリーのみ",
                action=lambda icon, item: self._handle_style_change("battery-only"),
                checked=lambda item: self.icon_style == "battery-only",
                radio=True
            ),
            pystray.MenuItem(
                text="数字+バッテリー表示",
                action=lambda icon, item: self._handle_style_change("numbers-battery"),
                checked=lambda item: self.icon_style == "numbers-battery",
                radio=True
            ),
        ]
        style_submenu = pystray.Menu(*style_menu_items)

        items = [
            # 1. 低残量通知の有効化トグル (最上部)
            pystray.MenuItem(
                text="低残量通知を有効にする",
                action=self._handle_toggle_notifications,
                checked=lambda item: self._is_notifications_enabled(),
                enabled=lambda item: self.notification_manager is not None
            ),
            # 2. テスト通知を送信
            pystray.MenuItem(
                text="テスト通知を送信",
                action=self._handle_send_test_notification,
                enabled=lambda item: self.notification_manager is not None
            ),
            # 3. Windows起動時の自動起動トグル
            pystray.MenuItem(
                text="Windows起動時に自動起動",
                action=self._handle_toggle_autostart,
                checked=lambda item: self._is_autostart_enabled(),
                enabled=lambda item: self.autostart_manager is not None
            ),
            # 区切り線
            pystray.Menu.SEPARATOR,
            # 4. アイコンデザイン (ネイティブサブメニュー)
            pystray.MenuItem(
                text="アイコンデザイン",
                action=style_submenu
            ),
            # 区切り線
            pystray.Menu.SEPARATOR,
            # 5. LAMZU Auroraを開く (公式Webドライバー連携)
            pystray.MenuItem(
                text="LAMZU Auroraを開く",
                action=self._handle_open_aurora
            ),
            # 区切り線
            pystray.Menu.SEPARATOR,
            # 6. 終了
            pystray.MenuItem(
                text="終了",
                action=self._handle_exit_clicked
            )
        ]

        return LeftClickMenu(*items, on_left_click=self._handle_left_click)

    def _handle_exit_clicked(self, icon: pystray.Icon, item: pystray.MenuItem) -> None:
        """「終了」メニュー選択時のハンドラー"""
        logger.info("ユーザーにより「終了」が選択されました")
        if self.on_exit_callback:
            try:
                self.on_exit_callback()
            except Exception as e:
                logger.error(f"終了コールバック実行エラー: {e}")
        self.stop()

    def _update_menu_safe(self, reason: str = "") -> None:
        """スレッドセーフに右クリックメニューを再生成する

        pystrayのWin32バックエンドでは、動的メニュー項目（lambda）が外部状態から
        変更された場合、Icon.update_menu()を明示的に呼び出さないと右クリック時の
        HMENUハンドルが再構築されない。本メソッドで排他制御を行い安全に再生成する。
        """
        if self._icon is None or not self._is_running:
            return

        with self._menu_lock:
            try:
                logger.debug(f"右クリックメニューを再生成します (契機: {reason})")
                self._icon.update_menu()
                self.menu_update_count += 1
                self._last_menu_percent = self.state.percent
                self._last_menu_state = self.state.receive_state
                logger.debug(f"右クリックメニューの再生成が完了しました (更新累計: {self.menu_update_count}回)")
            except Exception as e:
                logger.debug(f"メニュー更新時の一時的エラー: {e}")

    def update_ui(self, force_icon_redraw: bool = False) -> None:
        """内部状態に基づいてトレイアイコン・ツールチップ・右クリックメニューを更新"""
        if self._icon is None or not self._is_running:
            return

        is_stale = (self.state.receive_state == ReceiveState.SLEEP_SUSPECTED)
        is_disconnected = (not self.state.dongle_available or self.state.receive_state == ReceiveState.DONGLE_DISCONNECTED)
        current_percent = self.state.percent
        current_state = self.state.receive_state

        # アイコン再描画が必要か判定
        need_icon_redraw = (
            force_icon_redraw or
            self._last_icon_percent != current_percent or
            self._last_icon_style != self.icon_style or
            self._last_stale_state != is_stale or
            self._last_disconn_state != is_disconnected
        )

        # メニュー再構築が必要か判定 (残量や通信状態が変化したときのみ更新)
        need_menu_update = (
            self._last_menu_percent != current_percent or
            self._last_menu_state != current_state
        )

        try:
            if need_icon_redraw:
                self._icon.icon = create_battery_icon(
                    percent=current_percent,
                    style=self.icon_style,
                    size=self._get_icon_size(),
                    is_stale=is_stale,
                    is_disconnected=is_disconnected
                )
                self._last_icon_percent = current_percent
                self._last_icon_style = self.icon_style
                self._last_stale_state = is_stale
                self._last_disconn_state = is_disconnected

            # ツールチップ（ホバー表示）の更新
            self._icon.title = self.state.get_tooltip_text()

            # ステータスパネルのリアルタイム状態更新
            if self.status_panel is not None:
                try:
                    self.status_panel.update_state(self.state)
                except Exception as e:
                    logger.debug(f"ステータスパネル更新時の一時的エラー: {e}")

        except Exception as e:
            logger.debug(f"トレイUI更新時の一時的エラー: {e}")

    def on_state_changed(self, state: BatteryState) -> None:
        """状態変更リスナーコールバック"""
        self.update_ui()
        if self.status_panel is not None:
            try:
                self.status_panel.update_state(state)
            except Exception as e:
                logger.debug(f"ステータスパネル更新時の一時的エラー: {e}")

    def _on_setup(self, icon: pystray.Icon) -> None:
        """pystrayのメインループ開始後に実行される初期化セットアップハンドラー"""
        logger.info("トレイUIセットアップハンドラーが開始されました")
        self._is_running = True
        icon.visible = True

        # Windowsバックエンド固有の通知フックを設定
        if hasattr(icon, "_message_handlers") and hasattr(icon, "_on_notify"):
            original_notify = icon._on_notify

            def hooked_on_notify(wparam, lparam):
                if lparam == WM_RBUTTONUP:
                    logger.debug("右クリック(WM_RBUTTONUP)を検知: メニューポップアップ直前に最新状態へ更新")
                    self._update_menu_safe(reason="右クリック直前更新")
                elif lparam == WM_LBUTTONUP:
                    logger.debug("左クリック(WM_LBUTTONUP)を検知: ステータスパネル表示トグル")
                    self._handle_left_click()
                return original_notify(wparam, lparam)

            icon._on_notify = hooked_on_notify
            icon._message_handlers[WM_NOTIFY] = hooked_on_notify
            logger.debug("Win32 WM_NOTIFY 通知フックを設定しました")

        # 起動直後の初期メニュー更新
        self._update_menu_safe(reason="UI起動初期化")
        self.update_ui()

    def start(self) -> None:
        """トレイアイコンを作成してイベントループを開始 (ブロッキング実行)"""
        # 初期アイコンの生成
        initial_icon = create_battery_icon(
            percent=self.state.percent,
            style=self.icon_style,
            size=self._get_icon_size(),
            is_stale=False,
            is_disconnected=not self.state.dongle_available
        )
        initial_title = self.state.get_tooltip_text()
        menu = self.build_menu()

        self._icon = pystray.Icon(
            name="LAMZU_Battery_Monitor",
            icon=initial_icon,
            title=initial_title,
            menu=menu
        )

        # 状態変更リスナーを登録
        self.state.add_listener(self.on_state_changed)

        logger.info("システムトレイアイコンを開始します")
        # setupハンドラーを指定してpystrayのメインループを実行
        self._icon.run(setup=self._on_setup)

    def stop(self) -> None:
        """トレイアイコンの削除およびループ終了"""
        self._is_running = False
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None
            logger.info("システムトレイアイコンを停止しました")
