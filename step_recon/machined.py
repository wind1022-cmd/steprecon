"""Turn what can be expressed of a complex part into editable features - no model involved.

For cast or moulded parts (housings, covers) a full feature tree is out of reach, but the things one wants to vary
are local: hole sizes and positions, fillet radii, chamfer sizes. This module recognises them in the reference,
removes them to get a "blank" (kept as a frozen, non-parametric base) and puts each one back as a feature:

    ImportedBlank -> Hole_D8_x6 -> Hole_D25 -> Fillet_R3 -> Chamfer_1 -> ...

How:
  1. fillets and chamfers are taken off with the CAD kernel's defeaturing (faces removed, neighbours extended);
  2. complete round holes are filled with plugs;
  3. the holes are cut again as dimensioned pockets, the fillets and chamfers applied again as features, with
     sizes measured from the reference.
Nothing is taken on trust: every step is checked against the reference, and whatever does not come back exactly is
left in the blank untouched. So the result always equals the reference; only the number of features varies.

Recognised: complete concave cylinders (through or blind, any direction, each step of a counterbore);
constant-radius fillets (straight, around circular edges, with their corner patches); equal-leg chamfers;
flat faces whose surroundings run straight along their normal, as movable faces (thickness, height).
Left in the blank: everything else (drill points, slots, threads, variable fillets, freeform shapes, drafts)."""
import math

import FreeCAD as App
import Part

from . import fc_tools

TWO_PI = 2 * math.pi


def _canon(v):
    """Same direction for both orientations of an axis: the dominant component positive."""
    big = max(range(3), key=lambda i: abs(v[i]))
    return v if v[big] > 0 else v * -1


