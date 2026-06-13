# mxd_auto:冒险岛自动化工具实现计划(v2 — 本地 Windows 开发)

## Context

用户为冒险岛**私服**做纯外部自动化工具(不改游戏、不读内存),"截图 → 图像识别 → 按键模拟"。游戏在 Windows **窗口模式**运行。

**v2 变更**:
- 开发环境切换到用户本地 Windows 机器(即游戏机)上运行 Claude Code,可以直接截图、直接跑集成测试,不再需要云端/本地分离的离线开发架构。
- 第一版**忽略喝药和拾取**,专注:**怪物识别、地形识别、移动、攻击**。
- 新增需求:**地形识别**辅助移动(知道平台在哪,才能走位/跳跃接近怪物)。

仓库 `jackbaihaochen/mxd_auto`,骨架已推到分支 `claude/eloquent-clarke-p9ipw8`,本地 clone 后从该分支继续。

## 模块划分

```
src/mxd_auto/
├── main.py          # 入口:加载配置 → 注册 F12 紧急停止 → 启动 Bot
├── capture.py       # 窗口定位 + 客户区截图(win32gui + mss,DPI aware)
├── controller.py    # 按键封装(pydirectinput;hold/release/release_all)
├── detector.py      # 图像识别:怪物模板匹配、小地图玩家定位(纯函数)
├── terrain.py       # 地形数据:平台线加载/查询(玩家在哪个平台、目标怪在哪个平台)
├── navigator.py     # 移动决策:同平台走位 / 跨平台跳跃(后期)
├── bot.py           # 主循环:识怪 → 选目标 → 导航 → 攻击
└── tools/calibrate.py  # 标定工具:截图/截怪物模板/标小地图/标平台线/preview
templates/<map>/     # 怪物模板图
maps/<map>.yaml      # 每张地图的平台线数据(标定产出)
captures/            # 调试截图(gitignore)
tests/               # detector/terrain 纯函数单测(用真实截图 fixtures)
```

## 核心技术决策

1. **截图**:win32gui 定位客户区(`FindWindow`/`EnumWindows` 子串匹配 → `GetClientRect` → `ClientToScreen`)+ mss 抓图(~5ms)。模块初始化设 `SetProcessDpiAwareness(2)` 防缩放坐标错位。

2. **按键**:pydirectinput(DIK 扫描码,游戏可靠识别;pyautogui 的 VK 事件常被游戏忽略),`PAUSE = 0.01`。长按移动用 keyDown/keyUp(`hold/release`,`_held` 集合记录),`release_all()` 为安全兜底。Controller 抽象一层,私服不认时可切换实现。

3. **怪物识别**:灰度模板匹配 `cv2.matchTemplate(TM_CCOEFF_NORMED)`,阈值进配置(默认 0.75),`cv2.flip` 自动生成左右镜像,贪心 NMS 去重。模板不抗缩放 → 配置存 `calibrated_size`,启动时不符则警告。

4. **玩家定位(两套互补)**:
   - 屏幕内:镜头跟随角色,角色恒在客户区中心偏下(固定坐标,配置可覆盖)——用于与怪物的相对距离判断。
   - 全图:**小地图玩家光点识别**。标定工具框出小地图区域,运行时在该区域 `inRange` 找玩家黄色光点 → 得到全图坐标——用于巡逻边界和跨平台导航。

5. **地形识别(本次核心新增)**:
   - 冒险岛地图是静态的,平台不会动 → **每张地图一次性标定,运行时查表**,而不是每帧实时识别(实时识别背景干扰大且无必要)。
   - 标定流程:`calibrate platforms` 截当前画面 → 先用 `cv2.Canny` + `cv2.HoughLinesP` **自动检测水平线段作为平台候选**,叠加显示 → 用户鼠标确认/删除/补画平台线 → 存 `maps/<map>.yaml`(每条平台 = 两端点 + 所在屏幕 y;后续配合小地图坐标换算为地图坐标)。
   - `terrain.py` 提供查询:`platform_of(point) -> Platform | None`(点落在哪条平台上)、`same_platform(a, b) -> bool`。
   - 第一阶段以"屏幕坐标系 + 单屏地图"为前提跑通;大地图(镜头滚动)的地图坐标换算放后期(借助小地图玩家点做锚定)。

