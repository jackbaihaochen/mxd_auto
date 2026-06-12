"""标定工具(子命令式)。

用法:
    python -m mxd_auto.tools.calibrate screenshot [--title 标题子串]
    python -m mxd_auto.tools.calibrate template <地图名>
    python -m mxd_auto.tools.calibrate platforms <地图名> [--image 截图路径]
    python -m mxd_auto.tools.calibrate preview [--image 截图路径] [--map 地图名]

后续阶段会陆续加入 minimap 子命令。
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
    load_templates,
)
from mxd_auto.terrain import (
    Platform,
    detect_platform_candidates,
    load_platforms,
    save_platforms,
)

TEMPLATES_DIR = ROOT / "templates"
MAPS_DIR = ROOT / "maps"


def default_player_pos(width: int, height: int) -> tuple[int, int]:
    """镜头跟随时角色在客户区的位置:水平居中、垂直中心偏下。"""
    return width // 2, round(height * 0.6)


def get_player_pos(config: dict, width: int, height: int) -> tuple[int, int]:
    pos = (config.get("player") or {}).get("pos")
    if pos:
        return int(pos[0]), int(pos[1])
    return default_player_pos(width, height)


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


def draw_platforms(canvas: np.ndarray, platforms: list[Platform], color=(255, 128, 0)) -> None:
    for p in platforms:
        cv2.line(canvas, (p.x1, p.y), (p.x2, p.y), color, 2)
        cv2.circle(canvas, (p.x1, p.y), 4, color, -1)
        cv2.circle(canvas, (p.x2, p.y), 4, color, -1)


class PlatformEditor:
    """鼠标交互编辑平台线:左键拖拽画线,右键删除最近的线。"""

    CLICK_DELETE_DISTANCE = 10

    def __init__(self, frame: np.ndarray, platforms: list[Platform]):
        self.frame = frame
        self.platforms = platforms
        self.drag_start: tuple[int, int] | None = None
        self.drag_now: tuple[int, int] | None = None

    def on_mouse(self, event: int, x: int, y: int, _flags: int, _param) -> None:
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drag_start = (x, y)
            self.drag_now = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and self.drag_start:
            self.drag_now = (x, y)
        elif event == cv2.EVENT_LBUTTONUP and self.drag_start:
            x0, y0 = self.drag_start
            if abs(x - x0) >= 10:  # 拖拽足够长才算画线,y 取按下点(强制水平)
                self.platforms.append(Platform(x0, x, y0))
            self.drag_start = self.drag_now = None
        elif event == cv2.EVENT_RBUTTONDOWN:
            self._delete_near(x, y)

    def _delete_near(self, x: int, y: int) -> None:
        def distance(p: Platform) -> float:
            dx = max(p.x1 - x, 0, x - p.x2)
            return (dx**2 + (p.y - y) ** 2) ** 0.5

        if self.platforms:
            nearest = min(self.platforms, key=distance)
            if distance(nearest) <= self.CLICK_DELETE_DISTANCE:
                self.platforms.remove(nearest)

    def render(self) -> np.ndarray:
        canvas = self.frame.copy()
        draw_platforms(canvas, self.platforms)
        if self.drag_start and self.drag_now:
            cv2.line(canvas, self.drag_start, (self.drag_now[0], self.drag_start[1]), (0, 255, 255), 2)
        cv2.putText(
            canvas,
            f"platforms: {len(self.platforms)}  [drag]=add  [right-click]=del  [s]=save  [q]=quit",
            (8, 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 255),
            2,
        )
        return canvas


def cmd_platforms(args: argparse.Namespace) -> None:
    config = load_config()
    if args.image:
        frame = imread_bgr(Path(args.image))
    else:
        with WindowCapture(config["window_title"]) as cap:
            frame = cap.grab()
    candidates = detect_platform_candidates(frame)
    print(f"自动检测到 {len(candidates)} 条平台候选线(仅供参考,请人工修正)")
    print("操作:左键拖拽补画平台线;右键点线附近删除;s 保存退出;q/Esc 放弃")

    editor = PlatformEditor(frame, list(candidates))
    cv2.namedWindow("platforms")
    cv2.setMouseCallback("platforms", editor.on_mouse)
    while True:
        cv2.imshow("platforms", editor.render())
        key = cv2.waitKey(30) & 0xFF
        if key == ord("s"):
            out = MAPS_DIR / f"{args.map}.yaml"
            save_platforms(out, editor.platforms, (frame.shape[1], frame.shape[0]))
            print(f"已保存 {len(editor.platforms)} 条平台线到 {out}")
            break
        if key in (27, ord("q")):
            print("已放弃,未保存")
            break
    cv2.destroyAllWindows()


def cmd_preview(args: argparse.Namespace) -> None:
    config = load_config()
    combat = config.get("combat", {})
    map_name = args.map or combat.get("map")
    if not map_name:
        raise SystemExit("请用 --map 指定地图名,或在配置 combat.map 中设置")
    threshold = combat.get("match_threshold", DEFAULT_THRESHOLD)
    templates = load_templates(TEMPLATES_DIR / map_name)
    print(f"已加载 {len(templates)} 个模板(含镜像),阈值 {threshold}")

    map_file = MAPS_DIR / f"{map_name}.yaml"
    platforms = load_platforms(map_file) if map_file.exists() else []
    print(f"已加载 {len(platforms)} 条平台线" if platforms else f"无平台数据({map_file} 不存在)")

    def annotate(frame: np.ndarray, detections: list[Detection]) -> np.ndarray:
        canvas = draw_detections(frame, detections)
        draw_platforms(canvas, platforms)
        px, py = get_player_pos(config, frame.shape[1], frame.shape[0])
        cv2.drawMarker(canvas, (px, py), (0, 0, 255), cv2.MARKER_CROSS, 16, 2)
        return canvas

    if args.image:
        frame = imread_bgr(Path(args.image))
        detections = find_monsters(frame, templates, threshold)
        for d in detections:
            print(f"  {d.template} score={d.score:.3f} at ({d.x},{d.y}) {d.w}x{d.h}")
        cv2.imshow("preview", annotate(frame, detections))
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
            canvas = annotate(frame, detections)
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

    p_platforms = sub.add_parser("platforms", help="标定平台线(自动检测 + 人工修正)")
    p_platforms.add_argument("map", help="地图名(存到 maps/<地图名>.yaml)")
    p_platforms.add_argument("--image", help="对静态截图标定,而不是实时抓屏")
    p_platforms.set_defaults(func=cmd_platforms)

    p_preview = sub.add_parser("preview", help="实时预览怪物识别+平台线+玩家点(不按任何键)")
    p_preview.add_argument("--image", help="对静态截图运行识别,而不是实时抓屏")
    p_preview.add_argument("--map", help="地图名(默认读配置 combat.map)")
    p_preview.set_defaults(func=cmd_preview)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
