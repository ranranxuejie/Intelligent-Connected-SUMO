import pandas as pd
import xml.etree.ElementTree as ET
import math
from datetime import datetime, timedelta

# ================= 配置区域 =================
FCD_FILE = "output/20251122_20_cav_first/fcd.xml"  # 你的 SUMO 轨迹文件路径
OUTPUT_CSV = "kepler_trajectory_v2.csv"

# 1. 设置坐标原点 (你的特定中心点)
REF_LAT = 31.277272233806915
REF_LON = 121.21776857190831

# 2. 设置仿真对应的真实起始时间 (用于将 0.1s 转为 datetime)
# 格式: 年, 月, 日, 时, 分, 秒
BASE_TIME = datetime(2025, 11, 22, 8, 0, 0)

# 3. 旋转角度设置
# 需求: 顺时针旋转 arctan(68/97)
# math.atan 计算出来的是弧度
ROTATION_ANGLE_RAD = math.atan(68 / 97)


# ===========================================

def convert_fcd_to_kepler_v2():
    data = []
    print(f"正在解析 {FCD_FILE} ...")
    print(f"应用坐标中心: {REF_LAT}, {REF_LON}")
    print(f"应用顺时针旋转角度: {math.degrees(ROTATION_ANGLE_RAD):.2f} 度")

    # 预计算旋转所需的三角函数 (顺时针旋转)
    # x' = x*cos(θ) + y*sin(θ)
    # y' = y*cos(θ) - x*sin(θ)
    cos_theta = math.cos(ROTATION_ANGLE_RAD)
    sin_theta = math.sin(ROTATION_ANGLE_RAD)

    # 经纬度转换系数 (近似值)
    m_per_deg_lat = 111111
    m_per_deg_lon = 111111 * math.cos(math.radians(REF_LAT))

    # 增量解析 XML
    context = ET.iterparse(FCD_FILE, events=("start", "end"))
    context = iter(context)
    event, root = next(context)

    count = 0
    for event, elem in context:
        if event == "end" and elem.tag == "timestep":
            sim_seconds = float(elem.get("time"))

            # --- 【核心修改1】时间格式化 ---
            # 将仿真的秒数加到基准时间上
            current_dt = BASE_TIME + timedelta(seconds=sim_seconds)
            # 格式化为 Kepler 喜欢的字符串格式: YYYY-MM-DD HH:MM:SS
            time_str = current_dt.strftime("%Y-%m-%d %H:%M:%S")

            for veh in elem.findall("vehicle"):
                vid = veh.get("id")
                # 原始 SUMO 坐标 (米)
                x_raw = float(veh.get("x"))
                y_raw = float(veh.get("y"))
                speed = float(veh.get("speed"))

                # --- 【核心修改2】坐标旋转 (顺时针) ---
                # 注意：这里假设 (0,0) 是旋转中心。如果路网中心不是(0,0)，可能需要先平移再旋转
                # 通常 SUMO 路网是以 (0,0) 为起点的，这里直接旋转即可
                x_rot = x_raw * cos_theta + y_raw * sin_theta
                y_rot = y_raw * cos_theta - x_raw * sin_theta

                # --- 【核心修改3】经纬度映射 ---
                new_lon = REF_LON + (x_rot / m_per_deg_lon)
                new_lat = REF_LAT + (y_rot / m_per_deg_lat)

                data.append({
                    "id": vid,
                    "time": time_str,  # 现在是日期时间格式了
                    "longitude": new_lon,
                    "latitude": new_lat,
                    "speed": speed,
                    "type": veh.get("type"),
                    # 保留原始秒数用于调试(可选)
                    # "sim_time": sim_seconds
                })
                count += 1

            root.clear()

    print(f"解析完成，正在保存 CSV (共 {count} 条数据)...")
    df = pd.DataFrame(data)
    # 重新给id编号（从0开始）
    df['id'] = pd.Categorical(df['id']).codes
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"完成！请上传 {OUTPUT_CSV} 到 Kepler.gl")
    print("注意：在 Kepler 中添加 Filter 时，现在会显示真实的日期时间轴。")


if __name__ == "__main__":
    convert_fcd_to_kepler_v2()
