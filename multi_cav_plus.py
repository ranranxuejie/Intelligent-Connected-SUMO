import os
import subprocess
import threading

def run_task(signal, traj, scale,gui):
    signal_flag = "--signal" if signal else ""
    traj_flag = "--traj" if traj else ""
    gui_flag = "--gui" if gui else ""
    command = f"C:/ProgramData/anaconda3/envs/ENV2026/python.exe cav_plus.py {signal_flag} {traj_flag} --scale {scale} {gui_flag}"
    print(f"Running: {command}")
    subprocess.run(command, shell=True)

# 批量用命令行运行，8个并行
tasks = [(signal, traj, scale,False) for signal in [True, False] for traj in [True, False] for scale in [1.0, 1.2]]
threads = []

for task in tasks:
    t = threading.Thread(target=run_task, args=task)
    threads.append(t)
    t.start()

for t in threads:
    t.join()
