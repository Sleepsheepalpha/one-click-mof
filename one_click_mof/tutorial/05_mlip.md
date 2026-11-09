# 第 5 章：机器学习势（MLIP）预筛

## 本章目的

学完这一章，你应该能：

- 解释 MLIP 为什么快、什么时候不能信；
- 正确设置 MACE/UFF 的模型、head、device、dtype；
- 用 MLIP 找位点、排序，再用 DFT 标定；
- 判断“模型外推”导致的离谱结果。

## 计算背景速查

| 词 | 计算含义 | 为什么重要 |
|---|---|---|
| MLIP | 机器学习势：用训练数据学“原子位置→能量/力” | 比 DFT 快几个数量级 |
| 训练集 | 模型见过的结构/分子 | 没见过的分子可能乱给能量 |
| 外推 | 模型遇到训练集之外的情况 | 结果可能完全不可信 |
| head | 一个模型里的“输出头”，对应不同训练目标 | 选错 head，能量不对 |
| dtype | 浮点精度 | float64 稳，float32 快 |
| device | CPU/GPU | GPU 快；显存不够会 OOM |
| UFF | 经典力场，不是 MLIP | 快但精度低；可做几何预筛 |
| 标定 | 用 DFT 对照 MLIP | 至少 5–10 个位点 |

## 做法

### 步骤 1：选模型

| 模型 | 适合 | 注意 |
|---|---|---|
| uMOF-MH | MOF + 气体（训练含 CO2） | head='r2scan+d4'；CH4/C2H6/C6H6 需验证 |
| MACE-MOF0 | MOF 声子/结构 | v2 需 head='pbe_d3'；气体是否在训练集未知 |
| MACE-MP-0 | 通用分子/材料 | 需另装；精度/速度折中 |
| UFF | 快速几何预筛 | 能量不可当吸附能 |

### 步骤 2：小体系试跑

- 先用 1 个位点、1 个分子跑通；
- 看分子是否断键、是否飞出盒子；
- 看能量是否在合理范围（物理吸附 -0.1 ~ -0.5 eV）。

### 步骤 3：批量筛选

- 固定骨架，只优化分子；
- 多 seed；
- 保留 intact；
- 输出 CSV。

### 步骤 4：DFT 标定

- 取 top 3–5 位点做 DFT 单点；
- 比较 MLIP vs DFT 的偏差和排序；
- 如果偏差 >0.1–0.2 eV 或排序翻转，MLIP 只能当“找位点”，不能当“排序”。

## 参数表

| 参数 | 作用 | 默认 | 怎么调 |
|---|---|---|---|
| model | 模型文件 | uMOF-MH | 换分子先验证 |
| head | 输出头 | r2scan+d4 | 按模型 README 选 |
| dtype | 精度 | float64 | 大体系/显存紧可 float32 |
| device | 计算设备 | cuda | 无 GPU 改 cpu |
| n_sites | 起点数 | 24 | 先 24；不够加 |
| fmax | 优化收敛 | 0.05 eV/Å | 预筛可松；DFT 更紧 |
| maxstep | 步长 | 0.1 Å | 太大易崩 |
| seed | 随机种子 | 固定 | 换 seed 检查稳定性 |

## MOF-5 基准算例

### 现状

- `one_click_mof/tools/screen_adsorbate_mace.py` 已支持任意分子：`--adsorbate CH4|C2H6|C6H6|CO2`，或 `--adsorbate-file` 给自定义 XYZ。
- 每个起点随机取向、固定骨架、只优化分子；分子内部键长用 `FixBondLengths` 保持，跑完按 `intact` 过滤。
- 网页里的“MACE 位点筛选”工具与它是同一套参数。

### 实际命令（已跑通）

    .venv_mace/bin/python one_click_mof/tools/screen_adsorbate_mace.py \
      --cif one_click_mof/tutorial/benchmark/mof5/inputs/IRMOF-1_primitive.cif \
      --adsorbate CH4 \
      --n-sites 24 --seed 20261107 --probe 2.2 \
      --out /Data/mof5_benchmark/screen/CH4 --device cuda

