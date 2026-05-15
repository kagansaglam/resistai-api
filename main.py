from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import json
import os
import pandas as pd

app = FastAPI(
    title="ResistAI API",
    description="Given a protein identifier, ResistAI identifies druggable pockets and retrieves relevant resistance literature.",
    version="1.0.0"
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ANNOTATED_PATH = os.path.join(os.path.dirname(__file__), "data", "proteins_annotated.csv")
df = pd.read_csv(ANNOTATED_PATH) if os.path.exists(ANNOTATED_PATH) else pd.DataFrame()

class SearchQuery(BaseModel):
    query: str
    n_results: Optional[int] = 10
@app.get("/")
def root():
    return {
        "name": "ResistAI API",
        "version": "1.0.0",
        "description": "Given a protein identifier, ResistAI identifies druggable pockets and retrieves relevant resistance literature.",
        "endpoints": ["/proteins", "/proteins/{uniprot_id}", "/search", "/stats", "/docs"]
    }
@app.get("/stats")
def stats():
    if df.empty:
        raise HTTPException(status_code=500, detail="Data not loaded")
    high   = len(df[df["best_score"] >= 0.7])
    medium = len(df[(df["best_score"] >= 0.4) & (df["best_score"] < 0.7)])
    low    = len(df[df["best_score"] < 0.4])
    return {
        "total_proteins": len(df),
        "high_druggability": high,
        "medium_druggability": medium,
        "low_druggability": low,
        "best_score": float(df["best_score"].max()),
        "families": df["family"].value_counts().to_dict()
    }
@app.get("/proteins")
def list_proteins(family: Optional[str] = None, tier: Optional[str] = None, limit: int = 20):
    result = df.copy()
    if family:
        result = result[result["family"].str.lower() == family.lower()]
    if tier == "high":
        result = result[result["best_score"] >= 0.7]
    elif tier == "medium":
        result = result[(result["best_score"] >= 0.4) & (result["best_score"] < 0.7)]
    elif tier == "low":
        result = result[result["best_score"] < 0.4]
    result = result.sort_values("best_score", ascending=False).head(limit)
    return result[["uniprot_id","gene","organism","family","best_score","total_pockets"]].to_dict(orient="records")

@app.get("/proteins/{uniprot_id}")
def get_protein(uniprot_id: str):
    row = df[df["uniprot_id"] == uniprot_id.upper()]
    if row.empty:
        raise HTTPException(status_code=404, detail=f"Protein {uniprot_id} not found")
    pocket_path = os.path.expanduser(f"~/resistai/results/pockets/{uniprot_id.upper()}_pockets.json")
    pockets = []
    if os.path.exists(pocket_path):
        with open(pocket_path) as f:
            pocket_data = json.load(f)
            pockets = pocket_data.get("all_pockets", [])[:5]
    r = row.iloc[0]
    tier = "high" if r["best_score"] >= 0.7 else "medium" if r["best_score"] >= 0.4 else "low"
    return {
        "uniprot_id": r["uniprot_id"],
        "gene": r["gene"],
        "organism": r["organism"],
        "family": r["family"],
        "druggability": {
            "best_score": float(r["best_score"]),
            "tier": tier,
            "total_pockets": int(r["total_pockets"]),
            "high_pockets": int(r["high_druggability"]),
            "medium_pockets": int(r["medium_druggability"]),
        },
        "top_pockets": pockets
    }
@app.post("/search")
def search_literature(query: SearchQuery):
    try:
        import requests as req
        r = req.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi", params={
            "db": "pubmed", "term": query.query + " antibiotic resistance",
            "retmax": query.n_results, "retmode": "json", "sort": "relevance"
        })
        pmids = r.json()["esearchresult"]["idlist"]
        if not pmids:
            return {"query": query.query, "results": []}
        s = req.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi", params={
            "db": "pubmed", "id": ",".join(pmids), "retmode": "json"
        })
        data = s.json()
        articles = []
        for pmid in pmids:
            doc = data.get("result", {}).get(pmid, {})
            if not doc or pmid == "uids":
                continue
            articles.append({
                "title": doc.get("title", ""),
                "pmid": pmid,
                "journal": doc.get("source", ""),
                "year": doc.get("pubdate", "")[:4],
                "relevance_score": 1.0,
                "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}"
            })
        return {"query": query.query, "results": articles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class AskQuery(BaseModel):
    query: str
    articles: list

@app.post("/ask")
def ask_ai(query: AskQuery):
    try:
        from groq import Groq
        import os
        from dotenv import load_dotenv
        load_dotenv()
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        context = "\n".join([
            f"- [PMID:{a['pmid']}] ({a['year']}) {a['title']} ({a['journal']})"
            for a in query.articles[:10]
        ])
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are ResistAI, an expert research assistant specialising in antibiotic resistance mechanisms and drug discovery. Base your answers on the provided PubMed literature. Cite papers using PMID. Be scientifically precise and concise."},
                {"role": "user", "content": f"Question: {query.query}\n\nRelevant literature:\n{context}"}
            ],
            max_tokens=800
        )
        return {"answer": response.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class EmailReport(BaseModel):
    to_email: str
    user_name: str
    query: str
    answer: str
    articles: list

@app.post("/send-report")
def send_report(data: EmailReport):
    try:
        import resend
        resend.api_key = os.getenv("RESEND_API_KEY")
        articles_html = "".join([
            f'<li><a href="{a["pubmed_url"]}">[PMID:{a["pmid"]}] ({a["year"]}) {a["title"]}</a></li>'
            for a in data.articles[:5]
        ])
        resend.Emails.send({
            "from": "ResistAI <noreply@resend.dev>",
            "to": data.to_email,
            "subject": f"ResistAI Report: {data.query[:50]}",
            "html": f"""
            <h2>ResistAI Research Report</h2>
            <p>Hi {data.user_name},</p>
            <p>Here is your research summary for: <strong>{data.query}</strong></p>
            <h3>AI Analysis</h3>
            <p>{data.answer}</p>
            <h3>Referenced Articles</h3>
            <ul>{articles_html}</ul>
            <p><small>ResistAI — Antibiotic Resistance Research Platform</small></p>
            """
        })
        return {"success": True, "message": "Report sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class WelcomeEmail(BaseModel):
    to_email: str
    user_name: str

@app.post("/send-welcome")
def send_welcome(data: WelcomeEmail):
    try:
        import resend
        resend.api_key = os.getenv("RESEND_API_KEY")
        resend.Emails.send({
            "from": "ResistAI <noreply@resend.dev>",
            "to": data.to_email,
            "subject": "Welcome to ResistAI",
            "html": f"""
            <img src="https://resistai-web.vercel.app/logo.png" alt="ResistAI" style="height:48px;margin-bottom:16px;" /><h2>Welcome to ResistAI, {data.user_name}!</h2>
            <p>You now have access to our antibiotic resistance research platform.</p>
            <ul>
                <li>Search across 2,500+ PubMed articles</li>
                <li>Analyse druggable protein pockets</li>
                <li>Get AI-powered research summaries</li>
            </ul>
            <p><a href="https://resistai-web.vercel.app/dashboard">Go to Dashboard →</a></p>
            <p><small>ResistAI — Antibiotic Resistance Research Platform</small></p>
            """
        })
        return {"success": True, "message": "Welcome email sent"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
