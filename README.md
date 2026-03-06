# FastF1 排位赛最快圈走线动画

## 双车手排位赛对比（推荐）

使用 Web UI 选择年份、分站、排位赛阶段（Q1/Q2/Q3）、车手（最多 2 人），生成对比动画：

```bash
pip install -r requirements.txt
streamlit run app.py
```

- **排位赛阶段**：Q1、Q2、Q3 独立选择
- **双车显示**：两位车手在赛道上用不同颜色（蓝/红）的点和轨迹表示，垂直偏移避免重叠
- **仪表盘**：每位车手有独立仪表盘，显示速度、油门、刹车、档位

### 无法访问 http://localhost:8501 时

1. **确认 Streamlit 已启动**：终端应显示 `You can now view your Streamlit app in your browser.`
2. **远程开发 / Cursor 端口转发**：改用 `--server.address 0.0.0.0` 监听所有网卡：
   ```bash
   streamlit run app.py --server.address 0.0.0.0
   ```
3. **端口被占用**：换用其他端口，例如：
   ```bash
   streamlit run app.py --server.port 8502
   ```
   然后访问 http://localhost:8502

---

## 单车手脚本（qualifying_fastest_lap_animation.py）

1. 用 FastF1 拉取指定分站的排位赛数据；
2. 选择某个车手的最快单圈；
3. 在赛道图上用点位动画展示该圈走线；
4. 在动画右侧显示 F1 风格仪表盘（油门、刹车、速度、档位、RPM、DRS），无任何水印。

## 安装

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 运行示例

```bash
python qualifying_fastest_lap_animation.py \
  --year 2024 \
  --gp "Monaco" \
  --driver "VER"
```

保存为 GIF：

```bash
python qualifying_fastest_lap_animation.py \
  --year 2024 \
  --gp "Monaco" \
  --driver "VER" \
  --save outputs/monaco_ver_q_fastest.gif
```

速度热力图（按赛段上色，电视转播风格）：

```bash
python qualifying_fastest_lap_animation.py \
  --year 2024 \
  --gp "Monaco" \
  --driver "VER" \
  --heatmap \
  --save outputs/monaco_ver_q_heatmap.gif
```

宽赛道 + 赛车箭头（便于观察走线、入弯出弯）：

```bash
python qualifying_fastest_lap_animation.py \
  --year 2024 \
  --gp "Monaco" \
  --driver "VER" \
  --track-width 150 \
  --car-style arrow
```

## 常用参数

- `--year`: 赛季年份，例如 `2024`
- `--gp`: 分站名称，例如 `Monaco`、`Japanese Grand Prix`
- `--driver`: 车手缩写，例如 `VER`、`HAM`、`NOR`
- `--session`: 会话类型，默认 `Q`（排位赛）
- `--fps`: 动画帧率，默认 `30`
- `--tail-length`: 轨迹尾迹长度，默认 `40`
- `--save`: 输出文件（支持 `.gif` / `.mp4`）
- `--cache-dir`: FastF1 缓存目录，默认 `.fastf1_cache`
- `--heatmap`: 按速度分段上色（红=慢，绿=快），类似电视转播效果
- `--track-width`: 赛道宽度（1/10m 单位，默认 80≈8m），便于观察走线、入弯出弯
- `--car-style`: 赛车标记 `arrow`（带方向箭头）或 `point`（圆点）
