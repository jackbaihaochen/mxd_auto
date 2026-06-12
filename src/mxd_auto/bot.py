"""主循环:识怪 → 选目标 → 导航 → 攻击。

Bot.tick(frame) 每帧重评估;run() 负责抓屏循环、失焦保护与停止/暂停响应。
计时全用 time.monotonic(),等待用 stop.wait() 保证热键即时响应。
"""

import threading
import time
from typing import Callable, Sequence

import numpy as np

from mxd_auto.controller import Controller
from mxd_auto.detector import Detection, find_monsters
from mxd_auto.navigator import Decision, Navigator

DetectFn = Callable[[np.ndarray], Sequence[Detection]]


class Bot:
    def __init__(
        self,
        controller: Controller,
        navigator: Navigator,
        detect: DetectFn,
        player_pos: tuple[int, int],
        attack_key: str,
        jump_key: str,
        attack_presses: int = 3,
    ):
        self.controller = controller
        self.navigator = navigator
        self.detect = detect
        self.player_pos = player_pos
        self.attack_key = attack_key
        self.jump_key = jump_key
        self.attack_presses = attack_presses

    def tick(self, frame: np.ndarray, now: float | None = None) -> Decision:
        """识别一帧并执行决策;返回 Decision 供日志/测试。"""
        now = time.monotonic() if now is None else now
        detections = self.detect(frame)
        feet = [(d.center[0], d.y + d.h) for d in detections]  # 怪物脚底 = 框底边中点
        decision = self.navigator.decide(self.player_pos, feet, now)
        self._apply(decision)
        return decision

    def _apply(self, decision: Decision) -> None:
        if decision.action == "walk":
            other = "left" if decision.direction == "right" else "right"
            self.controller.release(other)
            self.controller.hold(decision.direction)
        elif decision.action == "attack":
            self._release_movement()
            self.controller.press(self.attack_key, presses=self.attack_presses)
        elif decision.action == "jump":
            self._release_movement()
            self.controller.press(self.jump_key)
        else:  # idle
            self._release_movement()

    def _release_movement(self) -> None:
        self.controller.release("left")
        self.controller.release("right")

    def run(
        self,
        grab: Callable[[], np.ndarray],
        is_foreground: Callable[[], bool],
        stop: threading.Event,
        pause: threading.Event,
        loop_interval: float = 0.1,
        log: Callable[[str], None] = print,
    ) -> None:
        last_reason = None
        try:
            while not stop.is_set():
                if pause.is_set() or not is_foreground():
                    self.controller.release_all()
                    stop.wait(0.3)
                    continue
                start = time.monotonic()
                decision = self.tick(grab(), start)
                if decision.reason != last_reason:
                    log(f"[bot] {decision.action} {decision.direction or ''} {decision.reason}")
                    last_reason = decision.reason
                remaining = loop_interval - (time.monotonic() - start)
                if remaining > 0:
                    stop.wait(remaining)
        finally:
            self.controller.release_all()
