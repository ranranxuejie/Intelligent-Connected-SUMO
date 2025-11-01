#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -------------------------- 交通需求核心参数（可快速调整） --------------------------
# 仿真时间设置（单位：秒）
simulation_start = 0
simulation_end = 3600  # 1小时仿真时长（早高峰）

# 私家车流量配置（单位：辆/小时）——按进口边总量
private_flow = {
    "east_in_far": 600,
    "west_in_far": 500,
    "north_in_far": 400,
    "south_in_far": 450
}

# 转向比例配置（单位：小数）顺序：直、左、右（合计=1）
turn_ratios = {
    "east_in_far": [0.6, 0.2, 0.2],
    "west_in_far": [0.5, 0.3, 0.2],
    "north_in_far": [0.55, 0.25, 0.2],
    "south_in_far": [0.5, 0.2, 0.3]
}

# 车型比例（单位：小数，合计=1）
vehicle_type_ratios = {
    "private": 0.85,
    "truck": 0.10,
    "taxi": 0.05
}

# 公交配置（注意：route_edges 仅包含边 id，不包含节点）
bus_lines = [
    {
        "id": "bus_line1",  # 东向西直行
        "route_edges": ["east_in_far", "east_in", "west_out"],  # 包含远段到近段再到出口
        "stops": [
            {"edge": "east_in_far", "position": 100, "duration": 30},
            {"edge": "west_out", "position": 100, "duration": 30}
        ],
        "depart_interval": 180,
        "start_time": 60,
        "end_time": 3540
    },
    {
        "id": "bus_line2",  # 北向南直行
        "route_edges": ["north_in_far", "north_in", "south_out"],  # 包含远段到近段再到出口
        "stops": [
            {"edge": "north_in_far", "position": 100, "duration": 30},
            {"edge": "south_out", "position": 100, "duration": 30}
        ],
        "depart_interval": 240,
        "start_time": 60,
        "end_time": 3540
    }
]

# 早高峰流量波动参数（高斯分布，以 1 为平均尺度）
peak_hour = 1800  # 高峰中心时间（秒）
peak_std = 600  # 标准差（秒）
time_bin = 300  # 生成流量的时间粒度（秒），默认5分钟
# ------------------------------------------------------------------------------

import xml.etree.ElementTree as ET
from xml.dom import minidom
import math

# 生成路由文件
route_filename = "./test/traffic.rou.xml"


def gaussian_scale(t, mu, sigma):
    # 原始高斯值
    val = math.exp(-0.5 * ((t - mu) / sigma) ** 2)
    return val


def build_time_bins(start_s, end_s, bin_s):
    bins = []
    t = start_s
    while t < end_s:
        bins.append((t, min(t + bin_s, end_s)))
        t += bin_s
    return bins


def normalize_scale_over_bins(bins, mu, sigma):
    # 计算每个时间片的平均尺度并归一化，使全时段平均尺度为 1
    raw = []
    for b, e in bins:
        tm = 0.5 * (b + e)
        raw.append(gaussian_scale(tm, mu, sigma))
    avg = sum(raw) / len(raw) if raw else 1.0
    if avg == 0:
        return [1.0 for _ in raw]
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
                  maxSpeed="50", accel="2.6", decel="4.5", sigma="0.5")
    ET.SubElement(root, "vType", id="truck", vClass="truck", length="7.5", width="2.5",
                  maxSpeed="40", accel="1.8", decel="3.5", sigma="0.6")
    ET.SubElement(root, "vType", id="taxi", vClass="taxi", length="4.5", width="1.8",
                  maxSpeed="50", accel="2.8", decel="4.8", sigma="0.4")
    ET.SubElement(root, "vType", id="bus", vClass="bus", length="12", width="2.5",
                  maxSpeed="40", accel="1.5", decel="3.0", sigma="0.3")

    vtd = ET.SubElement(root, "vTypeDistribution", id="mix")
    ET.SubElement(vtd, "vType", id="mix_private", vClass="private",
                  length="4.5", width="1.8", maxSpeed="50", accel="2.6", decel="4.5",
                  sigma="0.5", probability=str(vehicle_type_ratios["private"]))
    ET.SubElement(vtd, "vType", id="mix_truck", vClass="truck",
                  length="7.5", width="2.5", maxSpeed="40", accel="1.8", decel="3.5",
                  sigma="0.6", probability=str(vehicle_type_ratios["truck"]))
    ET.SubElement(vtd, "vType", id="mix_taxi", vClass="taxi",
                  length="4.5", width="1.8", maxSpeed="50", accel="2.8", decel="4.8",
                  sigma="0.4", probability=str(vehicle_type_ratios["taxi"]))

    # -------------------------- 定义固定路线（直/左/右） --------------------------
    # 每个进口三条 route（注意仅写边 id，内部连接由 SUMO 自动衔接）
    route_map = {
        "east_in_far": {
            "straight": ("r_east_straight", "east_in_far east_in west_out"),
            "left": ("r_east_left", "east_in_far east_in north_out"),
            "right": ("r_east_right", "east_in_far east_in south_out"),
        },
        "west_in_far": {
            "straight": ("r_west_straight", "west_in_far west_in east_out"),
            "left": ("r_west_left", "west_in_far west_in south_out"),
            "right": ("r_west_right", "west_in_far west_in north_out"),
        },
        "north_in_far": {
            "straight": ("r_north_straight", "north_in_far north_in south_out"),
            "left": ("r_north_left", "north_in_far north_in east_out"),
            "right": ("r_north_right", "north_in_far north_in west_out"),
        },
        "south_in_far": {
            "straight": ("r_south_straight", "south_in_far south_in north_out"),
            "left": ("r_south_left", "south_in_far south_in west_out"),
            "right": ("r_south_right", "south_in_far south_in east_out"),
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
    scales = normalize_scale_over_bins(bins, peak_hour, peak_std)

    flow_idx = 0
    for (b, e), scale in zip(bins, scales):
        for from_edge, base_vph in private_flow.items():
            straight_ratio, left_ratio, right_ratio = turn_ratios[from_edge]
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
                    direction = from_edge[:4]  # 备用方案

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


def main():
    generate_routes()
    generate_additional()


if __name__ == "__main__":
    main()
