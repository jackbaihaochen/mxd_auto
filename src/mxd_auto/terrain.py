"""地形数据:平台线的检测候选、加载/保存与查询。

平台 = 一条水平线段(x1..x2,屏幕 y)。地图静态,标定一次运行时查表。
纯函数模块(cv2/numpy/yaml,不 import Windows 专属库)。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np
import yaml

# 点到平台的判定容差:脚底 y 与平台 y 相差该像素内视为"站在平台上"
DEFAULT_Y_TOLERANCE = 12

# 自动检测参数
HOUGH_MIN_LINE_LENGTH = 80
HOUGH_MAX_LINE_GAP = 10
MAX_LINE_SLOPE = 0.03  # |dy/dx| 超过该值不算水平线
MERGE_Y_TOLERANCE = 6  # 合并候选线段:y 相差该像素内视为同一平台(含粗线的上下双边缘)
MERGE_X_GAP = 24       # 合并候选线段:水平间隙小于该像素则连成一条


@dataclass(frozen=True)
class Platform:
    x1: int
    x2: int
    y: int

    def __post_init__(self):
        if self.x1 > self.x2:
            lo, hi = self.x2, self.x1
            object.__setattr__(self, "x1", lo)
            object.__setattr__(self, "x2", hi)

    @property
    def length(self) -> int:
        return self.x2 - self.x1

    def contains_x(self, x: float) -> bool:
        return self.x1 <= x <= self.x2


def platform_of(
    point: tuple[float, float],
    platforms: Sequence[Platform],
    y_tolerance: int = DEFAULT_Y_TOLERANCE,
) -> Platform | None:
    """点(脚底坐标)落在哪条平台上;x 在范围内且 y 最接近的平台。"""
    x, y = point
    best: Platform | None = None
    best_dy = y_tolerance + 1
    for p in platforms:
        dy = abs(p.y - y)
        if p.contains_x(x) and dy <= y_tolerance and dy < best_dy:
            best, best_dy = p, dy
    return best


def same_platform(
    a: tuple[float, float],
    b: tuple[float, float],
    platforms: Sequence[Platform],
    y_tolerance: int = DEFAULT_Y_TOLERANCE,
) -> bool:
    pa = platform_of(a, platforms, y_tolerance)
    return pa is not None and pa == platform_of(b, platforms, y_tolerance)


def merge_segments(segments: Sequence[Platform]) -> list[Platform]:
    """合并 y 接近且 x 相邻/重叠的线段(Hough 常把一条平台切成几段)。"""
    merged: list[Platform] = []
    for seg in sorted(segments, key=lambda s: (s.y, s.x1)):
        for i, m in enumerate(merged):
            if (
                abs(m.y - seg.y) <= MERGE_Y_TOLERANCE
                and seg.x1 <= m.x2 + MERGE_X_GAP
                and m.x1 <= seg.x2 + MERGE_X_GAP
            ):
                merged[i] = Platform(
                    min(m.x1, seg.x1),
                    max(m.x2, seg.x2),
                    round((m.y * m.length + seg.y * seg.length) / max(1, m.length + seg.length)),
                )
                break
        else:
            merged.append(seg)
    return merged


def detect_platform_candidates(frame: np.ndarray) -> list[Platform]:
    """Canny + HoughLinesP 自动检测水平线段作为平台候选(仅供人工确认)。"""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame.ndim == 3 else frame
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=60,
        minLineLength=HOUGH_MIN_LINE_LENGTH,
        maxLineGap=HOUGH_MAX_LINE_GAP,
    )
    if lines is None:
        return []
    candidates = []
    for x1, y1, x2, y2 in lines[:, 0]:
        dx = abs(int(x2) - int(x1))
        if dx == 0 or abs(int(y2) - int(y1)) / dx > MAX_LINE_SLOPE:
            continue
        candidates.append(Platform(int(x1), int(x2), round((int(y1) + int(y2)) / 2)))
    return merge_segments(candidates)


def save_platforms(path: Path, platforms: Sequence[Platform], screen_size: tuple[int, int]) -> None:
    data = {
        "screen_size": list(screen_size),
        "platforms": [[p.x1, p.x2, p.y] for p in sorted(platforms, key=lambda p: (p.y, p.x1))],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def load_platforms(path: Path) -> list[Platform]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return [Platform(int(x1), int(x2), int(y)) for x1, x2, y in data["platforms"]]
