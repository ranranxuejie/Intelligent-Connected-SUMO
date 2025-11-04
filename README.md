# 智能交通信号控制系统（主动交通管控）

## 项目简介

本项目是一个基于SUMO（Simulation of Urban MObility）的智能交通信号控制系统仿真平台，实现了公交车优先通行、交通流量分析、排队长度统计等功能，旨在通过智能化的交通信号控制提升城市交通效率。

## 目录结构

├── .gitignore               # Git忽略文件配置
</span>├── analyze_results.py       # 仿真结果分析脚本
├── bus.py                   # 公交车优先控制主程序
├── create_intersection.py   # 交叉路口创建工具
├── crossroad_simulation.sumocfg  # SUMO仿真配置文件
├── generate/                # 仿真文件生成工具
│   ├── add.py               # 附加配置生成
│   ├── demand.py            # 交通需求生成
│   └── network.py           # 道路网络生成
├── output/                  # 仿真结果输出目录
│   ├── [timestamp]/         # 按时间戳命名的结果文件夹
│   ├── bench_mark.md        # 基准测试结果
│   ├── fcd.xml              # 浮动车数据
│   ├── queue.xml            # 排队数据
│   └── tripinfo.xml         # 行程信息数据
├── plot.py                  # 数据可视化脚本
├── quick_start.md           # 快速开始指南（待完善）
├── sumo.log                 # SUMO日志文件
└── test/                    # 测试配置文件
├── bus_stops.add.xml    # 公交站点配置
├── connections.con.xml  # 道路连接配置
├── crossroad.net.xml    # 道路网络配置
├── edges.edg.xml        # 道路边缘配置
├── nodes.nod.xml        # 道路节点配置
├── traffic.rou.xml      # 交通流配置
└── traffic_light.add.xml  # 交通灯配置
</code></pre></div></pre>

## 核心功能模块

### 1. 公交车优先控制系统（bus.py）

实现了基于实时交通状态的公交车优先通行策略，主要功能包括：

* **绿灯延长**：当公交车接近信号灯且当前为绿灯但剩余时间不足时，自动延长绿灯时间
* **红灯早断**：当公交车接近信号灯且当前为红灯时，在确保安全的前提下提前切换为绿灯
* **自适应控制**：根据公交车距离、当前相位状态和排队情况动态调整信号控制策略

### 2. 仿真结果分析系统（analyze\_results.py）

提供了全面的仿真结果分析功能，包括：

* **行程数据分析**：统计私家车和公交车的平均延误、等待时间、CO2排放等指标
* **排队长度分析**：按进口道方向和车道类型（公交专用道、直行车道、左转车道）统计最大排队长度和平均排队长度
* **XML文件修复**：处理SUMO输出的可能不完整的XML文件，确保数据完整性

### 3. 仿真文件生成系统（generate/）

提供了灵活的仿真场景配置工具：

* 道路网络生成
* 交通需求建模
* 附加设施（如公交站点、交通灯）配置

## 安装与使用

### 环境要求

* Python 3.6+
* SUMO 1.0+

### 安装步骤

1. 安装Python环境
2. 安装SUMO并配置环境变量
3. 克隆本项目代码

### 使用流程

#### 基础仿真

1. 准备仿真配置文件（位于test/目录下）
2. 运行主仿真程序：

```
python bus.py
```

3. 查看输出结果（位于output/[timestamp]/目录下）

#### 结果分析

仿真完成后，系统会自动调用分析模块处理结果。也可以单独运行分析脚本：

```
python analyze_results.py
```

## 配置说明

### 核心参数配置

在bus.py中可以调整以下关键参数：

* `MAX_EXTENSION`：最大绿灯延长时间（秒）
* `EXTEND_THRESHOLD`：绿灯延长触发阈值（秒）
* `EARLY_GREEN_DIST`：红灯早断触发距离（米）
* `QUEUE_THRESHOLD`：排队长度阈值（用于判断当前绿灯车道是否可以中断）

### 仿真输出配置

仿真结果会保存在按时间戳命名的目录下，主要输出文件包括：

* `tripinfo.xml`：车辆行程详细信息
* `queue.xml`：各车道排队长度数据
* `params.txt`：当前仿真使用的参数配置
* `queue_stats.json`：排队长度统计结果
* `trip_stats.json`：行程数据统计结果

## 结果解读

### 行程统计指标

* **Count**：车辆数量
* **Avg Delay(s)**：平均延误时间（秒）
* **Avg Wait(s)**：平均等待时间（秒）
* **Total CO2(g)**：总CO2排放量（克）
* **Total Fuel(g)**：总燃油消耗量（克）

### 排队长度统计指标

按4个方向（东、南、西、北）× 3种车道类型（公交专用道、直行车道、左转车道）分类统计：

* **最大排队长度(m)**：仿真期间该进口道的最大排队长度
* **平均排队长度(m)**：仿真期间该进口道的平均排队长度
* **记录数**：有效数据记录数量

## 开发指南

### 扩展公交车优先策略

可以在`handle_bus_priority()`函数中修改或添加新的优先策略逻辑。

### 添加新的分析指标

可以在`analyze_results.py`中扩展现有分析函数或添加新的分析函数。

### 创建新的仿真场景

可以使用`generate/`目录下的工具创建自定义仿真场景，或直接修改`test/`目录下的配置文件。

## 注意事项

1. 确保SUMO已正确安装并配置环境变量
2. 首次运行前检查test/目录下的配置文件是否完整
3. 大量仿真数据可能会占用较多磁盘空间，注意定期清理output/目录

## License

```
MIT License

Copyright (c) [2025] 李修然 @ 同济大学

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Acknowledgements

* SUMO仿真平台
* 相关交通控制算法研究
