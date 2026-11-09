#!/usr/bin/env python
"""Analyze NVT guest/MOF MD: MSD/D, guest integrity, binding, RDF, framework stability.

The guest is the last `n_guest` atoms of the trajectory, grouped into molecules of
`guest_natoms` atoms each. Both are read from summary.json:

    {"n_guest": 5, "guest_natoms": 5}          # CH4
    {"n_co2": 1}                                # old CO2 files, 3 atoms each

CH4 and CO2 are both supported; any rigid molecule works as long as its atoms are
contiguous at the end of the xyz.
"""
import argparse, json, os, csv
import numpy as np
from ase.io import read

CN_CUT = {"Mg": 2.6, "Zn": 2.8, "Zr": 2.8}
METALS = set("Li Be Na Mg Al K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi".split())

def unwrap(d, inv, cell):
    f = d @ inv
    f -= np.round(f)
    return f @ cell

def pair_dists(p, ii, jj, inv, cell):
    out = []
    for i in ii:
        d = p[jj] - p[i]
        f = d @ inv
        f -= np.round(f)
        out.append(np.linalg.norm(f @ cell, axis=1))
    return np.concatenate(out)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dt-ps", type=float, default=0.1)
    ap.add_argument("--fit-lo", type=float, default=5.0)
    ap.add_argument("--fit-hi", type=float, default=45.0)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    meta = json.load(open(os.path.join(args.dir, "summary.json")))
    frames = read(os.path.join(args.dir, "traj.xyz"), index=":")
    n = len(frames[0])
    gn = int(meta.get("guest_natoms", 5 if meta.get("guest") == "CH4" else 3))
    n_guest = int(meta.get("n_guest", gn * int(meta.get("n_co2", 1))))
    nmol = max(1, n_guest // gn)
    nco2 = nmol  # legacy name used below
    nfw = n - n_guest
    t = np.arange(len(frames))*args.dt_ps
    sym = frames[0].get_chemical_symbols()
    co2_idx = np.arange(nfw, n)
    fw_idx = np.arange(nfw)
    p0 = frames[0].get_positions()[co2_idx]
    inv = np.linalg.inv(frames[0].cell.array); cell = frames[0].cell.array
    V = abs(np.linalg.det(cell))
    h_fw = np.array([j for j in fw_idx if sym[j] == "H"])
    o_fw = np.array([j for j in fw_idx if sym[j] == "O"])
    metal_fw = np.array([j for j in fw_idx if sym[j] in METALS])
    o_co2 = np.array([i for i in co2_idx if sym[i] == "O"])
    iu = np.triu_indices(gn, 1)

    nf = len(frames)
    msd = np.zeros(nf); per = np.zeros((nf, nco2))
    mind = np.zeros(nf); nhb = np.zeros(nf, int)
    bond_dev = np.zeros(nf); intact_frac = np.zeros(nf)
    fw_disp = np.zeros(nf); min_mgo = np.zeros(nf)
    mgcn = []; prot = np.zeros(nf, int)

    def internal(g):
        rel = g - g[:, :1, :]
        rel = unwrap(rel, inv, cell)
        return np.linalg.norm(rel[:, iu[0], :] - rel[:, iu[1], :], axis=2)

    d0 = internal(p0.reshape(nmol, gn, 3))
    com0 = p0.reshape(nmol,gn,3).mean(1)
    comdisp = np.zeros((nf, nco2))

    for k, a in enumerate(frames):
        p = a.get_positions()
        d = p[co2_idx] - p0
        v = (d*d).sum(1)
        per[k] = v.reshape(nmol,gn).mean(1)
        msd[k] = v.mean()
        # min CO2-framework distance
        dcf = p[co2_idx][:,None,:] - p[fw_idx][None,:,:]
        f = dcf @ inv; f -= np.round(f)
        mind[k] = np.linalg.norm(f @ cell, axis=2).min()
        # H-bond count and proton transfer
        if len(o_co2) and len(h_fw):
            dch = p[o_co2][:,None,:] - p[h_fw][None,:,:]
            f = dch @ inv; f -= np.round(f)
            dh = np.linalg.norm(f @ cell, axis=2)
            nhb[k] = int((dh < 2.0).sum())
            for a_i, i in enumerate(o_co2):
                js = np.where(dh[a_i] < 1.2)[0]
                for jj in js:
                    j = h_fw[jj]
                    do = np.linalg.norm(unwrap(p[o_fw]-p[j], inv, cell), axis=1).min()
                    if do > 1.3: prot[k] += 1
        # guest internal geometry: deviation from the frame-0 reference
        dcur = internal(p[co2_idx].reshape(nmol, gn, 3))
        dev = np.abs(dcur - d0).max(1)
        bond_dev[k] = float(dev.max())
        intact_frac[k] = float((dev < 0.25).mean())
        # framework displacement
        fw_disp[k] = np.linalg.norm(unwrap(p[fw_idx]-frames[0].get_positions()[fw_idx], inv, cell), axis=1).mean()
        # metal coordination
        if len(metal_fw) and len(o_fw):
            dmo = p[o_fw][:,None,:] - p[metal_fw][None,:,:]
            f = dmo @ inv; f -= np.round(f)
            dm = np.linalg.norm(f @ cell, axis=2)
            mgcn.extend([int((dm[:, j] < CN_CUT.get(sym[metal_fw[j]], 2.6)).sum()) for j in range(len(metal_fw))])
            min_mgo[k] = dm.min()
        comdisp[k] = np.linalg.norm(p[co2_idx].reshape(nmol,gn,3).mean(1)-com0, axis=1)

    sel = (t >= args.fit_lo) & (t <= args.fit_hi)
    slope, intercept = np.polyfit(t[sel], msd[sel], 1)
    pred = slope*t[sel]+intercept
    r2fit = 1 - ((msd[sel]-pred)**2).sum()/max(((msd[sel]-msd[sel].mean())**2).sum(),1e-12)
    D = slope/6*1e-20/1e-12
    win = {}
    for lo, hi in [(5,20),(20,35),(35,50)]:
        s = (t >= lo) & (t <= hi)
        if s.sum() > 3:
            p = np.polyfit(t[s], msd[s], 1); pr = np.polyval(p, t[s])
            r2w = 1 - ((msd[s]-pr)**2).sum()/max(((msd[s]-msd[s].mean())**2).sum(),1e-12)
            win[f"{lo}-{hi}"] = dict(slope=float(p[0]), r2=float(r2w), dmsd=float(msd[s][-1]-msd[s][0]))
    sustained = bool(win.get("35-50",{}).get("slope",-1) > 0.05 and win.get("35-50",{}).get("r2",0) > 0.5)

    # RDF averaged over every 5th frame
    rmax = min(6.0, min(frames[0].cell.lengths())/2-0.5)
    nbins = 160
    def avg_rdf(ii, jj):
        hist = np.zeros(nbins)
        for a in frames[::5]:
            rs = pair_dists(a.get_positions(), ii, jj, inv, cell)
            h, _ = np.histogram(rs, bins=nbins, range=(0, rmax))
            hist += h
        r = (np.arange(nbins)+0.5)*rmax/nbins; dr = rmax/nbins
        norm = len(ii)*len(jj)*4*np.pi*r*r*dr/V*len(frames[::5])
        return r, hist/np.maximum(norm,1e-12)
    r_omg, g_omg = avg_rdf(o_fw, metal_fw) if len(metal_fw) else (None, None)
    r_oo, g_oo = avg_rdf(o_fw, o_fw)
    r_oh, g_oh = avg_rdf(o_fw, h_fw) if len(h_fw) else (None, None)

    def first_peak(r, g, lo, hi):
        if r is None: return None
        m = (r > lo) & (r < hi)
        if not m.any(): return None
        i = np.argmax(g[m]); return [float(r[m][i]), float(g[m][i])]
    def cn(r, g, cut, el):
        if r is None: return None
        m = r <= cut
        return float(np.trapz(g[m]*4*np.pi*r[m]**2, r[m]) * (sym[:nfw].count(el))/V)

    bound = mind < 3.5
    def longest(mask):
        best = cur = 0
        for b in mask:
            cur = cur+1 if b else 0
            best = max(best, cur)
        return best*args.dt_ps
    res = dict(
        dir=args.dir, n_atoms=n, n_guest=n_guest, guest_natoms=gn, n_molecules=nmol,
        n_co2=nco2, n_framework=nfw,
        time_ps=float(t[-1]), n_frames=nf,
        msd_final=float(msd[-1]), msd_max=float(msd.max()),
        D_m2_s=float(D), fit_r2=float(r2fit), msd_slope_A2_ps=float(slope),
        msd_windows=win, sustained_diffusion=sustained,
        msd_at={str(x): float(np.interp(x,t,msd)) for x in [1,2,5,10,20,30,40,50] if x <= t[-1]},
        min_dist_mean=float(mind.mean()), min_dist_min=float(mind.min()), min_dist_max=float(mind.max()),
        frac_bound=float(bound.mean()), longest_bound_ps=float(longest(bound)),
        longest_free_ps=float(longest(~bound)),
        hbond_mean=float(nhb.mean()), hbond_max=int(nhb.max()),
        proton_transfer_frames=int((prot>0).sum()),
        guest_intact_frac=float(intact_frac.mean()),
        guest_bond_dev_max=float(bond_dev.max()),
        co2_intact_frac=float(intact_frac.mean()) if gn == 3 else None,
        fw_disp_mean_final=float(fw_disp[-1]), fw_disp_max=float(fw_disp.max()),
        metal_cn_mean=float(np.mean(mgcn)) if mgcn else None, metal_cn_std=float(np.std(mgcn)) if mgcn else None,
        metal_cn_hist={str(k): int(mgcn.count(k)) for k in sorted(set(mgcn))} if mgcn else {},
        min_mgo_mean=float(min_mgo.mean()), min_mgo_min=float(min_mgo.min()),
        rdf_omg_peak=first_peak(r_omg,g_omg,1.5,3.0), rdf_oo_peak=first_peak(r_oo,g_oo,2.0,4.0),
        rdf_oh_peak=first_peak(r_oh,g_oh,1.2,2.5),
        cn_ometal=cn(r_omg,g_omg,2.8,"O"), cn_oh_2p0=cn(r_oh,g_oh,2.0,"H"),
        cn_cutoffs=CN_CUT,
        com_disp_mean=float(comdisp.mean()), com_disp_max=float(comdisp.max()),
        frac_near_site=float((comdisp<2.0).mean()),
        per_guest_D_m2_s=[float(np.polyfit(t[sel], per[sel,q], 1)[0]/6*1e-20/1e-12) for q in range(nmol)],
        per_guest_msd_final=[float(x) for x in per[-1]],
    )
    json.dump(res, open(os.path.join(args.out,"analysis.json"),"w"), indent=2)
    with open(os.path.join(args.out,"msd.csv"),"w",newline="") as f:
        w=csv.writer(f); w.writerow(["time_ps","msd_A2"]+[f"guest_{i+1}_A2" for i in range(nmol)])
        for k in range(nf): w.writerow([t[k],msd[k]]+list(per[k]))
    with open(os.path.join(args.out,"timeseries.csv"),"w",newline="") as f:
        w=csv.writer(f); w.writerow(["time_ps","min_dist_A","n_hbond","guest_bond_dev_A","fw_disp_A","min_mgo_A"])
        for k in range(nf): w.writerow([t[k],mind[k],nhb[k],bond_dev[k],fw_disp[k],min_mgo[k]])
    with open(os.path.join(args.out,"rdf.csv"),"w",newline="") as f:
        w=csv.writer(f); w.writerow(["r_A","g_OMg","g_OO","g_OH"])
        for i in range(nbins):
            w.writerow([r_oo[i], (g_omg[i] if g_omg is not None else ""), g_oo[i], (g_oh[i] if g_oh is not None else "")])
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        plt.figure(figsize=(5,3.5)); plt.plot(t,msd,"k-",lw=1)
        plt.plot(t[sel],pred,"r--",lw=1,label=f"fit D={D:.2e} m2/s")
        plt.xlabel("t (ps)"); plt.ylabel("MSD (A^2)"); plt.legend(); plt.tight_layout()
        plt.savefig(os.path.join(args.out,"msd.png"),dpi=150); plt.close()
        plt.figure(figsize=(5,3.5)); plt.plot(t,mind,"b-",lw=0.8); plt.axhline(3.5,color="r",ls="--",lw=0.8)
        plt.xlabel("t (ps)"); plt.ylabel("min guest-framework (A)"); plt.tight_layout()
        plt.savefig(os.path.join(args.out,"binding.png"),dpi=150); plt.close()
        plt.figure(figsize=(5,3.5))
        if g_omg is not None: plt.plot(r_omg,g_omg,label="O-metal")
        plt.plot(r_oo,g_oo,label="O-O")
        if g_oh is not None: plt.plot(r_oh,g_oh,label="O-H")
        plt.xlabel("r (A)"); plt.ylabel("g(r)"); plt.legend(); plt.tight_layout()
        plt.savefig(os.path.join(args.out,"rdf.png"),dpi=150); plt.close()
    except Exception as e:
        print("plot fail", e)
    print(json.dumps(res, indent=2))

if __name__ == "__main__":
    main()