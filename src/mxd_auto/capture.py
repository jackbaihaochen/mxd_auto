"""窗口定位 + 客户区截图。

win32gui 子串匹配窗口标题 → GetClientRect/ClientToScreen 得到客户区屏幕坐标,
mss 抓图返回 BGR ndarray。模块导入时设置 DPI aware,防止系统缩放导致坐标错位。
"""

import ctypes

import mss
import numpy as np
import win32gui


def _set_dpi_aware() -> None:
    try:
        # PROCESS_PER_MONITOR_DPI_AWARE = 2
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


_set_dpi_aware()


class WindowNotFoundError(RuntimeError):
    pass


def find_window(title_substring: str) -> int:
    """返回标题包含指定子串的第一个可见顶层窗口句柄。"""
    needle = title_substring.lower()
    matches: list[int] = []

    def _on_window(hwnd: int, _extra) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if title and needle in title.lower():
            matches.append(hwnd)

    win32gui.EnumWindows(_on_window, None)
    if not matches:
        raise WindowNotFoundError(f"未找到标题包含 {title_substring!r} 的可见窗口")
    return matches[0]


def get_client_rect(hwnd: int) -> tuple[int, int, int, int]:
    """返回客户区的屏幕坐标 (left, top, width, height)。"""
    _, _, width, height = win32gui.GetClientRect(hwnd)
    if width <= 0 or height <= 0:
        raise RuntimeError("客户区大小为 0,窗口可能已最小化")
    left, top = win32gui.ClientToScreen(hwnd, (0, 0))
    return left, top, width, height


class WindowCapture:
    """绑定到一个游戏窗口,反复抓取其客户区画面。"""

    def __init__(self, title_substring: str):
        self.title_substring = title_substring
        self.hwnd = find_window(title_substring)
        self._sct = mss.mss()

    @property
    def title(self) -> str:
        return win32gui.GetWindowText(self.hwnd)

    def client_rect(self) -> tuple[int, int, int, int]:
        return get_client_rect(self.hwnd)

    def is_foreground(self) -> bool:
        return win32gui.GetForegroundWindow() == self.hwnd

    def grab(self) -> np.ndarray:
        """抓取客户区,返回 BGR ndarray(shape = (h, w, 3))。"""
        left, top, width, height = self.client_rect()
        raw = self._sct.grab({"left": left, "top": top, "width": width, "height": height})
        frame = np.asarray(raw, dtype=np.uint8)
        return np.ascontiguousarray(frame[:, :, :3])  # BGRA → BGR

    def close(self) -> None:
        self._sct.close()

    def __enter__(self) -> "WindowCapture":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
