#!/usr/bin/env python3
"""
Animate a driver's fastest qualifying lap racing line on a track map.

Example:
    python qualifying_fastest_lap_animation.py \
        --year 2024 \
        --gp "Monaco" \
        --driver "VER" \
        --save monaco_ver_q_fastest.gif
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Tuple

import fastf1
import matplotlib.pyplot as plt
import matplotlib.collections as mcoll
from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
from matplotlib.patches import Wedge, Polygon
import numpy as np
import pandas as pd
from matplotlib.animation import FuncAnimation, PillowWriter


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Load Formula 1 qualifying data with FastF1 and animate the "
            "driver's fastest lap line on the track map."
        )
    )
    parser.add_argument("--year", type=int, required=True, help="Season year, e.g. 2024")
    parser.add_argument(
        "--gp",
        type=str,
        required=True,
        help='Grand Prix name as used by FastF1, e.g. "Monaco" or "Japanese Grand Prix"',
    )
    parser.add_argument(
        "--driver",
        type=str,
        required=True,
        help='Driver code, e.g. "VER", "HAM", "NOR"',
    )
    parser.add_argument(
        "--session",
        type=str,
        default="Q",
        help='Session identifier. Use "Q" for qualifying (default).',
    )
    parser.add_argument(
        "--cache-dir",
        type=str,
        default=".fastf1_cache",
        help="Directory used by FastF1 caching.",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Animation frames per second when saving.",
    )
    parser.add_argument(
        "--tail-length",
        type=int,
        default=40,
        help="Number of recent points to keep as trailing line.",
    )
    parser.add_argument(
        "--save",
        type=str,
        default="",
        help='Optional output file. Supports ".gif" and ".mp4". If omitted, only shows the animation window.',
    )
    parser.add_argument(
        "--heatmap",
        action="store_true",
        help="Color the line by speed (heatmap style, TV broadcast-like).",
    )
    parser.add_argument(
        "--track-width",
        type=float,
        default=120,
        help="Track width in 1/10m units (default 120 ≈ 12m, typical F1 width).",
    )
    parser.add_argument(
        "--car-style",
        type=str,
        default="arrow",
        choices=["arrow", "point"],
        help="Car marker: 'arrow' = directional shape, 'point' = simple dot.",
    )
    return parser


def _extract_time_seconds(pos_data: pd.DataFrame) -> np.ndarray:
    if "Time" in pos_data.columns:
        return pos_data["Time"].dt.total_seconds().to_numpy()
    if "SessionTime" in pos_data.columns:
        return pos_data["SessionTime"].dt.total_seconds().to_numpy()
    if "Date" in pos_data.columns:
        base = pos_data["Date"].iloc[0]
        return (pos_data["Date"] - base).dt.total_seconds().to_numpy()
    raise ValueError("Unable to find a valid time column in position data.")


def _prepare_lap_xy_and_time(lap: fastf1.core.Lap) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    pos_data = lap.get_pos_data().dropna(subset=["X", "Y"]).reset_index(drop=True)
    time_s = _extract_time_seconds(pos_data)
    x = pos_data["X"].to_numpy()
    y = pos_data["Y"].to_numpy()

    # Ensure strictly increasing time for interpolation.
    monotonic_mask = np.diff(time_s, prepend=time_s[0] - 1e-9) > 0
    x = x[monotonic_mask]
    y = y[monotonic_mask]
    time_s = time_s[monotonic_mask]

    if len(time_s) < 2:
        raise ValueError("Not enough position samples to animate this lap.")

    return x, y, time_s


def _prepare_lap_xy_time_speed(
    lap: fastf1.core.Lap,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Get X, Y, time, and Speed from merged telemetry (for heatmap mode)."""
    tel = lap.get_telemetry()
    tel = tel.dropna(subset=["X", "Y", "Speed"]).reset_index(drop=True)
    if len(tel) < 2:
        raise ValueError("Not enough telemetry samples with X, Y, Speed for heatmap.")
    time_s = _extract_time_seconds(tel)
    x = tel["X"].to_numpy()
    y = tel["Y"].to_numpy()
    speed = tel["Speed"].to_numpy()

    monotonic_mask = np.diff(time_s, prepend=time_s[0] - 1e-9) > 0
    x = x[monotonic_mask]
    y = y[monotonic_mask]
    time_s = time_s[monotonic_mask]
    speed = speed[monotonic_mask]

    return x, y, time_s, speed


