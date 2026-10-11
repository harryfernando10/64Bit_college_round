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

def _date(text, params):
    old=params.get("from"); new=params.get("to")
    pattern=r"(?:\d{4}|\d{4}-\d{2}-\d{2})"
    if not isinstance(old,str) or not isinstance(new,str) or not re.fullmatch(pattern,old) or not re.fullmatch(pattern,new) or old==new:
        raise ValueError("Use distinct ISO year or YYYY-MM-DD date strings")
    updated,n=re.subn(r"(?<!\w)"+re.escape(old)+r"(?!\w)",new,text,count=1)
    if n!=1: raise ValueError("The specified date must occur in the target text")
    return updated,f"{old} → {new}"

def _negate(text, params):
    match = re.search(r"\b(not|never|no)\b", text, re.I)
    if match: updated=text[:match.start()]+text[match.end():]; change=match.group()+" removed"
    else:
        match=re.search(r"\b(is|are|was|were|does|do|did|has|have|can|will)\b", text, re.I)
        if not match: raise ValueError("No supported auxiliary verb to negate")
        updated=text[:match.end()]+" not"+text[match.end():]; change="not inserted after "+match.group()
    return updated, change

def _entity(text, params): return _number(text, params)
def _quantifier(text, params):
    supported={"some","all","most","few","many","none"}
    if str(params.get("from","")).casefold() not in supported or str(params.get("to","")).casefold() not in supported: raise ValueError("Use supported quantifiers: some, all, most, few, many, none")
    return _number(text,params)
def _causal(text, params):
    supported={"because","caused","therefore","led to"}
    if str(params.get("from","")).casefold() not in supported or str(params.get("to","")).casefold() not in supported: raise ValueError("Use supported causal phrases: because, caused, therefore, led to")
    return _number(text,params)
def _vocative_comma(text, params):
    # Curated diagnostic: removing the vocative comma changes who is addressed,
    # while the baseline normalizer discards punctuation.
    updated,n=re.subn(r"\beat,\s*(Grandma)\b",r"eat \1",text,count=1,flags=re.I)
    if n!=1: raise ValueError("The exact vocative pattern 'eat, Grandma' is required")
    return updated,"removed vocative comma"
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
    expected = "SUPPORTED_TO_CONTRADICTED" if cls in {"NUMBER","DATE","NEGATION"} else "SUPPORTED_TO_NOT_SUPPORTED" if cls in {"QUANTIFIER","PUNCTUATION"} else exp
    model_expected = "UNTESTABLE_IN_MODE" if expected in {"SUPPORTED_TO_CONTRADICTED","SUPPORTED_TO_NOT_SUPPORTED"} else "INCONCLUSIVE"
    return Mutation(mid,cls,side,name,explanation,gt,expected,model_expected,pre,lim,fn)

CATALOG = [
 _entry("number.evidence","NUMBER","EVIDENCE","Change evidence number","Replace one explicitly selected value in a source.",_number),
 _entry("number.claim","NUMBER","CLAIM","Change claim number","Replace one explicitly selected value in the claim.",_number),
 _entry("date.evidence","DATE","EVIDENCE","Change evidence date","Replace one ISO year or full ISO date in a source.",_date,pre="Exactly one selected YYYY year or YYYY-MM-DD date must occur in the source."),
 _entry("date.claim","DATE","CLAIM","Change claim date","Replace one ISO year or full ISO date in a claim.",_date,pre="Exactly one selected YYYY year or YYYY-MM-DD date must occur in the claim."),
 _entry("negation.evidence","NEGATION","EVIDENCE","Toggle evidence negation","Insert or remove a supported negation marker.",_negate),
 _entry("negation.claim","NEGATION","CLAIM","Toggle claim negation","Insert or remove a supported negation marker.",_negate),
 _entry("entity.evidence","ENTITY","EVIDENCE","Change evidence entity","Replace an explicitly selected entity string.",_entity),
 _entry("entity.claim","ENTITY","CLAIM","Change claim entity","Replace an explicitly selected entity string.",_entity),
 _entry("quantifier.claim","QUANTIFIER","CLAIM","Change claim quantifier","Replace an explicitly selected quantifier string.",_quantifier),
 _entry("vocative-comma.claim","PUNCTUATION","CLAIM","Remove vocative comma","Remove the comma that marks direct address in the curated ‘Let’s eat, Grandma’ example.",_vocative_comma,pre="Curated English sentence must contain exactly the direct-address pattern ‘eat, Grandma’.",gt="The comma is removed exactly; the conventional reading changes from addressing Grandma to saying Grandma is food.",exp="SUPPORTED_TO_NOT_SUPPORTED",lim="Curated English punctuation example; interpretation relies on the conventional vocative reading. The audit engine has no semantic parser; FALSE_SUPPORT is an observed limitation, not a general punctuation claim."),
 _entry("causal.claim","CAUSAL_WORDING","CLAIM","Edit causal wording","Replace explicitly selected causal wording.",_causal,pre="The exact old phrase occurs in the claim; both phrases are supported causal phrases."),
 _entry("paraphrase.claim","PARAPHRASE","CLAIM","Replace claim wording","Use a user-supplied replacement; semantic preservation is unknown.",_paraphrase,gt="No semantic preservation is guaranteed.",exp="UNTESTABLE_IN_MODE",lim="Replacement wording may change meaning; BASELINE has no semantic-equivalence oracle."),
 _entry("noise.evidence","NOISE","EVIDENCE","Append controlled noise","Append a fixed unrelated sentence.",_noise,pre="Any non-empty source.",gt="The fixed sentence is appended; irrelevance to every claim is not guaranteed."),
 _entry("duplication.evidence","DUPLICATION","EVIDENCE","Duplicate source text","Append a second copy of the source text.",_duplicate,pre="Any non-empty source.",gt="Text is duplicated; duplicated text is not independent corroboration.",lim="Duplicate text is not independent corroboration and may affect retrieval."),
 _entry("order.evidence","ORDER","EVIDENCE","Reverse evidence order","Reverse sentence order in a source.",_order),
 _entry("source-removal.evidence","SOURCE_REMOVAL","EVIDENCE","Remove source","Remove one selected source.",_remove,pre="At least two sources are supplied so one remains after removal.",gt="One source is removed; relevance impact is not predetermined."),
 _entry("source-edit.evidence","SOURCE_EDIT","EVIDENCE","Edit source passage","Replace one explicitly selected passage.",_edit),
]
_ALLOWED_SIDES={"NUMBER":{"CLAIM","EVIDENCE"},"DATE":{"CLAIM","EVIDENCE"},"NEGATION":{"CLAIM","EVIDENCE"},"ENTITY":{"CLAIM","EVIDENCE"},"QUANTIFIER":{"CLAIM"},"PUNCTUATION":{"CLAIM"},"CAUSAL_WORDING":{"CLAIM"},"PARAPHRASE":{"CLAIM"},"NOISE":{"EVIDENCE"},"DUPLICATION":{"EVIDENCE"},"ORDER":{"EVIDENCE"},"SOURCE_REMOVAL":{"EVIDENCE"},"SOURCE_EDIT":{"EVIDENCE"}}
if any(item.side not in _ALLOWED_SIDES.get(item.mutation_class,set()) for item in CATALOG):
    raise RuntimeError("Mutation catalog contains an unsupported side/class combination")
