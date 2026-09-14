#!/usr/bin/env python3
import argparse, json, os, shutil, sys, tarfile, tempfile, urllib.request, zipfile
from pathlib import Path

API = "https://api.github.com/repos/pspdev/pspdev/releases/latest"

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "SpaceCadetPinball-PSP-builder/1.0.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)

def aliases(platform, arch):
    p = {
        "macos": ("macos", "osx", "darwin"),
        # Official PSPDEV Linux binaries are currently named for Ubuntu, e.g.
        # pspdev-ubuntu-latest-x86_64.tar.gz.  Keep generic Linux/Debian
        # aliases too so future release naming changes remain compatible.
        "linux": ("ubuntu", "linux", "debian"),
    }[platform]
    if arch in ("arm64", "aarch64"):
        a = ("arm64", "aarch64")
    else:
        a = ("x86_64", "amd64", "x64")
    return p, a

def choose_asset(data, platform, arch):
    pals, aals = aliases(platform, arch)
    ranked = []
    for asset in data.get("assets", []):
        name = asset.get("name", "")
        low = name.lower()
        if not any(x in low for x in pals) or not any(x in low for x in aals):
            continue
        if any(x in low for x in ("sha256", "checksum", ".sig", "source")):
            continue
        score = 0
        if low.endswith((".tar.xz", ".tar.gz", ".tgz", ".zip")):
            score += 20
        if "pspdev" in low:
            score += 5
        ranked.append((score, name, asset.get("browser_download_url", "")))
    ranked.sort(reverse=True)
    return ranked[0] if ranked else None

def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "SpaceCadetPinball-PSP-builder/1.0.0"})
    with urllib.request.urlopen(req, timeout=120) as src, open(dest, "wb") as out:
        shutil.copyfileobj(src, out)

def extract(archive, dest):
    n = archive.name.lower()
    if n.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            z.extractall(dest)
    elif n.endswith((".tar.gz", ".tgz", ".tar.xz", ".tar")):
        with tarfile.open(archive, "r:*") as t:
            t.extractall(dest)
    else:
        raise RuntimeError(f"Unsupported PSPDEV archive format: {archive.name}")

def find_root(extracted):
    candidates = []
    for exe in ("psp-gcc", "psp-gcc.exe", "psp-config", "psp-config.exe"):
        for p in extracted.rglob(exe):
            if p.parent.name == "bin":
                candidates.append(p.parent.parent)
    if not candidates:
        raise RuntimeError("Downloaded archive does not contain a PSPDEV bin directory")
    candidates.sort(key=lambda p: len(p.parts))
    return candidates[0]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platform", choices=("macos", "linux"), required=True)
    ap.add_argument("--arch", required=True)
    ap.add_argument("--dest", required=True)
    args = ap.parse_args()
    dest = Path(args.dest).expanduser().resolve()
    data = fetch_json(API)
    asset = choose_asset(data, args.platform, args.arch)
    if not asset:
        print("NO_MATCHING_RELEASE_ASSET")
        return 3
    _, name, url = asset
    print(f"Using PSPDEV release asset: {name}")
    with tempfile.TemporaryDirectory(prefix="pspdev_release_") as td:
        td = Path(td)
        arc = td / name
        download(url, arc)
        unpack = td / "unpack"
        unpack.mkdir()
        extract(arc, unpack)
        root = find_root(unpack)
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True, exist_ok=True)
        for child in root.iterdir():
            target = dest / child.name
            if child.is_dir():
                shutil.copytree(child, target, symlinks=True, dirs_exist_ok=True)
            else:
                shutil.copy2(child, target, follow_symlinks=False)
    gcc = dest / "bin" / "psp-gcc"
    if not gcc.exists() and not (dest / "bin" / "psp-gcc.exe").exists():
        raise RuntimeError("PSPDEV installation finished but psp-gcc is missing")
    print(f"PSPDEV installed at: {dest}")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(2)
