import os
import subprocess
import threading

def run_task(signal, traj, scale,gui):
    signal_flag = "--no-signal" if not signal else ""
    traj_flag = "--no-traj" if not traj else ""
    gui_flag = "--no-gui" if not gui else ""
    command = f"C:/ProgramData/anaconda3/envs/ENV2026/python.exe cav_plus.py {signal_flag} {traj_flag} --scale {scale} {gui_flag}"
    print(f"Running: {command}")
    subprocess.run(command, shell=True)

# 批量用命令行运行，8个并行
# tasks = [(signal, traj, scale,False) for signal in [True, False] for traj in [True, False] for scale in [1.0, 1.2]]
tasks = [(signal,traj,88/52,False) for signal in [True, False] for traj in [True, False]]
threads = []

for task in tasks:
# if True:
    t = threading.Thread(target=run_task, args=task)
    threads.append(t)
    t.start()

for t in threads:
    t.join()
