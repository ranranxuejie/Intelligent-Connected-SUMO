
MAX_EXTENSION = 15          # 最大延长秒数
EXTEND_THRESHOLD = 3        # 延长触发阈值（剩余绿灯 < X 秒）
EARLY_GREEN_DIST = 100       # 红灯早断触发距离（米）
QUEUE_THRESHOLD = 1         # 禁止红灯早断的队列长度阈值（超过X辆车排队时不执行早断）

import traci
import time
import json
from analyze_results import analyze_tripinfo, analyze_queue
# ===== 全局状态 =====
_bus_tsp_state = {}         # (tls_id, bus_id) -> {total_extended: float}
# 历史记录
_bus_tsp_history = {}       # (tls_id, bus_id) -> [ {time: float, total_extended: float} ]
OUTPUT_FOLDER = f"output/{time.strftime('%Y%m%d_%H%M%S')}/"
import os
import shutil
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
# 保存当前参数
def save_current_params():
    with open(OUTPUT_FOLDER + "params.txt", "w") as f:
        f.write(f"MAX_EXTENSION={MAX_EXTENSION}\n")
        f.write(f"EXTEND_THRESHOLD={EXTEND_THRESHOLD}\n")
        f.write(f"EARLY_GREEN_DIST={EARLY_GREEN_DIST}\n")
        f.write(f"QUEUE_THRESHOLD={QUEUE_THRESHOLD}\n")
        f.write(f"BUS_FIRST={BUS_FIRST}\n")
    # copy一份当前的xml和sumocfg配置文件
    shutil.copy("test/crossroad.net.xml", OUTPUT_FOLDER + "crossroad.net.xml")
    shutil.copy("test/traffic.rou.xml", OUTPUT_FOLDER + "traffic.rou.xml")
    shutil.copy("test/traffic_light.add.xml", OUTPUT_FOLDER + "traffic_light.add.xml")
    shutil.copy("test/bus_stops.add.xml", OUTPUT_FOLDER + "bus_stops.add.xml")
    shutil.copy("crossroad_simulation.sumocfg", OUTPUT_FOLDER + "crossroad_simulation.sumocfg")

def is_bus_lane(lane_id):
    # 方法2（更安全）：再检查是否允许 bus
    if "in_1" in lane_id:
        return True
    else:
        return False
def is_current_green_lane_empty(green_lanes):
    """
    检查所有绿灯车道是否无车排队
    green_lanes: 绿灯车道ID列表
    返回：True（无排队）/ False（有排队）
    """
    for lane_id in green_lanes:
        # 获取车道的排队长度（sumo内置：静止或低速行驶的车辆总长度，单位米）
        queue_length = (traci.lane.getLastStepHaltingNumber(lane_id))
        # 也可以用车辆数判断：traci.lane.getLastStepVehicleNumber(lane_id) > 0
        if queue_length > QUEUE_THRESHOLD:
            print(f"[TSP] 当前绿灯车道 {lane_id} 有排队（长度：{queue_length:.1f}m），不执行红灯早断")
            return False
    return True


def analyze_result():
    print("正在分析tripinfo.xml...")
    trip_stats = analyze_tripinfo(f"{OUTPUT_FOLDER}tripinfo.xml")

    # 分析queue.xml
    print("\n正在分析queue.xml...")
    queue_stats = analyze_queue(f"{OUTPUT_FOLDER}queue.xml")

    # 保存分析结果到JSON文件

    with open(f"{OUTPUT_FOLDER}queue_stats.json", "w", encoding="utf-8") as f:
        json.dump(queue_stats, f, ensure_ascii=False, indent=4)

    with open(f"{OUTPUT_FOLDER}trip_stats.json", "w", encoding="utf-8") as f:
        json.dump(trip_stats, f, ensure_ascii=False, indent=4)

    with open(f"{OUTPUT_FOLDER}bus_tsp_history.json", "w") as f:
        json.dump(_bus_tsp_history, f, indent=4)

def get_current_green_lanes(tls_id, current_phase):
    """
    获取当前相位的所有绿灯车道（state为'G'或'g'）
    返回：绿灯车道ID列表
    """
    controlled_links = traci.trafficlight.getControlledLinks(tls_id)
    green_lanes = []
    state_str = current_phase.state

    for idx, link in enumerate(controlled_links):
        # 确保索引不越界，且当前位置是绿灯
        if idx < len(state_str) and state_str[idx] in ('G'):
            # controlled_links中每个link是[(lane_id, edge_id, direction)]的列表
            if len(link) > 0:
                green_lane_id = link[0][0]  # 获取该link的车道ID
                green_lanes.append(green_lane_id)
    return green_lanes


