"""
F1 双车手排位赛最快圈对比动画模块。
支持 Q1/Q2/Q3，按真实时间同步，含油门刹车等仪表盘。
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import List, Tuple

import fastf1
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
from matplotlib.patches import Wedge, Polygon
import numpy as np
import pandas as pd
from matplotlib.animation import FuncAnimation, PillowWriter
from PIL import Image


DRIVER_COLORS = ["#00d4ff", "#e63946"]
MARKER_OFFSET = 25  # 两车垂直偏移（1/10m），避免重叠
CAR_MARKER_SCALE = 1.6  # 车手箭头缩放，增大可视性
TEAM_LOGO_DIR = Path(__file__).resolve().parent / "assets" / "team_logos"

# FastF1 TeamName (2018-2025) -> theme color
TEAM_THEME_COLORS = {
    "Ferrari": "#DC0000",
    "Mercedes": "#00D2BE",
    "Red Bull Racing": "#1E41FF",
    "McLaren": "#FF8700",
    "Williams": "#005AFF",
    "Haas F1 Team": "#B6BABD",
    "Aston Martin": "#006F62",
    "Alpine": "#0090FF",
    "Racing Point": "#F596C8",
    "Force India": "#F596C8",
    "Renault": "#FFF500",
    "Toro Rosso": "#2B4562",
    "AlphaTauri": "#2B4562",
    "RB": "#6692FF",
    "Racing Bulls": "#6692FF",
    "Sauber": "#9B0000",
    "Alfa Romeo Racing": "#900000",
    "Alfa Romeo": "#900000",
    "Kick Sauber": "#52E252",
}

TEAM_BADGE_LABELS = {
    "Ferrari": "FER",
    "Mercedes": "MER",
    "Red Bull Racing": "RBR",
    "McLaren": "MCL",
    "Williams": "WIL",
    "Haas F1 Team": "HAA",
    "Aston Martin": "AMR",
    "Alpine": "ALP",
    "Racing Point": "RPT",
    "Force India": "FIN",
    "Renault": "REN",
    "Toro Rosso": "TRR",
    "AlphaTauri": "ATR",
    "RB": "RB",
    "Racing Bulls": "RBU",
    "Sauber": "SAU",
    "Alfa Romeo Racing": "ARR",
    "Alfa Romeo": "ARO",
    "Kick Sauber": "KSA",
}

TEAM_LOGO_FILES = {
    "Ferrari": "ferrari",
    "Mercedes": "mercedes",
    "Red Bull Racing": "red-bull-racing",
    "McLaren": "mclaren",
    "Williams": "williams",
    "Haas F1 Team": "haas-f1-team",
    "Aston Martin": "aston-martin",
    "Alpine": "alpine",
    "Racing Point": "racing-point",
    "Force India": "force-india",
    "Renault": "renault",
    "Toro Rosso": "toro-rosso",
    "AlphaTauri": "alphatauri",
    "RB": "rb",
    "Racing Bulls": "racing-bulls",
    "Sauber": "sauber",
    "Alfa Romeo Racing": "alfa-romeo-racing",
    "Alfa Romeo": "alfa-romeo",
    "Kick Sauber": "kick-sauber",
}

_TEAM_LOGO_CACHE: dict[str, np.ndarray | None] = {}


def _team_color(team_name: str | None, fallback: str) -> str:
    """Return mapped team theme color with fallback."""
    if not team_name:
        return fallback
    return TEAM_THEME_COLORS.get(str(team_name).strip(), fallback)


def _same_hue_variant(base_color: str) -> str:
    """Generate a distinguishable lighter/darker variant of the same hue."""
    rgb = np.array(mcolors.to_rgb(base_color), dtype=float)
    luminance = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
    # Dark colors -> lighten, bright colors -> darken.
    if luminance < 0.52:
        out = rgb + (1.0 - rgb) * 0.38
    else:
        out = rgb * 0.68
    return mcolors.to_hex(np.clip(out, 0.0, 1.0))


def _team_badge_label(team_name: str | None) -> str:
    """Return compact team badge text shown before driver code."""
    if not team_name:
        return "TEAM"
    name = str(team_name).strip()
    return TEAM_BADGE_LABELS.get(name, name[:3].upper())


def _resolve_team_logo_path(team_name: str | None) -> Path | None:
    """Resolve team logo file path from assets/team_logos."""
    if not team_name:
        return None
    team = str(team_name).strip()
    stem = TEAM_LOGO_FILES.get(team)
    if not stem:
        return None
    for ext in (".png", ".svg", ".jpg", ".jpeg", ".webp"):
        path = TEAM_LOGO_DIR / f"{stem}{ext}"
        if path.exists():
            return path
    return None


def _load_team_logo(team_name: str | None) -> np.ndarray | None:
    """Load team logo image array from png/svg with cache."""
    key = str(team_name).strip() if team_name else ""
    if key in _TEAM_LOGO_CACHE:
        return _TEAM_LOGO_CACHE[key]

    path = _resolve_team_logo_path(team_name)
    if path is None:
        _TEAM_LOGO_CACHE[key] = None
        return None

    img: np.ndarray | None = None
    try:
        suffix = path.suffix.lower()
        if suffix == ".png":
            img = plt.imread(path)
        elif suffix == ".svg":
            # Optional dependency: cairosvg is needed to rasterize SVG.
            try:
                import cairosvg  # type: ignore
            except Exception:
                img = None
            else:
                png_bytes = cairosvg.svg2png(url=str(path))
                pil_img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
                img = np.asarray(pil_img)
        elif suffix in {".jpg", ".jpeg", ".webp"}:
            pil_img = Image.open(path).convert("RGBA")
            img = np.asarray(pil_img)
    except Exception:
        img = None

    _TEAM_LOGO_CACHE[key] = img
    return img


def _fmt_td(val) -> str:
    """Format pandas Timedelta like 28.534."""
    if pd.isna(val):
        return "N/A"
    sec = val.total_seconds()
    return f"{sec:.3f}"


def _compute_sector_boundaries(lap: fastf1.core.Lap, tel: pd.DataFrame) -> Tuple[float, float]:
    """Return sector split positions in RelativeDistance [0, 1)."""
    if "RelativeDistance" not in tel.columns:
        return 1 / 3, 2 / 3

    s1 = lap.get("Sector1Time")
    s2 = lap.get("Sector2Time")
    if pd.isna(s1) or pd.isna(s2):
        return 1 / 3, 2 / 3

    t = _extract_time_seconds(tel)
    if len(t) < 2:
        return 1 / 3, 2 / 3
    t = t - t[0]
    rd = tel["RelativeDistance"].to_numpy()
    t1 = float(s1.total_seconds())
    t2 = float((s1 + s2).total_seconds())
    t_end = float(t[-1])
    t1 = min(max(0.0, t1), t_end)
    t2 = min(max(t1, t2), t_end)
    r1 = float(np.interp(t1, t, rd))
    r2 = float(np.interp(t2, t, rd))
    return r1, r2


def _extract_time_seconds(tel: pd.DataFrame) -> np.ndarray:
    if "Time" in tel.columns:
        return tel["Time"].dt.total_seconds().to_numpy()
    if "SessionTime" in tel.columns:
        return tel["SessionTime"].dt.total_seconds().to_numpy()
    if "Date" in tel.columns:
        base = tel["Date"].iloc[0]
        return (tel["Date"] - base).dt.total_seconds().to_numpy()
    raise ValueError("Unable to find a valid time column.")


def _prepare_driver_lap_data(lap: fastf1.core.Lap) -> pd.DataFrame:
    tel = lap.get_telemetry()
    required = ["X", "Y", "Speed", "Throttle", "Brake", "nGear"]
    missing = [c for c in required if c not in tel.columns]
    if missing:
        raise ValueError(f"Telemetry missing: {missing}")
    tel = tel.dropna(subset=required).reset_index(drop=True)
    if len(tel) < 2:
        raise ValueError("Not enough telemetry samples.")
    if "RelativeDistance" not in tel.columns:
        tel = tel.add_relative_distance(drop_existing=True)
    tel = tel.dropna(subset=["RelativeDistance"]).reset_index(drop=True)
    time_s = _extract_time_seconds(tel)
    mono = np.diff(time_s, prepend=time_s[0] - 1e-9) > 0
    return tel.loc[mono].reset_index(drop=True)


def _track_centerline_to_polygon(x: np.ndarray, y: np.ndarray, half_width: float) -> np.ndarray:
    n = len(x)
    if n < 3:
        return np.array([[0, 0]])
    dx = np.zeros(n)
    dy = np.zeros(n)
    dx[:-1] = np.diff(x)
    dy[:-1] = np.diff(y)
    dx[-1], dy[-1] = dx[-2], dy[-2]
    dx[0], dy[0] = dx[1], dy[1]
    r = np.sqrt(dx**2 + dy**2) + 1e-12
    nx, ny = -dy / r, dx / r
    x_left = x + nx * half_width
    y_left = y + ny * half_width
    x_right = x - nx * half_width
    y_right = y - ny * half_width
    verts = np.vstack([
        np.column_stack([x_left, y_left]),
        np.column_stack([x_right[::-1], y_right[::-1]]),
    ])
    return verts


def _compute_heading(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    n = len(x)
    dx = np.zeros(n)
    dy = np.zeros(n)
    dx[:-1] = np.diff(x)
    dy[:-1] = np.diff(y)
    dx[-1], dy[-1] = dx[-2], dy[-2]
    dx[0], dy[0] = dx[1], dy[1]
    return np.arctan2(dy, dx)


def _sample_stepwise(rd: np.ndarray, values: np.ndarray, rd_uniform: np.ndarray) -> np.ndarray:
    """Sample categorical telemetry (e.g. DRS) without linear interpolation."""
    idx = np.searchsorted(rd, rd_uniform, side="left")
    idx = np.clip(idx, 0, len(values) - 1)
    return values[idx]


def _is_drs_open(value: float) -> bool:
    """FastF1 DRS state: open is usually 10/12/14; fallback for higher codes."""
    iv = int(round(value))
    return iv in {10, 12, 14} or iv >= 10


def _text_on_arc(
    ax: plt.Axes,
    text: str,
    center: tuple[float, float],
    radius: float,
    start_angle: float,
    end_angle: float,
    fontsize: int = 9,
) -> list:
    """Draw text along an arc using per-character labels."""
    chars = list(text)
    if not chars:
        return []
    angles = np.linspace(start_angle, end_angle, len(chars))
    out = []
    for ch, ang in zip(chars, angles):
        rad = np.radians(ang)
        x = center[0] + radius * np.cos(rad)
        y = center[1] + radius * np.sin(rad)
        txt = ax.text(
            x, y, ch,
            color="white", fontsize=fontsize, fontweight="bold",
            ha="center", va="center",
            rotation=ang - 90, rotation_mode="anchor",
            zorder=30,
        )
        out.append(txt)
    return out


def _create_telemetry_dashboard(ax: plt.Axes, driver: str, color: str) -> dict:
    """圆盘仪表盘：圆弧下方开口，外圈蓝=速度，内圈左绿=油门/右红=刹车，标签在弧上，中央 KMH/RPM/DRS/GEAR。"""
    ax.set_xlim(-1.5, 1.5)
    ax.set_ylim(-1.2, 1.2)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_facecolor("#1a1a1a")

    ax.set_title(driver, color="white", fontsize=11, fontweight="bold")

    cx, cy = 0.0, 0.0
    # 圆弧下方开口：弧从 315°(右下) 经右侧、顶部、左侧 到 225°(左下)，缺口在底部
    # 外圈：速度弧 (蓝)，左下(225°) -> 右下(315°) 方向递增
    r_speed_outer, r_speed_inner = 1.0, 0.82
    speed_left, speed_span = 225, 270
    wedge_speed_bg = Wedge(
        (cx, cy), r_speed_outer, 315, 225,
        width=r_speed_outer - r_speed_inner, facecolor="#1e2a3a", edgecolor="#333", linewidth=1,
    )
    ax.add_patch(wedge_speed_bg)
    wedge_speed_fill = Wedge(
        (cx, cy), r_speed_outer, speed_left, speed_left,
        width=r_speed_outer - r_speed_inner, facecolor="#2563eb", edgecolor="none",
    )
    ax.add_patch(wedge_speed_fill)
    speed_tick_texts = []
    for v, label in [(0, "0"), (60, "60"), (120, "120"), (180, "180"), (240, "240"), (300, "300"), (360, "360")]:
        # 0 在左下(225°)，360 在右下(315°)
        ang = speed_left - speed_span * (v / 360)
        rad = np.radians(ang)
        xl = (r_speed_outer - 0.03) * np.cos(rad) + cx
        yl = (r_speed_outer - 0.03) * np.sin(rad) + cy
        tick = ax.text(
            xl, yl, label,
            color="white", fontsize=16, fontweight="bold",
            ha="center", va="center", zorder=30
        )
        speed_tick_texts.append(tick)

    # 内圈：左绿油门 (40°~220°)、右红刹车 (320°~40°)
    # 这样油门满值与刹车在 40° 处相接，且两者不重叠
    r_inner_outer, r_inner_inner = 0.76, 0.58
    wedge_throttle_bg = Wedge((cx, cy), r_inner_outer, 40, 220, width=r_inner_outer - r_inner_inner,
                              facecolor="#1a2a1a", edgecolor="#333", linewidth=1)
    ax.add_patch(wedge_throttle_bg)
    th_r = 0.67
    wedge_brake_bg = Wedge((cx, cy), r_inner_outer, 320, 40, width=r_inner_outer - r_inner_inner,
                           facecolor="#2a1a1a", edgecolor="#333", linewidth=1)
    ax.add_patch(wedge_brake_bg)
    wedge_throttle = Wedge((cx, cy), r_inner_outer, 220, 220, width=r_inner_outer - r_inner_inner,
                           facecolor="#22c55e", edgecolor="none")
    ax.add_patch(wedge_throttle)
    wedge_brake = Wedge((cx, cy), r_inner_outer, 320, 320, width=r_inner_outer - r_inner_inner,
                        facecolor="#ef4444", edgecolor="none")
    ax.add_patch(wedge_brake)
    txt_throttle_label_chars = _text_on_arc(
        ax=ax,
        text="THROTTLE",
        center=(cx, cy),
        radius=th_r,
        start_angle=210,
        end_angle=155,
        fontsize=10,
    )
    txt_brake_label_chars = _text_on_arc(
        ax=ax,
        text="BRAKE",
        center=(cx, cy),
        radius=th_r,
        start_angle=16,
        end_angle=-8,
        fontsize=10,
    )

    # 中央：速度、KMH、RPM、DRS、GEAR
    txt_speed = ax.text(0, 0.42, "0", fontsize=26, color="white", ha="center", va="center", fontweight="bold")
    ax.text(0, 0.28, "KMH", fontsize=9, color="white", fontweight="bold", ha="center", va="center")
    txt_rpm = ax.text(0, 0.08, "0", fontsize=14, color="white", fontweight="bold", ha="center", va="center")
    ax.text(0, -0.02, "RPM", fontsize=8, color="white", fontweight="bold", ha="center", va="center")
    txt_drs = ax.text(0, -0.18, "DRS", fontsize=8, color="white", fontweight="bold", ha="center", va="center",
                      bbox=dict(boxstyle="round,pad=0.2", facecolor="#333333", edgecolor="#444"))
    txt_gear = ax.text(0, -0.38, "N", fontsize=13, color="white", fontweight="bold", ha="center", va="center")
    ax.text(0, -0.46, "GEAR", fontsize=8, color="white", fontweight="bold", ha="center", va="center")

    return {
        "wedge_speed": wedge_speed_fill,
        "wedge_throttle": wedge_throttle,
        "wedge_brake": wedge_brake,
        "txt_speed": txt_speed,
        "txt_rpm": txt_rpm,
        "txt_drs": txt_drs,
        "txt_gear": txt_gear,
        "speed_tick_texts": speed_tick_texts,
        "txt_throttle_label_chars": txt_throttle_label_chars,
        "txt_brake_label_chars": txt_brake_label_chars,
        "speed_left": speed_left,
        "speed_span": speed_span,
    }


def run_comparison_animation(
    year: int,
    gp: str,
    qualifying_phase: str,
    drivers: List[str],
    cache_dir: str = ".fastf1_cache",
    track_width: float = 120,
    fps: int = 30,
    save_path: str | None = None,
    show: bool = True,
    figsize: Tuple[float, float] = (16, 10),
) -> None:
    """
    运行双车手排位赛最快圈对比动画。
    qualifying_phase: "Q1", "Q2", 或 "Q3"
    drivers: 1 或 2 个车手代码
    """
    if len(drivers) < 1 or len(drivers) > 2:
        raise ValueError("drivers 必须包含 1 或 2 个车手。")
    drivers = [d.upper() for d in drivers]
    phase = qualifying_phase.upper()
    if phase not in ("Q1", "Q2", "Q3"):
        raise ValueError("qualifying_phase 必须为 Q1、Q2 或 Q3。")

    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache))

    sess = fastf1.get_session(year, gp, "Q")
    sess.load(laps=True, telemetry=True, weather=False, messages=False)

    q1_laps, q2_laps, q3_laps = sess.laps.split_qualifying_sessions()
    phase_map = {"Q1": q1_laps, "Q2": q2_laps, "Q3": q3_laps}
    phase_laps = phase_map.get(phase)
    if phase_laps is None or phase_laps.empty:
        raise ValueError(f"排位赛 {phase} 无数据。")

    laps_data = []
    for i, drv in enumerate(drivers):
        phase_driver = phase_laps.pick_drivers(drv)
        if phase_driver.empty:
            raise ValueError(f"车手 {drv} 在 {phase} 无圈速数据。")
        fastest_in_phase = phase_driver.pick_fastest()
        row_idx = fastest_in_phase.name
        lap = sess.laps.loc[row_idx]
        tel = _prepare_driver_lap_data(lap)
        team_name = lap.get("Team")
        color = _team_color(team_name, DRIVER_COLORS[i])
        laps_data.append({
            "lap": fastest_in_phase,
            "tel": tel,
            "driver": drv,
            "team": team_name,
            "color": color,
        })
    if (
        len(laps_data) == 2
        and str(laps_data[0]["color"]).lower() == str(laps_data[1]["color"]).lower()
    ):
        laps_data[1]["color"] = _same_hue_variant(laps_data[1]["color"])

    # 根据圈时长确定帧数：约 40 帧/秒，保证轨迹连续不跳跃
    valid_durations = [
        ld["lap"]["LapTime"].total_seconds()
        for ld in laps_data
        if pd.notna(ld["lap"]["LapTime"])
    ]
    lap_duration_seconds = max(valid_durations) if valid_durations else 75.0
    n_frames = max(400, min(3000, int(lap_duration_seconds * 40)))  # 40 fps 等效采样
    # 关键：按真实时间统一采样（不是按圈进度），才能体现快慢车位置差
    time_uniform = np.linspace(0.0, lap_duration_seconds, n_frames)
    interval_ms = int(1000 * lap_duration_seconds / n_frames)  # 每帧间隔（毫秒）
    save_fps = n_frames / lap_duration_seconds  # 保存时用于匹配实际时长

    driver_curves = []
    track_x, track_y, track_rd = None, None, None
    sector_r1, sector_r2 = None, None

    for i, ld in enumerate(laps_data):
        tel = ld["tel"]
        rd = tel["RelativeDistance"].to_numpy()
        time_s = _extract_time_seconds(tel)
        time_rel = time_s - time_s[0]
        x = tel["X"].to_numpy()
        y = tel["Y"].to_numpy()
        speed = tel["Speed"].to_numpy()
        throttle = tel["Throttle"].clip(0, 100).to_numpy()
        brake = (tel["Brake"].astype(float) * 100).to_numpy()
        gear = tel["nGear"].fillna(0).to_numpy()
        rpm = tel["RPM"].to_numpy() if "RPM" in tel.columns else None
        drs = tel["DRS"].to_numpy() if "DRS" in tel.columns else None
        if track_x is None:
            track_x, track_y = x, y
            track_rd = rd
            sector_r1, sector_r2 = _compute_sector_boundaries(ld["lap"], tel)
        x_u = np.interp(time_uniform, time_rel, x, left=x[0], right=x[-1])
        y_u = np.interp(time_uniform, time_rel, y, left=y[0], right=y[-1])
        heading_u = _compute_heading(x_u, y_u)
        if len(drivers) == 1:
            x_off, y_off = x_u, y_u
        else:
            nx = -np.sin(heading_u)
            ny = np.cos(heading_u)
            offset = MARKER_OFFSET * (-1 if i == 0 else 1)
            x_off = x_u + nx * offset
            y_off = y_u + ny * offset
        drs_u = _sample_stepwise(time_rel, drs, time_uniform) if drs is not None else None
        progress_u = np.interp(time_uniform, time_rel, rd, left=rd[0], right=rd[-1])
        driver_curves.append({
            "x": x_off,
            "y": y_off,
            "heading": heading_u,
            "speed": np.interp(time_uniform, time_rel, speed, left=speed[0], right=speed[-1]),
            "throttle": np.interp(time_uniform, time_rel, throttle, left=throttle[0], right=throttle[-1]),
            "brake": np.interp(time_uniform, time_rel, brake, left=brake[0], right=brake[-1]),
            "gear": np.interp(time_uniform, time_rel, gear, left=gear[0], right=gear[-1]),
            "rpm": np.interp(time_uniform, time_rel, rpm, left=rpm[0], right=rpm[-1]) if rpm is not None else None,
            "drs": drs_u,
            "progress": progress_u,
            "lap_elapsed": float(time_rel[-1]),
            "lap": ld["lap"],
            "driver": ld["driver"],
            "team": ld.get("team"),
            "color": ld["color"],
        })

    fig = plt.figure(figsize=figsize)
    fig.patch.set_facecolor("#101010")
    n_drivers = len(driver_curves)
    if n_drivers == 1:
        gs = fig.add_gridspec(1, 2, width_ratios=[1.2, 0.8], wspace=0.12)
    else:
        gs = fig.add_gridspec(2, 2, width_ratios=[1.2, 0.8], wspace=0.12, hspace=0.25)

    ax = fig.add_subplot(gs[:, 0])
    ax.set_facecolor("#101010")
    ax.set_aspect("equal", adjustable="datalim")
    ax.axis("off")

    half_w = max(1, track_width / 2)
    verts = _track_centerline_to_polygon(track_x, track_y, half_w)
    ax.add_patch(Polygon(verts, facecolor="#2a2a2a", edgecolor="#555", linewidth=1, zorder=0))
    ax.plot(track_x, track_y, color="#555", linewidth=0.8, alpha=0.5, zorder=1)
    if track_rd is not None and sector_r1 is not None and sector_r2 is not None:
        # 用三段颜色标记赛道计时段 S1/S2/S3
        m1 = track_rd <= sector_r1
        m2 = (track_rd > sector_r1) & (track_rd <= sector_r2)
        m3 = track_rd > sector_r2
        # 避免与车手蓝/红相近，采用黄/紫/绿三色
        ax.plot(track_x[m1], track_y[m1], color="#facc15", linewidth=2.2, alpha=0.95, zorder=2)  # S1
        ax.plot(track_x[m2], track_y[m2], color="#a855f7", linewidth=2.2, alpha=0.95, zorder=2)  # S2
        ax.plot(track_x[m3], track_y[m3], color="#84cc16", linewidth=2.2, alpha=0.95, zorder=2)  # S3

        # 在分段边界打点
        for rr, lbl in [(sector_r1, "S1"), (sector_r2, "S2"), (0.999, "S3")]:
            px = float(np.interp(rr, track_rd, track_x))
            py = float(np.interp(rr, track_rd, track_y))
            ax.scatter([px], [py], s=28, color="white", zorder=20)
            ax.text(px, py, f" {lbl}", color="white", fontsize=8, fontweight="bold", zorder=21)

    markers = []
    car_local = CAR_MARKER_SCALE * np.array([[45, 0], [-35, 14], [-25, 0], [-35, -14]])

    for dc in driver_curves:
        # 箭头标记使用车手代表色（车体+描边）
        car_poly = Polygon(
            car_local,
            facecolor=dc["color"],
            edgecolor=dc["color"],
            linewidth=2.0,
            zorder=15,
        )
        ax.add_patch(car_poly)
        markers.append(car_poly)

    title_parts = [f"{sess.event['EventName']} {year} {phase}"]
    for dc in driver_curves:
        lt = dc["lap"]["LapTime"]
        lt_str = "N/A" if pd.isna(lt) else str(lt)
        title_parts.append(f"{dc['driver']}: {lt_str}")
    ax.set_title(" | ".join(title_parts), color="white", fontsize=10, pad=12)

    legend_y = 0.98
    for dc in driver_curves:
        logo_img = _load_team_logo(dc.get("team"))
        if logo_img is not None:
            logo_box = OffsetImage(logo_img, zoom=0.085)
            logo_ab = AnnotationBbox(
                logo_box,
                (0.042, legend_y - 0.012),
                xycoords="axes fraction",
                frameon=False,
                box_alignment=(0.5, 0.5),
                zorder=40,
            )
            ax.add_artist(logo_ab)
        else:
            badge = _team_badge_label(dc.get("team"))
            ax.text(
                0.02,
                legend_y,
                f" {badge} ",
                color="white",
                fontsize=8,
                fontweight="bold",
                transform=ax.transAxes,
                va="top",
                ha="left",
                bbox=dict(
                    boxstyle="round,pad=0.18,rounding_size=0.15",
                    facecolor=dc["color"],
                    edgecolor="#222222",
                    linewidth=0.9,
                ),
            )
        ax.text(
            0.085,
            legend_y,
            dc["driver"],
            color=dc["color"],
            fontsize=11,
            transform=ax.transAxes,
            va="top",
            ha="left",
        )
        legend_y -= 0.04

    # 右上角分段时间：仅在对应车手完成该分段后显示
    sector_header = ax.text(
        0.98, 0.98, "Sector Times (s)",
        transform=ax.transAxes,
        ha="right", va="top",
        fontsize=8, color="white",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#111111cc", edgecolor="#444"),
        zorder=30,
    )
    sector_rows = []
    for idx, ld in enumerate(laps_data):
        lap = ld["lap"]
        row_artist = ax.text(
            0.98, 0.95 - idx * 0.035,
            "",
            transform=ax.transAxes,
            ha="right", va="top",
            fontsize=8,
            color=ld["color"],
            zorder=31,
        )
        sector_rows.append({
            "artist": row_artist,
            "driver": ld["driver"],
            "s1": _fmt_td(lap.get("Sector1Time")),
            "s2": _fmt_td(lap.get("Sector2Time")),
            "s3": _fmt_td(lap.get("Sector3Time")),
        })

    dash_artists = []
    for i, dc in enumerate(driver_curves):
        if n_drivers == 1:
            ax_d = fig.add_subplot(gs[0, 1])
        else:
            ax_d = fig.add_subplot(gs[i, 1])
        artists = _create_telemetry_dashboard(ax_d, dc["driver"], dc["color"])
        dash_artists.append(artists)

    def _update_dash(idx: int, frame: int):
        dc = driver_curves[idx]
        a = dash_artists[idx]
        t = np.clip(dc["throttle"][frame], 0, 100)
        b = np.clip(dc["brake"][frame], 0, 100)
        spd = min(int(round(dc["speed"][frame])), 360)
        # 外圈蓝弧：速度从左下(0)到右下(360)递增
        s_left, sspan = a["speed_left"], a["speed_span"]
        a["wedge_speed"].set_theta1(s_left - sspan * (spd / 360))
        a["wedge_speed"].set_theta2(s_left)
        # 内圈：油门从左下沿左/上侧增长，满值在 40° 与刹车终点连接
        a["wedge_throttle"].set_theta1(220 - 180 * t / 100)
        a["wedge_throttle"].set_theta2(220)
        a["wedge_brake"].set_theta2(320 + 80 * b / 100)
        a["txt_speed"].set_text(f"{int(round(dc['speed'][frame]))}")
        if dc["rpm"] is not None:
            a["txt_rpm"].set_text(f"{int(round(dc['rpm'][frame]))}")
        else:
            a["txt_rpm"].set_text("-")
        on = _is_drs_open(dc["drs"][frame]) if dc["drs"] is not None else False
        a["txt_drs"].set_color("white")
        a["txt_drs"].set_bbox(dict(boxstyle="round,pad=0.2", facecolor="#22c55e" if on else "#333333", edgecolor="#444"))
        g = dc["gear"][frame]
        a["txt_gear"].set_text("N" if g == 0 else str(int(g)))

    def _update_sector_rows(frame: int):
        t_now = time_uniform[frame]
        for i, row in enumerate(sector_rows):
            dc = driver_curves[i]
            progress = dc["progress"][frame]
            s1_txt = row["s1"] if (sector_r1 is not None and progress >= sector_r1) else "--"
            s2_txt = row["s2"] if (sector_r2 is not None and progress >= sector_r2) else "--"
            s3_txt = row["s3"] if t_now >= dc["lap_elapsed"] else "--"
            row["artist"].set_text(f"{row['driver']}  S1:{s1_txt}  S2:{s2_txt}  S3:{s3_txt}")

    def init():
        for i, (dc, mp) in enumerate(zip(driver_curves, markers)):
            cx, cy = dc["x"][0], dc["y"][0]
            h = dc["heading"][0]
            c, s = np.cos(h), np.sin(h)
            rot = np.array([[c, -s], [s, c]])
            mp.set_xy(car_local @ rot.T + np.array([cx, cy]))
            _update_dash(i, 0)
        _update_sector_rows(0)
        out = list(markers)
        for a in dash_artists:
            out.extend([a["wedge_speed"], a["wedge_throttle"], a["wedge_brake"], a["txt_speed"],
                        a["txt_rpm"], a["txt_drs"], a["txt_gear"]])
            out.extend(a["speed_tick_texts"])
            out.extend(a["txt_throttle_label_chars"])
            out.extend(a["txt_brake_label_chars"])
        out.append(sector_header)
        out.extend([r["artist"] for r in sector_rows])
        return out

    def update(frame: int):
        for i, dc in enumerate(driver_curves):
            cx, cy = dc["x"][frame], dc["y"][frame]
            h = dc["heading"][frame]
            c, s = np.cos(h), np.sin(h)
            rot = np.array([[c, -s], [s, c]])
            markers[i].set_xy(car_local @ rot.T + np.array([cx, cy]))
            _update_dash(i, frame)
        _update_sector_rows(frame)
        out = list(markers)
        for a in dash_artists:
            out.extend([a["wedge_speed"], a["wedge_throttle"], a["wedge_brake"], a["txt_speed"],
                        a["txt_rpm"], a["txt_drs"], a["txt_gear"]])
            out.extend(a["speed_tick_texts"])
            out.extend(a["txt_throttle_label_chars"])
            out.extend(a["txt_brake_label_chars"])
        out.append(sector_header)
        out.extend([r["artist"] for r in sector_rows])
        return out

    anim = FuncAnimation(
        fig, update, frames=n_frames,
        init_func=init,
        interval=max(16, interval_ms),  # 至少 16ms 避免过快
        blit=True,
        repeat=True,
    )

    if save_path:
        out_path = Path(save_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        suf = out_path.suffix.lower()
        if suf == ".gif":
            anim.save(out_path, writer=PillowWriter(fps=max(1, int(round(save_fps)))))
        elif suf == ".mp4":
            anim.save(out_path, fps=max(1, int(round(save_fps))), dpi=150)
        else:
            raise ValueError("仅支持 .gif 或 .mp4")
    if show:
        plt.show()
    else:
        plt.close(fig)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="F1 双车手排位赛最快圈对比动画")
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--gp", type=str, required=True)
    parser.add_argument("--phase", type=str, default="Q3", choices=["Q1", "Q2", "Q3"])
    parser.add_argument("--drivers", type=str, nargs="+", required=True, help="1 或 2 个车手代码")
    parser.add_argument("--save", type=str, default="", help="输出 .gif 或 .mp4，不填则仅弹窗显示")
    parser.add_argument("--cache-dir", type=str, default=".fastf1_cache")
    args = parser.parse_args()
    run_comparison_animation(
        year=args.year,
        gp=args.gp,
        qualifying_phase=args.phase,
        drivers=args.drivers,
        cache_dir=args.cache_dir,
        save_path=args.save if args.save else None,
        show=True,
    )
