"""Subgroup meeting configurations."""

GROUPS = {
    "general": {
        "display_name": "General Group Meeting",
        "short_name": "General",
        "emoji": "🔬",
        "num_presenters": 1,
        "meeting_day": "wednesday",
        "presentation_duration": 50,
        "email_subject": "[Confirmation Required] General Group Meeting",
        "meeting_title": "General Group Meeting",
    },
    "quantum": {
        "display_name": "Quantum Subgroup",
        "short_name": "QC@ML",
        "emoji": "⚛️",
        "num_presenters": 1,
        "meeting_day": "tuesday",
        "presentation_duration": 50,
        "email_subject": "[Confirmation Required] Quantum Subgroup",
        "meeting_title": "Quantum Subgroup Meeting",
    },
    "ml": {
        "display_name": "Machine Learning Subgroup",
        "short_name": "ML@ML",
        "emoji": "🧠",
        "num_presenters": 2,
        "meeting_day": "wednesday",
        "presentation_duration": 20,
        "email_subject": "[Confirmation Required] ML Subgroup",
        "meeting_title": "ML Subgroup Meeting",
    },
    "drugdiscovery": {
        "display_name": "Drug Discovery Subgroup",
        "short_name": "Drug Discovery",
        "emoji": "💊",
        "num_presenters": 1,
        "meeting_day": "wednesday",
        "presentation_duration": 50,
        "email_subject": "[Confirmation Required] Drug Discovery Subgroup",
        "meeting_title": "Drug Discovery Subgroup Meeting",
    },
    "handson": {
        "display_name": "Hands-on Subgroup",
        "short_name": "Hands-on",
        "emoji": "🛠️",
        "num_presenters": 1,
        "meeting_day": "wednesday",
        "presentation_duration": 50,
        "email_subject": "[Confirmation Required] Hands-on Subgroup",
        "meeting_title": "Hands-on Subgroup Meeting",
    },
}

DAY_MAP = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def get_presenter_cols(group):
    """Return the presenter column names for a group."""
    if group["num_presenters"] == 1:
        return ["Presenter"]
    return [f"Presenter {i+1}" for i in range(group["num_presenters"])]
