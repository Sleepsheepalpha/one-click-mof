"""SSH/Slurm helpers for the One-Click MOF HPC workspace.

Passwords are kept only in the in-memory HpcSession object.  Nothing in this
module writes credentials to disk.
"""
import base64
import hashlib
import os
import posixpath
import re
import secrets
import shlex
import shutil
import stat
import tarfile
import tempfile
import threading
import time
import uuid
from pathlib import Path

try:
    import paramiko
except ImportError:  # the local-only workspace still works without it
    paramiko = None


class HpcError(Exception):
    pass


def _fingerprint(key):
    return "SHA256:" + base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")


def _decode(data):
    if isinstance(data, bytes):
        return data.decode("utf-8", "replace")
    return data or ""


class HpcSession:
    def __init__(self, host, port, user, client, home, key):
        self.host = host
        self.port = int(port)
        self.user = user
        self.client = client
        self.home = home
        self.fingerprint = _fingerprint(key)
        self.lock = threading.RLock()
        self.created = time.time()

    def run(self, command, timeout=30):
        with self.lock:
            stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
            try:
                out = _decode(stdout.read())
                err = _decode(stderr.read())
                rc = stdout.channel.recv_exit_status()
            finally:
                try:
                    stdin.close()
                except Exception:
                    pass
        return {"rc": rc, "out": out, "err": err}

    def sftp(self):
        return self.client.open_sftp()

    def close(self):
        try:
            self.client.close()
        except Exception:
            pass


_SESSIONS = {}
_SESSIONS_LOCK = threading.RLock()


def _new_session(host, port, user, password):
    if paramiko is None:
        raise HpcError("缺少 paramiko；请在 Python 环境执行 pip install paramiko")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            host, port=int(port), username=user, password=password,
            timeout=12, banner_timeout=12, auth_timeout=12,
            look_for_keys=False, allow_agent=False,
        )
        key = client.get_transport().get_remote_server_key()
        sftp = client.open_sftp()
        try:
            home = sftp.normalize(".")
        finally:
            sftp.close()
    except Exception as exc:
        try:
            client.close()
        except Exception:
            pass
        raise HpcError("SSH 连接失败：" + str(exc))
    return HpcSession(host, port, user, client, home, key)


def test_connection(host, port, user, password):
    s = _new_session(host, port, user, password)
    try:
        r = s.run("hostname; whoami")
        return {
            "hostname": r["out"].splitlines()[0] if r["out"].splitlines() else host,
            "whoami": r["out"].splitlines()[1] if len(r["out"].splitlines()) > 1 else user,
            "home": s.home,
            "fingerprint": s.fingerprint,
        }
    finally:
        s.close()


def login(host, port, user, password):
    s = _new_session(host, port, user, password)
    token = secrets.token_urlsafe(32)
    with _SESSIONS_LOCK:
        _SESSIONS[token] = s
    return token, s


def get(token):
    with _SESSIONS_LOCK:
        s = _SESSIONS.get(token or "")
    if not s:
        raise HpcError("超算会话已失效，请重新输入密码登录")
    return s


def logout(token):
    with _SESSIONS_LOCK:
        s = _SESSIONS.pop(token or "", None)
    if s:
        s.close()


def normalize(session, path):
    path = (path or "").strip()
    if not path:
        return session.home
    if path == "~":
        return session.home
    if path.startswith("~/"):
        path = session.home + path[1:]
    if not path.startswith("/"):
        path = posixpath.join(session.home, path)
    return posixpath.normpath(path)


def under_home(session, path):
    home = session.home.rstrip("/")
    return path == home or path.startswith(home + "/")


def _require_home(session, path):
    p = normalize(session, path)
    if not under_home(session, p):
        raise HpcError("只允许操作当前账号家目录内的路径")
    return p


def resolve_root(session, root):
    return _require_home(session, root or (session.home + "/one_click_mof"))


