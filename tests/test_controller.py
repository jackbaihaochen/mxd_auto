import pytest

from mxd_auto.controller import Controller, is_known_key


class FakeBackend:
    def __init__(self):
        self.events: list[tuple[str, str]] = []

    def keyDown(self, key):
        self.events.append(("down", key))

    def keyUp(self, key):
        self.events.append(("up", key))


def make() -> tuple[Controller, FakeBackend]:
    backend = FakeBackend()
    controller = Controller(backend=backend)
    controller.TAP_SECONDS = 0.0  # 测试不真等
    return controller, backend


def test_press_sends_down_up_pairs():
    c, b = make()
    c.press("ctrl", presses=3)
    assert b.events == [("down", "ctrl"), ("up", "ctrl")] * 3
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


def test_known_key_names():
    for key in ["alt", "altright", "ctrl", "right", "delete", "z", "f12", " Space "]:
        assert is_known_key(key), key
    assert not is_known_key("notakey")


def test_real_backend_rejects_unknown_key():
    from mxd_auto.controller import ScanCodeBackend

    with pytest.raises(ValueError, match="未知按键名"):
        ScanCodeBackend()._send("notakey", keyup=False)