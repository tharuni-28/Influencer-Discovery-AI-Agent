# 🚀 Influencer Discovery AI Agent

An AI-powered web application designed to help brands and marketers discover, analyze, and manage social media influencers using natural language queries. 

## 🌟 Key Features
* **AI-Powered Search:** Find relevant influencers across platforms by simply typing what you need (e.g., "Tech YouTubers in Tamil Nadu").
* **Smart Data Extraction:** Utilizes Google Gemini and Tavily Search APIs to fetch up-to-date internet data and analyze influencer metrics.
* **CRM Management:** Save selected influencers directly into a local SQLite database to manage campaigns and track leads.
* **Modern UI:** Clean, responsive, and user-friendly web interface built with HTML, CSS, and JavaScript.

## 🛠️ Tech Stack
* **Backend:** Python, FastAPI
* **AI & Search:** Google Gemini API, Tavily Search API
* **Database:** SQLite (Local CRM)
* **Frontend:** HTML5, CSS3, Vanilla JavaScript
* **Deployment:** Vercel (UI & AI Search hosting)

## 📝 Important Note for Evaluators
* **Live Demo (Vercel):** The frontend and AI search functionalities are deployed live. 
* **Local CRM Database:** Because Vercel operates on a serverless architecture with a read-only file system, the SQLite database saving feature (`.db` modification) is intentionally showcased via **Localhost (VS Code)** during the video demo to demonstrate full Read/Write CRM capabilities.

## 💻 Local Setup & Installation (For Full Testing)

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/your-username/Influencer-Discovery-AI-Agent.git](https://github.com/your-username/Influencer-Discovery-AI-Agent.git)
   cd Influencer-Discovery-AI-Agent
 2.**Install Dependency**
 pip install -r requirements.txt
 3.**Environment Variables:**
Create a .env file in the root directory and add your API keys:
GEMINI_API_KEY=AQ.Ab8RN6Lf0g9vRVw87B6jryWMMAv5fbLOU1lQ8a0RdIPZaT9MCA
TAVILY_API_KEY=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
4.**Run the Application**
uvicorn main:app --reload
5.**Open in Browser**
Navigate to http://127.0.0.1:8000 to experience the full AI Agent with CRM database capabilities.