# ------------------------------------------------------------------ holes
def find_holes(ref, min_radius=0.2):
    """Complete concave cylinders of the shape: [{"axis", "foot", "radius", "t0", "t1", "faces"}], where a point
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


def _hole_key(h):
    """Identity of a hole that survives rebuilding the shape (face numbers do not)."""
    return (round(h["axis"].x, 4), round(h["axis"].y, 4), round(h["axis"].z, 4), round(h["foot"].x, 3),
            round(h["foot"].y, 3), round(h["foot"].z, 3), round(h["radius"], 4), round(h["t0"], 3), round(h["t1"], 3))


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


# ------------------------------------------------------------------ fillets and chamfers
def _neighbours(shape):
    """face index -> [(edge, other face index)] via shared edges."""
    by_edge = {}
    for i, f in enumerate(shape.Faces):
        for e in f.Edges:
            by_edge.setdefault(e.hashCode(), []).append((e, i))
    out = {i: [] for i in range(len(shape.Faces))}
    for items in by_edge.values():
        for a in range(len(items)):
            for b in range(len(items)):
                if a != b and items[a][1] != items[b][1] and items[a][0].isSame(items[b][0]):
                    out[items[a][1]].append((items[a][0], items[b][1]))
    return out


def _normal_at(face, p):
    try:
        return face.normalAt(*face.Surface.parameter(p))
    except Exception:
        return None


def _edge_mid(e):
    return e.valueAt((e.FirstParameter + e.LastParameter) / 2.0)


def find_blends(shape):
    """Faces that look like dress-up features: {("fillet", radius) | ("chamfer",): [face indices]}.

    fillet : a partial cylinder / torus / sphere that runs smoothly (tangent) into at least two different
             neighbours which are not the same surface (that would be the other half of a hole or shaft);
    chamfer: a narrow plane or a cone that meets two neighbours along its long edges at the same sharp angle.
    This is only a first guess - build() keeps a group only if putting it back reproduces the reference."""
    faces = shape.Faces
    nb = _neighbours(shape)
    groups = {}
    for i, f in enumerate(faces):
        s = f.Surface
        kind = type(s).__name__
        if kind in ("Cylinder", "Toroid", "Sphere"):
            radius = s.MinorRadius if kind == "Toroid" else s.Radius
            u0, u1, v0, v1 = f.ParameterRange
            if kind == "Cylinder" and abs(u1 - u0) > math.pi + 1e-6:
                continue                                    # more than half a turn: a hole, boss or shaft
            if kind == "Toroid" and abs(v1 - v0) > math.pi + 1e-6:
                continue
            smooth = set()
            for e, j in nb[i]:
                g = faces[j]
                gs = g.Surface
                if type(gs).__name__ == kind == "Cylinder" and abs(gs.Radius - s.Radius) < 1e-6 \
                        and gs.Axis.cross(s.Axis).Length < 1e-6 \
                        and (gs.Center - s.Center).cross(s.Axis).Length < 1e-6:
                    smooth = set()
                    break                                   # the other half of the same cylinder
                p = _edge_mid(e)
                n1, n2 = _normal_at(f, p), _normal_at(g, p)
                if n1 is not None and n2 is not None and n1.getAngle(n2) < math.radians(1.0):
                    smooth.add(j)
            if len(smooth) >= 2:
                groups.setdefault(("fillet", round(radius, 4)), []).append(i)
        elif kind in ("Plane", "Cone"):
            edges = sorted(f.Edges, key=lambda e: -e.Length)
            if len(edges) < 2 or (kind == "Plane" and len(f.Edges) != 4):
                continue
            long_edges = edges[:2]
            if kind == "Plane":
                width = f.Area / max(long_edges[0].Length, 1e-9)
                if width > 0.35 * long_edges[0].Length:
                    continue                                # not a narrow strip
            angles = []
            for e, j in nb[i]:
                if not any(e.isSame(x) for x in long_edges):
                    continue
                p = _edge_mid(e)
                n1, n2 = _normal_at(f, p), _normal_at(faces[j], p)
                if n1 is not None and n2 is not None:
                    angles.append(n1.getAngle(n2))
            if len(angles) == 2 and abs(angles[0] - angles[1]) < math.radians(1.0) \
                    and math.radians(20) < angles[0] < math.radians(70):
                groups.setdefault(("chamfer",), []).append(i)
    return groups


def _defeature(shape, face_ids):
    """Shape without those faces (neighbours extended), or None if the kernel cannot do it cleanly."""
    try:
        out = shape.defeaturing([shape.Faces[i] for i in face_ids])
    except Exception:
        return None
    if out.isNull() or not out.isValid() or len(out.Solids) != len(shape.Solids) or len(out.Faces) >= len(shape.Faces):
        return None
    if abs(out.Volume - shape.Volume) > 0.2 * shape.Volume:      # a dress-up never changes the volume that much
        return None
    return out.Solids[0] if len(out.Solids) == 1 else out


# ------------------------------------------------------------------ building
def _cut_holes(sess, target, report, exclude):
    """Fill the holes of `target`, use that as blank and cut them again. Returns the set of holes that failed."""
    holes = []
    for h in find_holes(target):
        key = _hole_key(h)
        if key in exclude:
            continue
        plug = _plug(h)
        try:
            overlap = plug.common(target).Volume
        except Exception:
            overlap = plug.Volume
        if overlap > 1e-6 * plug.Volume:        # something stands inside this cylinder: not a plain drilled hole
            report["skipped"].append(f"hole D{2 * h['radius']:g}: not empty inside")
            continue
        h["key"], h["plug"] = key, plug
        h["end"], h["out"] = _open_end(target, h)
        holes.append(h)
    if not holes:
        sess.import_shape(target, "blank (no holes turned into features)")
        return set()
    blank = target.fuse([h["plug"] for h in holes])
    try:
        refined = blank.copy().removeSplitter()
        if refined.isValid() and abs(refined.Volume - blank.Volume) <= 2e-4 * max(1.0, blank.Volume):
            blank = refined
    except Exception:
        pass
    if len(blank.Solids) == 1:
        blank = blank.Solids[0]
    sess.import_shape(blank, f"blank ({len(holes)} holes filled)")

    jobs = {}       # equal holes drilled from the same face in the same direction -> one feature
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
            failed.update(h["key"] for h in group)
            continue
        feat = sess.doc.getObject(r["feature"])
        d = round(2 * h0["radius"], 3)
        feat.Label = f"Hole_D{d:g}" + (f"_x{len(group)}" if len(group) > 1 else "")
        report["holes_made"] += len(group)
        report["features"] += 1
    return failed


def _dress(sess, report):
    """Put fillets and chamfers back: the sharp edges of the solid that the reference lacks, with the sizes
    measured there (Session.list_edges). Each group must bring the solid closer to the reference."""
    for _ in range(40):
        todo = [e for e in sess.list_edges(only_missing=True).get("edges", []) if e.get("suggest")]
        todo = [e for e in todo if str(e["suggest"]) not in report["_refused"]]
        if not todo:
            return
        # largest first: a big fillet has to exist before a small one can run over its end
        first = max((e["suggest"] for e in todo), key=lambda s: list(s.values())[0])
        ids = [e["edge"] for e in todo if e["suggest"] == first]
        before = sess.compare()["xor_pct"]
        kind, size = list(first.items())[0]
        r = sess.fillet(ids, size) if kind == "fillet" else sess.chamfer(ids, size)
        if r.get("ok") and sess.compare()["xor_pct"] < before - 1e-9:
            feat = sess.doc.getObject(r["feature"])
            feat.Label = (f"Fillet_R{size:g}" if kind == "fillet" else f"Chamfer_{size:g}") + \
                (f"_x{len(ids)}" if len(ids) > 1 else "")
            report[kind + "s_made"] += len(ids)
            report["features"] += 1
        else:
            if r.get("ok"):
                sess.undo()
            report["_refused"].add(str(first))


def _thickness(shape, face, normal):
    """How much material lies straight behind a planar face: probed at several points, the value met most often
    wins (under a chamfer or beside a boss the depth differs locally). 0 if unknown."""
    try:
        verts, tris = face.tessellate(max(shape.BoundBox.DiagonalLength * 0.01, 1e-3))
        reach = shape.BoundBox.DiagonalLength * 1.1
        found = []
        step = max(1, len(tris) // 24)
        for a, b, c in tris[::step][:24]:
            p = (verts[a] + verts[b] + verts[c]) * (1.0 / 3.0)
            line = Part.makeLine(p - normal * 1e-4, p - normal * reach)
            for e in line.common(shape).Edges:
                ends = [e.valueAt(e.FirstParameter), e.valueAt(e.LastParameter)]
                if min(v.distanceToPoint(p) for v in ends) < 1e-3:      # the stretch that starts at the face
                    found.append(round(e.Length + 1e-4, 3))
                    break
        if not found:
            return 0.0
        counts = {}
        for v in found:
            counts[v] = counts.get(v, 0) + 1
        top = max(counts.values())
        return min(v for v, k in counts.items() if k == top)
    except Exception:
        return 0.0


def add_face_moves(sess, report, limit=12):
    """Make the position of flat faces a parameter (plate thickness, boss height, depth of a seat ...).

    A face qualifies if everything around it runs straight along its normal - planes square to it, cylinders
    parallel to its normal - so pushing or pulling it simply lengthens or shortens those neighbours. Each such
    face gets a Pad (push out) and a Pocket (push in) taken directly from the face, both switched off until the
    parameter asks for a move; because the profile is the face itself, they follow changes made further up
    (hole sizes, fillets). The largest `limit` faces are offered."""
    body = sess.body
    anchor = body.Tip
    if anchor is None:
        return
    shape = anchor.Shape
    nb = _neighbours(shape)
    cands = []
    for i, f in enumerate(shape.Faces):
        if type(f.Surface).__name__ != "Plane" or not nb[i]:
            continue
        u0, u1, v0, v1 = f.ParameterRange
        n = f.normalAt((u0 + u1) / 2, (v0 + v1) / 2)
        ok = True
        for _, j in nb[i]:
            gs = shape.Faces[j].Surface
            kind = type(gs).__name__
            if kind == "Plane":
                ok = abs(App.Vector(gs.Axis).normalize().dot(n)) < 1e-6
            elif kind == "Cylinder":
                ok = App.Vector(gs.Axis).cross(n).Length < 1e-6
            else:
                ok = False
            if not ok:
                break
        if ok:
            cands.append((f.Area, i, n))
    cands.sort(key=lambda c: -c[0])
    made = 0
    for area, i, n in cands[:limit]:
        name = f"Face{i + 1}"
        thick = _thickness(shape, shape.Faces[i], n)
        test = min(1.0, 0.25 * thick) if thick > 0 else 1.0
        before = body.Tip.Shape.Volume
        pad = body.newObject("PartDesign::Pad", "FaceMove")
        pad.Profile = (anchor, [name])
        pad.Length = test
        cut = body.newObject("PartDesign::Pocket", "FaceMoveIn")
        cut.Profile = (anchor, [name])
        cut.Length = test
        good = False
        try:
            cut.Suppressed = True
            sess.doc.recompute()
            grew = pad.isValid() and abs((pad.Shape.Volume - before) - area * test) <= 2e-3 * area * test
            pad.Suppressed, cut.Suppressed = True, False
            sess.doc.recompute()
            shrank = cut.isValid() and abs((before - cut.Shape.Volume) - area * test) <= 2e-3 * area * test
            cut.Suppressed = True
            sess.doc.recompute()
            good = grew and shrank and abs(body.Tip.Shape.Volume - before) <= 1e-9 * max(before, 1.0)
        except Exception:
            good = False
        if not good:
            for o in (cut, pad):
                sess.doc.removeObject(o.Name)
            feats = [o for o in body.Group if o.isDerivedFrom("PartDesign::Feature")]
            body.Tip = feats[-1]
            sess.doc.recompute()
            continue
        made += 1
        pad.Label = f"Face_{made}"
        cut.Label = f"Face_{made}_in"
        pad.addProperty("App::PropertyString", "SR_Pair", "steprecon", "pocket that moves this face inward")
        pad.addProperty("App::PropertyFloat", "SR_Thickness", "steprecon", "material behind the face at the start")
        pad.SR_Pair, pad.SR_Thickness = cut.Name, float(thick)
        sess._record([cut.Name, pad.Name], f"movable face {made} (thickness {thick:g})")
    report["faces_made"] = made
    report["features"] += made


def _attempt(ref, blend_faces, exclude_holes):
    """One build: take `blend_faces` off, holes out, everything back on. Returns (session, report, identical)."""
    report = {"holes_made": 0, "fillets_made": 0, "chamfers_made": 0, "faces_made": 0, "features": 0, "skipped": [],
              "_refused": set()}
    target = ref
    if blend_faces:
        target = _defeature(ref, blend_faces)
        if target is None:
            return None, report, False
    sess = fc_tools.Session(ref)
    failed = _cut_holes(sess, target, report, exclude_holes)
    if failed:
        App.closeDocument(sess.doc.Name)
        return _attempt(ref, blend_faces, exclude_holes | failed)
    if blend_faces:
        _dress(sess, report)
    c = sess.compare()
    report["_excluded_holes"] = exclude_holes
    return sess, report, bool(c.get("converged"))


def build(ref):
    """Reference -> (Session with blank + features, report dict). The result is always identical to the reference:
    dress-ups that do not come back exactly are given up (first as a whole, then group by group)."""
    blends = find_blends(ref)
    everything = sorted(i for ids in blends.values() for i in ids)
    plans = [everything] if everything else []
    if len(blends) > 1:
        plans += [sorted(ids) for _, ids in sorted(blends.items(), key=lambda kv: str(kv[0]))]
    best = None
    good_groups = []
    for faces in plans:
        sess, report, same = _attempt(ref, faces, set())
        if sess is None:
            continue
        if same and faces == everything:
            best = (sess, report)
            break
        if same:
            good_groups.append(faces)
        App.closeDocument(sess.doc.Name)
    if best is None and good_groups:        # combine the groups that worked on their own, else take the biggest
        for faces in ([sorted(i for g in good_groups for i in g)] if len(good_groups) > 1 else []) \
                + [max(good_groups, key=len)]:
            sess, report, same = _attempt(ref, faces, set())
            if sess is not None and same:
                best = (sess, report)
                break
            if sess is not None:
                App.closeDocument(sess.doc.Name)
    if best is None:                        # holes only: identical by construction
        sess, report, _ = _attempt(ref, [], set())
        best = (sess, report)
    sess, report = best
    try:
        add_face_moves(sess, report)
    except Exception as e:      # an extra: the part itself is complete without it
        report["skipped"].append(f"movable faces: {type(e).__name__}: {e}")
    for key in sorted(report.pop("_excluded_holes", set())):
        report["skipped"].append(f"hole D{2 * key[6]:g}: could not be cut again cleanly")
    refused = report.pop("_refused", set())
    found = {("fillet R%g" % k[1]) if k[0] == "fillet" else "chamfer": len(v) for k, v in blends.items()}
    report["blend_faces_found"] = found
    if found and not (report["fillets_made"] or report["chamfers_made"]):
        report["skipped"].append("fillets/chamfers: could not be reproduced exactly, left in the blank")
    elif refused:
        report["skipped"].append("some fillets/chamfers left in the blank: " + ", ".join(sorted(refused)))
    return sess, report
