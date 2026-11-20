"""Separate same-response model metadata from user-visible streaming text."""
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

MARKER = '[CAPABILITIES]'
CapabilityId = Literal['book_recommendation', 'literary_discussion', 'reading_feelings',
                       'reading_experience', 'emotion_understanding', 'empathetic_response',
                       'user_memory', 'relationship_care']


class Capability(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: CapabilityId
    evidence: str = Field(min_length=1, max_length=240)


class LatentState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    part: Literal["needs", "goals", "self_view"]
    state: str = Field(min_length=1, max_length=180)
    quote: str = Field(min_length=1, max_length=300)


class CapabilityResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    capabilities: list[Capability] = Field(max_length=8)
    latent_psychology: LatentState | None = None


class CapabilityStream:
    def __init__(self):
        self.pending = ''
        self.metadata = None

    def feed(self, text):
        if self.metadata is not None:
            self.metadata += text
            return ''
        self.pending += text
        if MARKER in self.pending:
            visible, self.metadata = self.pending.split(MARKER, 1)
            self.pending = ''
            return visible.rstrip("\r\n")
        # Hold only a possible marker prefix, never the entire chat response.
        keep = next((n for n in range(min(len(self.pending), len(MARKER)), 0, -1)
                     if self.pending.endswith(MARKER[:n])), 0)
        visible = self.pending[:-keep] if keep else self.pending
        self.pending = self.pending[-keep:] if keep else ''
        trimmed = visible.rstrip('\r\n')
        self.pending = visible[len(trimmed):] + self.pending
        return trimmed

    def finish(self):
        tail, self.pending = self.pending, ''
        return tail

    def records(self):
        try:
            result = CapabilityResult.model_validate(json.loads(self.metadata or ''))
        except (ValueError, TypeError, ValidationError):
            return []
        unique = {}
        for item in result.capabilities:
            if item.evidence.strip():
                unique[item.id] = {**item.model_dump(), 'basis': 'model_self_report'}
        return list(unique.values())

    def psychology(self, current_content):
        try:
            result = CapabilityResult.model_validate(json.loads(self.metadata or ''))
        except (ValueError, TypeError, ValidationError):
            return None
        latent = result.latent_psychology
        if not latent or not latent.state.strip() or not latent.quote.strip():
            return None
        if latent.quote not in current_content:
            return None
        return latent.model_dump()
