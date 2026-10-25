"""Interpret open-ended fact keys consistently without rewriting their identity.

Field keys identify individual facts (e.g. experience_startup and experience_internship),
not unique categories. Keep those keys and provenance intact; resolve categories only
when a consumer needs them. Unknown, private and aspirational labels fail closed.
"""

import re

# Exact contact aliases only: never infer contact data from arbitrary fact names.
CONTACT_FIELD_ALIASES = {
    "name": ("name",),
    "email": ("email", "contact_email", "email_address"),
    "phone": ("phone", "contact_phone", "phone_number"),
    "github": ("github", "github_url"),
    "linkedin": ("linkedin", "linkedin_url"),
    "portfolio": ("portfolio", "portfolio_url"),
    "website": ("website", "website_url"),
}


def is_contact_field(field: str) -> bool:
    return any(field in aliases for aliases in CONTACT_FIELD_ALIASES.values())


_ALIASES = {
    "name": ("name",),
    "target_role": ("target_role", "target_roles"),
    "education": ("education", "academic_background", "degree", "degrees", "qualifications"),
    "skills": ("skills", "skill", "technical_skills"),
    "experience": (
        "experience",
        "work_experience",
        "professional_experience",
        "other_experience",
        "additional_experience",
        "employment",
        "employment_history",
        "work_history",
        "internship",
        "internships",
    ),
    # Academic research is project evidence, not proof of professional tenure.
    "project": ("project", "projects", "research", "research_experience"),
    "achievement": ("achievement", "achievements", "education_recognition"),
    "activity": ("activity", "activities"),
    "certification": ("certification", "certifications"),
}
_PREFIXES = sorted(
    ((alias, category) for category, aliases in _ALIASES.items() for alias in aliases),
    key=lambda item: (-len(item[0]), item[0]),
)
_NON_EVIDENCE_PARTS = frozenset(
    {
        "goal",
        "goals",
        "interest",
        "interests",
        "aspiration",
        "aspirations",
        "desired",
        "future",
        "planned",
        "planning",
        "plans",
        "learn",
        "wanted",
        "preferences",
        "requirements",
        "requirement",
        "contact",
        "email",
        "phone",
        "address",
        "account",
        "id",
        "url",
        "link",
        "links",
        "github",
        "linkedin",
        "password",
        "secret",
        "token",
        "credential",
        "credentials",
    }
)

PROFILE_FIELD_GUIDANCE = """Use stable field keys: name, education, skills, target_role.
Use email, phone, github, linkedin, portfolio, or website for supplied contact details.
For multiple roles or projects use separate keys such as experience_startup,
experience_internship, project_retrieval, and project_classifier. Keep an existing key when
correcting that same fact; never reuse one key for unrelated entries or combine all work
into one category just to pass confirmation. Research may use project_research.
Put aspirations under separate goal or interest fields, never under completed work.
The server's missing_fields list reports category completeness, not eligibility or approval.
An empty list means request explicit user review/confirmation, not further completeness questions.
"""


def profile_field_category(field: str) -> str | None:
    """Recognise bounded aliases and namespaced keys, never arbitrary substrings."""
    label = re.sub(r"[^a-z0-9]+", "_", field.casefold()).strip("_")
    if _NON_EVIDENCE_PARTS.intersection(label.split("_")) or "currently_learning" in label:
        return None
    for prefix, category in _PREFIXES:
        if label == prefix or (category != "name" and label.startswith(f"{prefix}_")):
            return category
    return None
