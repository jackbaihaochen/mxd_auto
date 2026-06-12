# mxd_auto

冒险岛(MapleStory)私服外部自动化工具:截图 → 图像识别 → 按键模拟,不改游戏、不读内存。

> ⚠️ 仅供个人学习与研究使用。游戏自动化可能违反游戏的服务条款,请自行评估风险。

## 项目结构

```
mxd_auto/
├── src/mxd_auto/
│   ├── main.py          # 入口:加载配置 → 注册热键 → 启动 Bot
│   ├── capture.py       # 窗口定位 + 客户区截图(win32gui + mss,DPI aware)
│   ├── controller.py    # 按键封装(pydirectinput;hold/release/release_all)
│   ├── detector.py      # 怪物模板匹配(灰度匹配 + 镜像 + NMS,纯函数)
│   ├── terrain.py       # 平台线检测/存取/查询(纯函数)
│   ├── navigator.py     # 移动决策:追击/攻击/巡逻/防卡墙(纯逻辑)
│   ├── bot.py           # 主循环:识怪 → 选目标 → 导航 → 攻击
│   └── tools/
│       ├── calibrate.py    # 标定工具(screenshot/template/platforms/preview)
│       └── check_input.py  # 按键链路验证脚本
├── templates/<地图名>/   # 怪物模板图(calibrate template 产出)
├── maps/<地图名>.yaml    # 平台线数据(calibrate platforms 产出)
├── captures/            # 调试截图(gitignore)
├── tests/               # 纯函数单测
└── config/config.example.yaml
```

## 环境准备(Windows)

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install -e . --no-deps
copy config\config.example.yaml config\config.yaml   # 然后按自己的键位修改
```

## 使用流程

> ⚠️ **必须用管理员 PowerShell 运行**(右键开始菜单 → Windows PowerShell(管理员))。
> 私服客户端通常以管理员权限运行,普通权限脚本发的按键会被 Windows 静默丢弃(UIPI),
> 截图也只能退化为"抓屏幕"模式(会被别的窗口遮挡)。脚本启动时会自动检测并提示。

```powershell
# 0. 验证截图链路(游戏开窗口模式)
python -m mxd_auto.tools.calibrate screenshot

# 1. 截怪物模板:每轮抓一帧,鼠标框住一只怪,空格确认;空选结束
python -m mxd_auto.tools.calibrate template <地图名>

# 2. 标定平台线:自动检测候选,左键拖拽补画、右键删除、s 保存
python -m mxd_auto.tools.calibrate platforms <地图名>

# 3. 预览识别效果(不按任何键,零风险):怪物框 + 平台线 + 玩家点
python -m mxd_auto.tools.calibrate preview --map <地图名>

# 4. 验证按键链路:角色走动出招,F12 立停
python -m mxd_auto.tools.check_input

# 5. 正式运行(config.yaml 配好 combat.map,先在安全地图试)
python -m mxd_auto.main
```

热键:**F12 紧急停止**,F11 暂停/恢复(可在 config 改)。

## 测试

```powershell
.venv\Scripts\python -m pytest tests -q
```

## 路线图

- [x] 截图链路(窗口定位 + 客户区抓图)
- [x] 怪物识别(模板匹配 + 镜像 + NMS)
- [x] 地形标定(自动检测 + 人工修正)
- [x] 按键模拟 + 紧急停止
- [x] 核心 Bot(同平台追击/攻击/巡逻/防卡墙)
- [ ] 跨平台导航(上跳/下跳/绳索)
- [ ] 小地图全图坐标(巡逻边界锚定)
- [ ] 自动喝药 / 拾取
