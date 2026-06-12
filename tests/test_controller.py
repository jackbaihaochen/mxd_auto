from mxd_auto.controller import Controller


class FakeBackend:
    def __init__(self):
        self.events: list[tuple[str, str]] = []

    def press(self, key):
        self.events.append(("press", key))

    def keyDown(self, key):
        self.events.append(("down", key))

    def keyUp(self, key):
        self.events.append(("up", key))


def make() -> tuple[Controller, FakeBackend]:
    backend = FakeBackend()
    return Controller(backend=backend), backend


def test_press_repeats():
    c, b = make()
    c.press("ctrl", presses=3)
    assert b.events == [("press", "ctrl")] * 3
    assert c.held == frozenset()


def test_hold_is_idempotent():
    c, b = make()
    c.hold("right")
    c.hold("right")
    assert b.events == [("down", "right")]
    assert c.held == {"right"}


def test_release_only_held_keys():
    c, b = make()
    c.release("right")  # 未按住,不应发事件
    assert b.events == []
    c.hold("right")
    c.release("right")
    assert b.events == [("down", "right"), ("up", "right")]
    assert c.held == frozenset()


def test_release_all():
    c, b = make()
    c.hold("right")
    c.hold("alt")
    c.release_all()
    assert c.held == frozenset()
    ups = {k for e, k in b.events if e == "up"}
    assert ups == {"right", "alt"}
