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

load_dotenv(override=True)  # .env always wins over old Windows variables

print(">>> main.py NEW VERSION loaded")



# ----------------- INITIALIZE DATABASE -----------------

Base.metadata.create_all(bind=engine)


# ----------------- INITIALIZE API CLIENTS -----------------

def clean_key(name: str) -> str:
    """Read a key from .env and remove spaces/quotes that cause 401 errors."""
    return (os.getenv(name) or "").strip().strip('"').strip("'")


TAVILY_API_KEY = clean_key("TAVILY_API_KEY")
GEMINI_API_KEY = clean_key("GEMINI_API_KEY")

# Safe check: shows only the first 3 characters and the length, never the full key
print(f"Gemini key check -> starts with: '{GEMINI_API_KEY[:3]}' | length: {len(GEMINI_API_KEY)}")
print(f"Tavily key check -> starts with: '{TAVILY_API_KEY[:5]}' | length: {len(TAVILY_API_KEY)}")

tavily_client = TavilyClient(api_key=TAVILY_API_KEY)

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

# Models to try, in order. If one is busy (503), the next one is used.
# Fastest model first. If it is busy or missing, the next one is used.
GEMINI_MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
]

# Remembers recent searches so the same search is instant
SEARCH_CACHE = {}


def call_gemini_with_retry(contents: str, max_seconds: int = 20):
    """Call Gemini. If busy (503/429), retry quickly, then try the next model.
    Stops after max_seconds so the request never hangs on Vercel."""
    last_error = None
    deadline = time.time() + max_seconds

    for model in GEMINI_MODELS:
        for attempt in range(2):
            if time.time() > deadline:
                raise last_error or Exception("503 UNAVAILABLE: time limit reached")
            try:
                return gemini_client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        max_output_tokens=2000,
                    ),
                )
            except Exception as e:
                last_error = e
                msg = str(e)
                if "503" in msg or "UNAVAILABLE" in msg or "429" in msg:
                    print(f"[{model}] busy, retry {attempt + 1}/2 ...")
                    time.sleep(1)
                    continue
                if "404" in msg or "NOT_FOUND" in msg:
                    print(f"[{model}] not found, trying next model")
                    break
                raise

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

        cache_key = req.prompt.strip().lower()
        if cache_key in SEARCH_CACHE:
            print("Cache hit -> instant result")
            return SEARCH_CACHE[cache_key]

        t_start = time.time()

        # 1. Search the web using Tavily

        search_query = f"{req.prompt} creator profile"

        search_response = tavily_client.search(
            query=search_query,
            max_results=5,
            search_depth="basic"
        )

        snippets = [
            res.get("content", "")[:600]
            for res in search_response.get("results", [])
        ]

        search_context = "\n---\n".join(snippets)
        print(f"Tavily took {time.time() - t_start:.1f}s")
        t_ai = time.time()


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

        result = data.get("influencers", [])
        print(f"Gemini took {time.time() - t_ai:.1f}s | total {time.time() - t_start:.1f}s")

        if result:
            SEARCH_CACHE[cache_key] = result

        return result


    except Exception as e:

        # Print actual error in VS Code terminal
        print(f"\n--- ERROR DETAILS ---\n{str(e)}\n---------------------\n")

        msg = str(e)

        if "503" in msg or "UNAVAILABLE" in msg:
            detail = "The AI service is busy right now. Please try again in a few seconds."
        elif "429" in msg or "RESOURCE_EXHAUSTED" in msg:
            detail = "AI usage limit reached. Please wait a minute and try again."
        elif "API key" in msg or "401" in msg or "403" in msg:
            detail = "An API key is missing or invalid. Check GEMINI_API_KEY and TAVILY_API_KEY."
        elif "Expecting value" in msg or "JSONDecodeError" in msg:
            detail = "The AI returned an unreadable answer. Please search again."
        else:
            detail = f"Search failed: {msg[:150]}"

        raise HTTPException(status_code=500, detail=detail)


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
