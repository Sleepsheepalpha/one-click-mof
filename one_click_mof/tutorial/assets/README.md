# 截图与示意图

> 状态：主体已补（2026-11-07），少量待补。
>
> 命名：章节号_内容.png。
>
> 要求：截图里不要出现用户自玩的旧体系；用 MOF-5 基准算例。
>
> 每张图在正文里有图注：这张图在说明什么、看到什么算成功。

## 已有

| 文件 | 来源 | 用在哪 |
|---|---|---|
| `02_mof5_cell.png` | VESTA | 02 章图 2-1 |
| `02_zn4o_node.png` | VESTA | 02 章图 2-2 |
| `02_pore.png` | VESTA | 02 章图 2-3 |
| `03_molecules.png` | ASE `build.molecule` | 03 章图 3-1 |
| `04_ch4_site03.png` | VESTA | 04 章图 4-1 |
| `04_c2h6_site21.png` | VESTA | 04 章图 4-2 |
| `04_c6h6_site17.png` | VESTA | 04 章图 4-3 |
| `06_ref_same_cell.png` | VESTA | 03 章图 3-2、06 章参考能小节 |

旧的 `03_reference_box.png`（20 Å 盒子示意）与现在的“同晶胞、同坐标参考”相反，已移到 `legacy/`，正文不再引用。

## 待补

- `07_relax_ch4.png`：CH4 弛豫前后叠图，等 `run_mof5_finish.py` 跑完再拍。
- 网页截图（项目页/教程页）暂不放进正文，避免教程依赖 UI 版本。

## VESTA 输入

`vesta/` 下是截图用的干净 CIF：106 原子原胞、三个分子的最稳位点、同晶胞 CH4 参考。
