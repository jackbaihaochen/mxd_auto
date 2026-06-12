"""按键封装。

默认后端 pydirectinput(DIK 扫描码,游戏可靠识别;VK 事件常被游戏忽略)。
后端可注入:私服不认 pydirectinput 时换实现,单测时传 fake。
`_held` 记录所有按住未松的键,`release_all()` 是所有异常路径的安全兜底。
"""


class Controller:
    def __init__(self, backend=None):
        if backend is None:
            import pydirectinput as backend

            backend.PAUSE = 0.01
        self._backend = backend
        self._held: set[str] = set()

    @property
    def held(self) -> frozenset[str]:
        return frozenset(self._held)

    def press(self, key: str, presses: int = 1) -> None:
        """点按(自动按下+松开)。"""
        for _ in range(presses):
            self._backend.press(key)

    def hold(self, key: str) -> None:
        """按住不放(已按住则不重复发事件)。"""
        if key not in self._held:
            self._backend.keyDown(key)
            self._held.add(key)

    def release(self, key: str) -> None:
        if key in self._held:
            self._backend.keyUp(key)
            self._held.discard(key)

    def release_all(self) -> None:
        for key in list(self._held):
            self.release(key)
