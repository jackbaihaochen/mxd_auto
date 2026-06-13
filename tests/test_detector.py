import cv2
import numpy as np
import pytest

from mxd_auto.detector import Detection, Template, find_monsters, with_mirrors


@pytest.fixture
def monster() -> np.ndarray:
    """不对称的随机纹理小图,模拟怪物外观。"""
    rng = np.random.default_rng(42)
    img = rng.integers(0, 256, size=(24, 18), dtype=np.uint8)
    img[:, :4] = 255  # 左侧亮条,保证左右不对称
    return img


@pytest.fixture
def canvas() -> np.ndarray:
    rng = np.random.default_rng(7)
    return rng.integers(0, 256, size=(240, 320), dtype=np.uint8)


def paste(canvas: np.ndarray, patch: np.ndarray, x: int, y: int) -> None:
    canvas[y : y + patch.shape[0], x : x + patch.shape[1]] = patch


def test_find_single_monster(canvas, monster):
    paste(canvas, monster, 100, 50)
    dets = find_monsters(canvas, [Template("slime", monster)], threshold=0.9)
    assert len(dets) == 1
    assert (dets[0].x, dets[0].y) == (100, 50)
    assert (dets[0].w, dets[0].h) == (18, 24)
    assert dets[0].template == "slime"
    assert dets[0].score > 0.99


def test_find_multiple_monsters(canvas, monster):
    paste(canvas, monster, 30, 20)
    paste(canvas, monster, 200, 150)
    dets = find_monsters(canvas, [Template("slime", monster)], threshold=0.9)
    assert sorted((d.x, d.y) for d in dets) == [(30, 20), (200, 150)]


def test_nms_dedups_near_threshold_neighbors(canvas, monster):
    """低阈值下完美匹配点周围会有大量重叠命中,NMS 应去重为一个框。"""
    paste(canvas, monster, 100, 50)
    dets = find_monsters(canvas, [Template("slime", monster)], threshold=0.5)
    assert len(dets) == 1
    assert (dets[0].x, dets[0].y) == (100, 50)


def test_mirror_template_detects_flipped_monster(canvas, monster):
    paste(canvas, cv2.flip(monster, 1), 100, 50)
    templates = with_mirrors([Template("slime", monster)])
    assert [t.name for t in templates] == ["slime", "slime_flip"]
    dets = find_monsters(canvas, templates, threshold=0.9)
    assert len(dets) == 1
    assert dets[0].template == "slime_flip"


def test_with_mirrors_skips_symmetric(monster):
    symmetric = np.hstack([monster, cv2.flip(monster, 1)])
    templates = with_mirrors([Template("sym", symmetric)])
    assert [t.name for t in templates] == ["sym"]


def test_no_false_positive_on_plain_background(canvas, monster):
    dets = find_monsters(canvas, [Template("slime", monster)], threshold=0.9)
    assert dets == []


def test_bgr_frame_is_converted(monster):
    rng = np.random.default_rng(7)
    gray = rng.integers(0, 256, size=(240, 320), dtype=np.uint8)
    paste(gray, monster, 60, 80)
    bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    dets = find_monsters(bgr, [Template("slime", monster)], threshold=0.9)
    assert len(dets) == 1
    assert (dets[0].x, dets[0].y) == (60, 80)


def test_template_larger_than_frame_is_skipped(monster):
    tiny = np.zeros((10, 10), dtype=np.uint8)
    assert find_monsters(tiny, [Template("slime", monster)]) == []


def test_flat_template_match_is_capped(canvas):
    """平坦模板在平坦背景上命中海量位置,必须截断防止 NMS O(n²) 卡死。"""
    flat_canvas = np.full((400, 600), 200, dtype=np.uint8)
    flat_template = np.full((30, 90), 200, dtype=np.uint8)
    with pytest.warns(UserWarning, match="过于普通"):
        dets = find_monsters(flat_canvas, [Template("flat", flat_template)], threshold=0.9)
    assert len(dets) < 50  # NMS 之后剩不了几个,关键是不卡死


def test_load_templates_rejects_flat(tmp_path):
    from mxd_auto.detector import load_templates

    flat = np.full((30, 90), 200, dtype=np.uint8)
    ok, buf = cv2.imencode(".png", flat)
    assert ok
    buf.tofile(str(tmp_path / "monster_01.png"))
    with pytest.warns(UserWarning, match="纯色"):
        with pytest.raises(ValueError, match="平坦"):
            load_templates(tmp_path)


def test_find_player_returns_feet_at_box_bottom_center(canvas, monster):
    from mxd_auto.detector import find_player

    paste(canvas, monster, 100, 50)  # 形象 18x24,底边中点(脚底)= (109, 74)
    assert find_player(canvas, [Template("player", monster)], threshold=0.9) == (109, 74)


def test_find_player_picks_best_of_multiple_templates(canvas, monster):
    from mxd_auto.detector import find_player

    other = np.random.default_rng(99).integers(0, 256, size=(20, 16), dtype=np.uint8)  # 不匹配的姿势
    paste(canvas, monster, 100, 50)
    templates = [Template("pose_a", other), Template("pose_b", monster)]
    assert find_player(canvas, templates, threshold=0.9) == (109, 74)


def test_find_player_none_when_absent(canvas, monster):
    from mxd_auto.detector import find_player

    assert find_player(canvas, [Template("player", monster)], threshold=0.9) is None


def test_detection_center():
    det = Detection(x=10, y=20, w=18, h=24, score=1.0, template="t")
    assert det.center == (19, 32)
