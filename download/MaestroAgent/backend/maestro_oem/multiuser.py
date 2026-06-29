"""
Multi-user OEM — shared organizational state with real-time synchronization.

Users (CEO, VP, Manager, Developer) share the same OEM.
Changes propagate via WebSocket with optimistic updates and conflict resolution.

Architecture:
  - SharedOEM: single OEM instance per organization, protected by a lock
  - UserSession: per-user session with role, permissions, and optimistic state
  - SyncManager: orchestrates WebSocket broadcasting and conflict resolution
  - OptimisticUpdate: client-side prediction with server reconciliation

Conflict resolution:
  - Last-Write-Wins for simple fields (e.g., decision status)
  - Merge for additive fields (e.g., evidence, stakeholder positions)
  - Server is authoritative — optimistic updates are reconciled on pushback

What synchronizes:
  - Decisions (status changes, stakeholder positions)
  - Receipts (new evidence appears for all users)
  - Laws (confidence changes, status changes)
  - Recommendations (appear/disappear as OEM evolves)
  - Contradiction events (CEO feedback visible to all)

What does NOT synchronize (per-user):
  - View state (which surface, scroll position)
  - Personal filters
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class UserRole(str, Enum):
    CEO = "ceo"
    VP = "vp"
    MANAGER = "manager"
    DEVELOPER = "developer"


class SyncEventType(str, Enum):
    DECISION_UPDATED = "decision.updated"
    DECISION_APPROVED = "decision.approved"
    DECISION_REJECTED = "decision.rejected"
    LAW_UPDATED = "law.updated"
    LAW_STRESSED = "law.stressed"
    LAW_INVALIDATED = "law.invalidated"
    EVIDENCE_ADDED = "evidence.added"
    CONTRADICTION_APPLIED = "contradiction.applied"
    RECOMMENDATION_CHANGED = "recommendation.changed"
    OEM_STATE_CHANGED = "oem.state_changed"
    USER_JOINED = "user.joined"
    USER_LEFT = "user.left"
    OPTIMISTIC_REJECTED = "optimistic.rejected"
    OPTIMISTIC_CONFIRMED = "optimistic.confirmed"


class SyncEvent(BaseModel):
    """An event broadcast to all connected users."""
    event_id: UUID = Field(default_factory=uuid4)
    event_type: SyncEventType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actor: str  # User who triggered the event
    target_type: str  # "decision", "law", "evidence", etc.
    target_id: str
    data: dict[str, Any] = Field(default_factory=dict)
    # For conflict resolution
    version: int = 0  # Monotonic version number
    parent_version: int = 0  # Version this update was based on


class OptimisticUpdate(BaseModel):
    """
    A client-side optimistic update waiting for server confirmation.

    Flow:
    1. Client applies update locally (instant UI feedback)
    2. Client sends update to server
    3. Server processes and either:
       a. Confirms → client marks update as confirmed
       b. Rejects (conflict) → client rolls back and applies server state
    """
    update_id: UUID = Field(default_factory=uuid4)
    user_id: str
    target_type: str
    target_id: str
    field: str
    old_value: Any = None
    new_value: Any = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    confirmed: bool = False
    rejected: bool = False
    rejection_reason: str = ""


class UserSession(BaseModel):
    """
    A connected user session.

    Each user has:
    - A role (determines permissions)
    - An optimistic update queue (pending changes)
    - A last-seen timestamp
    """
    session_id: UUID = Field(default_factory=uuid4)
    user_id: str  # email or internal ID
    user_name: str
    role: UserRole
    connected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    optimistic_updates: list[OptimisticUpdate] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}

    def can_approve_decisions(self) -> bool:
        return self.role in (UserRole.CEO, UserRole.VP)

    def can_reject_decisions(self) -> bool:
        return self.role in (UserRole.CEO, UserRole.VP)

    def can_provide_feedback(self) -> bool:
        return self.role in (UserRole.CEO, UserRole.VP, UserRole.MANAGER)

    def can_view_all(self) -> bool:
        return self.role == UserRole.CEO

    def add_optimistic(self, update: OptimisticUpdate) -> None:
        self.optimistic_updates.append(update)

    def confirm_optimistic(self, update_id: UUID) -> OptimisticUpdate | None:
        for u in self.optimistic_updates:
            if u.update_id == update_id:
                u.confirmed = True
                return u
        return None

    def reject_optimistic(self, update_id: UUID, reason: str) -> OptimisticUpdate | None:
        for u in self.optimistic_updates:
            if u.update_id == update_id:
                u.rejected = True
                u.rejection_reason = reason
                return u
        return None

    def cleanup_confirmed(self) -> None:
        """Remove confirmed/rejected updates older than 60 seconds."""
        now = datetime.now(timezone.utc)
        self.optimistic_updates = [
            u for u in self.optimistic_updates
            if not (u.confirmed or u.rejected) or (now - u.timestamp).total_seconds() < 60
        ]


class SharedDecision(BaseModel):
    """
    A shared decision that all users see.

    Synchronized fields:
    - status (approved, rejected, deferred)
    - stakeholder positions
    - confidence
    - linked laws

    Conflict resolution:
    - Status: Last-Write-Wins (CEO/VP can change)
    - Stakeholder positions: Merge (each stakeholder sets their own)
    """
    decision_id: str
    title: str
    status: str = "proposed"  # proposed, approved, rejected, deferred
    confidence: float = 0.0
    stakeholder_positions: dict[str, str] = Field(default_factory=dict)  # user_id → position
    linked_laws: list[str] = Field(default_factory=list)
    version: int = 0  # Monotonic version for conflict detection
    last_updated_by: str = ""
    last_updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SharedOEM:
    """
    Shared Organizational Execution Model.

    Single instance per organization. All users read from and write to this.
    Protected by an async lock for thread-safe access.

    Usage:
        shared = SharedOEM(persistent_oem)
        await shared.approve_decision("rec-123", user_session)
        → broadcasts SyncEvent to all connected users
    """

    def __init__(self, persistent_oem: Any = None) -> None:
        self.persistent = persistent_oem
        self._lock = asyncio.Lock()
        self._version = 0
        self._sessions: dict[UUID, UserSession] = {}
        self._decisions: dict[str, SharedDecision] = {}
        self._event_handlers: list[Callable] = []
        self._pending_events: list[SyncEvent] = []

    @property
    def model(self):
        """Get the underlying ExecutionModel."""
        if self.persistent:
            return self.persistent.get_model()
        return None

    async def connect_user(self, session: UserSession) -> SyncEvent:
        """Connect a user to the shared OEM."""
        async with self._lock:
            self._sessions[session.session_id] = session

        event = SyncEvent(
            event_type=SyncEventType.USER_JOINED,
            actor=session.user_id,
            target_type="user",
            target_id=str(session.session_id),
            data={"user_name": session.user_name, "role": session.role.value},
            version=self._next_version(),
        )
        await self._broadcast(event)
        return event

    async def disconnect_user(self, session_id: UUID) -> SyncEvent | None:
        """Disconnect a user."""
        async with self._lock:
            session = self._sessions.pop(session_id, None)
            if not session:
                return None

        event = SyncEvent(
            event_type=SyncEventType.USER_LEFT,
            actor=session.user_id,
            target_type="user",
            target_id=str(session_id),
            data={"user_name": session.user_name},
            version=self._next_version(),
        )
        await self._broadcast(event)
        return event

    def get_connected_users(self) -> list[UserSession]:
        """Get all currently connected users."""
        return list(self._sessions.values())

    async def approve_decision(
        self,
        decision_id: str,
        session: UserSession,
        parent_version: int = 0,
    ) -> tuple[SyncEvent, bool]:
        """
        Approve a decision.

        Returns (event, success).
        If parent_version doesn't match current version, it's a conflict.
        """
        if not session.can_approve_decisions():
            return SyncEvent(
                event_type=SyncEventType.OPTIMISTIC_REJECTED,
                actor=session.user_id,
                target_type="decision",
                target_id=decision_id,
                data={"reason": "Insufficient permissions"},
                version=self._version,
            ), False

        async with self._lock:
            decision = self._decisions.get(decision_id)
            if not decision:
                # Create if doesn't exist
                decision = SharedDecision(decision_id=decision_id, title=decision_id)
                self._decisions[decision_id] = decision

            # Conflict detection
            if parent_version != 0 and parent_version != decision.version:
                # Conflict — reject the optimistic update
                return SyncEvent(
                    event_type=SyncEventType.OPTIMISTIC_REJECTED,
                    actor=session.user_id,
                    target_type="decision",
                    target_id=decision_id,
                    data={
                        "reason": "Version conflict",
                        "current_version": decision.version,
                        "parent_version": parent_version,
                    },
                    version=self._version,
                ), False

            # Apply the change
            decision.status = "approved"
            decision.version += 1
            decision.last_updated_by = session.user_id
            decision.last_updated_at = datetime.now(timezone.utc)

            # Confirm the optimistic update
            session.confirm_optimistic(UUID(decision_id) if len(decision_id) == 36 else uuid4())

        event = SyncEvent(
            event_type=SyncEventType.DECISION_APPROVED,
            actor=session.user_id,
            target_type="decision",
            target_id=decision_id,
            data={
                "status": "approved",
                "version": decision.version,
                "decision": decision.model_dump(),
            },
            version=self._next_version(),
        )
        await self._broadcast(event)
        return event, True

    async def reject_decision(
        self,
        decision_id: str,
        session: UserSession,
        reason: str = "",
        parent_version: int = 0,
    ) -> tuple[SyncEvent, bool]:
        """Reject a decision."""
        if not session.can_reject_decisions():
            return SyncEvent(
                event_type=SyncEventType.OPTIMISTIC_REJECTED,
                actor=session.user_id,
                target_type="decision",
                target_id=decision_id,
                data={"reason": "Insufficient permissions"},
                version=self._version,
            ), False

        async with self._lock:
            decision = self._decisions.get(decision_id)
            if not decision:
                decision = SharedDecision(decision_id=decision_id, title=decision_id)
                self._decisions[decision_id] = decision

            if parent_version != 0 and parent_version != decision.version:
                return SyncEvent(
                    event_type=SyncEventType.OPTIMISTIC_REJECTED,
                    actor=session.user_id,
                    target_type="decision",
                    target_id=decision_id,
                    data={"reason": "Version conflict", "current_version": decision.version},
                    version=self._version,
                ), False

            decision.status = "rejected"
            decision.version += 1
            decision.last_updated_by = session.user_id
            decision.last_updated_at = datetime.now(timezone.utc)

        event = SyncEvent(
            event_type=SyncEventType.DECISION_REJECTED,
            actor=session.user_id,
            target_type="decision",
            target_id=decision_id,
            data={
                "status": "rejected",
                "reason": reason,
                "version": decision.version,
            },
            version=self._next_version(),
        )
        await self._broadcast(event)
        return event, True

    async def update_stakeholder_position(
        self,
        decision_id: str,
        session: UserSession,
        position: str,
        reasoning: str = "",
    ) -> SyncEvent:
        """
        Update a stakeholder's position on a decision.

        This is a MERGE operation — each stakeholder sets their own position.
        No conflict possible (different users, different fields).
        """
        async with self._lock:
            decision = self._decisions.get(decision_id)
            if not decision:
                decision = SharedDecision(decision_id=decision_id, title=decision_id)
                self._decisions[decision_id] = decision

            # Merge — no conflict possible
            decision.stakeholder_positions[session.user_id] = position
            decision.version += 1
            decision.last_updated_by = session.user_id
            decision.last_updated_at = datetime.now(timezone.utc)

        event = SyncEvent(
            event_type=SyncEventType.DECISION_UPDATED,
            actor=session.user_id,
            target_type="decision",
            target_id=decision_id,
            data={
                "stakeholder": session.user_id,
                "position": position,
                "reasoning": reasoning,
                "version": decision.version,
            },
            version=self._next_version(),
        )
        await self._broadcast(event)
        return event

    async def broadcast_evidence(self, signal_data: dict[str, Any], actor: str) -> SyncEvent:
        """Broadcast that new evidence was added to the OEM."""
        event = SyncEvent(
            event_type=SyncEventType.EVIDENCE_ADDED,
            actor=actor,
            target_type="evidence",
            target_id=signal_data.get("signal_id", str(uuid4())),
            data=signal_data,
            version=self._next_version(),
        )
        await self._broadcast(event)
        return event

    async def broadcast_contradiction(self, event_data: dict[str, Any], actor: str) -> SyncEvent:
        """Broadcast that CEO feedback was applied."""
        event = SyncEvent(
            event_type=SyncEventType.CONTRADICTION_APPLIED,
            actor=actor,
            target_type="contradiction",
            target_id=event_data.get("target_id", ""),
            data=event_data,
            version=self._next_version(),
        )
        await self._broadcast(event)
        return event

    async def broadcast_law_update(self, law_code: str, changes: dict[str, Any], actor: str) -> SyncEvent:
        """Broadcast that a law's confidence or status changed."""
        event_type = SyncEventType.LAW_UPDATED
        if changes.get("status") == "stressed":
            event_type = SyncEventType.LAW_STRESSED
        elif changes.get("status") == "invalidated":
            event_type = SyncEventType.LAW_INVALIDATED

        event = SyncEvent(
            event_type=event_type,
            actor=actor,
            target_type="law",
            target_id=law_code,
            data=changes,
            version=self._next_version(),
        )
        await self._broadcast(event)
        return event

    def get_decision(self, decision_id: str) -> SharedDecision | None:
        return self._decisions.get(decision_id)

    def get_all_decisions(self) -> list[SharedDecision]:
        return list(self._decisions.values())

    def get_current_version(self) -> int:
        return self._version

    def on_event(self, handler: Callable) -> None:
        """Register a handler for sync events (e.g., WebSocket send)."""
        self._event_handlers.append(handler)

    def _next_version(self) -> int:
        self._version += 1
        return self._version

    async def _broadcast(self, event: SyncEvent) -> None:
        """Broadcast an event to all connected users."""
        self._pending_events.append(event)
        for handler in self._event_handlers:
            try:
                result = handler(event)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                pass  # Handler failed — don't crash the OEM

    def get_pending_events(self) -> list[SyncEvent]:
        """Get events that haven't been consumed yet (for testing)."""
        return self._pending_events.copy()

    def clear_pending_events(self) -> None:
        self._pending_events.clear()


