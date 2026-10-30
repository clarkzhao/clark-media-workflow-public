"""Review an exported revision snapshot; never edit media or infer user approval.

Public interface: review(manifest, root, motion_probe=None) -> report.
No media dependencies unless the optional motion Adapter is requested.
"""
from __future__ import annotations

import argparse
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import re
import sys


CATEGORIES = ("technical", "semantic", "playback", "acceptance")
MEDIA_KINDS = {"still", "video", "svg_animation", "blender_sequence"}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _sha(value):
    _require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value),
             "expected a lowercase SHA256")
    return value


def _number(value):
    _require(isinstance(value, (int, float, str)) and not isinstance(value, bool),
             "expected a finite number")
    result = Decimal(str(value))
    _require(result.is_finite(), "expected a finite number")
    return result


def _pointer(document, pointer):
    _require(isinstance(pointer, str) and pointer.startswith("/"),
             "fact pointer must be a nonempty JSON pointer")
    for part in pointer[1:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(document, list):
            _require(part.isdecimal(), "array pointer must be a nonnegative index")
            document = document[int(part)]
        else:
            document = document[part]
    return document


def _display(value, source_unit, display_unit, decimals):
    _require(isinstance(decimals, int) and not isinstance(decimals, bool)
             and 0 <= decimals <= 6, "decimals must be 0..6")
    if source_unit != display_unit:
        factors = {("s", "min"): Decimal(1) / 60, ("min", "s"): Decimal(60)}
        _require((source_unit, display_unit) in factors, "unsupported unit conversion")
        value *= factors[(source_unit, display_unit)]
    return format(value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP), "f")


