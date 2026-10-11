"""Deterministic, conservative mutation catalog shared by mutation workflows."""
from dataclasses import dataclass
from typing import Callable
import re
from backend.models import SourceDocument

@dataclass(frozen=True)
class Mutation:
    mutation_id: str
    mutation_class: str
    side: str
    name: str
    explanation: str
    ground_truth_by_construction: str
    expected_baseline: str
    expected_model: str
    preconditions: str
    limitations: str
    apply: Callable[[str, dict], tuple[str, str]]

def _replace(pattern, replacement, text):
    updated, n = re.subn(pattern, replacement, text, count=1, flags=re.I)
    if not n: raise ValueError("The required token or pattern is not present exactly as required")
    return updated, updated[len(text[:0]):] if False else ""

def _number(text, params):
    old = params.get("from")
    new = params.get("to")
    if not isinstance(old, str) or not isinstance(new, str) or not old or not new or old == new: raise ValueError("Provide distinct string parameters 'from' and 'to'")
    updated, n = re.subn(r"(?<!\w)" + re.escape(old) + r"(?!\w)", new, text, count=1)
    if n != 1: raise ValueError("The specified value must occur in the target text")
    return updated, f"{old} → {new}"

def _negate(text, params):
    match = re.search(r"\b(not|never|no)\b", text, re.I)
    if match: updated=text[:match.start()]+text[match.end():]; change=match.group()+" removed"
    else:
        match=re.search(r"\b(is|are|was|were|does|do|did|has|have|can|will)\b", text, re.I)
        if not match: raise ValueError("No supported auxiliary verb to negate")
        updated=text[:match.end()]+" not"+text[match.end():]; change="not inserted after "+match.group()
    return updated, change

def _entity(text, params): return _number(text, params)
def _quantifier(text, params): return _number(text, params)
def _paraphrase(text, params):
    if not params.get("replacement"): raise ValueError("Provide a replacement claim")
    return str(params["replacement"]), "Entire claim replaced; semantic equivalence is not established"
def _noise(text, params): return text+" Unrelated note: the sky is blue.", "Appended fixed unrelated sentence"
def _duplicate(text, params): return text+"\n\n"+text, "Duplicated the complete source text"
def _order(text, params):
    parts=re.split(r"(?<=[.!?])\s+",text.strip())
    if len(parts)<2: raise ValueError("At least two sentences are required")
    return " ".join(reversed(parts)), "Reversed sentence order"
def _remove(text, params): return "", "Removed target source"
def _edit(text, params):
    old=params.get("from"); new=params.get("to")
    if not old or not new or old==new: raise ValueError("Provide distinct 'from' and 'to' strings")
    updated,n=re.subn(re.escape(old),new,text,count=1)
    if n!=1: raise ValueError("The exact source passage was not found")
    return updated,f"{old} → {new}"

def _entry(mid, cls, side, name, explanation, fn, pre="Target text must contain a uniquely specified editable token or supported structure.", gt="Only the stated string transformation is guaranteed; factual correctness is not inferred.", exp="INCONCLUSIVE", lim="The audit result is an observation from the configured engine, not a correctness guarantee."):
    return Mutation(mid,cls,side,name,explanation,gt,exp,"INCONCLUSIVE",pre,lim,fn)

CATALOG = [
 _entry("number.evidence","NUMBER","EVIDENCE","Change evidence number","Replace one explicitly selected value in a source.",_number),
 _entry("number.claim","NUMBER","CLAIM","Change claim number","Replace one explicitly selected value in the claim.",_number),
 _entry("date.evidence","DATE","EVIDENCE","Change evidence date","Replace one explicitly selected date string in a source.",_number),
 _entry("date.claim","DATE","CLAIM","Change claim date","Replace one explicitly selected date string in a claim.",_number),
 _entry("negation.evidence","NEGATION","EVIDENCE","Toggle evidence negation","Insert or remove a supported negation marker.",_negate),
 _entry("negation.claim","NEGATION","CLAIM","Toggle claim negation","Insert or remove a supported negation marker.",_negate),
 _entry("entity.evidence","ENTITY","EVIDENCE","Change evidence entity","Replace an explicitly selected entity string.",_entity),
 _entry("entity.claim","ENTITY","CLAIM","Change claim entity","Replace an explicitly selected entity string.",_entity),
 _entry("quantifier.claim","QUANTIFIER","CLAIM","Change claim quantifier","Replace an explicitly selected quantifier string.",_quantifier),
 _entry("causal.claim","CAUSAL_WORDING","CLAIM","Edit causal wording","Replace explicitly selected causal wording.",_number),
 _entry("paraphrase.claim","PARAPHRASE","CLAIM","Replace claim wording","Use a user-supplied replacement; semantic preservation is unknown.",_paraphrase,gt="No semantic preservation is guaranteed.",exp="UNTESTABLE_IN_MODE",lim="Replacement wording may change meaning; BASELINE has no semantic-equivalence oracle."),
 _entry("noise.evidence","NOISE","EVIDENCE","Append controlled noise","Append a fixed unrelated sentence.",_noise,pre="Any non-empty source.",gt="The fixed sentence is appended; irrelevance to every claim is not guaranteed."),
 _entry("duplication.evidence","DUPLICATION","EVIDENCE","Duplicate source text","Append a second copy of the source text.",_duplicate,pre="Any non-empty source.",gt="Text is duplicated; duplicated text is not independent corroboration.",lim="Duplicate text is not independent corroboration and may affect retrieval."),
 _entry("order.evidence","ORDER","EVIDENCE","Reverse evidence order","Reverse sentence order in a source.",_order),
 _entry("source-removal.evidence","SOURCE_REMOVAL","EVIDENCE","Remove source","Remove one selected source.",_remove,pre="At least two sources must remain after removal.",gt="One source is removed; relevance impact is not predetermined."),
 _entry("source-edit.evidence","SOURCE_EDIT","EVIDENCE","Edit source passage","Replace one explicitly selected passage.",_edit),
]
BY_ID={item.mutation_id:item for item in CATALOG}

def public_catalog():
    return [dict(mutation_id=m.mutation_id,mutation_class=m.mutation_class,side=m.side,name=m.name,explanation=m.explanation,ground_truth_by_construction=m.ground_truth_by_construction,expected_outcomes={"BASELINE":m.expected_baseline,"MODEL":m.expected_model},preconditions=m.preconditions,limitations=m.limitations) for m in CATALOG]

def apply_mutation(mutation_id, text, params=None):
    m=BY_ID.get(mutation_id)
    if m is None: raise ValueError(f"Unknown mutation_id: {mutation_id}")
    result, changed=m.apply(text,params or {})
    if result==text: raise ValueError("Mutation did not change the input")
    return m,result,changed
