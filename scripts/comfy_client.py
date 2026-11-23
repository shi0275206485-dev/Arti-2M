"""Submit shots to a running ComfyUI instance via its HTTP API and collect outputs.

Usage:
    python scripts/comfy_client.py --workflow workflows/wan_t2v_api.json \
        --shots shots/shots.json [--host 127.0.0.1:8188] [--only 3,4]

The workflow must be exported in API format (ComfyUI menu: Export (API)).
shots.json format:
[
  {"id": "s01", "prompt": "...", "negative": "...", "seconds": 4.0, "seed": 1,
   "overrides": {"<node_id>.<input_name>": value},
   "uploads":   {"<node_id>.<input_name>": "local/path/to/image_or_audio"}}
]
Map shot fields to workflow nodes with --prompt-node/--prompt-input, --neg-node/--neg-input,
--seed-node/--seed-input, --frames-node (Wan 4n+1 frames) or --seconds-node (models that
take seconds directly), or use per-shot "overrides" for anything else. "uploads" sends a
local file to ComfyUI's input folder (POST /upload/image) and sets the node input to it,
e.g. a member reference image for LoadImage or a vocal clip for LoadAudio.
"""
import argparse
import json
import time
import uuid
from pathlib import Path

import requests


def set_input(wf, node_id, name, value):
    if node_id not in wf:
        raise KeyError(f"node {node_id} not in workflow")
    wf[node_id]["inputs"][name] = value


def upload(host, path, subfolder="ai-mv"):
    """Upload a local file to ComfyUI's input dir; returns the name LoadImage/LoadAudio expect."""
    path = Path(path)
    with open(path, "rb") as f:
        r = requests.post(f"http://{host}/upload/image",
                          files={"image": (path.name, f)},
                          data={"subfolder": subfolder, "type": "input", "overwrite": "true"})
    r.raise_for_status()
    info = r.json()
    return f"{info['subfolder']}/{info['name']}" if info.get("subfolder") else info["name"]


def submit(host, wf, client_id):
    r = requests.post(f"http://{host}/prompt", json={"prompt": wf, "client_id": client_id})
    if r.status_code != 200:
        raise RuntimeError(f"ComfyUI rejected prompt: {r.status_code} {r.text[:500]}")
    body = r.json()
    if body.get("node_errors"):
        # ComfyUI still queues the prompt but silently drops outputs whose inputs failed validation
        raise RuntimeError(f"ComfyUI validation errors: {json.dumps(body['node_errors'])[:1500]}")
    return body["prompt_id"]


def wait(host, prompt_id, poll=3.0, timeout=3600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = requests.get(f"http://{host}/history/{prompt_id}").json()
        if prompt_id in h:
            status = h[prompt_id].get("status", {})
            if status.get("status_str") == "error":
                raise RuntimeError(f"generation failed: {status}")
            return h[prompt_id]["outputs"]
        time.sleep(poll)
    raise TimeoutError(prompt_id)


def download_outputs(host, outputs, dest, stem):
    saved = []
    for node_out in outputs.values():
        for key in ("videos", "gifs", "images"):
            for i, f in enumerate(node_out.get(key, [])):
                params = {"filename": f["filename"], "subfolder": f.get("subfolder", ""),
                          "type": f.get("type", "output")}
                data = requests.get(f"http://{host}/view", params=params).content
                ext = Path(f["filename"]).suffix
                path = dest / f"{stem}{'' if i == 0 else f'_{i}'}{ext}"
                path.write_bytes(data)
                saved.append(path)
    return saved


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workflow", required=True)
    ap.add_argument("--shots", required=True)
    ap.add_argument("--host", default="127.0.0.1:8188")
    ap.add_argument("--out", default="clips")
    ap.add_argument("--prompt-node", help="node id of positive prompt")
    ap.add_argument("--prompt-input", default="text")
    ap.add_argument("--neg-node", help="node id of negative prompt")
    ap.add_argument("--neg-input", default="text")
    ap.add_argument("--seconds-node", help="node id holding clip length in seconds")
    ap.add_argument("--seconds-input", default="value")
    ap.add_argument("--seed-node", help="node id of sampler (input 'seed' or 'noise_seed')")
    ap.add_argument("--seed-input", default="seed")
    ap.add_argument("--frames-node", help="node id holding frame count (input 'length')")
    ap.add_argument("--frames-input", default="length")
    ap.add_argument("--fps", type=float, default=16.0, help="model fps, for seconds->frames")
    ap.add_argument("--only", help="comma-separated shot ids to run")
    args = ap.parse_args()

    base = json.loads(Path(args.workflow).read_text(encoding="utf-8"))
    shots = json.loads(Path(args.shots).read_text(encoding="utf-8"))
    only = set(args.only.split(",")) if args.only else None
    dest = Path(args.out)
    dest.mkdir(parents=True, exist_ok=True)
    client_id = str(uuid.uuid4())

    for shot in shots:
        if only and shot["id"] not in only:
            continue
        wf = json.loads(json.dumps(base))
        if args.prompt_node and "prompt" in shot:
            set_input(wf, args.prompt_node, args.prompt_input, shot["prompt"])
        if args.neg_node and "negative" in shot:
            set_input(wf, args.neg_node, args.neg_input, shot["negative"])
        if args.seconds_node and "seconds" in shot:
            set_input(wf, args.seconds_node, args.seconds_input, shot["seconds"])
        for key, local in shot.get("uploads", {}).items():
            node_id, name = key.split(".", 1)
            set_input(wf, node_id, name, upload(args.host, local))
        if args.seed_node and "seed" in shot:
            set_input(wf, args.seed_node, args.seed_input, shot["seed"])
        if args.frames_node and "seconds" in shot:
            # Wan-family models want 4n+1 frames
            n = int(round(shot["seconds"] * args.fps))
            set_input(wf, args.frames_node, args.frames_input, (n // 4) * 4 + 1)
        for key, val in shot.get("overrides", {}).items():
            node_id, name = key.split(".", 1)
            set_input(wf, node_id, name, val)

        print(f"[{shot['id']}] submitting...", flush=True)
        t0 = time.time()
        pid = submit(args.host, wf, client_id)
        outputs = wait(args.host, pid)
        stem = f"{shot['id']}_{int(time.time())}"
        saved = download_outputs(args.host, outputs, dest, stem)
        if not saved:
            raise RuntimeError(f"[{shot['id']}] finished but produced no image/video output")
        print(f"[{shot['id']}] done in {time.time() - t0:.0f}s -> {[str(p) for p in saved]}")


if __name__ == "__main__":
    main()
