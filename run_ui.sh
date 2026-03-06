#!/bin/bash
# 启动 F1 双车手对比 Web UI
cd "$(dirname "$0")"

# 如通过 Cursor 远程/端口转发，加 --server.address 0.0.0.0
# 若 8501 被占用，加 --server.port 8502
exec streamlit run app.py --server.headless true
