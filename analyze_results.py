#!/usr/bin/env python3
import xml.etree.ElementTree as ET
from collections import defaultdict
import os
import json

# 读取配置文件
with open("./generate/config.json", "r", encoding="utf-8") as f:
    config = json.load(f)
LANE_FUNCTIONS = config["LANE_FUNCTIONS"]

def analyze_tripinfo(tripinfo_file):
    # fix_tripinfo_xml(tripinfo_file)

    tree = ET.parse(tripinfo_file)
    root = tree.getroot()

    stats = {
        "private": defaultdict(list),
        "bus": defaultdict(list)
    }

    for trip in root.findall("tripinfo"):
        vid = trip.get("id")
        duration = float(trip.get("duration", 0))
        route_length = float(trip.get("routeLength", 0))
        waiting_time = float(trip.get("waitingTime", 0))

        free_flow_time = route_length / 13.89 if route_length > 0 else duration
        delay = max(0, duration - free_flow_time)

        emissions = trip.find("emissions")
        co2 = float(emissions.get("CO2_abs", 0)) if emissions is not None else 0
        fuel = float(emissions.get("fuel_abs", 0)) if emissions is not None else 0

        category = "bus" if vid.startswith("bus_line") else "private"

        stats[category]["duration"].append(duration)
        stats[category]["waiting_time"].append(waiting_time)
        stats[category]["delay"].append(delay)
        stats[category]["route_length"].append(route_length)
        stats[category]["co2"].append(co2)
        stats[category]["fuel"].append(fuel)

    # 输出汇总
    # print(f"{'='*60}")
    print(f"| {'Vehicle Type':<12} | {'Count':<6} | {'Avg Delay(s)':<12} | {'Avg Wait(s)':<12} | {'Total CO2(g)':<12} | {'Total Fuel(g)':<12} |")
    print(f"| {'-'*5} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*5} | {'-'*5} |")
    result = {}
    for cat in ["private", "bus"]:
        data = stats[cat]
        n = len(data["duration"])
        if n == 0:
            continue
        avg_delay = sum(data["delay"]) / n
        avg_wait = sum(data["waiting_time"]) / n
        total_co2 = sum(data["co2"])
        total_fuel = sum(data["fuel"])
        print(f"| {cat:<12} | {n:<6} | {avg_delay:<12.2f} | {avg_wait:<12.2f} | {total_co2:<12.1f} | {total_fuel:<12.1f} |")
        result[cat] = {
            "count": n,
            "avg_delay": avg_delay,
            "avg_wait": avg_wait,
            "total_co2": total_co2,
            "total_fuel": total_fuel
        }
    return result

# 在 analyze_queue 函数中，替换车道类型判断部分

# 定义车道功能映射
def get_lane_type(direction, lane_index):
    """
    根据方向和车道索引，返回车道类型（bus / straight / left）
    lane_index: int, 从 0 开始
    """
    func_str = LANE_FUNCTIONS.get(f"{direction}_in")
    if not func_str:
        return None  # 未知方向

    if lane_index >= len(func_str):
        return None  # 车道索引越界

    char = func_str[lane_index]

    if char == 'b':
        return 'bus'
    elif char in ['s', 't', 'u']:  # 直行、直右、直左均视为“直行”类排队
        return 'straight'
    elif char == 'l':
        return 'left'
    elif char == 'r':
        return None  # 右转车道不统计排队
    else:
        return None
