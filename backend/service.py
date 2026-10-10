"""Source-driven, deterministic evidence discovery and conservative checks."""
import json
import os
import re
from functools import lru_cache
from decimal import Decimal, InvalidOperation
from collections import Counter
from pathlib import Path
from uuid import uuid4
from backend.models import *
from backend.verifier import NliResult, load_local_verifier
from backend.review_flags import review_claim
import hashlib

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "data" / "scenarios"
TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
NUMBER = re.compile(r"(?<!\w)[+-]?\d+(?:\.\d+)?(?:\s*(?:%|cm|mm|m|km|kg|g|mg|°[CF]|hours?|days?|weeks?|months?|years?))?", re.I)
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

def _duplicate_sources(sources):
    """Conservative text similarity; IDs are stable and filenames are ignored."""
    duplicates = {}
    canonical = []
    for source in sources:
        normalized = _normal(source.text)
        digest = hashlib.sha256(normalized.encode("utf8")).hexdigest()
        duplicate = next((sid for sid, _, other_digest, _ in canonical if digest == other_digest), None)
        sentence_sets = [set(_tokens(sentence.text)) for sentence in split_sentences(source.text, source.source_id)
                         if len(_tokens(sentence.text)) >= 8]
        if duplicate is None and sentence_sets:
            for sid, _, other_digest, other_sentences in canonical:
                if any(min(len(left), len(right)) >= 8 and len(left & right) / max(len(left | right), 1) >= .90
                       for left in sentence_sets for right in other_sentences):
                    duplicate = sid; break
        if duplicate:
            duplicates[source.source_id] = duplicate
        else:
            canonical.append((source.source_id, normalized, digest, sentence_sets))
    return duplicates

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
        unit_match = re.search(r"(?:%|cm|mm|km|m|kg|mg|g|°[CF]|hours?|days?|weeks?|months?|years?)$", match.group(0).strip(), re.I)
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

def _triage_reason(text):
    """Narrow, auditable rules for obvious non-assertions; uncertain text stays in scope."""
    stripped = text.strip()
    if stripped.endswith("?"):
        return "Question detected; no factual assertion was evaluated."
    words = _tokens(stripped)
    heading = re.sub(r"[^\w\s]", "", stripped.casefold()).strip()
    if heading in {"overview", "summary", "introduction", "background", "conclusion", "in conclusion", "in summary", "however", "therefore", "for example", "note", "next steps", "key takeaways"}:
        return "Heading or transition label detected; not assessed as a factual claim."
    if words and words[0] in {"please", "consider", "imagine", "remember", "note", "see", "refer", "look", "let", "use", "add", "remove", "choose", "select", "click", "open", "close", "enter", "run", "avoid", "keep", "do", "make", "check", "visit", "try"}:
        return "Instruction or command pattern detected; not assessed as a factual claim."
    if len(words) <= 5 and not re.search(r"[.!?]$", stripped):
        return "Short heading or label pattern detected; not assessed as a factual claim."
    if re.match(r"^(?:I think|I believe|I feel|in my opinion|we think|we believe)\b", stripped, re.I):
        return "Explicit opinion wording detected; not assessed as a factual claim."
    return None

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
    # Days and weeks have a fixed conversion. Calendar months deliberately do
    # not: their length varies, so month/week pairs abstain from this rule.
    duration_days = {"day": Decimal(1), "days": Decimal(1), "week": Decimal(7), "weeks": Decimal(7)}
    if len(cvals) == len(evals) == 1 and cvals[0][1] in duration_days and evals[0][1] in duration_days and same_context:
        claim_days = cvals[0][0] * duration_days[cvals[0][1]]
        passage_days = evals[0][0] * duration_days[evals[0][1]]
        mismatch = claim_days != passage_days
        checks.append(DeterministicCheck(check_type="duration", status="MISMATCH" if mismatch else "MATCH",
            detail=f"Compared durations using the fixed day/week conversion: claim {claim_days} days; passage {passage_days} days."))
        if mismatch: return "CONTRADICTED", checks, "The retrieved passage gives a different duration after a fixed day/week conversion."
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

_AUTO_VERIFIER = object()

@lru_cache(maxsize=2)
def _configured_verifier(path: str):
    return load_local_verifier(path)

def configured_verifier():
    """Opt in only through an explicit local directory; unset means baseline mode."""
    path = os.getenv("REFUTELLA_NLI_MODEL_PATH", "").strip()
    return _configured_verifier(path) if path else None

