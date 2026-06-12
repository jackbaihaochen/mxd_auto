"""mxd_auto 脚本入口。

用法:
    python -m mxd_auto.main
"""

from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "config.yaml"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"未找到配置文件 {CONFIG_PATH},请先复制 config/config.example.yaml 为 config/config.yaml"
        )
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> None:
    config = load_config()
    print("mxd_auto 已启动,当前配置:")
    print(config)
    # TODO: 在这里实现自动化主循环


if __name__ == "__main__":
    main()
