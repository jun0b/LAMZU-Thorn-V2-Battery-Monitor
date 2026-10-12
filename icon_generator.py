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


def get_font(size: int) -> ImageFont.ImageFont:
    """指定されたピクセルサイズに最適なフォントを取得"""
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


def get_battery_color(percent: Optional[int]) -> Tuple[int, int, int]:
    """残量パーセンテージに応じた色を返却 (RGB)

    - 51〜100%: 通常色 (緑系 #2ECC71)
    - 21〜50% : 注意色 (橙系 #F39C12)
    - 0〜20%  : 警告色 (赤系 #E74C3C)
    - 未取得  : 灰色 (#95A5A6)
    """
    if percent is None:
        return (149, 165, 166)  # 灰色
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


def create_battery_icon(
    percent: Optional[int],
    style: str = "numbers-battery",
    size: int = 16,
    is_stale: bool = False,
    is_disconnected: bool = False
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

    Returns:
        Image.Image: RGBA形式のPillowイメージオブジェクト
    """
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # 状態に応じたゲージ色 (全スタイル共通の統一しきい値)
    # 51〜100%: 緑, 21〜50%: 橙, 0〜20%: 赤, 未取得: 灰
    base_color = get_battery_color(percent)
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

    if norm_style == "numbers-only":
        # ==========================================
        # 1. 数字のみ：バッテリー形状なし、残量数値のみを最大化
        # ==========================================
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

        # 16x16px枠およびアウトライン(左右1px)が完全にはみ出ないよう自動縮小
        while (tw + 2 > size) and font_size > 5:
            font_size -= 1
            font = get_font(font_size)
            bbox = font.getbbox(text)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]

        tx = (size - tw) // 2 - bbox[0]
        ty = (size - th) // 2 - bbox[1]

        # ダーク・ライト両方のタスクバーで判読できるよう黒の全方位アウトラインを付与
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
    """3種類の全パターンの比較用サンプル画像を生成して保存する

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
    percents = [9, 10, 20, 50, 98, 99, 100, None]
    sizes = [16, 20, 24, 32]

    # 旧プレビュー画像（旧A1/A2/A3等）の整理
    obsolete_prefixes = [
        "icon_top_", "icon_bottom_", "icon_overlay_",
        "icon_top-a1_", "icon_top-a2_", "icon_top-a3_",
        "icon_numbers-only_", "icon_battery-only_", "comparison_a_variants.png"
    ]
    for fname in os.listdir(output_dir):
        if any(fname.startswith(prefix) for prefix in obsolete_prefixes) or fname == "comparison_a_variants.png":
            try:
                os.remove(os.path.join(output_dir, fname))
            except Exception:
                pass

    # 1. 各案・各残量の個別PNG (16x16px) の出力 (形式: icon_<style_slug>_<pct>pct_16px.png)
    for style_key, _ in styles:
        style_slug = style_key.replace("-", "_")
        for p in percents:
            p_str = f"{p}pct" if p is not None else "unknown"
            filename = f"icon_{style_slug}_{p_str}_16px.png"
            filepath = os.path.join(output_dir, filename)
            img = create_battery_icon(p, style=style_key, size=16)
            img.save(filepath)

    # 2. 全3案 横並び比較画像 (16x16px 実寸シート & ラベル付き)
    cell_w = 48
    cell_h = 36
    margin_left = 200
    margin_top = 40
    img_w = margin_left + len(percents) * cell_w + 20
    img_h = margin_top + len(styles) * cell_h + 20

    comp_16 = Image.new("RGBA", (img_w, img_h), (30, 32, 36, 255))
    draw_comp = ImageDraw.Draw(comp_16)
    label_font = get_font(12)

    # 列ヘッダー (パーセンテージ)
    for col_idx, p in enumerate(percents):
        header_text = f"{p}%" if p is not None else "未取得"
        bbox = label_font.getbbox(header_text)
        hx = margin_left + col_idx * cell_w + (cell_w - (bbox[2] - bbox[0])) // 2
        draw_comp.text((hx, 15), header_text, fill=(200, 205, 215, 255), font=label_font)

    # 各行の描画
    for row_idx, (style_key, style_label) in enumerate(styles):
        row_y = margin_top + row_idx * cell_h
        # 行ラベル
        draw_comp.text((15, row_y + 10), style_label, fill=(255, 255, 255, 255), font=label_font)

        for col_idx, p in enumerate(percents):
            icon_x = margin_left + col_idx * cell_w + (cell_w - 16) // 2
            icon_y = row_y + (cell_h - 16) // 2
            # アイコン背景枠（視認用）
            draw_comp.rectangle([icon_x - 2, icon_y - 2, icon_x + 17, icon_y + 17], outline=(60, 64, 72, 255))
            icon_img = create_battery_icon(p, style=style_key, size=16)
            comp_16.alpha_composite(icon_img, (icon_x, icon_y))

    path_comp_16 = os.path.join(output_dir, "comparison_all_styles_16px.png")
    comp_16.save(path_comp_16)
    generated_files["comparison_16px"] = path_comp_16

    # 3. 16x16pxのNearest Neighbor 8倍拡大画像 (ピクセル精査用)
    zoom_factor = 8
    zoom_w = img_w * zoom_factor
    zoom_h = img_h * zoom_factor
    zoom_img = comp_16.resize((zoom_w, zoom_h), Image.Resampling.NEAREST)
    path_zoom = os.path.join(output_dir, "preview_16px_pixel_zoom_8x.png")
    zoom_img.save(path_zoom)
    generated_files["zoom_8x"] = path_zoom

    # 4. 99% と 100% の視認性特化比較シート (3スタイル版)
    spec_w = 640
    spec_h = 60 + len(styles) * 40
    spec_img = Image.new("RGBA", (spec_w, spec_h), (25, 27, 30, 255))
    spec_draw = ImageDraw.Draw(spec_img)
    spec_draw.text((20, 15), "99% vs 100% 視認性・クリッピング比較シート (実寸 & 4倍拡大)", fill=(255, 255, 255, 255), font=label_font)
    spec_draw.text((260, 40), "99% (実寸/4x)", fill=(200, 205, 215, 255), font=label_font)
    spec_draw.text((440, 40), "100% (実寸/4x)", fill=(200, 205, 215, 255), font=label_font)

    for r_i, (st_k, st_lbl) in enumerate(styles):
        ry = 65 + r_i * 40
        spec_draw.text((20, ry + 8), st_lbl, fill=(240, 240, 240, 255), font=label_font)

        img99 = create_battery_icon(99, style=st_k, size=16)
        img99_4x = img99.resize((32, 32), Image.Resampling.NEAREST)
        spec_img.alpha_composite(img99, (270, ry + 8))
        spec_img.alpha_composite(img99_4x, (300, ry))

        img100 = create_battery_icon(100, style=st_k, size=16)
        img100_4x = img100.resize((32, 32), Image.Resampling.NEAREST)
        spec_img.alpha_composite(img100, (450, ry + 8))
        spec_img.alpha_composite(img100_4x, (480, ry))

    path_99_100 = os.path.join(output_dir, "comparison_99_100.png")
    spec_img.save(path_99_100)
    generated_files["comparison_99_100"] = path_99_100

    # 5. マルチサイズ比較画像 (16, 20, 24, 32px)
    ms_w = 720
    ms_h = 70 + len(styles) * 65
    ms_img = Image.new("RGBA", (ms_w, ms_h), (30, 32, 36, 255))
    draw_ms = ImageDraw.Draw(ms_img)

    draw_ms.text((20, 15), "各解像度での視認性比較 (16px, 20px, 24px, 32px)", fill=(255, 255, 255, 255), font=label_font)

    # ヘッダー (サイズ)
    x_offsets = [230, 330, 450, 580]
    for idx, sz in enumerate(sizes):
        draw_ms.text((x_offsets[idx], 40), f"{sz}×{sz}px", fill=(200, 205, 215, 255), font=label_font)

    for row_idx, (style_key, style_label) in enumerate(styles):
        ry = 70 + row_idx * 65
        draw_ms.text((15, ry + 15), style_label, fill=(255, 255, 255, 255), font=label_font)

        for col_idx, sz in enumerate(sizes):
            cx = x_offsets[col_idx]
            img_98 = create_battery_icon(98, style=style_key, size=sz)
            img_100 = create_battery_icon(100, style=style_key, size=sz)

            draw_ms.rectangle([cx - 2, ry - 2, cx + sz + 1, ry + sz + 1], outline=(55, 60, 68, 255))
            draw_ms.rectangle([cx + sz + 8, ry - 2, cx + sz * 2 + 11, ry + sz + 1], outline=(55, 60, 68, 255))

            ms_img.alpha_composite(img_98, (cx, ry))
            ms_img.alpha_composite(img_100, (cx + sz + 10, ry))

            draw_ms.text((cx + 1, ry + sz + 4), "98%", fill=(150, 155, 165, 255), font=get_font(9))
            draw_ms.text((cx + sz + 9, ry + sz + 4), "100%", fill=(150, 155, 165, 255), font=get_font(9))

    path_ms = os.path.join(output_dir, "comparison_multisize.png")
    ms_img.save(path_ms)
    generated_files["multisize"] = path_ms

    # 6. ダークモード・ライトモードタスクバー背景での見え方比較画像
    theme_w = 700
    theme_h = 60 + len(styles) * 45
    theme_img = Image.new("RGBA", (theme_w, theme_h), (20, 20, 20, 255))
    draw_theme = ImageDraw.Draw(theme_img)

    # 左半分: Windows Dark Mode タスクバー色 (#202020)
    draw_theme.rectangle([10, 10, 340, theme_h - 10], fill=(32, 32, 32, 255), outline=(60, 60, 60, 255))
    draw_theme.text((20, 20), "Windows 11 ダークモードタスクバー", fill=(255, 255, 255, 255), font=label_font)

    # 右半分: Windows Light Mode タスクバー色 (#F3F3F3)
    draw_theme.rectangle([360, 10, 690, theme_h - 10], fill=(243, 243, 243, 255), outline=(180, 180, 180, 255))
    draw_theme.text((370, 20), "Windows 11 ライトモードタスクバー", fill=(30, 30, 30, 255), font=label_font)

    for r_idx, (style_key, style_label) in enumerate(styles):
        ty = 50 + r_idx * 45
        # ダーク側
        draw_theme.text((20, ty + 10), style_label, fill=(200, 200, 200, 255), font=label_font)
        # ライト側
        draw_theme.text((370, ty + 10), style_label, fill=(40, 40, 40, 255), font=label_font)

        icon_98 = create_battery_icon(98, style=style_key, size=16)
        icon_20 = create_battery_icon(20, style=style_key, size=16)
        icon_98_32 = create_battery_icon(98, style=style_key, size=32)

        # ダーク側に合成
        theme_img.alpha_composite(icon_98, (160, ty + 10))
        theme_img.alpha_composite(icon_20, (190, ty + 10))
        theme_img.alpha_composite(icon_98_32, (230, ty + 2))

        # ライト側に合成
        theme_img.alpha_composite(icon_98, (510, ty + 10))
        theme_img.alpha_composite(icon_20, (540, ty + 10))
        theme_img.alpha_composite(icon_98_32, (580, ty + 2))

    path_theme = os.path.join(output_dir, "comparison_theme_dark_light.png")
    theme_img.save(path_theme)
    generated_files["theme_dark_light"] = path_theme

    return generated_files


if __name__ == "__main__":
    files = generate_all_previews()
    print("生成完了:")
    for k, v in files.items():
        print(f"  {k}: {v}")
