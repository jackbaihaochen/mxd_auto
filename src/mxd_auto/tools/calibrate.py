"""标定工具(子命令式)。

用法:
    python -m mxd_auto.tools.calibrate screenshot [--title 标题子串]

后续阶段会陆续加入 template / minimap / platforms / preview 子命令。
"""

import argparse
import time
from pathlib import Path

import cv2
import numpy as np

from mxd_auto.capture import WindowCapture
from mxd_auto.config import CAPTURES_DIR, load_config


def save_image(image: np.ndarray, path: Path) -> None:
    """cv2.imwrite 不支持非 ASCII 路径,用 imencode + tofile 代替。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(path.suffix, image)
    if not ok:
        raise RuntimeError(f"图像编码失败: {path}")
    buf.tofile(str(path))


def cmd_screenshot(args: argparse.Namespace) -> None:
    title = args.title or load_config()["window_title"]
    with WindowCapture(title) as cap:
        left, top, width, height = cap.client_rect()
        print(f"窗口: {cap.title!r} (hwnd={cap.hwnd})")
        print(f"客户区: 左上 ({left}, {top}),大小 {width}x{height}")
        frame = cap.grab()
    out = CAPTURES_DIR / f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png"
    save_image(frame, out)
    print(f"已保存 {out} ({frame.shape[1]}x{frame.shape[0]})")


def main() -> None:
    parser = argparse.ArgumentParser(prog="calibrate", description="mxd_auto 标定工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_screenshot = sub.add_parser("screenshot", help="截取游戏客户区,验证截图链路")
    p_screenshot.add_argument("--title", help="窗口标题子串(默认读配置 window_title)")
    p_screenshot.set_defaults(func=cmd_screenshot)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
