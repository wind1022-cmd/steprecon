"""Design of experiments on a reconstructed model: change its parameters and write one STEP file per variant.

Works on any .FCStd made by run.py or machined.py. No AI model is used.

1. See what can be varied (also written to <name>.params.csv):
       fc.cmd doe.py out_machined\\housing.FCStd --list

2a. Full factorial from ranges or value lists (lengths in mm, angles in degrees):
       fc.cmd doe.py out_machined\\housing.FCStd --vary "Hole_D6_x4.Diameter1=5:8:4" --vary "Fillet_R3_x4.Radius=2,3,4"
    "a:b:n" = n evenly spaced values from a to b;  "v1,v2,v3" = those values.
2b. Or your own table (CSV with one column per parameter, one row per variant):
       fc.cmd doe.py out_machined\\housing.FCStd --table my_runs.csv

Output in --out (default: doe_<name>): run_001.step, run_002.step, ... and results.csv with the parameter values,
whether the variant rebuilt cleanly, volume, surface area, centre of gravity and bounding box of each.
Parameters not mentioned keep the model's own value. A variant that cannot be built (e.g. a fillet too large) is
reported with ok=False and no STEP file; the run goes on."""
import argparse
import csv
import itertools
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from step_recon import params as P  # noqa: E402
import FreeCAD as App  # noqa: E402


def parse_vary(text):
    """'name=a:b:n' or 'name=v1,v2,...' -> (name, [values])."""
    if "=" not in text:
        raise SystemExit(f"--vary needs name=values, got {text!r}")
    name, spec = text.split("=", 1)
    name, spec = name.strip(), spec.strip()
    try:
        if ":" in spec:
            a, b, n = spec.split(":")
            a, b, n = float(a), float(b), int(n)
            if n < 2:
                raise ValueError
            vals = [a + (b - a) * i / (n - 1) for i in range(n)]
        else:
            vals = [float(v) for v in spec.split(",") if v.strip()]
        if not vals:
            raise ValueError
    except ValueError:
        raise SystemExit(f"cannot read the values of {name!r}: use a:b:n (n >= 2) or v1,v2,v3")
    return name, vals


