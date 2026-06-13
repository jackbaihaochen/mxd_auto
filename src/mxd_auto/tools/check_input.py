"""阶段 4 验证脚本:按键链路 + 紧急停止。

用法:
    python -m mxd_auto.tools.check_input              # 完整测试:走/跳/攻击循环
    python -m mxd_auto.tools.check_input --key altright --times 3   # 单键测试

完整模式:切到游戏窗口后,角色循环:右走 1 秒 → 左走 1 秒 → 跳 → 攻击 3 次。
单键模式:每秒点按一次指定键,肉眼核对游戏内效果(核对键位用)。
F12 随时立停(松开所有键),30 秒后自动结束。请在安全地图测试。
"""

import argparse
import threading
import time

import keyboard

from mxd_auto.capture import WindowCapture
from mxd_auto.config import load_config
from mxd_auto.controller import Controller, is_known_key

def main() -> None:
    parser = argparse.ArgumentParser(description="按键链路验证")
    parser.add_argument("--key", help="只测这个键(每秒点按一次)")
    parser.add_argument("--times", type=int, default=3, help="单键模式点按次数(默认 3)")
    args = parser.parse_args()

    config = load_config()
    keys = config["keys"]
    unknown = [f"{name}: {key}" for name, key in keys.items() if not is_known_key(str(key))]
    if unknown:
        raise SystemExit("config.yaml 里有未知键名(可用键名见 controller._SCANCODES):" + ", ".join(unknown))
    if args.key and not is_known_key(args.key):
        raise SystemExit(f"未知键名 {args.key!r}")

    hotkey_stop = (config.get("hotkeys") or {}).get("stop", "f12")
    stop = threading.Event()
    keyboard.add_hotkey(hotkey_stop, stop.set)
    print(f"紧急停止热键: {hotkey_stop}")

    method = (config.get("capture") or {}).get("method", "auto")
    cap = WindowCapture(config["window_title"], method=method)
    if cap.elevation_mismatch():
        raise SystemExit(
            "游戏以管理员运行而本脚本不是,按键会被 Windows 静默丢弃(UIPI)。\n"
            "请用管理员 PowerShell 重新运行:右键开始菜单 → Windows PowerShell(管理员)。"
        )
    print(f"找到窗口 {cap.title!r},正在把游戏拉到前台…")
    cap.bring_to_foreground()
    deadline = time.monotonic() + 10
    while not cap.is_foreground():
        if stop.is_set() or time.monotonic() > deadline:
            print("未获得焦点或已停止,退出")
            return
        print("请点击游戏窗口使其获得焦点…")
        time.sleep(1.0)

    controller = Controller()
    try:
        if args.key:
            print(f"单键测试: {args.key} x{args.times},观察游戏内效果")
            for i in range(args.times):
                if stop.is_set():
                    break
                print(f"  按下 {args.key} ({i + 1}/{args.times})")
                controller.press(args.key)
                stop.wait(1.0)
        else:
            run_full_loop(controller, cap, keys, stop)
    finally:
        controller.release_all()
        cap.close()
    print("已停止(热键)" if stop.is_set() else "测试结束")

def run_full_loop(controller: Controller, cap: WindowCapture, keys: dict, stop: threading.Event) -> None:
    print("开始测试,按 F12 停止")

    def walk(key: str, seconds: float) -> None:
        print(f"  按住 {key} {seconds}s")
        controller.hold(key)
        stop.wait(seconds)  # stop 触发立即返回,不用死板 sleep
        controller.release(key)

    while not stop.is_set():
        if not cap.is_foreground():
            controller.release_all()
            print("  窗口失焦,暂停(点回游戏窗口继续)")
            time.sleep(0.5)
            continue
        for i in range(100):
            walk("right", 0.1)
            if stop.is_set():
                break
            print(f"  攻击 ({keys['attack']})")
            controller.press(keys["attack"], presses=1)
            stop.wait(0.1)
        for i in range(100):
            walk("left", 0.1)
            if stop.is_set():
                break
            print(f"  攻击 ({keys['attack']})")
            controller.press(keys["attack"], presses=1)
            stop.wait(0.1)


if __name__ == "__main__":
    main()
