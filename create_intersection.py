import os
import traci
import random
from pathlib import Path

# 设置工作目录为当前文件所在目录
BASE_DIR = Path(os.path.abspath('./test'))
SUMO_PATH = "C:\Program Files (x86)\Eclipse\Sumo"
os.environ["SUMO_HOME"] = SUMO_PATH
sumo_bin_path = os.path.join(SUMO_PATH, 'bin')
if sumo_bin_path not in os.environ["PATH"]:
    os.environ["PATH"] += os.pathsep + sumo_bin_path

def build_network():
    os.system(
        f'netconvert '
        f'-n "{BASE_DIR / "nodes.nod.xml"}" '
        f'-e "{BASE_DIR / "edges.edg.xml"}" '
        f'-x "{BASE_DIR / "connections.con.xml"}" '
        f'--no-turnarounds true '  # 👈 禁止自动生成掉头
        f'-o "{BASE_DIR / "intersection.net.xml"}"'

    )
def run_sumo():
    sumo_cmd = ["sumo-gui", "-c", f"{BASE_DIR}\\intersection.sumocfg", "--start"]
    traci.start(sumo_cmd)
    step = 0
    while step < 2000:
        traci.simulationStep()

        # 每10个step新增一辆随机车辆（演示）
        if step % 10 == 0:
            vid = f"dyn_{step}"

            # ✅ 所有可能的转向路径（from_edge, to_edge）组合
            # 格式: (起始边, 终点边, 描述)
            routes = [
                # 北进口
                ("n2center", "center2s", "北→南 直行"),
                ("n2center", "center2e", "北→东 右转"),
                ("n2center", "center2w", "北→西 左转"),

                # 南进口
                ("s2center", "center2n", "南→北 直行"),
                ("s2center", "center2w", "南→西 右转"),
                ("s2center", "center2e", "南→东 左转"),

                # 东进口
                ("e2center", "center2w", "东→西 直行"),
                ("e2center", "center2s", "东→南 右转"),
                ("e2center", "center2n", "东→北 左转"),

                # 西进口
                ("w2center", "center2e", "西→东 直行"),
                ("w2center", "center2n", "西→北 右转"),
                ("w2center", "center2s", "西→南 左转"),
            ]
            # 随机选一个路径
            from_edge, to_edge, desc = random.choice(routes)
            rid = f"r_{vid}"
            # 添加路径（两段：进口段 + 出口段）
            traci.route.add(rid, [from_edge, to_edge])
            traci.vehicle.add(vid, rid, typeID="car")
            # 可选：打印生成的车辆信息（调试用）
            # print(f"[Step {step}] 生成车辆 {vid}: {desc}")
        step += 1
    traci.close()
    print("仿真结束")
if __name__ == "__main__":

    build_network()
    run_sumo()
