"""移动决策(纯逻辑,不碰按键/截图)。

每帧输入玩家与怪物的脚底坐标,输出一个动作意图(Decision),由 Bot 执行:
- 同平台有怪:不在攻击范围 → 朝它走;走太久没接近 → 跳一下防卡墙;进范围 → 攻击
- 同平台无怪:平台内左右巡逻,靠近端点折返
v1 只做同平台,跨平台导航(上跳/下跳/绳索)留给后续版本。
"""

from dataclasses import dataclass
from typing import Literal, Sequence

from mxd_auto.terrain import DEFAULT_Y_TOLERANCE, Platform, platform_of

# 巡逻折返:距平台端点该像素内就掉头
PATROL_EDGE_MARGIN = 40

Action = Literal["walk", "attack", "jump", "idle"]
Direction = Literal["left", "right"]


@dataclass(frozen=True)
class Decision:
    action: Action
    direction: Direction | None = None
    reason: str = ""


@dataclass(frozen=True)
class Target:
    x: int
    y: int


class Navigator:
    def __init__(
        self,
        platforms: Sequence[Platform],
        attack_range_x: int,
        attack_range_y: int,
        max_walk_seconds: float,
        y_tolerance: int = DEFAULT_Y_TOLERANCE,
    ):
        self.platforms = list(platforms)
        self.attack_range_x = attack_range_x
        self.attack_range_y = attack_range_y
        self.max_walk_seconds = max_walk_seconds
        self.y_tolerance = y_tolerance
        self.patrol_direction: Direction = "right"
        self._walk_direction: Direction | None = None
        self._walk_started: float | None = None

    def decide(
        self,
        player: tuple[int, int],
        monsters: Sequence[tuple[int, int]],
        now: float,
    ) -> Decision:
        """player/monsters 均为脚底坐标(x, y),now 为 time.monotonic()。"""
        platform = platform_of(player, self.platforms, self.y_tolerance)
        if platform is None:
            # 跳跃/下落中或站在未标定区域:松键等落地,别乱动
            self._reset_walk()
            return Decision("idle", reason="玩家不在任何已标定平台上")

        target = self._pick_target(platform, player[0], monsters)
        if target is None:
            return self._patrol(player, platform, now)

        dx = target.x - player[0]
        if abs(dx) <= self.attack_range_x and abs(target.y - player[1]) <= self.attack_range_y:
            self._reset_walk()
            return Decision("attack", reason=f"目标进入攻击范围 dx={dx}")

        direction: Direction = "right" if dx > 0 else "left"
        if self._walk_too_long(direction, now):
            return Decision("jump", reason=f"朝 {direction} 走超 {self.max_walk_seconds}s 未接近,跳一下防卡墙")
        return Decision("walk", direction, reason=f"追击目标 dx={dx}")

    def _pick_target(
        self, platform: Platform, player_x: int, monsters: Sequence[tuple[int, int]]
    ) -> Target | None:
        """同平台且与玩家水平距离最近的怪。"""
        candidates = [
            Target(int(m[0]), int(m[1]))
            for m in monsters
            if platform_of(m, self.platforms, self.y_tolerance) == platform
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda t: abs(t.x - player_x))

    def _patrol(self, player: tuple[int, int], platform: Platform, now: float) -> Decision:
        x = player[0]
        if x <= platform.x1 + PATROL_EDGE_MARGIN:
            self.patrol_direction = "right"
        elif x >= platform.x2 - PATROL_EDGE_MARGIN:
            self.patrol_direction = "left"
        if self._walk_too_long(self.patrol_direction, now):
            return Decision("jump", reason="巡逻中疑似卡墙,跳一下")
        return Decision("walk", self.patrol_direction, reason="无同平台怪,平台内巡逻")

    def _walk_too_long(self, direction: Direction, now: float) -> bool:
        """同方向连续走超时则触发防卡墙跳;触发后计时重置。"""
        if self._walk_direction != direction:
            self._walk_direction = direction
            self._walk_started = now
            return False
        if now - self._walk_started > self.max_walk_seconds:
            self._reset_walk()
            return True
        return False

    def _reset_walk(self) -> None:
        self._walk_direction = None
        self._walk_started = None