def list_local(path, show_hidden=False):
    p = Path(path or "~").expanduser().resolve()
    if not p.exists():
        raise HpcError("本地路径不存在：" + str(p))
    if not p.is_dir():
        raise HpcError("本地路径不是目录：" + str(p))
    items = []
    for entry in p.iterdir():
        if not show_hidden and entry.name.startswith("."):
            continue
        try:
            st = entry.stat()
            items.append({
                "name": entry.name,
                "path": str(entry),
                "is_dir": entry.is_dir(),
                "size": st.st_size,
                "mtime": int(st.st_mtime),
                "is_link": entry.is_symlink(),
            })
        except OSError:
            continue
    items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    return {"path": str(p), "parent": str(p.parent), "items": items}


def list_remote(session, path, show_hidden=False):
    p = normalize(session, path)
    sftp = session.sftp()
    try:
        attrs = sftp.listdir_attr(p)
        items = []
        for a in attrs:
            if not show_hidden and a.filename.startswith("."):
                continue
            is_link = stat.S_ISLNK(a.st_mode or 0)
            is_dir = stat.S_ISDIR(a.st_mode or 0)
            if is_link:
                try:
                    is_dir = stat.S_ISDIR(sftp.stat(posixpath.join(p, a.filename)).st_mode or 0)
                except Exception:
                    is_dir = False
            items.append({
                "name": a.filename,
                "path": posixpath.join(p, a.filename),
                "is_dir": is_dir,
                "size": a.st_size or 0,
                "mtime": int(a.st_mtime or 0),
                "is_link": is_link,
            })
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return {"path": p, "parent": posixpath.dirname(p) or "/", "items": items}
    except Exception as exc:
        raise HpcError("读取远端目录失败：" + str(exc))
    finally:
        sftp.close()


def mkdir_remote(session, path):
    p = _require_home(session, path)
    sftp = session.sftp()
    try:
        sftp.mkdir(p)
    except Exception as exc:
        raise HpcError("创建远端目录失败：" + str(exc))
    finally:
        sftp.close()
    return {"path": p}


def _delete_tree(sftp, path):
    st = sftp.lstat(path)
    if stat.S_ISDIR(st.st_mode):
        for item in sftp.listdir_attr(path):
            _delete_tree(sftp, posixpath.join(path, item.filename))
        sftp.rmdir(path)
    else:
        sftp.remove(path)


def delete_remote(session, paths):
    sftp = session.sftp()
    deleted = []
    try:
        for raw in paths:
            p = _require_home(session, raw)
            if p == session.home:
                raise HpcError("不能删除账号家目录")
            _delete_tree(sftp, p)
            deleted.append(p)
    except Exception as exc:
        raise HpcError("删除远端文件失败：" + str(exc))
    finally:
        sftp.close()
    return {"deleted": deleted}


def _ensure_remote_dir(session, path):
    p = _require_home(session, path)
    r = session.run("mkdir -p -- " + shlex.quote(p))
    if r["rc"] != 0:
        raise HpcError("创建远端目录失败：" + r["err"])
    return p


def _upload_one(sftp, local, remote):
    local = Path(local)
    if local.is_dir():
        try:
            sftp.mkdir(remote)
        except Exception:
            pass
        for child in local.iterdir():
            _upload_one(sftp, child, posixpath.join(remote, child.name))
    else:
        sftp.put(str(local), remote)


def upload_paths(session, local_paths, remote_dir, compress=False):
    if not local_paths:
        raise HpcError("没有选择本地文件")
    target = _ensure_remote_dir(session, remote_dir)
    sftp = session.sftp()
    try:
        if compress:
            tmpdir = tempfile.mkdtemp(prefix="ocm_upload_")
            archive = os.path.join(tmpdir, "upload.tar.gz")
            with tarfile.open(archive, "w:gz") as tf:
                for raw in local_paths:
                    src = Path(raw).expanduser()
                    if not src.exists():
                        raise HpcError("本地文件不存在：" + str(src))
                    tf.add(str(src), arcname=src.name)
            remote_archive = posixpath.join(target, ".ocm_upload_" + uuid.uuid4().hex + ".tar.gz")
            sftp.put(archive, remote_archive)
            sftp.close()
            r = session.run("tar -xzf " + shlex.quote(remote_archive) + " -C " + shlex.quote(target))
            session.run("rm -f -- " + shlex.quote(remote_archive))
            if r["rc"] != 0:
                raise HpcError("远端解压失败：" + r["err"])
            return {"uploaded": len(local_paths), "remote_dir": target, "compressed": True}
        for raw in local_paths:
            src = Path(raw).expanduser()
            if not src.exists():
                raise HpcError("本地文件不存在：" + str(src))
            _upload_one(sftp, src, posixpath.join(target, src.name))
        return {"uploaded": len(local_paths), "remote_dir": target, "compressed": False}
    except Exception as exc:
        if isinstance(exc, HpcError):
            raise
        raise HpcError("上传失败：" + str(exc))
    finally:
        try:
            sftp.close()
        except Exception:
            pass


