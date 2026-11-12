"""Split the machined holes of a complex part off as editable features - no model involved.

For cast or moulded parts (housings, covers) a full feature tree is out of reach, but what gets changed in practice
are the machined features. This module recognises round holes and bores in the reference, fills them to get the
"blank" (kept as a frozen, non-parametric base), and cuts every hole again as a dimensioned feature:

    ImportedBlank  ->  Hole_D8_x6  ->  Hole_D25  ->  ...

The result is identical to the reference by construction; diameters, positions and depths are now parameters.
Equal holes drilled from the same face form one feature (one sketch with several circles).
Recognised: complete concave cylinders - through or blind, in any direction, including each step of a counterbore.
Left in the blank: everything else (cones of drill points and countersinks, slots, threads, freeform shapes)."""
import math

import FreeCAD as App
import Part

from . import fc_tools

TWO_PI = 2 * math.pi


def _canon(v):
    """Same direction for both orientations of an axis: the dominant component positive."""
    big = max(range(3), key=lambda i: abs(v[i]))
    return v if v[big] > 0 else v * -1


def find_holes(ref, min_radius=0.2):
    """Complete concave cylinders of the reference: [{"axis", "foot", "radius", "t0", "t1", "faces"}], where a point
    of the axis is foot + axis * t and the hole runs from t0 to t1."""
    groups = {}
    for i, f in enumerate(ref.Faces):
        s = f.Surface
        if type(s).__name__ != "Cylinder" or s.Radius < min_radius:
            continue
        u0, u1, v0, v1 = f.ParameterRange
        um, vm = (u0 + u1) / 2, (v0 + v1) / 2
        pt = f.valueAt(um, vm)
        to_axis = s.Center - pt
        to_axis = to_axis - s.Axis * to_axis.dot(s.Axis)
        if f.normalAt(um, vm).dot(to_axis) <= 0:        # convex: a boss or shaft, not a hole
            continue
        a = _canon(App.Vector(s.Axis).normalize())
        foot = s.Center - a * s.Center.dot(a)
        t = sorted(((f.valueAt(um, v) - foot).dot(a)) for v in (v0, v1))
        key = (round(a.x, 5), round(a.y, 5), round(a.z, 5), round(foot.x, 3), round(foot.y, 3), round(foot.z, 3),
               round(s.Radius, 4), round(t[0], 3), round(t[1], 3))
        g = groups.setdefault(key, {"axis": a, "foot": foot, "radius": s.Radius, "t0": t[0], "t1": t[1],
                                    "span": 0.0, "faces": []})
        g["span"] += abs(u1 - u0)
        g["faces"].append(i)
    holes = [g for g in groups.values() if g["span"] >= TWO_PI - 1e-6 and g["t1"] - g["t0"] > 1e-6]
    holes.sort(key=lambda h: (-h["radius"], h["t0"]))
    return holes


def _plug(h):
    start = h["foot"] + h["axis"] * h["t0"]
    return Part.makeCylinder(h["radius"], h["t1"] - h["t0"], start, h["axis"])


def _open_end(ref, h):
    """Which end of the hole to drill from: the one with nothing beyond it. Returns (t of that end, direction
    pointing out of the hole there)."""
    eps = max(1e-3, 1e-4 * (h["t1"] - h["t0"]))
    for t, out in ((h["t1"], h["axis"]), (h["t0"], h["axis"] * -1)):
        probe = h["foot"] + h["axis"] * t + out * eps
        if not ref.isInside(probe, 1e-7, False):
            return t, out
    return h["t1"], h["axis"]


