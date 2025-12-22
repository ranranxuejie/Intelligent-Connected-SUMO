from re import T
import traci
import sys
import time
import os
import math
from sumolib import checkBinary
import argparse

# --- 控制开关配置 ---
# 是否执行信号优化逻辑 (Signal Priority)
CAV_FIRST = None
# 是否执行轨迹控制逻辑 (Trajectory/Platooning Control)
CAV_CONTROL = None
# 交通流量缩放比例
TRAFFIC_SCALE = None

def parse_args():
    parser = argparse.ArgumentParser(description="CAV协同仿真：通过命令行开关控制信号优先与轨迹编队")
    parser.add_argument("--signal", action="store_true", help="启用信号优先 (Signal Priority)",default=False)
    parser.add_argument("--traj", action="store_true", help="启用轨迹/编队控制 (Trajectory/Platooning Control)",default=False)
    parser.add_argument("--scale", type=float, help="交通流量缩放比例", default=1.0)
    parser.add_argument("--gui", action="store_true", help="启用 GUI 可视化", default=False)
    args = parser.parse_args()
    return args.signal, args.traj, args.scale, args.gui

# 解析命令行参数
CAV_FIRST, CAV_CONTROL, TRAFFIC_SCALE, USE_GUI = parse_args()

simu_speed = 0
OUTPUT_FOLDER = f"output/plus/{CAV_FIRST}_{CAV_CONTROL}_{TRAFFIC_SCALE}"
OUTPUT = True  # 新增：是否输出结果文件
# 1. 自动寻找 sumo-gui 路径
if USE_GUI:
    sumoBinary = checkBinary('sumo-gui')
else:
    sumoBinary = checkBinary('sumo')

# 2. 生成启动命令

sumoCmd = [sumoBinary, "-c", "crossroad_simulation.sumocfg"]
if OUTPUT:
    # 新建输出文件夹（如果不存在）
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
    sumoCmd.extend([
        "--statistic-output", f"{OUTPUT_FOLDER}/statistic.xml",
        "--tripinfo-output", f"{OUTPUT_FOLDER}/tripinfo.xml",
        "--queue-output", f"{OUTPUT_FOLDER}/queue.xml",
        # "--emission-output", f"{OUTPUT_FOLDER}/emission.xml",
        "--fcd-output", f"{OUTPUT_FOLDER}/fcd.xml"
    ])
sumoCmd.extend(["--start", "--quit-on-end"])  # 添加这两个参数，仿真结束后自动关闭 GUI，防止悬挂

# --- 1. 场景 ID 配置 ---
TLS_ID = "center"       # 交通灯 ID
SIM_STEP_LENGTH = 0.1   # 仿真步长（秒）
VEH_LENGTH = 4.5        # 车辆长度（米）
# --- 干扰流配置 (完善所有方向) ---

# 1. 南北直行/混合车道 (对应 Phase 6)
CROSS_LANES_NS_STRAIGHT = [
    "north_in_0", "north_in_1", 
    "south_in_0", "south_in_1"
]

# 2. 南北左转专用道 (对应 Phase 9)
CROSS_LANES_NS_LEFT = [
    "north_in_2", 
    "south_in_2"
]

# 3. 东西左转专用道 (对应 Phase 3, 新增)
# 根据之前的车道功能表: east_in_4/5, west_in_4 是左转
CROSS_LANES_EW_LEFT = [
    "east_in_4", "east_in_5",
    "west_in_4"
]
# --- 相位索引定义 ---
PHASE_EW_STRAIGHT = 0   # 目标相位 (东西直行)
PHASE_EW_LEFT = 3       # 干扰相位 (东西左转)
PHASE_NS_STRAIGHT = 6   # 干扰相位 (南北直行)
PHASE_NS_LEFT = 9       # 干扰相位 (南北左转)

# --- 3. 协同控制参数 ---
MAX_SPEED = 16.67       # 最大车速（m/s）
MAX_EXTENSION = 15.0    # 绿灯最长延长时间（s）
PRESSURE_THRESHOLD = 15 # 交通压力阈值（占有率/%）
# 红灯早断参数
EARLY_GREEN_PRESSURE = 1    # 南北左转只有少于3辆车排队时，才允许截断
MIN_NS_LEFT_TIME = 5.0      # 南北左转最小绿灯运行时间 (秒)
DETECTION_DIST = 200.0      # 头车检测距离

