# F1 遥测视频制作 —— 数据来源调研报告

> 针对 [BV1QDY3zXEoS](https://www.bilibili.com/video/BV1QDY3zXEoS/) 类视频的制作方式与所需数据的全网调研

---

## 一、视频制作方式概览

这类 F1 遥测/走线视频大致有几种实现路径：


| 方式               | 数据来源                         | 能否体现「靠内/靠外」    | 难度  |
| ---------------- | ---------------------------- | -------------- | --- |
| **1. 录屏 + 后期**   | MultiViewer / F1 官方 App 实时画面 | ✅ 可能（取决于官方 UI） | 低   |
| **2. 公开 API 编程** | FastF1、OpenF1                | ❌ 不能           | 中   |
| **3. F1 游戏回放**   | F1 24/23 等游戏内置遥测             | ✅ 能            | 中   |
| **4. 电视/官方转播**   | 内部专有系统                       | ✅ 能            | 需合作 |


---

## 二、公开数据源详细对比

### 1. FastF1（Python 库）

- **文档**：[https://docs.fastf1.dev/](https://docs.fastf1.dev/)
- **数据**：F1 官方 API 的 Python 封装
- **位置字段**：`X`, `Y`, `Z`（单位：1/10 m）
- **限制**：官方维护者明确说明（[GitHub #116](https://github.com/theOehrly/Fast-F1/discussions/116)）：
  > “All coordinates show the same line... It's certainly **not possible to analyze drivers lines through a corner**.”
- **结论**：仅为「归一化赛道位置」，沿近似理想走线，**无法体现内外侧、真实走线差异**。

### 2. OpenF1 API

- **文档**：[https://openf1.org/docs/](https://openf1.org/docs/)
- **端点**：`/v1/location`、`/v1/car_data`，约 3.7 Hz
- **位置字段**：`x`, `y`, `z`
- **官方说明**（[Location 端点](https://openf1.org/docs/)）：
  > “Useful for gauging their progress along the track, but **lacks details about lateral placement — i.e. whether the car is on the left or right side of the track**.”
- **结论**：与 FastF1 同源，同样 **不能区分靠内或靠外**。

### 3. MultiViewer F1

- **官网**：[https://multiviewer.io/](https://multiviewer.io/)
- **数据来源**：F1 TV 订阅流内嵌的 telemetry
- **功能**：实时 telemetry 覆盖、Race Trace、多画面同步等
- **结论**：数据来自官方转播流，与公开 API 逻辑相似；可 **录屏做视频**，但无法导出原始位置数据编程使用。

---

## 三、为何公开 API 没有「靠内/靠外」数据？

- F1 官方公开接口主要服务于 **Driver Tracker**、散点图等简单可视化。
- 坐标被设计成沿「理想走线」的归一化位置，以简化展示。
- 能体现真实走线、内外侧的详细位置数据，由 **转播系统内部使用**，不对外开放。

---

## 四、可行的实现路径

### 路径 A：录屏（最接近 B 站视频效果）

1. 安装 [MultiViewer F1](https://multiviewer.io/)。
2. 订阅 F1 TV，在比赛/回放时打开 MultiViewer。
3. 使用 OBS、系统录屏等工具录制 telemetry 覆盖画面。
4. 后期剪辑、加解说或字幕。

**优点**：可直接利用官方/类似官方的图形，观感最接近电视。  
**缺点**：依赖 F1 TV 订阅，无法用 Python/API 做二次开发。

### 路径 B：FastF1 / OpenF1 编程（你当前项目）

- **能做**：  
  - 沿理想走线的时间轴动画  
  - 速度、油门、刹车、档位等 telemetry 可视化  
  - 走线随时间推进的动画
- **不能做**：  
  - 区分车辆在赛道上是靠内还是靠外  
  - 分析真实弯道走线差异

### 路径 C：F1 游戏（F1 24/23/22 等）

- **工具**：如 [Sim Racing Telemetry (SRT)](https://www.simracingtelemetry.com/)。
- **数据**：游戏内遥测，可导出 CSV，包含真实 X/Y 位置。
- **限制**：只适用于 **游戏内圈速**，不是真实 F1 比赛数据。

### 路径 D：OpenF1 + car_data 组合

- **端点**：`/v1/car_data`（速度、油门、刹车、档位、RPM、DRS 等）
- **用法**：与 `/v1/location` 按时间对齐，做速度热力图、档位/油门等叠加。
- **限制**：位置仍为归一化，无法表达内外侧。

---

## 五、数据源速查表


| 数据源         | 网址                                                 | 位置数据       | 能否体现内外侧    | 费用           |
| ----------- | -------------------------------------------------- | ---------- | ---------- | ------------ |
| FastF1      | [https://docs.fastf1.dev](https://docs.fastf1.dev) | 归一化 X/Y/Z  | ❌          | 免费           |
| OpenF1      | [https://openf1.org](https://openf1.org)           | 归一化 x/y/z  | ❌          | 免费（历史），实时需订阅 |
| MultiViewer | [https://multiviewer.io](https://multiviewer.io)   | 依赖 F1 TV 流 | 取决于 UI，无导出 | 需 F1 TV      |
| F1 游戏 SRT   | 游戏 + SRT 工具                                        | 真实 X/Y     | ✅（仅游戏）     | 游戏 + 工具内购    |
| F1 官方转播     | 内部系统                                               | 专有         | ✅          | 不对外开放        |


---

## 六、针对你项目的建议

1. **若目标是「尽量接近 B 站那类视频」**
  - 优先考虑 **MultiViewer + F1 TV + 录屏**。  
  - 这是目前能用到的最接近官方展示效果的方式。
2. **若坚持用 Python 做可视化**
  - 继续用 FastF1 / OpenF1。  
  - 在现有基础上优化：更清晰的赛道、更好的速度热力图、更醒目的「当前位置」标记。  
  - 在说明或界面中标注：「位置沿理想走线，无法反映真实内外侧差异」。
3. **若需要「可编程的真实走线」**
  - 公开 API 目前无法满足。  
  - 只能等待 F1/第三方未来开放更细粒度位置数据，或转向 F1 游戏遥测。

---

## 参考文献

- [FastF1 官方文档](https://docs.fastf1.dev/)
- [FastF1 GitHub 讨论 #116：X/Y 坐标说明](https://github.com/theOehrly/Fast-F1/discussions/116)
- [OpenF1 API 文档](https://openf1.org/docs/)
- [MultiViewer 文档](https://multiviewer.dev/docs)
- [F1 转播技术简介](https://www.raceteq.com/articles/2025/10/how-f1-is-broadcast-on-tv)

