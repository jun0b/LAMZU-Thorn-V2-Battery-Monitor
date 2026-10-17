"""LAMZU Thorn V2 トレイアイコン生成モジュール

Pillow (PIL) を使用して、バッテリー残量の数値とバッテリーゲージを
同時に表示するシステムトレイアイコン画像を動的に生成する。

3種類のデザイン案に対応:
  - numbers-only   : 数字のみ (バッテリー枠なし、数値最大化)
  - battery-only   : バッテリーのみ (数値なし、横長ゲージのみ)
  - numbers-battery: 数字+バッテリー表示 (上部に数値、下部にバッテリーゲージ)

16x16px, 20x20px, 24x24px, 32x32px の各解像度に対応し、
Windowsのダークモード・ライトモードの両方で高い視認性を確保する。
"""

import os
from typing import Optional, Tuple, Dict, Any, List
from PIL import Image, ImageDraw, ImageFont

# Windows標準フォントの検索パス
WINDIR = os.environ.get("WINDIR", "C:\\Windows")
FONTS_DIR = os.path.join(WINDIR, "Fonts")

# 視認性に優れたボールドフォント候補
FONT_CANDIDATES = [
    os.path.join(FONTS_DIR, "arialbd.ttf"),   # Arial Bold (英数字の幅が狭く100%の収まりが良い)
    os.path.join(FONTS_DIR, "segoeuib.ttf"),  # Segoe UI Bold (Windows標準UIフォント)
    os.path.join(FONTS_DIR, "tahomabd.ttf"),  # Tahoma Bold
]


# プレビュー画像の日本語ラベル用フォント候補
LABEL_FONT_CANDIDATES = [
    os.path.join(FONTS_DIR, "meiryo.ttc"),    # Meiryo (日本語標準)
    os.path.join(FONTS_DIR, "msgothic.ttc"),  # MS Gothic
    os.path.join(FONTS_DIR, "yugothb.ttf"),   # Yu Gothic Bold
    os.path.join(FONTS_DIR, "arialbd.ttf"),   # Arial Bold
]


def get_font(size: int) -> ImageFont.ImageFont:
    """指定されたピクセルサイズに最適なフォントを取得 (数字描画用)"""
    for font_path in FONT_CANDIDATES:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def get_label_font(size: int) -> ImageFont.ImageFont:
    """プレビュー画像の日本語見出し・ラベル描画用フォントを取得"""
    for font_path in LABEL_FONT_CANDIDATES:
        if os.path.exists(font_path):
            try:
                return ImageFont.truetype(font_path, size)
            except Exception:
                continue
    return get_font(size)


def get_battery_color(percent: Optional[int], is_charging_complete: bool = False) -> Tuple[int, int, int]:
    """残量パーセンテージおよび充電完了状態に応じた色を返却 (RGB)

    - 充電完了: 水色/シアン (#00D2FF)
    - 51〜100%: 通常色 (緑系 #2ECC71)
    - 21〜50% : 注意色 (橙系 #F39C12)
    - 0〜20%  : 警告色 (赤系 #E74C3C)
    - 未取得  : 灰色 (#95A5A6)
    """
    if percent is None:
        return (149, 165, 166)  # 灰色
    if is_charging_complete:
        return (0, 210, 255)    # 水色/シアン (充電完了)
    if percent > 50:
        return (46, 204, 113)   # 緑
    if percent > 20:
        return (243, 156, 18)   # 橙
    return (231, 76, 60)        # 赤


# スタイル名の正規化・互換マッピング
STYLE_NORMALIZATION: Dict[str, str] = {
    "numbers-only": "numbers-only",
    "battery-only": "battery-only",
    "numbers-battery": "numbers-battery",
    # 旧設定キーとの互換マッピング
    "top-a3": "numbers-battery",
    "top-a1": "numbers-battery",
    "top-a2": "numbers-battery",
    "top": "numbers-battery",
    "bottom": "numbers-battery",
    "overlay": "numbers-battery",
}


