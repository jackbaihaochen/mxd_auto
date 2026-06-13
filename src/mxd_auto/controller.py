"""按键封装。

默认后端 ScanCodeBackend:自实现 SendInput(DIK 扫描码,方向键等带
KEYEVENTF_EXTENDEDKEY)。不用 pydirectinput——它在 NumLock 开启时会给
方向键附送一个裸 0xE0 扫描码(畸形事件),被游戏误译成别的键
(实测 KuroMS 会因此打开聊天窗)。

后端可注入:单测传 fake,真实后端只需 keyDown/keyUp。
`_held` 记录所有按住未松的键,`release_all()` 是所有异常路径的安全兜底。
"""

import ctypes
import time
from ctypes import wintypes

KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001

# DIK 扫描码(基础集,够冒险岛用;需要更多键在这里加)
_SCANCODES = {
    "esc": 0x01,
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06,
    "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B,
    "backspace": 0x0E,
    "tab": 0x0F,
    "q": 0x10, "w": 0x11, "e": 0x12, "r": 0x13, "t": 0x14, "y": 0x15,
    "u": 0x16, "i": 0x17, "o": 0x18, "p": 0x19,
    "enter": 0x1C,
    "ctrl": 0x1D, "ctrlleft": 0x1D,
    "a": 0x1E, "s": 0x1F, "d": 0x20, "f": 0x21, "g": 0x22, "h": 0x23,
    "j": 0x24, "k": 0x25, "l": 0x26,
    "shift": 0x2A, "shiftleft": 0x2A,
    "z": 0x2C, "x": 0x2D, "c": 0x2E, "v": 0x2F, "b": 0x30, "n": 0x31, "m": 0x32,
    "shiftright": 0x36,
    "alt": 0x38, "altleft": 0x38,
    "space": 0x39,
    "f1": 0x3B, "f2": 0x3C, "f3": 0x3D, "f4": 0x3E, "f5": 0x3F,
    "f6": 0x40, "f7": 0x41, "f8": 0x42, "f9": 0x43, "f10": 0x44,
    "f11": 0x57, "f12": 0x58,
    # 扩展键(发送时带 KEYEVENTF_EXTENDEDKEY)
    "ctrlright": 0x1D,
    "altright": 0x38,
    "up": 0x48, "left": 0x4B, "right": 0x4D, "down": 0x50,
    "insert": 0x52, "delete": 0x53,
    "home": 0x47, "end": 0x4F, "pageup": 0x49, "pagedown": 0x51,
}
_EXTENDED_KEYS = {
    "ctrlright", "altright", "up", "left", "right", "down",
    "insert", "delete", "home", "end", "pageup", "pagedown",
}

# SendInput 结构体(只用键盘部分)
ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)


class _KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [("ki", _KeyBdInput), ("padding", ctypes.c_byte * 32)]


class _Input(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _InputUnion)]


def normalize_key(key: str) -> str:
    return key.strip().lower()


def is_known_key(key: str) -> bool:
    return normalize_key(key) in _SCANCODES


class ScanCodeBackend:
    """SendInput 扫描码后端(干净实现,无 pydirectinput 的 0xE0 杂散事件)。"""

    def _send(self, key: str, keyup: bool) -> None:
        key = normalize_key(key)
        try:
            scan = _SCANCODES[key]
        except KeyError:
            raise ValueError(f"未知按键名 {key!r},可用键名见 controller._SCANCODES") from None
        flags = KEYEVENTF_SCANCODE
        if key in _EXTENDED_KEYS:
            flags |= KEYEVENTF_EXTENDEDKEY
        if keyup:
            flags |= KEYEVENTF_KEYUP
        extra = ctypes.c_ulong(0)
        union = _InputUnion()
        union.ki = _KeyBdInput(0, scan, flags, 0, ctypes.pointer(extra))
        inp = _Input(1, union)  # INPUT_KEYBOARD
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    def keyDown(self, key: str) -> None:
        self._send(key, keyup=False)

    def keyUp(self, key: str) -> None:
        self._send(key, keyup=True)


class Controller:
    # 点按时按住的时长:游戏按帧轮询输入,瞬发 down+up 可能被整帧错过
    TAP_SECONDS = 0.04

    def __init__(self, backend=None):
        self._backend = backend if backend is not None else ScanCodeBackend()
        self._held: set[str] = set()

    @property
    def held(self) -> frozenset[str]:
        return frozenset(self._held)

    def press(self, key: str, presses: int = 1) -> None:
        """点按(按住 TAP_SECONDS 再松开,保证游戏轮询能看到)。"""
        for i in range(presses):
            if i:
                time.sleep(self.TAP_SECONDS)
            self._backend.keyDown(key)
            time.sleep(self.TAP_SECONDS)
            self._backend.keyUp(key)

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
