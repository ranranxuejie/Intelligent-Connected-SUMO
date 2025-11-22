import os
import xml.etree.ElementTree as ET
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.colors as colors
import numpy as np


def plot_split_trajectory(test_name = '20251122_20_cav_first',in_dir = 'east'):
    trajectories = {}
    # ================= 配置区域 =================
    # 1. FCD 文件路径
    FCD_FILE = f"output/{test_name}/fcd.xml"

    # 2. 目标车道前缀
    TARGET_LANE_ID = f"{in_dir}_in_3"

    # 3. 车道长度 (米)
    LANE_LENGTH = 200

    # 4. 筛选特定类型的车
    TARGET_VTYPE = "taxi"


    # ===========================================

    print(f"正在解析 {FCD_FILE} ...")

    # --- 1. 数据解析部分 (保持不变) ---
    context = ET.iterparse(FCD_FILE, events=("start", "end"))
    context = iter(context)
    event, root = next(context)

    for event, elem in context:
        if event == "end" and elem.tag == "timestep":
            current_time = float(elem.get("time"))

            # 这里加个简单的过滤器，如果时间超过3600就不读了，节省内存
            if current_time > 3600:
                elem.clear()
                continue

            for veh in elem.findall("vehicle"):
                lane = veh.get("lane")
                vtype = veh.get("type")
                vid = veh.get("id")

                if TARGET_LANE_ID not in lane:
                    continue

                if TARGET_VTYPE and (TARGET_VTYPE not in vtype):
                    continue

                speed = float(veh.get("speed"))
                pos = float(veh.get("pos"))
                plot_pos = LANE_LENGTH - pos if LANE_LENGTH > 0 else pos

                if vid not in trajectories:
                    trajectories[vid] = {'t': [], 'p': [], 'v': []}

                trajectories[vid]['t'].append(current_time)
                trajectories[vid]['p'].append(plot_pos)
                trajectories[vid]['v'].append(speed)

            root.clear()

    print(f"解析完成，共找到 {len(trajectories)} 条符合条件的轨迹。开始绘图...")

    # ================= 2. 绘图设置 (修改为双子图) =================

    # 设置中文字体
    plt.rcParams['font.sans-serif'] = ['SimHei']
    plt.rcParams['axes.unicode_minus'] = False

    # 创建 2行1列 的子图，共享Y轴 (sharey=True)
    # figsize的高度增加到 12，保证上下两张图有足够空间
    fig, axes = plt.subplots(nrows=2, ncols=1, figsize=(14, 10), sharey=True)
    # 颜色映射设置
    cmap = plt.get_cmap('RdYlGn')
    norm = colors.Normalize(vmin=0, vmax=20)  # 假设最大速度 20m/s

    # 为了添加 colorbar，我们需要保存至少一个绘图对象
    sc_mappable = None

    # --- 3. 遍历数据并分段绘制 ---
    for vid, data in trajectories.items():
        t = np.array(data['t'])
        p = np.array(data['p'])
        v = np.array(data['v'])

        # === 第一部分：0 ~ 1800秒 ===
        # 创建掩码：找出所有时间小于等于 1800 的点
        mask1 = (t <= 1800)
        if np.any(mask1):  # 如果这辆车在这个时间段有数据
            axes[0].scatter(t[mask1], p[mask1], c=v[mask1], cmap=cmap, norm=norm, s=3, alpha=0.8)

        # === 第二部分：1800 ~ 3600秒 ===
        # 创建掩码：找出所有时间大于 1800 且 小于等于 3600 的点
        mask2 = (t > 1800) & (t <= 3600)
        if np.any(mask2):  # 如果这辆车在这个时间段有数据
            sc = axes[1].scatter(t[mask2], p[mask2], c=v[mask2], cmap=cmap, norm=norm, s=3, alpha=0.8)
            if sc_mappable is None:
                sc_mappable = sc

    # --- 4. 设置子图样式 ---

    # 子图 1 设置 (0-1800)
    axes[0].set_title(f'CAV 时空轨迹图（东进口）', fontsize=16)
    axes[0].set_xlim(0, 1800)  # 强制X轴范围
    axes[0].grid(True, linestyle=':', alpha=0.6)
    axes[0].set_ylabel('距离停止线距离 (m)', fontsize=12)
    # 画停止线
    axes[0].axhline(y=0, color='red', linestyle='--', linewidth=2)

    # 子图 2 设置 (1800-3600)
    # axes[1].set_title(f'{TARGET_VTYPE} 时空轨迹 (1800 - 3600s)', fontsize=14)
    axes[1].set_xlim(1800, 3600)  # 强制X轴范围
    axes[1].grid(True, linestyle=':', alpha=0.6)
    axes[1].set_xlabel('仿真时间 (s)', fontsize=12)
    axes[1].set_ylabel('距离停止线距离 (m)', fontsize=12)
    # 画停止线
    axes[1].axhline(y=0, color='red', linestyle='--', linewidth=2)

    # --- 5. 添加共用 Colorbar ---
    # 在图的右侧添加一个 colorbar
    if sc_mappable:
        fig.subplots_adjust(right=0.9)  # 腾出右侧空间
        cbar_ax = fig.add_axes([0.92, 0.15, 0.02, 0.7])  # [left, bottom, width, height]
        fig.colorbar(sc_mappable, cax=cbar_ax, label='速度 (m/s)')
    else:
        print("警告：没有绘制任何数据点，无法生成Colorbar")

    # 调整布局防止重叠 (因为我们手动加了colorbar，所以不用tight_layout的全图模式)
    # plt.tight_layout() # 可选，有时会和add_axes冲突
    os.makedirs('./results', exist_ok=True)
    plt.savefig(f'./results/trajectory_{in_dir}_{test_name}.png')
    plt.show()



# plot_split_trajectory('20251122_20_cav_first','east')
# plot_split_trajectory('20251122_20_cav_first','west')
# plot_split_trajectory('20251122_20_normal','east')
# plot_split_trajectory('20251122_20_normal','west')
plot_split_trajectory('20251122_22_cav_first','east')
plot_split_trajectory('20251122_22_cav_first','west')
