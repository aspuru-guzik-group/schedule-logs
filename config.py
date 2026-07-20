"""Subgroup meeting configurations."""

from runtime_config import get_group_runtime_config

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
        "self_service_setup": True,
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
        "self_service_setup": True,
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
        "self_service_setup": True,
    },
    "elagente": {
        "display_name": "El Agente Subgroup",
        "short_name": "El Agente",
        "emoji": "🎩",
        "num_presenters": 2,
        "meeting_day": "wednesday",
        "presentation_duration": 20,
        "email_subject": "[Confirmation Required] El Agente Subgroup",
        "meeting_title": "El Agente Subgroup Meeting",
        "default_slides_template_url": (
            "https://docs.google.com/presentation/d/"
            "1Gjpm344FZtayS9QCr5iPQI_pI1XZOfQ5bU4uoZ8o7d4/edit"
        ),
        "self_service_setup": True,
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
        "self_service_setup": True,
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
        "self_service_setup": True,
    },
    "robotics": {
        "display_name": "Robotics Subgroup",
        "short_name": "Robotics",
        "emoji": "⚙️",
        "num_presenters": 1,
        "meeting_day": "wednesday",
        "presentation_duration": 50,
        "email_subject": "[Confirmation Required] Robotics Subgroup",
        "meeting_title": "Robotics Subgroup Meeting",
        "self_service_setup": True,
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


def get_group_config(group_slug):
    """Return static group metadata with supported runtime overrides."""
    group = dict(GROUPS[group_slug])
    runtime = get_group_runtime_config(group_slug)

    num_presenters = runtime.get("num_presenters")
    if num_presenters in (1, 2):
        group["num_presenters"] = num_presenters

    meeting_day = runtime.get("meeting_day")
    if meeting_day in DAY_MAP:
        group["meeting_day"] = meeting_day

    presentation_duration = runtime.get("presentation_duration")
    if isinstance(presentation_duration, int) and presentation_duration > 0:
        group["presentation_duration"] = presentation_duration

    return group


def get_presenter_cols(group):
    """Return the presenter column names for a group."""
    if group["num_presenters"] == 1:
        return ["Presenter"]
    return [f"Presenter {i+1}" for i in range(group["num_presenters"])]
