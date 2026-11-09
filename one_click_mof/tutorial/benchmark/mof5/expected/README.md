# MOF-5 基准算例：预期输出

> 状态：结构体检已生成；其余待首次完整跑通后回填。  
> 原则：没有实际跑过的数不写；用【待回填】占位。

## 已生成

| 文件 | 内容 |
|---|---|
| structure_check.json | 106 原子、C48H24O26Zn8、密度 0.5933、Zn CN 4.0、无短接触 |

## 待生成

| 文件 | 内容 | 来源 |
|---|---|---|
| screen_CH4.csv | 24 个 CH4 位点、E_ads、intact、几何指标 | MACE 预筛 |
| screen_C2H6.csv | 同上 | MACE 预筛 |
| screen_C6H6.csv | 同上 | MACE 预筛 |
| eads_CH4.csv | top 3 位点的 DFT E_ads | QE 单点 |
| eads_C2H6.csv | top 3 位点的 DFT E_ads | QE 单点 |
| eads_C6H6.csv | top 3 位点的 DFT E_ads | QE 单点 |
| isotherm_CH4.csv | P、uptake、模型、来源 | GCMC/IAST/Langmuir |
| fig_sites_CH4.png | 位点能量分布 | matplotlib |
| fig_isotherm_CH4.pdf | 论文用等温线 | matplotlib |

## 结果表模板

| 分子 | 位点 | E_ads 固定 (eV) | E_ads 弛豫 (eV) | SCF 收敛 | 力收敛 | 备注 |
|---|---|---|---:|---:|---|---|---|
| CH4 | site-?? | 【待回填】 | 【待回填】 | 【待回填】 | 【待回填】 | 主教学 |
| C2H6 | site-?? | 【待回填】 | 【待回填】 | 【待回填】 | 【待回填】 | 构象 |
| C6H6 | site-?? | 【待回填】 | 【待回填】 | 【待回填】 | 【待回填】 | π–π/BSSE |
