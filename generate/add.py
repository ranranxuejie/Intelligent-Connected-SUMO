import xml.etree.ElementTree as ET
from xml.dom import minidom
import json

# 读取配置文件
with open("./generate/config.json", "r", encoding="utf-8") as f:
    config = json.load(f)


def inject_tl_into_net():
    net_file = "./test/crossroad.net.xml"
    tl_id = "center"
    output_tll_file = "./test/traffic_light.add.xml"

    # 信号配时参数
    signal = config["signal_timing"]
    green_cav = signal["green_cav"]
    green_ew_straight = signal["green_ew_straight"]
    green_ns_straight = signal["green_ns_straight"]
    green_ew_left = signal["green_ew_left"]
    green_ns_left = signal["green_ns_left"]
    yellow_time = signal["yellow_time"]
    all_red_time = signal["all_red_time"]

    # === 最小/最大绿灯时间（秒）===
    min_green_straight = 20
    max_green_straight = 60
    min_green_left = 20
    max_green_left = 60

    tree = ET.parse(net_file)
    root = tree.getroot()

    # === Step 1: 收集所有 tl="center" 的 connection ===
    connections = []
    max_index = -1
    for conn in root.iter("connection"):
        if conn.get("tl") == tl_id:
            idx_str = conn.get("linkIndex") or conn.get("tlIndex")
            if idx_str is None:
                continue
            try:
                idx = int(idx_str)
            except ValueError:
                continue
            connections.append((idx, conn.get("from"), conn.get("to"), conn.get("dir"), conn.get("allow")))
            max_index = max(max_index, idx)

    if not connections:
        raise RuntimeError(f"致命错误：在 {net_file} 中未找到任何 tl='{tl_id}' 的 connection！")

    print(f"[DEBUG] 找到 {len(connections)} 个受控连接，max_index={max_index}")

    # === Step 2: 分类 link ===
    straight_map = {"east_in": "west_out", "west_in": "east_out", "north_in": "south_out", "south_in": "north_out"}
    left_map = {"east_in": "north_out", "west_in": "south_out", "north_in": "east_out", "south_in": "west_out"}
    right_map = {"east_in": "south_out", "west_in": "north_out", "north_in": "west_out", "south_in": "east_out"}

    cav = set()
    ew_straight = set()
    ew_left = set()
    ns_straight = set()
    ns_left = set()
    right_turns = set()

    for idx, frm, to, d, allow in connections:
        # if allow == "taxi":
        #     cav.add(idx)
        #     continue
        # if d not in ('r', 's', 'l'):
        #     if straight_map.get(frm) == to:
        #         d = 's'
        #     elif left_map.get(frm) == to:
        #         d = 'l'
        #     elif right_map.get(frm) == to:
        #         d = 'r'
        #     else:
        #         continue
        if d == 'r':
            right_turns.add(idx)
        elif d == 's':
            if frm in ("east_in", "west_in"):
                ew_straight.add(idx)
            else:
                ns_straight.add(idx)
        elif d == 'l':
            if frm in ("east_in", "west_in"):
                ew_left.add(idx)
            else:
                ns_left.add(idx)

    total = max_index + 1
    print(f"[DEBUG] total links = {total}")
    print(f"[DEBUG] CAV专用: {sorted(cav)}")
    print(f"[DEBUG] 右转: {sorted(right_turns)}")
    print(f"[DEBUG] EW直行: {sorted(ew_straight)}, EW左转: {sorted(ew_left)}")
    print(f"[DEBUG] NS直行: {sorted(ns_straight)}, NS左转: {sorted(ns_left)}")

    def build_state(active_set, right_set, total, mode):
        s = []
        for i in range(total):
            if i in right_set:
                s.append('g')
            elif i in active_set:
                s.append('G' if mode == 'green' else 'y')
            else:
                s.append('r')
        return "".join(s)

    # ✅ 新增：构建全红相位状态（所有车道均为红色）
    def build_all_red_state(total):
        return "r" * total  # 生成长度为 total 的纯红色字符串

    # === 构建 tlLogic（新增全红相位）===
    new_tl = ET.Element("tlLogic", {
        "id": tl_id,
        "type": "static",
        "programID": "CAV",
        "offset": "0"
    })

    # === 相位配置：绿灯→黄灯→全红，依次循环 ===
    phase_config = [
        # taxi专用相位
        # taxi专用相位
        # (cav, green_cav, 'green', True, min_green_straight, max_green_straight),
        # (cav, yellow_time, 'yellow', False, None, None),
        # (set(), all_red_time, 'all_red', False, None, None),

        # 东西向直行：绿灯 → 黄灯 → 全红
        (ew_straight, green_ew_straight, 'green', True, min_green_straight, max_green_straight),
        (ew_straight, yellow_time, 'yellow', False, None, None),
        (set(), all_red_time, 'all_red', False, None, None),

        # 东西向左转：绿灯 → 黄灯 → 全红
        (ew_left, green_ew_left, 'green', True, min_green_left, max_green_left),
        (ew_left, yellow_time, 'yellow', False, None, None),
        (set(), all_red_time, 'all_red', False, None, None),

        # 南北向直行：绿灯 → 黄灯 → 全红
        (ns_straight, green_ns_straight, 'green', True, min_green_straight, max_green_straight),
        (ns_straight, yellow_time, 'yellow', False, None, None),
        (set(), all_red_time, 'all_red', False, None, None),

        # 南北向左转：绿灯 → 黄灯 → 全红
        (ns_left, green_ns_left, 'green', True, min_green_left, max_green_left),
        (ns_left, yellow_time, 'yellow', False, None, None),
        (set(), all_red_time, 'all_red', False, None, None),
    ]
    for active_set, dur, mode, is_green, min_d, max_d in phase_config:
        # 区分普通相位和全红相位的状态生成逻辑
        if mode == 'all_red':
            state_str = build_all_red_state(total)
        else:
            state_str = build_state(active_set, right_turns, total, mode)

        attrib = {"duration": str(dur), "state": state_str}
        if is_green:
            attrib["minDur"] = str(min_d)
            attrib["maxDur"] = str(max_d)

        new_tl.append(ET.Element("phase", attrib))
        # 打印相位信息（全红相位单独标注）
        if mode == 'all_red':
            print(f"[DEBUG] 相位: 全红, dur={dur}, state={state_str}")
        else:
            print(f"[DEBUG] 相位: {mode}, dur={dur}, state={state_str}" + (
                f", min={min_d}, max={max_d}" if is_green else ""))

    # === 创建 additional 根节点并写入独立文件 ===
    additional = ET.Element("additional")
    additional.append(new_tl)
    rough = ET.tostring(additional, 'utf-8')
    reparsed = minidom.parseString(rough)

    with open(output_tll_file, "w", encoding="utf-8") as f:
        f.write(reparsed.toprettyxml(indent="  "))

    print(f"[OK] 交通灯逻辑已成功写入: {output_tll_file}")
    print(f"请在 .sumocfg 配置文件中添加：<additional-files value=\"{output_tll_file}\"/>")

inject_tl_into_net()
