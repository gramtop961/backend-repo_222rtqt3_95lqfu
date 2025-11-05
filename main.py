import os
import random
import string
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document
from schemas import Room, Participant

app = FastAPI(title="AvatarMeet API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Fallback in-memory store when database quota blocks writes (non-persistent)
FALLBACK_ROOMS: dict[str, dict] = {}


@app.get("/")
def read_root():
    return {"message": "AvatarMeet backend running"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": [],
        "fallback_active": False,
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = os.getenv("DATABASE_NAME") or "❌ Not Set"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    response["fallback_active"] = len(FALLBACK_ROOMS) > 0
    return response


# --------------------- Rooms API ---------------------
class CreateRoomRequest(BaseModel):
    scene: Optional[str] = "classroom"
    max_participants: Optional[int] = 16


class CreateRoomResponse(BaseModel):
    code: str
    scene: str


class JoinRoomRequest(BaseModel):
    code: str
    name: Optional[str] = None


class JoinRoomResponse(BaseModel):
    code: str
    scene: str


def _generate_code(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))


def _save_room_persistently(room: Room) -> None:
    """Try to persist a room. If quota blocks writes, fall back to memory."""
    try:
        create_document("room", room)
    except Exception as e:
        # Quota errors from Cosmos DB (Mongo API) include Forbidden/Quota exceeded
        if "Quota" in str(e) or "Forbidden" in str(e) or "quota" in str(e).lower():
            FALLBACK_ROOMS[room.code] = room.model_dump()
        else:
            raise


def _find_room(code: str) -> Optional[dict]:
    # Try DB first
    try:
        if db is not None:
            doc = db["room"].find_one({"code": code})
            if doc:
                return doc
    except Exception:
        pass
    # Fallback memory
    return FALLBACK_ROOMS.get(code)


@app.post("/rooms", response_model=CreateRoomResponse)
def create_room(payload: CreateRoomRequest):
    try:
        # Generate unique code
        for _ in range(10):
            code = _generate_code()
            # Check both DB and fallback to ensure uniqueness
            unique = True
            try:
                if db is not None and db["room"].find_one({"code": code}) is not None:
                    unique = False
            except Exception:
                pass
            if code in FALLBACK_ROOMS:
                unique = False
            if unique:
                break
        else:
            raise RuntimeError("Failed to generate unique room code")

        room = Room(code=code, scene=payload.scene or "classroom", max_participants=payload.max_participants or 16)
        _save_room_persistently(room)
        return CreateRoomResponse(code=code, scene=room.scene)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Create room failed: {e}")


@app.post("/rooms/join", response_model=JoinRoomResponse)
def join_room(payload: JoinRoomRequest):
    try:
        code = payload.code.upper()
        doc = _find_room(code)
        if not doc:
            raise HTTPException(status_code=404, detail="Room not found")

        # Optionally track participant (best-effort)
        try:
            participant = Participant(room_code=code, name=payload.name)
            create_document("participant", participant)
        except Exception:
            pass

        return JoinRoomResponse(code=code, scene=doc.get("scene", "classroom"))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Join failed: {e}")


@app.get("/rooms/{code}")
def get_room(code: str):
    try:
        code = code.upper()
        doc = _find_room(code)
        if not doc:
            raise HTTPException(status_code=404, detail="Room not found")
        # Make JSON serializable if from DB
        if isinstance(doc, dict) and "_id" in doc:
            try:
                from bson import ObjectId  # type: ignore
                doc["_id"] = str(doc["_id"])  # noqa: F401
            except Exception:
                doc.pop("_id", None)
        return doc
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fetch room failed: {e}")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
