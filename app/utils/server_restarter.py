# 官网：https://www.yuturuishi.com
# 微信：yuturuishi
# gitee开源地址：https://gitee.com/yuturuishi/rebucca
# github开源地址：https://github.com/yuturuishi/rebucca
"""服务重启守护进程（独立脚本，由 SystemView.api_openRestart 以分离进程拉起）。

职责：主进程退出后监视服务端口——
  1. 等待端口下线（旧服务退出）；
  2. 再观察一段时间，若服务自行恢复（runserver autoreloader 以退出码 3 重载的场景），
     守护进程直接退出、不做任何事；
  3. 若超时仍未恢复（--noreload / 裸进程场景），按注入的启动命令重新拉起服务。

用法：
  python server_restarter.py <port> <wait_down_sec> <wait_up_sec> <spec_json>
spec_json 格式：{"argv": [...], "cwd": "..."}
"""
import json
import os
import socket
import subprocess
import sys
import time

# Windows 分离进程标志
if os.name == "nt":
    _CREATE_NEW_PROCESS_GROUP = 0x00000200
    _DETACHED_PROCESS = 0x00000008
else:
    _CREATE_NEW_PROCESS_GROUP = 0
    _DETACHED_PROCESS = 0


def port_alive(port, host="127.0.0.1"):
    try:
        with socket.create_connection((host, int(port)), timeout=1.0):
            return True
    except Exception:
        return False


def main():
    port = int(sys.argv[1])
    wait_down = float(sys.argv[2])
    wait_up = float(sys.argv[3])
    with open(sys.argv[4], "r", encoding="utf-8") as f:
        spec = json.load(f)
    argv = spec.get("argv") or []
    cwd = spec.get("cwd") or os.getcwd()
    if not argv:
        return

    # 1) 等旧服务下线
    t0 = time.time()
    while time.time() - t0 < wait_down:
        if not port_alive(port):
            break
        time.sleep(0.5)

    # 2) 观察是否自动恢复（autoreloader 重载场景）
    t0 = time.time()
    while time.time() - t0 < wait_up:
        if port_alive(port):
            return

    # 3) 未恢复 → 主动拉起
    flags = _DETACHED_PROCESS | _CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    log_path = os.path.join(cwd, "log_restart_helper.txt")
    try:
        lf = open(log_path, "a", encoding="utf-8")
        subprocess.Popen(
            argv, cwd=cwd, stdout=lf, stderr=lf,
            creationflags=flags,
            start_new_session=(os.name != "nt"),
        )
    except Exception:
        pass


if __name__ == "__main__":
    main()
