import matplotlib.cm
import traci
import time
import matplotlib.pyplot as plt
from tqdm import tqdm
colormap = plt.get_cmap('RdYlGn')
import os

def set_cav_route(veh_id):
    # 假设CAV的目标是到达目的地
    current_time = traci.simulation.getTime()
    speed = traci.vehicle.getSpeed(veh_id)
    if speed<=1e-3:
        nolonger_set_veh_list.append(veh_id)
        return False
    # 开始设置其速度，保证平缓通过交叉口
    # 获取预计到达停止线时间
    next_tls,_,dis_to_stop,current_state = traci.vehicle.getNextTLS(veh_id)[0]

    next_switch_time = traci.trafficlight.getNextSwitch(next_tls)
    current_phase_remaing_time = next_switch_time-current_time
    if current_state=='G':
        except_time = (1e-6,current_phase_remaing_time+3)
    else:
        except_phase = 0
        if current_phase<except_phase:
            time_to_green = sum(phase_duration[current_phase:except_phase])
            except_time = (time_to_green,time_to_green+phase_duration[except_phase])
        else:
            time_to_green = sum(phase_duration[current_phase:])+sum(phase_duration[:except_phase])
            except_time = (time_to_green,time_to_green+phase_duration[except_phase])

    except_speed = (dis_to_stop/except_time[1],dis_to_stop/except_time[0])
    if (except_speed[1]<MIN_SPEED) or (except_speed[0]>MAX_SPEED):
        # 预计无法通过，返回False
        veh_lane = traci.vehicle.getLaneID(veh_id)
        all_veh_loc = cav_loc[veh_lane]
        # 筛选小于dis_to_stop的车辆数量
        num_veh = sum([1 for loc in all_veh_loc if loc<dis_to_stop])
        # 设置车辆平稳减速（减速度较小）a=(v**2)/(2x)
        target_accl = speed**2/((dis_to_stop-num_veh*6)*2)
        traci.vehicle.setDecel(veh_id,max(MIN_ACCLERATION,target_accl))
        print(f"车辆{veh_id}预计无法通过，设置为减速")
        traci.vehicle.setColor(veh_id, (255, 0, 0, 255))
        set_veh_list.append(veh_id)
        return False
    # 设置cav预期速度
    target_speed = min(except_speed[1],MAX_SPEED)
    color = colormap(255*(target_speed-MIN_SPEED)/(MAX_SPEED-MIN_SPEED))
    traci.vehicle.setColor(veh_id, (int(color[0]*255), int(color[1]*255), int(color[2]*255), 255))
    traci.vehicle.setSpeed(veh_id,target_speed)
    print(f"车辆{veh_id}预计可以平顺通过，设置为速度{target_speed:.2f}")
    set_veh_list.append(veh_id)
    return True

def judge_if_set_route(veh_id):
    global set_veh_list,nolonger_set_veh_list
    if veh_id not in nolonger_set_veh_list:
        veh_type = traci.vehicle.getTypeID(veh_id)
        loc_edge = traci.vehicle.getRoadID(veh_id)
        loc_lane = traci.vehicle.getLaneID(veh_id)
        # 获取车道的禁用车辆类型
        allowed = traci.lane.getAllowed(loc_lane)
        if "taxi" in veh_type:
            if 'in' in loc_edge:
                if len(allowed)>0:
                    if ('east' in veh_id or 'west' in veh_id) and \
                            'straight' in veh_id:
                        if veh_id not in set_veh_list:
                            traci.vehicle.setColor(veh_id, (255, 255, 255, 255))
                        set_veh_list.append(veh_id)
                    return True
            elif 'out' in loc_edge:
                # 车辆离开管控范围
                # print(f"车辆{veh_id}离开管控范围")
                nolonger_set_veh_list.append(veh_id)
    return False



def clear_set_route(ID_list):
    global set_veh_list,nolonger_set_veh_list
    for veh_id in nolonger_set_veh_list:
        if veh_id not in ID_list:
            nolonger_set_veh_list.remove(veh_id)
            continue
        elif veh_id in set_veh_list:
            set_veh_list.remove(veh_id)
            # 设置为黑色
            traci.vehicle.setColor(veh_id, (50, 50, 50, 255))
            # 把MIN_SPEED的设置变成原来默认的速度
            traci.vehicle.setSpeed(veh_id,MAX_SPEED)
            # 把减速度设置为原来默认的
            traci.vehicle.setDecel(veh_id,MAX_ACCLERATION)
            # nolonger_set_veh_list.remove(veh_id)