def _audit_claim(i, claim, sentences, request, verifier=None, assess_flagged=False):
    triage = _triage_reason(claim.text)
    duplicates = _duplicate_sources(request.sources)
    labels = {source.source_id: f"S{n+1}" for n, source in enumerate(request.sources)}
    if triage and not assess_flagged:
        return ClaimFinding(claim_id=f"claim-{i+1}", claim_text=claim.text, start_offset=claim.start_offset,
            end_offset=claim.end_offset, verdict=Verdict.NOT_ASSESSED, verification_tier=VerificationTier.INSUFFICIENT,
            note=triage, triage_reason=triage, plain_summary=triage,
            search_receipt=SearchReceipt(status="NOT_ASSESSED", reason_code="NOT_ASSESSED"))
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
    receipt_candidates = []
    for s in candidates:
        source_id = s.sentence_id.rsplit("-s", 1)[0]
        source = next(src for src in request.sources if src.source_id == source_id)
        duplicate_of = duplicates.get(source_id)
        matched = sorted(set(_tokens(claim.text)) & set(_tokens(s.text)))
        reason = "DUPLICATE_SOURCE" if duplicate_of else "RETRIEVED_UNRESOLVED"
        receipt_candidates.append(ReceiptCandidate(source_id=source_id, source_label=labels[source_id], source_title=source.title,
            sentence_id=s.sentence_id, snippet=s.text, start_offset=s.start_offset, end_offset=s.end_offset,
            matched_terms=matched, reason_code=reason, duplicate_of=duplicate_of))
        refs.append(EvidenceReference(source_id=source_id, sentence_id=s.sentence_id, quote=s.text,
            start_offset=s.start_offset, end_offset=s.end_offset, quotation_validated=True))
    checks=[]; conflict=False; supported=False; contradiction=None
    model_entailments=[]; model_contradictions=[]; model_unknown=[]; model_failures=[]; semantic=[]
    for ref in refs:
        passage = next(s.text for s in sentences if s.sentence_id == ref.sentence_id)
        verdict, checkset, _ = _check(claim.text, passage); checks.extend(checkset)
        if verdict == "CONTRADICTED": contradiction = ref
        if not any(ch in set('"“”‘’') for ch in passage) and _normal(claim.text) == _normal(passage):
            supported = True
        if verifier is not None:
            if any(ch in set('"“”‘’') for ch in passage):
                result = NliResult("INCONCLUSIVE", verifier.model_id, detail="Quoted passage skipped because attribution is unresolved.")
            else:
                try:
                    result = verifier.verify(passage, claim.text)
                except Exception as exc:
                    result = NliResult("ERROR", verifier.model_id, detail=f"Inference failed: {type(exc).__name__}: {exc}")
            semantic.append(SemanticVerification(status=result.label, source_id=ref.source_id,
                sentence_id=ref.sentence_id, model_id=result.model_id, raw_logits=result.raw_logits,
                detail=result.detail))
            if result.label == "ENTAILMENT": model_entailments.append(ref)
            elif result.label == "CONTRADICTION": model_contradictions.append(ref)
            elif result.label in {"NEUTRAL", "INCONCLUSIVE", "UNAVAILABLE", "ERROR"}: model_unknown.append(result)
            if result.label in {"INCONCLUSIVE", "UNAVAILABLE", "ERROR"}: model_failures.append(result)
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
    model_conflict = bool(model_entailments and model_contradictions)
    mechanical_model_conflict = bool((contradiction and model_entailments) or (model_contradictions and supported))
    exact_nli_conflict = bool(supported and model_unknown)
    partial_nli_conflict = bool(model_failures and (model_entailments or model_contradictions))
    if conflict or conflicting_sources or model_conflict or mechanical_model_conflict or exact_nli_conflict or partial_nli_conflict:
        verdict = Verdict.AMBIGUOUS
        tier = VerificationTier.MODEL if model_entailments or model_contradictions or model_unknown else VerificationTier.MECHANICAL
        if conflict:
            note = "The source explicitly withholds a causal conclusion; this baseline cannot resolve the claim's causal interpretation."
        else:
            note = "Retrieved passages or independent checks disagree about this claim; the audit remains ambiguous."
    elif contradiction:
        verdict, tier = Verdict.CONTRADICTED, VerificationTier.MECHANICAL
        _, _, note = _check(claim.text, next(s.text for s in sentences if s.sentence_id == contradiction.sentence_id))
        if model_unknown:
            note += " NLI verification was unavailable or inconclusive; this verdict relies on the deterministic check only."
    elif model_contradictions:
        verdict, tier = Verdict.AMBIGUOUS, VerificationTier.MODEL_FLAG
        note = "The local verifier flagged a possible conflict, but no deterministic contradiction rule confirmed it. NLI output is uncalibrated and fallible."
    elif model_entailments:
        verdict, tier = Verdict.SUPPORTED, VerificationTier.MODEL
        note = "The local NLI verifier judged retrieved evidence to entail the claim; its output is uncalibrated and fallible."
    elif supported and not model_unknown:
        verdict, tier, note = Verdict.SUPPORTED, VerificationTier.MECHANICAL, "A supplied passage states the same normalized claim text. This narrow textual match does not establish source authority or world truth."
    else:
        verdict, tier = Verdict.INSUFFICIENT_EVIDENCE, VerificationTier.INSUFFICIENT
        note = "NLI verification was unavailable, failed, or inconclusive; no independent deterministic rule established a verdict." if model_unknown else "Relevant passages were retrieved but no implemented rule established support or contradiction." if refs else "No relevant passage met the retrieval threshold; the supplied sources do not establish this claim."
    plain_summary = (f"The source says “{next(s.text for s in sentences if s.sentence_id == contradiction.sentence_id)},” while the answer says “{claim.text}.”" if contradiction else
        "The source contains the same normalized wording as the answer; this is a text match, not proof of truth." if verdict == Verdict.SUPPORTED and tier == VerificationTier.MECHANICAL else
        "The local NLI model judged a retrieved passage to entail the claim; its output is fallible and uncalibrated." if verdict == Verdict.SUPPORTED else
        "The local NLI model judged a retrieved passage to contradict the claim; its output is fallible and uncalibrated." if verdict == Verdict.CONTRADICTED and not contradiction else
        "Retrieved passages or checks disagree, so the available evidence does not settle this claim." if verdict == Verdict.AMBIGUOUS else
        "Relevant passages were found, but no implemented check established support or contradiction." if refs else
        "No relevant passage was retrieved from the supplied sources." if verdict == Verdict.INSUFFICIENT_EVIDENCE else
        f"The supplied evidence was assessed as {verdict.value.replace('_', ' ').lower()}." if not triage else f"Included for assessment by request. {triage}")
    finding_id = f"claim-{i+1}"
    flag_candidates = [{"source_id": c.source_id, "source_label": c.source_label, "source_title": c.source_title,
        "sentence_id": c.sentence_id, "start_offset": c.start_offset, "end_offset": c.end_offset, "text": c.snippet}
        for c in receipt_candidates]
    receipt_status = "RETRIEVED" if receipt_candidates else ("SOURCE_EMPTY" if all(not src.text.strip() for src in request.sources) else "NO_CANDIDATE")
    receipt_reason = "RETRIEVED_UNRESOLVED" if receipt_candidates else ("SOURCE_EMPTY" if receipt_status == "SOURCE_EMPTY" else "NO_CANDIDATE")
    for candidate in receipt_candidates:
        if candidate.duplicate_of:
            continue
        if contradiction and candidate.sentence_id == contradiction.sentence_id:
            candidate.reason_code = "CONTRADICTION_RULE"
        elif any(ref.sentence_id == candidate.sentence_id for ref in model_entailments):
            candidate.reason_code = "MODEL_ENTAILMENT"
        elif any(ref.sentence_id == candidate.sentence_id for ref in model_contradictions):
            candidate.reason_code = "MODEL_CONFLICT"
        elif supported and any(ref.sentence_id == candidate.sentence_id for ref in refs):
            candidate.reason_code = "SUPPORT_RULE"
    return ClaimFinding(claim_id=finding_id, claim_text=claim.text, start_offset=claim.start_offset, end_offset=claim.end_offset,
        triage_reason=triage, plain_summary=plain_summary,
        verdict=verdict, verification_tier=tier, evidence=refs, deterministic_checks=checks,
        semantic_verifications=semantic, note=note, model_score=None, model_score_calibrated=None,
        search_receipt=SearchReceipt(query_terms=list(dict.fromkeys(_tokens(claim.text))), status=receipt_status,
            candidates=receipt_candidates, reason_code=receipt_reason),
        review_flags=review_claim(finding_id, claim.text, flag_candidates))

