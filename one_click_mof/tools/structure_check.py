#!/usr/bin/env python
"""Basic MOF structure audit used by the local web UI.

This is deliberately conservative: it reports numbers, it does not decide
whether a structure is "good".
"""
import argparse, json, math
import numpy as np
from ase.io import read
from ase.data import covalent_radii, atomic_numbers

METALS = set("Li Be Na Mg Al K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi".split())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cif", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    atoms = read(args.cif)
    syms = atoms.get_chemical_symbols()
    n = len(atoms)
    cell = atoms.cell.array
    vol = abs(float(np.linalg.det(cell)))
    d = atoms.get_all_distances(mic=True)
    np.fill_diagonal(d, 99.0)
    min_dist = float(d.min()) if n > 1 else None
    # short contacts: closer than 0.8 * sum of covalent radii
    z = [atomic_numbers[s] for s in syms]
    r = np.array([covalent_radii[i] for i in z])
    limit = 0.8 * (r[:, None] + r[None, :])
    short = np.argwhere((d < limit) & (np.triu(np.ones((n, n), dtype=bool), 1)))
    short_list = []
    for i, j in short[:20]:
        short_list.append({"i": int(i), "j": int(j), "elements": [syms[i], syms[j]], "d": round(float(d[i, j]), 3)})
    # metal-oxygen coordination, cutoff by metal
    cut = {"Zn": 2.6, "Mg": 2.6, "Zr": 2.8, "Co": 2.4, "Mn": 2.4}
    metal_idx = [i for i, s in enumerate(syms) if s in METALS]
    o_idx = [i for i, s in enumerate(syms) if s == "O"]
    cn = {}
    for i in metal_idx:
        c = cut.get(syms[i], 2.6)
        cn.setdefault(syms[i], []).append(int((d[i, o_idx] < c).sum()))
    cn_summary = {k: {"mean": round(float(np.mean(v)), 2), "min": int(min(v)), "max": int(max(v)), "n": len(v)} for k, v in cn.items()}
    # composition
    from collections import Counter
    comp = dict(sorted(Counter(syms).items()))
    formula = "".join(f"{k}{v}" for k, v in comp.items())
    res = {
        "natoms": n,
        "formula": formula,
        "composition": comp,
        "volume_A3": round(vol, 3),
        "density_g_cm3": round(float(atoms.get_masses().sum() / 0.602214076 / vol), 4) if vol else None,
        "min_distance_A": round(min_dist, 3) if min_dist is not None else None,
        "n_short_contacts": int(len(short)),
        "short_contacts": short_list,
        "metal_counts": {k: syms.count(k) for k in sorted(set(syms) & METALS)},
        "metal_oxygen_cn": cn_summary,
        "n_uncoordinated_O": int(sum(1 for j in o_idx if all(d[i, j] > cut.get(syms[i], 2.6) for i in metal_idx))) if metal_idx else None,
    }
    with open(args.out, "w") as f:
        json.dump(res, f, indent=2, ensure_ascii=False)
    print(json.dumps(res, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
