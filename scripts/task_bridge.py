#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仪表盘任务进度桥接: 监控重建/提炼等长任务, 用 DB 实时行数+进程状态反映进度,
写到 task_progress.json 供仪表盘读取. 轮询运行.
用法: python3 scripts/task_bridge.py   (配合 systemd 常驻, 或 Ctrl-C 停止)
"""
import json, os, sys, subprocess, time, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "<your-project-path>/ragkg")
from task_progress import Progress, read_all

INTERVAL = 5

def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""

def pg_count(t):
    o = sh(f"psql -d ragkg -Atc 'SELECT count(*) FROM {t};' 2>/dev/null")
    return int(o) if o.isdigit() else 0

def proc_alive(pat):
    try:
        subprocess.run(f"pgrep -f '{pat}' >/dev/null", shell=True, timeout=5)
        return True
    except Exception:
        return False

def main():
    print("task_bridge 启动 (5s 轮询). Ctrl-C 停止", flush=True)
    last_nodes = None
    while True:
        try:
            rebuild = proc_alive("rebuild_graph.py")
            if rebuild:
                nodes, edges = pg_count("nodes"), pg_count("edges")
                started = time.time() - 120  # 近似开始时间
                cur = read_all()
                t = cur.get("graph_rebuild") or {}
                # 用 nodes 数作为进度; total 未知时用增量估算
                if last_nodes is not None and nodes > last_nodes:
                    rate = nodes - last_nodes
                    # 估算总量(假设每 run 目标是达到数千则放缓)
                last_nodes = nodes
                total = t.get("total") or 3000
                p = Progress("图谱重建", total=total, id="graph_rebuild", started=t.get("started") or started)
                p.set(f"已构建 {nodes} 节点 / {edges} 边 · 图片抽取中", current=min(nodes, total))
            elif read_all().get("graph_rebuild"):
                # 重建结束 -> 标记完成(若还 running)
                cur = read_all()
                if cur.get("graph_rebuild", {}).get("status") == "running":
                    p = Progress("图谱重建", total=100, id="graph_rebuild")
                    p.done("图谱重建完成")
        except Exception as e:
            print("bridge err:", e, flush=True)
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()