def run_audit(request: AuditRequest, verifier=_AUTO_VERIFIER) -> AuditResponse:
    data = _fixture(request.scenario_id) if request.scenario_id else None
    if data and data["answer"] == request.answer and data["sources"] == [s.model_dump() for s in request.sources]:
        claims = [ClaimFinding(**c) for c in data["claims"]]
        mode, warnings = ExecutionMode.FIXTURE, ["Curated fixture findings; no model was used."]
    else:
        if verifier is _AUTO_VERIFIER:
            verifier = configured_verifier()
        sentence_map = {s.source_id: split_sentences(s.text, s.source_id) for s in request.sources}
        all_sentences = [sent for group in sentence_map.values() for sent in group]
        claim_spans = split_sentences(request.answer, "claim")
        claims = [_audit_claim(i, s, all_sentences, request, verifier if verifier is not None and verifier.available else None,
                    f"claim-{i+1}" in request.assess_claim_ids) for i, s in enumerate(claim_spans)]
        if verifier is None:
            mode = ExecutionMode.BASELINE
            warnings = ["Evidence-based baseline: local lexical retrieval plus narrow deterministic rules; no model was used.", "Lexical relevance is not truth verification. Support requires a normalized textual match; contradiction requires a scoped value/date/polarity rule."]
        elif not verifier.available:
            mode = ExecutionMode.MODEL_UNAVAILABLE
            # Return explicit per-passage unavailable states without silently invoking another verifier.
            for finding in claims:
                finding.semantic_verifications = [SemanticVerification(status="UNAVAILABLE", source_id=ref.source_id,
                    sentence_id=ref.sentence_id, model_id=verifier.model_id, detail=verifier.detail) for ref in finding.evidence]
                if finding.verdict in {Verdict.SUPPORTED, Verdict.CONTRADICTED} and finding.verification_tier == VerificationTier.MODEL:
                    finding.verdict = Verdict.INSUFFICIENT_EVIDENCE
                    finding.verification_tier = VerificationTier.INSUFFICIENT
                    finding.note = "Optional NLI is unavailable; no semantic verdict was substituted."
            warnings = [f"Optional local NLI ({verifier.model_id}) is unavailable: {verifier.detail}", "No NLI verdict was substituted. Deterministic baseline checks remain independent and limited."]
        else:
            mode = ExecutionMode.MODEL
            warnings = [f"Model-assisted verification used local NLI model {verifier.model_id}.", "NLI logits and class-margin decisions are fallible and uncalibrated; lexical retrieval only selects passages and never establishes support."]
    if mode == ExecutionMode.FIXTURE:
        sentence_map = {s.source_id: split_sentences(s.text, s.source_id) for s in request.sources}
    counts = {v: sum(c.verdict == v for c in claims) for v in Verdict}
    labels = {source.source_id: f"S{i+1}" for i, source in enumerate(request.sources)}
    duplicates = _duplicate_sources(request.sources)
    return AuditResponse(audit_id=f"audit-{uuid4().hex[:12]}", execution_mode=mode, answer=request.answer, sources=request.sources, source_sentences=sentence_map, source_labels=labels, claims=claims, summary=AuditSummary(supported=counts[Verdict.SUPPORTED], contradicted=counts[Verdict.CONTRADICTED], insufficient_evidence=counts[Verdict.INSUFFICIENT_EVIDENCE], ambiguous=counts[Verdict.AMBIGUOUS], not_assessed=counts[Verdict.NOT_ASSESSED], total_claims=len(claims)), warnings=warnings, duplicate_sources=duplicates)

