"""STEP Studio - the desktop app: open a STEP file, see which sizes can be changed, try values, run a DOE.

    app.cmd                      (or: fc.cmd app.py)
    app.cmd C:\\parts\\part.stp    open that file right away

A window opens (the Edge app window if Edge is installed, otherwise your default browser). The engine runs in this
console window on your own computer only (address 127.0.0.1); close the console to quit. No AI model is used.
Work files and results go to the folder "steprecon_studio" in your Documents (change with --workspace).

How much of the computer an analysis may use: at first half of the processor cores, at low priority so that other
programs stay responsive. Change it in the window (CPU button, applies at once) or with --cpu 4 / --cpu 75% /
--cpu all and --priority normal; the last choice is remembered in the workspace (settings.json)."""
import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from step_recon import cpu, studio  # noqa: E402


def default_workspace():
    docs = os.path.join(os.path.expanduser("~"), "Documents")
    return os.path.join(docs if os.path.isdir(docs) else os.path.expanduser("~"), "steprecon_studio")


def open_window(url):
    """An app-style window without browser chrome if Edge or Chrome is there; else the default browser."""
    candidates = [os.path.join(os.environ.get(v, ""), p) for v in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")
                  for p in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe")]
    candidates += [shutil.which(n) or "" for n in ("msedge", "chrome", "google-chrome", "chromium")]
    for exe in candidates:
        if exe and os.path.isfile(exe):
            try:
                subprocess.Popen([exe, f"--app={url}", "--window-size=1500,920"])
                return "app window"
            except OSError:
                pass
    webbrowser.open(url)
    return "browser"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", nargs="?", help="STEP/IGES file to open at start")
    ap.add_argument("--workspace", default=default_workspace(), help="folder for models and DOE results")
    ap.add_argument("--port", type=int, default=0, help="fixed port (default: any free one)")
    ap.add_argument("--no-window", action="store_true", help="do not open a window (print the address only)")
    ap.add_argument("--cpu", default=None, metavar="N",
                    help="processor cores the engine may use: a number, a percentage (75%%) or all "
                         "(default: what was chosen last time, at first half of the cores)")
    ap.add_argument("--priority", choices=["low", "normal"], default=None,
                    help="low lets other programs go first (default: low)")
    a = ap.parse_args()
    if a.file and not os.path.isfile(a.file):
        raise SystemExit(f"file not found: {a.file}\n(put paths with spaces or parentheses in double quotes)")
    server, st = studio.serve(a.workspace, a.port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"STEP Studio  {url}")
    print(f"workspace    {a.workspace}")
    saved = st.load_settings()
    try:
        cores = cpu.parse(a.cpu) if a.cpu else saved.get("cpu_cores", cpu.default_cores())
    except ValueError as e:
        raise SystemExit(f"--cpu: {e}")
    low = (a.priority == "low") if a.priority else saved.get("cpu_low", True)
    c = st.set_cpu(cores, low)
    print(f"CPU          {c['cores']} of {c['total']} cores" + (", low priority" if c["low"] else "")
          + ("" if c["can_limit"] else " (the number of cores cannot be limited on this system)"))
    if a.file:
        path = os.path.abspath(a.file)

        def open_at_start():
            try:
                s = st.worker.call(st.open, path)
                c = s["info"]["counts"]
                print(f"opened       {c['holes']} holes, {c['fillets']} filleted and {c['chamfers']} chamfered edges; "
                      f"identical={s['info']['identical']}, {s['info']['seconds']} s")
            except Exception as e:
                print(f"opened       could not open {a.file}: {type(e).__name__}: {e}")

        print(f"opening      {a.file} (progress is shown in the window)")
        # marked as running before the window asks, so that the page waits for it instead of showing an empty app
        st.progress = {"active": True, "pct": 0.0, "text": "준비 중", "started": time.time(), "name": os.path.basename(path)}
        threading.Thread(target=open_at_start, daemon=True).start()
    if not a.no_window:
        print("window       " + open_window(url))
    print("Keep this console open while you work. Close it (or press Ctrl+C) to quit.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        st.worker.call(st.close)
        server.server_close()


if __name__ == "__main__":
    main()
