# One-Click MOF

**版本：0.1.0**

一个面向化学/材料实验人员的本地 MOF 吸附计算工作台：在浏览器里选 CIF、配吸附质、跑结构体检 / MACE 位点筛选 / QE 单点或局部弛豫，查看日志、指标和结果表。

> 当前是研究原型，已在 Ubuntu 22.04 + Python 3.10 + QE 6.7MaX + MACE 0.3.16 上验证。绑定 `127.0.0.1`，仅限单机本地使用。

## 功能

- 项目目录扫描：CIF、QE 输入、XYZ
- 结构体检：原子数、密度、短接触、金属-氧配位数
- 同晶胞参考：从复合物提取同 cell、同坐标的 reference 分子
- MACE 位点筛选：CH4 / C2H6 / C6H6 / CO2 或自定义 XYZ
- 结构转 QE 输入：scf / relax，可固定骨架
- QE 单点、局部弛豫、运行已有输入
- MD 分析：MSD、扩散系数、RDF、稳定性
- 运行队列、实时日志、结果筛选、CSV 导出

## 系统要求

- Ubuntu 22.04（推荐）
- Python 3.10
- Quantum ESPRESSO 6.7（Ubuntu 包）
- OpenMPI / `mpiexec`
- NVIDIA GPU 可选；MACE 可用 CPU，但会慢很多
- 磁盘：至少 10 GB；QE 长任务建议把输出目录放到大盘

## Ubuntu 22.04 安装

### 1. 安装系统依赖

```bash
sudo apt update
sudo apt install -y \
  git python3 python3-venv python3-pip \
  quantum-espresso openmpi-bin \
  zenity xdg-utils
```

检查：

```bash
python3 --version
pw.x -h | head
mpiexec --version
```

> `pw.x --version` 会启动 pw.x；查看版本请用 `pw.x -h`。

### 2. 获取代码

```bash
git clone https://github.com/Sleepsheepalpha/one-click-mof.git
cd one-click-mof
```

### 3. 创建 Python 环境

```bash
python3 -m venv .venv_mace
source .venv_mace/bin/activate
python -m pip install --upgrade pip setuptools wheel
```

CUDA 11.8 显卡环境：

```bash
pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cu118
pip install -r requirements.txt
```

只有 CPU：

```bash
pip install torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

检查：

```bash
python -c "import ase, mace, torch; print(ase.__version__, mace.__version__, torch.cuda.is_available())"
```

### 4. 准备 MACE 模型

从 uMOF Figshare 下载 `uMOF-MH.model`：

<https://doi.org/10.6084/m9.figshare.33311829>

放到：

```text
models/umof/umof_models/uMOF-MH.model
```

### 5. 准备 SSSP 赝势

从 Materials Cloud SSSP 页面下载 SSSP 1.3.0 efficiency 的 UPF 文件：

<https://www.materialscloud.org/discover/sssp/table/efficiency>

解压/复制到：

```text
pseudo_sssp/
```

目录里应当能看到大量 `.UPF` 文件。

### 6. 启动网页

```bash
python3 one_click_mof/app.py --port 8765
```

或：

```bash
bash one_click_mof/start.sh
```

浏览器打开：

```text
http://127.0.0.1:8765
```

### 7. 路径设置

进入网页“路径设置”，填写：

| 工具 | 示例 |
|---|---|
| Python | `<repo>/.venv_mace/bin/python` |
| pw.x | `/usr/bin/pw.x` |
| mpiexec | `/usr/bin/mpiexec` |
| SSSP 赝势目录 | `<repo>/pseudo_sssp` |
| MACE 模型 | `<repo>/models/umof/umof_models/uMOF-MH.model` |
| 运行目录 | `<repo>/runs` 或 `/Data/mof_runs` |

VESTA、Avogadro、RASPA2、Zeo++ 是可选工具；没有安装不影响主流程。

### 8. 第一次验证

1. “项目与文件” → 输入目录选 `one_click_mof/tutorial/benchmark/mof5/inputs`
2. 扫描目录
3. 选 `IRMOF-1_primitive.cif`
4. 工具选“结构体检”
5. 加入队列 → 运行队列 → 启动队列
6. 结果应显示 106 原子、Zn–O 配位数 4、无短接触

## 教程

完整教程在：

```text
one_click_mof/tutorial/
```

包含 MOF-5 基准算例、结构体检、MACE 位点、QE 单点/弛豫、同晶胞参考、热力学和等温线说明。

## 目录

```text
one_click_mof/
  app.py                本地 Web 服务
  manifests/            工具清单
  static/               前端
  tools/                结构体检、MACE 筛选、同晶胞参考
  tutorial/             教程与 MOF-5 基准输入
make_qe_input.py        CIF -> QE 输入
trans.py                结构转换器
analyze_md.py           MD 分析
requirements.txt        Python 依赖
```

## 已知限制

- MD 目前只有分析，没有网页 MD 运行器
- 等温线/GCMC/IAST 还没有内置执行器
- QE 参数一致性仍需用户自己检查
- MACE 只用于找位点和排序，不能替代最终 DFT 能量
- 旧任务数据库里的绝对路径换机器后会失效

## Windows

暂无Windows 一键包。建议优先使用 **WSL2 + Ubuntu 22.04**，在 Linux 环境中运行同一套代码；Windows 浏览器访问 `http://127.0.0.1:8765`。原生 Windows 需要额外适配文件选择器、进程终止、启动脚本和 QE/MS-MPI 路径。

## 安全

- 服务只绑定 `127.0.0.1`
- 没有登录系统
- 不能改成 `0.0.0.0` 暴露到公网

## 版本

`0.1.0`