# 状态变量
last_extension_time = -100
managed_vehs_last_step = set() # 全局变量初始化
# 4. 停止线参数
VIRTUAL_STOP_GAP = 30.0  # 虚拟停止线距离实际路口的距离 (米)
STOP_BUFFER = 2.0       # 停止缓冲区距离 (米)
import math

# 默认参数定义
ACCEL_COMFORT_VAL = 1.5
DECEL_SHAPE_FACTOR = 1.5

import math

# 参数定义

LIMIT_DECEL_COMFORT = 0.5     # 【新】跟车时的舒适减速度阈值
LIMIT_DECEL_EMERGENCY = 1.0   # 【新】跟车时的紧急减速度阈值
SAFE_GAP_BASE = STOP_BUFFER

# 安全与跟车参数
LIMIT_DECEL_COMFORT = 1.5     # 舒适减速阈值
LIMIT_DECEL_EMERGENCY = 5.0   # 紧急减速阈值
SAFE_GAP_BASE = 2.0           # 静止时的最小间距 (m)
TIME_HEADWAY = 0.5            # 期望跟车时距 (s) -> 间距 = Base + v * Headway
FOLLOW_GAIN = 0.1             # 跟车速度调节增益 (K_p): 间距差1m，速度调整0.5m/s

# 【新增】防溜车/停车保持参数
STANDSTILL_SPEED_THR = 0.1    # 判定为静止的速度阈值 (m/s)
STOP_DISTANCE_DEADBAND = 0.5  # 定点停车时的距离死区 (m)，小于此距离且低速则直接停