# 修改后的队列分析函数，添加文件修复步骤
def analyze_queue(queue_file):
    """
    分析queue.xml文件，计算每个进口道的最大排队长度和平均排队长度
    按照4个方向（东南西北）× 3种车道类型（公交专用道、直行车道、左转车道）分类统计
    
    Args:
        queue_file: queue.xml文件路径
        
    Returns:
        dict: 包含每个进口道的排队统计数据
    """

    tree = ET.parse(queue_file)
    root = tree.getroot()


    # 用于存储每个进口道的排队数据
    # 格式: {进口道类型: {'max_length': 最大排队长度, 'total_length': 总排队长度, 'count': 记录数}}
    # 进口道类型格式：方向_车道类型（如 west_bus, east_straight, north_left 等）
    approach_data = defaultdict(lambda: {'max_length': 0, 'total_length': 0, 'count': 0})
    
    # 遍历每个时间步的数据
    for data_node in root.findall('data'):
        # 遍历该时间步的所有车道数据
        lanes_node = data_node.find('lanes')
        if lanes_node is None:
            continue
        
        for lane_node in lanes_node.findall('lane'):
            lane_id = lane_node.get('id')
            # 获取排队长度（优先使用queueing_length，实验性的作为后备）
            queue_length = float(lane_node.get('queueing_length', 0))
            if queue_length == 0:
                queue_length = float(lane_node.get('queueing_length_experimental', 0))
            
            # 识别进口道（根据车道ID中的方向标识）
            # 只处理进口道（以_in结尾的车道）
            if lane_id.endswith('_in') or '_in_' in lane_id:
                # 提取车道方向和车道号
                # 车道ID格式通常为：方向_in_车道号，如west_in_2, south_in_4等
                parts = lane_id.split('_')
                if len(parts) >= 3 and parts[1] == 'in':
                    direction = parts[0]
                    try:
                        lane_num = int(parts[2])  # SUMO 车道编号从 0 开始！
                        lane_type = get_lane_type(direction, lane_num)
                        if lane_type is None:
                            continue  # 跳过右转或无效车道

                        approach_key = f"{direction}_{lane_type}"
                        # 更新统计数据...
                        if queue_length > approach_data[approach_key]['max_length']:
                            approach_data[approach_key]['max_length'] = queue_length
                        approach_data[approach_key]['total_length'] += queue_length
                        approach_data[approach_key]['count'] += 1

                    except (ValueError, IndexError):
                        continue
    
    # 计算每个进口道的平均排队长度
    queue_stats = {}
    for approach, data in approach_data.items():
        count = data['count']
        if count > 0:
            queue_stats[approach] = {
                'max_queue_length': round(data['max_length'], 2),
                'avg_queue_length': round(data['total_length'] / count, 2),
                'record_count': count
            }
    
    # 输出统计结果，按方向和车道类型分类
    # print(f"\n{'='*80}")
    print(f"| {'进口道类型'} | {'最大排队长度(m)'} | {'平均排队长度(m)'} | {'记录数'}|")
    print(f"| {'-'*5}  |{'-'*5} | {'-'*5} | {'-'*5} |")
    
    # 按方向（东南西北）和车道类型（公交、直行、左转）顺序输出
    directions = ['east', 'south', 'west', 'north']
    lane_types = ['bus', 'straight', 'left']
    lane_type_names = {'bus': '公交专用道', 'straight': '直行车道', 'left': '左转车道'}
    direction_names = {'east': '东', 'south': '南', 'west': '西', 'north': '北'}
    
    for direction in directions:
        for lane_type in lane_types:
            key = f"{direction}_{lane_type}"
            if key in queue_stats:
                stats = queue_stats[key]
                # 输出中文方向和车道类型名称，便于阅读
                display_name = f"{direction_names[direction]}{lane_type_names[lane_type]}"
                print(f"| {display_name} | {stats['max_queue_length']} | {stats['avg_queue_length']} | {stats['record_count']} |")
    
    return queue_stats

def analyze_all(outfolder):
    print("正在分析tripinfo.xml...")
    trip_stats = analyze_tripinfo(f"{outfolder}tripinfo.xml")

    # 分析queue.xml
    print("\n正在分析queue.xml...")
    queue_stats = analyze_queue(f"{outfolder}queue.xml")

    # 保存分析结果到JSON文件

    with open(f"{outfolder}queue_stats.json", "w", encoding="utf-8") as f:
        json.dump(queue_stats, f, ensure_ascii=False, indent=4)

    with open(f"{outfolder}trip_stats.json", "w", encoding="utf-8") as f:
        json.dump(trip_stats, f, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    # 分析tripinfo.xml
    OUTPUT_FOLDER = "./output//"+ '20251105_165245'+'/'
    analyze_all(OUTPUT_FOLDER)
