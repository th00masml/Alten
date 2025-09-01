import io
import json
import os
from typing import Dict, Any, List, Tuple

import streamlit as st

from src.axa_extractor.pipeline import ExtractionPipeline
from src.axa_extractor.storage import Storage


st.set_page_config(page_title="AXA XL PDF Extractor", layout="wide")


@st.cache_resource
def get_pipeline() -> ExtractionPipeline:
    return ExtractionPipeline()


@st.cache_resource
def get_storage() -> Storage:
    return Storage(db_path="data/extractions.db")


def list_config_files() -> List[Tuple[str, str]]:
    base = "config/forms"
    items: List[Tuple[str, str]] = []
    if not os.path.isdir(base):
        return items
    for fn in os.listdir(base):
        if fn.lower().endswith(".json"):
            path = os.path.join(base, fn)
            items.append((fn, path))
    return sorted(items)


def load_config(path: str) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _score_result(result: Dict[str, Any]) -> Tuple[float, int, int]:
    fields = result.get("fields", {}) or {}
    total = len(fields)
    filled = 0
    for fv in fields.values():
        if isinstance(fv, dict) and (fv.get("value") or "").strip():
            filled += 1
    confidence = float(result.get("confidence", 0.0) or 0.0)
    # Composite score: confidence + weight on fill ratio
    fill_ratio = (filled / total) if total else 0.0
    score = confidence + 0.2 * fill_ratio
    return score, filled, total


def filename_hint_boost(filename: str, config_label: str) -> Tuple[float, List[str]]:
    name = (filename or "").lower()
    label = (config_label or "").lower()
    triggers: List[str] = []

    # Define keywords per form group
    groups = {
        "claim": ["claim", "fnol", "loss", "notice", "property-loss"],
        "policy": ["policy", "schedule", "certificate"],
        "customer": ["customer", "info", "information", "details"],
    }
    # Map config file name to group by simple heuristics
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
            # Boost up to 0.1 based on number of matches
            boost = min(0.1, 0.05 + 0.025 * (len(triggers) - 1))
    return boost, triggers


def run_auto_configs(pipeline, file_bytes: bytes, configs_index: List[Tuple[str, str]], filename: str) -> Tuple[Dict[str, Any], Dict[str, Any], List[Tuple[str, float, int, int, str]]]:
    candidates: List[Tuple[str, Dict[str, Any], float, int, int, str]] = []
    for fn, path in configs_index:
        cfg = load_config(path)
        result = pipeline.run(file_bytes, config=cfg)
        base_score, filled, total = _score_result(result)
        boost, triggers = filename_hint_boost(filename, fn)
        score = base_score + boost
        reason = " ".join([f"+{boost:.2f} filename match: {', '.join(triggers)}"]) if triggers else ""
        candidates.append((fn, result, score, filled, total, reason))
    if not candidates:
        empty = {"fields": {}, "confidence": 0.0, "meta": {"error": "No configs found"}}
        return empty, {}, []
    best = max(candidates, key=lambda x: x[2])
    best_name, best_result, best_score, best_filled, best_total, best_reason = best
    best_meta = {"selected_config": best_name, "score": round(best_score, 3), "filled": best_filled, "total": best_total, "reason": best_reason}
    # Prepare leaderboard data (top 3)
    leaderboard = [(name, round(sc, 3), fi, to, rsn) for name, _, sc, fi, to, rsn in sorted(candidates, key=lambda x: x[2], reverse=True)[:3]]
    # Attach meta info
    best_result["meta"] = {**best_result.get("meta", {}), **best_meta}
    return best_result, best_meta, leaderboard


st.title("AXA XL PDF Form Data Extraction")
st.markdown("Upload filled AXA XL forms and review extracted data with confidence scores.")

pipeline = get_pipeline()
storage = get_storage()

with st.sidebar:
    st.header("Settings")
    save_to_db = st.checkbox("Save results to DB", value=True)
    st.markdown("DB path: data/extractions.db")
    st.markdown("---")
    st.subheader("Form Variant")
    configs = list_config_files()
    options = ["Auto (recommended)"] + [c[0] for c in configs]
    default_idx = 0
    try:
        default_idx = options.index("Auto (recommended)")
    except ValueError:
        default_idx = 0
    selected = st.selectbox("Select a form configuration", options=options or ["None"], index=default_idx if options else 0)
    config_path = None if selected.startswith("Auto") else dict(configs).get(selected)

uploaded = st.file_uploader("Upload PDF(s)", type=["pdf"], accept_multiple_files=True)

if uploaded:
    for file in uploaded:
        st.subheader(f"File: {file.name}")
        data = file.read()
        if config_path:
            config = load_config(config_path)
            result = pipeline.run(data, config=config)
            chosen_meta = {"selected_config": os.path.basename(config_path)}
            result["meta"] = {**result.get("meta", {}), **chosen_meta}
            leaderboard = []
        else:
            # Auto selection across all configs
            result, chosen_meta, leaderboard = run_auto_configs(pipeline, data, configs, file.name)

        # Display results
        cols = st.columns([2, 1])
        with cols[0]:
            st.markdown("### Extracted Fields")
            editable = {}
            for k, fv in result["fields"].items():
                col1, col2, col3 = st.columns([2, 3, 1])
                col1.write(k)
                editable[k] = col2.text_input("", value=fv.get("value") or "", key=f"{file.name}-{k}")
                col3.write(f"{fv.get('confidence', 0.0):.2f}")

        with cols[1]:
            st.markdown("### Summary")
            st.write({"confidence": round(result.get("confidence", 0.0), 2), **result.get("meta", {})})
            if leaderboard:
                st.markdown("Top configs")
                for name, sc, fi, to, rsn in leaderboard:
                    extra = f" ({rsn})" if rsn else ""
                    st.write(f"- {name}: score={sc} filled={fi}/{to}{extra}")

            # Coverage checklist
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
            st.markdown("### Fields Coverage")
            st.write({"filled": len(filled_names), "missing": len(missing_names)})
            with st.expander("Filled fields"):
                st.write(", ".join(sorted(filled_names)) or "—")
            with st.expander("Missing fields"):
                st.write(", ".join(sorted(missing_names)) or "—")

        # Apply edits
        if st.button(f"Save {file.name}"):
            # Write edited values back
            for k in editable:
                if k in result["fields"]:
                    result["fields"][k]["value"] = editable[k].strip() or None
                    # If user edited, bump confidence slightly
                    if editable[k] != (result["fields"][k].get("value") or ""):
                        result["fields"][k]["confidence"] = max(result["fields"][k].get("confidence", 0.0), 0.7)
            if save_to_db:
                doc_id = storage.save_extraction(file.name, result)
                st.success(f"Saved with document_id={doc_id}")
            else:
                st.info("Saving disabled. Review complete.")
