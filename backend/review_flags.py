"""Narrow, transparent review cues. These flags never change a claim verdict."""
import re
from backend.models import ReviewFlag

RULES = {
    "CERTAINTY_MAY_WILL": (re.compile(r"\bmay\b", re.I), re.compile(r"\bwill\b", re.I)),
    "CERTAINTY_SOME_ALL": (re.compile(r"\bsome\b", re.I), re.compile(r"\ball\b", re.I)),
    "CERTAINTY_ASSOCIATION_CAUSATION": (re.compile(r"\b(?:associated with|linked to)\b", re.I), re.compile(r"\bcauses?\b", re.I)),
    "CERTAINTY_SUGGESTS_PROVES": (re.compile(r"\bsuggests?\b", re.I), re.compile(r"\bproves?\b", re.I)),
}
ADVICE = re.compile(r"\b(?:you should|we recommend|must|should|avoid|take|stop taking)\b", re.I)
INFERENCE = re.compile(r"\b(?:therefore|thus|so|proves?|causes?|leads? to)\b", re.I)
ASSOCIATION = re.compile(r"\b(?:associated with|linked to|correlated with|may|might|could|if|when)\b", re.I)
STOP = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "to", "of", "in", "on", "for", "by", "and", "or", "it", "this", "that", "with", "from", "as"}

def _related_context(answer, source, source_term, answer_term):
    clean = re.compile(r"[^\w]+", re.UNICODE)
    left = {word for word in clean.sub(" ", answer.casefold()).split() if word not in STOP and word != answer_term.casefold()}
    right = {word for word in clean.sub(" ", source.casefold()).split() if word not in STOP and word != source_term.casefold()}
    return len(left & right) >= 2 and len(left & right) / max(len(left | right), 1) >= .45

def review_claim(claim_id, claim_text, candidates):
    """Compare only retrieved candidate wording; do not infer source completeness."""
    flags = []
    for item in candidates:
        source = item["text"]
        for rule_id, (source_pattern, answer_pattern) in RULES.items():
            source_match, answer_match = source_pattern.search(source), answer_pattern.search(claim_text)
            if source_match and answer_match and _related_context(claim_text, source, source_match.group(0), answer_match.group(0)):
                flags.append(ReviewFlag(flag_id=f"{claim_id}-{rule_id.lower()}-{item['sentence_id']}", flag_type="CERTAINTY_DRIFT",
                    explanation="The answer uses stronger certainty or scope wording than this retrieved passage.",
                    answer_wording=answer_match.group(0), source_wording=source_match.group(0),
                    source_id=item["source_id"], source_label=item["source_label"], source_title=item["source_title"],
                    sentence_id=item["sentence_id"], start_offset=item["start_offset"], end_offset=item["end_offset"],
                    rule_id=rule_id, caveat_sentences=[source], limitations="Review cue only; this passage may not represent the complete source."))
        if ADVICE.search(claim_text):
            caveat = source if re.search(r"\b(?:not|avoid|unless|consult|risk|may|might|should)\b", source, re.I) else ""
            flags.append(ReviewFlag(flag_id=f"{claim_id}-advice-{item['sentence_id']}", flag_type="ADVICE_REVIEW",
                explanation="Advice wording needs human review against the retrieved evidence and its caveats.",
                answer_wording=ADVICE.search(claim_text).group(0), source_wording=source,
                source_id=item["source_id"], source_label=item["source_label"], source_title=item["source_title"],
                sentence_id=item["sentence_id"], start_offset=item["start_offset"], end_offset=item["end_offset"],
                rule_id="ADVICE_REQUIRES_HUMAN_REVIEW", caveat_sentences=[caveat] if caveat else [],
                limitations="This is not a safety or medical judgment. " + ("Caveat wording was found in this retrieved passage." if caveat else "No caveat was found in this retrieved passage; that does not mean the source has none.")))
        cue = INFERENCE.search(claim_text)
        if cue and cue.group(0).casefold() == "therefore" and re.search(r"\btherefore\s+(?:recommends?|suggests?|reports?|notes?)\b", claim_text, re.I):
            cue = None
        if cue:
            association = ASSOCIATION.search(source)
            flags.append(ReviewFlag(flag_id=f"{claim_id}-inference-{item['sentence_id']}", flag_type="INFERENCE_REVIEW",
                explanation="An inference cue appears in the answer; the retrieved premise itself needs review.",
                answer_wording=cue.group(0), source_wording=association.group(0) if association else source,
                source_id=item["source_id"], source_label=item["source_label"], source_title=item["source_title"],
                sentence_id=item["sentence_id"], start_offset=item["start_offset"], end_offset=item["end_offset"],
                rule_id="INFERENCE_CUE_REVIEW", caveat_sentences=[source] if association else [],
                limitations="The relationship could not be established from this passage alone; review the premise and connection."))
    return flags
