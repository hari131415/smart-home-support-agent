"""Input and output guardrails.

Input side runs before anything touches the model or the logs:
  - PII is redacted so it never reaches Gemini, BigQuery traces, or tickets
  - life-safety situations get a fixed response and an urgent handoff;
    we don't want a model improvising advice when someone smells gas
  - obvious prompt-injection attempts are flagged

Output side runs on the model's final answer:
  - hand off if the model says it isn't confident
  - hand off if it cites nothing, or cites chunks it never retrieved
  - block answers that tell users to do something we never want to recommend
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

# --- PII -------------------------------------------------------------------

_PII_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("CARD", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("PHONE", re.compile(r"(?<!\w)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]?\d{4}\b")),
    (
        "ADDRESS",
        re.compile(
            r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s){1,3}"
            r"(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Dr|Drive|Ln|Lane|Ct|Court|Way)\b\.?"
        ),
    ),
    # Wi-Fi passwords are the one thing users paste most often.
    ("WIFI_PASSWORD", re.compile(r"(?i)(?:wi-?fi\s+)?password\s*(?:is|:|=)\s*\S+")),
]


def redact_pii(text: str) -> tuple[str, list[str]]:
    found = []
    for label, pattern in _PII_PATTERNS:
        if pattern.search(text):
            found.append(label)
            text = pattern.sub(f"[{label}]", text)
    return text, found


# --- Input triage ----------------------------------------------------------


class Triage(StrEnum):
    OK = "ok"
    EMERGENCY = "emergency"
    INJECTION = "injection"


_EMERGENCY = re.compile(
    r"(?i)\b("
    r"smell(?:s|ing)? (?:of )?gas|gas leak|"
    r"(?:there'?s|is) (?:a )?fire|on fire|(?:see|seeing) (?:flames|fire)|"
    r"sparks?|sparking|smok(?:e|ing) (?:is )?coming (?:out|from)|"
    r"burning smell|smells? (?:like )?burning|"
    r"(?:co|carbon monoxide|smoke) alarm (?:is )?(?:going off|sounding|beeping (?:loudly|nonstop))|"
    r"alarm (?:is )?(?:going off|sounding) (?:for|and says) (?:smoke|carbon monoxide|co)|"
    r"(?:feel(?:ing)?|getting) (?:dizzy|nauseous|lightheaded)|"
    r"electric(?:al)? shock|got shocked"
    r")\b"
)

_INJECTION = re.compile(
    r"(?i)(ignore (?:all |any )?(?:previous|prior|above) (?:instructions|rules)|"
    r"you are now|system prompt|developer mode|disregard your)"
)

EMERGENCY_RESPONSE = (
    "This sounds like it could be a safety emergency. Please leave the home now and call "
    "emergency services (911 in the US) from outside. Don't try to troubleshoot the device. "
    "If it's a carbon monoxide or gas concern, get to fresh air right away. I'm also "
    "flagging this for our support team so someone follows up with you."
)


@dataclass
class InputVerdict:
    triage: Triage
    redacted_text: str
    pii_found: list[str] = field(default_factory=list)


def check_input(text: str) -> InputVerdict:
    redacted, pii = redact_pii(text)
    if _EMERGENCY.search(text):
        triage = Triage.EMERGENCY
    elif _INJECTION.search(text):
        triage = Triage.INJECTION
    else:
        triage = Triage.OK
    return InputVerdict(triage=triage, redacted_text=redacted, pii_found=pii)


# --- Output checks ---------------------------------------------------------

# Things support must never tell a customer to do, whatever the manual says.
_BLOCKED_ADVICE = re.compile(
    r"(?i)("
    r"remove (?:the )?batter(?:y|ies) (?:from|out of) (?:the|your) (?:smoke|co)|"
    r"disable (?:the |your )?(?:smoke|co|carbon monoxide) (?:alarm|detector)|"
    r"open (?:the |your )?(?:electrical|breaker) panel|"
    r"bypass (?:the )?(?:overload|safety)|"
    r"(?:open|disassemble) (?:the )?(?:device|unit) (?:housing|case)"
    r")"
)

DEVICE_CITATION = re.compile(r"^device:[\w-]+$")


@dataclass
class OutputVerdict:
    ok: bool
    reason: str | None = None


def check_output(
    answer: str,
    citations: list[str],
    confidence: float,
    retrieved_ids: set[str],
    min_confidence: float,
) -> OutputVerdict:
    if confidence < min_confidence:
        return OutputVerdict(False, f"low_confidence:{confidence:.2f}")
    if not answer.strip():
        return OutputVerdict(False, "empty_answer")
    if not citations:
        return OutputVerdict(False, "no_citations")

    unknown = [c for c in citations if c not in retrieved_ids and not DEVICE_CITATION.match(c)]
    if unknown:
        return OutputVerdict(False, f"ungrounded_citations:{','.join(unknown)}")

    if _BLOCKED_ADVICE.search(answer):
        return OutputVerdict(False, "blocked_advice")
    return OutputVerdict(True)
