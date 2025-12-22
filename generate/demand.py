#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json

# 读取配置文件
with open("./generate/config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

# 仿真时间
simulation_start = config["simulation"]["start"]
simulation_end = config["simulation"]["end"]

# 私家车流量（辆/小时）
private_flow = config["private_flow"]

# 转向比例（自动归一化为小数）
turn_ratios = {}
for edge, ratios in config["turn_ratios"].items():
    total = sum(ratios)
    if total == 0:
        turn_ratios[edge] = [0.0, 0.0, 0.0]
    else:
        turn_ratios[edge] = [r / total for r in ratios]  # [直行, 左转, 右转]

# 车型比例
vehicle_type_ratios = config["vehicle_type_ratios"]

# 公交线路
bus_lines = config["bus_lines"]
time_bin = config["time_bin"]

# ------------------------------------------------------------------------------

import xml.etree.ElementTree as ET
from xml.dom import minidom
import math
import random
# 生成路由文件
route_filename = "./test/traffic.rou.xml"


def build_time_bins(start_s, end_s, bin_s):
    bins = []
    t = start_s
    while t < end_s:
        bins.append((t, min(t + bin_s, end_s)))
        t += bin_s
    return bins


def normalize_scale_over_bins(bins):
    """
    生成每个时间片的小幅随机波动尺度，并归一化使平均值为 1。
    mu 和 sigma 参数保留以兼容调用，但不再使用。
    """
    n = len(bins)
    if n == 0:
        return []

    # 在 [0.8, 1.2] 范围内生成随机值（可调整范围）
    raw = [random.uniform(0.8, 1.2) for _ in bins]

    # 归一化：使平均值为 1
    avg = sum(raw) / n
    if avg == 0:
        return [1.0] * n
    return [x / avg for x in raw]

def prettify(elem):
    xml_bytes = ET.tostring(elem, encoding="utf-8")
    return minidom.parseString(xml_bytes).toprettyxml(indent="  ", encoding="utf-8")


def generate_routes():
    root = ET.Element("routes")
    # 创建 bus line 映射以便后续查找
    bus_line_by_id = {line["id"]: line for line in bus_lines}
    # 1) 车型与分布：flow 可直接 type="mix" 抽样
    ET.SubElement(root, "vType", id="private", vClass="private", length="4.5", width="1.8",
                  maxSpeed="50", accel="2.6", decel="4.5", sigma="0.5",color="1,1,1")
    ET.SubElement(root, "vType", id="truck", vClass="truck", length="7.5", width="2.5",
                  maxSpeed="40", accel="1.8", decel="3.5", sigma="0.6")
    ET.SubElement(root,"vType" , id ="taxi",vClass="taxi",length="4.5", width="1.8",
                  maxSpeed="50", accel="2", decel="3", sigma="0.5",color="1,0,0")

    vtd = ET.SubElement(root, "vTypeDistribution", id="mix")
    ET.SubElement(vtd, "vType", id="mix_private", vClass="private",
                  length="4.5", width="1.8", maxSpeed="50", accel="2.6", decel="4.5",
                  sigma="0.5", probability=str(vehicle_type_ratios["private"]))
    ET.SubElement(vtd, "vType", id="mix_truck", vClass="truck",
                  length="7.5", width="2.5", maxSpeed="40", accel="1.8", decel="3.5",
                  sigma="0.6", probability=str(vehicle_type_ratios["truck"]))
    ET.SubElement(vtd, "vType", id="mix_taxi", vClass="taxi",
                  length="4.5", width="1.8", maxSpeed="50", accel="2", decel="3",
                  sigma="0.5", probability=str(vehicle_type_ratios["taxi"]))

    # -------------------------- 定义固定路线（直/左/右） --------------------------
    # 每个进口三条 route（注意仅写边 id，内部连接由 SUMO 自动衔接）
    route_map = {
        "east_in_far": {
            "straight": ("r_east_straight", "east_in_far east_in west_out"),  # 东→直行→西出口（正确）
            "left": ("r_east_left", "east_in_far east_in south_out"),  # 东→左转→南出口（正确，原正确无需改）
            "right": ("r_east_right", "east_in_far east_in north_out"),  # 东→右转→北出口（原南→改为北，纠正）
        },
        "west_in_far": {
            "straight": ("r_west_straight", "west_in_far west_in east_out"),  # 西→直行→东出口（正确）
            "left": ("r_west_left", "west_in_far west_in north_out"),  # 西→左转→北出口（原南→改为北，纠正）
            "right": ("r_west_right", "west_in_far west_in south_out"),  # 西→右转→南出口（原北→改为南，纠正）
        },
        "north_in_far": {
            "straight": ("r_north_straight", "north_in_far north_in south_out"),  # 北→直行→南出口（正确）
            "left": ("r_north_left", "north_in_far north_in east_out"),  # 北→左转→东出口（原正确无需改）
            "right": ("r_north_right", "north_in_far north_in west_out"),  # 北→右转→西出口（原正确无需改）
        },
        "south_in_far": {
            "straight": ("r_south_straight", "south_in_far south_in north_out"),  # 南→直行→北出口（正确）
            "left": ("r_south_left", "south_in_far south_in west_out"),  # 南→左转→西出口（原正确无需改）
            "right": ("r_south_right", "south_in_far south_in east_out"),  # 南→右转→东出口（原正确无需改）
        },
    }

    # 写入 route 定义
    for from_edge, turns in route_map.items():
        for _, (rid, edges_str) in turns.items():
            ET.SubElement(root, "route", id=rid, edges=edges_str)

    # 公交路线
    for line in bus_lines:
        # 路线
        ET.SubElement(root, "route", id=f"{line['id']}_route",
                      edges=" ".join(line["route_edges"]))

    # -------------------------- 收集所有车辆和流量事件，按时间排序 --------------------------
    all_events = []

    # 1) 收集私家车流（按时间片 flow + 路线引用）
    bins = build_time_bins(simulation_start, simulation_end, time_bin)
    scales = normalize_scale_over_bins(bins)

    flow_idx = 0
    for (b, e), scale in zip(bins, scales):
        for from_edge, base_vph in private_flow.items():
            straight_ratio, left_ratio, right_ratio = turn_ratios[from_edge]
            straight_ratio, left_ratio, right_ratio = straight_ratio / sum([straight_ratio, left_ratio, right_ratio]), left_ratio / sum([straight_ratio, left_ratio, right_ratio]), right_ratio / sum([straight_ratio, left_ratio, right_ratio])
            od_vph = {
                "straight": base_vph * straight_ratio * scale,
                "left": base_vph * left_ratio * scale,
                "right": base_vph * right_ratio * scale,
            }
            for turn, vph in od_vph.items():
                if vph <= 0:
                    continue
                # 正确获取路线ID - 使用完整的方向名称（从far段获取）
                if from_edge == "east_in_far":
                    direction = "east"
                elif from_edge == "west_in_far":
                    direction = "west"
                elif from_edge == "north_in_far":
                    direction = "north"
                elif from_edge == "south_in_far":
                    direction = "south"
                else:
                    direction = from_edge.split("_")[0]  # 备用方案

                if turn == "straight":
                    rid = f"r_{direction}_straight"
                elif turn == "left":
                    rid = f"r_{direction}_left"
                else:  # right
                    rid = f"r_{direction}_right"

                all_events.append({
                    "type": "flow",
                    "id": f"f_{flow_idx}_{from_edge}_{turn}_{int(b)}",
                    "time": b,  # 按开始时间排序
                    "data": {
                        "type": "mix",
                        "begin": str(b),
                        "end": str(e),
                        "route": rid,
                        "vehsPerHour": str(round(vph, 4)),
                        "departLane": "best",
                        "departSpeed": "random"
                    }
                })
                flow_idx += 1

    # 2) 收集公交流（显式车辆）
    for line in bus_lines:
        depart_time = line["start_time"]
        bus_id = 0
        while depart_time <= line["end_time"]:
            all_events.append({
                "type": "vehicle",
                "id": f"{line['id']}_{bus_id}",
                "time": depart_time,
                "data": {
                    "type": "bus",
                    "route": f"{line['id']}_route",
                    "depart": str(depart_time),
                    "departSpeed": "0"
                }
            })
            depart_time += line["depart_interval"]
            bus_id += 1
    # 按时间排序
    all_events.sort(key=lambda x: x["time"])

    # 3) 按排序后的时间顺序添加所有事件
    for event in all_events:
        if event["type"] == "flow":
            attrs = {"id": event["id"], "type": event["data"]["type"],
                     "begin": event["data"]["begin"], "end": event["data"]["end"],
                     "route": event["data"]["route"],
                     "vehsPerHour": event["data"]["vehsPerHour"],
                     "departLane": event["data"]["departLane"],
                     "departSpeed": event["data"]["departSpeed"]}
            ET.SubElement(root, "flow", **attrs)
        elif event["type"] == "vehicle":
            # 提取 bus line id，例如 "bus_line1_0" -> "bus_line1"
            bus_line_id = event["id"].rsplit("_", 1)[0]
            if bus_line_id in bus_line_by_id:
                veh_elem = ET.SubElement(root, "vehicle",
                                         id=event["id"],
                                         type=event["data"]["type"],
                                         route=event["data"]["route"],
                                         depart=event["data"]["depart"],
                                         departSpeed=event["data"]["departSpeed"]
                                         )
                # 添加每个停靠站
                for i, stop_info in enumerate(bus_line_by_id[bus_line_id]["stops"]):
                    ET.SubElement(veh_elem, "stop",
                                  busStop=f"{bus_line_id}_stop_{i}",
                                  duration=str(stop_info["duration"])
                                  )
            else:
                # 非公交车辆（理论上不会发生）
                ET.SubElement(root, "vehicle", **event["data"])
    # 保存路由文件
    rough = ET.tostring(root, 'utf-8')
    reparsed = minidom.parseString(rough)
    with open(route_filename, "w", encoding="utf-8") as f:
        f.write(reparsed.toprettyxml(indent="  "))
    print(f"交通需求（流量）文件生成成功：{route_filename}")

def generate_additional():
    # 生成公交站点定义文件
    additional_filename = "./test/bus_stops.add.xml"
    root = ET.Element("additional")
    for line in bus_lines:
        for i, stop in enumerate(line["stops"]):
            # 使用第一个车道
            lane = f"{stop['edge']}_0"
            ET.SubElement(root, "busStop",
                          id=f"{line['id']}_stop_{i}",
                          lane=lane,
                          startPos=str(stop["position"] - 20),
                          endPos=str(stop["position"] + 20),
                          friendlyPos="true")

    # 保存公交站点文件
    rough = ET.tostring(root, 'utf-8')
    reparsed = minidom.parseString(rough)
    with open(additional_filename, "w", encoding="utf-8") as f:
        f.write(reparsed.toprettyxml(indent="  "))
    print(f"公交站点文件生成成功：{additional_filename}")


random.seed(42)
generate_routes()
generate_additional()
