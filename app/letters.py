"""Evidence-first, deterministic cover-letter drafting without external API calls.
Never creates employment claims or statistics not listed in the source resume.
"""
from .analyzer import _requirement_groups, _evidence


def cover_letter(name: str, company: str, role: str, resume: str, jd: str) -> dict:
    requirements, preferred = _requirement_groups(jd)
    matched = [x for x in (requirements + preferred)[:35] if _evidence(resume, x)]
    matched = list(dict.fromkeys(matched))[:5]
    # A mention in the resume is evidence of *documentation*, not independently
    # verified expertise; the copy therefore avoids claiming years or proficiency.
    if matched:
        topic = ', '.join(matched[:3])
        fit = (f'Your job description references {topic}. My resume documents experience '
               f'or project work mentioning these areas, and I would welcome the opportunity '
               f'to discuss the relevant examples with your team.')
    else:
        fit = ('I would appreciate the chance to discuss my relevant coursework, '
               'projects, and transferable experience in more detail.')
    text = (f'{name.strip() or "Applicant"}\n\n'
            f'Dear Hiring Team,\n\n'
            f'I am writing to express my interest in the {role.strip()} role at {company.strip()}. '
            f'I am excited by the responsibilities described in this opportunity and would '
            f'like to be considered.\n\n'
            f'{fit}\n\n'
            f'I would be glad to share specific examples of my work and learn more about '
            f'the challenges your team is solving. Thank you for your time and consideration.\n\n'
            f'Sincerely,\n{name.strip() or "Applicant"}')
    return {'draft': text, 'matched_terms': matched,
            'warning': 'Template only. Verify every statement against your actual experience before sending. No hiring outcomes are guaranteed.',
            'external_ai_used': False}