class ConflictResolution:
    """
    Conflict resolution strategies for shared state.

    Strategies:
    1. Last-Write-Wins (LWW): for status fields (approved/rejected/deferred)
       - The last update wins, but the loser gets a notification
    2. Merge: for additive fields (stakeholder positions, evidence)
       - No conflict possible — each user writes to their own slot
    3. Version-based: for confidence-sensitive fields
       - Client sends parent_version; server rejects if stale
    """

    @staticmethod
    def resolve_decision_status(
        current: SharedDecision,
        incoming_status: str,
        incoming_version: int,
        incoming_user: str,
    ) -> tuple[bool, str]:
        """
        Resolve a decision status conflict.

        Returns (accepted, reason).
        """
        # Version check
        if incoming_version != 0 and incoming_version < current.version:
            return False, f"Stale version: incoming={incoming_version}, current={current.version}"

        # LWW — last write wins
        return True, "accepted"

    @staticmethod
    def resolve_stakeholder_position(
        current: SharedDecision,
        user_id: str,
        position: str,
    ) -> tuple[bool, str]:
        """
        Resolve a stakeholder position update.

        Always succeeds — each user writes to their own slot.
        """
        return True, "merged"

    @staticmethod
    def create_rollback_events(
        rejected_update: OptimisticUpdate,
        current_state: dict[str, Any],
    ) -> SyncEvent:
        """Create a rollback event for a rejected optimistic update."""
        return SyncEvent(
            event_type=SyncEventType.OPTIMISTIC_REJECTED,
            actor=rejected_update.user_id,
            target_type=rejected_update.target_type,
            target_id=rejected_update.target_id,
            data={
                "field": rejected_update.field,
                "old_value": rejected_update.old_value,
                "new_value": rejected_update.new_value,
                "current_state": current_state,
                "reason": rejected_update.rejection_reason or "version conflict",
            },
        )
