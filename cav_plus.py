from re import T
import traci
import sys
import time
import os
import math
from sumolib import checkBinary

USE_GUI = True

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
    parser.add_argument("--signal", action="store_true", help="启用信号优先 (Signal Priority)",default=True)
    parser.add_argument("--traj", action="store_true", help="启用轨迹/编队控制 (Trajectory/Platooning Control)",default=True)
    parser.add_argument("--scale", type=float, help="交通流量缩放比例", default=1.0)
    args = parser.parse_args()
    return args.signal, args.traj, args.scale

# 解析命令行参数
CAV_FIRST, CAV_CONTROL, TRAFFIC_SCALE = parse_args()

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
        # "--fcd-output", f"{OUTPUT_FOLDER}/fcd.xml"
    ])
sumoCmd.extend(["--start", "--quit-on-end"])  # 添加这两个参数，仿真结束后自动关闭 GUI，防止悬挂

# --- 1. 场景 ID 配置 ---
TLS_ID = "center"

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
EARLY_GREEN_PRESSURE = 1     # 南北左转只有少于3辆车排队时，才允许截断
MIN_NS_LEFT_TIME = 5.0   # 南北左转最小绿灯运行时间 (秒)
DETECTION_DIST = 120.0   # CAV头车检测距离

# 状态变量
last_extension_time = -100
managed_vehs_last_step = set() # 全局变量初始化
def get_comprehensive_pressure(lane_list, detection_range=120.0):
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
    PLATOON_MINGAP = 1.0   
    DEFAULT_TAU = 1.0      
    PLATOON_TAU = 0.5      
    
    BRAKING_HORIZON = 150.0  
    STOP_BUFFER = 3.5        
    COMFORT_DECEL = 1.0      

    # =======================================================
    # 定义连贯路径
    # =======================================================
    PLATOON_PATHS = [
        {
            "lanes": ["east_in_3", ":center_5_2", "west_out_3"], 
            "inlet": "east_in_3" 
        },
        {
            "lanes": ["west_in_3", ":center_15_3", "east_out_3"],
            "inlet": "west_in_3"
        }
    ]

    # 遍历每一条完整的路径
    for path_config in PLATOON_PATHS:
        target_lanes = path_config["lanes"]
        inlet_lane_id = path_config["inlet"]
        
        # --- 1. 全局收集与排序 ---
        all_path_cavs = []
        for lane in target_lanes:
            try:
                vehs = traci.lane.getLastStepVehicleIDs(lane)
                cavs = [v for v in vehs if "taxi" in traci.vehicle.getTypeID(v)]
                all_path_cavs.extend(cavs)
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
            current_phase = traci.trafficlight.getPhase(TLS_ID)
            
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
            if current_phase == PHASE_EW_STRAIGHT:
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


        # =======================================================
        # 3. 逐车轨迹控制 (Trajectory Control) - 由 CAV_CONTROL 控制
        # =======================================================
        if CAV_CONTROL:
            for i, veh_id in enumerate(all_path_cavs):
                managed_vehs_this_step.add(veh_id)
                
                v_curr = traci.vehicle.getSpeed(veh_id)
                curr_lane = traci.vehicle.getLaneID(veh_id)
                is_on_inlet = (curr_lane == inlet_lane_id)
                
                # 开启安全模式
                traci.vehicle.setSpeedMode(veh_id, 31)

                # 判断全局头车 (或断裂头车)
                is_global_leader = (i == 0)
                if not is_global_leader:
                    leader_id = all_path_cavs[i-1]
                    dist_ego = traci.vehicle.getDistance(veh_id)
                    dist_lead = traci.vehicle.getDistance(leader_id)
                    if (dist_lead - dist_ego) > 50.0: 
                        is_global_leader = True

                # === 领航者逻辑 (Leader) ===
                if is_global_leader:
                    if is_on_inlet:
                        current_phase = traci.trafficlight.getPhase(TLS_ID)
                        is_green_now = (current_phase == PHASE_EW_STRAIGHT)
                        
                        if not is_green_now:
                            # 红灯：恢复默认，平滑减速
                            traci.vehicle.setTau(veh_id, DEFAULT_TAU)
                            traci.vehicle.setMinGap(veh_id, DEFAULT_MINGAP)
                            
                            pos_curr = traci.vehicle.getLanePosition(veh_id)
                            dist_to_stopline = traci.lane.getLength(curr_lane) - pos_curr

                            if dist_to_stopline < BRAKING_HORIZON:
                                valid_dist = max(0.1, dist_to_stopline - STOP_BUFFER)
                                smooth_speed = math.sqrt(2 * COMFORT_DECEL * valid_dist)
                                traci.vehicle.setSpeed(veh_id, smooth_speed)
                                traci.vehicle.setColor(veh_id, (255, 140, 0, 255)) # 橙色
                            else:
                                traci.vehicle.setSpeed(veh_id, -1)
                        else:
                            # 绿灯：全速
                            traci.vehicle.setTau(veh_id, DEFAULT_TAU)
                            traci.vehicle.setMinGap(veh_id, DEFAULT_MINGAP)
                            traci.vehicle.setSpeed(veh_id, MAX_SPEED)
                            traci.vehicle.setColor(veh_id, (0, 255, 0, 255)) # 绿
                    else:
                        # 非进口道：全速离开
                        traci.vehicle.setTau(veh_id, DEFAULT_TAU)
                        traci.vehicle.setMinGap(veh_id, DEFAULT_MINGAP)
                        traci.vehicle.setSpeed(veh_id, MAX_SPEED)
                        traci.vehicle.setColor(veh_id, (0, 255, 0, 255))

                # === 跟随者逻辑 (Follower) ===
                else:
                    leader_id = all_path_cavs[i-1]
                    v_lead = traci.vehicle.getSpeed(leader_id)
                    accel_lead = traci.vehicle.getAcceleration(leader_id)

                    dist_ego_abs = traci.vehicle.getDistance(veh_id)
                    dist_lead_abs = traci.vehicle.getDistance(leader_id)
                    actual_gap = dist_lead_abs - dist_ego_abs - 5.0 
                    
                    # 场景 A: 平滑停车
                    should_manual_brake = is_on_inlet and \
                                            (v_lead < 5.0) and \
                                            (actual_gap < BRAKING_HORIZON) and \
                                            (accel_lead < -0.5 or v_lead < 1.0)

                    if should_manual_brake:
                        traci.vehicle.setTau(veh_id, DEFAULT_TAU)
                        traci.vehicle.setMinGap(veh_id, DEFAULT_MINGAP)
                        
                        braking_dist = max(0.1, actual_gap - STOP_BUFFER)
                        v_smooth_stop = math.sqrt(2 * COMFORT_DECEL * braking_dist)
                        
                        traci.vehicle.setSpeed(veh_id, v_smooth_stop)
                        traci.vehicle.setColor(veh_id, (255, 165, 0, 255)) 
                    
                    # 场景 B: 编队模式
                    else:
                        traci.vehicle.setTau(veh_id, PLATOON_TAU)
                        traci.vehicle.setMinGap(veh_id, PLATOON_MINGAP)
                        traci.vehicle.setSpeed(veh_id, -1)
                        traci.vehicle.setSpeedMode(veh_id, 31)
                        traci.vehicle.setColor(veh_id, (0, 200, 255, 255)) # 蓝色

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