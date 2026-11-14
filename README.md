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

## Windows 用户：WSL2 + Ubuntu 22.04

本项目是 Linux 原生工作流（QE / OpenMPI / zenity）。Windows 上推荐先安装 **WSL2**，在 WSL2 的 Ubuntu 22.04 里运行；浏览器仍用 Windows 的 Edge/Chrome 打开 `http://localhost:8765`。

> 暂无 Windows 原生一键包。原生 Windows 需要额外适配文件选择器、进程终止、启动脚本和 QE/MS-MPI 路径，当前不作为主路线。

### 1. 前提检查

- Windows 10 21H2+ 或 Windows 11（64 位）
- BIOS 已开启虚拟化（Intel VT-x / AMD-V）
- 使用管理员 PowerShell
- 建议 Windows 11：自带 WSLg，`zenity` 文件选择框可用
- Windows 10 没有 WSLg，文件选择框可能不可用，需要在网页里直接手填 WSL 路径

### 2. 安装 WSL2 与 Ubuntu 22.04

管理员 PowerShell：

```powershell
wsl --install -d Ubuntu-22.04
wsl --set-default-version 2
wsl --update
```

安装完成后重启 Windows。第一次从开始菜单打开 **Ubuntu 22.04**，设置 Linux 用户名和密码。

检查版本：

```powershell
wsl -l -v
```

`VERSION` 应为 `2`。

如果系统提示 `wsl` 不是命令，先启用 Windows 功能（管理员 PowerShell）：

```powershell
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
```

重启后执行：

```powershell
wsl --set-default-version 2
wsl --install -d Ubuntu-22.04
```

如果 `Ubuntu-22.04` 不在可选列表中：

```powershell
wsl --list --online
wsl --install -d Ubuntu-22.04
```

### 3. 安装 Ubuntu 依赖

打开 Ubuntu 终端，执行：

```bash
sudo apt update
sudo apt upgrade -y
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
git --version
```

### 4. GPU 检查

Windows 侧安装支持 WSL 的新版 NVIDIA 驱动；**不要在 WSL 里安装 Linux 显卡驱动**。

在 Ubuntu 终端检查：

```bash
nvidia-smi
```

能显示 RTX 显卡即可。PyTorch 的 CUDA 版安装在 WSL 的 Python 环境里完成，安装命令与下面的 Ubuntu 步骤相同。

如果继续使用 CPU 版 PyTorch，也可以运行，只是 MACE 会明显变慢。

### 5. 放置代码

建议把项目放在 WSL 的 Linux 主目录，而不是 `/mnt/c`，避免 QE 大量小文件 I/O 变慢：

```bash
cd ~
git clone https://github.com/Sleepsheepalpha/one-click-mof.git
cd one-click-mof
```

之后按下面的 **Ubuntu 22.04 安装** 第 3–5 步创建 Python 环境、放置 MACE 模型和 SSSP 赝势。

> 不要在 Windows 里克隆后再用 WSL 运行。Windows 的换行符可能让 `start.sh` 报 `bad interpreter`；请直接在 WSL 终端里 `git clone`。

### 6. 启动与访问

在 WSL 的 Ubuntu 终端里：

```bash
cd ~/one-click-mof
bash one_click_mof/start.sh
```

然后在 Windows 浏览器打开：

```text
http://localhost:8765
```

WSL2 会自动把 localhost 转发到 Windows。服务只监听 `127.0.0.1`，不要改成 `0.0.0.0`。

> WSL2 里不要运行 `install_launcher.sh`：它面向 GNOME 桌面，WSL 没有 GNOME 会话。需要快捷方式时，在 Windows 创建一个指向 WSL 命令的快捷方式，或每次运行上面的 `start.sh`。

### 7. Windows 与 WSL 路径对应

| Windows | WSL2 |
|---|---|
| `C:\Users\name\data` | `/mnt/c/Users/name/data` |
| `D:\MOF\runs` | `/mnt/d/MOF/runs` |
| WSL 项目目录 | Windows 11：`\\wsl.localhost\Ubuntu\home\<user>\one-click-mof`；Windows 10：`\\wsl$\Ubuntu\home\<user>\one-click-mof` |

网页“路径设置”里应填 WSL 路径，例如：

```text
/home/<user>/one-click-mof/.venv_mace/bin/python
/usr/bin/pw.x
/usr/bin/mpiexec
/home/<user>/one-click-mof/pseudo_sssp
/home/<user>/one-click-mof/models/umof/umof_models/uMOF-MH.model
```

Windows 11 的 WSLg 下，“浏览…”通常能打开 `zenity`；Windows 10 没有 WSLg 时，直接在输入框粘贴 WSL 路径。

### 8. WSL 内存限制

WSL2 默认可能占用较多或较少内存。大体系 QE 建议在 Windows 用户目录创建 `C:\Users\<WindowsUser>\.wslconfig`：

```ini
[wsl2]
memory=24GB
processors=12
swap=8GB
```

保存后管理员 PowerShell 执行：

```powershell
wsl --shutdown
```

再重新打开 Ubuntu。数值按本机内存调整，至少给 Windows 留 4–6 GB。

### 9. 常见问题

| 现象 | 处理 |
|---|---|
| `wsl` 不是内部或外部命令 | 先启用 WSL/虚拟机平台功能并重启 |
| `WslRegisterDistribution failed` | BIOS 虚拟化未开启，或虚拟机平台功能未启用 |
| `nvidia-smi` 找不到 | 更新 Windows NVIDIA 驱动；不要装 Linux 显卡驱动 |
| 浏览器打不开 localhost | 确认 WSL 里 `start.sh` 仍在运行，端口 8765 未被占用 |
| “浏览…”没有弹窗 | Windows 10 没有 WSLg；直接手填 WSL 路径 |
| `start.sh: bad interpreter` | 在 WSL 里重新 clone，不要在 Windows 克隆后跨系统运行 |
| QE 很慢 / 磁盘占用大 | 项目与输出放在 WSL 的 `~/`，不要放 `/mnt/c` |
| 内存不足 | 调整 `.wslconfig` 的 `memory`，或减小 QE 并行/体系 |

## Ubuntu 22.04 安装（原生 Ubuntu / WSL2）

> 原生 Ubuntu 从第 1 步开始；已按上面 WSL2 完成系统依赖的，可跳过第 1 步，直接从第 3 步创建 Python 环境开始。

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

### 7. 安装桌面图标 / 任务栏

推荐安装成桌面应用，之后不用再 `cd` 或敲 Python 命令：

```bash
bash one_click_mof/install_launcher.sh
```

它会：

- 在应用菜单注册 `One-Click MOF`
- 在桌面生成 `One-Click MOF.desktop`
- 把图标加入 GNOME 任务栏收藏夹
- 双击图标时自动启动服务并打开浏览器

之后直接点任务栏/桌面的 **One-Click MOF** 图标即可。移动项目目录后重新运行一次安装脚本。

### 8. 路径设置

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

### 9. 第一次验证

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
  start.sh              启动服务并打开浏览器
  install_launcher.sh   安装桌面图标/任务栏收藏
  manifests/            工具清单
  static/               前端与图标
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

## 安全

- 服务只绑定 `127.0.0.1`
- 没有登录系统
- 不能改成 `0.0.0.0` 暴露到公网

## 版本

`0.1.0`