BY_ID={item.mutation_id:item for item in CATALOG}

def public_catalog():
    return [dict(mutation_id=m.mutation_id,mutation_class=m.mutation_class,side=m.side,name=m.name,explanation=m.explanation,ground_truth_by_construction=m.ground_truth_by_construction,expected_outcomes={"BASELINE":m.expected_baseline,"MODEL":m.expected_model},preconditions=m.preconditions,limitations=m.limitations) for m in CATALOG]

def compare_expected_behavior(expectation, comparable, before, after):
    if not comparable: return "NOT_COMPARABLE","Runs used different execution modes or a fixture; comparison is excluded."
    if expectation=="UNTESTABLE_IN_MODE": return "UNTESTABLE_IN_MODE","The selected execution mode has no valid oracle for this transformation."
    if expectation not in {"SUPPORTED_TO_CONTRADICTED","SUPPORTED_TO_NOT_SUPPORTED"}: return "INCONCLUSIVE","The catalog declares no determinate behavior for this transformation."
    if before is None or after is None: return "NOT_COMPARABLE","The targeted claim could not be matched in both runs."
    if before.verdict.value!="SUPPORTED": return "INCONCLUSIVE","The expectation applies only when the unperturbed claim is SUPPORTED; that precondition was not met."
    if expectation=="SUPPORTED_TO_NOT_SUPPORTED":
        if after.verdict.value in {"CONTRADICTED","INSUFFICIENT_EVIDENCE","AMBIGUOUS"}:
            return "EXPECTED_OBSERVED","The predeclared supported-to-not-supported expectation occurred."
        if after.verdict.value=="SUPPORTED": return "EXPECTED_CHANGE_NOT_OBSERVED","The perturbed claim remained SUPPORTED although the curated mutation is expected to change its meaning."
        return "UNEXPECTED_CHANGE","The perturbed claim produced an outcome outside the declared expectation."
    before_checks=[(c.check_type,c.status) for c in before.deterministic_checks]
    after_checks=[(c.check_type,c.status) for c in after.deterministic_checks]
    trace_changed=(before.evidence!=after.evidence or before.review_flags!=after.review_flags or before_checks!=after_checks or before.error_localizations!=after.error_localizations)
    if after.verdict.value=="CONTRADICTED": return "EXPECTED_OBSERVED","The predeclared supported-to-contradicted expectation occurred; the perturbed audit's evidence and applicable checks are included for review."
    if after.verdict.value=="SUPPORTED" and not trace_changed: return "EXPECTED_CHANGE_NOT_OBSERVED","The target remained SUPPORTED and its relevant evidence, checks, and review findings did not change."
    return "UNEXPECTED_CHANGE","The target did not meet the predeclared contradiction expectation; its verdict or relevant traces changed in another way."

def apply_mutation(mutation_id, text, params=None):
    m=BY_ID.get(mutation_id)
    if m is None: raise ValueError(f"Unknown mutation_id: {mutation_id}")
    result, changed=m.apply(text,params or {})
    if result==text: raise ValueError("Mutation did not change the input")
    return m,result,changed