6. **移动与攻击决策(`Bot.tick(frame)`,每帧重评估)**:
   1. 识别怪物 → 用 terrain 判断每只怪所在平台
   2. 目标选择:优先**与玩家同平台**且 `|dx|` 最小的怪
   3. 同平台、不在 `attack_range_x` 内 → `hold` 左/右走过去;持有移动键超 `max_walk_seconds` 仍未接近 → 松键 + 跳一下(防卡墙)
   4. 进入攻击范围 → 松移动键 → 按攻击键 N 次
   5. 无同平台怪:v1 先巡逻(本平台内左右走,靠平台端点折返,不再用纯计时);v2 再做跨平台导航(上跳/下跳/绳索)
   6. 窗口失焦 → `release_all` 跳过本帧
   - 计时全用 `time.monotonic()`,不阻塞 sleep,保证 F12 响应

7. **紧急停止**:`keyboard` 库全局热键独立线程,F12 → `stop_event.set()` + `release_all()`;run() 包 `try/finally: release_all()`。F11 暂停/恢复。

8. **依赖**:单一 `requirements.txt`(本地 Windows 开发,无需拆分):opencv-python、numpy、PyYAML、mss、pywin32、pydirectinput、keyboard、pytest。移除 pyautogui。detector/terrain 仍保持纯函数(不 import win 专属库),便于单测。

## 配置扩展(config.example.yaml)

新增:`combat.{map,match_threshold,attack_range_x,attack_range_y,attack_presses,max_walk_seconds}`、`player.pos`(null=中心偏下)、`minimap.rect`(标定生成)、`hotkeys.{stop,pause}`、`calibrated_size`、`debug.save_frames`。暂时保留 keys 中的喝药/拾取键位但不使用(potion 配置段删除,留待后续版本)。

## 标定工具(tools/calibrate.py,子命令式,cv2.selectROI / 鼠标交互)

```
calibrate screenshot          # 截客户区,验证截图链路
calibrate template <地图名>    # 框怪物 → templates/<map>/,可连续框多张
calibrate minimap             # 框小地图区域 → 打印 YAML 片段
calibrate platforms <地图名>   # 自动检测平台线 + 人工修正 → maps/<map>.yaml
calibrate preview [--image]   # 实时预览:怪物框 + 平台线 + 玩家点,不按任何键
```

## 切换到本地(计划批准后,本云端会话的唯一动作)

把本计划写入仓库 `docs/PLAN.md`,连同 v2 的 requirements.txt 调整一起提交推送到 `claude/eloquent-clarke-p9ipw8` 分支——这样用户在本地启动 Claude Code 后,新会话读 `docs/PLAN.md` 即可无缝接手,后续全部开发在本地进行。

## 实施顺序(本地 Windows,每阶段即时验证)

| 阶段 | 产出 | 验证方式 |
|---|---|---|
| 1. 环境 + 截图链路 | 本地 clone、装依赖;capture.py + screenshot 子命令 | 截到尺寸正确的客户区 PNG |
| 2. 怪物识别 | detector.py + template/preview 子命令 + 单测 | 游戏旁开 preview,肉眼看怪物框准确率,调阈值 |
| 3. 地形标定 | terrain.py + platforms 子命令(自动检测+人工修正) | preview 叠加平台线,与画面一致 |
| 4. 按键 + 紧急停止 | controller.py + F12 热键 + 最小 check 脚本 | 角色走动出招,F12 立停(暴露 pydirectinput 兼容性) |
| 5. 核心 Bot | bot.py + navigator(同平台走位+攻击+平台内巡逻)+ main.py | 单平台地图实战:找怪→走近→攻击→折返巡逻 |
| 6. 增强(后续) | 跨平台导航、小地图全图坐标、喝药/拾取回归 | 多平台地图实战 |

## 验证方案

- 每阶段在游戏机上直接集成验证(preview 不按键,零风险;check/Bot 在安全地图试)。
- `pytest tests/`:用真实截图 fixtures 断言 find_monsters 坐标、平台查询逻辑;fake controller 验证 tick 决策("怪在右按 right""进范围松移动按攻击")。

## 风险与对策

- pydirectinput 在该私服无效 → Controller 抽象,阶段 4 提前暴露,可切换方案。
- HoughLinesP 平台自动检测在花哨背景误检多 → 自动检测只是"候选建议",人工确认/补画兜底,不影响最终数据质量。
- 分辨率变化使模板/坐标失效 → 固定窗口大小,启动校验 `calibrated_size`。
