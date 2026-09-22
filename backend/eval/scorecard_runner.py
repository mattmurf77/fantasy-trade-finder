"""Independent offline scorecard runner; no app, database or network imports.

Consumes explicitly frozen JSON inputs. Reports unknown evidence, never an
acceptance probability or promotion based solely on synthetic/proxy results.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import random

VERSION = "scorecard-runner-v1"
DIMENSIONS = ("fairness", "outlook", "team_needs", "personal_ranks", "meaningful", "stud_tax")


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def cluster_mean_interval(rows, *, value="value", cluster="cluster_id", seed=0, draws=1000):
    """Equal-cluster mean/bootstrap; one cluster cannot establish uncertainty.

    Callers supply independent request/league-cluster summaries, never cards
    disguised as independent observations. This is descriptive, not a power test.
    """
    groups = defaultdict(list)
    for row in rows:
        v = row.get(value)
        if (row.get(cluster) is None or isinstance(v, bool)
                or not isinstance(v, (int, float)) or not math.isfinite(v)):
            raise ValueError("finite values and explicit cluster IDs required")
        groups[str(row[cluster])].append(float(v))
    means = [sum(groups[k]) / len(groups[k]) for k in sorted(groups)]
    estimate = sum(means) / len(means) if means else None
    result = {"estimate": estimate, "clusters": len(means), "ci95": None,
              "method": "equal-cluster percentile bootstrap", "seed": seed}
    if len(means) < 2:
        result["limitation"] = "insufficient_independent_clusters"
        return result
    if type(draws) is not int or draws < 100:
        raise ValueError("at least 100 bootstrap draws required")
    rng = random.Random(seed)
    samples = sorted(sum(rng.choice(means) for _ in means) / len(means) for _ in range(draws))
    result["ci95"] = [samples[int((draws - 1) * .025)], samples[int((draws - 1) * .975)]]
    result["limitation"] = "few clusters give imprecise intervals; not a promotion test"
    return result


def _cell_summary(cells):
    statuses = Counter(c.get("status", "unknown") for c in cells)
    grades = Counter(str(c["grade"]) for c in cells
                     if c.get("status") == "known" and c.get("grade") is not None)
    raw = defaultdict(list)
    for cell in cells:
        for key, value in cell.get("raw_features", {}).items():
            if isinstance(value, bool):
                raw[key].append(int(value))
            elif isinstance(value, (int, float)) and math.isfinite(value):
                raw[key].append(value)
    return {"count": len(cells), "status_counts": dict(sorted(statuses.items())),
            "grade_counts": dict(sorted(grades.items())),
            "numeric_features": {k: {"known": len(v), "mean": sum(v) / len(v),
                                       "min": min(v), "max": max(v)}
                                 for k, v in sorted(raw.items())}}


def summarize_evaluations(evaluations):
    result = {}
    for dim in DIMENSIONS:
        items = [e["dimensions"][dim] for e in evaluations]
        result[dim] = {
            "bilateral_status_counts": dict(sorted(Counter(
                e.get("bilateral_status", "unknown") for e in items).items())),
            "managers": {manager: {side: _cell_summary([
                item["managers"][manager][side] for item in items])
                for side in ("give", "receive", "package")}
                for manager in ("A", "B")}}
    return result


def expand_offer(row, manifest):
    """Resolve a shared frozen context without copying private boards per card."""
    if "offer" in row:
        if any(key in row for key in ("context_id", "terms", "offer_id")):
            raise ValueError("full offer and compact context envelope are mutually exclusive")
        return row["offer"]
    context = manifest.get("contexts", {}).get(row.get("context_id"))
    if context is None or not isinstance(row.get("terms"), dict):
        raise ValueError("offer or registered context_id/terms required")
    offer = dict(context)
    offer["offer_id"] = row.get("offer_id")
    offer["managers"] = {role: dict(manager, give=list(row["terms"][role]))
                          for role, manager in context["managers"].items()}
    return offer


def run_manifest(manifest, *, include_details=False):
    """Evaluate frozen normalized occurrences; all initial results are descriptive.

    Envelope: schema_version=1, benchmark_id, requests[], offers[]; optional
    cohort/episodes/cutoff. Offer rows have model_id, model_version, request_id,
    stage, native_rank, offer (the dimensions module schema). Request rows must
    exist even for error/empty outcomes. Stage names are caller-declared facts,
    not inferred from a card merely being stored in an impression table.
    """
    from .scorecard_dimensions import evaluate_offer
    if manifest.get("schema_version") != 1 or not manifest.get("benchmark_id"):
        raise ValueError("schema_version=1 and benchmark_id required")
    before = fingerprint(manifest)
    requests = manifest.get("requests")
    offers = manifest.get("offers")
    if not isinstance(requests, list) or not isinstance(offers, list):
        raise ValueError("explicit requests and offers lists required")
    reqs = {}
    for r in requests:
        key = (r.get("model_id"), r.get("request_id"))
        if not all(isinstance(v, str) and v for v in key) or key in reqs:
            raise ValueError("request/model identity missing or duplicate")
        reqs[key] = r
    groups = defaultdict(list)
    details = []
    errors = []
    seen = set()
    evaluation_cache = {}
    versions = defaultdict(set)
    for row_number, row in enumerate(offers):
        key = (row.get("model_id"), row.get("request_id"))
        if key not in reqs or not row.get("model_version") or not row.get("stage"):
            raise ValueError("offer requires registered request, model version and stage")
        versions[row["model_id"]].add(row["model_version"])
        if len(versions[row["model_id"]]) > 1:
            raise ValueError("use separate model/variant IDs for different versions in one manifest")
        offer = expand_offer(row, manifest)
        identity = (key, row["stage"], offer.get("offer_id"))
        if not identity[-1] or identity in seen:
            raise ValueError("duplicate/missing offer identity within request/stage")
        seen.add(identity)
        try:
            cache_key = (row.get("context_id"), fingerprint(row.get("terms")), offer.get("offer_id")) if row.get("context_id") else None
            if cache_key is not None and cache_key in evaluation_cache:
                evaluation = evaluation_cache[cache_key]
            else:
                evaluation = evaluate_offer(offer)
                if cache_key is not None:
                    evaluation_cache[cache_key] = evaluation
        except (ValueError, TypeError, KeyError) as exc:
            errors.append({"row_number": row_number, "error_type": type(exc).__name__})
            continue  # quarantined, visible; request denominator stays fixed
        if evaluation.get("integrity_status") != "valid":
            errors.append({"row_number": row_number, "error_type": "invalid_offer_integrity"})
            continue
        groups[(row["model_id"], row["model_version"], row["stage"])].append(evaluation)
        if include_details:
            details.append({"row_number": row_number, "evaluation": evaluation})
    models = {}
    for (model, version, stage), evaluations in sorted(groups.items()):
        model_key = f"{model}@{version}"
        registered = [r for (m, _), r in reqs.items() if m == model]
        models.setdefault(model_key, {"model_id": model, "model_version": version,
                                     "requests": len(registered), "stages": {}})
        models[model_key]["stages"][stage] = {
            "evaluated_offers": len(evaluations),
            "evaluated_offers_per_request": len(evaluations) / len(registered),
            "dimensions": summarize_evaluations(evaluations)}
    result = {"schema_version": 1, "runner_version": VERSION,
              "benchmark_id": manifest["benchmark_id"], "manifest_sha256": before,
              "evidence_class": manifest.get("evidence_class", "unspecified"),
              "promotion_status": "insufficient_evidence",
              "ratification_status": "draft_unratified",
              "requests": len(requests), "offer_rows": len(offers),
              "request_status_counts": dict(sorted(Counter(r.get("status", "unknown")
                                                            for r in requests).items())),
              "quarantined_offers": errors, "models": models,
              "zero_output_models": sorted({r[0] for r in reqs} - {k[0] for k in groups}),
              "limitations": ["Ordinal rubric has not been ratified against an independent baseline",
                               "No causal acceptance/probability claim from offline replay",
                               "Raw numerical metrics do not override an unknown or harmed manager",
                               "No joint score combines the six dimensions"]}
    if manifest.get("cohort") is not None:
        from .scorecard_outcomes import summarize_cohort
        if not manifest.get("cutoff"):
            raise ValueError("explicit cutoff required for outcomes")
        outcomes = summarize_cohort(manifest["cohort"], manifest.get("episodes", []), manifest["cutoff"])
        private_keys = ("episodes", "quarantined", "excluded_episodes", "ambiguous_origin_concepts", "ambiguous_history_concepts")
        result["outcomes"] = {key: value for key, value in outcomes.items() if key not in private_keys and key != "cohort_id"}
        result["outcomes"]["cohort_sha256"] = fingerprint(outcomes["cohort_id"])
        result["outcomes"]["detail_counts"] = {key: len(outcomes.get(key, [])) for key in private_keys}
        if include_details:
            result["private_outcome_details"] = {key: outcomes.get(key) for key in private_keys}
    else:
        result["outcomes"] = {"status": "unknown", "reason": "no_frozen_eligible_cohort"}
    if fingerprint(manifest) != before:
        raise AssertionError("evaluator mutated frozen input")
    if include_details:
        result["private_details"] = details
    return result


def render_markdown(result):
    lines = ["# Independent trade model scorecard", "",
             f"Benchmark: `{result['benchmark_id']}`. Runner: `{result['runner_version']}`.", "",
             "**Descriptive, evidence-limited; not a model promotion or calibrated acceptance result.**", "",
             f"Requests: {result['requests']}; offer rows: {result['offer_rows']}; "
             f"quarantined: {len(result['quarantined_offers'])}.", "",
             "All rows below retain independent give/receive/package cells for both managers in JSON.", ""]
    for name, model in result["models"].items():
        lines += [f"## {name}", ""]
        for stage, data in model["stages"].items():
            lines += [f"### {stage}", "", f"{data['evaluated_offers']} offers; "
                      f"{data['evaluated_offers_per_request']:.2f} per registered request.", "",
                      "| Dimension | Bilateral status counts | A package evidence | B package evidence |",
                      "|---|---|---|---|"]
            for dim, d in data["dimensions"].items():
                a = d["managers"]["A"]["package"]["status_counts"]
                b = d["managers"]["B"]["package"]["status_counts"]
                lines.append(f"| {dim} | {d['bilateral_status_counts']} | {a} | {b} |")
            lines.append("")
    if result["zero_output_models"]:
        lines += ["Zero-output models (not omitted): " + ", ".join(result["zero_output_models"]), ""]
    lines += ["## Limitations", ""] + ["- " + s for s in result["limitations"]]
    return "\n".join(lines) + "\n"


def write_report(result, output):
    """Never overwrite an earlier run or write into an existing/symlink directory."""
    output = Path(output)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    for name, content in (("scorecard.json", json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"),
                          ("scorecard.md", render_markdown(result))):
        target = output / name
        with target.open("x", encoding="utf-8") as stream:
            stream.write(content)
        target.chmod(0o600)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-details", action="store_true")
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text())
    result = run_manifest(manifest, include_details=args.private_details)
    write_report(result, args.output)
    print(json.dumps({"output": str(args.output.resolve()), "promotion_status": result["promotion_status"],
                      "manifest_sha256": result["manifest_sha256"]}))


if __name__ == "__main__":
    main()