def calculate_longitudinal_command(
    v_curr,
    a_curr,
    target_speed,
    dist_to_stop=None,
    dt=SIM_STEP_LENGTH,
    comfort_accel=ACCEL_COMFORT_VAL,
    decel_shape_factor=DECEL_SHAPE_FACTOR,
    leader_gap=None,
    leader_v=None,
):
    v0 = max(0.0, float(v_curr))
    a0 = float(a_curr)
    vt_cmd = float(target_speed)

    # ------------------------------------------------------------
    # 【修复 1】定点刹停模式 (Stop Mode)
    # ------------------------------------------------------------
    if target_speed == 0:
        S = max(0.0, float(dist_to_stop))


        if S <= 1e-6:
            return 0.0

        # 估计基准制动总时长：常加速度刹停的时间 T0 = 2S / v0（由 S = v0*T/2 推得）
        eps_v = 1e-4
        if v0 < eps_v:
            # 当初速极低时，用 sqrt 规则给一个温和的时长，避免过小 T
            # 推导：若常加速度 a_nom 则 S ~ 0.5*a*T^2 => T ~ sqrt(2S/a). 取 a_nom=1 作为时间尺度（单位无关，仅用于形状）
            # 你也可以按系统经验写入一个 a_nom 常量替换 1.0
            T0 = max(2.0 * (S ** 0.5), 2.0 * dt)
        else:
            T0 = 2.0 * S / v0

        # 形状调节：shape_factor>1 => 更平缓、时间更长；<1 => 更激进
        sf = max(0.3, float(DECEL_SHAPE_FACTOR))  # 下限避免过激进
        T = max(1.5 * dt, sf * T0)

        # 构建 quintic：x(t)=c0+c1 t+c2 t^2+c3 t^3+c4 t^4+c5 t^5
        # 边界：
        #  t=0:   x=0        v=v0       a=a0
        #  t=T:   x=S        v=0        a=0
        c0 = 0.0
        c1 = v0
        c2 = 0.5 * a0

        # 方便起见定义中间量
        xT0 = c1 * T + c2 * (T ** 2)        # = v0*T + 0.5*a0*T^2
        vT0 = c1 + 2.0 * c2 * T             # = v0 + a0*T
        aT0 = 2.0 * c2                      # = a0

        # 解未知 c3,c4,c5 的线性系统（推导后的封闭式）
        # 记 A=(S - xT0)/T^3, B=-(vT0)/T^3, C=-(aT0)/T^3
        T2 = T * T
        T3 = T2 * T

        A = (S - xT0) / T3
        B = (-vT0) / T3
        C = (-aT0) / T3

        # 由线性代数消元得到：
        # u5 = 0.5 * [ C + (12 A)/T^2 - (6/T) B ]
        # u4 = B - (3A)/T - 2 T u5
        # u3 = A - T u4 - T^2 u5
        invT = 1.0 / T
        invT2 = invT * invT

        u5 = 0.5 * (C + 12.0 * A * invT2 - 6.0 * invT * B)
        u4 = B - 3.0 * A * invT - 2.0 * T * u5
        u3 = A - T * u4 - T2 * u5

        c3, c4, c5 = u3, u4, u5

        # 计算下一时刻速度 v(dt)；限制不为负，且不超过当前速度太多（避免数值异常）
        t = min(dt, T)  # 若 T<dt，按末速度0
        if t >= T - 1e-9:
            v_next = 0.0
        else:
            v_next = (
                c1
                + 2.0 * c2 * t
                + 3.0 * c3 * (t ** 2)
                + 4.0 * c4 * (t ** 3)
                + 5.0 * c5 * (t ** 4)
            )
            # 数值保护
            if not (v_next == v_next):  # NaN
                v_next = 0.0
            v_next = max(0.0, float(v_next))

            # 额外的保守夹持：单步增幅不超过一个温和上限，避免意外上冲（通常不会发生在减速）
            v_next = min(v_next, v0 + max(0.0, 0.5 * abs(a0)) * dt)

        return v_next
    # ------------------------------------------------------------
    # 【修复 2】跟车/巡航模式 (Follow Mode)
    # ------------------------------------------------------------
    else:
        vt_final = vt_cmd

        if leader_gap is not None and leader_v is not None:
            # 如果速度相差小于5%或者小于0.5m/s，不执行修正
            if abs(leader_v - v0) < 0.5:
                return leader_v
            # [逻辑修复]: 前车静止时的防溜车逻辑
            # 如果前车停了 (leader_v < 0.1) 且 我也停了 (v0 < 0.1)
            else:
                # 1. 计算期望间距 (Desired Gap)
                # 期望间距 = 静止安全距离 + 当前速度 * 时距
                # 例如：速度10m/s, 时距1.5s -> 期望保持 4 + 15 = 19m
                desired_gap = SAFE_GAP_BASE + v0 * TIME_HEADWAY

                # 2. 计算间距误差 (Gap Error)
                current_gap = max(0.0, float(leader_gap))
                gap_error = current_gap - desired_gap
                # 正常的跟车速度计算
                v_follow = leader_v + FOLLOW_GAIN * gap_error
                v_follow = max(0.0, min(v_follow, vt_cmd))
                
                # 安全限制
                actual_gap_for_safety = max(0.0, current_gap - SAFE_GAP_BASE)
                v_soft = (leader_v**2 + 2.0 * LIMIT_DECEL_COMFORT * actual_gap_for_safety) ** 0.5
                v_hard = (leader_v**2 + 2.0 * LIMIT_DECEL_EMERGENCY * actual_gap_for_safety) ** 0.5 # 这里修正公式，前车速度不能忽略
                vt_final = min(v_follow, v_soft, v_hard)

        # --- Quintic 速度规划 ---
        dv = vt_final - v0
        a_nom = max(comfort_accel, 0.5)
        
        if dv < -1.0: T_base = abs(dv) / (a_nom * 0.8)
        else: T_base = abs(dv) / a_nom

        T = max(1.0, 50 * dt, T_base) 

        c1, c2 = v0, 0.5 * a0
        V_total = vt_final - v0 - a0 * T
        T2 = T * T
        c3 = (2.0 * V_total + a0 * T) / T2
        c4 = (-(5.0 / 4.0) * a0 * T - 2.0 * V_total) / (T2 * T)
        c5 = (3.0 * V_total + 2.0 * a0 * T) / (5.0 * (T2 * T2))

        t = dt if dt < T else T
        v_next = c1 + 2*c2*t + 3*c3*t**2 + 4*c4*t**3 + 5*c5*t**4
        if v_next != v_next: v_next = v0
        v_next = max(0.0, v_next)

        
    return v_next




def get_comprehensive_pressure(lane_list, detection_range=DETECTION_DIST):
    """
    更全面的压力检测：
    统计车道上【距离停止线一定范围内】的所有车辆，无论是否移动。
    解决了“起步就不算排队”的 BUG。
    """
    total_count = 0
    for lane in lane_list:
        try:
            # 获取该车道上所有车辆 ID
            vehs = traci.lane.getLastStepVehicleIDs(lane)
            
            # 获取车道长度
            lane_len = traci.lane.getLength(lane)
            
            for veh in vehs:
                # 获取车辆位置
                veh_pos = traci.vehicle.getLanePosition(veh)
                # 计算距离停止线的距离
                dist_to_stop = lane_len - veh_pos
                
                # 核心判断：只要在检测范围内 (例如 120米)，就算作有效压力
                if dist_to_stop < detection_range:
                    total_count += 1
        except:
            # 防止车道ID错误导致崩溃
            continue
            
    return total_count