def handle_bus_priority(tls_id, bus_id):
    global  _bus_tsp_state
    key = (tls_id, bus_id)

    if bus_id not in traci.vehicle.getIDList():
        _bus_tsp_state.pop(key, None)
        # 不在交通网络中
        return

    bus_lane = traci.vehicle.getLaneID(bus_id)
    a = is_bus_lane(bus_lane)
    if not a:
        _bus_tsp_state.pop(key, None)
        # 不在公交车车道
        return

    # === 获取当前激活的信号灯逻辑 ===
    current_program_id = traci.trafficlight.getProgram(tls_id)
    all_logics = traci.trafficlight.getAllProgramLogics(tls_id)
    current_logic = None
    for logic in all_logics:
        if logic.programID == current_program_id:
            current_logic = logic
            break
    if current_logic is None:
        current_logic = all_logics[0]  # fallback


    current_phase_index = traci.trafficlight.getPhase(tls_id)
    current_phase = current_logic.phases[current_phase_index]
    state_str = current_phase.state
    # 获取当前相位的持续时间
    current_phase_duration = traci.trafficlight.getPhaseDuration(tls_id)
    next_switch = traci.trafficlight.getNextSwitch(tls_id)  # 下一次切换的仿真时间（秒）
    current_time = traci.simulation.getTime()  # 当前仿真时间
    remaining = next_switch - current_time  # 剩余时间（浮点数）
    pasting = current_phase_duration - remaining
    if pasting <= current_phase.minDur:
        # 当前相位已持续时间不足最小时间，不处理
        return
    controlled_links = traci.trafficlight.getControlledLinks(tls_id)

    next_tls_list = traci.vehicle.getNextTLS(bus_id)
    dist_to_stop = None
    for tls_info in next_tls_list:
        if tls_info[0] == tls_id:
            dist_to_stop = tls_info[2]
            break
    if dist_to_stop is None or dist_to_stop <= 0:
        _bus_tsp_state.pop(key, None)
        print(f"[TSP] 清除无有效距离状态: {key}")
        return
    # print(f"[TSP] 距离 {dist_to_stop:.1f}m")

    is_current_green = False
    target_link_indices = None
    for i, link in enumerate(controlled_links):
        if len(link) > 0 and link[0][0] == bus_lane:
            target_link_indices = i
            if i < len(state_str) and state_str[i] in ('G', 'g'):
                is_current_green = True
            break
    # ==============================
    # ✅ 情况1：当前是绿灯 → 延长
    # ==============================
    if is_current_green and dist_to_stop > 0:
        total_extended = _bus_tsp_state.get(key, {}).get('total_extended', 0.0)
        if total_extended < MAX_EXTENSION:

            if remaining < EXTEND_THRESHOLD:
                extra = min(MAX_EXTENSION - total_extended, EXTEND_THRESHOLD - remaining + 1.0)
                if extra > 0:
                    # ⭐ 关键：延长当前相位的剩余时间
                    new_remaining = remaining + extra
                    traci.trafficlight.setPhaseDuration(tls_id, new_remaining)
                    _bus_tsp_state[key] = {'total_extended': total_extended + extra}
                    print(f"{current_time:.1f}s [TSP] 🚦 绿灯延长！ {extra:.1f}s ({total_extended + extra:.1f}/{MAX_EXTENSION}) for {bus_id}")
                    _bus_tsp_history[bus_id] = {'type':'Green Light Early Activation','time': total_extended + extra}
        return

    # ==============================
    # ✅ 情况2：当前是红灯，满足早断条件
    # ==============================
    if dist_to_stop < EARLY_GREEN_DIST:
        # 1. 先获取当前相位的所有绿灯车道
        current_green_lanes = get_current_green_lanes(tls_id, current_phase)
        # 2. 检查当前绿灯车道是否无车排队（核心新增逻辑）
        if not is_current_green_lane_empty(current_green_lanes):
            return  # 有排队，放弃红灯早断
        for need_phase_idx, phase in enumerate(all_logics[1].phases):
            # 检查该相位中，目标车道的状态是否为绿灯（'G'）
            if phase.state[target_link_indices] == 'G' or phase.state[target_link_indices] == 'g':
                break
        next_phase_idx = (traci.trafficlight.getPhase(tls_id)+int(len(all_logics[1].phases)/4))%12
        if next_phase_idx == need_phase_idx:
            traci.trafficlight.setPhase(tls_id, traci.trafficlight.getPhase(tls_id)+1)
            print(f"{current_time:.1f}s [TSP] 🚦 红灯早断！跳到相位 {need_phase_idx} 供 {bus_id} (距路口 {dist_to_stop:.1f}m)")
            _bus_tsp_history[bus_id] = {'type':'Red Light Early Termination','time': remaining}

traci.start(["sumo-gui", "-c", "crossroad_simulation.sumocfg","--tripinfo-output",
             f"{OUTPUT_FOLDER}tripinfo.xml","--queue-output",f"{OUTPUT_FOLDER}queue.xml","--start"])
simu_speed = 0 # 最大仿真倍速
BUS_FIRST = False
save_current_params()   # 仿真前备份可复现的全部支持文件

time_per_step = 0.1/simu_speed if simu_speed>0 else 0.1
t0 = time.time()
# time.sleep(10) # 准备录屏
while traci.simulation.getMinExpectedNumber() > 0:
    traci.simulationStep()
    if BUS_FIRST:
        # 处理每辆公交车
        for veh_id in traci.vehicle.getIDList():
            if veh_id.startswith("bus_"):
                next_tls_list = traci.vehicle.getNextTLS(veh_id)
                if next_tls_list:
                    tls_id = next_tls_list[0][0]
                    handle_bus_priority(tls_id, veh_id)
    # 控制仿真速度
    if simu_speed>0:
        time.sleep(max(0, time_per_step - (time.time() - t0)))
        t0 = time.time()
traci.close(wait=False)
analyze_result()
