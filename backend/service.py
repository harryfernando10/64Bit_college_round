"""Source-driven, deterministic evidence discovery and conservative checks."""
import json
import re
from decimal import Decimal, InvalidOperation
from collections import Counter
from pathlib import Path
from uuid import uuid4
from backend.models import *

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "data" / "scenarios"
TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
NUMBER = re.compile(r"(?<!\w)[+-]?\d+(?:\.\d+)?(?:\s*(?:%|cm|mm|m|km|kg|g|mg|°[CF]|hours?|days?|years?))?", re.I)
NEGATIONS = {"not", "no", "never", "neither", "cannot", "cant", "without", "doesnt", "isnt", "arent", "wont"}
CONTEXT_STOPWORDS = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being", "to", "of", "in", "on", "at", "for", "by", "and", "or", "it", "this", "that", "with", "from", "as", "after", "before"}

def split_sentences(text: str, prefix: str):
    # Split at punctuation followed by whitespace/end; decimal points and common abbreviations stay intact.
    spans = []; boundaries = []
    abbreviations = {"mr.", "mrs.", "ms.", "dr.", "prof.", "sr.", "jr.", "e.g.", "i.e.", "vs."}
    for match in re.finditer(r"[.!?]+(?=\s|$)|\n+", text):
        punct = match.group(0)
        if punct.startswith(".") and match.start() > 0 and match.start()+1 < len(text) and text[match.start()-1].isdigit() and text[match.start()+1].isdigit():
            continue
        if punct.startswith(".") and text[max(0, match.start()-5):match.end()].casefold().strip() in abbreviations:
            continue
        boundaries.append((match.start(), match.end()))
    start = 0
    for boundary_start, boundary_end in [*boundaries, (len(text), len(text))]:
        end = boundary_end if boundary_end > boundary_start and text[boundary_start] != "\n" else boundary_start
        while start < end and text[start].isspace(): start += 1
        while end > start and text[end-1].isspace(): end -= 1
        if start < end:
            spans.append(SentenceReference(sentence_id=f"{prefix}-s{len(spans)+1}", start_offset=start, end_offset=end, text=text[start:end]))
        start = boundary_end
    return spans

def _fixture(scenario_id: str):
    for path in SCENARIOS.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf8"))
        if data["scenario_id"] == scenario_id: return data
    return None

def _tokens(text):
    return [t.casefold() for t in TOKEN.findall(text)]

def _normal(text):
    return " ".join(_tokens(text))

def _rank(claim, sentences):
    """BM25-style lexical discovery score; ranking is not a truth score."""
    q = Counter(_tokens(claim)); docs = [(s, Counter(_tokens(s.text))) for s in sentences]
    n = len(docs); avg = sum(sum(tf.values()) for _, tf in docs) / max(n, 1)
    ranked = []
    for sent, tf in docs:
        dl = sum(tf.values()); score = 0.0
        for term, qf in q.items():
            df = sum(term in other for _, other in docs)
            if term in tf:
                idf = __import__('math').log(1 + (n - df + .5) / (df + .5))
                score += idf * tf[term] * 2.2 / (tf[term] + 1.2 * (0.25 + .75 * dl / max(avg, 1))) * min(qf, 2)
        if score > 0: ranked.append((score, sent))
    return sorted(ranked, key=lambda x: (-x[0], x[1].sentence_id))

def _values(text):
    # Remove complete date spans first so day/month/year components cannot be
    # mistaken for independent quantities. Only compare one unambiguous value.
    without_dates = _DATE_PATTERN.sub(" ", text)
    values = []
    for match in NUMBER.finditer(without_dates):
        raw_number = re.search(r"[+-]?\d+(?:\.\d+)?", match.group(0)).group(0)
        unit_match = re.search(r"(?:%|cm|mm|km|m|kg|mg|g|°[CF]|hours?|days?|years?)$", match.group(0).strip(), re.I)
        try:
            value = Decimal(raw_number).normalize()
        except InvalidOperation:
            continue
        unit = unit_match.group(0).casefold() if unit_match else ""
        values.append((value, unit))
    return values

_MONTH = "January February March April May June July August September October November December".split()
_MONTH_PATTERN = "(?:" + "|".join(_MONTH) + ")"
_DATE_PATTERN = re.compile(rf"\b(?:\d{{4}}-\d{{1,2}}-\d{{1,2}}|\d{{1,2}}\s+{_MONTH_PATTERN}\s+\d{{4}}|{_MONTH_PATTERN}\s+\d{{1,2}},?\s+\d{{4}}|\d{{4}})\b", re.I)