def run_cooperative_logic():
    global last_extension_time, managed_vehs_last_step
    current_time = traci.simulation.getTime()
    
    # 本帧受控车辆集合
    managed_vehs_this_step = set()

    # --- 参数配置 ---
    DEFAULT_MINGAP = 2.5   
    PLATOON_MINGAP = 0.5   
    DEFAULT_TAU = 1.0      
    PLATOON_TAU = 0.1      
    
    BRAKING_HORIZON = 150.0

    # =======================================================
    # 定义连贯路径
    # =======================================================
    PLATOON_PATHS = [
        {
            "lanes": ["east_in_3", ":center_5_2", "west_out_3"], 
            "inlet": "east_in_3" 
        },
        {
            "lanes": ["west_in_3", ":center_15_2", "east_out_3"],
            "inlet": "west_in_3"
        }
    ]
    # >>> 在循环外先获取信号状态，供所有车辆使用 <<<
    current_phase = traci.trafficlight.getPhase(TLS_ID)
    # 假设 PHASE_EW_STRAIGHT 是东西直行绿灯
    is_green_global = (current_phase == PHASE_EW_STRAIGHT)
    is_pre_start = (current_phase > PHASE_NS_LEFT)
    # 遍历每一条完整的路径
    for path_config in PLATOON_PATHS:
        target_lanes = path_config["lanes"]
        inlet_lane_id = path_config["inlet"]
        
        # --- 1. 全局收集与排序 ---
        all_path_cavs = []
        for lane in target_lanes:
            try:
                vehs = traci.lane.getLastStepVehicleIDs(lane)
                for v in vehs:
                    veh_type = traci.vehicle.getTypeID(v)
                    # 1. 车型检查
                    if ("taxi" not in veh_type)or("straight" not in v):
                        continue
                    if (not "east" in v) and (not "west" in v):
                        continue
                    all_path_cavs.append(v)
            except:
                continue
        if not all_path_cavs:
            continue

        # 按总里程排序
        all_path_cavs.sort(key=lambda v: traci.vehicle.getDistance(v), reverse=True)
       
        # =======================================================
        # 2. 信号优化逻辑 (Signal Priority)
        # =======================================================
        if CAV_FIRST:
            # 定义关键车辆
            tail_veh = all_path_cavs[-1]
            tail_lane = traci.vehicle.getLaneID(tail_veh)
            
            approaching_head_veh = None
            for v in all_path_cavs:
                if traci.vehicle.getLaneID(v) == inlet_lane_id:
                    approaching_head_veh = v
                    break

            # ---------------------------------------------------
            # 场景 A: 绿灯延长 (目标相位: 东西直行 Phase 0)
            # ---------------------------------------------------
            if  is_green_global:
                if tail_lane == inlet_lane_id:
                    next_switch = traci.trafficlight.getNextSwitch(TLS_ID)
                    time_rem = next_switch - current_time
                    dist_tail_to_stop = traci.lane.getLength(tail_lane) - traci.vehicle.getLanePosition(tail_veh)
                    v_tail = max(1.0, traci.vehicle.getSpeed(tail_veh))
                    eta_tail = dist_tail_to_stop / v_tail
                    
                    if eta_tail > time_rem:
                        needed_extension = eta_tail - time_rem
                        
                        # >>> 修改：使用新函数检测侧向压力 <<<
                        # 检测范围设为 80米，如果侧向 80米内有车，就不延长了，把路权还给别人
                        # 这里把所有干扰流加起来
                        total_cross_pressure = (get_comprehensive_pressure(CROSS_LANES_NS_STRAIGHT, 80) + 
                                                get_comprehensive_pressure(CROSS_LANES_NS_LEFT, 80) +
                                                get_comprehensive_pressure(CROSS_LANES_EW_LEFT, 80))
                        
                        if (needed_extension < MAX_EXTENSION and 
                            total_cross_pressure < PRESSURE_THRESHOLD and 
                            (current_time - last_extension_time > 3.0)): 

                            current_duration = traci.trafficlight.getPhaseDuration(TLS_ID)
                            traci.trafficlight.setPhaseDuration(TLS_ID, current_duration + needed_extension + 2.0)
                            last_extension_time = current_time
                            print(f"[{current_time:.1f}s] 信号优先: 绿灯延长 {needed_extension:.1f}s")

            # ---------------------------------------------------
            # 场景 B: 红灯早断/相位插入 (通用逻辑: 针对所有非目标绿灯)
            # ---------------------------------------------------
            else:
                # 定义哪些相位可以被截断，以及它们对应的压力检测车道
                # 格式: {相位ID: 检测车道列表}
                truncate_map = {
                    PHASE_EW_LEFT: CROSS_LANES_EW_LEFT,       # Phase 3
                    PHASE_NS_STRAIGHT: CROSS_LANES_NS_STRAIGHT, # Phase 6
                    PHASE_NS_LEFT: CROSS_LANES_NS_LEFT        # Phase 9
                }

                # 检查当前相位是否在可截断列表中
                if current_phase in truncate_map:
                    target_lanes_for_pressure = truncate_map[current_phase]
                    
                    if approaching_head_veh: 
                        head_lane = traci.vehicle.getLaneID(approaching_head_veh)
                        dist_head_to_stop = traci.lane.getLength(head_lane) - traci.vehicle.getLanePosition(approaching_head_veh)
                        if dist_head_to_stop < DETECTION_DIST:
                            
                            # 1. 安全时间检查 (保持不变)
                            current_dur_setting = traci.trafficlight.getPhaseDuration(TLS_ID)
                            next_switch = traci.trafficlight.getNextSwitch(TLS_ID)
                            time_spent = current_dur_setting - (next_switch - current_time)

                            # >>> 修改：使用新函数检测当前放行方向的压力 <<<
                            # 关键：这里检测范围要设大一点，比如 150米
                            # 含义：只要当前绿灯方向 150米 内还有车，就绝对不能截断！
                            current_pressure = get_comprehensive_pressure(target_lanes_for_pressure, detection_range=150.0)

                            # 调试打印 (可选)：看看现在的压力是不是变正常了
                            # print(f"DEBUG: 相位 {current_phase} 压力检测: {current_pressure} 辆")


                            # 3. 触发早断
                            # 注意：最小运行时间设为 5.0s，压力阈值设为 3
                            if (current_pressure < EARLY_GREEN_PRESSURE and 
                                time_spent > 5.0 and 
                                (current_time - last_extension_time > 5.0)):
                                
                                # >>> 强制跳转到下一相位 (黄灯) <<<
                                # 假设所有绿灯的下一相位都是黄灯，ID + 1
                                next_phase_index = current_phase + 1
                                traci.trafficlight.setPhase(TLS_ID, next_phase_index)
                                
                                time_saved = next_switch - current_time
                                last_extension_time = current_time
                                
                                print(f"[{current_time:.1f}s] 信号优先: 截断相位 {current_phase}! 跳转至 {next_phase_index} | 节省 {time_saved:.1f}s | 当前方向压力 {current_pressure}")
        # print(inlet_lane_id)
        # =======================================================
        # 3. 逐车轨迹控制 (Trajectory Control) - 五次多项式应用
        # =======================================================
        if CAV_CONTROL:
            SLOT_LENGTH = VEH_LENGTH + PLATOON_MINGAP + STOP_BUFFER
            action_share = {}
            for i, veh_id in enumerate(all_path_cavs):
                managed_vehs_this_step.add(veh_id)
                v_curr = traci.vehicle.getSpeed(veh_id)
                a_curr = traci.vehicle.getAcceleration(veh_id) # 获取当前加速度
                curr_lane = traci.vehicle.getLaneID(veh_id)
                is_on_inlet = (curr_lane == inlet_lane_id)
                traci.vehicle.setSpeedMode(veh_id, 31)

                is_global_leader = (i == 0)
                if not is_global_leader:
                    leader_id = all_path_cavs[i-1]
                    if is_on_inlet:
                        leader_lane = traci.vehicle.getLaneID(leader_id)
                        # 核心判断：如果前车所在的不是进口道（说明它已经进了路口内部或者到了出口道）
                        if leader_lane != inlet_lane_id:
                            # 如果现在不是绿灯，中间有红灯阻隔，即使距离再近也不能跟车！
                            if not is_green_global:
                                is_global_leader = True
                                # 此时被强制判定为头车，下文逻辑就会让它执行红灯停车（变橙色）
                                # 而不是执行跟随逻辑（变蓝色闯红灯）

                # === 领航者逻辑 (Leader) ===
                if is_global_leader:
                    should_stop = False
                    if is_on_inlet:
                        next_switch = traci.trafficlight.getNextSwitch(TLS_ID)
                        time_rem = next_switch - current_time
                        dist_tail_to_stop = traci.lane.getLength(curr_lane) - traci.vehicle.getLanePosition(veh_id)
                        v_tail = traci.vehicle.getSpeed(veh_id)
                        eta_tail = dist_tail_to_stop / max(0.01,v_tail)
                        if (not is_pre_start)and(not is_green_global):
                            should_stop = True
                        elif time_rem<15 and is_green_global: 
                            # print(f'剩余时间{time_rem:.1f}s, {veh_id}车剩余距离{dist_tail_to_stop:.1f}m, tail车速度{v_tail:.1f}m/s, tail车到达时间{eta_tail:.1f}s')
                            if (eta_tail > time_rem-3):
                                should_stop = True
                        
                    # 场景 1: 红灯停车 (必须严格限制在进口道内)
                    # 只有在进口道且红灯时，才执行停车逻辑。
                    # 如果已经出了进口道(在路口内)，即使红灯也不能停，必须继续走。
                    if should_stop:
                        traci.vehicle.setSpeedMode(veh_id, 31) # 停车需要安全模式
                        traci.vehicle.setTau(veh_id, PLATOON_TAU)
                        traci.vehicle.setMinGap(veh_id, PLATOON_MINGAP)
                        pos_curr = traci.vehicle.getLanePosition(veh_id)
                        dist_to_stopline = traci.lane.getLength(curr_lane) - pos_curr
                        dist_to_virtual_stop = dist_to_stopline - VIRTUAL_STOP_GAP
                        if dist_to_virtual_stop < BRAKING_HORIZON:
                            valid_dist = max(0.1, dist_to_virtual_stop)
                            quintic_speed = calculate_longitudinal_command(
                                v_curr, a_curr,0, dist_to_stop=valid_dist, dt=0.1, 
                                decel_shape_factor=DECEL_SHAPE_FACTOR
                            )
                            traci.vehicle.setSpeed(veh_id, quintic_speed)
                            traci.vehicle.setColor(veh_id, (255, 140, 0, 255)) # 橙色
                        # else:
                            # traci.vehicle.setSpeed(veh_id, -1)
                        action_share[i] = "stop"
                    # 场景 2: 绿灯行驶 OR 已经越过停止线 (通用加速逻辑)
                    else:
                        traci.vehicle.setSpeedMode(veh_id, 31)
                        traci.vehicle.setTau(veh_id, PLATOON_TAU)
                        traci.vehicle.setMinGap(veh_id, PLATOON_MINGAP)
                        # >>> 修正点：无论在哪，只要没达到极速，就继续五次多项式加速 <<<

                        acc_speed = calculate_longitudinal_command(
                            v_curr, a_curr, target_speed=MAX_SPEED, dt=0.1,
                            comfort_accel=ACCEL_COMFORT_VAL
                        )
                        traci.vehicle.setSpeed(veh_id, acc_speed)
                        # 颜色区分：
                        # 进口道内加速：淡绿
                        # 路口内/出口道加速：淡青 (方便观察是否延续了逻辑)
                        traci.vehicle.setColor(veh_id, (144, 238, 144, 255)) 
                        action_share[i] = "accel"

                # === 跟随者逻辑 (Follower) ===
                else:
                    leader_action = action_share[i-1]
                    leader_id = all_path_cavs[i-1]
                    leader_v = traci.vehicle.getSpeed(leader_id)
                    # accel_lead = traci.vehicle.getAcceleration(leader_id)
                    dist_to_lead = traci.vehicle.getDistance(leader_id) - traci.vehicle.getDistance(veh_id) - VEH_LENGTH
                    if leader_v <0.05:
                        dist_to_my_stop = dist_to_lead - STOP_BUFFER
                    else: 
                        dist_to_stopline = traci.lane.getLength(curr_lane) - traci.vehicle.getLanePosition(veh_id)
                        dist_to_virtual_stop = dist_to_stopline - VIRTUAL_STOP_GAP
                        # 前方有多少action是stop的车
                        num_stop_ahead = sum(1*(action == "stop") for action in action_share.values())
                        dist_to_my_stop = dist_to_virtual_stop - num_stop_ahead * SLOT_LENGTH
                    # print(f'no {i} : {dist_to_my_stop}')
                    if (dist_to_my_stop > BRAKING_HORIZON):
                        action_share[i] = "cruise"
                        # print(f'no {i} : 未达到距离')
                    elif (leader_action == "stop"):
                        # >>> 恢复安全模式 <<<
                        traci.vehicle.setSpeedMode(veh_id, 31) 
                        traci.vehicle.setTau(veh_id, PLATOON_TAU)
                        traci.vehicle.setMinGap(veh_id, PLATOON_MINGAP)
                        
                        braking_dist = max(0.1, dist_to_my_stop)
                        quintic_speed = calculate_longitudinal_command(
                            v_curr, a_curr, target_speed=0, dist_to_stop=braking_dist, dt=0.1, 
                            decel_shape_factor=DECEL_SHAPE_FACTOR
                        )
                        traci.vehicle.setSpeed(veh_id, quintic_speed)
                        traci.vehicle.setColor(veh_id, (255, 165, 0, 255)) # 橙色
                        action_share[i] = "stop"
                    # 2. 协同起步逻辑 (Mimic Leader Startup)
                    elif leader_action == "accel":
                        traci.vehicle.setSpeedMode(veh_id, 31) 
                        traci.vehicle.setTau(veh_id, PLATOON_TAU)
                        traci.vehicle.setMinGap(veh_id, PLATOON_MINGAP)
                        # 计算与头车完全一致的加速曲线
                        acc_speed = calculate_longitudinal_command(
                            v_curr, a_curr, target_speed=MAX_SPEED, dt=0.1,
                            comfort_accel=ACCEL_COMFORT_VAL,
                            leader_gap=dist_to_lead,
                            leader_v=leader_v,
                        )
                        acc_speed = acc_speed
                        traci.vehicle.setSpeed(veh_id, acc_speed)
                        # 青色：协同强行加速中
                        traci.vehicle.setColor(veh_id, (0, 255, 255, 255)) 
                        action_share[i] = "accel"
                    else:
                        action_share[i] = 'unknown'


    # 4. 全局清理逻辑 (释放未受控车辆 - 仅在开启轨迹控制时生效)
    # >>> 4. 全局清理逻辑 (大幅优化：只处理变化的差集) <<<
    if CAV_CONTROL:
        # 找出上一帧在受控，但这一帧不在受控名单里的车
        vehs_to_release = managed_vehs_last_step - managed_vehs_this_step
        # 还要获取当前还在路网里的所有车ID，防止报错
        # (这一步虽然也有开销，但比遍历全量属性快得多)
        existing_vehs = set(traci.vehicle.getIDList())
        for veh_id in vehs_to_release:
            # 只有当车辆还存在时，才进行重置，否则忽略
            if veh_id in existing_vehs:
                traci.vehicle.setColor(veh_id, (255, 255, 0, 255)) 
                traci.vehicle.setSpeed(veh_id, -1) 
                traci.vehicle.setSpeedMode(veh_id, 31)
                traci.vehicle.setTau(veh_id, DEFAULT_TAU)
                traci.vehicle.setMinGap(veh_id, DEFAULT_MINGAP)
                
        managed_vehs_last_step = managed_vehs_this_step

# 3. 核心运行逻辑
try:
    try:
        traci.close()
    except:
        pass

    traci.start(sumoCmd)
    
    if USE_GUI:
        view_id = "View #0"
        traci.gui.setZoom(view_id, 800)
        traci.gui.setSchema(view_id, "real world")
    traci.simulation.setScale(TRAFFIC_SCALE)
    step = 0
    while traci.simulation.getMinExpectedNumber() > 0:
        traci.simulationStep()
        
        # 只要开启了任一控制功能，就调用逻辑函数
        if CAV_FIRST or CAV_CONTROL:
            run_cooperative_logic()
            
        step += 1
        
        if USE_GUI and simu_speed > 0:
            time.sleep(0.1 / simu_speed)

except traci.exceptions.FatalTraCIError:
    print("错误：SUMO 连接意外断开。")
except Exception as e:
    print(f"发生代码错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    try:
        traci.close()
        print("仿真结束，连接已关闭。")
    except:
        pass