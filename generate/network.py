#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import shutil
import subprocess
import xml.etree.ElementTree as ET
from xml.dom import minidom

# -------------------------- 可调参数 --------------------------
center_x, center_y = 0, 0
road_length = 500        # 进口总长
bus_only_length = 200    # 距路口最后多少米为公交专用
speed_kmh = 60
speed_ms = round(speed_kmh / 3.6, 2)

# 8 条边的普通车道数（不含公交专用道）
LANES = {
    "east_in": 4,
    "west_in": 4,
    "north_in": 4,
    "south_in": 4,
    "east_out": 3,
    "west_out": 3,
    "north_out": 3,
    "south_out": 3,
}

# 进口边是否启用"近段公交专用车道"（右起第二车道）
BUS_LANE_ENABLED = {
    "east_in": True,
    "west_in": True,
    "north_in": True,
    "south_in": True,
}

bus_lane_width = 3.5
normal_lane_width = 3.5
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

    # 进口拆分为两段：*_in_far（远段：端点->mid），*_in（近段：mid->center）
    edge_defs = [
        ("east_in_far",  "east_end",  "east_mid",  True,  "east_in"),
        ("east_in",      "east_mid",  "center",    True,  "east_in"),
        ("west_in_far",  "west_end",  "west_mid",  True,  "west_in"),
        ("west_in",      "west_mid",  "center",    True,  "west_in"),
        ("north_in_far", "north_end", "north_mid", True,  "north_in"),
        ("north_in",     "north_mid", "center",    True,  "north_in"),
        ("south_in_far", "south_end", "south_mid", True,  "south_in"),
        ("south_in",     "south_mid", "center",    True,  "south_in"),

        ("east_out",  "center", "east_end",  False, None),
        ("west_out",  "center", "west_end",  False, None),
        ("north_out", "center", "north_end", False, None),
        ("south_out", "center", "south_end", False, None),
    ]

    for edge_id, frm, to, is_in, base_key in edge_defs:
        base_lanes = int(LANES[base_key]) if base_key else int(LANES[edge_id])

        # 仅在近段 *_in 启用公交专用道；远段 *_in_far 混行
        enable_bus_lane_here = is_in and edge_id.endswith("_in") and BUS_LANE_ENABLED.get(base_key, False)
        total_lanes = base_lanes + (1 if enable_bus_lane_here else 0)

        e = ET.SubElement(
            edges, "edge",
            id=edge_id, **{"from": frm, "to": to},
            numLanes=str(total_lanes),
            speed=str(speed_ms),
        )

        # 公交专用车道：右起第二车道 index=1（若仅1条普通车道，则 index=0）
        bus_lane_index = None
        if enable_bus_lane_here:
            bus_lane_index = 1 if base_lanes >= 1 else 0

        # 是否在此段禁变道（仅近段 *_in）
        forbid_changes = edge_id.endswith("_in")

        # 从右到左依次编号
        for i in range(total_lanes):
            is_bus_lane = (enable_bus_lane_here and i == bus_lane_index)
            lane_attrs = {
                "index": str(i),
                "speed": str(speed_ms),
                "width": str(bus_lane_width if is_bus_lane else normal_lane_width),
            }

            # 近段：公交专用/普通车道权限
            if enable_bus_lane_here:
                if is_bus_lane:
                    lane_attrs["allow"] = "bus"
                else:
                    lane_attrs["disallow"] = "bus"
            # 远段：不设置 allow/disallow（混行）

            # 禁止变道（仅近段）
            if forbid_changes:
                lane_attrs["changeLeft"] = "emergency"
                lane_attrs["changeRight"] = "emergency"
                # 如需仅允许应急车辆向右变道，可改为：
                # lane_attrs["changeLeft"] = "none"
                # lane_attrs["changeRight"] = "emergency"

            ET.SubElement(e, "lane", **lane_attrs)

    with open(path, "wb") as f:
        f.write(prettify(edges))
    print(f"[OK] edges -> {path}")