def get_all_cav_loc(ID_list):
    # 查找每个车道的allowed
    cav_loc = {}
    for lane in traci.lane.getIDList():
        if len(traci.lane.getAllowed(lane))==1:
            # print(traci.lane.getAllowed(lane))
            cav_loc[lane] = []

    for veh_id in ID_list:
        veh_type = traci.vehicle.getTypeID(veh_id)
        if "taxi" in veh_type:
            next_tls = traci.vehicle.getNextTLS(veh_id)
            if len(next_tls)>0:
                _, _, dis_to_stop, _ = next_tls[0]
                if dis_to_stop>=1e-3:
                    lane = traci.vehicle.getLaneID(veh_id)
                    if lane in cav_loc:
                        cav_loc[lane] = cav_loc[lane]+[dis_to_stop]
    for lane in cav_loc:
        cav_loc[lane] = sorted(cav_loc[lane])
    return cav_loc

USE_GUI = False
# for MIN_SPEED in [0,15/3.6,20/3.6,25/3.6]:
MIN_SPEED = [0,15/3.6,20/3.6,25/3.6][3]

if MIN_SPEED==0:
    CAV_FIRST = False
    output_name = 'normal'
else:
    output_name = f'cav_first_{MIN_SPEED:.2f}'
    CAV_FIRST = True
OUTPUT_FOLDER = f"output/{output_name}/"
# if os.path.exists(OUTPUT_FOLDER+'tripinfo.xml'):
#     if input(f"是否覆盖{output_name}的结果？(y/n)")!='y':
#         continue
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

try:
    traci.close(wait=False)
except:
    pass
set_veh_list=[]
nolonger_set_veh_list=[]
traci.start(["sumo", "-c", "crossroad_simulation.sumocfg",
             "--tripinfo-output",f"{OUTPUT_FOLDER}tripinfo.xml",
             # "--queue-output",f"{OUTPUT_FOLDER}queue.xml",
             # 2. Emission: 包含每一秒的油耗、CO2、NOx排放
             "--emission-output", f"{OUTPUT_FOLDER}emission.xml",
             # 3. FCD (Floating Car Data): 包含每一秒的位置、速度、加速度，用于画时空图
             "--fcd-output", f"{OUTPUT_FOLDER}fcd.xml",
             "--start"])
MAX_SPEED = traci.lane.getMaxSpeed('east_in_3')
MAX_ACCLERATION = traci.vehicletype.getDecel('taxi')
MIN_ACCLERATION = MAX_ACCLERATION/3
simu_speed = 0 # 最大仿真倍速
if USE_GUI:
    view_id = "View #0"  # 对应默认视图ID
    traci.gui.setZoom(view_id, 800)
    traci.gui.setSchema(view_id, "real world")  # 核心：切换到真实世界配色方案


time_per_step = 0.1/simu_speed if simu_speed>0 else 0.1
t0 = time.time()
# time.sleep(10) # 准备录屏
# while traci.simulation.getMinExpectedNumber() > 0:

# debug = False
tls_program = (traci.trafficlight.getAllProgramLogics('center'))[1].phases
phase_duration = [tls_program[i].duration for i in range(len(tls_program))]
pbar = tqdm(total=37250)
# for i in range(1000):
i = 0
while traci.simulation.getMinExpectedNumber() > 0:
    i += 1
    pbar.update(1)
    traci.simulationStep()
    if not CAV_FIRST:
        continue
    # 获取车辆要等的信号灯相位编号
    current_phase = traci.trafficlight.getPhase('center')
    ID_list = traci.vehicle.getIDList()
    if i % 10 == 0:
        cav_loc = get_all_cav_loc(ID_list)
        for veh_id in ID_list:
        # 获取类型
            judgement = judge_if_set_route(veh_id)
            if judgement==False:
                continue
            set_cav_route(veh_id)
        clear_set_route(ID_list)

        # 控制仿真速度
        # if simu_speed>0:
        #     time.sleep(max(0, time_per_step - (time.time() - t0)))
        #     t0 = time.time()
# traci.close(wait=False)