def review(manifest: dict, root: Path, motion_probe=None) -> dict:
    """Check declared dependencies, fact uses, decisions and scene motion.

    Returns invalid/stale artifact IDs and separate coverage categories. Numeric
    bindings are declarations from the renderer, NOT OCR/ASR of final media.
    motion_probe(path, spec) must return status passed/failed/unknown plus evidence.
    """
    root = Path(root).resolve()
    checks, invalid, actual, paths, facts = [], set(), {}, {}, {}
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be an object")

    def add(code, target, status, detail):
        checks.append(dict(code=code, target=target, status=status, detail=detail))

    def attempt(code, target, operation):
        try:
            operation()
        except (ValueError, TypeError, KeyError, IndexError, OSError, ArithmeticError) as exc:
            add(code, target, "failed", str(exc))
            return False
        return True

    def structure():
        _require(manifest.get("schema_version") == 1, "schema_version must be 1")
        _require(isinstance(manifest.get("revision"), str) and manifest["revision"], "revision required")
        for name in ("inputs", "artifacts"):
            _require(isinstance(manifest.get(name), dict) and manifest[name], f"nonempty {name} required")
            _require(all(isinstance(k, str) and k and isinstance(v, dict) for k, v in manifest[name].items()),
                     f"{name} must map nonempty IDs to objects")
        _require(not set(manifest["inputs"]) & set(manifest["artifacts"]), "input and artifact IDs must differ")
        for name in ("experiments", "facts"):
            _require(isinstance(manifest.get(name, {}), dict), f"{name} must be an object")
            _require(all(isinstance(v, dict) for v in manifest.get(name, {}).values()), f"{name} entries must be objects")
        for name in ("bindings", "decisions", "scenes", "reviews", "required_reviews"):
            _require(isinstance(manifest.get(name, []), list), f"{name} must be an array")
            if name != "required_reviews":
                _require(all(isinstance(v, dict) for v in manifest.get(name, [])), f"{name} entries must be objects")
        _require(set(manifest.get("required_reviews", [])) <= set(CATEGORIES), "unknown review category")
        targets = manifest.get("review_targets", {})
        _require(isinstance(targets, dict) and set(targets) <= set(CATEGORIES), "invalid review_targets")
        for category, ids in targets.items():
            _require(isinstance(ids, list) and ids and set(ids) <= set(manifest["artifacts"]),
                     f"review_targets.{category} must list registered artifacts")

    if not attempt("schema", "manifest", structure):
        return dict(revision=manifest.get("revision"), automated_status="failed", checks=checks,
                    invalidated=[], display_facts={}, coverage={c: "unknown" for c in CATEGORIES},
                    required_uncovered=manifest.get("required_reviews", []))

    artifacts = manifest["artifacts"]
    nodes = {**manifest["inputs"], **artifacts}
    for node_id, node in nodes.items():
        def inspect_file():
            _require(isinstance(node_id, str) and node_id, "nonempty node ID required")
            _require(isinstance(node, dict), "node must be an object")
            _require(isinstance(node.get("path"), str) and node["path"], "path required")
            expected = _sha(node.get("sha256"))
            paths[node_id] = (root / node["path"]).resolve()
            with paths[node_id].open("rb") as stream:
                actual[node_id] = hashlib.file_digest(stream, "sha256").hexdigest()
            _require(actual[node_id] == expected, "file changed since this snapshot")
            add("file", node_id, "passed", "content matches snapshot")
        if not attempt("file", node_id, inspect_file):
            invalid.add(node_id)

    dependencies = {}
    for node_id, node in artifacts.items():
        def inspect_dependencies():
            deps = node.get("depends_on")
            _require(isinstance(deps, dict) and deps, "artifact requires build-time dependency hashes")
            dependencies[node_id] = set(deps)
            for dep, built_hash in deps.items():
                _require(dep in nodes, f"unknown dependency: {dep}")
                _require(_sha(built_hash) == actual.get(dep), f"stale dependency: {dep}")
        if not attempt("dependency", node_id, inspect_dependencies):
            invalid.add(node_id)

    visiting, visited = set(), set()

    def visit(node_id):
        if node_id in visiting:
            raise ValueError(f"dependency cycle at {node_id}")
        if node_id in visited:
            return
        visiting.add(node_id)
        for dep in dependencies.get(node_id, set()):
            visit(dep)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in artifacts:
        if not attempt("dependency_graph", node_id, lambda: visit(node_id)):
            invalid.add(node_id)
            visiting.clear()

    def propagate():
        while True:
            stale = {n for n, deps in dependencies.items() if deps & invalid} - invalid
            if not stale:
                break
            invalid.update(stale)
            for n in sorted(stale):
                add("dependency", n, "failed", "upstream artifact/input is invalid")
    propagate()

    experiments, documents = {}, {}
    for exp_id, exp in manifest.get("experiments", {}).items():
        def inspect_experiment():
            _require(exp["input"] in manifest["inputs"], "experiment must reference a registered input")
            _require(exp["input"] not in invalid, "experiment input is stale/missing")
            _require(exp["kind"] in {"sample", "expectation_estimate", "analytic", "observation"}, "unknown evidence kind")
            for field in ("metric", "population", "conditions", "method", "unit", "display_unit"):
                _require(isinstance(exp.get(field), str) and exp[field].strip(), f"{field} required")
            if exp["kind"] == "expectation_estimate":
                _require(isinstance(exp.get("replicates"), int) and exp["replicates"] >= 2, "independent replicate count required")
                _require(bool(exp.get("sampling")) and bool(exp.get("uncertainty")), "sampling and uncertainty method required")
            _display(Decimal(0), exp["unit"], exp["display_unit"], exp["decimals"])
            documents[exp_id] = json.loads(paths[exp["input"]].read_text(encoding="utf-8-sig"))
            experiments[exp_id] = exp
        attempt("experiment", exp_id, inspect_experiment)

    for fact_id, fact in manifest.get("facts", {}).items():
        def inspect_fact():
            exp_id = fact["experiment"]
            exp = experiments[exp_id]
            value = _number(_pointer(documents[exp_id], fact["pointer"]))
            facts[fact_id] = dict(value=_display(value, exp["unit"], exp["display_unit"], exp["decimals"]),
                                  unit=exp["display_unit"], experiment=exp_id, kind=exp["kind"])
        attempt("fact", fact_id, inspect_fact)

    def ancestors(node_id, seen=None):
        seen = set() if seen is None else seen
        for dep in dependencies.get(node_id, set()):
            if dep not in seen:
                seen.add(dep)
                ancestors(dep, seen)
        return seen

    for index, binding in enumerate(manifest.get("bindings", [])):
        def inspect_binding():
            target, fact_id = binding["artifact"], binding["fact"]
            _require(target in artifacts, "unknown bound artifact")
            _require(target not in invalid, "bound artifact is stale")
            fact = facts[fact_id]
            _require(binding["value"] == fact["value"] and binding["unit"] == fact["unit"], "value/unit differs from shared display fact")
            _require(experiments[fact["experiment"]]["input"] in ancestors(target), "bound artifact lacks result dependency")
            add("binding", str(index), "passed", "declared number and unit match result")
        attempt("binding", str(index), inspect_binding)

    decision_ids = set()
    for index, decision in enumerate(manifest.get("decisions", [])):
        def inspect_decision():
            _require(decision["id"] not in decision_ids, "duplicate active decision ID")
            decision_ids.add(decision["id"])
            _require(bool(decision.get("scope")) and bool(decision.get("instruction")), "decision scope and instruction required")
            targets = decision["targets"]
            _require(isinstance(targets, list) and targets, "decision targets required")
            for target in targets:
                _require(target in artifacts and target not in invalid, f"invalid decision target: {target}")
                _require(_sha(decision.get("applied", {}).get(target)) == actual[target], f"decision not applied to current content: {target}")
            add("decision", decision["id"], "passed", "recorded application covers all declared targets")
        attempt("decision", str(index), inspect_decision)

    scene_ids = set()
    for index, scene in enumerate(manifest.get("scenes", [])):
        def inspect_scene():
            _require(scene["id"] not in scene_ids, "duplicate scene ID")
            scene_ids.add(scene["id"])
            target = scene["artifact"]
            _require(target in artifacts and target not in invalid, "scene artifact is invalid")
            _require(scene["media_kind"] in MEDIA_KINDS, "unknown media kind")
            _require(isinstance(scene["motion_required"], bool), "motion_required must be explicit")
            if not scene["motion_required"]:
                _require(bool(scene.get("static_reason")), "explain intentional static/unchecked motion")
                add("motion", scene["id"], "not_required", scene["static_reason"])
                return
            _require(scene["media_kind"] != "still", "required action cannot use a still")
            _require(bool(scene.get("action")), "describe required action")
            _require(isinstance(scene.get("motion"), dict), "motion window/region required")
            if motion_probe is None:
                add("motion", scene["id"], "unknown", "optional motion probe was not run")
                return
            try:
                result = motion_probe(paths[target], scene["motion"])
                _require(result.get("status") in {"passed", "failed", "unknown"}, "invalid probe status")
                add("motion", scene["id"], result["status"], result)
            except Exception as exc:
                # Optional decoder/registration failures must never turn green.
                add("motion", scene["id"], "unknown", f"probe unavailable: {type(exc).__name__}: {exc}")
        attempt("scene", str(index), inspect_scene)

    records = {}
    for index, record in enumerate(manifest.get("reviews", [])):
        def inspect_review():
            target, category = record["artifact"], record["category"]
            _require(category in CATEGORIES and target in artifacts, "unknown review target/category")
            _require((target, category) not in records, "duplicate review; export only current decision")
            _require(target not in invalid and _sha(record["sha256"]) == actual[target], "review belongs to stale content")
            _require(record["status"] in {"passed", "failed", "partial"}, "invalid review status")
            _require(bool(record.get("reference")) and bool(record.get("reviewer")), "review evidence reference and reviewer required")
            _require(record.get("scope") == "whole_artifact" or record["status"] != "passed", "partial review cannot pass the whole artifact")
            records[(target, category)] = record["status"]
        attempt("review", str(index), inspect_review)

    coverage = {}
    uncovered = {}
    for category in CATEGORIES:
        targets = manifest.get("review_targets", {}).get(category, list(artifacts))
        values = [records.get((target, category), "unknown") for target in targets]
        coverage[category] = "failed" if "failed" in values else "passed" if all(v == "passed" for v in values) else "unknown"
        uncovered[category] = [t for t in targets if records.get((t, category)) != "passed"]
    required = manifest.get("required_reviews", [])
    statuses = [c["status"] for c in checks]
    automated = "failed" if "failed" in statuses else "incomplete" if "unknown" in statuses else "passed"
    return dict(revision=manifest["revision"], automated_status=automated, checks=checks,
                invalidated=sorted(invalid & set(artifacts)), display_facts=facts, coverage=coverage,
                uncovered=uncovered, required_uncovered=[c for c in required if coverage[c] != "passed"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--report", type=Path, help="New local JSON report; otherwise stdout")
    parser.add_argument("--motion", action="store_true", help="Use installed PyAV/OpenCV/numpy; no downloads")
    args = parser.parse_args()
    if args.report and args.report.exists():
        parser.error("report exists; use a new output path")
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    probe = None
    if args.motion:
        from motion_probe import probe_motion
        probe = probe_motion
    result = review(manifest, args.manifest.resolve().parent, probe)
    content = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as stream:
            stream.write(content + "\n")
    print(content)
    return 1 if result["automated_status"] == "failed" else 2 if result["automated_status"] == "incomplete" or result["required_uncovered"] else 0


if __name__ == "__main__":
    sys.exit(main())
