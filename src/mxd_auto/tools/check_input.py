"""阶段 4 验证脚本:按键链路 + 紧急停止。

用法:
    python -m mxd_auto.tools.check_input

启动后切到游戏窗口,角色会循环:右走 1 秒 → 左走 1 秒 → 跳 → 攻击 3 次。
F12 随时立停(松开所有键),30 秒后自动结束。请在安全地图测试。
"""

import threading
import time

import keyboard

from mxd_auto.capture import WindowCapture
from mxd_auto.config import load_config
from mxd_auto.controller import Controller

MAX_RUN_SECONDS = 30


def main() -> None:
    config = load_config()
    keys = config["keys"]
    hotkey_stop = (config.get("hotkeys") or {}).get("stop", "f12")

    stop = threading.Event()
    keyboard.add_hotkey(hotkey_stop, stop.set)
    print(f"紧急停止热键: {hotkey_stop}")

    cap = WindowCapture(config["window_title"])
    print(f"找到窗口 {cap.title!r},请在 10 秒内点击游戏窗口使其获得焦点…")
    deadline = time.monotonic() + 10
    while not cap.is_foreground():
        if stop.is_set() or time.monotonic() > deadline:
            print("未获得焦点或已停止,退出")
            return
        time.sleep(0.2)
    print(f"开始测试,{hotkey_stop} 立停,{MAX_RUN_SECONDS} 秒后自动结束")

    controller = Controller()
    end = time.monotonic() + MAX_RUN_SECONDS

    def walk(key: str, seconds: float) -> None:
        print(f"  按住 {key} {seconds}s")
        controller.hold(key)
        stop.wait(seconds)  # stop 触发立即返回,不用死板 sleep
        controller.release(key)

    try:
        while not stop.is_set() and time.monotonic() < end:
            if not cap.is_foreground():
                controller.release_all()
                print("  窗口失焦,暂停(点回游戏窗口继续)")
                time.sleep(0.5)
                continue
            walk("right", 1.0)
            if stop.is_set():
                break
            walk("left", 1.0)
            if stop.is_set():
                break
            print(f"  跳跃 ({keys['jump']})")
            controller.press(keys["jump"])
            stop.wait(0.5)
            print(f"  攻击 ({keys['attack']}) x3")
            controller.press(keys["attack"], presses=3)
            stop.wait(0.5)
    finally:
        controller.release_all()
        cap.close()
    print("已停止(F12)" if stop.is_set() else "测试结束")


if __name__ == "__main__":
    main()
