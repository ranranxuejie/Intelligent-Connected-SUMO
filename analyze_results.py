#!/usr/bin/env python3
import xml.etree.ElementTree as ET
from collections import defaultdict
import os

def fix_tripinfo_xml(tripinfo_file):
    if not os.path.exists(tripinfo_file):
        raise FileNotFoundError(f"文件不存在: {tripinfo_file}")

    with open(tripinfo_file, "r", encoding="utf-8") as f:
        content = f.read()

    content = content.strip()
    if not content:
        raise ValueError("tripinfo.xml 为空！")

    # 快速检查是否已完整
    if content.endswith("</tripinfos>"):
        print("[INFO] tripinfo.xml 已完整，跳过修复。")
        return

    # 找 <tripinfos> 起始位置
    start_idx = content.find("<tripinfos")
    if start_idx == -1:
        raise ValueError("错误：未找到 <tripinfos> 根标签！")

    header = content[:start_idx]
    body = content[start_idx:]

    # 提取 <tripinfos ...> 开始标签（直到第一个 >）
    gt_pos = body.find(">")
    if gt_pos == -1:
        raise ValueError("无法解析 <tripinfos> 开始标签！")

    open_tag = body[:gt_pos+1]
    rest = body[gt_pos+1:]

    # 分割 tripinfo 块
    parts = rest.split("</tripinfo>")
    valid_blocks = []
    for part in parts[:-1]:
        if "<tripinfo" in part:
            candidate = part + "</tripinfo>"
            if "<emissions " in candidate:
                valid_blocks.append(candidate)

    print(f"[INFO] 修复：共保留 {len(valid_blocks)} 个完整 tripinfo 记录")

    # 重写
    with open(tripinfo_file, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(open_tag + "\n")
        for block in valid_blocks:
            f.write(block + "\n")
        f.write("</tripinfos>\n")

    print("[INFO] 修复完成。")

def analyze_tripinfo(tripinfo_file):
    fix_tripinfo_xml(tripinfo_file)

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
    print(f"{'='*60}")
    print(f"{'Vehicle Type':<12} | {'Count':<6} | {'Avg Delay(s)':<12} | {'Avg Wait(s)':<12} | {'Total CO2(g)':<12} | {'Total Fuel(g)':<12}")
    print(f"{'-'*60}")
    for cat in ["private", "bus"]:
        data = stats[cat]
        n = len(data["duration"])
        if n == 0:
            continue
        avg_delay = sum(data["delay"]) / n
        avg_wait = sum(data["waiting_time"]) / n
        total_co2 = sum(data["co2"])
        total_fuel = sum(data["fuel"])
        print(f"{cat:<12} | {n:<6} | {avg_delay:<12.2f} | {avg_wait:<12.2f} | {total_co2:<12.1f} | {total_fuel:<12.1f}")

    return stats

# 新增函数：修复queue.xml文件，处理可能不完整的XML格式
def fix_queue_xml(queue_file):
    """
    修复queue.xml文件，确保它是一个完整的XML文档
    如果文件不完整，会尝试保留有效的数据部分并添加正确的结束标签
    
    Args:
        queue_file: queue.xml文件路径
    """
    if not os.path.exists(queue_file):
        raise FileNotFoundError(f"文件不存在: {queue_file}")

    with open(queue_file, "r", encoding="utf-8") as f:
        content = f.read()

    content = content.strip()
    if not content:
        raise ValueError("queue.xml 为空！")

    # 快速检查是否已完整
    if content.endswith("</queue-export>"):
        print("[INFO] queue.xml 已完整，跳过修复。")
        return

    # 找 <queue-export> 起始位置
    start_idx = content.find("<queue-export")
    if start_idx == -1:
        raise ValueError("错误：未找到 <queue-export> 根标签！")

    header = content[:start_idx]
    body = content[start_idx:]

    # 提取 <queue-export ...> 开始标签（直到第一个 >）
    gt_pos = body.find(">")
    if gt_pos == -1:
        raise ValueError("无法解析 <queue-export> 开始标签！")

    open_tag = body[:gt_pos+1]
    rest = body[gt_pos+1:]

    # 检查是否有有效的数据部分
    # 我们保留所有直到最后一个有效的data标签
    data_parts = []
    current_data = ""
    in_data = False
    
    for line in rest.splitlines():
        stripped_line = line.strip()
        if stripped_line.startswith("<data"):
            in_data = True
            current_data = line
        elif stripped_line.startswith("</data>") and in_data:
            current_data += "\n" + line
            data_parts.append(current_data)
            current_data = ""
            in_data = False
        elif in_data:
            current_data += "\n" + line
    
    print(f"[INFO] 修复queue.xml：共保留 {len(data_parts)} 个完整 data 记录")

    # 重写修复后的文件
    with open(queue_file, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(open_tag + "\n")
        for data in data_parts:
            f.write(data + "\n")
        f.write("</queue-export>\n")

    print("[INFO] queue.xml 修复完成。")

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
    # 首先修复queue.xml文件
    fix_queue_xml(queue_file)

    try:
        tree = ET.parse(queue_file)
        root = tree.getroot()
    except ET.ParseError as e:
        print(f"[ERROR] XML解析错误: {e}")
        print("[INFO] 尝试使用备用解析方法...")
        # 备用方法：手动解析文件，提取有用数据
        return analyze_queue_manually(queue_file)

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
                    direction = parts[0]  # 获取方向部分（west, south等）
                    try:
                        lane_num = int(parts[2])  # 获取车道号
                        
                        # 根据车道号确定车道类型
                        lane_type = None
                        if lane_num == 1:
                            lane_type = 'bus'  # 1号车道为公交专用进口道
                        elif lane_num in [2, 3]:
                            lane_type = 'straight'  # 2,3为直行车道
                        elif lane_num == 4:
                            lane_type = 'left'  # 4为左转车道
                        # 0号车道（右转）忽略不计
                        
                        # 如果是有效车道类型，则统计数据
                        if lane_type:
                            approach_key = f"{direction}_{lane_type}"
                            
                            # 更新该进口道的排队数据
                            if queue_length > approach_data[approach_key]['max_length']:
                                approach_data[approach_key]['max_length'] = queue_length
                            approach_data[approach_key]['total_length'] += queue_length
                            approach_data[approach_key]['count'] += 1
                    except (ValueError, IndexError):
                        # 如果车道号无法解析，跳过该车道
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
    print(f"\n{'='*80}")
    print(f"{'进口道类型':<20} | {'最大排队长度(m)':<18} | {'平均排队长度(m)':<18} | {'记录数':<8}")
    print(f"{'-'*80}")
    
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
                print(f"{display_name:<20} | {stats['max_queue_length']:<18} | {stats['avg_queue_length']:<18} | {stats['record_count']:<8}")
    
    return queue_stats

# 新增备用解析方法：当XML解析失败时手动解析文件
def analyze_queue_manually(queue_file):
    """
    当XML解析器失败时，手动解析queue.xml文件的备用方法
    按照4个方向（东南西北）× 3种车道类型（公交专用道、直行车道、左转车道）分类统计
    
    Args:
        queue_file: queue.xml文件路径
        
    Returns:
        dict: 包含每个进口道的排队统计数据
    """
    # 用于存储每个进口道的排队数据
    approach_data = defaultdict(lambda: {'max_length': 0, 'total_length': 0, 'count': 0})
    
    with open(queue_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    for line in lines:
        line = line.strip()
        # 查找lane标签
        if '<lane ' in line and '/>' in line or '</lane>' in line:
            try:
                # 提取lane_id
                id_start = line.find('id="') + 4
                id_end = line.find('"', id_start)
                lane_id = line[id_start:id_end] if id_start < id_end else ''
                
                # 提取queueing_length
                length = 0
                if 'queueing_length="' in line:
                    len_start = line.find('queueing_length="') + 17
                    len_end = line.find('"', len_start)
                    if len_start < len_end:
                        length = float(line[len_start:len_end])
                
                # 如果queueing_length为0，尝试使用实验性值
                if length == 0 and 'queueing_length_experimental="' in line:
                    exp_len_start = line.find('queueing_length_experimental="') + 28
                    exp_len_end = line.find('"', exp_len_start)
                    if exp_len_start < exp_len_end:
                        length = float(line[exp_len_start:exp_len_end])
                
                # 识别进口道并更新数据
                # 只处理进口道（以_in结尾的车道）
                if lane_id.endswith('_in') or '_in_' in lane_id:
                    # 提取车道方向和车道号
                    parts = lane_id.split('_')
                    if len(parts) >= 3 and parts[1] == 'in':
                        direction = parts[0]  # 获取方向部分（west, south等）
                        try:
                            lane_num = int(parts[2])  # 获取车道号
                            
                            # 根据车道号确定车道类型
                            lane_type = None
                            if lane_num == 1:
                                lane_type = 'bus'  # 1号车道为公交专用进口道
                            elif lane_num in [2, 3]:
                                lane_type = 'straight'  # 2,3为直行车道
                            elif lane_num == 4:
                                lane_type = 'left'  # 4为左转车道
                            # 0号车道（右转）忽略不计
                            
                            # 如果是有效车道类型，则统计数据
                            if lane_type:
                                approach_key = f"{direction}_{lane_type}"
                                
                                # 更新该进口道的排队数据
                                if length > approach_data[approach_key]['max_length']:
                                    approach_data[approach_key]['max_length'] = length
                                approach_data[approach_key]['total_length'] += length
                                approach_data[approach_key]['count'] += 1
                        except (ValueError, IndexError):
                            # 如果车道号无法解析，跳过该车道
                            continue
            except Exception as e:
                # 忽略解析错误的行，继续处理
                continue
    
    # 计算统计数据
    queue_stats = {}
    for approach, data in approach_data.items():
        count = data['count']
        if count > 0:
            queue_stats[approach] = {
                'max_queue_length': round(data['max_length'], 2),
                'avg_queue_length': round(data['total_length'] / count, 2),
                'record_count': count
            }
    
    print("[INFO] 已使用手动解析方法完成数据提取。")
    return queue_stats

if __name__ == "__main__":
    # 分析tripinfo.xml
    print("正在分析tripinfo.xml...")
    trip_stats = analyze_tripinfo("./output/tripinfo.xml")
    
    # 分析queue.xml
    print("\n正在分析queue.xml...")
    queue_stats = analyze_queue("./output/queue.xml")
