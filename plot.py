import matplotlib.pyplot as plt
import pandas as pd
# 设置中文显示
plt.rcParams['font.sans-serif'] = ['SimHei']
plt.rcParams['axes.unicode_minus'] = False

# 数据
data = {
    '方式': ['高铁(宁沪)', '高铁(沪杭)', '高铁(杭甬)', '长途汽车', '航空', '地铁', '公交(骨干)', '公交(常规)', '轮渡'],
    '效率': [2.08, 4.17, 1.80, 1.0, 0.5, 24.0, 3.0, 1.7, 0.3],
    '成本': [37.8, 15.5, 24.8, 25.0, 80.0, 7.5, 4.0, 3.3, 8.0],
    '类型': ['城际']*5 + ['城区']*4
}

df = pd.DataFrame(data)

# 绘图
plt.figure(figsize=(6, 6), dpi=300)
colors = {'城际': 'red', '城区': 'blue'}
markers = {'城际': 'o', '城区': 's'}

for typ in df['类型'].unique():
    subset = df[df['类型'] == typ]
    plt.scatter(subset['效率'], subset['成本'],
                label=typ,
                color=colors[typ],
                marker=markers[typ],
                s=100)

# 添加标签
for i in range(len(df)):
    plt.text(df['效率'][i], df['成本'][i]+1.5, df['方式'][i], fontsize=9)

plt.xlabel('运输效率（班次/小时）')
plt.ylabel('单位时间成本（元/小时）')
plt.title('长三角客运交通：效率 vs 成本')
plt.legend()
plt.grid(True, linestyle='--', alpha=0.6)
plt.xscale('log')  # 因地铁效率远高于城际，建议对数坐标
plt.tight_layout()
plt.show()
#%%
import matplotlib.pyplot as plt
import pandas as pd

# 数据准备
data = {
    '交通方式': ['高铁（城际走廊）', '长途汽车（城际）', '航空（城际）', '上海地铁', '上海公交', '上海轮渡'],
    '覆盖率评分': [7, 5, 3, 9, 8, 3],
    '可达性评分': [8, 4, 5, 9, 7, 4],
    '类型': ['城际'] * 3 + ['城区'] * 3  # 区分城际和城区交通方式
}

df = pd.DataFrame(data)

# 绘图设置
plt.figure(figsize=(6, 6), dpi=300)
colors = {'城际': 'red', '城区': 'blue'}
markers = {'城际': 'o', '城区': 's'}

for typ in df['类型'].unique():
    subset = df[df['类型'] == typ]
    plt.scatter(subset['覆盖率评分'], subset['可达性评分'],
                label=typ,
                color=colors[typ],
                marker=markers[typ],
                s=100)  # 点的大小

# 添加文本标签
for i in range(len(df)):
    plt.text(df['覆盖率评分'][i] + 0.1, df['可达性评分'][i], df['交通方式'][i], fontsize=9)

plt.xlabel('覆盖率评分 (0-10)')
plt.ylabel('可达性评分 (0-10)')
plt.title('长三角客运交通：覆盖率 vs. 可达性')
plt.legend()
plt.grid(True, linestyle='--', alpha=0.6)
plt.xlim(0, 10)  # 设置x轴范围
plt.ylim(0, 10)  # 设置y轴范围
plt.tight_layout()
plt.show()