def run_stress_experiment(experiment: StressExperimentRequest) -> StressExperimentResponse:
    """Rerun the regular engine over immutable, request-local source copies."""
    baseline = experiment.baseline
    sources = [source.model_copy(deep=True) for source in baseline.sources]
    source = next((item for item in sources if item.source_id == experiment.source_id), None)
    if source is None:
        raise ValueError(f"Unknown source_id: {experiment.source_id}")

    sentence = None
    if experiment.operation != "REMOVE_SOURCE":
        sentence = next((item for item in baseline.source_sentences[source.source_id]
                         if item.sentence_id == experiment.sentence_id), None)
        if sentence is None:
            raise ValueError(f"Unknown sentence_id {experiment.sentence_id!r} for source {source.source_id}")
        if not any(ref.source_id == source.source_id and ref.sentence_id == sentence.sentence_id
                   for claim in baseline.claims for ref in claim.evidence):
            raise ValueError("The selected sentence is not a retrieved evidence passage in the baseline")

    changed_text = ""
    label = ""
    if experiment.operation == "REMOVE_SOURCE":
        sources = [item for item in sources if item.source_id != source.source_id]
        changed_text = source.text
        label = f"Removed source {source.source_id} — {source.title}"
    elif experiment.operation == "REMOVE_PASSAGE":
        changed_text = sentence.text
        source.text = source.text[:sentence.start_offset] + source.text[sentence.end_offset:]
        if not source.text.strip():
            sources = [item for item in sources if item.source_id != source.source_id]
        label = f"Removed passage {sentence.sentence_id} from {source.source_id}"
    else:
        changed_text = experiment.replacement_text or ""
        if changed_text == sentence.text:
            raise ValueError("Replacement text is unchanged from the selected passage")
        source.text = source.text[:sentence.start_offset] + changed_text + source.text[sentence.end_offset:]
        label = f"Edited passage {sentence.sentence_id} in {source.source_id}"

    if not sources:
        comparison = [StressClaimComparison(claim_id=c.claim_id, claim_text=c.claim_text,
            baseline=c, perturbed=None, outcome="NOT_COMPARABLE",
            explanation="No source context remains, so the audit engine cannot run with its required non-empty source set.",
            baseline_execution_mode=baseline.execution_mode, perturbed_execution_mode=None)
            for c in baseline.claims]
        warnings = ["The experiment removed the entire source context; no perturbed audit was run."]
        if baseline.execution_mode == ExecutionMode.FIXTURE:
            warnings.append("The baseline used curated fixture findings; the empty-context experiment cannot be directly compared with them.")
        return StressExperimentResponse(experiment_label=label, changed_source_id=source.source_id,
            changed_sentence_id=experiment.sentence_id, changed_text=changed_text, baseline=baseline,
            perturbed=None, comparisons=comparison, comparable=False,
            warnings=warnings)

    try:
        request = AuditRequest(answer=baseline.answer, sources=sources, scenario_id=None)
        perturbed = run_audit(request)
    except Exception as exc:
        if isinstance(exc, (ValueError,)):
            raise
        raise ValueError(f"The experiment could not be audited: {exc}") from exc
    by_id = {claim.claim_id: claim for claim in perturbed.claims}
    comparisons = []
    modes_comparable = baseline.execution_mode == perturbed.execution_mode and baseline.execution_mode != ExecutionMode.FIXTURE
    for original in baseline.claims:
        updated = by_id.get(original.claim_id)
        if not modes_comparable:
            outcome = "NOT_COMPARABLE"
            explanation = ("The baseline is a curated fixture and the perturbed result comes from the audit engine; verdict differences are not directly comparable."
                           if baseline.execution_mode == ExecutionMode.FIXTURE else
                           f"Execution modes differ ({baseline.execution_mode.value} vs {perturbed.execution_mode.value}); verdict differences are not directly comparable.")
        elif updated is None:
            outcome = "NOT_COMPARABLE"
            explanation = "The perturbed audit returned no corresponding claim."
        elif updated.verdict != original.verdict:
            outcome = "UNRESOLVED" if updated.verdict == Verdict.INSUFFICIENT_EVIDENCE else "CHANGED"
            explanation = f"The verdict changed from {original.verdict.value} to {updated.verdict.value} in the returned audit."
        else:
            outcome = "UNCHANGED"
            explanation = f"Both audits returned {original.verdict.value}; this result alone does not indicate evidence independence or model memory leakage."
        comparisons.append(StressClaimComparison(claim_id=original.claim_id, claim_text=original.claim_text,
            baseline=original, perturbed=updated, outcome=outcome, explanation=explanation,
            baseline_execution_mode=baseline.execution_mode,
            perturbed_execution_mode=perturbed.execution_mode if updated is not None else None))
    warnings = [f"Baseline ({baseline.execution_mode.value}): {warning}" for warning in baseline.warnings]
    warnings.extend(f"Perturbed ({perturbed.execution_mode.value}): {warning}" for warning in perturbed.warnings)
    if baseline.execution_mode == ExecutionMode.FIXTURE:
        warnings.append("The baseline used curated fixture findings; the perturbed audit uses the live engine, so mode differences limit direct comparability.")
    if baseline.execution_mode != perturbed.execution_mode:
        warnings.append(f"Execution modes differ ({baseline.execution_mode.value} baseline, {perturbed.execution_mode.value} perturbed).")
    return StressExperimentResponse(experiment_label=label, changed_source_id=source.source_id,
        changed_sentence_id=experiment.sentence_id, changed_text=changed_text, baseline=baseline,
        perturbed=perturbed, comparisons=comparisons, comparable=modes_comparable,
        warnings=warnings)
