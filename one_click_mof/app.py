#!/usr/bin/env python3
"""One-Click MOF：一个最小、单机、无第三方 Web 依赖的本地工具链界面。

原名 MOF 工具台；旧版备份在 ../mof_ui_backup_2026-11-06/。

启动：
    python3 one_click_mof/app.py
然后浏览器打开 http://127.0.0.1:8765

设计原则：
- 只绑定 127.0.0.1，不暴露公网；
- 工具由 manifests/*.json 声明，界面按参数自动生成表单；
- 每个任务在独立目录运行，保留输入、日志、命令和解析结果；
- 不提供任意 shell 输入框。
"""
import argparse
import csv
import json
import mimetypes
import markdown
import os
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote
from urllib.request import urlopen

__version__ = "0.1.0"

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
MANIFEST_DIR = ROOT / "manifests"
STATIC_DIR = ROOT / "static"
TUTORIAL_DIR = ROOT / "tutorial"
DATA_DIR = ROOT / "data"
RUN_ROOT = ROOT / "runs"
DB_PATH = DATA_DIR / "one_click_mof.sqlite3"
SETTINGS_PATH = DATA_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "python": str(PROJECT_ROOT / ".venv_mace" / "bin" / "python"),
    "pw": "/usr/bin/pw.x",
    "mpiexec": "/usr/bin/mpiexec",
    "pseudo_dir": str(PROJECT_ROOT / "pseudo_sssp"),
    "mace_model": str(PROJECT_ROOT / "models" / "umof" / "umof_models" / "uMOF-MH.model"),
    "vesta": shutil.which("vesta") or "/usr/local/bin/vesta",
    "avogadro": shutil.which("avogadro") or shutil.which("avogadro2") or "",
    "raspa2": shutil.which("raspa2") or "",
    "zeopp": shutil.which("zeo++") or shutil.which("zeopp") or "",
    "work_root": str(RUN_ROOT),
    "default_np": 6,
    "default_device": "cuda",
}


TOOL_SPECS = [
    {"id": "python", "label": "Python 环境", "key": "python", "pick": "file", "detect": "python", "exec": True,
     "download": {"kind": "file", "url": "https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-Linux-x86_64.sh",
                  "name": "Miniconda3-latest-Linux-x86_64.sh", "source": "TUNA 清华镜像"}},
    {"id": "pw", "label": "Quantum ESPRESSO (pw.x)", "key": "pw", "pick": "file", "detect": "pw", "exec": True,
     "download": {"kind": "page", "url": "https://mirrors.tuna.tsinghua.edu.cn/help/ubuntu/", "source": "TUNA Ubuntu 镜像"}},
    {"id": "mpiexec", "label": "MPI (mpiexec)", "key": "mpiexec", "pick": "file", "detect": "mpiexec", "exec": True,
     "download": {"kind": "page", "url": "https://mirrors.tuna.tsinghua.edu.cn/help/ubuntu/", "source": "TUNA Ubuntu 镜像"}},
    {"id": "pseudo_dir", "label": "SSSP 赝势目录", "key": "pseudo_dir", "pick": "dir", "detect": "pseudo", "exec": False,
     "download": {"kind": "page", "url": "https://www.materialscloud.org/discover/sssp/table/efficiency", "source": "Materials Cloud SSSP"}},
    {"id": "mace_model", "label": "MACE 模型文件", "key": "mace_model", "pick": "file", "detect": "mace", "exec": False,
     "download": {"kind": "page", "url": "https://doi.org/10.6084/m9.figshare.33311829", "source": "uMOF Figshare"}},
    {"id": "vesta", "label": "VESTA（结构可视化）", "key": "vesta", "pick": "file", "detect": "vesta", "exec": True,
     "download": {"kind": "page", "url": "https://jp-minerals.org/vesta/en/download.html", "source": "VESTA 官网"}},
    {"id": "avogadro", "label": "Avogadro（分子编辑，可选）", "key": "avogadro", "pick": "file", "detect": "avogadro", "exec": True, "optional": True,
     "download": {"kind": "page", "url": "https://avogadro.cc/", "source": "Avogadro 官网"}},
    {"id": "raspa2", "label": "RASPA2（GCMC，可选）", "key": "raspa2", "pick": "file", "detect": "raspa2", "exec": True, "optional": True,
     "download": {"kind": "page", "url": "https://github.com/iraspa/raspa2", "source": "RASPA2 GitHub"}},
    {"id": "zeopp", "label": "Zeo++（孔结构，可选）", "key": "zeopp", "pick": "file", "detect": "zeo", "exec": True, "optional": True,
     "download": {"kind": "page", "url": "http://www.zeoplusplus.org/download.html", "source": "Zeo++ 官网"}},
    {"id": "work_root", "label": "运行目录", "key": "work_root", "pick": "dir", "detect": "work", "exec": False,
     "download": None},
]

