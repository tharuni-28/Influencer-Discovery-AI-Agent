import os
import json
import time

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from pydantic import BaseModel
from typing import List, Optional

from sqlalchemy.orm import Session
from dotenv import load_dotenv
from tavily import TavilyClient

from google import genai
from google.genai import types

# Import database session and model
from database import engine, get_db, Influencer, Base


# ----------------- LOAD ENVIRONMENT VARIABLES -----------------

load_dotenv()


# ----------------- INITIALIZE DATABASE -----------------

Base.metadata.create_all(bind=engine)


# ----------------- INITIALIZE API CLIENTS -----------------

tavily_client = TavilyClient(
    api_key=os.getenv("TAVILY_API_KEY")
)

gemini_client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

# Models to try, in order. If one is busy (503), the next one is used.
GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
]


def call_gemini_with_retry(contents: str):
    """Call Gemini. If it is busy (503/429), retry, then try the next model."""
    last_error = None

    for model in GEMINI_MODELS:
        for attempt in range(3):
            try:
                return gemini_client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    ),
                )
            except Exception as e:
                last_error = e
                msg = str(e)
                if "503" in msg or "UNAVAILABLE" in msg or "429" in msg:
                    print(f"[{model}] busy, retry {attempt + 1}/3 ...")
                    time.sleep(2 ** attempt)  # wait 1s, 2s, 4s
                    continue
                if "404" in msg or "NOT_FOUND" in msg:
                    print(f"[{model}] not found, trying next model")
                    break  # skip to the next model
                raise  # a real bug, show it

    raise last_error


# ----------------- FASTAPI APP -----------------

app = FastAPI(
    title="Influencer Discovery AI Agent"
)


# ----------------- ENABLE CORS -----------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------- PYDANTIC SCHEMAS -----------------

class SearchRequest(BaseModel):
    prompt: str


class InfluencerSchema(BaseModel):
    name: str
    handle: str
    platform: str
    followers: Optional[str] = "Not specified"
    niche: Optional[str] = "Content Creator"
    url: Optional[str] = "#"


class InfluencerResponse(InfluencerSchema):
    id: str   # <-- CHANGED from int to str (your database uses UUID text ids)

    class Config:
        from_attributes = True


# ----------------- SERVE FRONTEND -----------------

@app.get("/")
def serve_frontend():

    if not os.path.exists("index.html"):
        raise HTTPException(
            status_code=404,
            detail="index.html not found."
        )

    return FileResponse("index.html")


# ----------------- SEARCH API (GEMINI) -----------------

@app.post("/api/search")
def search_influencers(req: SearchRequest):

    try:

        # 1. Search the web using Tavily

        search_query = f"{req.prompt} creator profile"

        search_response = tavily_client.search(
            query=search_query,
            max_results=10,
            search_depth="advanced"
        )

        snippets = [
            res.get("content", "")
            for res in search_response.get("results", [])
        ]

        search_context = "\n---\n".join(snippets)


        # 2. Prepare the Prompt

        system_prompt = (
            "You are an expert influencer marketing AI research assistant. "
            "Analyze the search context provided and extract relevant creator "
            "profiles matching the user's criteria. "

            "Return valid JSON matching this schema: "

            '{"influencers": ['
            '{"name": "string", '
            '"handle": "string", '
            '"platform": "string", '
            '"followers": "string", '
            '"niche": "string", '
            '"url": "string"}'
            "]}. "

            "If exact metrics are missing, use 'Not specified'."
        )

        full_prompt = (
            f"{system_prompt}\n\n"
            f"User Prompt: {req.prompt}\n\n"
            f"Search Context:\n{search_context}"
        )


        # 3. Ask Gemini to extract the data (with retry + fallback models)

        response = call_gemini_with_retry(full_prompt)


        # 4. Get Gemini response

        raw_text = response.text.strip()

        # Remove Markdown code fences if Gemini adds them

        raw_text = raw_text.replace("```json", "").replace("```", "").strip()


        # 5. Convert Gemini JSON response into Python data

        data = json.loads(raw_text)


        # 6. Return influencers

        return data.get("influencers", [])


    except Exception as e:

        # Print actual error in VS Code terminal

        print(
            f"\n--- ERROR DETAILS ---\n"
            f"{str(e)}\n"
            f"---------------------\n"
        )

        # Friendly message if Google's AI is overloaded

        if "503" in str(e) or "UNAVAILABLE" in str(e):
            raise HTTPException(
                status_code=503,
                detail="The AI service is busy right now. Please try again in a few seconds."
            )

        raise HTTPException(
            status_code=500,
            detail="Internal Server Error: Check VS Code Terminal for details."
        )


# ----------------- CRM API -----------------

@app.get(
    "/api/crm",
    response_model=List[InfluencerResponse]
)
def get_saved_influencers(
    db: Session = Depends(get_db)
):

    return (
        db.query(Influencer)
        .order_by(Influencer.id.desc())
        .all()
    )


# ----------------- SAVE INFLUENCER TO CRM -----------------

@app.post(
    "/api/crm",
    response_model=InfluencerResponse
)
def save_influencer_to_crm(
    inf: InfluencerSchema,
    db: Session = Depends(get_db)
):

    new_influencer = Influencer(
        name=inf.name,
        handle=inf.handle,
        platform=inf.platform,
        followers=inf.followers,
        niche=inf.niche,
        url=inf.url
    )

    db.add(new_influencer)

    db.commit()

    db.refresh(new_influencer)

    return new_influencer