# CAV 协同信号优先与编队控制仿真系统技术说明书

## 1. 系统概述
本系统基于 SUMO (Simulation of Urban MObility) 交通仿真平台构建，旨在模拟与评估**网联自动驾驶车辆 (Connected and Automated Vehicles, CAV)** 在城市信号控制交叉口场景下的协同控制效能。

系统集成了两项核心协同技术：
1.  **主动信号优先 (Active Signal Priority)**：基于 V2I (Vehicle-to-Infrastructure) 通信，实时优化信号配时方案（绿灯延长/相位截断），提升 CAV 车队通行效率。
2.  **协同轨迹与编队控制 (Cooperative Trajectory & Platooning)**：基于 V2V (Vehicle-to-Vehicle) 通信，实现车辆在接近路口时的速度引导与紧密编队行驶，提升道路时空资源利用率。

本系统支持通过命令行参数灵活配置实验场景，适用于不同控制策略组合及交通流量条件下的对比测试。

---

## 2. 运行控制与参数配置
系统通过接收外部参数控制仿真运行模式。

### 2.1 启动参数说明
运行脚本时可指定以下参数，以构建不同的实验组/对照组：

| 参数标识 | 参数名称 | 功能定义 | 默认值 |
| :--- | :--- | :--- | :--- |
| `--signal` | **信号优先开关** | 启用后，信号控制机将响应 CAV 车队的通行请求，执行动态相位调整。 | False (关闭) |
| `--traj` | **轨迹控制开关** | 启用后，CAV 将接管 SUMO 默认驾驶模型，执行平滑减速与 CACC 编队逻辑。 | False (关闭) |
| `--scale` | **流量缩放系数** | 调整路网交通需求的生成强度。系数 $1.0$ 代表基准流量，$1.2$ 代表流量增加 20%。 | 0.1 |

### 2.2 实验方案设计
本研究采用正交实验设计方法，针对 **信号优先控制**、**轨迹编队控制** 以及 **交通流量强度** 三个维度进行组合，共设计 **8 组** 对比实验场景，以全面评估不同控制策略在不同交通压力下的效能。

具体实验分组如下表所示：

| 实验组编号 | 流量场景 (Scale) | 信号优先策略 (Signal) | 轨迹编队策略 (Traj) | 实验目的与预期 |
| :---: | :---: | :---: | :---: | :--- |
| **G1** | **1.0 (基准流)** | **关闭** | **关闭** | **基准对照组**：模拟现状常规交通流运行情况，作为评估优化的基础标尺。 |
| **G2** | 1.0 (基准流) | **开启** | 关闭 | 评估在正常流量下，仅依靠信号机主动调节对通行效率的提升效果。 |
| **G3** | 1.0 (基准流) | 关闭 | **开启** | 评估在正常流量下，仅依靠车辆自身编队与速度引导对通行效率的提升效果。 |
| **G4** | 1.0 (基准流) | **开启** | **开启** | **综合优化组**：评估车路协同（信号+车辆）全功能开启下的系统最优性能。 |
| **G5** | **1.2 (高负荷)** | **关闭** | **关闭** | **高压对照组**：模拟高峰期拥堵状态下的常规运行情况，用于观察系统崩溃点。 |
| **G6** | 1.2 (高负荷) | **开启** | 关闭 | 测试信号优先策略在交通高压力状态下的抗压能力与调节极限。 |
| **G7** | 1.2 (高负荷) | 关闭 | **开启** | 测试车辆编队技术在高密度交通流中提升道路时空资源利用率的能力。 |
| **G8** | 1.2 (高负荷) | **开启** | **开启** | **高压综合组**：验证全功能协同控制在极端交通压力下缓解拥堵、维持系统稳定的能力。 |

---

## 3. 控制策略逻辑详解

### 3.1 主动信号优先策略 (Signal Priority Strategy)
系统根据 CAV 车队的实时状态与路口排队情况，动态调整信号相位。

