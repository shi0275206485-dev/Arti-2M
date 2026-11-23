"""Generate candidate reference portraits for each member with Qwen Image 2.1 t2i.

Usage (run inside a project root):
    python scripts/gen_refs.py [--members shots/members.json] [--n 4] [--only NAME] [--seed-base 10]

Reads members.json (members.<NAME>.look / signature_color and reference_sheet_prompt) and
writes shots/refs/<NAME>_cand<k>.png. Choosing one (copy to shots/refs/<NAME>.png) is up to
the caller (the web agent picks with Claude vision or lets the user choose).
"""
import argparse
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comfy_client import download_outputs, submit, wait  # noqa: E402
from wf_bindings import DEFAULTS, fill, load_role  # noqa: E402

DEFAULT_SHEET = ("Character reference portrait of {look}. Front-facing, head and shoulders, looking straight at "
                 "the camera, neutral expression, even soft studio lighting with a subtle {signature_color} rim "
                 "light, plain dark grey background, sharp focus, photorealistic, 85mm lens, no text, no watermark.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--members", default="shots/members.json")
    ap.add_argument("--workflow", help="API workflow using the built-in t2i node ids "
                    "(default: the project's t2i role from workflows/bindings.json)")
    ap.add_argument("--host", default="127.0.0.1:8188")
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--only")
    ap.add_argument("--seed-base", type=int, default=10)
    ap.add_argument("--width", type=int, default=1024)
    ap.add_argument("--height", type=int, default=1024)
    args = ap.parse_args()

    data = json.loads(Path(args.members).read_text(encoding="utf-8"))
    sheet = data.get("reference_sheet_prompt") or DEFAULT_SHEET
    if args.workflow:
        base, b = json.loads(Path(args.workflow).read_text(encoding="utf-8")), DEFAULTS["t2i"]
    else:
        base, b = load_role("t2i")
    out = Path("shots/refs")
    out.mkdir(parents=True, exist_ok=True)
    client = str(uuid.uuid4())
    for mi, (name, m) in enumerate(data["members"].items()):
        if args.only and name != args.only:
            continue
        prompt = sheet.format(look=m["look"], signature_color=m.get("signature_color", "neutral"))
        for k in range(args.n):
            wf = fill(json.loads(json.dumps(base)), b, {
                "prompt": prompt, "seed": args.seed_base + mi * 100 + k, "width": args.width,
                "height": args.height, "output": f"ai-mv/ref_{name}"})
            saved = download_outputs(args.host, wait(args.host, submit(args.host, wf, client)), out, f"_{name}_tmp")
            dest = out / f"{name}_cand{k}.png"
            if dest.exists():
                dest.unlink()
            saved[0].rename(dest)
            print(f"ref {name} cand{k} -> {dest}", flush=True)


if __name__ == "__main__":
    main()
