# 第 14 章：附录（术语、单位、参数速查、排错）

## 本章目的

- 忘了某个词/参数时，能快速查；
- 报错时，先在这里找；
- 写论文时，直接抄单位/方法。

## 1. 术语表（计算背景）

| 术语 | 英文 | 计算含义 |
|---|---|---|
| E_ads（计算） | adsorption energy | 0 K 电子能差；不是实验吸附热/ΔG |
| ΔG_ads（计算） | adsorption free energy | 加 ZPE/热校正/熵；需标准态 |
| 计算等温线 | isotherm | GCMC/IAST/Langmuir；不是单个 DFT 点 |
| 计算选择性 | selectivity | IAST/竞争 GCMC；需混合气组成 |
| DFT | density functional theory | 电子结构计算 |
| PBE | Perdew-Burke-Ernzerhof | 常用泛函 |
| D3 | Grimme dispersion correction | 色散校正 |
| 赝势 | pseudopotential | 近似核心电子的文件 |
| 截断 | cutoff | 波函数/密度展开上限 |
| k 点 | k-point | 倒空间采样 |
| 展宽 | smearing / degauss | 费米面软化 |
| SCF | self-consistent field | 自洽迭代 |
| BSSE | basis set superposition error | 基组重叠误差 |
| ZPE | zero-point energy | 零点能 |
| 吸附熵 | entropy | 吸附态与气相的熵差；来自频率/统计力学 |
| MLIP | machine learning interatomic potential | 机器学习势 |
| MACE | a MLIP architecture | 本教程用的 MLIP |
| GCMC | grand canonical Monte Carlo | 直接模拟吸附等温线 |
| IAST | ideal adsorbed solution theory | 用单组分等温线预测混合物 |
| PBC | periodic boundary conditions | 周期性边界 |
| CN | coordination number | 配位数 |
| BVS | bond valence sum | 键价和 |
| MSD | mean squared displacement | 均方位移 |
| RDF | radial distribution function | 径向分布函数 |

## 2. 单位换算

- 1 Ry = 13.605693 eV
- 1 eV = 96.485 kJ/mol
- 1 bar = 10⁵ Pa = 0.9869 atm
- 1 Å = 10⁻¹⁰ m
- 1 ps = 10⁻¹² s
- 1 mmol/g = 22.414 cm³(STP)/g（理想气体）

## 3. 参数速查

| 参数 | 教学默认 | 省内存 | 高精度 | 备注 |
|---|---|---|---|---|
| ecutwfc/ecutrho | 50/400 | 40/320 | 60/480 | 做收敛测试 |
| k 点 | Γ | Γ | 2×2×2 | 小胞/金属要测 |
| degauss | 0.02 | 0.02 | 0.01 | bare/complex 一致 |
| conv_thr | 1e-4 | 1e-3 | 1e-5 | 看实际 scf accuracy |
| nspin | 1 | 1 | 2（开壳层） | Zn/Mg/Zr=1 |
| vdw_corr | grimme-d3 | 同 | 同 | 物理吸附必须 |
| np | 6 | 4 | 6–8 | 内存不够减 |
| nstep | 50 | 20 | 100+ | 到上限不是崩溃 |
| forc_conv_thr | 1e-3 Ry/au | 1e-2 | 5e-4 | 0.01≈0.26 eV/Å |
| MACE n_sites | 24 | 16 | 48–100 | 看体系 |
| MACE fmax | 0.05 eV/Å | 0.1 | 0.02 | 预筛可松 |
| MD dt | 0.5 fs | 0.5 | 0.5 | 含 H 不要大 |

## 4. 排错表

| 报错/现象 | 可能原因 | 先做什么 |
|---|---|---|
| command not found: pw.x | QE 没装/路径错 | which pw.x |
| ModuleNotFoundError | Python 环境错 | 用 .venv_mace/bin/python |
| 赝势 not found | pseudo_dir/元素 | ls 目录，检查元素 |
| SCF 不收敛 | 混合/展宽/几何 | 降 mixing_beta，换 local-TF |
| OOM | np/体系/截断 | 减 np，40/320 |
| JOB DONE 但能量怪 | 参考/原子顺序/单位 | 检查 reference、Ry/eV |
| 力不收敛 | nstep/阈值 | 续跑，检查最终力 |
| 分子断键 | 位点/模型 | 换位点/模型 |
| 图不能复现 | 随机种子/版本 | 固定 seed，记录版本 |

## 5. 文件命名

    projects/<project>/
      inputs/            CIF/XYZ
      runs/<date>_<tool>_<sample>_<adsorbate>_<site>/
        input/
        run.log
        job.json
        metrics.json
        qe.out
      expected/
      figures/

## 6. 参考与延伸

- Quantum ESPRESSO 手册（pw.x 输入）
- ASE 文档（Atoms、read/write、optimize）
- MACE / uMOF 模型 README
- RASPA2 手册（GCMC）
- pyIAST 文档（IAST）
- 本教程 benchmark/mof5/README.md

## 练习

1. 为什么不能把 E_ads 直接当 ΔG 用？
2. 为什么“JOB DONE”不等于“结果可信”？
3. 如果审稿人问 BSSE，而你只算了 PBE-D3 单点，应该怎么回答？

## 练习答案

1. E_ads 是 0 K 电子能差；ΔG 还包含 ZPE、热校正、熵和标准态。吸附熵通常为负，−TΔS 为正，所以 ΔG 通常比 E_ads 浅。
2. JOB DONE 只说明程序正常结束；还要看 SCF accuracy、力/几何收敛、参数一致性、参考能和单位。程序正常结束但设置错，结果仍然不可信。
3. 不能装作算过。应说明未做 counterpoise，给出 BSSE 可能的量级（例如 0.05–0.2 eV，苯更大），并指出这会影响绝对 E_ads 但不一定改变趋势；如果审稿要求，补 counterpoise 或更大基组。

## 7. 最后检查

- [ ] 结构不是含溶剂/无序的“脏”结构；
- [ ] 参考分子同盒子/同参数；
- [ ] bare/complex/ref 四个一致；
- [ ] SCF 真收敛；
- [ ] 力真收敛；
- [ ] E_ads 单位和符号对；
- [ ] E_ads 与 ΔG 分清；
- [ ] 等温线来源写清；
- [ ] 图和表能对上；
- [ ] 原始文件能复现。
