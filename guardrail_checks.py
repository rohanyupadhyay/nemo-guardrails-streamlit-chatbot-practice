import re
from dataclasses import dataclass
from typing import Iterable


CHEESE_TERMS = {
    "affinage",
    "asiago",
    "blue cheese",
    "brie",
    "burrata",
    "camembert",
    "casein",
    "cheddar",
    "cheese",
    "cheesemaking",
    "chevre",
    "colby",
    "curd",
    "dairy",
    "emmental",
    "feta",
    "fondue",
    "gouda",
    "gruyere",
    "halloumi",
    "lactose",
    "manchego",
    "mozzarella",
    "paneer",
    "parmesan",
    "pecorino",
    "provolone",
    "rennet",
    "ricotta",
    "roquefort",
    "stilton",
    "swiss",
    "whey",
}

PROMPT_INJECTION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bignore (all |the |your )?(previous|prior|above|system|developer) instructions\b",
        r"\b(disregard|override|bypass) (all |the |your )?(instructions|guardrails|rules|policy)\b",
        r"\breveal (your )?(system|developer|hidden) (prompt|message|instructions)\b",
        r"\bshow (your )?(system|developer|hidden) (prompt|message|instructions)\b",
        r"\binclude (your )?(system|developer|hidden) (prompt|message|instructions)\b",
        r"\b(system|developer|hidden) (prompt|message|instructions)\b",
        r"\bpretend (that )?you are\b",
        r"\bact as\b",
        r"\bjailbreak\b",
        r"\bDAN\b",
        r"\bclassify this (as )?(allowed|safe|cheese-related)\b",
    ]
]

PII_OR_SECRET_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\bsk-[A-Za-z0-9_-]{20,}\b",
        r"\b[A-Za-z0-9_-]{32,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b",
        r"\b(password|passcode|api[_ -]?key|secret|token)\s*[:=]\s*\S+",
        r"\b(password|passcode|api[_ -]?key|secret|token)\s+is\s+\S+",
        r"\b\d{3}[-.\s]?\d{2}[-.\s]?\d{4}\b",
        r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",
        r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b",
    ]
]

MEDICAL_BOUNDARY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\b(cure|treat|diagnose|prescribe|reverse) .{0,80}\b",
        r"\b(allergic|allergy|anaphylaxis|kidney disease|lactose intoleran(?:t|ce)|pregnan(?:t|cy)|diabetes|cholesterol|blood pressure)\b",
        r"\bhow much .{0,60}(can|should) i eat\b",
        r"\bmake me .{0,80}(diet|meal plan)\b",
    ]
]

FOOD_SAFETY_TERMS = [
    "botulism",
    "expired",
    "food poisoning",
    "listeria",
    "mold",
    "mould",
    "pasteurized",
    "pasteurised",
    "pregnancy",
    "pregnant",
    "raw milk",
    "salmonella",
    "sick",
    "spoiled",
    "unpasteurized",
    "unpasteurised",
]

OFF_TOPIC_OUTPUT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"\b(system|developer) prompt\b",
        r"\bhidden instructions\b",
        r"\bi can help with (coding|cybersecurity|finance|legal)\b",
        r"\bbypass (your |the )?guardrails\b",
        r"\bhere'?s how to bypass\b",
    ]
]


@dataclass(frozen=True)
class GuardrailEvent:
    name: str
    action: str
    reason: str
    message: str = ""


@dataclass(frozen=True)
class GuardrailSettings:
    max_prompt_chars: int = 1200
    topic_guardrail: bool = True
    prompt_injection_guardrail: bool = True
    pii_guardrail: bool = True
    food_safety_guardrail: bool = True
    medical_boundary_guardrail: bool = True
    output_guardrail: bool = True
    strictness: str = "Strict"


def contains_cheese_topic(text: str, strictness: str = "Strict") -> bool:
    normalized = text.lower()
    if any(term in normalized for term in CHEESE_TERMS):
        return True

    if strictness == "Loose":
        return any(
            term in normalized
            for term in ["milk", "cream", "butter", "yogurt", "fermentation", "recipe"]
        )

    return False