def read_table(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        vals = {}
        for k, v in r.items():
            if k is None or k.strip().lower() in ("run", "") or v is None or not str(v).strip():
                continue
            try:
                vals[k.strip()] = float(v)
            except ValueError:
                raise SystemExit(f"{path}: value {v!r} in column {k!r} is not a number")
        out.append(vals)
    return out


def measure(shape):
    bb = shape.BoundBox
    solids = shape.Solids or [shape]
    vol = sum(s.Volume for s in solids)
    c = [sum(getattr(s.CenterOfMass, ax) * s.Volume for s in solids) / vol for ax in "xyz"]
    return {"volume": round(vol, 4), "area": round(shape.Area, 4),
            "cog_x": round(c[0], 4), "cog_y": round(c[1], 4), "cog_z": round(c[2], 4),
            "size_x": round(bb.XLength, 4), "size_y": round(bb.YLength, 4), "size_z": round(bb.ZLength, 4)}


def run(fcstd, runs, out_dir, save_fcstd=False, verbose=True):
    """Build every variant. `runs` is a list of {parameter: value}. Returns the result rows."""
    doc = App.openDocument(os.path.abspath(fcstd))
    try:
        doc.recompute()
        plist = P.collect(doc)
        names = [p["name"] for p in plist]
        base = {p["name"]: p["value"] for p in plist}
        used = sorted({k for r in runs for k in r}, key=lambda k: names.index(k) if k in names else 1e9)
        unknown = [k for k in used if k not in base]
        if unknown:
            raise SystemExit("unknown parameter(s): " + ", ".join(unknown) + "\n(see the names with --list)")
        os.makedirs(out_dir, exist_ok=True)
        rows = []
        fields = ["run"] + used + ["ok", "volume", "area", "cog_x", "cog_y", "cog_z", "size_x", "size_y", "size_z",
                                   "file", "error"]
        for n, values in enumerate(runs, 1):
            row = {"run": n, "ok": False, "file": "", "error": ""}
            row.update({k: values.get(k, base[k]) for k in used})
            try:
                P.apply(doc, plist, {k: base[k] for k in used})      # start every variant from the original
                P.apply(doc, plist, values)
                doc.recompute()
                bad = P.problems(doc)
                if bad:
                    row["error"] = "; ".join(bad)[:300]
                else:
                    shape = P.result_shape(doc)
                    row.update(measure(shape))
                    path = os.path.join(out_dir, f"run_{n:03d}.step")
                    shape.exportStep(path)
                    row["file"], row["ok"] = os.path.basename(path), True
                    if save_fcstd:
                        doc.saveCopy(os.path.join(out_dir, f"run_{n:03d}.FCStd"))
            except Exception as e:
                row["error"] = f"{type(e).__name__}: {e}"[:300]
            rows.append(row)
            if verbose:
                what = ", ".join(f"{k}={row[k]:g}" for k in used)
                print(f"[{n}/{len(runs)}] {what} -> " + (f"ok, volume {row['volume']}" if row["ok"] else f"FAILED: {row['error']}"))
            with open(os.path.join(out_dir, "results.csv"), "w", newline="", encoding="utf-8-sig") as f:
                w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                w.writeheader()
                w.writerows(rows)
        return rows
    finally:
        App.closeDocument(doc.Name)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("fcstd", help="model written by run.py or machined.py")
    ap.add_argument("--list", action="store_true", help="show the parameters and write <name>.params.csv")
    ap.add_argument("--vary", action="append", default=[], metavar="NAME=VALUES",
                    help="a:b:n or v1,v2,...; several --vary give every combination")
    ap.add_argument("--table", help="CSV file: one column per parameter, one row per variant")
    ap.add_argument("--out", help="output folder (default: doe_<name> next to the model)")
    ap.add_argument("--save-fcstd", action="store_true", help="also save every variant as .FCStd")
    ap.add_argument("--max-runs", type=int, default=500, help="refuse larger experiments (default 500)")
    a = ap.parse_args()
    if not os.path.isfile(a.fcstd):
        raise SystemExit(f"file not found: {a.fcstd}")
    base = os.path.splitext(os.path.basename(a.fcstd))[0]
    here = os.path.dirname(os.path.abspath(a.fcstd))
    if a.list or not (a.vary or a.table):
        doc = App.openDocument(os.path.abspath(a.fcstd))
        doc.recompute()
        plist = P.collect(doc)
        App.closeDocument(doc.Name)
        path = os.path.join(here, base + ".params.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["name", "value", "unit"])
            for p in plist:
                w.writerow([p["name"], round(p["value"], 6), "deg" if p["kind"] == "angle" else "mm"])
        width = max([len(p["name"]) for p in plist] + [4])
        for p in plist:
            print(f"{p['name']:<{width}}  {p['value']:.6g} " + ("deg" if p["kind"] == "angle" else "mm"))
        print(f"\n{len(plist)} parameters; also written to {path}")
        if not a.list:
            print('nothing to run: add --vary "NAME=a:b:n" or --table file.csv')
        return
    runs = []
    if a.table:
        runs += read_table(a.table)
    if a.vary:
        pairs = [parse_vary(v) for v in a.vary]
        runs += [dict(zip([n for n, _ in pairs], combo)) for combo in itertools.product(*[v for _, v in pairs])]
    if len(runs) > a.max_runs:
        raise SystemExit(f"{len(runs)} variants is more than --max-runs {a.max_runs}")
    out_dir = a.out or os.path.join(here, "doe_" + base)
    rows = run(a.fcstd, runs, out_dir, a.save_fcstd)
    ok = sum(1 for r in rows if r["ok"])
    print(f"\n{ok}/{len(rows)} variants built; results: {os.path.join(out_dir, 'results.csv')}")


if __name__ == "__main__":
    main()
