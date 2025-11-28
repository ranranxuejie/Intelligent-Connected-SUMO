import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.colors as colors
import numpy as np
import os
import xml.etree.ElementTree as ET

# ================= 美化配置 (可选) =================
import matplotlib as mpl
mpl.rcParams['font.family'] = 'sans-serif'
mpl.rcParams['font.sans-serif'] = ['SimHei']
mpl.rcParams['axes.unicode_minus'] = False
mpl.rcParams['font.size'] = 14
mpl.rcParams['axes.spines.top'] = False
mpl.rcParams['axes.spines.right'] = False

# 信号灯状态映射字典
LIGHT_STATE_MAP = {
    'g': 'green',  # 绿灯
    'G': 'green',  # 绿灯（可能是方向指示）
    'y': 'yellow',  # 黄灯
    'Y': 'yellow',  # 黄灯（可能是方向指示）
    'r': 'red',  # 红灯
    'R': 'red'  # 红灯（可能是方向指示）
}

# 进口道对应的信号灯索引映射
APPROACH_TO_LIGHT_INDEX = {
    'east': 7,  # 假设东进口对应state字符串中的第5个字符（索引4）
    'west': 7,  # 假设西进口对应state字符串中的第10个字符（索引9）
    'north': 6,  # 假设北进口对应state字符串中的第15个字符（索引14）
    'south': 6  # 假设南进口对应state字符串中的第20个字符（索引19）
}


def parse_traffic_light_config(tl_file="test/traffic_light.add.xml"):
    """
    解析交通信号灯配置文件，返回信号灯周期和状态信息
    """
    try:
        tree = ET.parse(tl_file)
        root = tree.getroot()

        # 找到center交通信号灯的逻辑配置
        tl_logic = root.find(".//tlLogic[@id='center']")
        if not tl_logic:
            print(f"警告: 在{tl_file}中找不到center交通信号灯配置")
            return None

        phases = []
        total_duration = 0

        # 解析每个相位
        for phase in tl_logic.findall("phase"):
            duration = float(phase.get("duration"))
            state = phase.get("state")
            phases.append({
                "duration": duration,
                "state": state,
                "start_time": total_duration
            })
            total_duration += duration

        return {
            "phases": phases,
            "cycle_length": total_duration
        }
    except Exception as e:
        print(f"解析交通信号灯配置文件时出错: {e}")
        return None


def get_light_state_at_time(tl_config, approach, time):
    """
    根据时间获取特定进口道的信号灯状态
    """
    if not tl_config or approach not in APPROACH_TO_LIGHT_INDEX:
        return 'unknown'

    cycle_time = time % tl_config["cycle_length"]
    light_index = APPROACH_TO_LIGHT_INDEX[approach]

    for phase in tl_config["phases"]:
        if phase["start_time"] <= cycle_time < phase["start_time"] + phase["duration"]:
            # 确保索引有效
            if light_index < len(phase["state"]):
                state_char = phase["state"][light_index]
                return LIGHT_STATE_MAP.get(state_char, 'unknown')

    return 'unknown'


def add_traffic_light_info(ax, tl_config, approach, x_range, y_pos=0):
    """
    在指定轴上添加交通信号灯信息
    """
    if not tl_config or approach not in APPROACH_TO_LIGHT_INDEX:
        return

    # 采样时间点，每0.5秒检查一次状态变化
    sample_times = np.arange(x_range[0], x_range[1], 0.5)

    current_state = None
    state_start_time = x_range[0]
    stop_line_loc = 0.2
    width = 0.04
    for t in sample_times:
        state = get_light_state_at_time(tl_config, approach, t)

        # 状态变化时，绘制前一个状态的区域
        if state != current_state and current_state is not None:
            if current_state == 'green':
                color = 'green'
                alpha = 0.6
            elif current_state == 'yellow':
                color = 'yellow'
                alpha = 0.6
            elif current_state == 'red':
                color = 'red'
                alpha = 0.6
            else:
                color = 'gray'
                alpha = 0.1

            # 绘制信号灯状态区域（在停止线位置上下一定范围）
            ax.axvspan(state_start_time, t, ymin=stop_line_loc-width/2, ymax=stop_line_loc+width/2, color=color, alpha=alpha, zorder=0)
            state_start_time = t

        current_state = state

    # 绘制最后一个状态
    if current_state is not None:
        if current_state == 'green':
            color = 'green'
            alpha = 0.2
        elif current_state == 'yellow':
            color = 'yellow'
            alpha = 0.2
        elif current_state == 'red':
            color = 'red'
            alpha = 0.2
        else:
            color = 'gray'
            alpha = 0.1

        ax.axvspan(state_start_time, x_range[1], ymin=stop_line_loc-width/2, ymax=stop_line_loc+width/2, color=color, alpha=alpha, zorder=0)