def evaluate_input(prompt: str, settings: GuardrailSettings) -> list[GuardrailEvent]:
    events: list[GuardrailEvent] = []

    if len(prompt) > settings.max_prompt_chars:
        events.append(
            GuardrailEvent(
                name="length",
                action="block",
                reason=f"Prompt is {len(prompt)} characters; limit is {settings.max_prompt_chars}.",
                message="Please shorten your message and ask one cheese-related question.",
            )
        )

    if settings.prompt_injection_guardrail and _matches_any(prompt, PROMPT_INJECTION_PATTERNS):
        events.append(
            GuardrailEvent(
                name="prompt injection",
                action="block",
                reason="Prompt appears to ask for instruction override, policy leakage, or role change.",
                message="I can only help with cheese-related questions.",
            )
        )

    if settings.pii_guardrail and _matches_any(prompt, PII_OR_SECRET_PATTERNS):
        events.append(
            GuardrailEvent(
                name="PII/secrets",
                action="block",
                reason="Prompt appears to include personal data or a secret.",
                message="Please remove personal data, passwords, API keys, or secrets before asking a cheese question.",
            )
        )

    if settings.topic_guardrail and not contains_cheese_topic(prompt, settings.strictness):
        events.append(
            GuardrailEvent(
                name="deterministic topic",
                action="warn",
                reason="No obvious cheese or dairy term found. NeMo will make the final topic decision.",
            )
        )

    if settings.food_safety_guardrail and any(term in prompt.lower() for term in FOOD_SAFETY_TERMS):
        events.append(
            GuardrailEvent(
                name="food safety",
                action="warn",
                reason="Prompt includes food-safety terms; answer should be conservative and avoid risky certainty.",
            )
        )

    if settings.medical_boundary_guardrail and _matches_any(prompt, MEDICAL_BOUNDARY_PATTERNS):
        events.append(
            GuardrailEvent(
                name="medical boundary",
                action="warn",
                reason="Prompt may involve personal health, allergy, pregnancy, or nutrition advice.",
            )
        )

    return events


def evaluate_output(response: str, settings: GuardrailSettings) -> list[GuardrailEvent]:
    if not settings.output_guardrail:
        return []

    events: list[GuardrailEvent] = []
    if _matches_any(response, OFF_TOPIC_OUTPUT_PATTERNS):
        events.append(
            GuardrailEvent(
                name="output",
                action="block",
                reason="Response appears to expose hidden instructions or leave the cheese domain.",
                message="I can only help with cheese-related questions.",
            )
        )

    if settings.food_safety_guardrail and any(term in response.lower() for term in FOOD_SAFETY_TERMS):
        if not _has_safety_language(response):
            events.append(
                GuardrailEvent(
                    name="food safety output",
                    action="warn",
                    reason="Response mentions food-safety terms without obvious conservative safety language.",
                )
            )

    return events


def first_block(events: Iterable[GuardrailEvent]) -> GuardrailEvent | None:
    return next((event for event in events if event.action == "block"), None)


def safe_answer_context(events: Iterable[GuardrailEvent]) -> str:
    guidance: list[str] = []
    names = {event.name for event in events}

    if "food safety" in names:
        guidance.append(
            "For food-safety topics, be conservative: mention uncertainty, avoid guarantees, "
            "and suggest discarding questionable cheese or consulting official guidance when appropriate."
        )

    if "medical boundary" in names:
        guidance.append(
            "For health, allergy, pregnancy, or nutrition topics, provide general information only "
            "and do not diagnose, prescribe, or create a personalized medical plan."
        )

    return "\n".join(f"- {item}" for item in guidance)


def _matches_any(text: str, patterns: Iterable[re.Pattern[str]]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def _has_safety_language(text: str) -> bool:
    normalized = text.lower()
    return any(
        phrase in normalized
        for phrase in [
            "discard",
            "do not eat",
            "food-safety",
            "health professional",
            "official guidance",
            "when in doubt",
        ]
    )
