# Jupyter Notebook 规划

> 状态：只有规划，还没有创建 .ipynb。  
> 结论：Jupyter 作为“教学/可复现/画图层”保留；不做网页的第二个入口。

## 1. 只做 4 个核心 notebook

| Notebook | 对应章节 | 内容 | 依赖 |
|---|---|---|---|
| 00_setup_check.ipynb | 01 | 打印版本、检查 QE/赝势/模型/GPU、跑结构体检 | one_click_mof/core、ASE |
| 01_structure_sites.ipynb | 02–05 | 读 CIF、结构体检、MOF-5 原胞、位点搜索、位点图 | core、MACE/UFF |
| 02_dft_eads.ipynb | 06–08 | 生成 bare/complex/reference、跑/读 QE、算 E_ads、误差表 | core、QE |
| 03_isotherm_figure.ipynb | 09–11 | Langmuir/IAST/GCMC、论文图、报告表 | core、matplotlib |

## 2. Cell 设计规则

1. 第一个 cell 只做环境与路径，不跑计算。
2. 每个 notebook 从第一行跑到最后一行必须成功；不依赖隐藏状态。
3. 所有“动作”调用 one_click_mof/core 或 CLI，不在 notebook 里复制一套逻辑。
4. 参数集中在顶部 cell，改成变量，不在命令里手写魔法数。
5. 大轨迹/大日志只显示路径和摘要，不嵌入输出。
6. 图保存到 tutorial/figures/，同时显示。
7. 每个 notebook 末尾有“检查清单”和“如果失败先看什么”。

## 3. 路径约定

    tutorial/benchmark/mof5/inputs/
    tutorial/benchmark/mof5/expected/
    tutorial/figures/

## 4. 验收

- 用 nbclient 或 papermill 在干净环境跑一遍。
- 每个 notebook 记录运行时间；超过 10 分钟的步骤改成“可选/长任务”。
- notebook 与 Markdown 章节一一对应，不出现“notebook 里有、正文没有”的步骤。

## 5. 为什么不是每章一个 notebook

- 维护成本高，容易和网页/正文漂移。
- 新手需要的是 4 个完整闭环，不是 15 个碎片。
- 长篇解释放 Markdown；notebook 只保留可执行的关键步骤。
