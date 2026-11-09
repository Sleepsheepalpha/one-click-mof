#!/usr/bin/env python
"""Generic adsorbate site screening on a MOF with uMOF-MH.

Usage:
  screen_adsorbate_mace.py --cif mof.cif --adsorbate CH4 --out screen
  screen_adsorbate_mace.py --cif mof.cif --adsorbate custom --adsorbate-file mol.xyz --out screen
"""
import os, csv, argparse, warnings
warnings.filterwarnings("ignore")
import numpy as np
from ase import Atoms
from ase.io import read, write
from ase.optimize import BFGS
from ase.constraints import FixAtoms, FixBondLengths
from ase.neighborlist import neighbor_list, natural_cutoffs
from mace.calculators import MACECalculator

DEFAULT_MODEL = "/home/sleep-sheep/mof_calculation/models/umof/umof_models/uMOF-MH.model"


def random_rotation_matrix(rng):
    q = rng.normal(size=4)
    q /= np.linalg.norm(q)
    w, x, y, z = q
    return np.array([
        [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
        [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
        [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)],
    ])


def make_adsorbate(name, path=None):
    if path:
        mol = read(path)
        if len(mol) == 0:
            raise SystemExit("empty adsorbate file: %s" % path)
        return mol
    if name == "custom":
        raise SystemExit("--adsorbate custom requires --adsorbate-file")
    return __import__("ase.build", fromlist=["molecule"]).molecule(name)


def void_points(atoms, spacing=1.2, probe=2.2):
    from scipy.spatial import cKDTree
    cell = atoms.cell.array
    lengths = atoms.cell.lengths()
    pos = atoms.get_positions()
    reps = []
    for i in (-1, 0, 1):
        for j in (-1, 0, 1):
            for k in (-1, 0, 1):
                reps.append(pos + i*cell[0] + j*cell[1] + k*cell[2])
    tree = cKDTree(np.vstack(reps))
    grid = []
    for x in np.arange(0, lengths[0], spacing):
        for y in np.arange(0, lengths[1], spacing):
            for z in np.arange(0, lengths[2], spacing):
                p = np.array([x, y, z])
                d, _ = tree.query(p)
                if d > probe:
                    grid.append(p)
    return np.array(grid)


def internal_bonds(mol):
    cut = np.array(natural_cutoffs(mol, mult=1.15))
    i, j = neighbor_list("ij", mol, cut)
    bonds = []
    for a, b in zip(i, j):
        if a < b:
            bonds.append((int(a), int(b)))
    return bonds


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cif", required=True)
    ap.add_argument("--adsorbate", default="CH4", help="CO2, CH4, C2H6, C6H6, or custom")
    ap.add_argument("--adsorbate-file", default="", help="XYZ file for custom, or override built-in")
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-sites", type=int, default=24)
    ap.add_argument("--seed", type=int, default=20261024)
    ap.add_argument("--spacing", type=float, default=1.2)
    ap.add_argument("--probe", type=float, default=2.2)
    ap.add_argument("--min-fw", type=float, default=0.0,
                    help="reject optimized sites whose molecule-framework distance is below this (A)")
    ap.add_argument("--fmax", type=float, default=0.05)
    ap.add_argument("--maxstep", type=float, default=0.1)
    ap.add_argument("--steps", type=int, default=150)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--head", default="r2scan+d4")
    ap.add_argument("--dtype", default="float64")
    ap.add_argument("--device", default="cuda")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    rng = np.random.default_rng(args.seed)

    mof = read(args.cif)
    n = len(mof)
    mol = make_adsorbate(args.adsorbate, args.adsorbate_file or None)
    m = len(mol)
    bonds = internal_bonds(mol)
    print("%s: framework=%d adsorbate=%s atoms=%d bonds=%d void_points..." % (
        args.cif, n, args.adsorbate, m, len(bonds)), flush=True)

    calc = MACECalculator(model_paths=args.model, device=args.device, default_dtype=args.dtype, head=args.head)
    mof.calc = calc
    e_mof = float(mof.get_potential_energy())

    ref = mol.copy()
    ref.set_cell([20, 20, 20])
    ref.center()
    ref.set_pbc(True)
    ref.calc = calc
    e_ref = float(ref.get_potential_energy())

    pts = void_points(mof, spacing=args.spacing, probe=args.probe)
    print("void_points=%d" % len(pts), flush=True)
    if len(pts) == 0:
        raise SystemExit("no void points")

    idx = rng.choice(len(pts), size=min(args.n_sites, len(pts)), replace=False)
    rows = []
    for k, ii in enumerate(idx):
        center = pts[ii]
        m2 = mol.copy()
        m2.positions = m2.positions @ random_rotation_matrix(rng).T
        m2.translate(center - m2.get_center_of_mass())
        at = mof.copy()
        at += m2
        at.calc = calc
        cons = [FixAtoms(mask=[True]*n + [False]*m)]
        if bonds:
            cons.append(FixBondLengths([(n+a, n+b) for a, b in bonds]))
        at.set_constraint(cons)
        d = at.get_all_distances(mic=True)
        if d[n:, :n].min() < 1.6:
            continue
        opt = BFGS(at, logfile=os.path.join(args.out, "opt_%02d.log" % k), trajectory=None, maxstep=args.maxstep)
        try:
            opt.run(fmax=args.fmax, steps=args.steps)
        except Exception as exc:
            print("OPT FAIL", k, exc, flush=True)
            continue
        e = float(at.get_potential_energy())
        fmax = float(np.abs(at.get_forces()[-m:]).max())
        dm = at.get_all_distances(mic=True)
        min_fw = float(dm[n:, :n].min())
        dmm = dm[n:, n:].copy()
        np.fill_diagonal(dmm, np.inf)
        min_mol = float(dmm.min())
        dev = 0.0
        for a, b in bonds:
            r0 = np.linalg.norm(mol.positions[a] - mol.positions[b])
            r1 = np.linalg.norm(at.positions[n+a] - at.positions[n+b])
            dev = max(dev, abs(r1 - r0) / max(r0, 1e-6))
        intact = (dev < 0.20) and (min_mol > 0.7) and (min_fw >= args.min_fw)
        eads = e - e_mof - e_ref
        rows.append(dict(site=k, e_total=e, e_ads=eads, fmax_mol=fmax,
                         min_mol_framework=min_fw, min_mol=min_mol,
                         bond_max_dev=dev, intact=int(intact),
                         cx=center[0], cy=center[1], cz=center[2],
                         adsorbate=args.adsorbate))
        write(os.path.join(args.out, "site_%02d.cif" % k), at)
        print("site %02d E_ads=%+.4f eV Fmax=%.3f min_fw=%.2f dev=%.2f intact=%s" % (
            k, eads, fmax, min_fw, dev, intact), flush=True)

    if not rows:
        raise SystemExit("no valid sites")
    rows.sort(key=lambda r: (0 if r["intact"] else 1, r["e_ads"]))
    with open(os.path.join(args.out, "screen.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    if rows[0]["intact"]:
        write(os.path.join(args.out, "best.cif"), read(os.path.join(args.out, "site_%02d.cif" % rows[0]["site"])))
        print("BEST intact E_ads=%+.4f eV site=%d" % (rows[0]["e_ads"], rows[0]["site"]), flush=True)
    else:
        print("NO INTACT SITE", flush=True)


if __name__ == "__main__":
    main()
