import numpy as np

from mxd_auto.bot import Bot
from mxd_auto.controller import Controller
from mxd_auto.detector import Detection
from mxd_auto.navigator import Navigator
from mxd_auto.terrain import Platform

from test_controller import FakeBackend

FRAME = np.zeros((600, 1000, 3), dtype=np.uint8)


def make_bot(detections: list[Detection], player_pos=(500, 500)) -> tuple[Bot, FakeBackend]:
    backend = FakeBackend()
    nav = Navigator([Platform(0, 1000, 500)], attack_range_x=120, attack_range_y=40, max_walk_seconds=3.0)
    controller = Controller(backend=backend)
    controller.TAP_SECONDS = 0.0
    bot = Bot(
        controller=controller,
        navigator=nav,
        detect=lambda frame: detections,
        locate_player=lambda frame: player_pos,
        attack_key="ctrl",
        jump_key="alt",
        attack_presses=3,
    )
    return bot, backend


def monster_at(feet_x: int, feet_y: int, w: int = 40, h: int = 30) -> Detection:
    """构造脚底中点为 (feet_x, feet_y) 的检测框。"""
    return Detection(x=feet_x - w // 2, y=feet_y - h, w=w, h=h, score=0.9, template="m")


def test_tick_holds_right_when_monster_on_right():
    bot, backend = make_bot([monster_at(900, 500)])
    d = bot.tick(FRAME, now=0.0)
    assert (d.action, d.direction) == ("walk", "right")
    assert ("down", "right") in backend.events
    assert bot.controller.held == {"right"}


def test_tick_attacks_and_releases_movement_in_range():
    bot, backend = make_bot([monster_at(900, 500)])
    bot.tick(FRAME, now=0.0)  # 先走起来
    backend.events.clear()
    bot.detect = lambda frame: [monster_at(550, 500)]  # 怪进入范围
    d = bot.tick(FRAME, now=0.2)
    assert d.action == "attack"
    assert ("up", "right") in backend.events  # 先松移动键
    assert backend.events.count(("down", "ctrl")) == 3
    assert bot.controller.held == frozenset()


def test_tick_walk_switches_direction_releases_other():
    bot, backend = make_bot([monster_at(900, 500)])
    bot.tick(FRAME, now=0.0)
    bot.detect = lambda frame: [monster_at(100, 500)]
    d = bot.tick(FRAME, now=0.1)
    assert (d.action, d.direction) == ("walk", "left")
    assert ("up", "right") in backend.events
    assert bot.controller.held == {"left"}


def test_tick_jump_when_stuck():
    bot, backend = make_bot([monster_at(900, 500)])
    bot.tick(FRAME, now=0.0)
    bot.tick(FRAME, now=2.0)
    d = bot.tick(FRAME, now=4.0)
    assert d.action == "jump"
    assert ("down", "alt") in backend.events
    assert bot.controller.held == frozenset()


def test_tick_idle_releases_movement_when_airborne():
    bot, backend = make_bot([monster_at(900, 500)], player_pos=(500, 400))
    d = bot.tick(FRAME, now=0.0)
    assert d.action == "idle"
    assert bot.controller.held == frozenset()


def test_tick_idle_when_player_not_found():
    bot, backend = make_bot([monster_at(900, 500)])
    bot.tick(FRAME, now=0.0)  # 先走起来
    bot.locate_player = lambda frame: None  # 名牌丢失(换图/被遮挡)
    d = bot.tick(FRAME, now=0.1)
    assert d.action == "idle"
    assert "未定位到玩家" in d.reason
    assert bot.controller.held == frozenset()  # 必须松开移动键
