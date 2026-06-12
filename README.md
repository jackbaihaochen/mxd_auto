# mxd_auto

冒险岛(MapleStory)简易自动化脚本,用于辅助个人游戏操作。

> ⚠️ 仅供个人学习与研究使用。游戏自动化可能违反游戏的服务条款,请自行评估风险。

## 项目结构

```
mxd_auto/
├── src/
│   └── mxd_auto/
│       ├── __init__.py
│       └── main.py        # 脚本入口
├── config/
│   └── config.example.yaml  # 配置文件示例(复制为 config.yaml 使用)
├── requirements.txt
└── README.md
```

## 环境准备

```bash
# 建议使用虚拟环境
python -m venv .venv
.venv\Scripts\activate      # Windows
# source .venv/bin/activate # macOS / Linux

pip install -r requirements.txt
```

## 使用

```bash
# 复制配置文件并按需修改
copy config\config.example.yaml config\config.yaml

python -m mxd_auto.main
```

## 规划中的功能

- [ ] 基础按键模拟(移动 / 攻击 / 拾取)
- [ ] 屏幕截图与图像识别(定位怪物 / 血条 / 小地图)
- [ ] 自动喝药(血量 / 蓝量低于阈值时)
- [ ] 定时换频道 / 防卡死处理
