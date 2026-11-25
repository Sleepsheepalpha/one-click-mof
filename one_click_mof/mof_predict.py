"""Scaffolding helpers for the MOF crystal predictor workspace.

This module only prepares model/checkpoint discovery, run directories and the
artifact contract.  The actual inference and CIF conversion adapters can be
added without changing the web API or the UI.
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path

MODEL_SUFFIXES = (".ckpt", ".pt", ".pth", ".safetensors")
CHECKPOINT_SUFFIXES = MODEL_SUFFIXES
MAX_SCAN_DEPTH = 8


def _project_root():
    return Path(__file__).resolve().parent.parent


def _candidate_model_roots():
    home = Path.home()
    return [
        home / "mofreinf_venv" / "lib" / "python3.10" / "site-packages" / "mofreinforce" / "model",
        home / "mofreinf_venv" / "lib" / "python3.11" / "site-packages" / "mofreinforce" / "model",
        home / "MOFreinforce" / "mofreinforce" / "model",
        _project_root() / "models",
    ]


def _candidate_checkpoint_roots():
    home = Path.home()
    return [
        home / "mofreinf_venv" / "lib" / "python3.10" / "site-packages" / "mofreinforce" / "reinforce" / "logs",
        home / "MOFreinforce" / "mofreinforce" / "reinforce" / "logs",
        home / "mofreinf_venv" / "lib" / "python3.11" / "site-packages" / "mofreinforce" / "reinforce" / "logs",
    ]


def _first_existing(candidates):
    for p in candidates:
        if p.exists():
            return str(p)
    return str(candidates[0])


def default_model_root():
    return _first_existing(_candidate_model_roots())


def default_checkpoint_root():
    return _first_existing(_candidate_checkpoint_roots())


def _walk_files(root, suffixes, max_depth=MAX_SCAN_DEPTH):
    root = Path(root).expanduser()
    if not root.exists():
        return []
    if root.is_file():
        return [root] if root.suffix.lower() in suffixes else []
    found = []
    base_depth = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).parts) - base_depth
        if depth >= max_depth:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in ("__pycache__",)]
        for name in filenames:
            if name.startswith("."):
                continue
            if Path(name).suffix.lower() in suffixes:
                found.append(Path(dirpath) / name)
    return found


def _step_fields(path):
    text = str(path)
    step = None
    epoch = None
    mm = re.search(r"step[=_-](\d+)", text, re.I)
    if mm:
        step = int(mm.group(1))
    mm = re.search(r"epoch[=_-](\d+)", text, re.I)
    if mm:
        epoch = int(mm.group(1))
    if step is None:
        mm = re.search(r"iteration[=_-](\d+)", text, re.I)
        if mm:
            step = int(mm.group(1))
    return step, epoch


def _kind(path):
    text = str(path).lower()
    name = Path(path).name.lower()
    if "predictor" in name or "/predictor/" in text:
        return "predictor"
    if "generator" in name or "/generator/" in text:
        return "generator"
    if "reinforce" in text or "/logs/" in text:
        return "reinforce"
    return "model"


def _target(path):
    text = Path(path).name.lower()
    for key in ("selectivity", "qkh", "co2", "h2o"):
        if key in text:
            return key
    return ""


def _item(path, root=None):
    p = Path(path).resolve()
    try:
        st = p.stat()
    except OSError:
        return None
    step, epoch = _step_fields(p)
    return {
        "name": p.name,
        "label": p.stem,
        "path": str(p),
        "root": str(root) if root else "",
        "kind": _kind(p),
        "target": _target(p),
        "step": step,
        "epoch": epoch,
        "size": int(st.st_size),
        "mtime": int(st.st_mtime),
        "is_checkpoint": "checkpoint" in str(p).lower() or step is not None or epoch is not None,
    }


def scan_models(settings):
    roots = []
    candidates = [settings.get("predict_model_root")] + [str(p) for p in _candidate_model_roots()]
    for raw in candidates:
        if not raw:
            continue
        p = Path(raw).expanduser()
        if p.exists() and str(p) not in roots:
            roots.append(str(p))
    items = []
    seen = set()
    for root in roots:
        for path in _walk_files(root, MODEL_SUFFIXES):
            try:
                key = str(path.resolve())
            except OSError:
                continue
            if key in seen:
                continue
            seen.add(key)
            item = _item(path, root)
            if item:
                items.append(item)
    items.sort(key=lambda x: (0 if x["kind"] == "predictor" else 1, x["kind"], x["label"].lower()))
    return {"roots": roots, "items": items[:300], "total": len(items)}


def scan_checkpoints(path, limit=300):
    raw = str(path or "").strip()
    if not raw:
        raise ValueError("请填写保存点目录")
    root = Path(raw).expanduser()
    if not root.exists():
        raise ValueError("保存点路径不存在：" + str(root))
    items = []
    seen = set()
    for path in _walk_files(root, CHECKPOINT_SUFFIXES):
        try:
            key = str(path.resolve())
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        item = _item(path, root)
        if item:
            items.append(item)
    items.sort(key=lambda x: (x["mtime"], x["size"]), reverse=True)
    return {
        "path": str(root.resolve()),
        "items": items[:limit],
        "total": len(items),
    }


def _slug(text):
    text = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(text or "")).strip("._")
    return (text or "prediction")[:48]


def prepare_run(run_id, spec, base_dir):
    base = Path(base_dir or "").expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    slug = _slug(spec.get("name"))
    run_dir = base / ("%04d_%s" % (int(run_id), slug))
    suffix = 2
    while run_dir.exists():
        run_dir = base / ("%04d_%s_%d" % (int(run_id), slug, suffix))
        suffix += 1
    (run_dir / "checkpoints").mkdir(parents=True)
    (run_dir / "logs").mkdir(parents=True)
    (run_dir / "output").mkdir(parents=True)

    created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    record = {
        "schema": "mof-predictor-framework/0.1",
        "id": int(run_id),
        "name": spec.get("name") or "prediction",
        "created_at": created,
        "status": "configured",
        "stage": "configured",
        "location": spec.get("location") or "local",
        "model": {
            "path": spec.get("model_path") or "",
            "name": Path(spec.get("model_path") or "").name,
        },
        "target": spec.get("target") or "",
        "preference": spec.get("preference"),
        "echos": int(spec.get("echos") or 30),
        "input_path": spec.get("input_path") or "",
        "save_dir": str(run_dir),
        "resume_from": spec.get("resume_from") or "",
        "checkpoint_dir": str(run_dir / "checkpoints"),
        "output_dir": str(run_dir / "output"),
        "executor": {
            "status": "not_connected",
            "note": "本地推理适配器尚未接入；接入后写入 logs/run.log 与 output/。",
        },
        "conversion": {
            "status": "not_connected",
            "note": "checkpoint → CIF 转换适配器尚未接入。",
        },
    }
    (run_dir / "run.json").write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / "README.md").write_text(
        "# MOF prediction run scaffold\n\n"
        "- run.json: frozen configuration for this run.\n"
        "- checkpoints/: resumed or newly produced checkpoints.\n"
        "- logs/run.log: executor log contract.\n"
        "- output/: raw inference output.\n"
        "- output/cif/: converted CIF files (conversion adapter).\n\n"
        "The web UI only prepares this directory for now; connect the local "
        "inference and conversion adapters to fill the artifacts.\n",
        encoding="utf-8",
    )
    return record


def scan_artifacts(run_dir):
    root = Path(run_dir).expanduser() if run_dir else None
    cifs = []
    jsons = []
    checkpoints = []
    if root and root.exists():
        cifs = sorted(_walk_files(root, (".cif",), 8))
        jsons = sorted(_walk_files(root / "output", (".json",), 6))
        checkpoints = sorted(_walk_files(root / "checkpoints", CHECKPOINT_SUFFIXES, 6),
                             key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return {
        "run_dir": str(root) if root else "",
        "cif_count": len(cifs),
        "json_count": len(jsons),
        "checkpoint_count": len(checkpoints),
        "cif_preview": [{"name": p.name, "path": str(p), "size": p.stat().st_size} for p in cifs[:40]],
        "json_preview": [{"name": p.name, "path": str(p), "size": p.stat().st_size} for p in jsons[:40]],
        "checkpoint_preview": [
            {"name": p.name, "path": str(p), "size": p.stat().st_size}
            for p in checkpoints[:40]
        ],
    }
