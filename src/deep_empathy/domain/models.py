"""Typed contracts for cloud results and HTTP requests."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Layer = Literal["behavior", "identity", "cognition", "regulation", "core"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Citation(Contract):
    message_id: str
    quote: str = Field(min_length=1, max_length=1000)


class ClaimProposal(Contract):
    layer: Layer
    statement: str = Field(min_length=1, max_length=300)
    citations: list[Citation] = Field(min_length=1, max_length=8)
    explicit: bool = False
    replaces_id: str | None = None


class Psychology(Contract):
    focus: Literal["needs", "goals", "self_view"] | None = None
    needs: list[Literal["autonomy", "competence", "relatedness"]] = Field(default_factory=list)
    goals: list[Literal["mastery", "performance", "avoidance"]] = Field(default_factory=list)
    actual_self: str = Field(default="", max_length=300)
    ideal_self: str = Field(default="", max_length=300)
    ought_self: str = Field(default="", max_length=300)
    interpretation: str = Field(default="尚需了解", max_length=500)
    alternatives: list[str] = Field(default_factory=list, max_length=3)
    uncertainty: Literal["low", "medium", "high"] = "high"
    citations: list[Citation] = Field(default_factory=list, max_length=6)


class Analysis(Contract):
    emotion: str = Field(max_length=100)
    event: str = Field(max_length=500)
    support_preference: Literal["listen", "advice", "clarify", "unknown"] = "unknown"
    risk: Literal["ordinary", "urgent"] = "ordinary"
    claims: list[ClaimProposal] = Field(default_factory=list, max_length=6)
    psychology: Psychology


class SupportPlan(Contract):
    goal: str = Field(max_length=500)
    validation: str = Field(max_length=500)
    user_perspective: str = Field(max_length=500)
    agent_constraints: list[str] = Field(max_length=8)
    style: str = Field(max_length=200)
    ask_clarification: bool
    offer_advice: bool
    avoid_assertions: list[str] = Field(max_length=8)
    uncertainty_method: Literal["heuristic"] = "heuristic"


class Reply(Contract):
    text: str = Field(min_length=1, max_length=4000)


class Review(Contract):
    passed: bool
    issues: list[str] = Field(default_factory=list, max_length=8)


class Preparation(Contract):
    analysis: Analysis
    plan: SupportPlan


class Summary(Contract):
    text: str = Field(max_length=2000)
    source_message_ids: list[str] = Field(max_length=80)


class SceneEvent(Contract):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    action: Literal[
        "enter",
        "leave",
        "walk",
        "arrive",
        "sit",
        "stand",
        "take_book",
        "read_book",
        "close_book",
        "return_book",
        "make_coffee",
        "coffee_ready",
        "take_cup",
        "deliver_cup",
        "deliver_book",
        "put_book",
        "drink",
        "put_cup",
    ]
    actor: Literal["boss", "user"]
    description: str = Field(max_length=200)


class SceneBook(Contract):
    location: Literal["shelf", "table", "table-front-left", "table-front-right", "table-window", "held"] = "shelf"
    id: str = Field(max_length=100)
    title: str = Field(max_length=100)
    holder: Literal["boss", "user"] | None = None


class BookstoreContext(Contract):
    user_activity: Literal["none", "drinking", "reading"] = "none"
    pending_user_actions: list[Literal["drink_coffee", "read_book"]] = Field(default_factory=list, max_length=10)
    book_catalog: list[SceneBook] = Field(default_factory=list, max_length=20)
    pending_actions: list[Literal["bring_book", "serve_coffee"]] = Field(default_factory=list, max_length=20)
    owner_activity: str = Field(default="", max_length=200)
    interruption: Literal["available", "waiting_safe_point", "interacting"] = "available"
    scene_id: Literal["bookstore"] = "bookstore"
    user_present: bool
    boss_pose: Literal["standing", "walking", "sitting"]
    user_pose: Literal["absent", "standing", "walking", "sitting"]
    user_item: Literal["none", "book", "cup"] = "none"
    boss_item: Literal["none", "book", "cup"] = "none"
    coffee_phase: Literal["idle", "brewing", "ready"] = "idle"
    cup_full: bool = False
    reading_title: str = Field(default="", max_length=100)
    recent_events: list[SceneEvent] = Field(default_factory=list, max_length=8)


class SceneEventsRequest(Contract):
    events: list[SceneEvent] = Field(max_length=30)


class ChatRequest(Contract):
    weather_snapshot_id: str | None = Field(default=None, max_length=64)
    weather_preview: Literal["clear", "rain", "snow", "overcast"] | None = None
    content: str = Field(min_length=1, max_length=4000)
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    interaction_mode: Literal["online", "in_person"] = "online"
    processing_mode: Literal["auto", "fast", "deep"] = "auto"
    scene: BookstoreContext | None = None


class SessionRequest(Contract):
    mode: Literal["cloud", "demo"] = "cloud"


class ClaimEdit(Contract):
    action: Literal["confirm", "correct", "retract"]
    statement: str = Field(default="", max_length=300)


class MemorySearchRequest(Contract):
    query: str = Field(min_length=1, max_length=2000)


class MemorySettings(Contract):
    enabled: bool


class FeedbackRequest(Contract):
    rating: Literal["helpful", "missed", "neutral"]
    comment: str = Field(default="", max_length=1000)


class Evaluation(Contract):
    resonation: int = Field(ge=1, le=5)
    expression: int = Field(ge=1, le=5)
    reception: int = Field(ge=1, le=5)
    evidence_supported: bool
    notes: str = Field(max_length=1000)
