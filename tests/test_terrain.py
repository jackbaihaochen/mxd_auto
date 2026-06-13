import cv2
import numpy as np
import pytest

from mxd_auto.terrain import (
    Platform,
    detect_platform_candidates,
    load_platforms,
    merge_segments,
    platform_of,
    same_platform,
    save_platforms,
)


def test_platform_normalizes_endpoints():
    p = Platform(300, 100, 50)
    assert (p.x1, p.x2, p.y) == (100, 300, 50)
    assert p.length == 200


def test_platform_of_basic():
    platforms = [Platform(0, 200, 100), Platform(250, 400, 100)]
    assert platform_of((50, 102), platforms) == Platform(0, 200, 100)
    assert platform_of((300, 95), platforms) == Platform(250, 400, 100)
    assert platform_of((220, 100), platforms) is None  # 两平台之间的空隙
    assert platform_of((50, 130), platforms) is None  # y 超出容差


def test_platform_of_picks_nearest_y():
    """上下两层平台 x 范围重叠时,取 y 最接近的。"""
    upper = Platform(0, 400, 100)
    lower = Platform(0, 400, 110)
    assert platform_of((50, 101), [upper, lower]) == upper
    assert platform_of((50, 109), [upper, lower]) == lower


def test_same_platform():
    platforms = [Platform(0, 200, 100), Platform(0, 200, 300)]
    assert same_platform((10, 100), (190, 102), platforms)
    assert not same_platform((10, 100), (10, 300), platforms)
    assert not same_platform((10, 100), (10, 500), platforms)  # b 不在任何平台


def test_merge_segments_joins_collinear():
    segments = [Platform(0, 100, 50), Platform(110, 300, 51), Platform(0, 100, 200)]
    merged = merge_segments(segments)
    assert sorted(merged, key=lambda p: p.y) == [Platform(0, 300, 51), Platform(0, 100, 200)]


def test_merge_segments_keeps_distant_y():
    segments = [Platform(0, 100, 50), Platform(0, 100, 70)]
    assert len(merge_segments(segments)) == 2


def test_detect_platform_candidates_on_synthetic():
    frame = np.zeros((400, 600, 3), dtype=np.uint8)
    cv2.line(frame, (100, 150), (500, 150), (255, 255, 255), 3)
    cv2.line(frame, (50, 300), (250, 300), (255, 255, 255), 3)
    cv2.line(frame, (300, 100), (300, 350), (255, 255, 255), 3)  # 竖线,应被过滤
    candidates = detect_platform_candidates(frame)
    ys = sorted(p.y for p in candidates)
    assert len(candidates) == 2
    assert all(abs(y - expect) <= 3 for y, expect in zip(ys, [150, 300]))
    long = max(candidates, key=lambda p: p.length)
    assert abs(long.x1 - 100) <= 5 and abs(long.x2 - 500) <= 5


def test_save_load_roundtrip(tmp_path):
    platforms = [Platform(10, 200, 100), Platform(0, 400, 300)]
    path = tmp_path / "测试地图.yaml"
    save_platforms(path, platforms, (1366, 768))
    assert load_platforms(path) == sorted(platforms, key=lambda p: (p.y, p.x1))