[![](https://mermaid.ink/img/pako:eNqNlXtv0lAYxr8KOWYJSwppy70mmmVbookmJuMvh3_U9nQ0g5aUEpmEBBLd3FC2RZ3LmG46ZdNkoMbd3O3LcE7hW3hKV2DQ4CChh3Pe5znP--stBwRVhIADMxqfiruiEzEtprjIZ2TE5fF4XGi_ijfrrZ0y3j7D20fobBnVNhoni-aiXSok-HR6Akqup3wauiQ5keBuSZJEpXVNnYXcLZqmr8aeZ7KoxzkmlaUENaFq7bXbAz5pndd0qIhXXl39cC-y56CXCAU5LavKTXNpWY6mtDnyMywhL-g9nrT5HWLrDQw23McZHxSNvRKqXBinb_GnF714p0wabjc6K6Dd0ugox3EdPh7PHdd9Rdanm-UjtLxmVI4b528ax-XmebW1vmUsHeJC8QkRmCfGtrOPpq5tMB6HwuyjOCnJGZUa3l7AaydoZRWv143TS6NYv5snDjbGfhcS36pCr-bxu7o93fV0mc2t17s7RXk5MY13CvighH5ekKQksnFeI6kno2P9YTuKtt4cPFBnZCFHHNFKtbVZaFaL6PSw9f7SMWVHMJBiipcgk2tc7JJOUbmEliqotohe7jnadBW9PmOCPpnVp_HibvPza85KYbEwu7CuECdcf7_8BxfprBv0HuRFG9fXPx1cjqDM2rbSHFigLA0uf2terjaP6mh5x7HDjsARFJtD87-NH0XrwrgJKLYPVFTLKDYpCwD-8B2v7Q8nRW6Fj1v410KzuOF4Rm1Qk4rodlvV1-4P5_PXo3Js32H9el8OBda14DBrNm5PA4o8ZWURcBKfSEMKJKGW5M3_IGfWx4Aeh0kYAxwZilDiMwk9BtorSp5oU7zyWFWTgNO1DFFramYm3vHKpERehxMyT57jyc4skQAuB7KAY5iwNxRgff5IOMT4mXDQR4E5wLFswBuO-FlfiI2w4SAdDOQp8Ly9C-MN-iN-P0P7faEQGw4FyZaEKdTG1YyiEynNshSAoqyr2kPrHdJ-leT_ASYQblM?type=png)](https://mermaid-live.nodejs.cn/edit#pako:eNqNlXtv0lAYxr8KOWYJSwppy70mmmVbookmJuMvh3_U9nQ0g5aUEpmEBBLd3FC2RZ3LmG46ZdNkoMbd3O3LcE7hW3hKV2DQ4CChh3Pe5znP--stBwRVhIADMxqfiruiEzEtprjIZ2TE5fF4XGi_ijfrrZ0y3j7D20fobBnVNhoni-aiXSok-HR6Akqup3wauiQ5keBuSZJEpXVNnYXcLZqmr8aeZ7KoxzkmlaUENaFq7bXbAz5pndd0qIhXXl39cC-y56CXCAU5LavKTXNpWY6mtDnyMywhL-g9nrT5HWLrDQw23McZHxSNvRKqXBinb_GnF714p0wabjc6K6Dd0ugox3EdPh7PHdd9Rdanm-UjtLxmVI4b528ax-XmebW1vmUsHeJC8QkRmCfGtrOPpq5tMB6HwuyjOCnJGZUa3l7AaydoZRWv143TS6NYv5snDjbGfhcS36pCr-bxu7o93fV0mc2t17s7RXk5MY13CvighH5ekKQksnFeI6kno2P9YTuKtt4cPFBnZCFHHNFKtbVZaFaL6PSw9f7SMWVHMJBiipcgk2tc7JJOUbmEliqotohe7jnadBW9PmOCPpnVp_HibvPza85KYbEwu7CuECdcf7_8BxfprBv0HuRFG9fXPx1cjqDM2rbSHFigLA0uf2terjaP6mh5x7HDjsARFJtD87-NH0XrwrgJKLYPVFTLKDYpCwD-8B2v7Q8nRW6Fj1v410KzuOF4Rm1Qk4rodlvV1-4P5_PXo3Js32H9el8OBda14DBrNm5PA4o8ZWURcBKfSEMKJKGW5M3_IGfWx4Aeh0kYAxwZilDiMwk9BtorSp5oU7zyWFWTgNO1DFFramYm3vHKpERehxMyT57jyc4skQAuB7KAY5iwNxRgff5IOMT4mXDQR4E5wLFswBuO-FlfiI2w4SAdDOQp8Ly9C-MN-iN-P0P7faEQGw4FyZaEKdTG1YyiEynNshSAoqyr2kPrHdJ-leT_ASYQblM)

#### 3.1.1 绿灯延长 (Green Extension)
旨在防止正在通过路口的车队被红灯截断。
*   **触发逻辑**：
    1.  目标相位（东西直行）当前为**绿灯**。
    2.  检测到 CAV 车队**尾车 (Tail Vehicle)** 位于进口道，且其预计到达停止线时间 (ETA) 大于当前剩余绿灯时间。
    3.  **冲突约束检测**：侧向冲突相位（南北向及左转相位）的**车道占有率**低于阈值 `PRESSURE_THRESHOLD`，确保不造成严重的支路拥堵。
*   **控制动作**：
    延长当前相位绿灯时长，延长时间量 $T_{ext} = ETA_{tail} - T_{remaining}$，但受最大延长时间限制。

#### 3.1.2 相位截断/红灯早断 (Phase Truncation / Early Green)
旨在缩短 CAV 车队在红灯前的无效等待时间。
*   **触发逻辑**：
    1.  目标相位当前为**红灯**（即冲突相位正在放行）。
    2.  CAV **头车 (Head Vehicle)** 距离路口小于检测距离 `DETECTION_DIST`。
    3.  **安全约束检测**：当前正在放行的相位（如南北直行）交通需求极低，其检测区域内的车辆数低于安全阈值 `EARLY_GREEN_PRESSURE`。
    4.  当前相位已满足最小绿灯运行时间 `MIN_NS_LEFT_TIME`。
*   **控制动作**：
    立即终止当前放行相位，切换至黄灯过渡，随后开启目标相位绿灯。

### 3.2 协同轨迹控制策略 (Cooperative Trajectory Control)
系统对 CAV 车辆施加分层控制，根据车辆在车队中的位置及其与路口的状态关系，执行差异化速度引导。

[![](https://mermaid.ink/img/pako:eNqNVWtP2lAY_ivkGBNNCmu52y1bHC77smWJ7tNkHzp6kEagpC2ZjpBAsiGKDt0WY5w31CBboiS7iArqn_H08i92TrUFJrhBQg7v5Xmf5zmnpxkQEXkIWDAlcamY4-VYWAonHfgzOOhwOp0OdFhVN-rG3kd1p6XuNFCrjI7Wr07nSdIqjcQ5WR6DUccbToaOqBCPswPRaJSSFUmchuwATdM3a-dbgVdiLJOaoSJiXJTM3P1bOLLCSQpM8jdY7f67sfDM21g8jAiyICb_l5c0w9KUNIt_7mLIRZQOTJp874B1-W4L_stn9Xdeq5XQ1wut-Vndet9p7wRxY2gItXLooDQ8zLKs7Y_T-dARisHI9LgYhxlU3FdXD_Xzqn5R0A8-6fM_srjYMsCC6xhs7Bb04nfcgIoF9UvdytiIGL9d0x42IUxl0PySunp6dVlB5Ya2cKzm8o96DbPqCZLWvNTydRNmNKKEpLQgw0m1VsFnikUfakZuGzUqeNZrjHPtb0-Us10LxQyPCbKS0RubWrWJ8hvq4a52dvmA8dGJ_nxIC4FS12w2T-MCb5NRS9sYCp3-VJsraK6MifWhZAGh5Wq3rB5e641tY718t9d2TVveM8jxxGwc_JfNpNRkY1K-hyVYSJjXY4mbbru9VEbLi6h4jBZqfaRZYOrhHjo50SuLxrdjW-NoKGRBkbX26wDVC1pr1Vjr4VSHB-Rsb24buaZ-sWKFbc_aml-klQzeG-wq2dRWTm_UUXmvp3Br67qaO5Km7H5Jwr1nrssJHO88LONQhsqkMbeknR9dnZwZzTX9aJ-YsVUi2s0rkNQ9SfJDQ9eCu57ZXtjW-cE9gMI3scADNsrFZUiBBJQSHPkPMqQvDJQYTMAwYPGSh1EuHVfCwMwks7g3xSVfiWICsIqUxt2SmJ6K2VjpFM8pcEzg8F2fsKO4BbAZMANYxu920V6P1xN0MyNuxhdwU2AWsE5PIODyBf0e30jA7_GOBL1ZCrwzpzAuDxNk6ICX8TBuP1nhmVgklEJiOqkA1k0HfRSAvKCI0vPrF435vsn-Acz2hdw?type=png)](https://mermaid-live.nodejs.cn/edit#pako:eNqNVWtP2lAY_ivkGBNNCmu52y1bHC77smWJ7tNkHzp6kEagpC2ZjpBAsiGKDt0WY5w31CBboiS7iArqn_H08i92TrUFJrhBQg7v5Xmf5zmnpxkQEXkIWDAlcamY4-VYWAonHfgzOOhwOp0OdFhVN-rG3kd1p6XuNFCrjI7Wr07nSdIqjcQ5WR6DUccbToaOqBCPswPRaJSSFUmchuwATdM3a-dbgVdiLJOaoSJiXJTM3P1bOLLCSQpM8jdY7f67sfDM21g8jAiyICb_l5c0w9KUNIt_7mLIRZQOTJp874B1-W4L_stn9Xdeq5XQ1wut-Vndet9p7wRxY2gItXLooDQ8zLKs7Y_T-dARisHI9LgYhxlU3FdXD_Xzqn5R0A8-6fM_srjYMsCC6xhs7Bb04nfcgIoF9UvdytiIGL9d0x42IUxl0PySunp6dVlB5Ya2cKzm8o96DbPqCZLWvNTydRNmNKKEpLQgw0m1VsFnikUfakZuGzUqeNZrjHPtb0-Us10LxQyPCbKS0RubWrWJ8hvq4a52dvmA8dGJ_nxIC4FS12w2T-MCb5NRS9sYCp3-VJsraK6MifWhZAGh5Wq3rB5e641tY718t9d2TVveM8jxxGwc_JfNpNRkY1K-hyVYSJjXY4mbbru9VEbLi6h4jBZqfaRZYOrhHjo50SuLxrdjW-NoKGRBkbX26wDVC1pr1Vjr4VSHB-Rsb24buaZ-sWKFbc_aml-klQzeG-wq2dRWTm_UUXmvp3Br67qaO5Km7H5Jwr1nrssJHO88LONQhsqkMbeknR9dnZwZzTX9aJ-YsVUi2s0rkNQ9SfJDQ9eCu57ZXtjW-cE9gMI3scADNsrFZUiBBJQSHPkPMqQvDJQYTMAwYPGSh1EuHVfCwMwks7g3xSVfiWICsIqUxt2SmJ6K2VjpFM8pcEzg8F2fsKO4BbAZMANYxu920V6P1xN0MyNuxhdwU2AWsE5PIODyBf0e30jA7_GOBL1ZCrwzpzAuDxNk6ICX8TBuP1nhmVgklEJiOqkA1k0HfRSAvKCI0vPrF435vsn-Acz2hdw)

#### 3.2.1 领航车/自由流车辆控制 (Leader Control)
针对车队头车或独立行驶车辆：
*   **绿灯通行模式**：当信号为绿灯时，车辆按道路限速 `MAX_SPEED` 巡航，追求最大通行效率。
*   **拟停平滑减速模式 (Glide-to-Stop)**：
    *   **触发条件**：前方信号为红灯，且车辆距离停止线小于制动视距 `BRAKING_HORIZON`。
    *   **计算逻辑**：摒弃急停急起，计算恒定舒适减速度，使车辆到达停止线时速度恰好衰减为 0。
    *   **速度公式**：目标速度 $v_{target} = \sqrt{2 \cdot a_{comf} \cdot d_{stop}}$
        *   $a_{comf}$：预设舒适减速度 (Comfort Deceleration)。
        *   $d_{stop}$：当前位置距离停止线（减去安全余量）的距离。

#### 3.2.2 跟随车编队控制 (Follower / Platooning Control)
针对车队中的后随车辆：
*   **CACC 紧密编队模式**：
    *   **触发条件**：前车处于正常行驶状态。
    *   **控制逻辑**：激活协同自适应巡航控制 (CACC)。通过 V2V 通信获取前车状态，大幅压缩跟驰间距。
    *   **参数特征**：车间距维持在 `PLATOON_MINGAP` (如 1.0m)，车头时距维持在 `PLATOON_TAU` (如 0.5s)，显著提升道路容量。
*   **协同制动模式**：
    *   **触发条件**：前车进入“拟停平滑减速模式”或正在制动。
    *   **控制逻辑**：后车同步执行平滑减速逻辑，保持与前车一致的制动节奏，避免追尾并抑制交通激波的产生。

---

## 4. 关键技术参数定义
以下参数位于代码配置区，用户可根据道路几何条件和交通特性进行校准。

### 4.1 信号控制参数
| 参数变量名 | 推荐值 | 物理含义及设置原则 |
| :--- | :--- | :--- |
| `MAX_EXTENSION` | `15.0` (s) | **最大绿灯延长时间**。限制单次绿灯延长的上限，防止单一方向长时间占用路权导致周期紊乱。 |
| `PRESSURE_THRESHOLD` | `15` (%) | **侧向压力阈值（占有率）**。表示冲突相位进口道的空间占有率。若冲突车道占有率超过此值（说明排队较长），系统将拒绝执行绿灯延长，优先保障路网公平性。 |
| `EARLY_GREEN_PRESSURE` | `1` (辆) | **红灯早断安全阈值**。仅当当前放行相位的检测区域内车辆数少于此值时，才允许截断相位。必须设置为极低值以确保清空冲突车流，保障安全。 |
| `DETECTION_DIST` | `120.0` (m) | **CAV 感知距离**。定义 CAV 向信号机发送请求的通信范围。数值通常取决于 DSRC/C-V2X 通信模组的有效覆盖范围。 |

### 4.2 车辆运动学参数
| 参数变量名 | 推荐值 | 物理含义及设置原则 |
| :--- | :--- | :--- |
| `MAX_SPEED` | `16.67` (m/s) | **道路限速**。对应约 60km/h。应与仿真路网的道路等级保持一致。 |
| `PLATOON_MINGAP` | `1.0` (m) | **编队静止间距**。CACC 模式下车辆停止时的最小物理间距。数值越小，路口空间利用率越高，但对控制精度要求越高。 |
| `PLATOON_TAU` | `0.5` (s) | **编队车头时距**。表示后车通过前车位置所需的时间差。普通驾驶员通常为 1.5s~2.0s，自动驾驶可压缩至 0.6s 以下，显著提升通行能力。 |
| `COMFORT_DECEL` | `1.0` (m/s²) | **舒适减速度**。用于计算平滑减速轨迹。数值越小，减速过程越平缓，乘客舒适度越高，能耗越低。 |

---

## 5. 数据输出与分析
仿真结束后，系统将在 `output/plus/` 目录下生成结构化的数据文件，文件命名格式为 `{Signal}_{Traj}_{Scale}`（例如 `True_True_1.0`），包含以下关键指标文件：

1.  **`tripinfo.xml` (行程信息表)**：
    *   记录每辆车的出发时间、到达时间、总耗时 (Duration)、停车等待时间 (Waiting Time) 及能耗数据。
    *   *用途：用于计算平均延误、平均车速等微观评价指标。*
2.  **`statistic.xml` (全局统计表)**：
    *   包含仿真期间的总车辆数、路网平均拥堵指数、总行驶里程等。
    *   *用途：用于评估路网层面的宏观运行状态。*
3.  **`queue.xml` (排队数据表)**：
    *   记录各进口道在每个时间步的排队长度。
    *   *用途：分析交叉口排队消散规律及溢出风险。*