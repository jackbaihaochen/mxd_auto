"""图像识别:怪物模板匹配。

纯函数模块(只依赖 cv2/numpy,不 import Windows 专属库),便于离线单测。
灰度 TM_CCOEFF_NORMED 匹配 + 左右镜像模板 + 贪心 NMS 去重。
"""

import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np

DEFAULT_THRESHOLD = 0.75
NMS_IOU_THRESHOLD = 0.3
# 单模板命中数上限:平坦/过于普通的模板会在 TM_CCOEFF_NORMED 下匹配到海量位置,
# 不设上限会让贪心 NMS O(n²) 卡死
MAX_MATCHES_PER_TEMPLATE = 300
# 灰度标准差低于该值视为"平坦模板"(标定时框到了纯色背景),直接拒绝
MIN_TEMPLATE_STDDEV = 4.0


@dataclass(frozen=True)
class Template:
    name: str
    image: np.ndarray  # 灰度图


@dataclass(frozen=True)
class Detection:
    x: int
    y: int
    w: int
    h: int
    score: float
    template: str

    @property
    def center(self) -> tuple[int, int]:
        return self.x + self.w // 2, self.y + self.h // 2


def imread_gray(path: Path) -> np.ndarray:
    """读灰度图;cv2.imread 不支持非 ASCII 路径,用 fromfile + imdecode。"""
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"无法解码图像: {path}")
    return img


def with_mirrors(templates: Sequence[Template]) -> list[Template]:
    """为每个模板补充左右镜像(怪物朝向两边);对称模板不重复添加。"""
    result = list(templates)
    for t in templates:
        flipped = cv2.flip(t.image, 1)
        if not np.array_equal(flipped, t.image):
            result.append(Template(f"{t.name}_flip", flipped))
    return result


def load_templates(dir_path: Path) -> list[Template]:
    """加载 templates/<map>/ 下所有 PNG 模板,自动补镜像;拒绝平坦模板。"""
    paths = sorted(dir_path.glob("*.png"))
    if not paths:
        raise FileNotFoundError(f"{dir_path} 下没有模板图,请先运行 calibrate template")
    templates = []
    for p in paths:
        img = imread_gray(p)
        if float(img.std()) < MIN_TEMPLATE_STDDEV:
            warnings.warn(f"模板 {p.name} 几乎是纯色(可能框到了空白背景),已跳过")
            continue
        templates.append(Template(p.stem, img))
    if not templates:
        raise ValueError(f"{dir_path} 下没有可用模板(全部过于平坦)")
    return with_mirrors(templates)


def _to_gray(frame: np.ndarray) -> np.ndarray:
    if frame.ndim == 3:
        return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return frame


def _iou(a: Detection, b: Detection) -> float:
    x1 = max(a.x, b.x)
    y1 = max(a.y, b.y)
    x2 = min(a.x + a.w, b.x + b.w)
    y2 = min(a.y + a.h, b.y + b.h)
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter == 0:
        return 0.0
    return inter / (a.w * a.h + b.w * b.h - inter)


def _nms(detections: list[Detection], iou_threshold: float = NMS_IOU_THRESHOLD) -> list[Detection]:
    """贪心 NMS:按分数降序保留,与已保留框重叠过大的丢弃。"""
    kept: list[Detection] = []
    for det in sorted(detections, key=lambda d: d.score, reverse=True):
        if all(_iou(det, k) <= iou_threshold for k in kept):
            kept.append(det)
    return kept


def find_player(
    frame: np.ndarray,
    templates: Sequence[Template],
    threshold: float = 0.7,
) -> tuple[int, int] | None:
    """定位玩家:与怪物同一套模板匹配逻辑,多模板(含镜像)取全帧最高分。

    返回脚底坐标(最佳匹配框底边中点)。角色动作/朝向多变,建议截
    站立+走路各一张(calibrate player 可连续截多张);裁到脚底,
    不要把脚下名牌裁进去。低于阈值返回 None(换图/被遮挡)。
    """
    gray = _to_gray(frame)
    best: tuple[float, tuple[int, int]] | None = None
    for t in templates:
        th, tw = t.image.shape[:2]
        if gray.shape[0] < th or gray.shape[1] < tw:
            continue
        res = cv2.matchTemplate(gray, t.image, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val >= threshold and (best is None or max_val > best[0]):
            best = (max_val, (max_loc[0] + tw // 2, max_loc[1] + th))
    return best[1] if best else None


def build_player_locator(config: dict, verbose: bool = True):
    """玩家定位策略(main 与 preview 共用):
    player.pos 固定坐标 > templates/player/ 多模板 > 旧版 templates/player.png
    > 客户区中心偏下兜底(仅镜头跟随的大地图成立)。
    返回 locate(frame) -> (x, y) | None。
    """
    from mxd_auto.config import ROOT

    def say(msg: str) -> None:
        if verbose:
            print(msg)

    player_cfg = config.get("player") or {}
    pos = player_cfg.get("pos")
    if pos:
        fixed = (int(pos[0]), int(pos[1]))
        say(f"玩家定位:固定坐标 {fixed}(player.pos)")
        return lambda frame: fixed
    threshold = player_cfg.get("match_threshold", 0.7)
    player_dir = ROOT / "templates" / "player"
    if player_dir.is_dir() and any(player_dir.glob("*.png")):
        templates = load_templates(player_dir)
        say(f"玩家定位:templates/player/ {len(templates)} 个模板(含镜像)")
        return lambda frame: find_player(frame, templates, threshold)
    legacy = ROOT / "templates" / "player.png"
    if legacy.exists():
        templates = with_mirrors([Template("player", imread_gray(legacy))])
        say("玩家定位:旧版 templates/player.png(建议重新运行 calibrate player)")
        return lambda frame: find_player(frame, templates, threshold)
    say(
        "警告:玩家定位用客户区中心偏下兜底——只对镜头跟随的大地图成立!\n"
        "      单屏小地图请运行 calibrate player 截角色模板。"
    )
    return lambda frame: (frame.shape[1] // 2, round(frame.shape[0] * 0.6))


def find_monsters(
    frame: np.ndarray,
    templates: Sequence[Template],
    threshold: float = DEFAULT_THRESHOLD,
) -> list[Detection]:
    """在画面中匹配所有模板,返回去重后的检测框(按分数降序)。"""
    gray = _to_gray(frame)
    raw: list[Detection] = []
    for t in templates:
        th, tw = t.image.shape[:2]
        if gray.shape[0] < th or gray.shape[1] < tw:
            continue
        res = cv2.matchTemplate(gray, t.image, cv2.TM_CCOEFF_NORMED)
        ys, xs = np.where(res >= threshold)
        scores = res[ys, xs]
        if len(scores) > MAX_MATCHES_PER_TEMPLATE:
            warnings.warn(
                f"模板 {t.name} 命中 {len(scores)} 处,过于普通或阈值过低,只保留分数最高的 "
                f"{MAX_MATCHES_PER_TEMPLATE} 处"
            )
            top = np.argpartition(-scores, MAX_MATCHES_PER_TEMPLATE)[:MAX_MATCHES_PER_TEMPLATE]
            ys, xs, scores = ys[top], xs[top], scores[top]
        for x, y, score in zip(xs, ys, scores):
            raw.append(Detection(int(x), int(y), tw, th, float(score), t.name))
    return _nms(raw)
