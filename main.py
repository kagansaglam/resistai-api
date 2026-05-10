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
        import chromadb
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        client = chromadb.PersistentClient(
            path=os.path.join(os.path.dirname(__file__), "data", "chroma_db")
        )
        collection = client.get_collection("pubmed_articles")
        embedding = model.encode([query.query]).tolist()
        results = collection.query(query_embeddings=embedding, n_results=query.n_results)
        articles = []
        for i, doc in enumerate(results["documents"][0]):
            meta = results["metadatas"][0][i]
            articles.append({
                "title": doc,
                "pmid": meta["pmid"],
                "journal": meta["journal"],
                "year": meta["year"],
                "relevance_score": round(1 - results["distances"][0][i], 3),
                "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{meta['pmid']}"
            })
        return {"query": query.query, "results": articles}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
