import xml.etree.ElementTree as ET
import numpy as np
import os
import json
import time

class SumoAnalyzer:
    def __init__(self, files):
        self.files = files
        # 1. Tripinfo 数据容器 (宏观)
        # 新增 HV_same 类别
        self.cats = ['HV', 'HV_same', 'CAV']
        
        self.data = {cat: {'timeLoss': [], 'waitingCount': [], 'duration': [], 'routeLength': [], 'CO2': []} 
                     for cat in self.cats}
        
        # 2. FCD 数据容器 (微观)
        self.fcd_stats = {cat: {'sum_abs_accel': 0.0, 'sum_abs_jerk': 0.0, 'count': 0} 
                          for cat in self.cats}
        
        # 3. 全局统计
        self.global_stats = {
            'collisions': 0,
            'emergencyStops': 0,
            'max_queue_hv': 0.0,
            'max_queue_cav': 0.0
        }
        
        # 4. 配置
        self.cav_dedicated_lanes = {'east_in_3', 'west_in_3'}
        self.target_edges = ('east_in', 'west_in', 'north_in', 'south_in')

    def get_vehicle_category(self, vehicle_id, v_type):
        """
        核心分类逻辑：
        1. CAV: 类型含 taxi
        2. HV_same: 类型不含 taxi，但路线是东西向直行 (和 CAV 一样)
        3. HV: 其他所有普通车 (南北向、左转车等)
        """
        # 判定是否为 CAV
        is_taxi = 'taxi' in v_type
        if not v_type and 'taxi' in vehicle_id: # 兼容处理
            is_taxi = True
            
        # 判定是否为东西向直行 (Target Route)
        is_ew = ('east_in' in vehicle_id) or ('west_in' in vehicle_id)
        is_straight = 'straight' in vehicle_id
        is_target_route = is_ew and is_straight

        if is_taxi and is_target_route:
            return 'CAV'
        elif is_target_route:
            return 'HV_same'
        else:
            return 'HV'

    def parse_statistic(self):
        """解析 statistic.xml"""
        if not os.path.exists(self.files['statistic']):
            print(f"Warning: {self.files['statistic']} not found.")
            return

        try:
            tree = ET.parse(self.files['statistic'])
            root = tree.getroot()
            safety = root.find('safety')
            if safety is not None:
                self.global_stats['collisions'] = int(safety.get('collisions', 0))
                self.global_stats['emergencyStops'] = int(safety.get('emergencyStops', 0))
        except Exception as e:
            print(f"Error parsing statistic.xml: {e}")

    def parse_queue(self):
        """解析 queue.xml"""
        if not os.path.exists(self.files['queue']):
            print(f"Warning: {self.files['queue']} not found.")
            return

        try:
            for event, elem in ET.iterparse(self.files['queue'], events=('end',)):
                if elem.tag == 'lane':
                    lane_id = elem.get('id')
                    q_len = float(elem.get('queueing_length', 0))
                    
                    if lane_id.startswith(self.target_edges):
                        if lane_id in self.cav_dedicated_lanes:
                            if q_len > self.global_stats['max_queue_cav']:
                                self.global_stats['max_queue_cav'] = q_len
                        else:
                            if q_len > self.global_stats['max_queue_hv']:
                                self.global_stats['max_queue_hv'] = q_len
                    elem.clear()
        except Exception as e:
            print(f"Error parsing queue.xml: {e}")

    def parse_tripinfo(self):
        """解析 tripinfo.xml"""
        if not os.path.exists(self.files['tripinfo']):
            print(f"Warning: {self.files['tripinfo']} not found.")
            return

        try:
            for event, elem in ET.iterparse(self.files['tripinfo'], events=('end',)):
                if elem.tag == 'tripinfo':
                    v_id = elem.get('id')
                    v_type = elem.get('vType')
                    
                    # 使用新的分类逻辑
                    cat = self.get_vehicle_category(v_id, v_type)

                    try:
                        self.data[cat]['timeLoss'].append(float(elem.get('timeLoss')))
                        self.data[cat]['waitingCount'].append(int(elem.get('waitingCount')))
                        self.data[cat]['duration'].append(float(elem.get('duration')))
                        self.data[cat]['routeLength'].append(float(elem.get('routeLength')))
                        
                        emissions = elem.find('emissions')
                        if emissions is not None:
                            self.data[cat]['CO2'].append(float(emissions.get('CO2_abs', 0)))
                    except ValueError:
                        pass
                    elem.clear()
        except Exception as e:
            print(f"Error parsing tripinfo.xml: {e}")

    def parse_fcd(self):
        """解析 fcd.xml 获取加速度和舒适度指标"""
        if not os.path.exists(self.files['fcd']):
            print(f"Warning: {self.files['fcd']} not found. Skipping comfort analysis.")
            return

        print("正在解析 FCD 数据 (可能耗时较长)...")
        start_time = time.time()
        
        last_state = {} 

        try:
            for event, elem in ET.iterparse(self.files['fcd'], events=('end',)):
                if elem.tag == 'timestep':
                    time_now = float(elem.get('time'))
                    
                    for veh in elem.findall('vehicle'):
                        v_id = veh.get('id')
                        v_type = veh.get('type', '')
                        v_speed = float(veh.get('speed'))
                        
                        # 使用新的分类逻辑
                        cat = self.get_vehicle_category(v_id, v_type)
                        
                        if v_id in last_state:
                            prev = last_state[v_id]
                            dt = time_now - prev['time']
                            
                            if dt > 0:
                                # 计算加速度 a
                                curr_accel = (v_speed - prev['speed']) / dt
                                
                                # 计算 Jerk
                                if prev['accel'] is not None:
                                    curr_jerk = (curr_accel - prev['accel']) / dt
                                    
                                    # 累加统计
                                    self.fcd_stats[cat]['sum_abs_accel'] += abs(curr_accel)
                                    self.fcd_stats[cat]['sum_abs_jerk'] += abs(curr_jerk)
                                    self.fcd_stats[cat]['count'] += 1
                                
                                # 更新状态
                                last_state[v_id]['speed'] = v_speed
                                last_state[v_id]['accel'] = curr_accel
                                last_state[v_id]['time'] = time_now
                        else:
                            last_state[v_id] = {'speed': v_speed, 'accel': None, 'time': time_now}
                    
                    elem.clear() 
        except Exception as e:
            print(f"Error parsing fcd.xml: {e}")
        
        del last_state
        print(f"FCD 解析完成，耗时: {time.time() - start_time:.2f}s")

    def calculate_results(self):
        """汇总计算所有指标"""
        results = {
            'Global': self.global_stats,
            'Metrics': {}
        }
        
        # 遍历三个类别：HV, HV_same, CAV
        for cat in self.cats:
            n_trips = len(self.data[cat]['timeLoss'])
            n_fcd = self.fcd_stats[cat]['count']
            
            # 基础统计 (Tripinfo)
            if n_trips > 0:
                avg_delay = np.mean(self.data[cat]['timeLoss'])
                avg_stops = np.mean(self.data[cat]['waitingCount'])
                avg_co2 = np.mean(self.data[cat]['CO2']) if self.data[cat]['CO2'] else 0.0
                
                total_dist = sum(self.data[cat]['routeLength'])
                total_dur = sum(self.data[cat]['duration'])
                avg_speed = (total_dist / total_dur) if total_dur > 0 else 0.0
            else:
                avg_delay = avg_stops = avg_co2 = avg_speed = 0.0

            # 舒适度统计 (FCD)
            if n_fcd > 0:
                avg_abs_accel = self.fcd_stats[cat]['sum_abs_accel'] / n_fcd
                avg_abs_jerk = self.fcd_stats[cat]['sum_abs_jerk'] / n_fcd
            else:
                avg_abs_accel = avg_abs_jerk = 0.0

            results['Metrics'][cat] = {
                'sample_size': n_trips,
                'fcd_sample_points': n_fcd,
                'avg_delay_s': round(avg_delay, 3),
                'avg_stops_count': round(avg_stops, 3),
                'avg_speed_m_s': round(avg_speed, 3),
                'avg_co2_mg': round(avg_co2, 3),
                'avg_abs_accel_m_s2': round(avg_abs_accel, 4),
                'avg_abs_jerk_m_s3': round(avg_abs_jerk, 4)
            }
        
        return results

    def save_json(self, results, output_path):
        """保存为 JSON 文件"""
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=4, ensure_ascii=False)
            print(f"结果已保存至: {output_path}")
        except Exception as e:
            print(f"Error saving JSON: {e}")

    def run(self, output_json_path=None):
        """执行完整流程"""
        print(f"开始分析...")
        self.parse_statistic()
        self.parse_tripinfo()
        self.parse_queue()
        self.parse_fcd()
        
        final_res = self.calculate_results()
        
        # 打印控制台报告
        self.print_console_report(final_res)
        
        # 保存 JSON
        if output_json_path:
            self.save_json(final_res, output_json_path)
            
        return final_res

    def print_console_report(self, res):
        """打印人类可读的报告"""
        print("\n" + "="*85)
        print("SUMO 仿真综合分析报告 (含 HV_same 专项对比)")
        print("="*85)
        
        # 1. 全局安全
        g = res['Global']
        print(f"【全局安全】 碰撞: {g['collisions']} | 急刹车: {g['emergencyStops']}")
        print(f"【排队峰值】 HV: {g['max_queue_hv']:.1f}m | CAV: {g['max_queue_cav']:.1f}m")
        
        # 2. 对比指标
        print("\n【分类指标对比】")
        # 表头调整
        print(f"{'指标':<25} | {'HV (其他)':<12} | {'HV_same (同向)':<15} | {'CAV (智驾)':<12}")
        print("-" * 75)
        
        m_hv = res['Metrics']['HV']
        m_hv_s = res['Metrics']['HV_same'] # 新增
        m_cav = res['Metrics']['CAV']
        
        print(f"{'平均延误 (s)':<25} | {m_hv['avg_delay_s']:<12} | {m_hv_s['avg_delay_s']:<15} | {m_cav['avg_delay_s']:<12}")
        print(f"{'平均停车 (次)':<25} | {m_hv['avg_stops_count']:<12} | {m_hv_s['avg_stops_count']:<15} | {m_cav['avg_stops_count']:<12}")
        print(f"{'平均速度 (m/s)':<25} | {m_hv['avg_speed_m_s']:<12} | {m_hv_s['avg_speed_m_s']:<15} | {m_cav['avg_speed_m_s']:<12}")
        print(f"{'车均排放 (mg CO2)':<25} | {m_hv['avg_co2_mg']:<12} | {m_hv_s['avg_co2_mg']:<15} | {m_cav['avg_co2_mg']:<12}")
        print(f"{'舒适度: |加速度|':<25} | {m_hv['avg_abs_accel_m_s2']:<12} | {m_hv_s['avg_abs_accel_m_s2']:<15} | {m_cav['avg_abs_accel_m_s2']:<12}")
        print(f"{'舒适度: |加加速度|':<25} | {m_hv['avg_abs_jerk_m_s3']:<12} | {m_hv_s['avg_abs_jerk_m_s3']:<15} | {m_cav['avg_abs_jerk_m_s3']:<12}")
        print("="*85 + "\n")


