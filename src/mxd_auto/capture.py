"""窗口定位 + 客户区截图。

win32gui 子串匹配窗口标题定位客户区。两种抓图后端:
- printwindow:PrintWindow(PW_RENDERFULLCONTENT)直接读窗口内容,可后台抓、
  不怕别的窗口遮挡(标定工具的选择窗口压在游戏上也没事);需与游戏权限对等。
- mss:屏幕区域抓图,谁在最上层抓谁。
默认 auto:PrintWindow 可用就用,否则回退 mss。
模块导入时设置 DPI aware,防止系统缩放导致坐标错位。

注意:游戏(如 KuroMS)常以管理员运行,低权限进程对它 SendInput 会被系统
静默丢弃(UIPI)、PrintWindow 也会失败——脚本必须同样以管理员运行,
用 elevation_mismatch() 在启动时检查。
"""

import ctypes
import time
from ctypes import wintypes

import mss
import numpy as np
import win32con
import win32gui
import win32process


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


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def window_process_is_elevated(hwnd: int) -> bool:
    """目标窗口所属进程是否以管理员(提权)运行;查不到时按提权处理(保守)。"""
    _, pid = win32process.GetWindowThreadProcessId(hwnd)
    k32 = ctypes.windll.kernel32
    advapi = ctypes.windll.advapi32
    k32.OpenProcess.restype = wintypes.HANDLE
    process = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not process:
        return True
    try:
        token = wintypes.HANDLE()
        if not advapi.OpenProcessToken(process, 0x0008, ctypes.byref(token)):  # TOKEN_QUERY
            return True
        try:
            elevated = wintypes.DWORD()
            size = wintypes.DWORD()
            advapi.GetTokenInformation(  # TokenElevation = 20
                token, 20, ctypes.byref(elevated), 4, ctypes.byref(size)
            )
            return bool(elevated.value)
        finally:
            k32.CloseHandle(token)
    finally:
        k32.CloseHandle(process)


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
    """绑定到一个游戏窗口,反复抓取其客户区画面。

    method: "printwindow" / "mss" / "auto"(默认,探测 PrintWindow 可用则用)。
    """

    def __init__(self, title_substring: str, method: str = "auto"):
        self.title_substring = title_substring
        self.hwnd = find_window(title_substring)
        self._sct = mss.mss()
        self.method = self._resolve_method(method)

    def _resolve_method(self, method: str) -> str:
        if method in ("mss", "printwindow"):
            return method
        try:
            frame = self._grab_printwindow()
            if frame.mean() > 1.0:  # 全黑视为不支持(硬件渲染窗口可能给黑帧)
                return "printwindow"
        except Exception:
            pass
        return "mss"

    @property
    def title(self) -> str:
        return win32gui.GetWindowText(self.hwnd)

    def client_rect(self) -> tuple[int, int, int, int]:
        return get_client_rect(self.hwnd)

    def is_foreground(self) -> bool:
        return win32gui.GetForegroundWindow() == self.hwnd

    def elevation_mismatch(self) -> bool:
        """游戏提权而我们没有 → SendInput 会被静默丢弃,必须管理员运行。"""
        return window_process_is_elevated(self.hwnd) and not is_admin()

    def bring_to_foreground(self, settle_seconds: float = 0.25) -> None:
        win32gui.ShowWindow(self.hwnd, win32con.SW_RESTORE)
        try:
            win32gui.SetForegroundWindow(self.hwnd)
        except Exception:
            pass  # 系统可能拒绝抢前台,由调用方提示用户手动点击
        time.sleep(settle_seconds)

    def grab(self) -> np.ndarray:
        """抓取客户区,返回 BGR ndarray(shape = (h, w, 3))。"""
        if self.method == "printwindow":
            return self._grab_printwindow()
        return self._grab_mss()

    def _grab_mss(self) -> np.ndarray:
        left, top, width, height = self.client_rect()
        raw = self._sct.grab({"left": left, "top": top, "width": width, "height": height})
        frame = np.asarray(raw, dtype=np.uint8)
        return np.ascontiguousarray(frame[:, :, :3])  # BGRA → BGR

    def _grab_printwindow(self) -> np.ndarray:
        """PrintWindow 直接读窗口内容:可后台抓、不怕遮挡;权限不对等时会失败。"""
        import win32ui

        _, _, width, height = win32gui.GetClientRect(self.hwnd)
        if width <= 0 or height <= 0:
            raise RuntimeError("客户区大小为 0,窗口可能已最小化")
        hwnd_dc = win32gui.GetWindowDC(self.hwnd)
        mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
        save_dc = mfc_dc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc_dc, width, height)
        save_dc.SelectObject(bmp)
        try:
            # PW_CLIENTONLY(1) | PW_RENDERFULLCONTENT(2)
            ok = ctypes.windll.user32.PrintWindow(self.hwnd, save_dc.GetSafeHdc(), 3)
            if not ok:
                raise RuntimeError("PrintWindow 调用失败(权限不对等或窗口不支持)")
            arr = np.frombuffer(bmp.GetBitmapBits(True), dtype=np.uint8)
            return arr.reshape((height, width, 4))[:, :, :3].copy()
        finally:
            win32gui.DeleteObject(bmp.GetHandle())
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(self.hwnd, hwnd_dc)

    def close(self) -> None:
        self._sct.close()

    def __enter__(self) -> "WindowCapture":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
