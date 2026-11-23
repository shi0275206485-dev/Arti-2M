"""Start / stop / check a headless ComfyUI server using the Comfy Desktop install.

Usage:
    python scripts/comfy_server.py start [--wait 180]
    python scripts/comfy_server.py status
    python scripts/comfy_server.py stop          # frees the GPU (e.g. before running YuE2)

Same model paths (E:\\models via the Desktop-generated YAML), input/output folders and
port as the Desktop app, so files and workflows are interchangeable. Refuses to start a
second server if something already answers on the port (e.g. the Desktop app).
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import requests

INSTALL = Path(r"D:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI")
PYTHON = INSTALL / ".venv" / "Scripts" / "python.exe"
MODEL_PATHS = Path(os.environ["APPDATA"]) / "Comfy Desktop" / "instance-model-paths" / "inst-1794813914203.yaml"
SHARED = Path(r"D:\Comfy-Desktop\ComfyUI-Shared")
ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".comfy_server.json"
LOG = ROOT / "logs" / "comfy_server.log"


def alive(host):
    try:
        return requests.get(f"http://{host}/system_stats", timeout=3).json()
    except (requests.RequestException, ValueError):
        return None


def start(args):
    if alive(args.host):
        print(f"ComfyUI already running at {args.host}")
        return
    port = args.host.split(":")[1]
    cmd = [str(PYTHON), "main.py", "--listen", "127.0.0.1", "--port", port,
           "--extra-model-paths-config", str(MODEL_PATHS),
           "--input-directory", str(SHARED / "input"),
           "--output-directory", str(SHARED / "output")]
    if args.cache_none:
        cmd.append("--cache-none")
    LOG.parent.mkdir(exist_ok=True)
    log = open(LOG, "ab")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS if os.name == "nt" else 0
    proc = subprocess.Popen(cmd, cwd=INSTALL, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
    STATE.write_text(json.dumps({"pid": proc.pid, "host": args.host, "started": time.time()}))
    print(f"started pid {proc.pid}, log {LOG}")
    t0 = time.time()
    while time.time() - t0 < args.wait:
        if proc.poll() is not None:
            sys.exit(f"ComfyUI exited with code {proc.returncode}; see {LOG}")
        if alive(args.host):
            print(f"ready at http://{args.host} after {time.time() - t0:.0f}s")
            return
        time.sleep(2)
    sys.exit(f"not ready after {args.wait}s; see {LOG}")


def status(args):
    info = alive(args.host)
    if not info:
        print("not running")
        return
    dev = info.get("devices", [{}])[0]
    print(f"running at {args.host}: ComfyUI {info.get('system', {}).get('comfyui_version')}, "
          f"{dev.get('name')}, VRAM free {dev.get('vram_free', 0) / 2**30:.1f}/{dev.get('vram_total', 0) / 2**30:.1f} GiB")
    try:
        q = requests.get(f"http://{args.host}/queue", timeout=3).json()
        print(f"queue: {len(q.get('queue_running', []))} running, {len(q.get('queue_pending', []))} pending")
    except requests.RequestException:
        pass


def stop(args):
    if not STATE.exists():
        print("no server started by this script" + (" (but something answers on the port)" if alive(args.host) else ""))
        return
    pid = json.loads(STATE.read_text())["pid"]
    try:
        requests.post(f"http://{args.host}/interrupt", timeout=3)
    except requests.RequestException:
        pass
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        os.kill(pid, signal.SIGTERM)
    for _ in range(20):
        if not alive(args.host):
            break
        time.sleep(0.5)
    STATE.unlink(missing_ok=True)
    print(f"stopped pid {pid}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("start", "stop", "status"))
    ap.add_argument("--host", default="127.0.0.1:8188")
    ap.add_argument("--wait", type=int, default=180)
    ap.add_argument("--cache-none", action="store_true",
                    help="pass --cache-none to ComfyUI: no node-output cache in RAM (lower peak RAM, models reload each job)")
    args = ap.parse_args()
    {"start": start, "stop": stop, "status": status}[args.action](args)


if __name__ == "__main__":
    main()