def _draw_lightning_bolt(
    draw: ImageDraw.ImageDraw,
    x: float,
    y: float,
    w: float,
    h: float,
    color: Tuple[int, int, int, int] = (255, 213, 79, 255),
    outline: Tuple[int, int, int, int] = (0, 0, 0, 255)
) -> None:
    """指定された矩形領域 (x, y, w, h) 内に金色⚡マーク（稲妻図形）を描画"""
    points = [
        (x + w * 0.65, y),               # 上部頂点 (右寄り)
        (x + w * 0.10, y + h * 0.52),    # 左外側カド
        (x + w * 0.50, y + h * 0.52),    # 左内側ノッチ
        (x + w * 0.20, y + h),           # 最下部先端
        (x + w * 0.90, y + h * 0.42),    # 右外側カド
        (x + w * 0.50, y + h * 0.42),    # 右内側ノッチ
    ]
    # 全方位1pxオフセットで黒アウトラインを描画
    if outline:
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                if dx == 0 and dy == 0:
                    continue
                offset_points = [(px + dx, py + dy) for px, py in points]
                draw.polygon(offset_points, fill=outline)
    draw.polygon(points, fill=color)


def create_battery_icon(
    percent: Optional[int],
    style: str = "numbers-battery",
    size: int = 16,
    is_stale: bool = False,
    is_disconnected: bool = False,
    is_charging: bool = False,
    is_charging_complete: bool = False
) -> Image.Image:
    """バッテリー残量と数値を組み合わせたトレイ用アイコン画像を生成

    Args:
        percent: バッテリー残量 (0〜100 または None)
        style: デザイン案
               - 'numbers-only'   : 数字のみ (バッテリー枠なし、数値最大化)
               - 'battery-only'   : バッテリーのみ (数値なし、横長ゲージのみ)
               - 'numbers-battery': 数字+バッテリー表示 (上部に数値、下部にバッテリーゲージ)
        size: 画像のピクセルサイズ (デフォルト: 16x16, 20, 24, 32等)
        is_stale: 受信途絶・スリープ推測状態か
        is_disconnected: ドングル切断状態か
        is_charging: 充電中かどうか (正常受信中かつCHARGING判定時のみ有効)
        is_charging_complete: 充電完了かどうか (正常受信中かつCHARGING_COMPLETE判定時のみ有効)

    Returns:
        Image.Image: RGBA形式のPillowイメージオブジェクト
    """
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # 状態に応じたゲージ色 (全スタイル共通の統一しきい値)
    # 充電完了: 水色/シアン, 51〜100%: 緑, 21〜50%: 橙, 0〜20%: 赤, 未取得: 灰
    effective_complete = is_charging_complete and not is_disconnected and not is_stale and percent is not None
    base_color = get_battery_color(percent, is_charging_complete=effective_complete)
    if is_disconnected:
        gauge_color = (231, 76, 60, 255)
    elif is_stale and percent is not None:
        gauge_color = base_color + (180,)
    else:
        gauge_color = base_color + (255,)

    # ダーク/ライト両モードで見やすい外枠・背景色
    border_color = (255, 255, 255, 220)
    bg_color = (25, 25, 25, 200)

    # 表示するテキスト
    if is_disconnected:
        text = "X"
    elif percent is None:
        text = "?"
    else:
        text = str(max(0, min(100, percent)))

    s = size / 16.0  # 16pxを基準としたスケーリング比率
    norm_style = STYLE_NORMALIZATION.get(style, "numbers-battery")

    # 確実に正常接続・残量取得中である場合のみ充電中/充電完了の⚡マークを表示
    show_charging = (is_charging or is_charging_complete) and not is_disconnected and not is_stale and percent is not None

    if norm_style == "numbers-only":
        # ==========================================
        # 1. 数字のみ：バッテリー形状なし、残量数値のみを表示
        # ==========================================
        if show_charging:
            # 充電中: 数字を左側に配置し、右下に金色の⚡マークを表示
            if text == "100":
                font_size = max(6, int(size * 0.44))
                font = get_font(font_size)
                bbox = font.getbbox(text)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                tx = 0 - bbox[0]
                ty = max(0, int(1 * s)) - bbox[1]
                bw = max(4, int(4.5 * s))
                bh = max(6, int(7 * s))
                bx = size - bw - 1
                by = size - bh
            elif len(text) == 1:
                font_size = max(10, int(size * 0.72))
                font = get_font(font_size)
                bbox = font.getbbox(text)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                tx = max(1, int(1 * s)) - bbox[0]
                ty = (size - th) // 2 - bbox[1]
                bw = max(5, int(5 * s))
                bh = max(7, int(8 * s))
                bx = size - bw - 1
                by = size - bh - 1
            else:
                font_size = max(8, int(size * 0.60))
                font = get_font(font_size)
                bbox = font.getbbox(text)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                tx = 0 - bbox[0]
                ty = (size - th) // 2 - bbox[1]
                bw = max(4, int(4.5 * s))
                bh = max(6, int(7 * s))
                bx = size - bw
                by = size - bh - 1

            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]:
                draw.text((tx + dx, ty + dy), text, font=font, fill=(0, 0, 0, 255))
            draw.text((tx, ty), text, font=font, fill=gauge_color)
            _draw_lightning_bolt(draw, bx, by, bw, bh)

        else:
            # 非充電時 (v1.0.0と完全同一)
            if text == "100":
                font_size = max(7, int(size * 0.50))
            elif len(text) == 1:
                font_size = max(11, int(size * 0.82))
            else:
                font_size = max(9, int(size * 0.68))

            font = get_font(font_size)
            bbox = font.getbbox(text)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]

            while (tw + 2 > size) and font_size > 5:
                font_size -= 1
                font = get_font(font_size)
                bbox = font.getbbox(text)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]

            tx = (size - tw) // 2 - bbox[0]
            ty = (size - th) // 2 - bbox[1]

            for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]:
                draw.text((tx + dx, ty + dy), text, font=font, fill=(0, 0, 0, 255))
            draw.text((tx, ty), text, font=font, fill=gauge_color)

    elif norm_style == "battery-only":
        # ==========================================
        # 2. バッテリーのみ：数値非表示、横長バッテリー形状のみ
        # ==========================================
        bh = max(6, int(7 * s))
        by0 = (size - bh) // 2
        by1 = by0 + bh
        bx0 = max(1, int(1 * s))
        bx1 = size - max(3, int(3 * s))

        # 端子 (プラス極)
        tx0 = bx1 + 1
        tx1 = min(size - 1, tx0 + max(1, int(1 * s)))
        ty0 = by0 + max(1, int(1.5 * s))
        ty1 = by1 - max(1, int(1.5 * s))

        draw.rectangle([bx0, by0, bx1, by1], outline=border_color, fill=bg_color)
        draw.rectangle([tx0, ty0, tx1, ty1], fill=border_color)

        if is_disconnected:
            # 切断時: 内部に赤いXを描画
            draw.line([bx0 + 2, by0 + 2, bx1 - 2, by1 - 2], fill=(231, 76, 60, 255), width=max(1, int(1 * s)))
            draw.line([bx0 + 2, by1 - 2, bx1 - 2, by0 + 2], fill=(231, 76, 60, 255), width=max(1, int(1 * s)))
        elif percent is not None and percent > 0:
            inner_w = bx1 - bx0 - 2
            fill_w = max(1, int(inner_w * (min(100, percent) / 100.0)))
            draw.rectangle([bx0 + 1, by0 + 1, bx0 + 1 + fill_w, by1 - 1], fill=gauge_color)

        if show_charging:
            # 充電中: 残量ゲージの視認性を確保するためスリムな金色⚡マークを描画
            bolt_w = max(3, int(3.5 * s))
            bolt_h = max(7, int(7.5 * s))
            bolt_x = max(6, int(6.5 * s))
            bolt_y = (by0 + by1 - bolt_h) // 2
            _draw_lightning_bolt(draw, bolt_x, bolt_y, bolt_w, bolt_h)

    else:
        # ==========================================
        # 3. 数字+バッテリー表示：数値とバッテリーゲージの併記
        # ==========================================
        # 1. バッテリーゲージ (下部: 高さ5px、端子明確化)
        by0 = size - max(5, int(5 * s))
        by1 = size - 1
        bx0 = max(1, int(1 * s))
        bx1 = size - max(4, int(4 * s))

        # 端子 (プラス極: 幅2px, 高さ3px)
        tx0 = bx1 + 1
        tx1 = min(size - 1, tx0 + max(1, int(1.5 * s)))
        ty0 = by0 + max(1, int(1 * s))
        ty1 = by1 - max(1, int(1 * s))

        draw.rectangle([bx0, by0, bx1, by1], outline=border_color, fill=bg_color)
        draw.rectangle([tx0, ty0, tx1, ty1], fill=border_color)

        # ゲージ内部塗りつぶし (内側3px)
        if percent is not None and percent > 0 and not is_disconnected:
            inner_w = bx1 - bx0 - 2
            fill_w = max(1, int(inner_w * (min(100, percent) / 100.0)))
            draw.rectangle([bx0 + 1, by0 + 1, bx0 + 1 + fill_w, by1 - 1], fill=gauge_color)

        if show_charging:
            # 充電中: 下部バッテリーゲージ中央に金色の⚡マークを描画
            bolt_w = max(4, int(4 * s))
            bolt_h = max(4, int(5 * s))
            bolt_x = (bx0 + bx1 - bolt_w) // 2
            bolt_y = by0
            _draw_lightning_bolt(draw, bolt_x, bolt_y, bolt_w, bolt_h)

        # 2. 数値 (上部: 10〜11px領域)
        if text == "100":
            font_size = max(7, int(size * 0.46))
        elif len(text) == 1:
            font_size = max(10, int(size * 0.60))
        else:
            font_size = max(9, int(size * 0.56))
        font = get_font(font_size)

        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (size - tw) // 2 - bbox[0]
        ty = max(0, int(0.2 * s)) - bbox[1]

        # 十字輪郭描画
        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            draw.text((tx + dx, ty + dy), text, font=font, fill=(0, 0, 0, 255))
        draw.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))

    return image


