from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

CaseActivityEventType = Literal[
    "job_status_changed",
    "job_completed",
    "image_status_changed",
]

CaseActivityCommandType = Literal[
    "subscribe",
    "unsubscribe",
]

AnalysisJobStatus = Literal[
    "queued",
    "running",
    "completed",
    "failed",
    "canceled",
    "dead_letter",
]

TerminalAnalysisJobStatus = Literal[
    "completed",
    "failed",
    "canceled",
    "dead_letter",
]

ImageProcessingStatus = Literal[
    "uploaded",
    "processing",
    "ready",
    "failed",
]


class CaseActivityEventBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: CaseActivityEventType
    caseId: str
    timestamp: datetime


class JobStatusChangedEvent(CaseActivityEventBase):
    type: Literal["job_status_changed"]
    jobId: str
    status: AnalysisJobStatus


class JobCompletedEvent(CaseActivityEventBase):
    type: Literal["job_completed"]
    jobId: str
    status: TerminalAnalysisJobStatus


class ImageStatusChangedEvent(CaseActivityEventBase):
    type: Literal["image_status_changed"]
    imageId: str
    status: ImageProcessingStatus
    jobId: str | None = None


CaseActivityEvent = Annotated[
    JobStatusChangedEvent | JobCompletedEvent | ImageStatusChangedEvent,
    Field(discriminator="type"),
]

CASE_ACTIVITY_EVENT_ADAPTER = TypeAdapter(CaseActivityEvent)


class CaseActivityCommandBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: CaseActivityCommandType


class CaseActivitySubscribeCommand(CaseActivityCommandBase):
    type: Literal["subscribe"]
    caseId: str
    jobId: str | None = None


class CaseActivityUnsubscribeCommand(CaseActivityCommandBase):
    type: Literal["unsubscribe"]


CaseActivityCommand = Annotated[
    CaseActivitySubscribeCommand | CaseActivityUnsubscribeCommand,
    Field(discriminator="type"),
]

CASE_ACTIVITY_COMMAND_ADAPTER = TypeAdapter(CaseActivityCommand)


def validate_case_activity_event(payload: object) -> CaseActivityEvent:
    return CASE_ACTIVITY_EVENT_ADAPTER.validate_python(payload)


def validate_case_activity_command(payload: object) -> CaseActivityCommand:
    return CASE_ACTIVITY_COMMAND_ADAPTER.validate_python(payload)