### 结果表（MACE 已跑；DFT 用同 cell/同位置参考）

重筛（probe 2.8 Å、min_mol_framework ≥ 3.0 Å、32 个起点）之后的对照：

| 分子 | 模型 | 起点 | intact | MACE 最低 (eV, site) | DFT 最低 (eV, site) | 比值 |
|---|---|---:|---:|---|---|---:|
| CH4 | uMOF-MH | 32 | 26 | -0.115 (14) | -0.668 (14) | 5.8× |
| C2H6 | uMOF-MH | 32 | 15 | -0.121 (17) | -1.061 (17) | 8.8× |
| C6H6 | uMOF-MH | 27 | 12 | -0.252 (17) | -2.394 (17) | 9.5× |

读这张表要抓三件事：

1. **排序一致**：这次 MACE 和 DFT 都选 site 14 / 17 / 17，说明加了最小距离约束后，MACE 找位点的能力是可靠的。
2. **绝对值差 6–10 倍**：MACE 训练集主要是 MOF + CO2，对 CH4/C2H6/C6H6 是外推，势阱明显比 PBE-D3 浅。苯差 9.5 倍，模型对芳香分子最不可靠。
3. **DFT 自己也偏强**：第 6 章的合理性检查指出，这组 DFT 值仍比文献/实验量级强 3–5 倍。所以“DFT 比 MACE 强 6–10 倍”不能理解成“MACE 低估了”，两边都有问题。

> 上一轮（probe 2.2、无最小距离约束）是 CH4 -0.188、C2H6 -0.259、C6H6 -0.270；重筛后变成 -0.115 / -0.121 / -0.252。MACE 排序变了，DFT 只弱了 0.05–0.11 eV。

> 最初 DFT 用 20 Å 盒子做参考，得到 -2.6/-5.4/-16.8 eV 的荒谬值；原因是 QE 分子总能量对 cell/形状敏感。上表 DFT 列已改用同晶胞、同分子坐标的参考能。详见 benchmark/mof5/expected/RESULT_CHECK_2026-11-07.md。

## 怎么判断成功

- 分子没有断键/飞出盒子；
- 位点在孔里，排序不是随机的；
- 至少 5 个位点做过 DFT 对照；
- 偏差和排序写进报告，不隐瞒；
- 知道模型是否“见过”这个分子。

## 常见错误

| 现象 | 原因 | 处理 |
|---|---|---|
| E_ads 比 -1 eV 还负很多 | 分子嵌进骨架/模型外推 | 检查几何；换模型；DFT 验证 |
| 所有位点能量一样 | 分子没动/优化失败 | 看 fmax、轨迹、约束 |
| CUDA OOM | 显存不够 | device=cpu、float32、减原子 |
| head 报错 | head 名不对 | 看模型 README |
| MLIP 排序和 DFT 翻转 | 模型偏差 | 只把 MLIP 当找位点 |

## 练习

1. 用 uMOF-MH 对 CH4 跑 1 个位点，记录能量和力。
2. 把 device 改成 cpu，比较时间。
3. 解释为什么“MLIP 最快”不等于“MLIP 最准”。

## 练习答案

1. 记录 E_ads 和最终 fmax。若 fmax >0.05 eV/Å，说明局域优化没收敛，这个 MACE 数不能当最终值；只能作为“有位点”的证据。
2. CPU 通常比 GPU 慢 5–10 倍；能量/排序应接近，但不保证完全一样（精度/并行差异）。如果时间不可接受，减少 n_sites 或换小体系。
3. MLIP 的快来自“学过的势”，不是“更精确的物理”。训练集没覆盖的分子/环境会外推，能量可能完全错；所以必须用 DFT 标定 top 位点。

## 本章产出

一张 MLIP vs DFT 对照表（至少 3 个位点）。  
下一章：06_dft.md。