def download_paths(session, remote_paths, local_dir):
    if not remote_paths:
        raise HpcError("没有选择远端文件")
    outdir = Path(local_dir or "~").expanduser().resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    sftp = session.sftp()
    try:
        for raw in remote_paths:
            p = normalize(session, raw)
            st = sftp.stat(p)
            if stat.S_ISDIR(st.st_mode):
                tmp = tempfile.mkdtemp(prefix="ocm_download_")
                archive = os.path.join(tmp, "download.tar.gz")
                parent = posixpath.dirname(p)
                remote_archive = "/tmp/.ocm_download_" + uuid.uuid4().hex + ".tar.gz"
                base = posixpath.basename(p)
                r = session.run("tar -czf " + shlex.quote(remote_archive) + " -C " + shlex.quote(parent) + " " + shlex.quote(base))
                if r["rc"] != 0:
                    raise HpcError("远端打包失败：" + r["err"])
                try:
                    sftp.get(remote_archive, archive)
                    with tarfile.open(archive, "r:gz") as tf:
                        tf.extractall(outdir)
                finally:
                    session.run("rm -f -- " + shlex.quote(remote_archive))
            else:
                sftp.get(p, str(outdir / posixpath.basename(p)))
        return {"downloaded": len(remote_paths), "local_dir": str(outdir)}
    except Exception as exc:
        if isinstance(exc, HpcError):
            raise
        raise HpcError("下载失败：" + str(exc))
    finally:
        sftp.close()




def delete_local(paths, trash_root):
    import datetime
    trash = Path(trash_root) / datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    trash.mkdir(parents=True, exist_ok=True)
    moved = []
    for raw in paths:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            continue
        dest = trash / (p.name + '_' + uuid.uuid4().hex[:6])
        shutil.move(str(p), str(dest))
        moved.append(str(dest))
    return {'moved': moved, 'trash': str(trash)}

def read_log(session, path, lines=200):
    p = normalize(session, path)
    r = session.run("tail -n " + str(max(1, min(int(lines), 2000))) + " -- " + shlex.quote(p))
    if r["rc"] != 0:
        raise HpcError("读取日志失败：" + r["err"])
    return {"path": p, "text": r["out"]}


def dashboard(session):
    cmd = (
        "sinfo -N -h -o '%P|%n|%t|%c|%m|%e|%O'; "
        "echo '---QUEUE---'; squeue -h -o '%T'; "
        "echo '---USER---'; squeue -u " + shlex.quote(session.user) + " -h -o '%i|%j|%T|%M|%N|%R'"
    )
    r = session.run(cmd, timeout=20)
    if r["rc"] != 0:
        raise HpcError("读取 Slurm 状态失败：" + r["err"])
    nodes = []
    counts = {}
    user_jobs = []
    section = "nodes"
    queue = {}
    for line in r["out"].splitlines():
        line = line.strip()
        if line == "---QUEUE---":
            section = "queue"
            continue
        if line == "---USER---":
            section = "user"
            continue
        if not line:
            continue
        if section == "nodes":
            parts = line.split("|")
            if len(parts) < 7:
                continue
            try:
                mem = int(float(parts[4]))
                free = int(float(parts[5]))
                cpus = int(float(parts[3]))
            except Exception:
                continue
            state = parts[2]
            counts[state] = counts.get(state, 0) + 1
            nodes.append({
                "partition": parts[0].rstrip("*"),
                "node": parts[1],
                "state": state,
                "cpus": cpus,
                "memory_mb": mem,
                "free_mem_mb": free,
                "load": parts[6],
            })
        elif section == "queue":
            queue[line] = queue.get(line, 0) + 1
        else:
            parts = line.split("|", 5)
            if len(parts) >= 6:
                user_jobs.append({
                    "job_id": parts[0], "name": parts[1], "state": parts[2],
                    "time": parts[3], "nodes": parts[4], "reason": parts[5],
                })
    return {
        "fetched_at": int(time.time()),
        "nodes": nodes,
        "node_states": counts,
        "queue": queue,
        "running": queue.get("RUNNING", 0),
        "pending": queue.get("PENDING", 0),
        "user_jobs": user_jobs,
        "totals": {
            "nodes": len(nodes),
            "cpus": sum(n["cpus"] for n in nodes),
            "memory_mb": sum(n["memory_mb"] for n in nodes),
            "free_mem_mb": sum(n["free_mem_mb"] for n in nodes),
        },
    }


