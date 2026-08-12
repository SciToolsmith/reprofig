#!/usr/bin/env python3
"""Create, validate, or expand token-efficient SciRepro report authoring JSON."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from build_report import ReportError, bind_target_manifest, load_target_manifest, validate_report


COMPACT_SCHEMA = "scirepro.compact-report/v1"
TODO_PREFIX = "TODO::"
CATEGORIES = ("input", "method", "protocol", "validation", "environment")
AUTOMATIC_EFFECTS = {"run-local-code", "create-workspace-files"}
GATED_EFFECTS = {
    "network", "install", "login", "payment", "upload", "overwrite", "gpu",
    "shared-license", "external-publish",
}
ID_LIMIT = 128


class ScaffoldError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ScaffoldError(message)


def exact_keys(value: object, keys: set[str], label: str) -> dict:
    require(isinstance(value, dict), f"{label} must be an object")
    require(set(value) == keys, f"{label} fields must be exactly {sorted(keys)}")
    return value


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def todo(label: str) -> str:
    return f"{TODO_PREFIX}{label}"


def stable_id(prefix: str, value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._") or "target"
    candidate = f"{prefix}-{slug}"
    if len(candidate) <= ID_LIMIT:
        return candidate
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    keep = ID_LIMIT - len(prefix) - len(digest) - 2
    return f"{prefix}-{slug[:keep].rstrip('-._')}-{digest}"


def todo_locations(value: object, path: str = "$") -> Iterator[str]:
    if isinstance(value, str) and TODO_PREFIX in value:
        yield path
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from todo_locations(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from todo_locations(child, f"{path}[{index}]")


def atomic_create_json(path: Path, value: object) -> None:
    require(not path.exists(), f"output already exists (create-only): {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    require(path.parent.is_dir() and not path.parent.is_symlink(), f"output parent must be a real directory: {path.parent}")
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    temporary: Path | None = None
    try:
        fd, name = tempfile.mkstemp(prefix=f".{path.name}.tmp-", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)
    except FileExistsError as exc:
        raise ScaffoldError(f"output already exists (create-only): {path}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def base_source(manifest: dict) -> tuple[dict, str]:
    checked_at = manifest.get("createdAt") or utc_now()
    if manifest.get("paper") is not None:
        return (
            {
                "sourceId": "src-paper",
                "kind": "paper",
                "title": "Paper preserved in the verified Phase 0 target set",
                "access": {"state": "local", "checkedAt": checked_at},
                "license": {"state": "unknown"},
            },
            "src-paper",
        )
    return (
        {
            "sourceId": "src-target-set",
            "kind": "target-image",
            "title": "Verified Phase 0 target set",
            "access": {"state": "local", "checkedAt": checked_at},
            "license": {"state": "unknown"},
        },
        "src-target-set",
    )


def compact_condition(category: str) -> dict:
    return {
        "state": todo(f"{category}-state"),
        "blocking": True,
        "detail": todo(f"{category}-evidence-gap-or-resolution"),
    }


def compact_figure(target: dict) -> dict:
    image_derived = target["workflowMode"] == "image-derived-reconstruction"
    return {
        "targetId": target["targetId"],
        "section": None,
        "understanding": {
            "visualSummary": todo("visible-figure-summary"),
            "observations": [
                {
                    "location": todo("observation-location"),
                    "statement": todo("directly-visible-observation"),
                    "confidence": todo("high-medium-or-low"),
                }
            ],
            "paperClaim": None if image_derived else todo("paper-claim"),
            "evidenceRole": todo("evidence-role-or-bounded-visual-scope"),
            "authorInterpretation": None if image_derived else todo("author-interpretation"),
            "limitations": [todo("material-limit")],
        },
        "generation": {
            "inputs": [
                {
                    "label": todo("input-label"),
                    "description": todo("input-origin-and-content"),
                    "origin": todo("paper-code-derived-assumption-or-user"),
                }
            ],
            "steps": [
                {
                    "label": todo("generation-step"),
                    "description": todo("method-to-output-description"),
                    "origin": todo("paper-code-derived-assumption-or-user"),
                }
            ],
            "plotMapping": {
                "description": todo("data-to-visible-plot-mapping"),
                "encodings": [todo("axis-legend-panel-or-mark-encoding")],
            },
            "unknowns": [todo("remaining-unknown-or-explicit-none")],
        },
        "validation": [
            {
                "label": todo("validation-label"),
                "kind": todo("qualitative-pattern-quantitative-comparative-structural-or-visual-fidelity"),
                "origin": todo("paper-code-derived-assumption-or-user"),
                "observable": todo("observable-result"),
                "criterion": todo("success-criterion"),
                "supportsClaim": todo("supported-and-unsupported-claim-scope"),
            }
        ],
        "assessment": {
            "level": "image-derived-reconstruction" if image_derived else todo("reproduction-level"),
            "verdict": todo("bounded-verdict"),
            "confidence": todo("high-medium-or-low"),
            "rationale": todo("evidence-backed-assessment"),
        },
        "route": {
            "label": todo("single-route-label"),
            "status": todo("ready-conditional-or-blocked"),
            "goal": todo("scientific-or-bounded-visual-goal"),
            "claimCoverage": todo("route-claim-coverage"),
            "doesNotReproduce": [todo("explicit-route-boundary")],
            "substitutions": [],
            "assumptions": [],
            "rationale": todo("why-this-route"),
            "engine": todo("runtime-or-tool"),
            "environmentIds": [],
            "conditions": {category: compact_condition(category) for category in CATEGORIES},
            "deliverables": [],
            "parameters": [],
            "effects": ["run-local-code", "create-workspace-files"],
            "estimated": {
                "downloadBytes": None,
                "diskBytes": None,
                "runtimeMinutes": None,
                "gpu": False,
                "costUsd": None,
            },
            "plan": [todo("short-execution-step")],
            "blockers": [todo("current-blocker-or-remove-when-executable")],
        },
    }


def init_compact(manifest: dict, targets: dict[str, dict], audience: str) -> dict:
    paper = manifest.get("paper")
    return {
        "schemaVersion": COMPACT_SCHEMA,
        "mode": "compact",
        "reportId": stable_id("rpt", f"{manifest['targetSetId']}-compact"),
        "generatedAt": utc_now(),
        "audience": audience,
        "targetManifestSha256": manifest["integrity"]["manifestSha256"],
        "objective": todo("researcher-reproduction-objective"),
        "oneLine": todo("one-line-overall-assessment"),
        "paper": None if paper is None else {
            "title": todo("paper-title"),
            "doi": None,
            "citation": todo("paper-citation"),
        },
        # Additional evidence and environment records live once at the root.
        # The verified paper/target-set source is injected automatically.
        "sources": [],
        "environment": [],
        "figures": [compact_figure(target) for target in targets.values()],
    }


def optional_refs(item: dict, base_id: str) -> list[str]:
    refs = item.get("sourceIds")
    if refs is None:
        return [base_id]
    require(isinstance(refs, list) and all(isinstance(value, str) and value for value in refs), "sourceIds must be non-empty IDs")
    require(len(refs) == len(set(refs)), "sourceIds must not contain duplicates")
    return refs


def validate_compact_shape(compact: object, manifest: dict, targets: dict[str, dict]) -> dict:
    root_keys = {
        "schemaVersion", "mode", "reportId", "generatedAt", "audience", "targetManifestSha256",
        "objective", "oneLine", "paper", "sources", "environment", "figures",
    }
    value = exact_keys(compact, root_keys, "compact report")
    require(value["schemaVersion"] == COMPACT_SCHEMA, f"unsupported compact schema: {value['schemaVersion']}")
    require(value["mode"] == "compact", "mode must be compact")
    require(value["audience"] in {"local", "public"}, "audience must be local or public")
    require(value["targetManifestSha256"] == manifest["integrity"]["manifestSha256"], "compact report targets a different manifest")
    require(isinstance(value["sources"], list), "sources must be a list")
    require(isinstance(value["environment"], list), "environment must be a list")
    figures = value["figures"]
    require(isinstance(figures, list) and len(figures) == len(targets), "compact figures must match the verified target count")
    ids = [figure.get("targetId") if isinstance(figure, dict) else None for figure in figures]
    require(len(ids) == len(set(ids)) and set(ids) == set(targets), "compact figures must bind every verified target exactly once")
    if manifest.get("paper") is None:
        require(value["paper"] is None, "images-only compact report cannot declare paper metadata")
    else:
        exact_keys(value["paper"], {"title", "doi", "citation"}, "compact paper")

    figure_keys = {"targetId", "section", "understanding", "generation", "validation", "assessment", "route"}
    understanding_keys = {"visualSummary", "observations", "paperClaim", "evidenceRole", "authorInterpretation", "limitations"}
    generation_keys = {"inputs", "steps", "plotMapping", "unknowns"}
    route_keys = {
        "label", "status", "goal", "claimCoverage", "doesNotReproduce", "substitutions", "assumptions",
        "rationale", "engine", "environmentIds", "conditions", "deliverables", "parameters", "effects",
        "estimated", "plan", "blockers",
    }
    for figure in figures:
        exact_keys(figure, figure_keys, f"compact figure {figure.get('targetId')}")
        exact_keys(figure["understanding"], understanding_keys, f"{figure['targetId']} understanding")
        exact_keys(figure["generation"], generation_keys, f"{figure['targetId']} generation")
        exact_keys(figure["generation"]["plotMapping"], {"description", "encodings"} | ({"sourceIds"} if "sourceIds" in figure["generation"]["plotMapping"] else set()), f"{figure['targetId']} plotMapping")
        exact_keys(figure["assessment"], {"level", "verdict", "confidence", "rationale"}, f"{figure['targetId']} assessment")
        require(isinstance(figure["assessment"]["level"], str), f"{figure['targetId']} assessment level must be a string")
        route = exact_keys(figure["route"], route_keys, f"{figure['targetId']} route")
        for field in ("environmentIds", "deliverables", "parameters", "effects", "plan", "blockers"):
            require(isinstance(route[field], list), f"{figure['targetId']} route {field} must be a list")
        require(all(isinstance(effect, str) for effect in route["effects"]), f"{figure['targetId']} route effects must be strings")
        exact_keys(
            route["estimated"],
            {"downloadBytes", "diskBytes", "runtimeMinutes", "gpu", "costUsd"},
            f"{figure['targetId']} route estimate",
        )
        require(isinstance(route["conditions"], dict) and set(route["conditions"]) == set(CATEGORIES), f"{figure['targetId']} conditions must cover all five categories")
        for category, condition in route["conditions"].items():
            allowed = {"state", "blocking", "detail", "sourceIds", "resolution"}
            require(isinstance(condition, dict) and {"state", "blocking", "detail"} <= set(condition) <= allowed, f"{figure['targetId']} {category} condition fields are invalid")
        for label, items, required in (
            ("observations", figure["understanding"]["observations"], {"location", "statement", "confidence"}),
            ("inputs", figure["generation"]["inputs"], {"label", "description", "origin"}),
            ("steps", figure["generation"]["steps"], {"label", "description", "origin"}),
            ("validation", figure["validation"], {"label", "kind", "origin", "observable", "criterion", "supportsClaim"}),
        ):
            require(isinstance(items, list) and items, f"{figure['targetId']} {label} must be non-empty")
            for item in items:
                require(isinstance(item, dict) and required <= set(item) <= required | {"sourceIds"}, f"{figure['targetId']} {label} item fields are invalid")
    return value


def expand_paper(compact: dict, manifest: dict, manifest_path: Path) -> dict | None:
    paper = manifest.get("paper")
    if paper is None:
        return None
    authored = compact["paper"]
    return {
        "paperId": stable_id("paper", paper["sha256"][:20]),
        "title": authored["title"],
        "doi": authored["doi"],
        "citation": authored["citation"],
        "sourcePath": str((manifest_path.parent / paper["originalPath"]).resolve()),
        "sourceSha256": paper["sha256"],
        "pageCount": paper["pageCount"],
    }


def expand_figure(authored: dict, target: dict, manifest_path: Path, base_id: str) -> dict:
    target_id = target["targetId"]
    token = stable_id("t", target_id)
    figure_id = stable_id("fig", target_id)
    observation_ids = [stable_id("obs", f"{token}-{index + 1}") for index in range(len(authored["understanding"]["observations"]))]
    validation_ids = [stable_id("val", f"{token}-{index + 1}") for index in range(len(authored["validation"]))]
    route_id = stable_id("route", f"{token}-candidate")
    conditions = authored["route"]["conditions"]
    requirements = []
    used_refs = {base_id}
    for category in CATEGORIES:
        source = conditions[category]
        refs = optional_refs(source, base_id)
        used_refs.update(refs)
        row = {
            "requirementId": stable_id("req", f"{token}-{category}"),
            "category": category,
            "label": category.title(),
            "state": source["state"],
            "blocking": source["blocking"],
            "detail": source["detail"],
            "evidenceRefs": refs,
        }
        if source.get("resolution") is not None:
            row["resolution"] = source["resolution"]
        requirements.append(row)

    def expanded_items(items: list[dict], kind: str) -> list[dict]:
        output = []
        for index, item in enumerate(items):
            refs = optional_refs(item, base_id)
            used_refs.update(refs)
            clean = {key: value for key, value in item.items() if key != "sourceIds"}
            clean[{"input": "inputId", "step": "stepId"}[kind]] = stable_id(kind, f"{token}-{index + 1}")
            clean["evidenceRefs"] = refs
            # Put the stable ID first for readable expanded JSON.
            id_key = {"input": "inputId", "step": "stepId"}[kind]
            output.append({id_key: clean.pop(id_key), **clean})
        return output

    observations = []
    for index, item in enumerate(authored["understanding"]["observations"]):
        refs = optional_refs(item, base_id)
        used_refs.update(refs)
        observations.append(
            {
                "observationId": observation_ids[index],
                **{key: value for key, value in item.items() if key != "sourceIds"},
                "evidenceRefs": refs,
            }
        )
    validation = []
    for index, item in enumerate(authored["validation"]):
        refs = optional_refs(item, base_id)
        used_refs.update(refs)
        validation.append(
            {
                "targetId": validation_ids[index],
                **{key: value for key, value in item.items() if key != "sourceIds"},
                "evidenceRefs": refs,
            }
        )
    plot = authored["generation"]["plotMapping"]
    plot_refs = optional_refs(plot, base_id)
    used_refs.update(plot_refs)
    route = authored["route"]
    recommended = route["status"] != "blocked"
    requested_ref = target.get("requestedAs") or target.get("figureReference")
    caption = target.get("caption") or target.get("sourceFileName") or requested_ref or target_id
    return {
        "figureId": figure_id,
        "label": target.get("figureReference") or requested_ref or target_id,
        "page": target.get("paperPage"),
        "section": authored["section"],
        "caption": caption,
        "target": {"targetId": target_id},
        "image": {"sourceRef": base_id},
        "understanding": {
            **{key: value for key, value in authored["understanding"].items() if key != "observations"},
            "observations": observations,
        },
        "generationLogic": {
            "inputs": expanded_items(authored["generation"]["inputs"], "input"),
            "steps": expanded_items(authored["generation"]["steps"], "step"),
            "plotMapping": {
                "description": plot["description"],
                "encodings": plot["encodings"],
                "evidenceRefs": plot_refs,
            },
            "unknowns": authored["generation"]["unknowns"],
        },
        "validationTargets": validation,
        "reproduction": {
            "level": authored["assessment"]["level"],
            "verdict": authored["assessment"]["verdict"],
            "confidence": authored["assessment"]["confidence"],
            "assessment": authored["assessment"]["rationale"],
            "recommendedRouteId": route_id if recommended else None,
        },
        "requirements": requirements,
        "routes": [
            {
                "routeId": route_id,
                "label": route["label"],
                "status": route["status"],
                "recommended": recommended,
                "scientificScope": {
                    "goal": route["goal"],
                    "reproducesObservationIds": observation_ids if recommended else [],
                    "claimCoverage": route["claimCoverage"],
                    "doesNotReproduce": route["doesNotReproduce"],
                    "substitutions": route["substitutions"],
                    "assumptions": route["assumptions"],
                    "validationTargetIds": validation_ids if recommended else [],
                    "recommendationRationale": route["rationale"],
                },
                "engine": route["engine"],
                "environmentIds": route["environmentIds"],
                "requirementIds": [row["requirementId"] for row in requirements],
                "deliverables": route["deliverables"],
                "parameters": route["parameters"],
                "effects": route["effects"],
                "estimated": route["estimated"],
                "plan": route["plan"],
                "blockers": route["blockers"],
            }
        ],
        "sourceRefs": sorted(used_refs),
    }


def expand_compact(compact: dict, manifest: dict, targets: dict[str, dict], manifest_path: Path) -> dict:
    value = validate_compact_shape(compact, manifest, targets)
    base, base_id = base_source(manifest)
    effects = {
        effect
        for figure in value["figures"]
        for effect in figure["route"]["effects"]
    }
    report = {
        "schemaVersion": "reprofig.report/v3",
        "reportId": value["reportId"],
        "generatedAt": value["generatedAt"],
        "generator": {"name": "scirepro", "version": "0.1.0"},
        "workflow": {"stage": "awaiting-approval", "executionAllowed": False, "approvalRequired": True},
        "integrity": {"algorithm": "sha256", "canonicalization": "json-sort-keys-v1", "reportSha256": ""},
        "audience": value["audience"],
        "targetSet": {
            "targetSetId": manifest["targetSetId"],
            "manifestSha256": manifest["integrity"]["manifestSha256"],
            "targetCount": len(targets),
            "acquisitionModes": sorted({target["acquisitionMode"] for target in targets.values()}),
        },
        "paper": expand_paper(value, manifest, manifest_path),
        "summary": {
            "objective": value["objective"],
            "overallLevel": "mixed",
            "oneLine": value["oneLine"],
            "figureCount": len(targets),
        },
        "environment": copy.deepcopy(value["environment"]),
        "sources": [base, *copy.deepcopy(value["sources"])],
        "figures": [expand_figure(item, targets[item["targetId"]], manifest_path, base_id) for item in value["figures"]],
        "approvalPolicy": {
            "minFigures": 1,
            "maxFigures": len(targets),
            "defaultOutputPolicy": "create-only",
            "allowedEffects": sorted(effects & AUTOMATIC_EFFECTS),
            "consentRequiredEffects": sorted(effects & GATED_EFFECTS),
            "ttlMinutes": 60,
        },
    }
    levels = {figure["reproduction"]["level"] for figure in report["figures"]}
    report["summary"]["overallLevel"] = next(iter(levels)) if len(levels) == 1 else "mixed"
    bind_target_manifest(report, manifest, targets, manifest_path, value["audience"])
    validate_report(report)
    return report


def load_compact(path: Path) -> dict:
    require(path.is_file() and not path.is_symlink(), f"compact input must be a real file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScaffoldError(f"cannot read compact input: {exc}") from exc
    require(isinstance(value, dict), "compact input must be a JSON object")
    unresolved = list(todo_locations(value))
    if unresolved:
        preview = ", ".join(unresolved[:20])
        suffix = "" if len(unresolved) <= 20 else f", ... (+{len(unresolved) - 20} more)"
        raise ScaffoldError(f"compact report has {len(unresolved)} unresolved TODO fields: {preview}{suffix}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    init_parser = subparsers.add_parser("init", help="Create compact authoring JSON.")
    init_parser.add_argument("--target-manifest", required=True, type=Path)
    init_parser.add_argument("--output", required=True, type=Path)
    init_parser.add_argument("--mode", choices=("compact",), default="compact")
    init_parser.add_argument("--audience", choices=("local", "public"), default="local")
    for command, help_text in (
        ("validate-ready", "Reject TODOs and validate deterministic v3 expansion."),
        ("expand", "Create a complete v3 report input from compact authoring JSON."),
    ):
        child = subparsers.add_parser(command, help=help_text)
        child.add_argument("--input", required=True, type=Path)
        child.add_argument("--target-manifest", required=True, type=Path)
        if command == "expand":
            child.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest_path = args.target_manifest.expanduser().resolve()
        require(manifest_path.is_file() and not manifest_path.is_symlink(), f"target manifest must be a real file: {manifest_path}")
        manifest, targets = load_target_manifest(manifest_path)
        if args.command == "init":
            output = args.output.expanduser().resolve()
            compact = init_compact(manifest, targets, args.audience)
            atomic_create_json(output, compact)
            result = {
                "status": "compact-created", "mode": args.mode, "output": str(output),
                "targetCount": len(targets), "todoCount": len(list(todo_locations(compact))),
            }
        else:
            input_path = args.input.expanduser().resolve()
            compact = load_compact(input_path)
            report = expand_compact(compact, manifest, targets, manifest_path)
            if args.command == "expand":
                output = args.output.expanduser().resolve()
                atomic_create_json(output, report)
                result = {
                    "status": "expanded", "input": str(input_path), "output": str(output),
                    "targetCount": len(report["figures"]),
                }
            else:
                result = {"status": "ready", "input": str(input_path), "targetCount": len(report["figures"])}
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ReportError, ScaffoldError) as exc:
        print(f"SciRepro report scaffold failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
