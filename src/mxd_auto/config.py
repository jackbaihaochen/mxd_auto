"""配置加载。

config/config.yaml 不存在时回退到 config.example.yaml(方便标定工具开箱即用)。
"""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "config.yaml"
EXAMPLE_CONFIG_PATH = ROOT / "config" / "config.example.yaml"
CAPTURES_DIR = ROOT / "captures"


def load_config() -> dict:
    path = CONFIG_PATH
    if not path.exists():
        if not EXAMPLE_CONFIG_PATH.exists():
            raise FileNotFoundError(f"未找到配置文件 {CONFIG_PATH},也没有 {EXAMPLE_CONFIG_PATH}")
        print(
            f"[config] 未找到 {CONFIG_PATH.name},使用示例配置 {EXAMPLE_CONFIG_PATH.name}"
            "(建议复制为 config.yaml 后修改)",
            file=sys.stderr,
        )
        path = EXAMPLE_CONFIG_PATH
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)
