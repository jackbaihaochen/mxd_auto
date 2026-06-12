"""mxd_auto 脚本入口。

用法:
    python -m mxd_auto.main

前置:已用 calibrate template/platforms 标定当前地图,配置 combat.map。
F12 紧急停止,F11 暂停/恢复。请先在安全地图验证。
"""

import functools
import threading

import keyboard

from mxd_auto.bot import Bot
from mxd_auto.capture import WindowCapture
from mxd_auto.config import ROOT, load_config
from mxd_auto.controller import Controller
from mxd_auto.detector import DEFAULT_THRESHOLD, find_monsters, load_templates
from mxd_auto.navigator import Navigator
from mxd_auto.terrain import load_platforms


def main() -> None:
    config = load_config()
    combat = config.get("combat") or {}
    map_name = combat.get("map")
    if not map_name:
        raise SystemExit("请先在 config.yaml 配置 combat.map(当前地图名)")

    templates = load_templates(ROOT / "templates" / map_name)
    platforms = load_platforms(ROOT / "maps" / f"{map_name}.yaml")
    print(f"地图 {map_name}: {len(templates)} 个模板(含镜像),{len(platforms)} 条平台线")

    method = (config.get("capture") or {}).get("method", "auto")
    cap = WindowCapture(config["window_title"], method=method)
    if cap.elevation_mismatch():
        raise SystemExit(
            "游戏以管理员运行而本脚本不是,按键会被 Windows 静默丢弃(UIPI)。\n"
            "请用管理员 PowerShell 重新运行:右键开始菜单 → Windows PowerShell(管理员)。"
        )
    print(f"抓图后端: {cap.method}")
    _, _, width, height = cap.client_rect()
    calibrated = config.get("calibrated_size")
    if calibrated and list(calibrated) != [width, height]:
        print(f"警告:当前客户区 {width}x{height} 与标定时 {calibrated} 不一致,模板匹配可能失效!")

    pos = (config.get("player") or {}).get("pos")
    player_pos = (int(pos[0]), int(pos[1])) if pos else (width // 2, round(height * 0.6))

    stop = threading.Event()
    pause = threading.Event()
    hotkeys = config.get("hotkeys") or {}
    keyboard.add_hotkey(hotkeys.get("stop", "f12"), stop.set)

    def toggle_pause() -> None:
        (pause.clear if pause.is_set() else pause.set)()
        print("[bot] 已暂停" if pause.is_set() else "[bot] 已恢复")

    keyboard.add_hotkey(hotkeys.get("pause", "f11"), toggle_pause)
    print(f"热键:{hotkeys.get('stop', 'f12')} 停止,{hotkeys.get('pause', 'f11')} 暂停/恢复")

    threshold = combat.get("match_threshold", DEFAULT_THRESHOLD)
    navigator = Navigator(
        platforms=platforms,
        attack_range_x=combat.get("attack_range_x", 120),
        attack_range_y=combat.get("attack_range_y", 40),
        max_walk_seconds=combat.get("max_walk_seconds", 3.0),
    )
    bot = Bot(
        controller=Controller(),
        navigator=navigator,
        detect=functools.partial(find_monsters, templates=templates, threshold=threshold),
        player_pos=player_pos,
        attack_key=config["keys"]["attack"],
        jump_key=config["keys"]["jump"],
        attack_presses=combat.get("attack_presses", 3),
    )

    print("请把焦点切到游戏窗口,Bot 开始运行…")
    try:
        bot.run(
            grab=cap.grab,
            is_foreground=cap.is_foreground,
            stop=stop,
            pause=pause,
            loop_interval=config.get("loop_interval", 0.1),
        )
    finally:
        cap.close()
    print("已停止")


if __name__ == "__main__":
    main()
