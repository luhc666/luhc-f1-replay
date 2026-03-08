#!/usr/bin/env python3
"""
F1 双车手最快圈对比 - Streamlit Web UI
"""
import os
import subprocess
import sys
from pathlib import Path

import streamlit as st
import fastf1
import pandas as pd

st.set_page_config(page_title="F1 最快圈对比", page_icon="🏎️", layout="centered")

st.title("🏎️ F1 排位赛最快圈对比")
st.caption("选择年份、比赛、排位赛阶段（Q1/Q2/Q3）与最多 2 名车手，生成赛道对比动画")

# 缓存目录
CACHE_DIR = Path(".fastf1_cache")


@st.cache_data(ttl=86400)  # 24h
def get_event_schedule(year: int):
    try:
        schedule = fastf1.get_event_schedule(year)
        if schedule is None or len(schedule) == 0:
            return []
        return schedule[["EventName", "EventDate", "Country"]].to_dict("records")
    except Exception:
        return []


@st.cache_data(ttl=3600)
def get_session_drivers(year: int, gp: str, qualifying_phase: str):
    """返回当前 Q 的排名与车手列表（均按该 Q 最快圈排序）。"""
    try:
        fastf1.Cache.enable_cache(str(CACHE_DIR))
        sess = fastf1.get_session(year, gp, "Q")
        sess.load()
        if sess.laps is None or sess.laps.empty:
            return []
        phase = qualifying_phase.upper()
        if phase not in ("Q1", "Q2", "Q3"):
            return []
        q1, q2, q3 = sess.laps.split_qualifying_sessions()
        phase_laps = {"Q1": q1, "Q2": q2, "Q3": q3}.get(phase)
        if phase_laps is None or phase_laps.empty:
            return [], []

        col = "Abbreviation" if "Abbreviation" in phase_laps.columns else "Driver"
        raw_driver = phase_laps[col]
        normalized_driver = raw_driver.fillna("").astype(str).str.strip().str.upper()
        driver_codes = sorted(set(d for d in normalized_driver.tolist() if d))

        ranking_raw = []
        for driver in driver_codes:
            driver_laps = phase_laps[normalized_driver == driver]
            if driver_laps.empty:
                continue
            fastest_lap = driver_laps.pick_fastest()
            lap_time = fastest_lap.get("LapTime") if fastest_lap is not None else pd.NaT
            ranking_raw.append({"driver": driver, "lap_time": lap_time})

        ranking_raw.sort(key=lambda r: (pd.isna(r["lap_time"]), r["lap_time"]))

        ranking = []
        for i, item in enumerate(ranking_raw, start=1):
            lap_time = item["lap_time"]
            if pd.isna(lap_time):
                lap_time_text = "N/A"
            else:
                total_seconds = lap_time.total_seconds()
                minutes = int(total_seconds // 60)
                seconds = total_seconds - minutes * 60
                lap_time_text = f"{minutes}:{seconds:06.3f}"
            ranking.append({"排名": i, "车手": item["driver"], "最快圈": lap_time_text})

        drivers_sorted = [r["车手"] for r in ranking]
        return drivers_sorted, ranking
    except Exception as e:
        st.error(f"加载排位赛数据失败: {e}")
        return [], []


QUALIFYING_PHASES = {"Q1": "Q1", "Q2": "Q2", "Q3": "Q3"}

col1, col2, col3 = st.columns(3)

with col1:
    year = st.selectbox(
        "年份",
        options=list(range(2025, 2017, -1)),
        index=2,
        format_func=lambda x: str(x),
    )

with col2:
    schedule = get_event_schedule(year)
    if not schedule:
        st.warning(f"{year} 年暂无赛历数据")
        events = []
    else:
        events = [s["EventName"] for s in schedule]
    gp = st.selectbox(
        "分站",
        options=events if events else [""],
        format_func=lambda x: x or "（无数据）",
    )

with col3:
    session_key = st.selectbox(
        "排位赛阶段",
        options=list(QUALIFYING_PHASES.keys()),
        format_func=lambda x: QUALIFYING_PHASES.get(x, x),
    )

if gp and events:
    drivers_available, ranking_rows = get_session_drivers(year, gp, session_key)
else:
    drivers_available = []
    ranking_rows = []

if drivers_available:
    selected = st.multiselect(
        "车手（最多选 2 人）",
        options=drivers_available,
        max_selections=2,
        default=drivers_available[:2] if len(drivers_available) >= 2 else drivers_available[:1],
    )
else:
    selected = []
    st.info("请先选择年份、分站和排位赛阶段以加载车手列表")

if ranking_rows:
    st.markdown(f"### {session_key} 当前排名")
    st.dataframe(pd.DataFrame(ranking_rows), use_container_width=True, hide_index=True)

if st.button("生成对比动画", type="primary", use_container_width=True):
    if not selected:
        st.error("请至少选择 1 名车手")
    elif len(selected) > 2:
        st.error("最多选择 2 名车手")
    elif not gp or gp not in events:
        st.error("请选择有效的分站")
    else:
        with st.spinner("正在拉取数据，将打开新窗口播放动画（关闭窗口后返回）..."):
            try:
                cmd = [
                    sys.executable, "-m", "f1_comparison",
                    "--year", str(year),
                    "--gp", gp,
                    "--phase", session_key,
                    "--drivers", *selected,
                    "--cache-dir", str(CACHE_DIR),
                ]
                # 覆盖 MPLBACKEND：Streamlit 设为 Agg，子进程需用 GUI 后端才能弹窗
                env = dict(os.environ)
                env["MPLBACKEND"] = "MacOSX" if sys.platform == "darwin" else "TkAgg"
                result = subprocess.run(cmd, cwd=Path(__file__).resolve().parent, env=env)
                if result.returncode == 0:
                    st.success("动画已播放完成")
                else:
                    st.error("生成或播放失败")
            except Exception as e:
                st.error(f"启动失败: {e}")
                import traceback
                st.code(traceback.format_exc())
