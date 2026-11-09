# 输入文件说明

| 文件 | 来源/生成方式 | 用途 |
|---|---|---|
| IRMOF-1_conventional.cif | 本机 RASPA2 示例结构（IRMOF-1.cif）；常规立方胞 424 原子 | 对照/可视化 |
| IRMOF-1_primitive.cif | 用 spglib 从常规胞约化；原胞 106 原子 | 主计算结构 |
| CH4.xyz | ASE build.molecule('CH4') | 主教学分子 |
| C2H6.xyz | ASE build.molecule('C2H6') | 乙烷案例 |
| C6H6.xyz | ASE build.molecule('C6H6') | 苯案例 |

## 注意事项

- 原胞是菱方表示（a=b=c=18.266 Å，α=β=γ=60°），不是立方；不要用 length^3 当体积。
- 分子几何是常规几何；正式计算前可用 Avogadro/UFF 再优化，并记录构象。
- 不要用常规胞 424 原子直接跑大量 DFT/MD；它只用于对照。
- 引用/发表前确认 CIF 来源和许可；教学内部使用可先保留来源说明。
