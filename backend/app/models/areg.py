from __future__ import annotations

from pydantic import BaseModel, Field


class AregStaticObjectRequest(BaseModel):
    host: str | None = None
    port: int = Field(default=5025, ge=1, le=65535)
    source_hw: int = Field(default=1, ge=1, le=8)
    object_index: int = Field(default=1, ge=1, le=8)
    range_value: float | None = None
    attenuation: float | None = None
    rcs: float | None = None
    doppler_speed: float | None = None
    doppler_frequency: float | None = None
    angle_horizontal: float | None = None


class AregCommandStep(BaseModel):
    command: str
    response: str | None = None
    note: str | None = None


class AregCommandTemplate(BaseModel):
    group: str
    command: str
    purpose: str
    example: str | None = None
    placeholders: list[str] = Field(default_factory=list)


class AregCommandLibraryResponse(BaseModel):
    device: str
    warning: str
    placeholders: dict[str, str] = Field(default_factory=dict)
    commands: list[AregCommandTemplate]


class AregStaticObjectResponse(BaseModel):
    host: str
    port: int
    source_hw: int
    object_index: int
    steps: list[AregCommandStep]
    errors: list[str]