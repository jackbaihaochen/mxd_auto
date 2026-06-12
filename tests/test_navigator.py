from mxd_auto.navigator import Navigator
from mxd_auto.terrain import Platform


def make_nav(platforms=None, **kw) -> Navigator:
    defaults = dict(attack_range_x=120, attack_range_y=40, max_walk_seconds=3.0)
    defaults.update(kw)
    return Navigator(platforms or [Platform(0, 1000, 500)], **defaults)


def test_walk_towards_monster_on_right():
    nav = make_nav()
    d = nav.decide(player=(300, 500), monsters=[(700, 500)], now=0.0)
    assert (d.action, d.direction) == ("walk", "right")


def test_walk_towards_monster_on_left():
    nav = make_nav()
    d = nav.decide(player=(700, 500), monsters=[(200, 500)], now=0.0)
    assert (d.action, d.direction) == ("walk", "left")


def test_attack_when_in_range():
    nav = make_nav()
    d = nav.decide(player=(300, 500), monsters=[(350, 500)], now=0.0)
    assert d.action == "attack"


def test_picks_nearest_same_platform_monster():
    nav = make_nav()
    d = nav.decide(player=(500, 500), monsters=[(900, 500), (700, 500)], now=0.0)
    assert (d.action, d.direction) == ("walk", "right")
    # 最近的在 700,走到 600 即进入范围(120)
    d = nav.decide(player=(581, 500), monsters=[(900, 500), (700, 500)], now=0.1)
    assert d.action == "attack"


def test_ignores_monster_on_other_platform():
    nav = make_nav([Platform(0, 1000, 500), Platform(0, 1000, 300)])
    d = nav.decide(player=(500, 500), monsters=[(510, 300)], now=0.0)
    assert d.action == "walk"
    assert "巡逻" in d.reason


def test_patrol_flips_at_platform_edges():
    nav = make_nav()
    assert nav.decide((500, 500), [], now=0.0).direction == "right"
    assert nav.decide((990, 500), [], now=0.1).direction == "left"  # 右端点折返
    assert nav.decide((10, 500), [], now=0.2).direction == "right"  # 左端点折返


def test_idle_when_off_platform():
    nav = make_nav()
    d = nav.decide(player=(500, 400), monsters=[(700, 500)], now=0.0)
    assert d.action == "idle"


def test_anti_stuck_jump_after_walking_too_long():
    nav = make_nav(max_walk_seconds=3.0)
    assert nav.decide((300, 500), [(900, 500)], now=0.0).action == "walk"
    assert nav.decide((300, 500), [(900, 500)], now=2.0).action == "walk"
    d = nav.decide((300, 500), [(900, 500)], now=3.5)
    assert d.action == "jump"
    # 跳完计时重置,继续走
    assert nav.decide((300, 500), [(900, 500)], now=3.6).action == "walk"


def test_walk_timer_resets_on_direction_change():
    nav = make_nav(max_walk_seconds=3.0)
    nav.decide((300, 500), [(900, 500)], now=0.0)  # 往右
    nav.decide((300, 500), [(100, 500)], now=2.9)  # 换方向往左,重新计时
    d = nav.decide((300, 500), [(100, 500)], now=4.0)
    assert d.action == "walk"  # 往左才走了 1.1s,不触发防卡墙