def write_connections(path=CONN_FILE):
    cons = ET.Element("connections")

    # 去向映射（已按你更正后的左右转方向）
    straight_map = {
        "east_in": "west_out",
        "west_in": "east_out",
        "north_in": "south_out",
        "south_in": "north_out",
    }
    right_map = {
        "east_in": "north_out",   # 东→右转到北
        "west_in": "south_out",   # 西→右转到南
        "north_in": "west_out",   # 北→右转到西
        "south_in": "east_out",   # 南→右转到东
    }
    left_map = {
        "east_in": "south_out",   # 东→左转到南
        "west_in": "north_out",   # 西→左转到北
        "north_in": "east_out",   # 北→左转到东
        "south_in": "west_out",   # 南→左转到西
    }

    # 出口车道数（需与 edges 中 numLanes 一致；出口没有公交增量）
    out_counts = {k: int(LANES[k]) for k in ["east_out", "west_out", "north_out", "south_out"]}

    def add_conn(fr_edge, fr_lane, to_edge, to_lane, allow=None, disallow=None):
        attrs = {
            "from": fr_edge,
            "to": to_edge,
            "fromLane": str(fr_lane),
            "toLane": str(to_lane),  # 强制转字符串
        }
        if allow: attrs["allow"] = allow
        if disallow: attrs["disallow"] = disallow
        ET.SubElement(cons, "connection", **attrs)
    def plan_straight_targets(to_edge):
        n = max(out_counts.get(to_edge, 1), 1)
        if n == 1:
            return [0]
        if n == 2:
            return [0, 1]
        # n >= 3：优先最右(0)、最左(n-1)，再补中间
        mid = n // 2
        normals = [0, n - 1, mid] + [i for i in range(n) if i not in (0, n - 1, mid)]
        return normals
    def rightmost_to_lane(edge):  # 出口最右
        return 0
    def leftmost_to_lane(edge):   # 出口最左
        n = max(out_counts.get(edge, 1), 1)
        return max(n - 1, 0)
    for in_edge in ["east_in", "west_in", "north_in", "south_in"]:
        has_bus = BUS_LANE_ENABLED.get(in_edge, False)
        base_norm = int(LANES[in_edge])
        total_in = base_norm + (1 if has_bus else 0)
        if total_in == 0:
            continue

        bus_idx = 1 if (has_bus and base_norm >= 1) else (0 if has_bus else None)
        normal_indices = [i for i in range(total_in) if i != bus_idx]

        to_s = straight_map[in_edge]
        to_r = right_map[in_edge]
        to_l = left_map[in_edge]

        # === 公交专用道：仅直行 → 连接到直行出口的最右侧车道（lane 0） ===
        if bus_idx is not None:
            add_conn(in_edge, bus_idx, to_s, "0", allow="bus")  # 显式用字符串 "0"
        # === 普通车道连接 ===
        if not normal_indices:
            continue

        normal_indices = sorted(normal_indices)  # [0,1,2,...] 0=最右
        n_norm = len(normal_indices)

        # 出口车道数
        n_out_s = out_counts[to_s]
        n_out_r = out_counts[to_r]
        n_out_l = out_counts[to_l]

        if n_norm == 1:
            # 唯一车道：可直行、右转、左转
            lane = normal_indices[0]
            # 直行：连到出口唯一车道（0）
            add_conn(in_edge, lane, to_s, "0")
            add_conn(in_edge, lane, to_r, "0")
            add_conn(in_edge, lane, to_l, "0")

        elif n_norm == 2:
            # 右侧车道（0）→ 右转 + 直行
            # 左侧车道（1）→ 左转 + 直行
            right_lane = normal_indices[0]
            left_lane = normal_indices[1]
            add_conn(in_edge, right_lane, to_r, "0")
            add_conn(in_edge, right_lane, to_s, "0")  # 直行到最右
            add_conn(in_edge, left_lane, to_l, str(n_out_l - 1) if n_out_l > 0 else "0")
            add_conn(in_edge, left_lane, to_s, str(n_out_s - 1) if n_out_s > 0 else "0")  # 直行到最左

        else:
            # n_norm >= 3
            rightmost_norm = normal_indices[0]      # 最右 → 右转
            leftmost_norm = normal_indices[-1]      # 最左 → 左转
            middle_norms = normal_indices[1:-1]     # 中间 → 直行

            # 右转：连到出口最右车道（0）
            add_conn(in_edge, rightmost_norm, to_r, "0")

            # 左转：连到出口最左车道（n-1）
            left_target = str(n_out_l - 1) if n_out_l > 0 else "0"
            add_conn(in_edge, leftmost_norm, to_l, left_target)

            # 直行：middle_norms 是 [1, 2, ..., N-2]（从右到左）
            # 但我们希望：从左到右的中间车道 → 从左到右的出口车道
            # 所以将 middle_norms 反转，得到从左到右顺序
            middle_from_left = list(reversed(middle_norms))  # e.g., [3,2,1] if middle_norms=[1,2,3]

            # 出口车道从左到右：[n-1, n-2, ..., 0]
            out_from_left = list(range(n_out_s - 1, -1, -1))  # e.g., [2,1,0]

            # 如果中间车道多于出口车道，循环使用出口车道（从左开始）
            for i, in_lane in enumerate(middle_from_left):
                if n_out_s == 0:
                    continue
                out_lane = out_from_left[i % len(out_from_left)]
                add_conn(in_edge, in_lane, to_s, str(out_lane))
    # 2) 处理远段到近段的连接（从左侧顺次连接，远端最右侧连接剩余其他车道）
    for in_edge in ["east_in", "west_in", "north_in", "south_in"]:
        far_edge = in_edge.replace("_in", "_in_far")

        # 获取远段和近段的车道数
        far_base_norm = int(LANES[in_edge])  # 远段的普通车道数
        far_has_bus = False  # 远段没有公交专用道
        far_total_lanes = far_base_norm

        has_bus = BUS_LANE_ENABLED.get(in_edge, False)
        near_base_norm = int(LANES[in_edge])  # 近段的普通车道数
        near_total_lanes = near_base_norm + (1 if has_bus else 0)

        # 获取近段公交专用道索引
        near_bus_idx = None
        if has_bus:
            near_bus_idx = 1 if (near_base_norm >= 1) else (0 if has_bus else None)

        # 一一对应连接：远段车道索引对应近段车道索引
        # 远段普通车道（从左到右）连接到近段普通车道（从左到右）
        far_normal_lanes = list(range(far_total_lanes))  # 远段所有普通车道
        near_normal_lanes = [i for i in range(near_total_lanes) if i != near_bus_idx]  # 近段非公交专用道

        # 按索引顺序一一对应连接
        for i in range(min(len(far_normal_lanes), len(near_normal_lanes))):
            far_lane = far_normal_lanes[i]
            near_lane = near_normal_lanes[i]
            # 普通车道，不允许公交通过
            add_conn(far_edge, far_lane, in_edge, near_lane, disallow="bus")

        # 如果远段车道数多于近段普通车道数，剩余的远段车道连接到近段公交专用道（只允许公交通过）
        if near_bus_idx is not None:
            for i in range(len(far_normal_lanes)):
                if i >= len(near_normal_lanes):  # 剩余的远段车道
                    far_lane = far_normal_lanes[i]
                    # 连接到公交专用道，只允许公交通过
                    add_conn(far_edge, far_lane, in_edge, near_bus_idx, allow="bus")

                # 远段所有车道也可以连接到公交专用道（但只允许公交通过）
                far_lane = far_normal_lanes[i]
                add_conn(far_edge, far_lane, in_edge, near_bus_idx, allow="bus")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(prettify(cons))
    print(f"[OK] connections ->", path)


write_nodes()
write_edges()
write_connections()

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
build_net()