def _prepare_full_telemetry(lap: fastf1.core.Lap) -> pd.DataFrame:
    """Get full telemetry (X, Y, Speed, Throttle, Brake, nGear, RPM, DRS) for dashboard."""
    tel = lap.get_telemetry()
    required = ["X", "Y", "Speed", "Throttle", "Brake", "nGear"]
    missing = [c for c in required if c not in tel.columns]
    if missing:
        raise ValueError(f"Telemetry missing columns: {missing}")
    tel = tel.dropna(subset=required).reset_index(drop=True)
    if len(tel) < 2:
        raise ValueError("Not enough telemetry samples for dashboard.")
    time_s = _extract_time_seconds(tel)
    monotonic_mask = np.diff(time_s, prepend=time_s[0] - 1e-9) > 0
    return tel.loc[monotonic_mask].reset_index(drop=True)


def _track_centerline_to_polygon(x: np.ndarray, y: np.ndarray, half_width: float) -> np.ndarray:
    """Build track polygon from centerline (x,y) with given half-width (1/10m units)."""
    n = len(x)
    if n < 3:
        return np.array([[0, 0]])
    # Tangent at each point (forward difference at ends)
    dx = np.zeros(n)
    dy = np.zeros(n)
    dx[:-1] = np.diff(x)
    dy[:-1] = np.diff(y)
    dx[-1], dy[-1] = dx[-2], dy[-2]
    dx[0], dy[0] = dx[1], dy[1]
    # Perpendicular (normalized), left = (-dy, dx)
    r = np.sqrt(dx**2 + dy**2) + 1e-12
    nx, ny = -dy / r, dx / r
    x_left = x + nx * half_width
    y_left = y + ny * half_width
    x_right = x - nx * half_width
    y_right = y - ny * half_width
    # Closed polygon: left edge forward, right edge backward
    verts = np.vstack([
        np.column_stack([x_left, y_left]),
        np.column_stack([x_right[::-1], y_right[::-1]]),
    ])
    return verts


