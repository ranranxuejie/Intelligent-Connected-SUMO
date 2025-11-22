#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from xml.dom import minidom

# -------------------------- 可调参数 --------------------------
import json

# 读取配置文件
with open("./generate/config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

# 重建变量
center_x = config["center_x"]
center_y = config["center_y"]
road_length = config["road_length"]
bus_only_length = config["bus_only_length"]
speed_kmh = config["speed_kmh"]
speed_ms = round(speed_kmh / 3.6, 2)

bus_lane_width = config["bus_lane_width"]
normal_lane_width = config["normal_lane_width"]

LANES = config["LANES"]
LANE_FUNCTIONS = config["LANE_FUNCTIONS"]

# 可选：验证加载成功
print(f"Speed: {speed_kmh} km/h → {speed_ms} m/s")
print("LANE_FUNCTIONS:", LANE_FUNCTIONS)
# ----------------------------------------------------------------

OUT_DIR = "./test"
NODES_FILE = os.path.join(OUT_DIR, "nodes.nod.xml")
EDGES_FILE = os.path.join(OUT_DIR, "edges.edg.xml")
NET_FILE = os.path.join(OUT_DIR, "crossroad.net.xml")
CONN_FILE = os.path.join('./test', "connections.con.xml")

def prettify(elem):
    xml_bytes = ET.tostring(elem, encoding="utf-8")
    return minidom.parseString(xml_bytes).toprettyxml(indent="  ", encoding="utf-8")

def write_nodes(path=NODES_FILE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    nodes = ET.Element("nodes")

    # 中心与端点
    ET.SubElement(nodes, "node", id="center", x=str(center_x), y=str(center_y), type="traffic_light")
    ET.SubElement(nodes, "node", id="east_end",  x=str(center_x + road_length), y=str(center_y), type="priority")
    ET.SubElement(nodes, "node", id="west_end",  x=str(center_x - road_length), y=str(center_y), type="priority")
    ET.SubElement(nodes, "node", id="north_end", x=str(center_x), y=str(center_y + road_length), type="priority")
    ET.SubElement(nodes, "node", id="south_end", x=str(center_x), y=str(center_y - road_length), type="priority")

    # 中间节点（距中心 bus_only_length 处），用于把进口拆成远段和近段
    ET.SubElement(nodes, "node", id="east_mid",  x=str(center_x + bus_only_length),  y=str(center_y), type="priority")
    ET.SubElement(nodes, "node", id="west_mid",  x=str(center_x - bus_only_length),  y=str(center_y), type="priority")
    ET.SubElement(nodes, "node", id="north_mid", x=str(center_x), y=str(center_y + bus_only_length), type="priority")
    ET.SubElement(nodes, "node", id="south_mid", x=str(center_x), y=str(center_y - bus_only_length), type="priority")

    with open(path, "wb") as f:
        f.write(prettify(nodes))
    print(f"[OK] nodes -> {path}")

def write_edges(path=EDGES_FILE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    edges = ET.Element("edges")
    edge_defs = [
        ("east_in_far",  "east_end",  "east_mid",  True,  "east_in"),
        ("east_in",      "east_mid",  "center",    True,  "east_in"),
        ("west_in_far",  "west_end",  "west_mid",  True,  "west_in"),
        ("west_in",      "west_mid",  "center",    True,  "west_in"),
        ("north_in_far", "north_end", "north_mid", True,  "north_in"),
        ("north_in",     "north_mid", "center",    True,  "north_in"),
        ("south_in_far", "south_end", "south_mid", True,  "south_in"),
        ("south_in",     "south_mid", "center",    True,  "south_in"),
        ("east_out",     "center",    "east_end",  False, "east_out"),
        ("west_out",     "center",    "west_end",  False, "west_out"),
        ("north_out",    "center",    "north_end", False, "north_out"),
        ("south_out",    "center",    "south_end", False, "south_out"),
    ]

    for edge_id, frm, to, is_in, base_key in edge_defs:
        # 1. 从LANE_FUNCTIONS获取当前道路的功能字符串（仅进口道有定义）
        if base_key and base_key in LANE_FUNCTIONS:
            func_str = LANE_FUNCTIONS[base_key]
            total_lanes = len(func_str)  # 车道数 = 功能字符串长度
        else:
            # 出口道/远段：用原有LANES配置（若需自定义出口道，可新增出口功能字典）
            total_lanes = int(LANES[edge_id])

        # 2. 创建道路节点
        e = ET.SubElement(
            edges, "edge", id=edge_id, **{"from": frm, "to": to},
            numLanes=str(total_lanes), speed=str(speed_ms)
        )
        if base_key and base_key in LANE_FUNCTIONS:
            # 3. 按功能字符串逐车道生成属性（外侧到内侧，对应字符串索引0到n-1）
            for lane_idx, func in enumerate(func_str):
                lane_attrs = {
                    "index": str(lane_idx),
                    "speed": str(speed_ms),
                    "width": str(bus_lane_width if func == 'b' else normal_lane_width)
                }

                # 3.1 设置公交专用道属性
                if (func == 'b')&('far' not in edge_id):
                    lane_attrs["allow"] = "bus"  # 仅允许公交
                # else:
                #     lane_attrs["disallow"] = "bus"  # 禁止公交（非公交道）

                # 3.2 设置近段禁变道（保持原有逻辑）
                if edge_id.endswith("_in"):
                    lane_attrs["changeLeft"] = "emergency"
                    lane_attrs["changeRight"] = "emergency"

                ET.SubElement(e, "lane", **lane_attrs)
        else:
            for lane_idx in range(total_lanes):
                lane_attrs = {
                    "index": str(lane_idx),
                    "speed": str(speed_ms),
                    "width": str(bus_lane_width if func == 'b' else normal_lane_width)
                }
                ET.SubElement(e, "lane", **lane_attrs)
    with open(path, "wb") as f:
        f.write(prettify(edges))
    print(f"[OK] edges -> {path}")
def write_connections(path=CONN_FILE):
    cons = ET.Element("connections")

    # 去向映射（保持原有逻辑不变）
    straight_map = {"east_in": "west_out", "west_in": "east_out", "north_in": "south_out", "south_in": "north_out"}
    right_map = {"east_in": "north_out", "west_in": "south_out", "north_in": "west_out", "south_in": "east_out"}
    left_map = {"east_in": "south_out", "west_in": "north_out", "north_in": "east_out", "south_in": "west_out"}
    out_counts = {k: int(LANES[k]) for k in ["east_out", "west_out", "north_out", "south_out"]}

    def add_conn(fr_edge, fr_lane, to_edge, to_lane, allow=None):
        attrs = {"from": fr_edge, "to": to_edge, "fromLane": str(fr_lane), "toLane": str(to_lane)}
        if allow: attrs["allow"] = allow
        ET.SubElement(cons, "connection", **attrs)

    # 处理进口道（近段）到出口道的连接
    for in_edge in ["east_in", "west_in", "north_in", "south_in"]:
        if in_edge not in LANE_FUNCTIONS:
            continue
        func_str = LANE_FUNCTIONS[in_edge]
        # 倒序处理，确保直行车道从左到右对应出口从左到右
        # func_str = func_str[::-1]

        to_s = straight_map[in_edge]  # 直行去向
        to_r = right_map[in_edge]    # 右转去向
        to_l = left_map[in_edge]     # 左转去向

        # 逐车道解析功能，生成转向连接

        # 计算['s', 't', 'u']的数量（直行车道数）
        straight_count = func_str.count('s') + func_str.count('t') + func_str.count('u')+func_str.count('b')
        left_count = func_str.count('l') + func_str.count('u')
        for lane_idx, func in enumerate(func_str):
            # 普通车道：按功能生成转向
            allow = None  # 非公交道不限制车辆类型（除bus已在edges中禁止）
            # 右转功能（r/t）：连出口最右车道（0）
            if func in ['r', 't']:
                add_conn(in_edge, lane_idx, to_r, "0", allow)
            # 左转功能（l/u）：连出口最左车道（n_out_l-1）
            if func in ['l', 'u']:
                left_count-=1
                left_target = str(out_counts[to_l] - 1 - left_count)
                add_conn(in_edge, lane_idx, to_l, left_target, allow)
            # 直行功能（s/t/u）：连出口对应车道（按出口车道数分配）
            if func in ['b','s', 't', 'u']:
                straight_count -= 1
                # 直行车道按从左到右，对应出口从左到右（如出口3车道：2→1→0）
                out_lane = str(out_counts[to_s] - 1 - straight_count)
                add_conn(in_edge, lane_idx, to_s, out_lane, allow)

    # 处理远段到近段的连接（简化：远段车道按索引对应近段车道，非公交道禁止bus）
    for in_edge in ["east_in", "west_in", "north_in", "south_in"]:
        if in_edge not in LANE_FUNCTIONS:
            continue
        far_edge = in_edge.replace("_in", "_in_far")
        func_str = LANE_FUNCTIONS[in_edge]
        total_lanes = len(func_str)

        # 远段车道数 = 近段车道数（无公交道，功能同近段非公交道）
        for lane_idx in range(total_lanes):
            func = func_str[lane_idx]
            # 近段公交道：仅允许bus从远段进入
            if func == 'b':
                add_conn(far_edge, lane_idx, in_edge, lane_idx, allow="bus")
            # 近段普通车道：禁止bus
            else:
                add_conn(far_edge, lane_idx, in_edge, lane_idx, allow=None)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(prettify(cons))
    print(f"[OK] connections -> {path}")

def build_net(nodes=NODES_FILE, edges=EDGES_FILE, out_net=NET_FILE, conns_path=CONN_FILE):
    netconvert = shutil.which("netconvert")
    if netconvert is None:
        print("[WARN] 未找到 netconvert，请手动执行：netconvert -n {} -e {} {} -o {}".format(
            nodes, edges, ("" if not conns_path else f"-x {conns_path}"), out_net
        ))
        return False
    cmd = ["netconvert", "-n", nodes, "-e", edges]
    if conns_path:
        cmd += ["-x", conns_path]
    cmd += ["-o", out_net]
    print("[RUN] " + " ".join(cmd))
    subprocess.run(cmd, check=True)
    print(f"[OK] net -> {out_net}")
    return True


write_nodes()
write_edges()
write_connections()
build_net()
