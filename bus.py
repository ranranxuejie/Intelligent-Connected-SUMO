import traci
import traceback

# ===== 全局状态 =====
_bus_tsp_state = {}         # (tls_id, bus_id) -> {total_extended: float}
# 历史记录
_bus_tsp_history = {}       # (tls_id, bus_id) -> [ {time: float, total_extended: float} ]

MAX_EXTENSION = 30          # 最大延长秒数
EXTEND_THRESHOLD = 5        # 延长触发阈值（剩余绿灯 < X 秒）
EARLY_GREEN_DIST = 100       # 红灯早断触发距离（米）

def is_bus_lane(lane_id):
    # 方法2（更安全）：再检查是否允许 bus
    if "in_1" in lane_id:
        return True
    else:
        return False
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
    # ==============================
    # ✅ 情况1：当前是绿灯 → 延长
    # ==============================
    is_current_green = False
    target_link_indices = None
    for i, link in enumerate(controlled_links):
        if len(link) > 0 and link[0][0] == bus_lane:
            target_link_indices = i
            if i < len(state_str) and state_str[i] in ('G', 'g'):
                is_current_green = True
            break

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
                    _bus_tsp_history[bus_id] = {'time': total_extended + extra}
        return

    # ==============================
    # ✅ 情况2：当前是红灯，满足早断条件
    # ==============================
    if dist_to_stop < EARLY_GREEN_DIST:
        for need_phase_idx, phase in enumerate(all_logics[1].phases):
            # 检查该相位中，目标车道的状态是否为绿灯（'G'）
            if phase.state[target_link_indices] == 'G' or phase.state[target_link_indices] == 'g':
                break
        next_phase_idx = (traci.trafficlight.getPhase(tls_id)+int(len(all_logics[1].phases)/4))%12
        if next_phase_idx == need_phase_idx:
            traci.trafficlight.setPhase(tls_id, traci.trafficlight.getPhase(tls_id)+1)
            print(f"{current_time:.1f}s [TSP] 🚦 红灯早断！跳到相位 {need_phase_idx} 供 {bus_id} (距路口 {dist_to_stop:.1f}m)")
            _bus_tsp_history[bus_id] = {'time': remaining}

traci.start(["sumo-gui", "-c", "crossroad_simulation.sumocfg", "--start"])
step = 0
while traci.simulation.getMinExpectedNumber() > 0:
    traci.simulationStep()
    # 处理每辆公交车
    for veh_id in traci.vehicle.getIDList():
        if veh_id.startswith("bus_"):
            next_tls_list = traci.vehicle.getNextTLS(veh_id)
            if next_tls_list:
                tls_id = next_tls_list[0][0]
                handle_bus_priority(tls_id, veh_id)
    step += 1
    # if step>6250:
    #     break

traci.close()

for i in range(100):
    traci.simulationStep()
