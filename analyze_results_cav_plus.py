import xml.etree.ElementTree as ET
import numpy as np
import os

class SumoAnalyzer:
    def __init__(self, files):
        self.files = files
        # 数据容器
        self.data = {
            'HV': {'timeLoss': [], 'waitingCount': [], 'duration': [], 'routeLength': [], 'CO2': []},
            'CAV': {'timeLoss': [], 'waitingCount': [], 'duration': [], 'routeLength': [], 'CO2': []}
        }
        self.global_stats = {
            'collisions': 0,
            'emergencyStops': 0,
            'max_queue_hv': 0.0,
            'max_queue_cav': 0.0
        }
        
        # --- 核心配置：根据您的表格定义的车道映射 ---
        # 只有这两个车道被标记为 "允许taxi（CAV专用）"
        self.cav_dedicated_lanes = {'east_in_3', 'west_in_3'}
        
        # 定义所有进口Edge的前缀，用于过滤掉交叉口内部车道(如:cluster_xxx)
        self.target_edges = ('east_in', 'west_in', 'north_in', 'south_in')

    def is_cav_vehicle(self, vehicle_id, v_type):
        """
        判断【车辆】是否为CAV (用于分析Tripinfo)
        条件：类型含taxi + 东西向进入 + 直行
        """
        is_taxi = 'taxi' in v_type
        # 检查是否为东西向 (east_in 或 west_in)
        is_ew = ('east_in' in vehicle_id) or ('west_in' in vehicle_id)
        # 检查是否为直行 (straight)
        is_straight = 'straight' in vehicle_id
        
        return is_taxi and is_ew and is_straight

    def parse_statistic(self):
        """解析 statistic.xml 获取全局安全统计"""
        if not os.path.exists(self.files['statistic']):
            print("Warning: statistic.xml not found.")
            return

        tree = ET.parse(self.files['statistic'])
        root = tree.getroot()
        
        safety = root.find('safety')
        if safety is not None:
            self.global_stats['collisions'] = int(safety.get('collisions', 0))
            self.global_stats['emergencyStops'] = int(safety.get('emergencyStops', 0))

    def parse_tripinfo(self):
        """解析 tripinfo.xml 获取 延误、停车、排放、效率指标"""
        if not os.path.exists(self.files['tripinfo']):
            print("Warning: tripinfo.xml not found.")
            return

        # 使用iterparse流式读取，节省内存
        for event, elem in ET.iterparse(self.files['tripinfo'], events=('end',)):
            if elem.tag == 'tripinfo':
                v_id = elem.get('id')
                v_type = elem.get('vType')
                
                # 1. 区分 HV 和 CAV
                if self.is_cav_vehicle(v_id, v_type):
                    cat = 'CAV'
                else:
                    cat = 'HV'

                # 2. 提取指标
                try:
                    self.data[cat]['timeLoss'].append(float(elem.get('timeLoss')))
                    self.data[cat]['waitingCount'].append(int(elem.get('waitingCount')))
                    self.data[cat]['duration'].append(float(elem.get('duration')))
                    self.data[cat]['routeLength'].append(float(elem.get('routeLength')))
                    
                    # 排放数据
                    emissions = elem.find('emissions')
                    if emissions is not None:
                        self.data[cat]['CO2'].append(float(emissions.get('CO2_abs', 0)))
                except ValueError:
                    pass

                elem.clear() # 清理内存

    def parse_queue(self):
        """
        解析 queue.xml 获取最大排队长度。
        依据：东/西进口的第3车道归为CAV排队，其余归为HV排队。
        """
        if not os.path.exists(self.files['queue']):
            print("Warning: queue.xml not found.")
            return

        for event, elem in ET.iterparse(self.files['queue'], events=('end',)):
            if elem.tag == 'lane':
                lane_id = elem.get('id')
                # 获取排队长度 (queueing_length 是 SUMO 标准输出属性)
                q_len = float(elem.get('queueing_length', 0))
                
                # 仅处理我们关心的进口道 (过滤内部车道)
                if lane_id.startswith(self.target_edges):
                    
                    # 判定：是 CAV 专用道 还是 普通 HV 车道
                    if lane_id in self.cav_dedicated_lanes:
                        if q_len > self.global_stats['max_queue_cav']:
                            self.global_stats['max_queue_cav'] = q_len
                    else:
                        if q_len > self.global_stats['max_queue_hv']:
                            self.global_stats['max_queue_hv'] = q_len
                
                elem.clear()

    def calculate_indicators(self):
        """汇总计算平均值"""
        results = {}
        for cat in ['HV', 'CAV']:
            n = len(self.data[cat]['timeLoss'])
            if n == 0:
                results[cat] = None
                continue
            
            # 计算平均值
            avg_delay = np.mean(self.data[cat]['timeLoss'])
            avg_stops = np.mean(self.data[cat]['waitingCount'])
            
            # 计算平均速度 (总路程/总时间)
            total_dist = sum(self.data[cat]['routeLength'])
            total_dur = sum(self.data[cat]['duration'])
            avg_speed = (total_dist / total_dur) if total_dur > 0 else 0
            
            # 计算总排放和车均排放
            total_co2 = sum(self.data[cat]['CO2'])
            avg_co2 = np.mean(self.data[cat]['CO2'])

            results[cat] = {
                'count': n,
                'avg_delay': avg_delay,
                'avg_stops': avg_stops,
                'avg_speed': avg_speed,
                'total_co2': total_co2,
                'avg_co2': avg_co2
            }
        return results

    def print_report(self):
        # 1. 执行解析
        self.parse_statistic()
        self.parse_tripinfo()
        self.parse_queue()
        
        # 2. 计算结果
        res = self.calculate_indicators()
        
        print("\n" + "="*60)
        print("SUMO 仿真指标分析报告 (基于专用道配置)")
        print("="*60)

        # --- 第一部分：基础指标 ---
        print("\n【1】基础指标分析 (HV vs CAV)")
        print(f"{'指标 (Metric)':<30} | {'HV (普通车辆)':<15} | {'CAV (自动驾驶)':<15}")
        print("-" * 65)

        if res['HV'] and res['CAV']:
            # 延误
            print(f"{'车均延误 (Average Delay)':<30} | {res['HV']['avg_delay']:.2f} s{'':<9} | {res['CAV']['avg_delay']:.2f} s")
            # 停车
            print(f"{'车均停车 (Average Stops)':<30} | {res['HV']['avg_stops']:.2f} 次{'':<8} | {res['CAV']['avg_stops']:.2f} 次")
            # 排队 (从 queue.xml 根据车道 ID 区分)
            print(f"{'最大排队长度 (Max Queue)':<30} | {self.global_stats['max_queue_hv']:.2f} m{'':<9} | {self.global_stats['max_queue_cav']:.2f} m")
            # 车辆数
            print(f"{'样本车辆数 (Sample Size)':<30} | {res['HV']['count']}{'':<12} | {res['CAV']['count']}")
        else:
            print("数据不足，无法完成对比分析。")

        # --- 第二部分：综合分析 ---
        print("\n【2】多角度综合分析")

        if res['HV'] and res['CAV']:
            # 1. 效率 (Efficiency)
            print("\n>>> A. 效率分析 (Efficiency)")
            hv_speed = res['HV']['avg_speed']
            cav_speed = res['CAV']['avg_speed']
            print(f"   - HV  平均速度: {hv_speed:.2f} m/s")
            print(f"   - CAV 平均速度: {cav_speed:.2f} m/s")
            
            eff_diff = (cav_speed - hv_speed) / hv_speed * 100
            if eff_diff > 0:
                print(f"   - 结论: 引入专用道后，CAV 通行效率比 HV 高 {eff_diff:.1f}%。")
            else:
                print(f"   - 结论: CAV 通行效率略低于 HV ({eff_diff:.1f}%)，需检查专用道利用率。")

            # 2. 低碳 (Low Carbon)
            print("\n>>> B. 低碳/环境分析 (Low Carbon)")
            hv_co2 = res['HV']['avg_co2']
            cav_co2 = res['CAV']['avg_co2']
            print(f"   - HV  车均CO2排放: {hv_co2:.2f} mg")
            print(f"   - CAV 车均CO2排放: {cav_co2:.2f} mg")
            
            if cav_co2 < hv_co2:
                print("   - 结论: CAV 运行更加平滑，有效降低了单车碳排放。")
            else:
                print("   - 结论: CAV 排放未见明显优势，可能受频繁启停影响。")

            # 3. 安全 (Safety)
            print("\n>>> C. 安全分析 (Safety)")
            print(f"   - 路网总急刹车次数 (Emergency Stops): {self.global_stats['emergencyStops']}")
            print(f"   - 路网总碰撞次数 (Collisions): {self.global_stats['collisions']}")
            print(f"   - HV  停车频次: {res['HV']['avg_stops']:.2f}")
            print(f"   - CAV 停车频次: {res['CAV']['avg_stops']:.2f}")
            
            if res['CAV']['avg_stops'] < res['HV']['avg_stops']:
                print("   - 结论: CAV 停车次数更少，交通流更稳定，追尾风险较低。")

            # 4. 公平性 (Fairness)
            print("\n>>> D. 公平性分析 (Fairness)")
            delay_ratio = res['CAV']['avg_delay'] / res['HV']['avg_delay'] if res['HV']['avg_delay'] > 0 else 0
            print(f"   - 延误比率 (CAV延误 / HV延误): {delay_ratio:.2f}")
            
            if delay_ratio < 0.8:
                print("   - 结论: [不公平] CAV 享有显著路权优势（专用道），牺牲了 HV 的部分效率。")
            elif delay_ratio > 1.2:
                print("   - 结论: [不公平] CAV 延误显著高于 HV，专用道可能出现了排队溢出或信号配置不当。")
            else:
                print("   - 结论: [相对公平] 两种车辆类型的延误水平接近 (0.8 - 1.2 区间)。")
        
        print("\n" + "="*60)


# --- 配置与运行 ---
if __name__ == "__main__":
    # 请根据实际文件名修改此处路径
    OUTPUT_FOLDER = f"output\plus\False_False_0.1"
    input_files = {
        'statistic': f'./{OUTPUT_FOLDER}/statistic.xml',
        'tripinfo': f'./{OUTPUT_FOLDER}/tripinfo.xml',
        'queue': f'./{OUTPUT_FOLDER}/queue.xml'
    }

    # 创建分析器并运行
    analyzer = SumoAnalyzer(input_files)
    analyzer.print_report()