def build(ref, _exclude=None, _round=0):
    """Reference -> (Session with blank + hole features, report dict).

    Every hole is checked after it has been cut again: it must remove exactly its own volume. One that does not
    (the CAD kernel can fail where a hole enters through a curved face) is left in the blank as it is and the
    part is built again without it, so the result stays identical to the reference in any case."""
    exclude = set(_exclude or ())
    report = {"holes_found": 0, "holes_made": 0, "features": 0, "skipped": []}
    holes = []
    for h in find_holes(ref):
        hid = tuple(h["faces"])
        if hid in exclude:
            report["skipped"].append(f"D{2 * h['radius']:g}: could not be cut again cleanly, left in the blank")
            continue
        plug = _plug(h)
        try:
            overlap = plug.common(ref).Volume
        except Exception:
            overlap = plug.Volume
        if overlap > 1e-6 * plug.Volume:        # something stands inside this cylinder: not a plain drilled hole
            report["skipped"].append(f"D{2 * h['radius']:g}: not empty inside, left in the blank")
            continue
        h["id"], h["plug"] = hid, plug
        h["end"], h["out"] = _open_end(ref, h)
        holes.append(h)
    report["holes_found"] = len(holes) + len(report["skipped"])
    sess = fc_tools.Session(ref)
    if not holes:
        sess.import_shape(ref, "blank (reference as is: no holes turned into features)")
        return sess, report
    blank = ref.fuse([h["plug"] for h in holes])
    try:
        refined = blank.copy().removeSplitter()
        if refined.isValid() and abs(refined.Volume - blank.Volume) <= 2e-4 * max(1.0, blank.Volume):
            blank = refined
    except Exception:
        pass
    solids = blank.Solids
    if len(solids) == 1:
        blank = solids[0]
    sess.import_shape(blank, f"blank (reference with {len(holes)} holes filled)")

    # equal holes drilled from the same face in the same direction -> one feature
    jobs = {}
    for h in holes:
        plane_off = (h["foot"] + h["axis"] * h["end"]).dot(h["out"])
        key = (round(h["out"].x, 5), round(h["out"].y, 5), round(h["out"].z, 5), round(plane_off, 3),
               round(h["radius"], 4), round(h["t1"] - h["t0"], 3))
        jobs.setdefault(key, []).append(h)
    failed = set()
    for group in jobs.values():
        h0 = group[0]
        n = h0["out"]
        entry0 = h0["foot"] + h0["axis"] * h0["end"]
        plane = {"origin": list(n * entry0.dot(n)), "normal": [n.x, n.y, n.z]}
        o, x, y, _ = sess._frame(plane)
        plane["x_dir"] = [x.x, x.y, x.z]
        circles = []
        for h in group:
            e = h["foot"] + h["axis"] * h["end"] - o
            circles.append({"type": "circle", "c": [e.dot(x), e.dot(y)], "r": h["radius"]})
        current = sess._tip_shape()
        before = current.Volume
        try:        # what is still there to remove (an earlier, crossing hole may have taken part of it already)
            want = sum(h["plug"].common(current).Volume for h in group)
        except Exception:
            want = sum(h["plug"].Volume for h in group)
        depth = h0["t1"] - h0["t0"]
        ok = False
        for attempt in (0, 1):
            if attempt == 1:    # second try: sketch on the far end of the hole, cutting back toward the entry
                far = {"origin": list(n * -1 * (entry0 - n * depth).dot(n * -1)), "normal": [-n.x, -n.y, -n.z],
                       "x_dir": plane["x_dir"]}
                o2, x2, y2, _ = sess._frame(far)
                circles = []
                for h in group:
                    e = h["foot"] + h["axis"] * h["end"] - n * depth - o2
                    circles.append({"type": "circle", "c": [e.dot(x2), e.dot(y2)], "r": h["radius"]})
                plane = far
            r = sess.pocket(plane, circles, depth=depth)
            if r.get("ok"):
                removed = before - sess.body.Tip.Shape.Volume
                if abs(removed - want) <= 5e-3 * max(want, 1e-9):
                    ok = True
                    break
                sess.undo()
        if not ok:
            failed.update(h["id"] for h in group)
            continue
        feat = sess.doc.getObject(r["feature"])
        d = round(2 * h0["radius"], 3)
        feat.Label = f"Hole_D{d:g}" + (f"_x{len(group)}" if len(group) > 1 else "")
        report["holes_made"] += len(group)
        report["features"] += 1
    if failed and _round < 4:       # build again, leaving those holes in the blank
        App.closeDocument(sess.doc.Name)
        return build(ref, exclude | failed, _round + 1)
    return sess, report
