# MOF-5 基准算例（MOF-5 / IRMOF-1）

> 状态：输入已就位；结构体检已跑；MACE 位点、DFT 能量、等温线数值待首次完整跑通后回填。
> 用途：整套教程的“同一条主线”算例。所有章节都尽量回到这个算例，避免每章换一个体系。  
> 时间估算：见 [TIMING.md](TIMING.md)（各节结果表的壁钟时间、最小闭环 vs 论文级）。

## 1. 为什么用 MOF-5

- 结构小、经典、文献多，适合教学。
- 原胞 106 原子，QE 50/400 单点在普通笔记本上可承受。
- 有 Zn4O 节点、苯环 linker、大孔道，CH4/C2H6/C6H6 都能讲。
- 不含开壳层金属，默认 nspin=1 合理。
- 注意：MOF-5 的水稳定性差；本教程默认干气，不把湿度作为主线。

## 2. 输入文件

| 文件 | 说明 |
|---|---|
| inputs/IRMOF-1_conventional.cif | 常规立方胞，424 原子，a=25.832 Å；来源：本机 RASPA2 示例结构 IRMOF-1.cif |
| inputs/IRMOF-1_primitive.cif | 用 spglib 约化后的原胞，106 原子；本教程默认用这个 |
| inputs/CH4.xyz | 甲烷，5 原子 |
| inputs/C2H6.xyz | 乙烷，8 原子 |
| inputs/C6H6.xyz | 苯，12 原子 |

分子文件由 ASE build.molecule 生成，几何为常规实验/力场几何；正式计算前可用 Avogadro/UFF 再优化一次。

## 3. 结构体检结果（已跑）

命令：

    cd /home/sleep-sheep/mof_calculation
    .venv_mace/bin/python one_click_mof/tools/structure_check.py \
      --cif tutorial/benchmark/mof5/inputs/IRMOF-1_primitive.cif \
      --out tutorial/benchmark/mof5/expected/structure_check.json

结果：

| 指标 | 值 |
|---|---|
| 原子数 | 106 |
| 化学式 | C48H24O26Zn8 |
| 晶胞 | 原胞，a=b=c=18.266 Å，α=β=γ=60°（菱方表示） |
| 体积 | 4309.37 Å³ |
| 密度 | 0.5933 g/cm³ |
| 最短距离 | 0.927 Å（C–H，正常） |
| 短接触 | 0 |
| Zn–O 配位数 | 平均 4.0（8 个 Zn 全部 4 配位） |
| 未配位 O | 0 |
| 空隙率（网格法） | 约 87%（1.2 Å 探针）/ 82%（1.4 Å 探针） |

> 空隙率是教学用网格估算；论文里建议用 Zeo++ 的 probe 1.2 Å 结果并注明方法。

## 4. 计划中的基准算例

### 4.1 结构

- 主结构：IRMOF-1_primitive.cif（106 原子）。
- 可选对照：常规胞 424 原子，只用于验证原胞/常规胞一致性，不用于生产。

### 4.2 分子

- CH4：主教学分子，弱物理吸附，适合先跑通。
- C2H6：比 CH4 强，讲构象和 C–H···O。
- C6H6：讲 π–π 堆叠、色散、BSSE 和取向采样。

### 4.3 计算顺序

1. 结构体检（已完成）。
2. 位点搜索：每个分子 24 个起点，probe 2.2 Å，seed 固定。
3. 取 top 3 位点做 QE 单点。
4. 取 top 1 位点做局部弛豫（只放吸附质，或吸附质+第一壳层）。
5. 算 E_ads；做参考能、截断/展宽一致性检查。
6. 用 Langmuir/IAST 或 RASPA2 GCMC 生成等温线；画论文图。
7. 写一页报告。

### 4.4 结果表（2026-11-08，重筛后）

| 分子 | MACE best (eV) | 位点 | DFT 单点 (eV) | 最近接触 (Å) | 上一轮 DFT (eV) |
|---|---:|---:|---:|---:|---:|
| CH4 | -0.115 (14) | 14 | **-0.6682** | 3.23 | -0.7161 (site 3) |
| C2H6 | -0.121 (17) | 17 | **-1.0611** | 3.30 | -1.1753 (site 21) |
| C6H6 | -0.252 (17) | 17 | **-2.3941** | 3.22 | -2.4397 (site 17) |

> 重筛条件：probe 2.8 Å、min_mol_framework ≥ 3.0 Å、32 起点、seed 20261109。全部用同晶胞参考。
>
> **重筛没有解决问题**：接触推到 3.2–3.4 Å，E_ads 只弱 0.05–0.11 eV。孔心对照（应得 0）实测 CH4 -0.40、C2H6 -0.92、C6H6 -2.16 eV；同一原胞换位置参考能变化约 4 eV（立方胞无此问题，ecutrho 1600 也不收敛）。双差分校准后 CH4 -0.27、C2H6 -0.14、C6H6 -0.23 eV；苯比甲烷弱，说明过度校正。这组数只作流程演示。
>
> 新位点还没做弛豫；旧位点弛豫过，只再降 0.004–0.019 eV。
>
> 原始 20 Å 参考得到 -2.6/-5.4/-16.8 eV，已作废。详见 expected/RESULT_CHECK_2026-11-07.md。

> 不要用 MACE 数直接填这张表；MACE 只能作为预筛，最终列必须是 DFT。

## 5. 预期输出目录

    tutorial/benchmark/mof5/
      inputs/                 输入 CIF/XYZ
      expected/               结构体检、位点表、E_ads 表、图
      runs/                   实际 QE/MACE 输出（不提交到教程正文）

建议命名：

    runs/YYYYMMDD_mof5_CH4_site03_scf/
    runs/YYYYMMDD_mof5_CH4_site03_relax/
    runs/YYYYMMDD_mof5_CH4_ref/

## 6. 判断标准（本算例）

- 结构：106 原子、C48H24O26Zn8、Zn CN 4、无短接触。
- 位点：至少 10 个 intact 位点；top 位点不嵌入骨架、分子不变形。
- 能量：bare/complex/reference 的截断、degauss、conv_thr、赝势一致；SCF 收敛；JOB DONE。
- 合理性：CH4 约 -0.1 ~ -0.3 eV；C2H6 约 -0.2 ~ -0.4 eV；C6H6 约 -0.4 ~ -0.8 eV（数量级参考，不是本算例结果）。
- 等温线：标明来源（GCMC/IAST/Langmuir/实验）、温度、压力范围、单位。

## 7. 不要做的事

- 不要把常规胞 424 原子直接拿去做 50 ps MD 或大量 DFT。
- 不要把 MACE 排序当 DFT 结论。
- 不要用未收敛的 SCF/弛豫结果填表。
- 不要在教程里混入用户自玩的旧体系。