def _date_values(text):
    dates = []
    for match in _DATE_PATTERN.finditer(text):
        raw = match.group(0)
        iso = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
        if iso:
            dates.append(tuple(map(int, iso.groups()))); continue
        day_first = re.fullmatch(rf"(\d{{1,2}})\s+({_MONTH_PATTERN})\s+(\d{{4}})", raw, re.I)
        month_first = re.fullmatch(rf"({_MONTH_PATTERN})\s+(\d{{1,2}}),?\s+(\d{{4}})", raw, re.I)
        if day_first:
            dates.append((int(day_first.group(3)), _MONTH.index(day_first.group(2).title()) + 1, int(day_first.group(1)))); continue
        if month_first:
            dates.append((int(month_first.group(3)), _MONTH.index(month_first.group(1).title()) + 1, int(month_first.group(2)))); continue
        dates.append((int(raw),))
    return dates

def _context_terms(text):
    without_dates = _DATE_PATTERN.sub(" ", text)
    without_values = NUMBER.sub(" ", without_dates)
    return {t for t in _tokens(without_values) if t not in CONTEXT_STOPWORDS and len(t) > 1}

def _same_context(left, right):
    a, b = _context_terms(left), _context_terms(right)
    return len(a & b) >= 2 and len(a & b) / max(len(a | b), 1) >= 0.8

def _polarity_terms(text):
    normalized = re.sub(r"\b(?:isn't|aren't|wasn't|weren't|doesn't|don't|didn't|can't|cannot|won't)\b", " not ", text, flags=re.I)
    return _tokens(normalized)

def _check(claim, passage):
    checks = []
    if any(ch in set('"“”‘’') for ch in passage):
        return None, [DeterministicCheck(check_type="quoted_passage", status="NOT_CHECKED", detail="Polarity and discrepancy checks are skipped because quotation attribution is unresolved.")], ""
    # Compare only a single, unit-compatible value with at least two shared
    # content terms. Multiple values in either sentence are context-ambiguous.
    cvals, evals = _values(claim), _values(passage)
    same_context = _same_context(claim, passage)
    date_c, date_e = _date_values(claim), _date_values(passage)
    if len(cvals) == len(evals) == 1 and cvals[0][1] == evals[0][1] and same_context:
        mismatch = cvals != evals
        checks.append(DeterministicCheck(check_type="quantity_or_unit", status="MISMATCH" if mismatch else "MATCH", detail=f"Compared values in shared context: claim {cvals}; passage {evals}."))
        if mismatch: return "CONTRADICTED", checks, "The retrieved passage gives a different quantity or unit for the same overlapping context."
    if len(date_c) == len(date_e) == 1 and same_context:
        mismatch = date_c != date_e
        checks.append(DeterministicCheck(check_type="date", status="MISMATCH" if mismatch else "MATCH", detail=f"Compared dates in shared context: claim {date_c}; passage {date_e}."))
        if mismatch: return "CONTRADICTED", checks, "The retrieved passage gives a different date for the same overlapping context."
    # A passage-level negation flag has no scope information. Apply only the
    # narrow case where removing explicit negation yields identical wording;
    # quoted text is skipped because attribution is not resolved here.
    quote_marks = set('"“”‘’')
    if not any(ch in quote_marks for ch in passage):
        claim_terms, passage_terms = _polarity_terms(claim), _polarity_terms(passage)
        cneg, pneg = bool(set(claim_terms) & NEGATIONS), bool(set(passage_terms) & NEGATIONS)
        cplain = [t for t in claim_terms if t not in NEGATIONS]
        pplain = [t for t in passage_terms if t not in NEGATIONS]
        if cneg != pneg and cplain == pplain and len(cplain) >= 3:
            checks.append(DeterministicCheck(check_type="polarity", status="MISMATCH", detail="Opposite explicit polarity markers occur in otherwise identical unquoted wording."))
            return "CONTRADICTED", checks, "The passage negates the same wording asserted by the claim."
        antonyms = ({"open", "closed"}, {"available", "unavailable"}, {"enabled", "disabled"}, {"present", "absent"})
        if len(claim_terms) == len(passage_terms):
            differences = [(a, b) for a, b in zip(claim_terms, passage_terms) if a != b]
            if len(differences) == 1 and any(set(differences[0]) == pair for pair in antonyms):
                checks.append(DeterministicCheck(check_type="polarity", status="MISMATCH", detail=f"One explicit antonym differs in otherwise identical wording: {differences[0]}"))
                return "CONTRADICTED", checks, "The passage uses an explicit opposite predicate in otherwise identical wording."
    if not checks: checks.append(DeterministicCheck(check_type="numeric_date_polarity", status="NOT_CHECKED", detail="No safely comparable discrepancy rule applied."))
    return None, checks, ""