LOCK = threading.RLock()
PICK_LOCK = threading.Lock()
CURRENT = {"job_id": None, "proc": None}
CANCELLED = set()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def connect():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            input_dir TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            input_rel TEXT NOT NULL,
            tool_id TEXT NOT NULL,
            params TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            workdir TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            error TEXT,
            metrics TEXT
        );
        """)
        con.commit()
        have = {row[1] for row in con.execute("PRAGMA table_info(jobs)")}
        for col, ddl in [
            ("output_root", "TEXT"),
            ("position", "INTEGER DEFAULT 0"),
            ("checkpoint", "INTEGER DEFAULT 0"),
            ("resume_from", "TEXT"),
        ]:
            if col not in have:
                con.execute(f"ALTER TABLE jobs ADD COLUMN {col} {ddl}")
        con.commit()


def load_settings():
    s = dict(DEFAULT_SETTINGS)
    if SETTINGS_PATH.exists():
        try:
            s.update(json.loads(SETTINGS_PATH.read_text()))
        except Exception:
            pass
    return s


def save_settings(s):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")


SYSTEM_CACHE = {"ts": 0.0, "data": None}


def system_info():
    """Detect the local GPU/RAM/CPU, cached for 30 seconds."""
    now_ts = time.time()
    if SYSTEM_CACHE["data"] is not None and now_ts - SYSTEM_CACHE["ts"] < 30:
        return SYSTEM_CACHE["data"]
    gpu_name = None
    vram_gb = None
    gpu_score = 0
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=4,
        )
        line = (out.stdout or "").strip().splitlines()[0] if (out.stdout or "").strip() else ""
        if line:
            parts = [x.strip() for x in line.split(",")]
            gpu_name = parts[0]
            m = re.search(r"RTX\s*(\d{4})", gpu_name, re.I)
            if m:
                gpu_score = int(m.group(1))
            if len(parts) > 1:
                mm = re.search(r"(\d+)", parts[1])
                if mm:
                    vram_gb = round(int(mm.group(1)) / 1024.0, 1)
    except Exception:
        pass
    ram_gb = 0.0
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                ram_gb = round(int(line.split()[1]) / 1024.0 / 1024.0, 1)
                break
    except Exception:
        pass
    cpu_count = os.cpu_count() or 1
    gpu_ok = gpu_score >= 3060
    data = {
        "gpu_name": gpu_name,
        "vram_gb": vram_gb,
        "gpu_score": gpu_score,
        "gpu_ok": gpu_ok,
        "ram_gb": ram_gb,
        "cpu_count": cpu_count,
        "reference_ok": bool(gpu_ok and ram_gb >= 16),
        "reference": "RTX 3060+ / 16 GB RAM / 6 MPI",
    }
    SYSTEM_CACHE.update({"ts": now_ts, "data": data})
    return data


def disk_info(path):
    p = Path(os.path.abspath(os.path.expanduser(str(path))))
    while not p.exists() and p != p.parent:
        p = p.parent
    try:
        u = shutil.disk_usage(str(p))
        return {"path": str(p), "free_gb": round(u.free / 1e9, 2), "total_gb": round(u.total / 1e9, 2)}
    except Exception as e:
        return {"path": str(p), "error": str(e)}


def load_manifests():
    out = []
    for p in sorted(MANIFEST_DIR.glob("*.json")):
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
            m["_file"] = str(p)
            out.append(m)
        except Exception as e:
            print("manifest error", p, e)
    out.sort(key=lambda m: (m.get("order", 999), m.get("name", "")))
    return out


def manifest_map():
    return {m["id"]: m for m in load_manifests()}


def _coerce(value, spec):
    t = spec.get("type", "str")
    if t == "int":
        v = int(value)
    elif t == "float":
        v = float(value)
    elif t == "bool":
        if isinstance(value, str):
            v = value.lower() in ("1", "true", "yes", "on")
        else:
            v = bool(value)
    else:
        v = str(value)
    if t in ("int", "float"):
        if "min" in spec and v < spec["min"]:
            raise ValueError(f"{spec['key']} 不能小于 {spec['min']}")
        if "max" in spec and v > spec["max"]:
            raise ValueError(f"{spec['key']} 不能大于 {spec['max']}")
    return v


def resolve_params(manifest, overrides):
    params = {}
    specs = {p["key"]: p for p in manifest.get("params", [])}
    for key, spec in specs.items():
        params[key] = _coerce(spec.get("default"), spec) if spec.get("default") is not None else None
    for key, value in (overrides or {}).items():
        if key not in specs:
            continue
        if value is None or value == "":
            continue
        params[key] = _coerce(value, specs[key])
    return params


def subst(value, ctx):
    if not isinstance(value, str):
        return value
    try:
        return value.format_map(ctx)
    except KeyError as e:
        raise RuntimeError(f"命令模板缺少参数：{e}") from e


def tail(text, n=4000):
    return text[-n:]


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

def parse_qe(text):
    def last(pattern, cast=float):
        m = re.findall(pattern, text)
        return cast(m[-1]) if m else None
    metrics = {}
    e = re.findall(r"!\s+total energy\s+=\s+(-?\d+\.\d+)\s+Ry", text)
    if e:
        metrics["total_energy_Ry"] = float(e[-1])
        metrics["total_energy_eV"] = float(e[-1]) * 13.605693122994
    fe = re.findall(r"Final energy\s+=\s+(-?\d+\.\d+)\s+Ry", text)
    if fe:
        metrics["final_energy_Ry"] = float(fe[-1])
    acc = re.findall(r"estimated scf accuracy\s*<\s*([0-9.eE+-]+)", text)
    if acc:
        metrics["scf_accuracy_Ry"] = float(acc[-1])
    tf = re.findall(r"Total force\s+=\s+([0-9.eE+-]+)", text)
    if tf:
        metrics["total_force"] = float(tf[-1])
    metrics["scf_converged"] = "convergence has been achieved" in text
    metrics["job_done"] = "JOB DONE" in text
    metrics["bfgs_converged"] = ("bfgs converged" in text) or ("End of BFGS" in text)
    m = re.findall(r"number of scf cycles\s*=\s*(\d+)", text)
    if m:
        metrics["n_scf_cycles"] = int(m[-1])
    m = re.findall(r"bfgs converged in\s+\d+ scf cycles and\s+(\d+) bfgs steps", text)
    if m:
        metrics["n_bfgs_steps"] = int(m[-1])
    else:
        m = re.findall(r"number of bfgs steps\s*=\s*(\d+)", text)
        if m:
            metrics["n_bfgs_steps"] = int(m[-1])
    return metrics


def parse_mace_screen(csv_path):
    if not csv_path.exists():
        raise RuntimeError("没有找到 screen.csv")
    rows = list(csv.DictReader(csv_path.open(newline="")))
    if not rows:
        raise RuntimeError("screen.csv 为空")
    def f(row, key):
        try:
            return float(row.get(key, ""))
        except Exception:
            return None
    intact = [r for r in rows if str(r.get("intact", "0")) in ("1", "True", "true")]
    best = min(intact or rows, key=lambda r: f(r, "e_ads") if f(r, "e_ads") is not None else 1e9)
    vals = [f(r, "e_ads") for r in rows if f(r, "e_ads") is not None]
    return {
        "n_sites": len(rows),
        "n_intact": len(intact),
        "best_site": int(float(best.get("site", -1))),
        "best_eads_eV": f(best, "e_ads"),
        "best_fmax_co2": f(best, "fmax_co2") if f(best, "fmax_co2") is not None else f(best, "fmax_mol"),
        "best_min_co2_framework_A": f(best, "min_co2_framework") if f(best, "min_co2_framework") is not None else f(best, "min_mol_framework"),
        "mean_eads_eV": round(sum(vals) / len(vals), 6) if vals else None,
        "min_eads_eV": round(min(vals), 6) if vals else None,
    }


def parse_md(json_path):
    data = json.loads(json_path.read_text())
    keys = [
        "n_atoms", "n_co2", "time_ps", "msd_final", "D_m2_s", "fit_r2",
        "sustained_diffusion", "frac_bound", "longest_bound_ps", "longest_free_ps",
        "co2_intact_frac", "min_mgo_min", "metal_cn_mean", "fw_disp_max",
        "frac_near_site", "com_disp_max",
    ]
    return {k: data.get(k) for k in keys if k in data}


def parse_structure(json_path):
    data = json.loads(json_path.read_text())
    out = {}
    for k in ("natoms", "formula", "volume_A3", "density_g_cm3", "min_distance_A",
              "n_short_contacts", "n_uncoordinated_O"):
        if k in data:
            out[k] = data[k]
    if data.get("metal_counts"):
        out["metals"] = ",".join(f"{k}{v}" for k, v in data["metal_counts"].items())
    return out


def parse_convert(json_path):
    data = json.loads(json_path.read_text())
    keys = [
        "natoms_input", "natoms_output", "formula", "mode", "fix_framework",
        "primitive", "spacegroup", "ecutwfc_Ry", "ecutrho_Ry", "degauss_Ry",
        "conv_thr_Ry", "forc_conv_thr_Ry_au", "nspin", "nstep",
    ]
    return {k: data.get(k) for k in keys if k in data}


def parse_same_cell_ref(json_path):
    data = json.loads(json_path.read_text())
    keys = [
        "n_total", "n_mol", "formula", "cell_a_A", "cell_b_A", "cell_c_A",
        "alpha_deg", "beta_deg", "gamma_deg", "cell_volume_A3", "max_roundtrip_error_A",
    ]
    return {k: data.get(k) for k in keys if k in data}


def parse_outputs(manifest, workdir):
    parser = manifest.get("parser")
    if parser == "qe":
        candidates = [workdir / "qe.out", workdir / "run.log"]
        text = ""
        for p in candidates:
            if p.exists():
                text = p.read_text(errors="replace")
                if "total energy" in text or "JOB DONE" in text:
                    break
        return parse_qe(text)
    if parser == "mace_screen":
        return parse_mace_screen(workdir / "screen" / "screen.csv")
    if parser == "md":
        return parse_md(workdir / "md" / "analysis.json")
    if parser == "structure_check":
        return parse_structure(workdir / "structure_check.json")
    if parser == "same_cell_ref":
        return parse_same_cell_ref(workdir / "same_cell_ref.json")
    if parser == "convert":
        return parse_convert(workdir / "convert_info.json")
    return {}


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def update_job(job_id, **fields):
    if not fields:
        return
    keys = ", ".join(f"{k}=?" for k in fields)
    with connect() as con:
        con.execute(f"UPDATE jobs SET {keys} WHERE id=?", list(fields.values()) + [job_id])
        con.commit()


CACHE_DIR_NAMES = {"tmp", "__pycache__", ".cache", ".mypy_cache", ".pytest_cache"}
CACHE_FILE_PATTERNS = ("*.wfc*", "*.mix*", "*.igk*", "*.rho", "*.pot", "*.res", "*.tmp", "*.part", "*.bak", "*.old")


def _job_output_path(job):
    """Return the task directory only when it is exactly inside the output root
    the user chose for this job.  Never fall back to the current global setting:
    a job may have been created with a custom tool/file output directory."""
    raw = job.get("workdir")
    root = job.get("output_root")
    if not raw or not root:
        return None, "任务没有记录 workdir 或 output_root"
    try:
        p = Path(str(raw)).expanduser().resolve()
        r = Path(str(root)).expanduser().resolve()
    except Exception as exc:
        return None, f"路径无法解析：{exc}"
    if p == r or r not in p.parents:
        return None, f"任务目录不在它自己的输出目录内：{p}"
    if p.parent.name != f"project_{job['project_id']}" or not p.name.startswith(f"job_{job['id']}_"):
        return None, f"任务目录不符合 job_{job['id']}_* 规则：{p}"
    return p, ""


def _cache_match(name):
    import fnmatch
    return any(fnmatch.fnmatch(name, pat) for pat in CACHE_FILE_PATTERNS)


def clear_job_cache(path):
    """Remove restart/wavefunction scratch from a job directory, keeping the
    log, metrics, copied input and final outputs."""
    removed = 0
    errors = []
    for child in path.iterdir():
        try:
            if child.is_symlink():
                if _cache_match(child.name):
                    child.unlink()
                    removed += 1
                continue
            if child.is_dir() and (child.name in CACHE_DIR_NAMES or child.name.endswith(".save")):
                shutil.rmtree(child)
                removed += 1
            elif child.is_file() and _cache_match(child.name):
                child.unlink()
                removed += 1
        except Exception as exc:
            errors.append(f"{child}: {exc}")
    return removed, errors


def delete_job_records(ids, clear_cache=False, clear_outputs=False):
    """Delete job records and optionally their own cache/output directories.

    The path check uses each job's stored output_root, so custom per-tool or
    per-file output directories are respected.  Running jobs are never removed.
    """
    ids = sorted({int(x) for x in ids})
    if not ids:
        return {"ok": True, "deleted": [], "skipped": [], "errors": [],
                "cache_removed": 0, "outputs_removed": 0}
    marks = ",".join("?" for _ in ids)
    deleted, skipped, errors = [], [], []
    cache_removed = outputs_removed = 0
    with connect() as con:
        rows = con.execute(f"SELECT * FROM jobs WHERE id IN ({marks})", ids).fetchall()
        found = {int(r["id"]): r for r in rows}
        for jid in ids:
            row = found.get(jid)
            if not row:
                skipped.append({"id": jid, "reason": "记录不存在"})
                continue
            job = dict(row)
            if job["status"] in ("running", "cancelling"):
                skipped.append({"id": jid, "reason": "任务正在运行，请先终止"})
                continue
            if clear_cache or clear_outputs:
                p, reason = _job_output_path(job)
                if reason:
                    errors.append({"id": jid, "reason": reason})
                    continue
                try:
                    if clear_outputs:
                        if p.exists():
                            if p.is_symlink() or not p.is_dir():
                                errors.append({"id": jid, "reason": f"任务目录不是普通目录：{p}"})
                                continue
                            shutil.rmtree(p)
                            outputs_removed += 1
                        # Remove only an empty project_<id> parent, never anything else.
                        try:
                            p.parent.rmdir()
                        except OSError:
                            pass
                    elif clear_cache and p.exists():
                        n, errs = clear_job_cache(p)
                        cache_removed += n
                        errors.extend({"id": jid, "reason": x} for x in errs)
                        if errs:
                            continue
                except Exception as exc:
                    errors.append({"id": jid, "reason": f"清理文件失败：{exc}"})
                    continue
            con.execute("DELETE FROM jobs WHERE id=?", (jid,))
            deleted.append(jid)
        con.commit()
    return {"ok": True, "deleted": deleted, "skipped": skipped, "errors": errors,
            "cache_removed": cache_removed, "outputs_removed": outputs_removed}


def claim_next():
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY position, id LIMIT 1").fetchone()
        if row:
            con.execute("UPDATE jobs SET status='running', started_at=? WHERE id=?", (now(), row["id"]))
            con.commit()
            return dict(row)
        con.commit()
    return None


def patch_qe_control(text, key, value):
    """Insert or replace a &CONTROL namelist entry in a QE input."""
    line = f"  {key} = {value}"
    if re.search(rf"^\s*{re.escape(key)}\s*=", text, re.M):
        return re.sub(rf"^\s*{re.escape(key)}\s*=.*$", line, text, count=1, flags=re.M)
    if "&CONTROL" in text:
        return text.replace("&CONTROL", "&CONTROL\n" + line, 1)
    return text


def run_job(job):
    job_id = job["id"]
    manifest = manifest_map().get(job["tool_id"])
    if not manifest:
        update_job(job_id, status="failed", error=f"工具清单不存在：{job['tool_id']}", finished_at=now())
        return
    work_root = Path(job.get("output_root") or load_settings()["work_root"])
    workdir = work_root / f"project_{job['project_id']}" / f"job_{job_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "input").mkdir(exist_ok=True)
    with connect() as con:
        project = con.execute("SELECT * FROM projects WHERE id=?", (job["project_id"],)).fetchone()
    if not project:
        update_job(job_id, status="failed", error="项目不存在", finished_at=now())
        return
    src = Path(project["input_dir"]) / job["input_rel"]
    if not src.exists():
        update_job(job_id, status="failed", error=f"输入文件不存在：{src}", finished_at=now())
        return
    dst = workdir / "input" / src.name
    shutil.copy2(src, dst)
    params = json.loads(job["params"])
    settings = load_settings()
    ctx = {
        "input": str(dst),
        "input_name": dst.name,
        "input_dir": str(dst.parent),
        "source_dir": str(src.parent),
        "workdir": str(workdir),
        "outdir": str(workdir),
        "scripts": str(PROJECT_ROOT),
        "app": str(ROOT),
        "python": settings["python"],
        "pw": settings["pw"],
        "mpiexec": settings["mpiexec"],
        "pseudo_dir": settings["pseudo_dir"],
        "mace_model": settings["mace_model"],
    }
    # manifest defaults first, so jobs queued before a new param was added still run
    for p in (manifest or {}).get("params", []):
        ctx.setdefault(p["key"], p.get("default"))
    ctx.update({k: v for k, v in params.items() if v is not None})
    checkpoint = bool(job.get("checkpoint"))
    resume_from = job.get("resume_from")
    steps = manifest.get("steps", [])
    if resume_from:
        old = Path(str(resume_from))
        if not old.exists():
            update_job(job_id, status="failed", error=f"保存点目录不存在：{old}", finished_at=now())
            return
        old_tmp = old / "tmp"
        if old_tmp.exists():
            shutil.copytree(str(old_tmp), str(workdir / "tmp"), dirs_exist_ok=True)
        old_mof = old / "mof.in"
        old_input = old / "input" / Path(job["input_rel"]).name
        source = old_mof if old_mof.exists() else old_input
        if not source.exists():
            update_job(job_id, status="failed", error="保存点里找不到 mof.in 或原始输入", finished_at=now())
            return
        text = source.read_text(errors="replace")
        text = patch_qe_control(text, "restart_mode", "'restart'")
        text = patch_qe_control(text, "disk_io", "'high'")
        resume_in = workdir / "input" / "resume.in"
        resume_in.write_text(text)
        ctx["input"] = str(resume_in)
        ctx["input_name"] = "resume.in"
        np = str(params.get("np", 6))
        npool = str(params.get("npool", 1))
        steps = [{
            "cmd": ["{mpiexec}", "-np", np, "{pw}", "-nk", npool, "-in", "{input}"],
            "stdout": "{workdir}/qe.out",
        }]
    elif checkpoint and manifest["id"] == "qe_from_in":
        text = dst.read_text(errors="replace")
        text = patch_qe_control(text, "disk_io", "'high'")
        cp = workdir / "input" / ("checkpoint_" + dst.name)
        cp.write_text(text)
        ctx["input"] = str(cp)
        ctx["input_name"] = cp.name
    log_path = workdir / "run.log"
    job_meta = {
        "job_id": job_id,
        "tool": manifest["id"] if manifest else job["tool_id"],
        "input": str(src),
        "copied_input": str(dst),
        "params": params,
        "settings": settings,
        "started_at": now(),
        "workdir": str(workdir),
        "output_root": str(work_root),
        "checkpoint": checkpoint,
        "resume_from": resume_from,
    }
    (workdir / "job.json").write_text(json.dumps(job_meta, indent=2, ensure_ascii=False))
    update_job(job_id, workdir=str(workdir))
    try:
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"# {now()}  {manifest['name'] if manifest else job['tool_id']}\n")
            log.write(f"# input: {src}\n")
            log.write(f"# params: {json.dumps(params, ensure_ascii=False)}\n\n")
            for idx, step in enumerate(steps, 1):
                if job_id in CANCELLED:
                    raise RuntimeError("用户取消")
                cmd = [subst(x, ctx) for x in step["cmd"]]
                cwd = subst(step.get("cwd", "{workdir}"), ctx)
                env = os.environ.copy()
                env.update({"OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
                if checkpoint:
                    env["MOF_CHECKPOINT"] = "1"
                for k, v in (step.get("env") or {}).items():
                    env[str(k)] = str(subst(v, ctx))
                log.write(f"\n## step {idx}: {' '.join(cmd)}\n")
                log.write(f"## cwd: {cwd}\n")
                log.flush()
                out_target = step.get("stdout")
                if out_target:
                    out_path = Path(subst(out_target, ctx))
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    fh = out_path.open("a", encoding="utf-8")
                else:
                    fh = log
                with LOCK:
                    CURRENT["job_id"] = job_id
                    proc = subprocess.Popen(
                        cmd, cwd=cwd, stdout=fh, stderr=subprocess.STDOUT,
                        env=env, start_new_session=True, text=True,
                    )
                    CURRENT["proc"] = proc
                rc = proc.wait()
                with LOCK:
                    CURRENT["job_id"] = None
                    CURRENT["proc"] = None
                if out_target:
                    fh.close()
                log.write(f"\n## step {idx} exit={rc}\n")
                log.flush()
                if rc != 0 and not step.get("allow_fail"):
                    raise RuntimeError(f"第 {idx} 步失败，退出码 {rc}")
                if job_id in CANCELLED:
                    raise RuntimeError("用户取消")
        metrics = parse_outputs(manifest, workdir)
        (workdir / "metrics.json").write_text(json.dumps(metrics, indent=2, ensure_ascii=False))
        update_job(job_id, status="done", finished_at=now(), metrics=json.dumps(metrics, ensure_ascii=False))
    except Exception as e:
        msg = str(e)
        with log_path.open("a", encoding="utf-8") as log:
            log.write(f"\n!! {msg}\n")
            log.write(traceback.format_exc())
        status = "cancelled" if job_id in CANCELLED or msg == "用户取消" else "failed"
        update_job(job_id, status=status, finished_at=now(), error=msg)
    finally:
        CANCELLED.discard(job_id)
        with LOCK:
            CURRENT["job_id"] = None
            CURRENT["proc"] = None


def worker():
    while True:
        try:
            job = claim_next()
            if job:
                run_job(job)
            else:
                time.sleep(1.0)
        except Exception:
            traceback.print_exc()
            time.sleep(2.0)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def scan_files(project, recursive=True):
    root = Path(project["input_dir"])
    if not root.exists():
        return []
    manifests = load_manifests()
    exts = sorted({e.lower() for m in manifests for e in m.get("accepts", [])})
    found = []
    it = root.rglob("*") if recursive else root.glob("*")
    for p in it:
        if not p.is_file() or p.name.startswith("."):
            continue
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        try:
            if ROOT.resolve() in p.resolve().parents:
                continue
        except Exception:
            pass
        if exts and p.suffix.lower() not in exts:
            continue
        rel = str(p.relative_to(root))
        item = {"rel": rel, "name": p.name, "size": p.stat().st_size, "suffix": p.suffix.lower()}
        if p.suffix.lower() == ".cif":
            try:
                from ase.io import read
                a = read(str(p))
                item["natoms"] = len(a)
                item["formula"] = a.get_chemical_formula()
            except Exception as e:
                item["error"] = str(e)[:200]
        elif p.suffix.lower() in (".in", ".pwi"):
            try:
                text = p.read_text(errors="replace")[:200000]
                m = re.search(r"\bnat\s*=\s*(\d+)", text, re.I)
                if m:
                    item["natoms"] = int(m.group(1))
                m = re.search(r"calculation\s*=\s*['\"]([A-Za-z_]+)", text, re.I)
                item["formula"] = "QE " + (m.group(1) if m else "input")
                item["calculation"] = (m.group(1).lower() if m else "scf")
                m = re.search(r"\bnstep\s*=\s*(\d+)", text, re.I)
                if m:
                    item["nstep"] = int(m.group(1))
            except Exception as e:
                item["error"] = str(e)[:200]
        elif p.suffix.lower() == ".xyz":
            try:
                with p.open(errors="replace") as fh:
                    item["natoms"] = int(fh.readline().strip())
                item["formula"] = "XYZ"
            except Exception as e:
                item["error"] = str(e)[:200]
        with connect() as con:
            row = con.execute(
                "SELECT id,status,finished_at FROM jobs WHERE project_id=? AND input_rel=? ORDER BY id DESC LIMIT 1",
                (project["id"], rel),
            ).fetchone()
        item["last_job"] = dict(row) if row else None
        found.append(item)
        if len(found) >= 2000:
            break
    found.sort(key=lambda x: x["rel"])
    return found



def _tool_version(spec, path):
    if not path:
        return "未设置"
    fp = Path(path)
    if not fp.exists():
        return "未找到"
    tid = spec["id"]
    try:
        if tid == "python":
            out = subprocess.run([path, "-c", "import sys; print(sys.version.split()[0])"], capture_output=True, text=True, timeout=4)
            return ("Python " + (out.stdout or "").strip()) if out.returncode == 0 else "已找到（版本未知）"
        if tid == "pw":
            # pw.x has no non-running --version flag; -h prints the banner and exits.
            out = subprocess.run([path, "-h"], capture_output=True, text=True, timeout=4)
            m = re.search(r"v\.([0-9][^\s]*)", (out.stdout or "") + (out.stderr or ""))
            return ("QE " + m.group(1)) if m else "已找到（版本未知）"
        if tid == "mpiexec":
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=6)
            line = ((out.stdout or "") + (out.stderr or "")).strip().splitlines()
            return line[0][:80] if line else "已找到（版本未知）"
        if tid == "pseudo_dir":
            n = len(list(fp.glob("*.UPF"))) + len(list(fp.glob("*.upf")))
            return "SSSP · %d 个 UPF" % n if n else "目录存在（未发现 UPF）"
        if tid == "mace_model":
            return "%s · %.1f MB" % (fp.name, fp.stat().st_size / 1e6)
        if tid in ("vesta", "avogadro"):
            return "已找到（GUI）"
        if tid == "raspa2":
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            line = ((out.stdout or "") + (out.stderr or "")).strip().splitlines()
            return line[0][:80] if line else "已找到"
        if tid == "zeopp":
            return "已找到 · %s" % fp.name
        if tid == "work_root":
            u = shutil.disk_usage(str(fp))
            return "可用 %.1f GB" % (u.free / 1e9)
    except Exception:
        return "已找到（版本未知）"
    return "已找到"


def tool_cards():
    s = load_settings()
    items = []
    for spec in TOOL_SPECS:
        path = s.get(spec["key"], "")
        exists = bool(path) and Path(path).exists()
        items.append({
            "id": spec["id"], "label": spec["label"], "key": spec["key"],
            "pick": spec.get("pick", "file"), "path": path, "exists": exists,
            "version": _tool_version(spec, path) if exists else "未找到",
            "download": bool(spec.get("download")),
            "optional": bool(spec.get("optional")),
            "source": (spec.get("download") or {}).get("source", ""),
        })
    return {"items": items, "settings": s}


def detect_tool(spec):
    s = load_settings()
    key = spec["key"]
    tid = spec["detect"]
    candidates = []
    if tid == "python":
        candidates = [str(PROJECT_ROOT / ".venv_mace" / "bin" / "python"), sys.executable, shutil.which("python3") or ""]
    elif tid == "pw":
        candidates = ["/usr/bin/pw.x", shutil.which("pw.x") or ""]
    elif tid == "mpiexec":
        candidates = ["/usr/bin/mpiexec", shutil.which("mpiexec") or ""]
    elif tid == "pseudo":
        candidates = [str(PROJECT_ROOT / "pseudo_sssp"), str(PROJECT_ROOT / "pseudo")]
    elif tid == "mace":
        candidates = [str(PROJECT_ROOT / "models" / "umof" / "umof_models" / "uMOF-MH.model"),
                      str(PROJECT_ROOT / "models" / "mace-mof-0" / "v2" / "mofs_v2.model")]
    elif tid == "vesta":
        candidates = [s.get("vesta", ""), shutil.which("vesta") or "", "/usr/local/bin/vesta", "/usr/bin/vesta"]
    elif tid == "avogadro":
        candidates = [s.get("avogadro", ""), shutil.which("avogadro") or "", shutil.which("avogadro2") or ""]
    elif tid == "raspa2":
        candidates = [s.get("raspa2", ""), shutil.which("raspa2") or ""]
    elif tid == "zeo":
        candidates = [s.get("zeopp", ""), shutil.which("zeo++") or "", shutil.which("zeopp") or ""]
    elif tid == "work":
        candidates = [str(ROOT / "runs"), str(PROJECT_ROOT / "runs")]
    for c in candidates:
        if c and Path(c).exists():
            s[key] = c
            save_settings(s)
            return s[key]
    return ""


def download_tool(spec):
    dl = spec.get("download")
    if not dl:
        return {"ok": False, "message": "该工具不需要下载，请用自动检测或更改路径。"}
    if dl.get("kind") == "page":
        return {"ok": True, "url": dl["url"], "message": "已打开%s，请在页面里下载/安装。" % dl.get("source", "下载页")}
    name = dl.get("name") or (spec["id"] + ".download")
    dest = DATA_DIR / "downloads" / name
    dest.parent.mkdir(parents=True, exist_ok=True)

    def worker():
        try:
            with urlopen(dl["url"], timeout=30) as r, open(dest, "wb") as f:
                while True:
                    chunk = r.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
        except Exception as exc:
            print("download failed", spec["id"], exc, flush=True)

    threading.Thread(target=worker, daemon=True).start()
    return {"ok": True, "message": "已开始从%s下载 %s；完成后在 downloads/ 里选择。" % (dl.get("source", "镜像"), name), "path": str(dest)}

def tutorial_files():
    files = []
    for fp in sorted(TUTORIAL_DIR.glob("*.md")):
        title = fp.stem
        try:
            for line in fp.read_text(errors="ignore").splitlines():
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
        except Exception:
            pass
        files.append({"name": fp.name, "title": title})
    files.sort(key=lambda x: (0 if x["name"] == "README.md" else 1, x["name"]))
    return files


def safe_tutorial_path(rel):
    if not rel:
        raise ValueError("empty path")
    fp = (TUTORIAL_DIR / rel).resolve()
    base = TUTORIAL_DIR.resolve()
    if fp != base and base not in fp.parents:
        raise ValueError("path outside tutorial")
    return fp


class Handler(BaseHTTPRequestHandler):
    server_version = "One-Click-MOF/" + __version__

    def log_message(self, fmt, *args):
        if args and str(args[0]).startswith("GET /api/jobs"):
            return
        super().log_message(fmt, *args)

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self):
        n = int(self.headers.get("Content-Length", "0") or 0)
        if not n:
            return {}
        return json.loads(self.rfile.read(n).decode())

    def _project(self, pid):
        with connect() as con:
            return con.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()

    def do_GET(self):
        try:
            u = urlparse(self.path)
            path = u.path
            q = parse_qs(u.query)
            if path == "/":
                return self._static("index.html")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):])
            if path == "/api/tutorial":
                try:
                    name = q.get("file", ["README.md"])[0]
                    if not re.fullmatch(r"[0-9A-Za-z_.-]+\.md", name):
                        return self._send(400, {"error": "invalid tutorial name"})
                    fp = safe_tutorial_path(name)
                    text = fp.read_text(errors="ignore")
                    html = markdown.markdown(text, extensions=["tables", "fenced_code", "sane_lists"])
                    html = re.sub(
                        r'src="([^"]+)"',
                        lambda m: m.group(0) if m.group(1).startswith(("http://", "https://", "/")) else 'src="/api/tutorial/asset?path=' + quote(m.group(1)) + '"',
                        html,
                    )
                    return self._send(200, {"files": tutorial_files(), "name": name, "html": html})
                except Exception as exc:
                    return self._send(404, {"error": str(exc)})
            if path == "/api/tutorial/asset":
                try:
                    rel = q.get("path", [""])[0]
                    fp = safe_tutorial_path(rel)
                    if not fp.is_file():
                        return self._send(404, {"error": "asset not found"})
                    ctype = mimetypes.guess_type(str(fp))[0] or "application/octet-stream"
                    return self._send(200, fp.read_bytes(), ctype)
                except Exception as exc:
                    return self._send(403, {"error": str(exc)})
            if path == "/api/tools":
                return self._send(200, tool_cards())
            if path == "/api/system":
                return self._send(200, system_info())
            if path == "/api/disk":
                target = q.get("path", [load_settings()["work_root"]])[0]
                return self._send(200, disk_info(target))
            if path == "/api/settings":
                return self._send(200, load_settings())
            if path == "/api/manifests":
                return self._send(200, load_manifests())
            if path == "/api/projects":
                with connect() as con:
                    rows = con.execute("SELECT * FROM projects ORDER BY id DESC").fetchall()
                return self._send(200, [dict(r) for r in rows])
            if path == "/api/projects/scan":
                pid = int(q.get("id", ["0"])[0])
                p = self._project(pid)
                if not p:
                    return self._send(404, {"error": "项目不存在"})
                return self._send(200, scan_files(p, recursive=q.get("recursive", ["1"])[0] != "0"))
            if path == "/api/jobs":
                pid = q.get("project_id", [None])[0]
                with connect() as con:
                    if pid:
                        rows = con.execute("SELECT * FROM jobs WHERE project_id=? ORDER BY id DESC LIMIT 500", (int(pid),)).fetchall()
                    else:
                        rows = con.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT 500").fetchall()
                out = []
                for r in rows:
                    d = dict(r)
                    d["params"] = json.loads(d["params"])
                    d["metrics"] = json.loads(d["metrics"]) if d.get("metrics") else {}
                    out.append(d)
                def queue_key(d):
                    st = d["status"]
                    if st == "staged":
                        return (0, d.get("position", 0), d["id"])
                    if st in ("queued", "running", "cancelling"):
                        return (1, d.get("position", 0), d["id"])
                    return (2, -d["id"], d["id"])
                out.sort(key=queue_key)
                return self._send(200, out)
            m = re.match(r"^/api/jobs/(\d+)/log$", path)
            if m:
                jid = int(m.group(1))
                with connect() as con:
                    row = con.execute("SELECT workdir,status,error FROM jobs WHERE id=?", (jid,)).fetchone()
                if not row:
                    return self._send(404, {"error": "任务不存在"})
                text = ""
                if row["workdir"]:
                    p = Path(row["workdir"]) / "run.log"
                    if p.exists():
                        text = p.read_text(errors="replace")
                return self._send(200, {"log": tail(text), "status": row["status"], "error": row["error"]})
            m = re.match(r"^/api/jobs/(\d+)$", path)
            if m:
                jid = int(m.group(1))
                with connect() as con:
                    row = con.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
                if not row:
                    return self._send(404, {"error": "任务不存在"})
                d = dict(row); d["params"] = json.loads(d["params"]); d["metrics"] = json.loads(d["metrics"]) if d.get("metrics") else {}
                return self._send(200, d)
            if path == "/api/results":
                pid = q.get("project_id", [None])[0]
                with connect() as con:
                    sql = "SELECT * FROM jobs WHERE status IN ('done','failed','cancelled')"
                    args = []
                    if pid:
                        sql += " AND project_id=?"
                        args.append(int(pid))
                    sql += " ORDER BY id DESC LIMIT 1000"
                    rows = con.execute(sql, args).fetchall()
                out = []
                for r in rows:
                    d = dict(r)
                    d["params"] = json.loads(d["params"])
                    d["metrics"] = json.loads(d["metrics"]) if d.get("metrics") else {}
                    out.append(d)
                return self._send(200, out)
            return self._send(404, {"error": "not found"})
        except Exception as e:
            traceback.print_exc()
            return self._send(500, {"error": str(e)})

    def do_POST(self):
        try:
            u = urlparse(self.path)
            path = u.path
            body = self._json()
            if path == "/api/tools/detect":
                spec = next((x for x in TOOL_SPECS if x["id"] == body.get("id")), None)
                if not spec:
                    return self._send(404, {"error": "未知工具"})
                found = detect_tool(spec)
                if not found:
                    return self._send(404, {"error": "没有自动找到；请手动选择路径"})
                item = next((x for x in tool_cards()["items"] if x["id"] == spec["id"]), None)
                return self._send(200, {"path": found, "item": item, "message": "已自动检测并保存"})
            if path == "/api/tools/download":
                spec = next((x for x in TOOL_SPECS if x["id"] == body.get("id")), None)
                if not spec:
                    return self._send(404, {"error": "未知工具"})
                return self._send(200, download_tool(spec))
            if path == "/api/settings":
                s = load_settings()
                for k in DEFAULT_SETTINGS:
                    if k in body:
                        s[k] = body[k]
                s["default_np"] = int(s.get("default_np", 6))
                save_settings(s)
                return self._send(200, s)
            if path == "/api/settings/test":
                s = load_settings()
                results = []
                def check(label, p, executable=False, optional=False):
                    p = str(p or "")
                    ok = bool(p) and Path(p).exists()
                    if executable:
                        ok = ok and os.access(p, os.X_OK)
                    results.append({"label": label, "path": p, "ok": ok, "optional": optional})
                for spec in TOOL_SPECS:
                    check(spec["label"], s.get(spec["key"], ""), bool(spec.get("exec")), bool(spec.get("optional")))
                return self._send(200, {"results": results})
            if path == "/api/pick-path":
                kind = str(body.get("kind", "dir"))
                if kind not in ("file", "dir"):
                    return self._send(400, {"error": "kind 只能是 file 或 dir"})
                if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
                    return self._send(400, {"error": "当前服务没有图形显示（DISPLAY/WAYLAND_DISPLAY 为空），无法打开系统对话框；请直接粘贴路径。"})
                zenity = shutil.which("zenity")
                if not zenity:
                    return self._send(400, {"error": "系统里没有 zenity，无法打开文件夹选择框；请直接粘贴路径，或安装 zenity。"})
                title = str(body.get("title") or ("选择文件夹" if kind == "dir" else "选择文件"))
                cmd = [zenity, "--file-selection", "--title", title]
                if kind == "dir":
                    cmd.append("--directory")
                try:
                    with PICK_LOCK:
                        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                except subprocess.TimeoutExpired:
                    return self._send(408, {"error": "选择框等待超时，请重试。"})
                if proc.returncode != 0:
                    return self._send(200, {"cancelled": True})
                picked = (proc.stdout or "").strip().splitlines()
                if not picked:
                    return self._send(200, {"cancelled": True})
                return self._send(200, {"path": os.path.abspath(os.path.expanduser(picked[0]))})
            if path == "/api/open-path":
                target = str(body.get("path", "")).strip()
                if not target or not Path(target).exists():
                    return self._send(400, {"error": "路径不存在"})
                xdg = shutil.which("xdg-open")
                if not xdg:
                    return self._send(400, {"error": "系统里没有 xdg-open"})
                subprocess.Popen([xdg, target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return self._send(200, {"ok": True})
            if path == "/api/projects":
                name = str(body.get("name", "")).strip()
                input_dir = str(body.get("input_dir", "")).strip()
                if not name or not input_dir:
                    return self._send(400, {"error": "需要项目名和输入目录"})
                if not Path(input_dir).is_dir():
                    return self._send(400, {"error": f"目录不存在：{input_dir}"})
                with connect() as con:
                    cur = con.execute("INSERT INTO projects(name,input_dir,created_at) VALUES(?,?,?)", (name, input_dir, now()))
                    con.commit()
                    pid = cur.lastrowid
                return self._send(200, {"id": pid, "name": name, "input_dir": input_dir})
            if path == "/api/jobs/delete":
                raw_ids = body.get("ids") or []
                try:
                    ids = [int(x) for x in raw_ids]
                except (TypeError, ValueError):
                    return self._send(400, {"error": "ids 必须是任务编号"})
                return self._send(200, delete_job_records(
                    ids,
                    clear_cache=bool(body.get("clear_cache")),
                    clear_outputs=bool(body.get("clear_outputs")),
                ))
            if path == "/api/jobs":
                pid = int(body["project_id"])
                tool_id = str(body["tool_id"])
                manifest = manifest_map().get(tool_id)
                if not manifest:
                    return self._send(400, {"error": "工具不存在"})
                files = body.get("files") or []
                if not files:
                    return self._send(400, {"error": "没有选择文件"})
                p = self._project(pid)
                if not p:
                    return self._send(404, {"error": "项目不存在"})
                root = Path(p["input_dir"]).resolve()
                settings = load_settings()
                output_dir = os.path.abspath(os.path.expanduser(str(body.get("output_dir") or settings["work_root"])))
                out_root = Path(output_dir)
                try:
                    out_root.mkdir(parents=True, exist_ok=True)
                except Exception as e:
                    return self._send(400, {"error": f"输出目录不可用：{e}"})
                if not out_root.is_dir():
                    return self._send(400, {"error": f"输出目录不是文件夹：{output_dir}"})
                if not os.access(str(out_root), os.W_OK):
                    return self._send(400, {"error": f"输出目录不可写：{output_dir}"})
                checkpoint = 1 if body.get("checkpoint") else 0
                created = []
                for rel in files:
                    src = (root / rel).resolve()
                    if root not in src.parents and src != root:
                        return self._send(400, {"error": f"文件越界：{rel}"})
                    if not src.exists():
                        return self._send(400, {"error": f"文件不存在：{rel}"})
                    if manifest.get("accepts") and src.suffix.lower() not in [x.lower() for x in manifest["accepts"]]:
                        continue
                    try:
                        params = resolve_params(manifest, body.get("params") or {})
                    except Exception as e:
                        return self._send(400, {"error": str(e)})
                    with connect() as con:
                        pos = con.execute("SELECT COALESCE(MAX(position),0)+1 FROM jobs").fetchone()[0]
                        cur = con.execute(
                            "INSERT INTO jobs(project_id,input_rel,tool_id,params,status,output_root,position,checkpoint,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                            (pid, rel, tool_id, json.dumps(params, ensure_ascii=False), "staged", output_dir, pos, checkpoint, now()),
                        )
                        con.commit()
                        created.append(cur.lastrowid)
                return self._send(200, {"created": created, "status": "staged"})
            if path == "/api/queue/start":
                pid = body.get("project_id")
                with connect() as con:
                    if pid:
                        cur = con.execute("UPDATE jobs SET status='queued' WHERE status='staged' AND project_id=?", (int(pid),))
                    else:
                        cur = con.execute("UPDATE jobs SET status='queued' WHERE status='staged'")
                    con.commit()
                    n = cur.rowcount
                return self._send(200, {"started": n})
            m = re.match(r"^/api/jobs/(\d+)/move$", path)
            if m:
                jid = int(m.group(1))
                direction = str(body.get("direction", "up"))
                if direction not in ("up", "down"):
                    return self._send(400, {"error": "direction 只能是 up 或 down"})
                with connect() as con:
                    row = con.execute("SELECT id,status,position,project_id FROM jobs WHERE id=?", (jid,)).fetchone()
                    if not row:
                        return self._send(404, {"error": "任务不存在"})
                    if row["status"] != "staged":
                        return self._send(400, {"error": "只有“待启动”的任务可以调整顺序"})
                    if direction == "up":
                        other = con.execute(
                            "SELECT id,position FROM jobs WHERE status='staged' AND project_id=? AND (position < ? OR (position = ? AND id < ?)) ORDER BY position DESC, id DESC LIMIT 1",
                            (row["project_id"], row["position"], row["position"], jid),
                        ).fetchone()
                    else:
                        other = con.execute(
                            "SELECT id,position FROM jobs WHERE status='staged' AND project_id=? AND (position > ? OR (position = ? AND id > ?)) ORDER BY position ASC, id ASC LIMIT 1",
                            (row["project_id"], row["position"], row["position"], jid),
                        ).fetchone()
                    if other:
                        con.execute("UPDATE jobs SET position=? WHERE id=?", (other["position"], jid))
                        con.execute("UPDATE jobs SET position=? WHERE id=?", (row["position"], other["id"]))
                        con.commit()
                return self._send(200, {"ok": True})
            m = re.match(r"^/api/jobs/(\d+)/resume$", path)
            if m:
                jid = int(m.group(1))
                with connect() as con:
                    row = con.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
                    if not row:
                        return self._send(404, {"error": "任务不存在"})
                    if not row["checkpoint"]:
                        return self._send(400, {"error": "这个任务没有开启保存点"})
                    if not row["workdir"] or not Path(row["workdir"]).exists():
                        return self._send(400, {"error": "找不到上一次的任务目录，无法继续"})
                    pos = con.execute("SELECT COALESCE(MAX(position),0)+1 FROM jobs").fetchone()[0]
                    cur = con.execute(
                        "INSERT INTO jobs(project_id,input_rel,tool_id,params,status,output_root,position,checkpoint,resume_from,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (row["project_id"], row["input_rel"], row["tool_id"], row["params"], "staged",
                         row["output_root"], pos, 1, row["workdir"], now()),
                    )
                    con.commit()
                    new_id = cur.lastrowid
                return self._send(200, {"id": new_id, "resume_from": row["workdir"]})
            m = re.match(r"^/api/jobs/(\d+)/cancel$", path)
            if m:
                jid = int(m.group(1))
                CANCELLED.add(jid)
                with connect() as con:
                    row = con.execute("SELECT status FROM jobs WHERE id=?", (jid,)).fetchone()
                    if not row:
                        return self._send(404, {"error": "任务不存在"})
                    if row["status"] in ("staged", "queued"):
                        con.execute("UPDATE jobs SET status='cancelled', finished_at=? WHERE id=?", (now(), jid))
                        con.commit()
                        return self._send(200, {"ok": True, "status": "cancelled"})
                with LOCK:
                    proc = CURRENT["proc"] if CURRENT["job_id"] == jid else None
                if proc and proc.poll() is None:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                    except Exception:
                        proc.terminate()
                with connect() as con:
                    con.execute("UPDATE jobs SET status='cancelling' WHERE id=? AND status='running'", (jid,))
                    con.commit()
                return self._send(200, {"ok": True, "status": "cancelling"})
            m = re.match(r"^/api/jobs/(\d+)/rerun$", path)
            if m:
                jid = int(m.group(1))
                with connect() as con:
                    row = con.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
                    if not row:
                        return self._send(404, {"error": "任务不存在"})
                    pos = con.execute("SELECT COALESCE(MAX(position),0)+1 FROM jobs").fetchone()[0]
                    cur = con.execute(
                        "INSERT INTO jobs(project_id,input_rel,tool_id,params,status,output_root,position,checkpoint,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                        (row["project_id"], row["input_rel"], row["tool_id"], row["params"], "staged",
                         row["output_root"], pos, row["checkpoint"], now()),
                    )
                    con.commit()
                    return self._send(200, {"id": cur.lastrowid})
            return self._send(404, {"error": "not found"})
        except json.JSONDecodeError:
            return self._send(400, {"error": "请求 JSON 格式错误"})
        except Exception as e:
            traceback.print_exc()
            return self._send(500, {"error": str(e)})

    def do_DELETE(self):
        try:
            u = urlparse(self.path)
            m = re.match(r"^/api/projects/(\d+)$", u.path)
            if m:
                pid = int(m.group(1))
                with connect() as con:
                    con.execute("DELETE FROM projects WHERE id=?", (pid,))
                    con.execute("DELETE FROM jobs WHERE project_id=?", (pid,))
                    con.commit()
                return self._send(200, {"ok": True})
            return self._send(404, {"error": "not found"})
        except Exception as e:
            return self._send(500, {"error": str(e)})

    def _static(self, rel):
        p = (STATIC_DIR / rel).resolve()
        if STATIC_DIR.resolve() not in p.parents and p != STATIC_DIR.resolve():
            return self._send(403, {"error": "forbidden"})
        if not p.exists() or not p.is_file():
            return self._send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self._send(200, p.read_bytes(), ctype)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    init_db()
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"MOF 工具台: http://{args.host}:{args.port}")
    print(f"数据库: {DB_PATH}")
    print(f"运行目录: {load_settings()['work_root']}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
