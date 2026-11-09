#!/usr/bin/env python
"""Generate a Quantum ESPRESSO input from a CIF.

Usage:
  make_qe_input.py --cif mof.cif --out mof.in --mode scf --nspin 1
  make_qe_input.py --cif mof_co2.cif --out mof_co2.in --mode relax --fix-framework
"""
import argparse, os
import numpy as np
from ase.io import read

PSEUDO = {
    "H": "H.pbe-rrkjus_psl.1.0.0.UPF",
    "C": "C.pbe-n-kjpaw_psl.1.0.0.UPF",
    "N": "N.pbe-n-radius_5.UPF",
    "O": "O.pbe-n-kjpaw_psl.0.1.UPF",
    "Mg": "Mg.pbe-n-kjpaw_psl.0.3.0.UPF",
    "Co": "Co_pbe_v1.2.uspp.F.UPF",
    "Mn": "mn_pbe_v1.5.uspp.F.UPF",
    "Zn": "Zn_pbe_v1.uspp.F.UPF",
    "Zr": "Zr_pbe_v1.uspp.F.UPF",
}
MASS = {"H":1.008,"C":12.011,"N":14.007,"O":15.999,"Mg":24.305,
        "Co":58.933,"Mn":54.938,"Zn":65.38,"Zr":91.224}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cif", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mode", choices=["scf","relax"], default="scf")
    ap.add_argument("--fix-framework", action="store_true",
                    help="relax only the last N atoms (default 3, CO2); fix all others")
    ap.add_argument("--movable-atoms", type=int, default=3,
                    help="number of movable atoms at the tail when --fix-framework is used")
    ap.add_argument("--ecutwfc", type=float, default=50.0)
    ap.add_argument("--ecutrho", type=float, default=400.0)
    ap.add_argument("--nspin", type=int, default=1)
    ap.add_argument("--prefix", default="mof")
    ap.add_argument("--outdir", default="./tmp")
    ap.add_argument("--pseudo-dir", default="/home/sleep-sheep/mof_calculation/pseudo_sssp")
    ap.add_argument("--nstep", type=int, default=50)
    ap.add_argument("--forc-conv-thr", type=float, default=1.0e-3,
                    help="force convergence threshold in Ry/au for relax")
    ap.add_argument("--etot-conv-thr", type=float, default=1.0e-5,
                    help="energy convergence threshold in Ry for relax")
    ap.add_argument("--degauss", type=float, default=0.01)
    ap.add_argument("--mixing-beta", type=float, default=0.2)
    ap.add_argument("--mixing-mode", default="local-TF")
    ap.add_argument("--diagonalization", default="david")
    ap.add_argument("--conv-thr", type=float, default=1.0e-6)
    ap.add_argument("--unwrap-co2", action="store_true",
                    help="shift the last two O images next to C (same PBC structure)")
    args = ap.parse_args()

    atoms = read(args.cif)
    syms = atoms.get_chemical_symbols()
    uniq = []
    for s in syms:
        if s not in uniq:
            uniq.append(s)
    for s in uniq:
        if s not in PSEUDO:
            raise SystemExit("no pseudopotential for %s" % s)

    lines = []
    lines.append("&CONTROL")
    lines.append("  calculation = '%s'" % args.mode)
    lines.append("  prefix = '%s'" % args.prefix)
    lines.append("  outdir = '%s'" % args.outdir)
    lines.append("  pseudo_dir = '%s'" % args.pseudo_dir)
    lines.append("  verbosity = 'high'")
    lines.append("  disk_io = '%s'" % ("high" if os.environ.get("MOF_CHECKPOINT") == "1" else "low"))
    if args.mode == "relax":
        lines.append("  forc_conv_thr = %.1e" % args.forc_conv_thr)
        lines.append("  etot_conv_thr = %.1e" % args.etot_conv_thr)
        lines.append("  nstep = %d" % args.nstep)
    lines.append("/")
    lines.append("&SYSTEM")
    lines.append("  ibrav = 0")
    lines.append("  nat = %d" % len(atoms))
    lines.append("  ntyp = %d" % len(uniq))
    lines.append("  ecutwfc = %.1f" % args.ecutwfc)
    lines.append("  ecutrho = %.1f" % args.ecutrho)
    lines.append("  occupations = 'smearing'")
    lines.append("  smearing = 'gaussian'")
    lines.append("  degauss = %.4f" % args.degauss)
    lines.append("  nspin = %d" % args.nspin)
    if args.nspin == 2:
        for i, s in enumerate(uniq, start=1):
            if s in ("Mn", "Co", "Fe", "Ni", "Cu"):
                lines.append("  starting_magnetization(%d) = 1.0" % i)
    lines.append("  vdw_corr = 'grimme-d3'")
    lines.append("  nosym = .true.")
    lines.append("  noinv = .true.")
    lines.append("/")
    lines.append("&ELECTRONS")
    lines.append("  electron_maxstep = 200")
    lines.append("  conv_thr = %.1e" % args.conv_thr)
    lines.append("  mixing_beta = %.2f" % args.mixing_beta)
    lines.append("  mixing_ndim = 8")
    lines.append("  mixing_mode = '%s'" % args.mixing_mode)
    lines.append("  diagonalization = '%s'" % args.diagonalization)
    lines.append("/")
    if args.mode == "relax":
        lines.append("&IONS")
        lines.append("  ion_dynamics = 'bfgs'")
        lines.append("/")
    lines.append("")
    lines.append("ATOMIC_SPECIES")
    for s in uniq:
        lines.append("  %-3s %9.3f  %s" % (s, MASS[s], PSEUDO[s]))
    lines.append("")
    lines.append("CELL_PARAMETERS angstrom")
    for v in atoms.cell.array:
        lines.append("  %14.9f %14.9f %14.9f" % tuple(v))
    lines.append("")
    lines.append("ATOMIC_POSITIONS crystal")
    nfix = len(atoms) - args.movable_atoms if args.fix_framework else 0
    frac = atoms.get_scaled_positions(wrap=False)
    if args.unwrap_co2 and len(atoms) >= 3:
        c = frac[-3]
        for i in (-2, -1):
            frac[i] = frac[i] - np.round(frac[i] - c)
    for i, (s, p) in enumerate(zip(syms, frac)):
        line = "  %-3s %16.10f %16.10f %16.10f" % (s, p[0], p[1], p[2])
        if args.fix_framework:
            line += "  0 0 0" if i < nfix else "  1 1 1"
        lines.append(line)
    lines.append("")
    lines.append("K_POINTS gamma")
    lines.append("")
    with open(args.out, "w") as f:
        f.write("\n".join(lines))
    print("wrote", args.out, "nat=", len(atoms), "ntyp=", len(uniq), "mode=", args.mode)

if __name__ == "__main__":
    main()
