"""
Database Schemas for AvatarMeet

Each Pydantic model represents a MongoDB collection.
Class name lowercased is used as the collection name (e.g., Room -> "room").
"""
from pydantic import BaseModel, Field
from typing import Optional

class Room(BaseModel):
    code: str = Field(..., description="Unique room code (e.g., ABC123)")
    scene: str = Field("classroom", description="3D scene preset: classroom | space | nature")
    is_active: bool = Field(True, description="Whether room is active")
    max_participants: int = Field(16, ge=1, le=64)

class Participant(BaseModel):
    room_code: str = Field(..., description="Room code this participant belongs to")
    name: Optional[str] = Field(None, description="Display name")
    is_muted: bool = Field(False)
    avatar_url: Optional[str] = None