# --- 使用示例 ---
if __name__ == "__main__":
    # 配置输入文件夹路径
    FOLDER_NAME = os.listdir("output/plus")[0]
    for FOLDER_NAME in os.listdir("output/plus"):
        FOLDER_NAME = f'output/plus/{FOLDER_NAME}'
        files_config = {
            'statistic': f'{FOLDER_NAME}/statistic.xml',
            'tripinfo':  f'{FOLDER_NAME}/tripinfo.xml',
            'queue':     f'{FOLDER_NAME}/queue.xml',
            'fcd':       f'{FOLDER_NAME}/fcd.xml'
        }
        
        # 实例化并运行
        analyzer = SumoAnalyzer(files_config)
        
        # 运行分析并导出 JSON
        analyzer.run(output_json_path=f'{FOLDER_NAME}/analysis_result.json')

all_data = {}
for FOLDER_NAME in os.listdir("output/plus"):
    analysis_result = f'output/plus/{FOLDER_NAME}/analysis_result.json'
    with open(analysis_result, 'r', encoding='utf-8') as f:
        data = json.load(f)
    flatten_data = data['Metrics']
    all_data[FOLDER_NAME] = flatten_data
import pandas as pd
all_data = pd.DataFrame(all_data)
os.makedirs('./results/plus', exist_ok=True)
for indicator in flatten_data['HV'].keys():
    indicator_result = all_data.map(lambda x: x[indicator])
    indicator_result.to_csv(f'./results/plus/{indicator}.csv', index=False)
