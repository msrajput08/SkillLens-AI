"""Transparent NLP-based JD alignment analysis.

No model here can predict an employer's proprietary ATS outcome; score is an
explainable heuristic combining literal skill evidence, TF-IDF overlap, and
resume structure. No personally identifiable resume content is persisted.
"""

import re
from collections import OrderedDict
from math import floor

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .taxonomy import SKILLS


def _contains(text: str, alias: str) -> bool:
    # Whitespace and punctuation boundaries prevent 'java' matching 'javascript'.
    # Match symbol-bearing names like C++, C#, CI/CD too.
    return bool(re.search(r"(?<![\w+#])" + re.escape(alias) + r"(?![\w+#])", text, re.I))


def _mentions(text: str):
    return {skill for skill, aliases in SKILLS.items() if any(_contains(text, alias) for alias in aliases)}


def _evidence(text: str, skill: str) -> str:
    rows = [line.strip() for line in text.splitlines() if line.strip()]
    aliases = SKILLS[skill]
    hits = [row for row in rows if any(_contains(row, alias) for alias in aliases)]
    # Prefer a project/skills line over contact information. Returned excerpts
    # intentionally redact basic identifiers even though the requesting user
    # supplied the full resume.
    hits.sort(key=lambda row: bool(re.search(r"@|(?:https?://)|(?:www\.)|linkedin\.com|github\.com", row, re.I)))
    for row in hits:
        row = re.sub(r"[\w.+'-]+@[\w.-]+\.[a-z]{2,}", "[email]", row, flags=re.I)
        row = re.sub(r"(?:https?://|www\.)\S+|(?:linkedin|github)\.com/\S+", "[profile link]", row, flags=re.I)
        row = re.sub(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)", "[phone]", row)
        row = re.sub(r"\s+", " ", row)
        return row[:225] + ("…" if len(row) > 225 else "")
    return ""


def _requirement_groups(jd: str):
    """Treat skills under 'preferred' headers as preferred; otherwise required.

    This conservative parser does not assert hiring criteria it cannot read.
    """
    preferred_header = re.compile(r"\b(preferred|nice[- ]to[- ]have|bonus|good[- ]to[- ]have|desirable|plus if)\b", re.I)
    required_header = re.compile(r"\b(requirements?|must[- ]have|required|qualifications?|what you(?:'|’)ll need|responsibilities|you should have)\b", re.I)
    found = OrderedDict()
    section = "required"
    for line in jd.splitlines():
        clean = line.strip()
        if not clean:
            continue
        # Section classification applies from an explicit heading, not an arbitrary
        # sentence containing "preferred" or "required".
        is_header = bool(re.search(r":\s*$", clean) or (len(clean) <= 48 and not clean.endswith(".")))
        if is_header and preferred_header.search(clean):
            section = "preferred"
        elif is_header and required_header.search(clean):
            section = "required"
        for skill, aliases in SKILLS.items():
            if any(_contains(clean, alias) for alias in aliases):
                # Required mentions take precedence if both sections mention skill.
                if skill not in found or section == "required":
                    found[skill] = section
    required = [skill for skill, group in found.items() if group == "required"]
    preferred = [skill for skill, group in found.items() if group == "preferred"]
    return required, preferred


def _similarity(resume: str, jd: str) -> float:
    try:
        vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True, max_features=14000)
        X = vectorizer.fit_transform([resume, jd])
        return max(0.0, min(1.0, float(cosine_similarity(X[0], X[1])[0, 0])))
    except ValueError:
        return 0.0


def _structure(text: str):
    clean = text.lower()
    sections = OrderedDict([
        ("Contact details", bool(re.search(r"[\w.+'-]+@[\w.-]+\.[a-z]{2,}", text, re.I))),
        ("Skills section", bool(re.search(r"(?im)^\s*(technical\s+)?skills(?:\s*&\s*tools)?\s*[:\-]?\s*$", text)) or "technical skills" in clean),
        ("Projects or experience", bool(re.search(r"(?im)^\s*(?:work\s+)?experience\s*[:\-]?\s*$|^\s*projects?\s*[:\-]?\s*$", text)) or "internship" in clean),
        ("Education section", bool(re.search(r"(?im)^\s*education\s*[:\-]?\s*$", text)) or "bachelor" in clean or "master of" in clean),
        ("Measurable impact", bool(re.search(r"(?:\d+(?:\.\d+)?\s*%|(?:increased|reduced|improved|saved|grew|decreased)\s+[^.!\n]{0,70}\d|\b\d+[kKmM+]\s+(?:users|requests|records|downloads))", text, re.I))),
    ])
    return sections


