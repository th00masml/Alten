import argparse
import json
import os
from typing import Dict, Any, List, Tuple

from src.axa_extractor.pipeline import ExtractionPipeline
from src.axa_extractor.storage import Storage


def load_config(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def list_config_files() -> List[Tuple[str, str]]:
    base = "config/forms"
    out: List[Tuple[str, str]] = []
    if not os.path.isdir(base):
        return out
    for fn in os.listdir(base):
        if fn.lower().endswith(".json"):
            out.append((fn, os.path.join(base, fn)))
    return sorted(out)


def score_result(result: Dict[str, Any]) -> Tuple[float, int, int]:
    fields = result.get("fields", {}) or {}
    total = len(fields)
    filled = 0
    for fv in fields.values():
        if isinstance(fv, dict) and (fv.get("value") or "").strip():
            filled += 1
    confidence = float(result.get("confidence", 0.0) or 0.0)
    fill_ratio = (filled / total) if total else 0.0
    score = confidence + 0.2 * fill_ratio
    return score, filled, total


def filename_hint_boost(filename: str, config_label: str) -> Tuple[float, List[str]]:
    name = (filename or "").lower()
    label = (config_label or "").lower()
    triggers: List[str] = []
    groups = {
        "claim": ["claim", "fnol", "loss", "notice", "property-loss"],
        "policy": ["policy", "schedule", "certificate"],
        "customer": ["customer", "info", "information", "details"],
    }
    group = None
    if "claim" in label:
        group = "claim"
    elif "policy" in label:
        group = "policy"
    elif "customer" in label or "info" in label:
        group = "customer"
    boost = 0.0
    if group and group in groups:
        for kw in groups[group]:
            if kw in name:
                triggers.append(kw)
        if triggers:
            boost = min(0.1, 0.05 + 0.025 * (len(triggers) - 1))
    return boost, triggers


def main():
    parser = argparse.ArgumentParser(description="Batch extract data from AXA XL PDFs")
    parser.add_argument("--input", required=True, help="File or directory of PDFs")
    parser.add_argument("--out-db", default="data/extractions.db", help="SQLite DB path")
    parser.add_argument("--config", default="config/forms/axa_xl_claim.json", help="JSON config path")
    parser.add_argument("--auto-config", action="store_true", help="Try all configs and pick the best by score")
    args = parser.parse_args()

    pipeline = ExtractionPipeline()
    storage = Storage(db_path=args.out_db)
    config = load_config(args.config)
    configs_index = list_config_files()

    targets = []
    if os.path.isdir(args.input):
        for root, _, files in os.walk(args.input):
            for fn in files:
                if fn.lower().endswith(".pdf"):
                    targets.append(os.path.join(root, fn))
    else:
        targets.append(args.input)

    for path in targets:
        with open(path, "rb") as f:
            data = f.read()
        if args.auto_config and configs_index:
            # Try all configs and choose best
            candidates = []
            for fn, cfg_path in configs_index:
                cfg = load_config(cfg_path)
                res = pipeline.run(data, config=cfg)
                base_sc, fi, to = score_result(res)
                boost, triggers = filename_hint_boost(os.path.basename(path), fn)
                sc = base_sc + boost
                reason = f"+{boost:.2f} filename match: {', '.join(triggers)}" if triggers else ""
                candidates.append((sc, fi, to, fn, res, reason))
            best = max(candidates, key=lambda x: x[0]) if candidates else (0.0, 0, 0, None, {"fields": {}, "confidence": 0.0, "meta": {}}, "")
            score, filled, total, best_name, result, reason = best
            # Annotate meta
            result["meta"] = {**result.get("meta", {}), "selected_config": best_name, "score": round(score, 3), "filled": filled, "total": total, "reason": reason}
        else:
            result = pipeline.run(data, config=config)
            best_name = os.path.basename(args.config) if args.config else None
            score, filled, total = score_result(result)
            result["meta"] = {**result.get("meta", {}), "selected_config": best_name, "score": round(score, 3), "filled": filled, "total": total, "reason": "manual config"}

        doc_id = storage.save_extraction(os.path.basename(path), result)
        print(f"Processed {path} -> document_id={doc_id} confidence={result.get('confidence', 0.0):.2f} using={result['meta'].get('selected_config') or 'n/a'} score={result['meta'].get('score'):.2f} filled={result['meta'].get('filled')}/{result['meta'].get('total')} reason={result['meta'].get('reason')}")

        # Checklist of filled vs missing fields (shortened output)
        fields_map = result.get("fields", {}) or {}
        filled_names = []
        missing_names = []
        for key, fv in fields_map.items():
            val = ""
            if isinstance(fv, dict):
                val = (fv.get("value") or "").strip()
            if val:
                filled_names.append(key)
            else:
                missing_names.append(key)

        def shortlist(items, n=8):
            items = list(items)
            if len(items) > n:
                return ", ".join(items[:n]) + f", ...(+{len(items)-n} more)"
            return ", ".join(items)

        print(f"  filled=[{shortlist(sorted(filled_names))}]")
        print(f"  missing=[{shortlist(sorted(missing_names))}]")


if __name__ == "__main__":
    main()
