from pydantic import BaseModel, Field


class CopilotAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    # Omit to start a new Wingman thread; pass it back to continue one.
    thread_id: str | None = Field(None, max_length=200)
    # Whatever page the user asked from, forwarded to Wingman as localContext.
    local_context: str | None = Field(None, max_length=2000)


class CopilotApproveRequest(BaseModel):
    thread_id: str = Field(..., min_length=1, max_length=200)
    tool_names: list[str] = Field(default_factory=list)
    approve: bool = True
    remember: bool = False


class CopilotFact(BaseModel):
    label: str
    value: str
    raw: bool = False


class CopilotCitation(BaseModel):
    tone: str
    headline: str
    facts: list[CopilotFact] = []
    # Always populated: how this answer was obtained, so it can be verified.
    source: str


class CopilotAnswer(BaseModel):
    text: str
    citation: CopilotCitation | None = None
    thread_id: str | None = None
    # Set when Wingman is waiting for permission to call LEON data tools.
    approval_required: bool = False
    pending_tool_names: list[str] = []
