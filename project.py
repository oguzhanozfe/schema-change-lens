"""Compare a small, explicit JSON payload contract from an input consumer's perspective."""

import math

TITLE = "Schema Change Lens"
DESCRIPTION = "See which JSON contract changes can reject payloads accepted by the earlier version."
PROMPT = "Review the directional input-compatibility findings. Use the JSON pointer and old/new constraints. Avoid claims about output clients or features outside the supported subset."

TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}
BOUNDS = {"string": ("minLength", "maxLength"), "array": ("minItems", "maxItems"),
          "integer": ("minimum", "maximum"), "number": ("minimum", "maximum")}


def validate(s, path):
    if not isinstance(s, dict) or not isinstance(s.get("type"), str) or s["type"] not in TYPES:
        raise ValueError(f"{path} needs one supported 'type'.")
    typ = s["type"]
    allowed = {"type", "description", "title"} | set(BOUNDS.get(typ, ()))
    if typ == "object":
        allowed |= {"properties", "required", "additionalProperties"}
        props, req = s.get("properties", {}), s.get("required", [])
        if not isinstance(props, dict) or not all(isinstance(k, str) for k in props):
            raise ValueError(f"Invalid properties at {path}.")
        if not isinstance(req, list) or any(not isinstance(k, str) or k not in props for k in req) or len(set(req)) != len(req):
            raise ValueError(f"Required names must be unique declared properties at {path}.")
        if not isinstance(s.get("additionalProperties", True), bool):
            raise ValueError("Only boolean additionalProperties is supported.")
        for name, child in props.items():
            validate(child, path + "/" + name)
    if typ == "array":
        allowed.add("items")
        if "items" in s:
            validate(s["items"], path + "/items")
    if typ in BOUNDS:
        lo, hi = BOUNDS[typ]
        for k in (lo, hi):
            if k in s:
                v = s[k]
                if type(v) not in (float, int) or not math.isfinite(v):
                    raise ValueError(f"Invalid {k} at {path}.")
                if typ in ("string", "array") and (type(v) != int or v < 0):
                    raise ValueError(f"{k} must be a nonnegative integer.")
        if lo in s and hi in s and s[lo] > s[hi]:
            raise ValueError(f"Contradictory bounds at {path}.")
    extra = set(s) - allowed
    if extra:
        raise ValueError(f"Unsupported constraints at {path}: {', '.join(sorted(extra))}")


def analyze(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Provide before and after schema objects.")
    before, after = data.get("before"), data.get("after")
    validate(before, "$")
    validate(after, "$")
    rows = []

    def report(path, constraint, original, updated, narrowing):
        rows.append({"Pointer": path or "(root)", "Constraint": constraint, "Before": str(original),
                     "After": str(updated), "Impact": "Can reject old input" if narrowing else "Compatible"})

    def compare(a, b, path):
        ta, tb = a["type"], b["type"]
        if ta != tb:
            report(path, "type", ta, tb, (ta, tb) != ("integer", "number"))
            if {ta, tb} != {"integer", "number"}:
                return
        if tb in BOUNDS:
            for idx, bound in enumerate(BOUNDS[tb]):
                old, new = a.get(bound), b.get(bound)
                # Lengths and item counts have an implicit lower bound of zero.
                implied = 0 if idx == 0 and tb in ("string", "array") else None
                old = implied if old is None else old
                new = implied if new is None else new
                if old != new:
                    reduced = new is not None and (old is None or (new > old if idx == 0 else new < old))
                    report(path, bound, old if old is not None else "unbounded",
                           new if new is not None else "unbounded", reduced)
        if tb == "array":
            if "items" in a and "items" in b:
                compare(a["items"], b["items"], path + "/items")
            elif ("items" in a) != ("items" in b):
                report(path + "/items", "items", a.get("items", {}).get("type", "any"),
                       b.get("items", {}).get("type", "any"), "items" in b)
        if tb != "object":
            return
        ap, bp = a.get("properties", {}), b.get("properties", {})
        open_a, open_b = a.get("additionalProperties", True), b.get("additionalProperties", True)
        if open_a != open_b:
            report(path, "additionalProperties", open_a, open_b, not open_b)
        for k in sorted(set(ap) | set(bp)):
            child = path + "/properties/" + k.replace("~", "~0").replace("/", "~1")
            old_req, new_req = k in a.get("required", []), k in b.get("required", [])
            if old_req != new_req:
                report(child, "required", old_req, new_req, new_req)
            if k in ap and k in bp:
                compare(ap[k], bp[k], child)
            elif k in bp:
                report(child, "property", "any" if open_a else "not allowed", bp[k]["type"], open_a)
            else:
                report(child, "property", ap[k]["type"], "any" if open_b else "not allowed", not open_b)
    compare(before, after, "")
    narrowing = sum(x["Impact"] == "Can reject old input" for x in rows)
    return {"summary": f"{len(rows)} constraint changes, including {narrowing} local compatibility risks.",
            "metrics": {"Changes":len(rows), "Narrowing":narrowing, "Compatible":len(rows)-narrowing}, "rows":rows}
