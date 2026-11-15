"""Structured crisis helpline data (Prompt D §2).

No logic beyond sorting: the resource list is data. If a regional pack is added
later it must extend ``CRISIS_RESOURCES`` - helplines are never hard-coded
anywhere else in the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CrisisResource:
    """One helpline entry.

    ``phone`` holds digits usable in a ``tel:`` URI (short codes such as ``988``
    are valid). ``sms_text`` is the body for an ``sms:`` URI when the service
    accepts a keyword. ``display_order`` sorts the list; lower shows first.
    """

    id: str
    name: str
    action_text: str
    phone: str | None
    sms_text: str | None
    url: str | None
    region: str
    display_order: int


#: Canonical resource list, verbatim from Prompt D §2.1.
CRISIS_RESOURCES: tuple[CrisisResource, ...] = (
    CrisisResource(
        id="988_lifeline",
        name="988 Suicide & Crisis Lifeline",
        action_text="Call or text 988 (US)",
        phone="988",
        sms_text=None,
        url=None,
        region="US",
        display_order=1,
    ),
    CrisisResource(
        id="crisis_text_line",
        name="Crisis Text Line",
        action_text="Text HOME to 741741 (US)",
        phone="741741",
        sms_text="HOME",
        url=None,
        region="US",
        display_order=2,
    ),
    CrisisResource(
        id="find_a_helpline",
        name="Find A Helpline",
        action_text="findahelpline.com for help outside the US",
        phone=None,
        sms_text=None,
        url="https://findahelpline.com",
        region="International",
        display_order=3,
    ),
    CrisisResource(
        id="emergency_services",
        name="Emergency services",
        action_text="Call 911 (US) / 112 (EU) if you are in immediate danger",
        phone="911",
        sms_text=None,
        url=None,
        region="US/EU",
        display_order=4,
    ),
)

#: The helpline named on the crisis dialog's quick-dial button.
PRIMARY_LIFELINE_ID = "988_lifeline"
#: The helpline whose "find help" button opens a web page.
WEB_HELPLINE_ID = "find_a_helpline"


def resources_in_display_order() -> tuple[CrisisResource, ...]:
    """Return every crisis resource sorted by ``display_order``, ascending."""
    return tuple(sorted(CRISIS_RESOURCES, key=lambda resource: resource.display_order))


def resource_by_id(resource_id: str) -> CrisisResource:
    """Return the resource with ``resource_id``. Raises ``KeyError`` if absent."""
    for resource in CRISIS_RESOURCES:
        if resource.id == resource_id:
            return resource
    raise KeyError(f"Unknown crisis resource id {resource_id!r}")


def tel_uri(resource: CrisisResource) -> str | None:
    """Return a ``tel:`` URI for a resource, or ``None`` when it has no phone."""
    return f"tel:{resource.phone}" if resource.phone else None


def sms_uri(resource: CrisisResource) -> str | None:
    """Return an ``sms:`` URI for a resource, or ``None`` when it has no phone."""
    if not resource.phone:
        return None
    if resource.sms_text:
        return f"sms:{resource.phone}?body={resource.sms_text}"
    return f"sms:{resource.phone}"


def resource_line(resource: CrisisResource) -> str:
    """Return the display line for a resource: ``"{name} — {action_text}"``."""
    return f"{resource.name} — {resource.action_text}"
