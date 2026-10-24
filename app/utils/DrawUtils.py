# 官网：https://www.yuturuishi.com
# 微信：yuturuishi
# gitee开源地址：https://gitee.com/yuturuishi/rebucca
# github开源地址：https://github.com/yuturuishi/rebucca
"""OpenCV 图像文本绘制工具 —— 统一支持中文。

cv2.putText 只能渲染 ASCII，中文类别名（如「人」「公交车」）会显示成 ???。
本模块用 PIL + 项目内嵌中文字体（static/fonts/tsimhei.ttf）渲染文本后
贴回 OpenCV BGR 图像；字体不可用时退化为 ASCII 过滤 + cv2.putText，保证不崩溃。
"""
import logging
import os

logger = logging.getLogger("app.draw")

_cv2 = None
_np = None
_font_cache = {}
_font_failed = set()


def _lazy_cv():
    global _cv2, _np
    if _cv2 is None:
        import cv2
        import numpy as np
        _cv2 = cv2
        _np = np
    return _cv2, _np


def _project_root():
    try:
        from django.conf import settings
        base = str(getattr(settings, "BASE_DIR", "") or "")
    except Exception:
        base = ""
    if not base:
        # app/utils/DrawUtils.py -> 项目根
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return base


def _font_candidates():
    root = _project_root()
    return [
        os.path.join(root, "static", "fonts", "tsimhei.ttf"),  # 项目内嵌黑体（支持中文）
        r"C:\Windows\Fonts\msyh.ttc",       # Windows 微软雅黑
        r"C:\Windows\Fonts\simhei.ttf",     # Windows 黑体
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",       # Linux 文泉驿
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Linux Noto CJK
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",    # Linux 兜底（仅 ASCII）
    ]


def get_font(px=18):
    """按像素高度取缓存字体；全部失败返回 None。"""
    key = int(px)
    if key in _font_cache:
        return _font_cache[key]
    font = None
    try:
        from PIL import ImageFont
        for p in _font_candidates():
            if p in _font_failed:
                continue
            try:
                if os.path.isfile(p):
                    font = ImageFont.truetype(p, key)
                    break
            except Exception:
                _font_failed.add(p)
                continue
        if font is None:
            font = ImageFont.load_default()
    except Exception as e:
        logger.warning("get_font(%s) 失败: %s" % (px, e))
        font = None
    _font_cache[key] = font
    return font


def _is_ascii(s):
    try:
        return s.isascii()
    except Exception:
        return all(ord(c) < 128 for c in s)


def _text_size(txt, font):
    """测量文本像素尺寸，返回 (tw, th, off_y)；off_y 为 textbbox 顶部偏移补偿。"""
    from PIL import Image, ImageDraw
    _d = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    try:
        l, t, r, b = _d.textbbox((0, 0), txt, font=font)
        return r - l, b - t, -t
    except Exception:
        tw, th = _d.textsize(txt, font=font)
        return tw, th, 0


def put_text(img, txt, org, color=(255, 255, 255), font_px=18, bg=None, padding=2):
    """在 BGR 图像上绘制文本（支持中文），返回绘制后的图像。

    性能：仅对文字所在的 ROI 小区域做 PIL 往返，不整帧转换
    （1080p 整帧往返约数十 ms，ROI 通常 <100x30，快两个数量级）。

    参数：
      img     : numpy BGR 图像（ROI 区域会被原地修改并返回）
      txt     : 文本（str，可含中文）
      org     : (x, y) 文本左上角
      color   : 文字颜色，BGR 元组
      font_px : 字体像素高度
      bg      : 底色矩形 BGR 元组；None 不画底色
      padding : 底色矩形内边距
    """
    cv2, np = _lazy_cv()
    txt = str(txt or "")
    if not txt:
        return img
    font = get_font(font_px)
    # 字体不可用：ASCII 兜底（中文替换为 ?），绝不让 putText 抛异常
    if font is None:
        safe = txt if _is_ascii(txt) else "".join(c if ord(c) < 128 else "?" for c in txt)
        cv2.putText(img, safe, (int(org[0]), int(org[1]) + font_px),
                    cv2.FONT_HERSHEY_SIMPLEX, max(0.4, font_px / 28.0),
                    color, 1, cv2.LINE_AA)
        return img
    try:
        from PIL import Image, ImageDraw
        x, y = int(org[0]), int(org[1])
        tw, th, off_y = _text_size(txt, font)
        h, w = img.shape[:2]
        # ROI：文字 + 底色边距，裁到图像范围内
        rx1 = max(0, x)
        ry1 = max(0, y)
        rx2 = min(w, x + tw + padding * 2)
        ry2 = min(h, y + th + padding * 2)
        if rx2 <= rx1 or ry2 <= ry1:
            return img
        roi = img[ry1:ry2, rx1:rx2]
        pil = Image.fromarray(cv2.cvtColor(roi, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil)
        if bg is not None:
            draw.rectangle([x - rx1, y - ry1,
                            x - rx1 + tw + padding * 2, y - ry1 + th + padding * 2],
                           fill=(int(bg[2]), int(bg[1]), int(bg[0])))
        draw.text((x + padding - rx1, y + padding + off_y - ry1), txt, font=font,
                  fill=(int(color[2]), int(color[1]), int(color[0])))
        img[ry1:ry2, rx1:rx2] = cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)
        return img
    except Exception as e:
        logger.warning("put_text 绘制失败，退化为 ASCII: %s" % e)
        safe = txt if _is_ascii(txt) else "".join(c if ord(c) < 128 else "?" for c in txt)
        cv2.putText(img, safe, (int(org[0]), int(org[1]) + font_px),
                    cv2.FONT_HERSHEY_SIMPLEX, max(0.4, font_px / 28.0),
                    color, 1, cv2.LINE_AA)
        return img


def draw_box_label(img, txt, box, color=(220, 38, 38), font_px=18):
    """在检测框上方绘制「底色矩形 + 文本」标签（支持中文），返回绘制后的图像。

    box: [x1, y1, x2, y2]；标签底色与框色一致，文字白色。
    """
    cv2, _ = _lazy_cv()
    txt = str(txt or "").strip()
    if not txt:
        return img
    x1, y1 = int(box[0]), int(box[1])
    # 先量尺寸定标签纵向位置
    font = get_font(font_px)
    th = font_px
    if font is not None:
        try:
            _, th, _ = _text_size(txt, font)
        except Exception:
            th = font_px
    ty = max(0, y1 - th - 8)
    return put_text(img, txt, (x1, ty), color=(255, 255, 255), font_px=font_px,
                    bg=(int(color[0]), int(color[1]), int(color[2])), padding=3)