def generate_all_previews(output_dir: str = "logs/icon_previews") -> Dict[str, str]:
    """3種類全デザイン・各残量・各サイズにおける非充電/充電中の比較画像を生成して保存する

    Args:
        output_dir: プレビュー画像の保存先ディレクトリ (デフォルト: logs/icon_previews)

    Returns:
        Dict[str, str]: 生成した主要比較画像のファイルパス辞書
    """
    os.makedirs(output_dir, exist_ok=True)
    generated_files = {}

    styles = [
        ("numbers-only", "数字のみ"),
        ("battery-only", "バッテリーのみ"),
        ("numbers-battery", "数字+バッテリー表示"),
    ]
    # 指示書指定のバッテリー残量: 9%, 10%, 20%, 50%, 99%, 100%
    percents = [9, 10, 20, 50, 99, 100]
    sizes = [16, 20, 24, 32]
    label_font = get_label_font(12)
    sub_font = get_label_font(9)

    # 1. 各案・各残量の個別PNG (16x16px) 出力 (非充電・充電中)
    for style_key, _ in styles:
        style_slug = style_key.replace("-", "_")
        for p in percents:
            for is_chg in [False, True]:
                suffix = "_charging" if is_chg else ""
                filename = f"icon_{style_slug}_{p}pct{suffix}_16px.png"
                filepath = os.path.join(output_dir, filename)
                img = create_battery_icon(p, style=style_key, size=16, is_charging=is_chg)
                img.save(filepath)

    # 2. 全3案 横並び比較画像 (16x16px 実寸シート: 通常 vs 充電中⚡)
    pair_w = 64
    margin_left = 220
    margin_top = 50
    img_w = margin_left + len(percents) * pair_w + 20
    row_h = 50
    img_h = margin_top + len(styles) * row_h + 20

    comp_16 = Image.new("RGBA", (img_w, img_h), (30, 32, 36, 255))
    draw_comp = ImageDraw.Draw(comp_16)

    # タイトル
    draw_comp.text((15, 12), "トレイアイコン表示比較 (16×16px 実寸: 通常 / 充電中)", fill=(255, 255, 255, 255), font=label_font)

    # 列ヘッダー
    for col_idx, p in enumerate(percents):
        cx = margin_left + col_idx * pair_w
        header_text = f"{p}%"
        bbox = label_font.getbbox(header_text)
        hw = bbox[2] - bbox[0]
        draw_comp.text((cx + (pair_w - hw) // 2, margin_top - 24), header_text, fill=(200, 205, 215, 255), font=label_font)
        draw_comp.text((cx + 6, margin_top - 10), "通常", fill=(140, 145, 155, 255), font=sub_font)
        draw_comp.text((cx + 34, margin_top - 10), "充電中", fill=(255, 213, 79, 255), font=sub_font)

    for row_idx, (style_key, style_label) in enumerate(styles):
        row_y = margin_top + row_idx * row_h
        draw_comp.text((15, row_y + 14), style_label, fill=(255, 255, 255, 255), font=label_font)

        for col_idx, p in enumerate(percents):
            cx = margin_left + col_idx * pair_w

            # 通常 (左)
            icon_norm = create_battery_icon(p, style=style_key, size=16, is_charging=False)
            x_norm = cx + 8
            y_norm = row_y + 12
            draw_comp.rectangle([x_norm - 2, y_norm - 2, x_norm + 17, y_norm + 17], outline=(55, 60, 68, 255))
            comp_16.alpha_composite(icon_norm, (x_norm, y_norm))

            # 充電中 (右)
            icon_chg = create_battery_icon(p, style=style_key, size=16, is_charging=True)
            x_chg = cx + 38
            y_chg = row_y + 12
            draw_comp.rectangle([x_chg - 2, y_chg - 2, x_chg + 17, y_chg + 17], outline=(85, 80, 50, 255))
            comp_16.alpha_composite(icon_chg, (x_chg, y_chg))

    path_comp_16 = os.path.join(output_dir, "comparison_charging_vs_normal_16px.png")
    comp_16.save(path_comp_16)
    generated_files["comparison_16px"] = path_comp_16

    # 3. 16x16pxのNearest Neighbor 8倍拡大シート (ピクセル精査用)
    zoom_factor = 8
    zoom_w = img_w * zoom_factor
    zoom_h = img_h * zoom_factor
    zoom_img = comp_16.resize((zoom_w, zoom_h), Image.Resampling.NEAREST)
    path_zoom = os.path.join(output_dir, "preview_charging_vs_normal_zoom8x.png")
    zoom_img.save(path_zoom)
    generated_files["zoom_8x"] = path_zoom

    # 4. 「数字のみ (numbers-only)」重点視認性・クリッピング比較シート (9, 10, 20, 50, 99, 100%)
    focus_w = 820
    focus_row_h = 148
    focus_h = 60 + len(percents) * focus_row_h
    focus_img = Image.new("RGBA", (focus_w, focus_h), (25, 27, 30, 255))
    draw_focus = ImageDraw.Draw(focus_img)

    draw_focus.text((20, 15), "「数字のみ (numbers-only)」重点視認性比較 (16px実寸 & 8倍拡大 128px)", fill=(255, 255, 255, 255), font=label_font)
    draw_focus.text((120, 38), "16px 通常", fill=(180, 185, 195, 255), font=sub_font)
    draw_focus.text((200, 38), "16px 充電中", fill=(255, 213, 79, 255), font=sub_font)
    draw_focus.text((310, 38), "通常 (8倍拡大 128px)", fill=(180, 185, 195, 255), font=sub_font)
    draw_focus.text((560, 38), "充電中 (8倍拡大 128px)", fill=(255, 213, 79, 255), font=sub_font)

    for p_idx, p in enumerate(percents):
        ry = 60 + p_idx * focus_row_h
        draw_focus.text((20, ry + 55), f"{p}%", fill=(240, 240, 240, 255), font=label_font)

        i_norm = create_battery_icon(p, style="numbers-only", size=16, is_charging=False)
        i_chg = create_battery_icon(p, style="numbers-only", size=16, is_charging=True)

        # 実寸
        draw_focus.rectangle([129, ry + 55, 146, ry + 72], outline=(55, 60, 68, 255))
        focus_img.alpha_composite(i_norm, (130, ry + 56))

        draw_focus.rectangle([209, ry + 55, 226, ry + 72], outline=(85, 80, 50, 255))
        focus_img.alpha_composite(i_chg, (210, ry + 56))

        # 8倍拡大 (128x128px)
        i_norm_8x = i_norm.resize((128, 128), Image.Resampling.NEAREST)
        i_chg_8x = i_chg.resize((128, 128), Image.Resampling.NEAREST)

        draw_focus.rectangle([299, ry + 9, 429, ry + 139], outline=(55, 60, 68, 255))
        focus_img.alpha_composite(i_norm_8x, (300, ry + 10))

        draw_focus.rectangle([549, ry + 9, 679, ry + 139], outline=(85, 80, 50, 255))
        focus_img.alpha_composite(i_chg_8x, (550, ry + 10))

    path_focus = os.path.join(output_dir, "comparison_numbers_only_focus.png")
    focus_img.save(path_focus)
    generated_files["numbers_only_focus"] = path_focus

    # 4-2. 「バッテリーのみ (battery-only)」重点視認性・ゲージ露出比較シート (9, 10, 20, 50, 99, 100%)
    batt_focus_img = Image.new("RGBA", (focus_w, focus_h), (25, 27, 30, 255))
    draw_bf = ImageDraw.Draw(batt_focus_img)

    draw_bf.text((20, 15), "「バッテリーのみ (battery-only)」重点視認性比較 (16px実寸 & 8倍拡大 128px)", fill=(255, 255, 255, 255), font=label_font)
    draw_bf.text((120, 38), "16px 通常", fill=(180, 185, 195, 255), font=sub_font)
    draw_bf.text((200, 38), "16px 充電中", fill=(255, 213, 79, 255), font=sub_font)
    draw_bf.text((310, 38), "通常 (8倍拡大 128px)", fill=(180, 185, 195, 255), font=sub_font)
    draw_bf.text((560, 38), "充電中 (8倍拡大 128px)", fill=(255, 213, 79, 255), font=sub_font)

    for p_idx, p in enumerate(percents):
        ry = 60 + p_idx * focus_row_h
        draw_bf.text((20, ry + 55), f"{p}%", fill=(240, 240, 240, 255), font=label_font)

        i_norm = create_battery_icon(p, style="battery-only", size=16, is_charging=False)
        i_chg = create_battery_icon(p, style="battery-only", size=16, is_charging=True)

        # 実寸
        draw_bf.rectangle([129, ry + 55, 146, ry + 72], outline=(55, 60, 68, 255))
        batt_focus_img.alpha_composite(i_norm, (130, ry + 56))

        draw_bf.rectangle([209, ry + 55, 226, ry + 72], outline=(85, 80, 50, 255))
        batt_focus_img.alpha_composite(i_chg, (210, ry + 56))

        # 8倍拡大 (128x128px)
        i_norm_8x = i_norm.resize((128, 128), Image.Resampling.NEAREST)
        i_chg_8x = i_chg.resize((128, 128), Image.Resampling.NEAREST)

        draw_bf.rectangle([299, ry + 9, 429, ry + 139], outline=(55, 60, 68, 255))
        batt_focus_img.alpha_composite(i_norm_8x, (300, ry + 10))

        draw_bf.rectangle([549, ry + 9, 679, ry + 139], outline=(85, 80, 50, 255))
        batt_focus_img.alpha_composite(i_chg_8x, (550, ry + 10))

    path_batt_focus = os.path.join(output_dir, "comparison_battery_only_focus.png")
    batt_focus_img.save(path_batt_focus)
    generated_files["battery_only_focus"] = path_batt_focus

    # 5. マルチサイズ比較画像 (16, 20, 24, 32px) × (通常 vs 充電中)
    ms_w = 820
    ms_h = 70 + len(styles) * 75
    ms_img = Image.new("RGBA", (ms_w, ms_h), (30, 32, 36, 255))
    draw_ms = ImageDraw.Draw(ms_img)

    draw_ms.text((20, 15), "各解像度での視認性比較 (16px, 20px, 24px, 32px: 通常 vs 充電中)", fill=(255, 255, 255, 255), font=label_font)

    x_offsets = [230, 350, 490, 650]
    for idx, sz in enumerate(sizes):
        draw_ms.text((x_offsets[idx], 40), f"{sz}×{sz}px (100%)", fill=(200, 205, 215, 255), font=label_font)

    for row_idx, (style_key, style_label) in enumerate(styles):
        ry = 70 + row_idx * 75
        draw_ms.text((15, ry + 20), style_label, fill=(255, 255, 255, 255), font=label_font)

        for col_idx, sz in enumerate(sizes):
            cx = x_offsets[col_idx]
            img_norm = create_battery_icon(100, style=style_key, size=sz, is_charging=False)
            img_chg = create_battery_icon(100, style=style_key, size=sz, is_charging=True)

            draw_ms.rectangle([cx - 2, ry - 2, cx + sz + 1, ry + sz + 1], outline=(55, 60, 68, 255))
            draw_ms.rectangle([cx + sz + 8, ry - 2, cx + sz * 2 + 11, ry + sz + 1], outline=(85, 80, 50, 255))

            ms_img.alpha_composite(img_norm, (cx, ry))
            ms_img.alpha_composite(img_chg, (cx + sz + 10, ry))

            draw_ms.text((cx, ry + sz + 4), "通常", fill=(140, 145, 155, 255), font=sub_font)
            draw_ms.text((cx + sz + 10, ry + sz + 4), "充電中", fill=(255, 213, 79, 255), font=sub_font)

    path_ms = os.path.join(output_dir, "comparison_multisize.png")
    ms_img.save(path_ms)
    generated_files["multisize"] = path_ms

    # 6. ダークモード・ライトモードタスクバー背景での見え方比較画像
    theme_w = 760
    theme_h = 70 + len(styles) * 55
    theme_img = Image.new("RGBA", (theme_w, theme_h), (20, 20, 20, 255))
    draw_theme = ImageDraw.Draw(theme_img)

    # 左半分: Windows Dark Mode タスクバー色 (#202020)
    draw_theme.rectangle([10, 10, 370, theme_h - 10], fill=(32, 32, 32, 255), outline=(60, 60, 60, 255))
    draw_theme.text((20, 20), "Windows 11 ダークモードタスクバー", fill=(255, 255, 255, 255), font=label_font)
    draw_theme.text((150, 42), "通常 (50/100%)", fill=(180, 180, 180, 255), font=sub_font)
    draw_theme.text((260, 42), "充電中 (50/100%)", fill=(255, 213, 79, 255), font=sub_font)

    # 右半分: Windows Light Mode タスクバー色 (#F3F3F3)
    draw_theme.rectangle([390, 10, 750, theme_h - 10], fill=(243, 243, 243, 255), outline=(180, 180, 180, 255))
    draw_theme.text((400, 20), "Windows 11 ライトモードタスクバー", fill=(30, 30, 30, 255), font=label_font)
    draw_theme.text((530, 42), "通常 (50/100%)", fill=(70, 70, 70, 255), font=sub_font)
    draw_theme.text((640, 42), "充電中 (50/100%)", fill=(180, 130, 0, 255), font=sub_font)

    for r_idx, (style_key, style_label) in enumerate(styles):
        ty = 65 + r_idx * 55
        # ダーク側
        draw_theme.text((20, ty + 10), style_label, fill=(200, 200, 200, 255), font=label_font)
        # ライト側
        draw_theme.text((400, ty + 10), style_label, fill=(40, 40, 40, 255), font=label_font)

        i50_norm = create_battery_icon(50, style=style_key, size=16, is_charging=False)
        i100_norm = create_battery_icon(100, style=style_key, size=16, is_charging=False)
        i50_chg = create_battery_icon(50, style=style_key, size=16, is_charging=True)
        i100_chg = create_battery_icon(100, style=style_key, size=16, is_charging=True)

        # ダーク側に合成
        theme_img.alpha_composite(i50_norm, (150, ty + 10))
        theme_img.alpha_composite(i100_norm, (180, ty + 10))
        theme_img.alpha_composite(i50_chg, (260, ty + 10))
        theme_img.alpha_composite(i100_chg, (290, ty + 10))

        # ライト側に合成
        theme_img.alpha_composite(i50_norm, (530, ty + 10))
        theme_img.alpha_composite(i100_norm, (560, ty + 10))
        theme_img.alpha_composite(i50_chg, (640, ty + 10))
        theme_img.alpha_composite(i100_chg, (670, ty + 10))

    path_theme = os.path.join(output_dir, "comparison_theme_dark_light.png")
    theme_img.save(path_theme)
    generated_files["theme_dark_light"] = path_theme

    return generated_files


if __name__ == "__main__":
    files = generate_all_previews()
    print("プレビュー画像生成完了:")
    for k, v in files.items():
        print(f"  {k}: {v}")
