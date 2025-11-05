import os
import random
import string
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents
from schemas import Room, Participant

app = FastAPI(title="AvatarMeet API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
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


@app.post("/rooms", response_model=CreateRoomResponse)
def create_room(payload: CreateRoomRequest):
    # Generate unique code
    for _ in range(10):
        code = _generate_code()
        if db["room"].find_one({"code": code}) is None:
            break
    else:
        raise HTTPException(status_code=500, detail="Failed to generate unique room code")

    room = Room(code=code, scene=payload.scene or "classroom", max_participants=payload.max_participants or 16)
    create_document("room", room)
    return CreateRoomResponse(code=code, scene=room.scene)


@app.post("/rooms/join", response_model=JoinRoomResponse)
def join_room(payload: JoinRoomRequest):
    doc = db["room"].find_one({"code": payload.code.upper()})
    if not doc:
        raise HTTPException(status_code=404, detail="Room not found")

    # Optionally track participant
    participant = Participant(room_code=payload.code.upper(), name=payload.name)
    try:
        create_document("participant", participant)
    except Exception:
        pass

    return JoinRoomResponse(code=doc["code"], scene=doc.get("scene", "classroom"))


@app.get("/rooms/{code}")
def get_room(code: str):
    doc = db["room"].find_one({"code": code.upper()})
    if not doc:
        raise HTTPException(status_code=404, detail="Room not found")
    doc["_id"] = str(doc["_id"])  # make JSON serializable
    return doc


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
