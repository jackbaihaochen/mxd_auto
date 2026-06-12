"""标定工具(子命令式)。

用法:
    python -m mxd_auto.tools.calibrate screenshot [--title 标题子串]
    python -m mxd_auto.tools.calibrate template <地图名>
    python -m mxd_auto.tools.calibrate preview [--image 截图路径] [--map 地图名]

后续阶段会陆续加入 minimap / platforms 子命令。
"""

import argparse
import time
from pathlib import Path

import cv2
import numpy as np

from mxd_auto.capture import WindowCapture
from mxd_auto.config import ROOT, CAPTURES_DIR, load_config
from mxd_auto.detector import (
    DEFAULT_THRESHOLD,
    Detection,
    find_monsters,
    imread_gray,
    load_templates,
)

TEMPLATES_DIR = ROOT / "templates"


def save_image(image: np.ndarray, path: Path) -> None:
    """cv2.imwrite 不支持非 ASCII 路径,用 imencode + tofile 代替。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(path.suffix, image)
    if not ok:
        raise RuntimeError(f"图像编码失败: {path}")
    buf.tofile(str(path))


def imread_bgr(path: Path) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"无法解码图像: {path}")
    return img


def draw_detections(frame: np.ndarray, detections: list[Detection]) -> np.ndarray:
    canvas = frame.copy()
    for d in detections:
        cv2.rectangle(canvas, (d.x, d.y), (d.x + d.w, d.y + d.h), (0, 255, 0), 2)
        cv2.putText(
            canvas,
            f"{d.template} {d.score:.2f}",
            (d.x, max(12, d.y - 4)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 0),
            1,
        )
    return canvas


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


def cmd_template(args: argparse.Namespace) -> None:
    config = load_config()
    out_dir = TEMPLATES_DIR / args.map
    out_dir.mkdir(parents=True, exist_ok=True)
    print("操作说明:每轮重新抓一帧 → 鼠标框住一只怪 → 空格/回车确认保存;")
    print("不框直接空格/回车(或按 c 取消)结束。窗口标题: select monster")
    saved = 0
    with WindowCapture(config["window_title"]) as cap:
        while True:
            frame = cap.grab()
            x, y, w, h = cv2.selectROI("select monster", frame, showCrosshair=True)
            if w == 0 or h == 0:
                break
            crop = frame[y : y + h, x : x + w]
            idx = 1
            while (out_dir / f"monster_{idx:02d}.png").exists():
                idx += 1
            out = out_dir / f"monster_{idx:02d}.png"
            save_image(crop, out)
            saved += 1
            print(f"已保存 {out} ({w}x{h})")
    cv2.destroyAllWindows()
    print(f"共保存 {saved} 张模板到 {out_dir}")


def cmd_preview(args: argparse.Namespace) -> None:
    config = load_config()
    combat = config.get("combat", {})
    map_name = args.map or combat.get("map")
    if not map_name:
        raise SystemExit("请用 --map 指定地图名,或在配置 combat.map 中设置")
    threshold = combat.get("match_threshold", DEFAULT_THRESHOLD)
    templates = load_templates(TEMPLATES_DIR / map_name)
    print(f"已加载 {len(templates)} 个模板(含镜像),阈值 {threshold}")

    if args.image:
        frame = imread_bgr(Path(args.image))
        detections = find_monsters(frame, templates, threshold)
        for d in detections:
            print(f"  {d.template} score={d.score:.3f} at ({d.x},{d.y}) {d.w}x{d.h}")
        cv2.imshow("preview", draw_detections(frame, detections))
        print("按任意键退出")
        cv2.waitKey(0)
        cv2.destroyAllWindows()
        return

    print("实时预览中,按 q 或 Esc 退出(本工具不会按任何游戏键)")
    with WindowCapture(config["window_title"]) as cap:
        while True:
            start = time.monotonic()
            frame = cap.grab()
            detections = find_monsters(frame, templates, threshold)
            canvas = draw_detections(frame, detections)
            elapsed_ms = (time.monotonic() - start) * 1000
            cv2.putText(
                canvas,
                f"{len(detections)} hits, {elapsed_ms:.0f} ms",
                (8, 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 255),
                1,
            )
            cv2.imshow("preview", canvas)
            key = cv2.waitKey(50) & 0xFF
            if key in (27, ord("q")):
                break
    cv2.destroyAllWindows()


def main() -> None:
    parser = argparse.ArgumentParser(prog="calibrate", description="mxd_auto 标定工具")
    sub = parser.add_subparsers(dest="command", required=True)

    p_screenshot = sub.add_parser("screenshot", help="截取游戏客户区,验证截图链路")
    p_screenshot.add_argument("--title", help="窗口标题子串(默认读配置 window_title)")
    p_screenshot.set_defaults(func=cmd_screenshot)

    p_template = sub.add_parser("template", help="框选怪物,保存模板图到 templates/<地图名>/")
    p_template.add_argument("map", help="地图名(模板目录名)")
    p_template.set_defaults(func=cmd_template)

    p_preview = sub.add_parser("preview", help="实时预览怪物识别结果(不按任何键)")
    p_preview.add_argument("--image", help="对静态截图运行识别,而不是实时抓屏")
    p_preview.add_argument("--map", help="地图名(默认读配置 combat.map)")
    p_preview.set_defaults(func=cmd_preview)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
