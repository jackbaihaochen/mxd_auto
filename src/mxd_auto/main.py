"""mxd_auto 脚本入口。

用法:
    python -m mxd_auto.main
"""

from mxd_auto.config import load_config


def main() -> None:
    config = load_config()
    print("mxd_auto 已启动,当前配置:")
    print(config)
    # TODO: 在这里实现自动化主循环


if __name__ == "__main__":
    main()