def analyze(resume: str, jd: str, target_role: str = "", semantic: dict | None = None, custom_evidence: list[dict] | None = None) -> dict:
    resume_skills = _mentions(resume)
    required, preferred = _requirement_groups(jd)
    matched_required = [x for x in required if x in resume_skills]
    missing_required = [x for x in required if x not in resume_skills]
    matched_preferred = [x for x in preferred if x in resume_skills]
    missing_preferred = [x for x in preferred if x not in resume_skills]
    sections = _structure(resume)
    structure_score = sum(sections.values()) / len(sections)
    text_overlap = _similarity(resume, jd)
    # TF-IDF on short CV/JD pairs often has low cosine even for strong alignment;
    # rescale for a useful contribution, not to claim a trained semantic model.
    overlap_component = min(1.0, text_overlap / 0.36)
    if semantic is not None:
        # Opt-in pretrained embedding similarity; weights unchanged and displayed.
        overlap_component = max(0.0, min(1.0, float(semantic['score'])))
    req_match = len(matched_required) / len(required) if required else None
    pref_match = len(matched_preferred) / len(preferred) if preferred else None
    weights = {"required_skills": 0.50 if required else 0,
               "preferred_skills": 0.15 if preferred else 0,
               "text_overlap": 0.25,
               "resume_structure": 0.10}
    # Redistribute missing category weights to content overlap, so they sum to 1.
    weights["text_overlap"] += 1 - sum(weights.values())
    final = 100 * (weights["required_skills"] * (req_match or 0)
                   + weights["preferred_skills"] * (pref_match or 0)
                   + weights["text_overlap"] * overlap_component
                   + weights["resume_structure"] * structure_score)
    score = max(0, min(100, floor(final + 0.5)))
    if score >= 80:
        verdict = "Strong documented match"
    elif score >= 60:
        verdict = "Promising match"
    elif score >= 40:
        verdict = "Partial match"
    else:
        verdict = "Needs closer alignment"

    improvements = []
    for skill in missing_required[:5]:
        improvements.append({
            "priority": "High",
            "title": f"Clarify your experience with {skill}",
            "detail": f"The job description mentions {skill}, but the resume does not explicitly mention it. If you genuinely have this experience, add a truthful project or work example. Otherwise, treat it as a learning gap.",
        })
    for label, present in sections.items():
        if not present:
            messages = {
                "Contact details": "Add a professional email address so employers can reach you.",
                "Skills section": "Include a short, easy-to-scan technical skills section containing tools you actually know.",
                "Projects or experience": "Describe relevant projects or experience, your role, the tools used and a concrete result.",
                "Education section": "Include your degree, institution and graduation year if applicable.",
                "Measurable impact": "Where you have verified figures, show outcomes (performance, scale, accuracy or time saved). Never invent metrics.",
            }
            improvements.append({"priority": "Medium", "title": f"Improve: {label.lower()}", "detail": messages[label]})
    if not improvements:
        improvements.append({"priority": "Low", "title": "Sharpen role-specific evidence", "detail": "Move your strongest relevant examples nearer the top, use concise action verbs, and quantify only outcomes you can verify."})

    strengths = [{"skill": skill, "evidence": _evidence(resume, skill)} for skill in (matched_required + matched_preferred)[:10]]
    if not required and not preferred:
        notes = "No skills from the supported skills dictionary were identified in this job description. The score relies mostly on text overlap and resume structure; interpret with extra caution."
    else:
        notes = "A skill marked 'not found' may still be one you possess; it means the specific wording was not detected in the resume. Skills explicitly listed are not independently verified."
    role = target_role.strip()[:100] or "this role"
    interview = [f"Tell me about a project where you used {s}. What did you personally build?" for s in matched_required[:3]]
    interview += [f"How would you approach a task requiring {s}? What would you need to learn?" for s in missing_required[:2]]
    if not interview:
        interview = [f"What is your most relevant project for {role}, and what measurable result did you achieve?",
                     "Which job requirement can you demonstrate with the strongest real example?"]

    return {
        "score": score,
        "verdict": verdict,
        "role": role,
        "summary": f"Found {len(matched_required)} of {len(required)} detected core skills and {len(matched_preferred)} of {len(preferred)} preferred skills explicitly in your resume. This is a document-alignment estimate, not a hiring prediction.",
        "required": {"matched": matched_required, "not_found": missing_required, "total": len(required)},
        "preferred": {"matched": matched_preferred, "not_found": missing_preferred, "total": len(preferred)},
        "resume_skills": sorted(resume_skills),
        "evidence": strengths,
        "sections": [{"name": key, "present": value} for key, value in sections.items()],
        "text_overlap_percent": round(text_overlap * 100),
        "breakdown": [
            {"key": "required_skills", "label": "Core skill evidence", "weight": round(weights["required_skills"] * 100), "score": round((req_match or 0) * 100)},
            {"key": "preferred_skills", "label": "Preferred skill evidence", "weight": round(weights["preferred_skills"] * 100), "score": round((pref_match or 0) * 100)},
            {"key": "text_overlap", "label": "Semantic evidence relevance" if semantic else "Text relevance", "weight": round(weights["text_overlap"] * 100), "score": round(overlap_component * 100)},
            {"key": "resume_structure", "label": "Resume essentials", "weight": round(weights["resume_structure"] * 100), "score": round(structure_score * 100)},
        ],
        "improvements": improvements,
        "interview_questions": interview[:5],
        "notes": notes,
        "semantic": semantic,
        "custom_evidence": custom_evidence or [],
        "methodology": "Weighted job-description skill mentions, " + ("opt-in local sentence embeddings" if semantic else "TF-IDF lexical similarity") + ", and resume structure. Optional custom classifier assesses evidence snippets only. Not an employer ATS or hiring prediction.",
    }
