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

if __name__ == "__main__":
    stats = analyze_tripinfo("./output/tripinfo.xml")