def _compute_heading(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Compute heading angle (radians, 0=east) at each point from position sequence."""
    n = len(x)
    dx = np.zeros(n)
    dy = np.zeros(n)
    dx[:-1] = np.diff(x)
    dy[:-1] = np.diff(y)
    dx[-1], dy[-1] = dx[-2], dy[-2]
    dx[0], dy[0] = dx[1], dy[1]
    return np.arctan2(dy, dx)


def _create_telemetry_dashboard(
    ax_dash: plt.Axes,
    throttle: np.ndarray,
    brake: np.ndarray,
    speed: np.ndarray,
    gear: np.ndarray,
    rpm: np.ndarray | None,
    drs: np.ndarray | None,
) -> dict:
    """Create F1-style telemetry dashboard (no watermark). Returns updatable artists."""
    ax_dash.set_xlim(-1.5, 1.5)
    ax_dash.set_ylim(-1.2, 1.2)
    ax_dash.set_aspect("equal")
    ax_dash.axis("off")
    ax_dash.set_facecolor("#1a1a1a")

    # Arc geometry: left=throttle (angles 220->320), right=brake (40->140)
    cx, cy = 0.0, 0.0
    r_outer, r_inner = 1.0, 0.75

    # Static throttle arc (blue track)
    wedge_throttle_bg = Wedge(
        (cx, cy), r_outer, 220, 320, width=r_outer - r_inner,
        facecolor="#2a3a5a", edgecolor="#4a6a9a", linewidth=1,
    )
    ax_dash.add_patch(wedge_throttle_bg)
    ax_dash.text(-1.0, -0.3, "0", color="#888", fontsize=8, ha="center")
    ax_dash.text(-1.0, 0.35, "100", color="#888", fontsize=8, ha="center")
    ax_dash.text(-1.15, 0.0, "THROTTLE", color="#4ade80", fontsize=7, rotation=90, va="center")

    # Static brake arc (dark track)
    wedge_brake_bg = Wedge(
        (cx, cy), r_outer, 40, 140, width=r_outer - r_inner,
        facecolor="#2a2a2a", edgecolor="#555", linewidth=1,
    )
    ax_dash.add_patch(wedge_brake_bg)
    ax_dash.text(1.0, -0.3, "0", color="#888", fontsize=8, ha="center")
    ax_dash.text(1.0, 0.35, "100", color="#888", fontsize=8, ha="center")
    ax_dash.text(1.15, 0.0, "BRAKE", color="#fff", fontsize=7, rotation=-90, va="center")

    # Dynamic throttle fill (green) - updated each frame
    wedge_throttle_fill = Wedge(
        (cx, cy), r_outer, 220, 220, width=r_outer - r_inner,
        facecolor="#4ade80", edgecolor="none",
    )
    ax_dash.add_patch(wedge_throttle_fill)

    # Dynamic brake fill (red) - updated each frame
    wedge_brake_fill = Wedge(
        (cx, cy), r_outer, 40, 40, width=r_outer - r_inner,
        facecolor="#ef4444", edgecolor="none",
    )
    ax_dash.add_patch(wedge_brake_fill)

    # Center text (updated each frame)
    txt_speed = ax_dash.text(0, 0.5, "0", fontsize=22, color="white", ha="center", va="center", fontweight="bold")
    ax_dash.text(0, 0.35, "KMH", fontsize=8, color="#aaa", ha="center", va="center")
    txt_rpm = ax_dash.text(0, 0.08, "0", fontsize=12, color="white", ha="center", va="center")
    ax_dash.text(0, -0.05, "RPM", fontsize=7, color="#aaa", ha="center", va="center")
    txt_drs = ax_dash.text(0, -0.22, "DRS", fontsize=7, color="#666", ha="center", va="center",
                           bbox=dict(boxstyle="round,pad=0.2", facecolor="#222", edgecolor="#444"))
    txt_gear = ax_dash.text(0, -0.45, "N", fontsize=11, color="white", ha="center", va="center")
    ax_dash.text(0, -0.52, "GEAR", fontsize=7, color="#aaa", ha="center", va="center")

    artists = {
        "wedge_throttle": wedge_throttle_fill,
        "wedge_brake": wedge_brake_fill,
        "txt_speed": txt_speed,
        "txt_rpm": txt_rpm,
        "txt_drs": txt_drs,
        "txt_gear": txt_gear,
    }
    return artists


def _update_dashboard(
    artists: dict,
    frame_idx: int,
    throttle: np.ndarray,
    brake: np.ndarray,
    speed: np.ndarray,
    gear: np.ndarray,
    rpm: np.ndarray | None,
    drs: np.ndarray | None,
) -> list:
    """Update dashboard with values for current frame."""
    t = np.clip(throttle[frame_idx], 0, 100)
    b = np.clip(brake[frame_idx], 0, 100)
    # Throttle wedge: 220 + (320-220)*t/100
    artists["wedge_throttle"].set_theta2(220 + 100 * t / 100)
    # Brake wedge: 40 to 40 + 100*b/100
    artists["wedge_brake"].set_theta2(40 + 100 * b / 100)
    artists["txt_speed"].set_text(f"{int(round(speed[frame_idx]))}")
    if rpm is not None:
        artists["txt_rpm"].set_text(f"{int(round(rpm[frame_idx]))}")
    if drs is not None:
        on = bool(round(drs[frame_idx]))
        artists["txt_drs"].set_color("#4ade80" if on else "#666")
    g = gear[frame_idx]
    artists["txt_gear"].set_text("N" if g == 0 else str(int(g)))
    return [
        artists["wedge_throttle"],
        artists["wedge_brake"],
        artists["txt_speed"],
        artists["txt_rpm"],
        artists["txt_drs"],
        artists["txt_gear"],
    ]


def main() -> None:
    args = _build_parser().parse_args()

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache_dir))

    session = fastf1.get_session(args.year, args.gp, args.session)
    session.load(laps=True, telemetry=True, weather=False, messages=False)

    driver = args.driver.upper()
    lap = session.laps.pick_drivers(driver).pick_fastest()
    if lap.empty:
        raise ValueError(f"No laps found for driver '{driver}' in this session.")

    tel = _prepare_full_telemetry(lap)
    time_s = _extract_time_seconds(tel)
    x = tel["X"].to_numpy()
    y = tel["Y"].to_numpy()
    speed_raw = tel["Speed"].to_numpy()
    throttle_raw = tel["Throttle"].clip(0, 100).to_numpy()
    brake_raw = (tel["Brake"].astype(float) * 100).to_numpy()  # bool -> 0 or 100
    gear_raw = tel["nGear"].fillna(0).to_numpy()
    rpm_raw = tel["RPM"].to_numpy() if "RPM" in tel.columns else None
    drs_raw = tel["DRS"].to_numpy() if "DRS" in tel.columns else None

    # Build an evenly spaced timeline for a smooth animation.
    total_duration = float(time_s[-1] - time_s[0])
    frame_count = max(2, int(total_duration * max(1, args.fps)))
    t_uniform = np.linspace(time_s[0], time_s[-1], frame_count)
    x_uniform = np.interp(t_uniform, time_s, x)
    y_uniform = np.interp(t_uniform, time_s, y)
    speed_uniform = np.interp(t_uniform, time_s, speed_raw)
    throttle_uniform = np.interp(t_uniform, time_s, throttle_raw)
    brake_uniform = np.interp(t_uniform, time_s, brake_raw)
    gear_uniform = np.interp(t_uniform, time_s, gear_raw)
    rpm_uniform = np.interp(t_uniform, time_s, rpm_raw) if rpm_raw is not None else None
    drs_uniform = np.interp(t_uniform, time_s, drs_raw) if drs_raw is not None else None

    heading_uniform = _compute_heading(x_uniform, y_uniform)

    fig = plt.figure(figsize=(12, 8))
    fig.patch.set_facecolor("#101010")
    gs = fig.add_gridspec(1, 2, width_ratios=[1.4, 1], wspace=0.15)
    ax = fig.add_subplot(gs[0])
    ax_dash = fig.add_subplot(gs[1])
    ax.set_facecolor("#101010")
    ax.set_aspect("equal", adjustable="datalim")
    ax.axis("off")

    # Wide track polygon (tarmac)
    half_width = max(1, args.track_width / 2)
    track_verts = _track_centerline_to_polygon(x, y, half_width)
    track_poly = Polygon(
        track_verts,
        facecolor="#2a2a2a",
        edgecolor="#555",
        linewidth=1.0,
        zorder=0,
    )
    ax.add_patch(track_poly)
    # Centerline (thin) for reference
    ax.plot(x, y, color="#555", linewidth=0.8, alpha=0.5, zorder=1)

    if args.heatmap:
        # Speed heatmap: red (slow) -> yellow -> green (fast), TV broadcast style
        cmap = plt.cm.RdYlGn
        vmin, vmax = float(np.nanmin(speed_uniform)), float(np.nanmax(speed_uniform))
        norm = Normalize(vmin=vmin, vmax=vmax)

        line_collection = mcoll.LineCollection([], linewidths=3.0, cmap=cmap, norm=norm, zorder=5)
        ax.add_collection(line_collection)

        # Speed legend
        cbar = fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), ax=ax, shrink=0.4, pad=0.05)
        cbar.set_label("Speed (km/h)", color="white", fontsize=9)
        cbar.ax.yaxis.set_tick_params(color="white")
        plt.setp(plt.getp(cbar.ax.axes, "yticklabels"), color="white")

        trail_line = None
    else:
        trail_line, = ax.plot([], [], color="#00d4ff", linewidth=3.0, zorder=5)
        line_collection = None

    # Car marker: arrow (directional) or point
    if args.car_style == "arrow":
        # Local car shape: nose +x, length~50, width~24 (1/10m)
        car_local = np.array([[45, 0], [-35, 14], [-25, 0], [-35, -14]])
        car_marker = Polygon(
            car_local,
            facecolor="#e63946",
            edgecolor="#fff",
            linewidth=1.2,
            zorder=15,
        )
        ax.add_patch(car_marker)
        marker = None  # Use car_marker
    else:
        car_marker = None
        marker, = ax.plot([], [], "o", color="#e63946", markersize=14, markeredgecolor="#fff",
                          markeredgewidth=1.5, zorder=15)

    lap_time = lap["LapTime"]
    lap_time_text = "N/A" if pd.isna(lap_time) else str(lap_time)
    title = (
        f"{session.event['EventName']} {args.year} {args.session} | "
        f"{driver} fastest lap: {lap_time_text}"
    )
    if args.heatmap:
        title += " | Speed heatmap"
    ax.set_title(title, color="white", fontsize=11, pad=12)

    # Telemetry dashboard (no watermark)
    dash_artists = _create_telemetry_dashboard(
        ax_dash,
        throttle_uniform,
        brake_uniform,
        speed_uniform,
        gear_uniform,
        rpm_uniform,
        drs_uniform,
    )

    def _set_car_marker(frame_idx: int):
        cx, cy = x_uniform[frame_idx], y_uniform[frame_idx]
        h = heading_uniform[frame_idx]
        cos_h, sin_h = np.cos(h), np.sin(h)
        if car_marker is not None:
            # Rotate and translate car shape
            rot = np.array([[cos_h, -sin_h], [sin_h, cos_h]])
            verts = car_local @ rot.T + np.array([cx, cy])
            car_marker.set_xy(verts)
        else:
            marker.set_data([cx], [cy])

    def init():
        if trail_line is not None:
            trail_line.set_data([], [])
        if line_collection is not None:
            line_collection.set_segments([])
            line_collection.set_array(np.array([]))
        _set_car_marker(0)
        dash_out = _update_dashboard(
            dash_artists, 0,
            throttle_uniform, brake_uniform, speed_uniform,
            gear_uniform, rpm_uniform, drs_uniform,
        )
        out = dash_out
        if car_marker is not None:
            out.append(car_marker)
        else:
            out.append(marker)
        if trail_line is not None:
            out.append(trail_line)
        if line_collection is not None:
            out.append(line_collection)
        return out

    def update(frame_idx: int):
        start = max(0, frame_idx - max(1, args.tail_length))
        xs = x_uniform[start : frame_idx + 1]
        ys = y_uniform[start : frame_idx + 1]

        if line_collection is not None:
            segments = [
                [(xs[i], ys[i]), (xs[i + 1], ys[i + 1])]
                for i in range(len(xs) - 1)
            ]
            seg_speeds = (
                (speed_uniform[start : frame_idx] + speed_uniform[start + 1 : frame_idx + 1]) / 2
                if frame_idx > start
                else np.array([])
            )
            line_collection.set_segments(segments)
            line_collection.set_array(seg_speeds)
            line_collection.set_linewidth(3.0)
        elif trail_line is not None:
            trail_line.set_data(xs, ys)

        _set_car_marker(frame_idx)
        dash_out = _update_dashboard(
            dash_artists, frame_idx,
            throttle_uniform, brake_uniform, speed_uniform,
            gear_uniform, rpm_uniform, drs_uniform,
        )
        out = list(dash_out)
        if car_marker is not None:
            out.append(car_marker)
        else:
            out.append(marker)
        if trail_line is not None:
            out.append(trail_line)
        if line_collection is not None:
            out.append(line_collection)
        return out

    anim = FuncAnimation(
        fig,
        update,
        frames=frame_count,
        init_func=init,
        interval=1000 / max(1, args.fps),
        blit=True,
        repeat=True,
    )

    if args.save:
        output_path = Path(args.save)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        suffix = output_path.suffix.lower()
        if suffix == ".gif":
            anim.save(output_path, writer=PillowWriter(fps=max(1, args.fps)))
        elif suffix == ".mp4":
            anim.save(output_path, fps=max(1, args.fps), dpi=150)
        else:
            raise ValueError("Unsupported --save extension. Use .gif or .mp4")
        print(f"Saved animation to: {output_path.resolve()}")

    plt.show()


if __name__ == "__main__":
    main()
