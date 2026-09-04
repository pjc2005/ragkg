#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务进度工具: 任务写状态到 JSON 文件, 供仪表盘 collect.py 读取渲染.

任务脚本用法:
  from task_progress import Progress
  p = Progress("图谱重建", total=28)   # 启动时 reset
  for i, chunk in enumerate(chunks):
      p.tick(chunk_text[:40])           # 每处理一块更新一次
  p.done()
"""
import json, os, time

PROGRESS_FILE = "<your-project-path>/ragkg/task_progress.json"


def _write(data):
    tmp = PROGRESS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PROGRESS_FILE)


def clear(id=None):
    """清除指定任务或全部进度. 返回清除后的状态."""
    if os.path.exists(PROGRESS_FILE):
        try:
            cur = json.load(open(PROGRESS_FILE, encoding="utf-8"))
        except Exception:
            cur = {}
    else:
        cur = {}
    if id:
        cur.pop(id, None)
        _write(cur)
    else:
        if os.path.exists(PROGRESS_FILE):
            os.remove(PROGRESS_FILE)
        cur = {}
    return cur


def read_all():
    if os.path.exists(PROGRESS_FILE):
        try:
            return json.load(open(PROGRESS_FILE, encoding="utf-8"))
        except Exception:
            return {}
    return {}


class Progress:
    def __init__(self, name, total, id=None, unit="块", started=None):
        self.id = id or name
        self.name = name
        self.total = max(total, 1)
        self.unit = unit
        self.current = 0
        self.status = "running"   # running | done | error
        self.message = "启动"
        self.started = started or time.time()
        self._heartbeat()

    def _heartbeat(self):
        self._write()

    def _write(self):
        pct = round(self.current * 100.0 / self.total, 1)
        data = read_all()
        data[self.id] = {
            "id": self.id, "name": self.name,
            "current": self.current, "total": self.total,
            "pct": pct, "percent": pct,
            "status": self.status, "message": self.message,
            "unit": self.unit, "started": self.started,
            "updated": time.time(),
        }
        _write(data)

    def tick(self, message=None, n=1):
        self.current += n
        if message:
            self.message = message
        self._write()

    def set(self, message, current=None):
        if current is not None:
            self.current = current
        self.message = message
        self._write()

    def done(self, message="完成"):
        self.current = self.total
        self.status = "done"
        self.message = message
        self._write()

    def error(self, message):
        self.status = "error"
        self.message = message
        self._write()