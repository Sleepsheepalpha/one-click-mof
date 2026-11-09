# 第 1 章：把环境跑起来（不装软件版 + 终端版）

## 本章目的

学完这一章，你应该能：

- 用“便携包/网页”启动 one_click_mof；
- 知道 Python、QE、赝势、MACE 模型分别在哪里；
- 跑通第一次“结构体检”；
- 知道缺文件时去哪看错误，而不是重装系统。

## 计算背景速查

| 词 | 计算含义 |
|---|---|
| 终端 / terminal | 打命令的黑框；本教程默认你可以不用它 |
| Python 环境 | 一套“带着库的 Python”，不是系统自带那个 |
| PATH | 系统找可执行文件的目录列表 |
| QE / pw.x | 算 DFT 的程序；pw.x 是主程序 |
| 赝势 / pseudopotential | 用“近似核心电子”的方式描述原子的文件；缺了 QE 跑不了 |
| MACE 模型 | 机器学习势的权重文件；用来快速找位点 |
| Jupyter | 网页里一格一格跑 Python 的笔记本 |

## 做法（两条路，选一条）

### 路线 A：给“不想装软件”的人（目标形态）

> 现状：便携包还没做；下面描述的是最终用户路径。当前开发机先用路线 B。

1. 解压 one_click_mof_portable（未来产物）。
2. 双击 One-Click MOF。
3. 浏览器自动打开 http://127.0.0.1:8765。
4. 首次启动自检：Python、QE、赝势、模型、GPU 五项。
5. 打开 tutorial/benchmark/mof5/inputs/IRMOF-1_primitive.cif，跑“结构体检”。

### 路线 B：当前开发机（已经可用）

1. 打开终端。
2. 进入项目目录：

    cd /home/sleep-sheep/mof_calculation

3. 启动网页：

    python3 one_click_mof/app.py --port 8765

4. 浏览器打开 http://127.0.0.1:8765。
5. 在“路径设置”里确认：
   - Python：/home/sleep-sheep/mof_calculation/.venv_mace/bin/python
   - pw.x：/usr/bin/pw.x
   - mpiexec：/usr/bin/mpiexec
   - 赝势目录：/home/sleep-sheep/mof_calculation/pseudo_sssp
   - MACE 模型：models/umof/umof_models/uMOF-MH.model

### 路线 C：纯终端（进阶）

    cd /home/sleep-sheep/mof_calculation
    .venv_mace/bin/python -c "import ase, mace, torch; print(ase.__version__, mace.__version__, torch.cuda.is_available())"
    pw.x --version
    ls pseudo_sssp | head

## 界面操作（VESTA / Avogadro / ASE GUI）

| 软件 | 用途 | 在 Ubuntu 22.04 怎么打开 |
|---|---|---|
| VESTA | 看 CIF、量距离、看孔道、导出图片 | 应用菜单搜索 VESTA；或终端 vesta |
| Avogadro | 画分子、加 H、UFF 预优化、导出 XYZ | 应用菜单搜索 Avogadro |
| ASE GUI | 快速看结构/轨迹 | 终端 ase gui 文件.cif |

> 这三个都不是 DFT；它们只帮你“看”和“改结构”。

## 参数表

| 参数 | 作用 | 默认 | 怎么调 |
|---|---|---|---|
| python | 用哪个 Python 跑脚本 | .venv_mace/bin/python | 换环境时改；必须是装了 ase/mace 的那个 |
| pw.x | QE 主程序 | /usr/bin/pw.x | which pw.x 查 |
| mpiexec | 并行启动器 | /usr/bin/mpiexec | which mpiexec 查 |
| pseudo_dir | 赝势目录 | pseudo_sssp | 换元素/换泛函时改 |
| mace_model | MACE 权重 | uMOF-MH.model | 换模型时改；注意 head |
| np | MPI 进程数 | 6 | 303 原子常用 6；内存不够就减 |
| device | MACE 设备 | cuda | 没显卡改 cpu |

> 路径设置里还有 VESTA、Avogadro、RASPA2、Zeo++ 卡片：VESTA 用于看结构/截图，Avogadro 用于画分子，RASPA2/Zeo++ 是可选论文级工具。ASE GUI 不需要单独路径，用 Python 环境运行 `python -m ase gui`；Jupyter 按当前计划暂搁置。

## MOF-5 基准算例

### 1. 检查环境

    cd /home/sleep-sheep/mof_calculation
    .venv_mace/bin/python -c "import ase, mace, torch; print('ase', ase.__version__); print('mace', mace.__version__); print('cuda', torch.cuda.is_available())"

应看到 ase 3.29.0、mace 0.3.16、cuda True（本机）。

### 2. 检查 QE

    pw.x --version

应看到 PWSCF v.6.7MaX。

### 3. 跑结构体检

    .venv_mace/bin/python one_click_mof/tools/structure_check.py \
      --cif tutorial/benchmark/mof5/inputs/IRMOF-1_primitive.cif \
      --out tutorial/benchmark/mof5/expected/structure_check.json

应看到：106 原子、C48H24O26Zn8、Zn CN 4.0、n_short_contacts 0。

## 怎么判断成功

- 三条检查命令都没有 ModuleNotFoundError / command not found；
- 结构体检 JSON 能打开，natoms=106；
- 网页能打开，路径设置没有红字；
- 你没有用 sudo 装任何东西（路线 A 的目标）。

## 常见错误

| 现象 | 先看什么 | 处理 |
|---|---|---|
| command not found: pw.x | which pw.x | 装 QE 或改路径 |
| ModuleNotFoundError: ase | 用的哪个 python | 用 .venv_mace/bin/python |
| MACE 报 CUDA out of memory | 显存 | device=cpu 或减少并行 |
| 赝势找不到 | pseudo_dir | 确认文件在目录里、元素对得上 |
| 网页打不开 | 端口/进程 | 看终端是否报错；换端口 8766 |

## 练习

1. 把 python 路径故意改错，看网页报什么错；再改回来。
2. 用 VESTA 打开 IRMOF-1_primitive.cif，找到 Zn4O 节点，量一个 Zn–O 距离。
3. 用 ase gui 打开 CH4.xyz，确认有 5 个原子。

## 练习答案

1. 通常会看到 ModuleNotFoundError / “python 不可执行” / 路径不存在；网页任务失败，run.log 里有 traceback。把路径改回 .venv_mace/bin/python 后，结构体检应恢复正常。
2. Zn4O 节点是 4 个 Zn 围一个中心 O；每个 Zn 还连 3 个羧基 O，总共 4 配位。VESTA 里量 Zn–O 原子中心距离，约 1.9–2.0 Å（MOF-5 约 1.95 Å）；注意不要量到周期镜像。
3. ase gui 打开后应显示 5 个原子（1 C + 4 H），C–H 约 1.09 Å；如果少于 5 个，XYZ 读入有问题。

## 本章产出

一份“环境自检记录”：Python 版本、QE 版本、赝势目录、模型路径、GPU 是否可用。  
下一章：02_structure.md。
