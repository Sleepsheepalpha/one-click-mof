#!/usr/bin/env python
"""Build a same-cell / same-position reference from a complex CIF.

The reference is the molecule exactly as it sits in the complex: same cell,
same fractional coordinates, only the framework atoms removed.  This is the
only reliable way to get a QE reference energy that cancels in

    E_ads = E_complex - E_bare - E_ref

A separate large box (20 A) does NOT work: QE total energies depend on the cell
and on the molecule position, and the shift does not cancel.

Usage
-----
  python tools/make_same_cell_ref.py --complex CH4_site03.cif --n-mol 5 --out CH4_ref.cif

  # or let it guess from the formula difference against the bare framework
  python tools/make_same_cell_ref.py --complex CH4_site03.cif --framework-natoms 106 --out CH4_ref.cif
"""
import argparse
import json
from pathlib import Path

from ase import Atoms
from ase.io import read, write


def build(complex_cif, n_mol):
    a = read(complex_cif)
    if not 0 < n_mol < len(a):
        raise SystemExit("n_mol=%d out of range for %d atoms" % (n_mol, len(a)))
    ref = Atoms(symbols=a.get_chemical_symbols()[-n_mol:],
                scaled_positions=a.get_scaled_positions(wrap=False)[-n_mol:],
                cell=a.cell, pbc=True)
    return a, ref


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--complex", required=True, help="complex CIF (framework first, molecule last)")
    ap.add_argument("--n-mol", type=int, default=0, help="number of molecule atoms at the tail")
    ap.add_argument("--framework-natoms", type=int, default=0,
                    help="alternative: number of framework atoms; n_mol = nat - this")
    ap.add_argument("--out", required=True)
    ap.add_argument("--info-json", default="", help="also write a small metrics JSON")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    a = read(args.complex)
    if args.n_mol:
        n_mol = args.n_mol
    elif args.framework_natoms:
        n_mol = len(a) - args.framework_natoms
    else:
        raise SystemExit("give --n-mol or --framework-natoms")

    a, ref = build(args.complex, n_mol)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    write(args.out, ref, format="cif")
    back = read(args.out)
    err = max(abs(back.get_positions() - ref.get_positions()).max(0))
    if err > 1e-4:
        raise SystemExit("CIF round-trip error too large; do not use this file")
    if not args.quiet:
        print("complex : %s (%d atoms)" % (args.complex, len(a)))
        print("molecule: %d atoms  %s" % (n_mol, ref.get_chemical_formula()))
        print("cell    : a=%.4f b=%.4f c=%.4f alpha=%.2f beta=%.2f gamma=%.2f"
              % (*ref.cell.lengths(), *ref.cell.angles()))
        print("wrote   : %s  (max CIF round-trip error %.2e A)" % (args.out, err))
    if args.info_json:
        lengths = ref.cell.lengths()
        angles = ref.cell.angles()
        info = {
            "complex": str(args.complex),
            "output": str(args.out),
            "n_total": len(a),
            "n_mol": n_mol,
            "formula": ref.get_chemical_formula(),
            "cell_a_A": float(lengths[0]),
            "cell_b_A": float(lengths[1]),
            "cell_c_A": float(lengths[2]),
            "alpha_deg": float(angles[0]),
            "beta_deg": float(angles[1]),
            "gamma_deg": float(angles[2]),
            "cell_volume_A3": float(ref.get_volume()),
            "max_roundtrip_error_A": float(err),
        }
        ip = Path(args.info_json)
        ip.parent.mkdir(parents=True, exist_ok=True)
        ip.write_text(json.dumps(info, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
