"""
Email feature data models.

Models for email threads, voice profiles, and draft generation.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class EmailMessage(BaseModel):
    """Single email message in a thread."""
    id: str = Field(..., description="Gmail message ID")
    thread_id: str = Field(..., description="Gmail thread ID")
    from_email: str = Field(..., description="Sender email address")
    to_email: str = Field(..., description="Recipient email address")
    subject: str = Field(..., description="Email subject line")
    date: datetime = Field(..., description="Email sent date")
    body: str = Field(..., description="Email body text")
    is_from_user: bool = Field(..., description="True if sent by current user")


class EmailThread(BaseModel):
    """Complete email thread with all messages."""
    thread_id: str = Field(..., description="Gmail thread ID")
    messages: list[EmailMessage] = Field(..., description="Messages in chronological order")
    commitment_id: Optional[str] = Field(None, description="Associated commitment ID")


class VoiceProfile(BaseModel):
    """User's email writing style profile."""
    user_email: str = Field(..., description="User email address")
    style: str = Field(..., description="Writing style: professional, casual, formal")
    common_phrases: list[str] = Field(default_factory=list, description="Frequently used phrases")
    signature: str = Field("", description="Email signature pattern")
    avg_sentence_length: float = Field(12.0, description="Average sentence length in words")
    formality: float = Field(0.5, ge=0.0, le=1.0, description="Formality score 0.0-1.0")
    samples_analyzed: int = Field(0, description="Number of emails analyzed")
    last_updated: datetime = Field(default_factory=datetime.utcnow, description="Profile update timestamp")


class EmailDraft(BaseModel):
    """Generated email draft."""
    draft_id: str = Field(..., description="Unique draft ID")
    commitment_id: str = Field(..., description="Source commitment ID")
    to: str = Field(..., description="Recipient email")
    subject: str = Field(..., description="Email subject")
    body: str = Field(..., description="Email body")
    voice_confidence: float = Field(0.0, ge=0.0, le=1.0, description="Voice matching confidence")
    suggested_edits: list[str] = Field(default_factory=list, description="Suggested improvements")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Draft creation time")


class DraftRequest(BaseModel):
    """Request to generate a draft."""
    tone: str = Field("professional", description="Email tone: professional, casual, urgent")
    length: str = Field("medium", description="Email length: short, medium, long")
    context: Optional[str] = Field(None, description="Additional context for draft")


class SendRequest(BaseModel):
    """Request to send a draft."""
    edited_body: Optional[str] = Field(None, description="Edited email body (if user modified)")