def submit_cp2k(session, remote_root, input_path, name, cores, nodes, task_dir):
    root = resolve_root(session, remote_root)
    task_dir = _require_home(session, task_dir)
    input_path = normalize(session, input_path)
    sftp = session.sftp()
    try:
        sftp.stat(input_path)
        _ensure_remote_dir(session, task_dir)
        input_name = posixpath.basename(input_path)
        dest = posixpath.join(task_dir, input_name)
        if input_path != dest:
            sftp.close()
            r = session.run("cp -p -- " + shlex.quote(input_path) + " " + shlex.quote(dest))
            sftp = session.sftp()
            if r["rc"] != 0:
                raise HpcError("复制输入文件失败：" + r["err"])
    except Exception as exc:
        if isinstance(exc, HpcError):
            raise
        raise HpcError("准备任务目录失败：" + str(exc))
    finally:
        try:
            sftp.close()
        except Exception:
            pass
    cmd = "cd " + shlex.quote(task_dir) + " && ifmccp2k " + shlex.quote(input_name) + " " + str(int(cores)) + " " + str(int(nodes))
    r = session.run(cmd, timeout=30)
    m = re.search(r"Submitted batch job\s+(\d+)", r["out"] + r["err"])
    if not m:
        raise HpcError("提交失败或未识别到 job id：" + (r["out"] + r["err"]).strip()[:500])
    return {
        "job_id": m.group(1),
        "task_dir": task_dir,
        "input_name": input_name,
        "log_path": posixpath.join(task_dir, posixpath.splitext(input_name)[0] + ".log"),
        "out_path": posixpath.join(task_dir, posixpath.splitext(input_name)[0] + ".o" + m.group(1)),
        "stdout": (r["out"] + r["err"]).strip(),
    }


def task_status(session, job_id):
    if not job_id:
        return {"state": "unknown", "time": "", "nodes": "", "reason": ""}
    r = session.run("squeue -j " + shlex.quote(str(job_id)) + " -h -o '%T|%M|%N|%R'", timeout=15)
    line = r["out"].strip().splitlines()
    if line:
        p = line[0].split("|", 3)
        return {"state": p[0] if len(p) > 0 else "unknown", "time": p[1] if len(p) > 1 else "",
                "nodes": p[2] if len(p) > 2 else "", "reason": p[3] if len(p) > 3 else ""}
    r = session.run("sacct -j " + shlex.quote(str(job_id)) + " -X -n -P -o State,Elapsed,Start,End", timeout=15)
    line = r["out"].strip().splitlines()
    if line:
        p = line[0].split("|")
        return {"state": p[0] if p else "unknown", "time": p[1] if len(p) > 1 else "",
                "nodes": "", "reason": ""}
    return {"state": "unknown", "time": "", "nodes": "", "reason": ""}


def cancel_job(session, job_id):
    r = session.run("scancel " + shlex.quote(str(job_id)), timeout=15)
    if r["rc"] != 0:
        raise HpcError("取消任务失败：" + r["err"])
    return {"ok": True}
