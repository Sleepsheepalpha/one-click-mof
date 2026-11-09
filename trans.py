#!/usr/bin/env python3
"""结构 -> Quantum ESPRESSO 输入转换器。

这是给网页界面用的“转换器”工具，也可以直接命令行使用：

    python3 trans.py mof.cif --out mof.in --mode scf
    python3 trans.py site_09.cif --out relax.in --mode relax --fix-framework

它本身不跑 DFT，只负责把 CIF/XYZ/POSCAR 等结构变成 pw.x 能读的 .in 文件。
真正的 QE 运行由“QE 运行已有输入”工具完成。
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from ase.io import read, write

HERE = Path(__file__).resolve().parent
MAKE_INPUT = HERE / "make_qe_input.py"


def parse_bool(v):
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "on", "y")


def primitive_cell(atoms):
    """返回 spglib 原胞和空间群符号；失败时抛异常。"""
    import spglib
    dataset = spglib.get_symmetry_dataset(
        (atoms.cell[:], atoms.get_scaled_positions(), atoms.numbers),
        symprec=1e-3,
    )
    if dataset is None:
        raise RuntimeError("spglib 无法判断对称性，不能约化成原胞")
    lattice, positions, numbers = spglib.standardize_cell(
        (atoms.cell[:], atoms.get_scaled_positions(), atoms.numbers),
        to_primitive=True,
        no_idealize=False,
        symprec=1e-3,
    )
    from ase import Atoms
    prim = Atoms(cell=lattice, scaled_positions=positions, numbers=numbers, pbc=True)
    return prim, dataset.international


def main():
    ap = argparse.ArgumentParser(description="CIF/XYZ/POSCAR -> QE .in 转换器")
    ap.add_argument("structure", help="输入结构文件（CIF/XYZ/POSCAR 等）")
    ap.add_argument("--out", required=True, help="输出 .in 文件")
    ap.add_argument("--mode", choices=["scf", "relax"], default="scf")
    ap.add_argument("--primitive", nargs="?", const=True, default=False, type=parse_bool,
                    help="约化成 spglib 原胞；可写 --primitive 或 --primitive false")
    ap.add_argument("--fix-framework", nargs="?", const=True, default=False, type=parse_bool,
                    help="仅 relax 模式有效：固定骨架，只放开尾部 movable-atoms 个原子")
    ap.add_argument("--movable-atoms", type=int, default=3,
                    help="尾部可动原子数：CH4=5、C2H6=8、C6H6=12、CO2=3")
    ap.add_argument("--unwrap-co2", nargs="?", const=True, default=False, type=parse_bool,
                    help="把最后两个 O 移到 C 旁边，避免跨晶胞边界")
    ap.add_argument("--ecutwfc", type=float, default=50.0)
    ap.add_argument("--ecutrho", type=float, default=400.0)
    ap.add_argument("--degauss", type=float, default=0.02)
    ap.add_argument("--conv-thr", type=float, default=1.0e-4)
    ap.add_argument("--forc-conv-thr", type=float, default=1.0e-3)
    ap.add_argument("--etot-conv-thr", type=float, default=1.0e-5)
    ap.add_argument("--nspin", type=int, default=1)
    ap.add_argument("--nstep", type=int, default=50)
    ap.add_argument("--prefix", default="mof")
    ap.add_argument("--outdir", default="./tmp")
    ap.add_argument("--pseudo-dir", default=str(HERE / "pseudo_sssp"))
    ap.add_argument("--info-json", default="", help="可选：写一份转换信息 JSON")
    args = ap.parse_args()

    src = Path(args.structure)
    if not src.exists():
        raise SystemExit(f"输入文件不存在：{src}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    atoms = read(str(src))
    n0 = len(atoms)
    spacegroup = None
    tmp_cif = None
    try:
        if args.primitive:
            atoms, spacegroup = primitive_cell(atoms)
            tmp = tempfile.NamedTemporaryFile(suffix=".cif", delete=False, dir=str(out.parent))
            tmp_cif = Path(tmp.name)
            tmp.close()
            write(str(tmp_cif), atoms)
            structure_for_qe = str(tmp_cif)
        else:
            structure_for_qe = str(src)

        fix = bool(args.fix_framework and args.mode == "relax")
        cmd = [
            sys.executable, str(MAKE_INPUT),
            "--cif", structure_for_qe,
            "--out", str(out),
            "--mode", args.mode,
            "--ecutwfc", str(args.ecutwfc),
            "--ecutrho", str(args.ecutrho),
            "--degauss", str(args.degauss),
            "--conv-thr", str(args.conv_thr),
            "--forc-conv-thr", str(args.forc_conv_thr),
            "--etot-conv-thr", str(args.etot_conv_thr),
            "--nspin", str(args.nspin),
            "--nstep", str(args.nstep),
            "--prefix", args.prefix,
            "--outdir", args.outdir,
            "--pseudo-dir", args.pseudo_dir,
        ]
        if fix:
            cmd.append("--fix-framework")
            cmd += ["--movable-atoms", str(args.movable_atoms)]
        if args.unwrap_co2:
            cmd.append("--unwrap-co2")
        proc = subprocess.run(cmd, text=True, capture_output=True)
        if proc.stdout:
            print(proc.stdout, end="")
        if proc.returncode != 0:
            if proc.stderr:
                print(proc.stderr, end="", file=sys.stderr)
            raise SystemExit(f"生成失败，退出码 {proc.returncode}")

        info = {
            "input": str(src),
            "output": str(out),
            "mode": args.mode,
            "fix_framework": fix,
            "movable_atoms": args.movable_atoms if fix else 0,
            "primitive": bool(args.primitive),
            "spacegroup": spacegroup,
            "natoms_input": n0,
            "natoms_output": len(atoms),
            "formula": atoms.get_chemical_formula(),
            "ecutwfc_Ry": args.ecutwfc,
            "ecutrho_Ry": args.ecutrho,
            "degauss_Ry": args.degauss,
            "conv_thr_Ry": args.conv_thr,
            "forc_conv_thr_Ry_au": args.forc_conv_thr if args.mode == "relax" else None,
            "nspin": args.nspin,
            "nstep": args.nstep if args.mode == "relax" else None,
            "pseudo_dir": args.pseudo_dir,
        }
        if args.info_json:
            ip = Path(args.info_json)
            ip.parent.mkdir(parents=True, exist_ok=True)
            ip.write_text(json.dumps(info, indent=2, ensure_ascii=False))
        print(f"结构: {src}")
        print(f"原子数: {n0} -> {len(atoms)}  ({atoms.get_chemical_formula()})")
        if spacegroup:
            print(f"空间群: {spacegroup}")
        print(f"模式: {args.mode}  固定骨架: {fix}")
        print(f"输出: {out}")
    finally:
        if tmp_cif and tmp_cif.exists():
            tmp_cif.unlink()


if __name__ == "__main__":
    main()