def _audit_claim(i, claim, sentences, request):
    ranked = _rank(claim.text, sentences)
    # Candidate threshold is intentionally permissive for evidence discovery, never verdict selection.
    eligible = [(score, s) for score, s in ranked if score >= 0.5]
    # Reserve the best candidate from each supplied source before adding
    # additional passages; a single verbose document cannot crowd out another.
    candidates = []
    seen_sources = set()
    for _, sent in eligible:
        source_id = sent.sentence_id.rsplit("-s", 1)[0]
        if source_id not in seen_sources:
            candidates.append(sent); seen_sources.add(source_id)
    for _, sent in eligible:
        if len(candidates) >= max(3, len(seen_sources)):
            break
        if sent not in candidates:
            candidates.append(sent)
    refs = []
    for s in candidates:
        source_id = s.sentence_id.rsplit("-s", 1)[0]
        refs.append(EvidenceReference(source_id=source_id, sentence_id=s.sentence_id, quote=s.text,
            start_offset=s.start_offset, end_offset=s.end_offset, quotation_validated=True))
    checks=[]; conflict=False; supported=False; contradiction=None
    for ref in refs:
        passage = next(s.text for s in sentences if s.sentence_id == ref.sentence_id)
        verdict, checkset, _ = _check(claim.text, passage); checks.extend(checkset)
        if verdict == "CONTRADICTED": contradiction = ref
        if not any(ch in set('"“”‘’') for ch in passage) and _normal(claim.text) == _normal(passage):
            supported = True
        # Only a direct causal-qualification phrase signals this narrow ambiguity;
        # unrelated negation elsewhere in the sentence is not enough.
        claim_causal = re.search(r"\b(?:cause|causes|caused|causation)\b", claim.text, re.I)
        source_withholds_causation = re.search(
            r"\b(?:does not (?:state|establish|show|prove)|cannot establish|is not established)\b.{0,50}\b(?:cause|caused|causation)\b",
            passage, re.I,
        )
        if claim_causal and source_withholds_causation and not any(ch in set('"“”‘’') for ch in passage):
            conflict = True
    conflicting_sources = bool(contradiction and supported)
    if conflict or conflicting_sources:
        verdict, tier = Verdict.AMBIGUOUS, VerificationTier.MECHANICAL
        note = "Retrieved supplied passages materially conflict about this claim; the baseline cannot resolve the disagreement." if conflicting_sources else "The source distinguishes an observed association from established causation, so the claim wording admits materially different readings."
    elif contradiction:
        verdict, tier = Verdict.CONTRADICTED, VerificationTier.MECHANICAL
        _, _, note = _check(claim.text, next(s.text for s in sentences if s.sentence_id == contradiction.sentence_id))
    elif supported:
        verdict, tier, note = Verdict.SUPPORTED, VerificationTier.MECHANICAL, "A supplied passage states the same normalized claim text. This narrow textual match does not establish source authority or world truth."
    else:
        verdict, tier = Verdict.INSUFFICIENT_EVIDENCE, VerificationTier.INSUFFICIENT
        note = "Relevant passages were retrieved but no implemented rule established support or contradiction." if refs else "No relevant passage met the retrieval threshold; the supplied sources do not establish this claim."
    return ClaimFinding(claim_id=f"claim-{i+1}", claim_text=claim.text, start_offset=claim.start_offset, end_offset=claim.end_offset,
        verdict=verdict, verification_tier=tier, evidence=refs, deterministic_checks=checks,
        note=note, model_score=None, model_score_calibrated=None)

def run_audit(request: AuditRequest) -> AuditResponse:
    data = _fixture(request.scenario_id) if request.scenario_id else None
    if data and data["answer"] == request.answer and data["sources"] == [s.model_dump() for s in request.sources]:
        claims = [ClaimFinding(**c) for c in data["claims"]]
        mode, warnings = ExecutionMode.FIXTURE, ["Curated fixture findings; no model was used."]
    else:
        sentence_map = {s.source_id: split_sentences(s.text, s.source_id) for s in request.sources}
        all_sentences = [sent for group in sentence_map.values() for sent in group]
        claims = [_audit_claim(i, s, all_sentences, request) for i, s in enumerate(split_sentences(request.answer, "claim"))]
        mode = ExecutionMode.BASELINE
        warnings = ["Evidence-based baseline: local lexical retrieval plus narrow deterministic rules; no model was used.", "Lexical relevance is not truth verification. Support requires a normalized textual match; contradiction requires a scoped value/date/polarity rule."]
    if mode == ExecutionMode.FIXTURE:
        sentence_map = {s.source_id: split_sentences(s.text, s.source_id) for s in request.sources}
    counts = {v: sum(c.verdict == v for c in claims) for v in Verdict}
    return AuditResponse(audit_id=f"audit-{uuid4().hex[:12]}", execution_mode=mode, answer=request.answer, sources=request.sources, source_sentences=sentence_map, claims=claims, summary=AuditSummary(supported=counts[Verdict.SUPPORTED], contradicted=counts[Verdict.CONTRADICTED], insufficient_evidence=counts[Verdict.INSUFFICIENT_EVIDENCE], ambiguous=counts[Verdict.AMBIGUOUS], total_claims=len(claims)), warnings=warnings)