def plot_aligned_trajectory(test_name='20251122_20_cav_first', in_dir='east'):
    # ================= 配置区域 =================
    FCD_FILE = f"output/{test_name}/fcd.xml"
    TL_FILE = "test/traffic_light.add.xml"  # 交通信号灯配置文件路径
    TARGET_VTYPE = "taxi"

    # 1. 定义路网拓扑：{方向: (进口车道, 交叉口内部车道)}
    LANE_MAP = {
        'east': ('east_in_3', 'center_5_2'),
        'west': ('west_in_3', 'center_15_3')
    }

    if in_dir not in LANE_MAP:
        print(f"错误: 未知的方向 '{in_dir}'")
        return

    IN_LANE_ID, INNER_LANE_ID = LANE_MAP[in_dir]

    print(f"=== 开始分析 {in_dir} 方向 ===")
    print(f"进口车道: {IN_LANE_ID}")
    print(f"内部车道: {INNER_LANE_ID}")
    print(f"正在解析文件: {FCD_FILE} ...")

    # 解析交通信号灯配置
    tl_config = parse_traffic_light_config(TL_FILE)
    if tl_config:
        print(f"成功解析交通信号灯配置，周期长度: {tl_config['cycle_length']}秒")

    # ================= 第一步：数据读取与存储 =================
    # 我们需要先存下来，计算出进口道的最大pos，再进行坐标转换
    raw_data = {}  # {vid: [{'t': time, 'lane': lane, 'pos': pos, 'v': speed}, ...]}
    max_inlet_pos_observed = 0.0  # 用于记录进口道观测到的最大位置

    try:
        context = ET.iterparse(FCD_FILE, events=("start", "end"))
        context = iter(context)
        event, root = next(context)

        for event, elem in context:
            if event == "end" and elem.tag == "timestep":
                current_time = float(elem.get("time"))
                if current_time > 3600:
                    elem.clear()
                    continue

                for veh in elem.findall("vehicle"):
                    lane = veh.get("lane")
                    vtype = veh.get("type")
                    vid = veh.get("id")

                    # 筛选车型
                    if TARGET_VTYPE and (TARGET_VTYPE not in vtype):
                        continue

                    # 筛选感兴趣的车道
                    # 使用 exact match 或者 startswith 防止匹配到错误的副作用
                    # 这里假设 sumolib 没有改乱 lane id，用包含匹配
                    is_in_lane = IN_LANE_ID in lane
                    is_inner_lane = INNER_LANE_ID in lane

                    if not (is_in_lane or is_inner_lane):
                        continue

                    pos = float(veh.get("pos"))
                    speed = float(veh.get("speed"))

                    # 更新进口道的最大观测位置 (用于后续对齐)
                    if is_in_lane:
                        if pos > max_inlet_pos_observed:
                            max_inlet_pos_observed = pos

                    if vid not in raw_data:
                        raw_data[vid] = []

                    raw_data[vid].append({
                        't': current_time,
                        'lane': lane,
                        'pos': pos,
                        'v': speed,
                        'is_inlet': is_in_lane  # 标记是否在进口道
                    })

                root.clear()
    except FileNotFoundError:
        print(f"错误: 找不到文件 {FCD_FILE}")
        return

    # ================= 第二步：坐标对齐与转换 =================
    # 核心逻辑：使用 max_inlet_pos_observed 作为基准
    # 进口道坐标 = max_inlet_pos_observed - raw_pos (确保终点是0)
    # 内部道坐标 = - raw_pos (起点是0，向负方向延伸)

    print(f"数据读取完毕。")
    print(f"检测到 {IN_LANE_ID} 的最大行驶位置(StopLine参考点)为: {max_inlet_pos_observed:.2f} m")
    print("正在执行坐标缝合...")

    plot_trajectories = {}  # {vid: {'t':[], 'p':[], 'v':[]}}

    for vid, records in raw_data.items():
        plot_trajectories[vid] = {'t': [], 'p': [], 'v': []}

        for r in records:
            if r['is_inlet']:
                # 进口道：减去最大值，实现 0 对齐
                # 比如最大是192.5，当前是190.0，画出来就是 2.5 (距离停止线)
                # 当前是192.5，画出来就是 0.0
                plot_pos = max_inlet_pos_observed - r['pos']
            else:
                # 内部道：直接取负
                plot_pos = -r['pos']

            # 过滤掉异常跳变 (可选：如果数据中有瞬间跳变太大可以过滤)

            plot_trajectories[vid]['t'].append(r['t'])
            plot_trajectories[vid]['p'].append(plot_pos)
            plot_trajectories[vid]['v'].append(r['v'])

    print(f"准备绘图，共 {len(plot_trajectories)} 条轨迹...")

    # ================= 第三步：双子图绘制 =================
    fig, axes = plt.subplots(nrows=2, ncols=1, figsize=(14, 12),dpi=300, sharey=True)

    cmap = plt.get_cmap('RdYlGn')
    norm = colors.Normalize(vmin=0, vmax=20)
    sc_mappable = None
    TIME_SPLIT = 1800

    for vid, data in plot_trajectories.items():
        t = np.array(data['t'])
        p = np.array(data['p'])
        v = np.array(data['v'])

        # 0 ~ 1800
        mask1 = (t <= TIME_SPLIT)
        if np.any(mask1):
            axes[0].scatter(t[mask1], p[mask1], c=v[mask1], cmap=cmap, norm=norm, s=2, alpha=0.8)

        # 1800 ~ 3600
        mask2 = (t > TIME_SPLIT)
        if np.any(mask2):
            sc = axes[1].scatter(t[mask2], p[mask2], c=v[mask2], cmap=cmap, norm=norm, s=2, alpha=0.8)
            if sc_mappable is None: sc_mappable = sc

    # ================= 样式设置 =================
    def style_ax(ax, title_suffix, x_range):
        ax.set_title(f'CAV 连续轨迹 ({title_suffix})', fontsize=14)
        ax.set_xlim(x_range)
        # Y轴范围根据实际数据调整，通常进口道很长(正)，内部道较短(负)
        # 设为 -50 到 200 比较通用
        ax.set_ylim(-50,200)
        ax.set_ylabel('距离停止线距离 (m)', fontsize=12)
        ax.grid(True, linestyle=':', alpha=0.6)
        # 0线就是完美的拼接缝
        ax.axhline(y=0, color='red', linestyle='-', linewidth=1.5, label='停止线 (拼接点)')

        # 添加红绿灯信息
        if tl_config:
            add_traffic_light_info(ax, tl_config, in_dir, x_range)

    style_ax(axes[0], '0-1800s', (0, 1800))
    style_ax(axes[1], '1800-3600s', (1800, 3600))

    axes[1].set_xlabel('仿真时间 (s)', fontsize=14)

    if sc_mappable:
        fig.subplots_adjust(right=0.9)
        cbar_ax = fig.add_axes([0.92, 0.15, 0.02, 0.7])
        fig.colorbar(sc_mappable, cax=cbar_ax, label='速度 (m/s)')

    # 根据test_name确定是Normal还是CAV First模式，并提取速度值
    if test_name == 'normal':
        mode_title = 'Normal'
        vmin_text = ''
    else:
        mode_title = 'CAV First'
        # 从文件夹名称中提取速度值，例如 cav_first_4.17 -> 4.17 m/s
        try:
            vmin_value = float(test_name.split('_')[-1])
            vmin_text = f' (Vmin={vmin_value:.2f} m/s)'
        except:
            vmin_text = ''

    # 添加大标题显示模式和速度信息
    fig.suptitle(f'{mode_title}{vmin_text}', fontsize=20, fontweight='bold')

    save_path = f'results/{test_name}_{in_dir}.png'
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"图片已保存至: {save_path}")
    plt.show()


for MIN_SPEED in [0, 15 / 3.6, 20 / 3.6, 25 / 3.6, 30 / 3.6]:
    if MIN_SPEED == 0:
        out_folder = 'normal'
    else:
        out_folder = f'cav_first_{MIN_SPEED:.2f}'
    plot_aligned_trajectory(f'{out_folder}', 'east')
    plot_aligned_trajectory(f'{out_folder}', 'west')
