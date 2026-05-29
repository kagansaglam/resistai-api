from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import json
import logging
import os
import pandas as pd

log = logging.getLogger(__name__)

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

ANNOTATED_PATH   = os.path.join(os.path.dirname(__file__), "data", "proteins_annotated.csv")
CHROMA_PATH      = os.path.join(os.path.dirname(__file__), "data", "chroma_esm")
EMBEDDINGS_PATH  = os.path.join(os.path.dirname(__file__), "data", "embeddings.parquet")
PROTEIN_COLL     = "esm_embeddings"

df = pd.read_csv(ANNOTATED_PATH) if os.path.exists(ANNOTATED_PATH) else pd.DataFrame()

# --- ChromaDB protein-embedding index (lazy-loaded on first use) ---
_chroma_client  = None
_protein_collection = None

def _get_protein_collection():
    global _chroma_client, _protein_collection
    if _protein_collection is not None:
        return _protein_collection

    import chromadb
    _chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)

    if not os.path.exists(EMBEDDINGS_PATH):
        return None  # embeddings not generated yet

    emb_df = pd.read_parquet(EMBEDDINGS_PATH)
    feat_cols = [c for c in emb_df.columns if c.startswith("f")]

    try:
        existing = _chroma_client.get_collection(PROTEIN_COLL)
        if existing.count() == len(emb_df):
            _protein_collection = existing
            log.info(f"Loaded existing '{PROTEIN_COLL}' collection ({existing.count()} proteins)")
            return _protein_collection
        # Stale — delete and rebuild
        _chroma_client.delete_collection(PROTEIN_COLL)
        log.info("Rebuilding protein_embeddings collection …")
    except Exception:
        log.info("Creating protein_embeddings collection …")

    collection = _chroma_client.create_collection(
        PROTEIN_COLL,
        metadata={"hnsw:space": "cosine"},
    )

    # Index in batches of 500
    BATCH = 500
    for start in range(0, len(emb_df), BATCH):
        chunk = emb_df.iloc[start : start + BATCH]
        ids        = chunk["uniprot_id"].tolist()
        embeddings = chunk[feat_cols].values.tolist()
        metas      = []
        for uid in ids:
            row = df[df["uniprot_id"] == uid]
            if not row.empty:
                r = row.iloc[0]
                metas.append({
                    "gene":      str(r.get("gene", "")),
                    "organism":  str(r.get("organism", "")),
                    "family":    str(r.get("family", "")),
                    "best_score": float(r.get("best_score", 0)),
                })
            else:
                metas.append({})
        collection.add(ids=ids, embeddings=embeddings, metadatas=metas)
        log.info(f"  indexed {min(start + BATCH, len(emb_df))}/{len(emb_df)}")

    _protein_collection = collection
    log.info(f"protein_embeddings indexed: {collection.count()} proteins")
    return _protein_collection

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
def list_proteins(family: Optional[str] = None, tier: Optional[str] = None, limit: int = 50, offset: int = 0):
    result = df.copy()
    if family:
        result = result[result["family"].str.lower() == family.lower()]
    if tier == "high":
        result = result[result["best_score"] >= 0.7]
    elif tier == "medium":
        result = result[(result["best_score"] >= 0.4) & (result["best_score"] < 0.7)]
    elif tier == "low":
        result = result[result["best_score"] < 0.4]
    result = result.sort_values("best_score", ascending=False).iloc[offset:offset+limit]
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
    # Guvenlik agi: gecersiz/bos email'i reddet - yanlis adrese rapor gitmesin
    email = (data.to_email or "").strip()
    if "@" not in email or "." not in email.split("@")[-1] or len(email) < 5:
        raise HTTPException(status_code=400, detail="Valid recipient email required")
    try:
        import resend
        resend.api_key = os.getenv("RESEND_API_KEY")

        articles_rows = "".join([
            f'<tr style="border-bottom:1px solid #e5e7eb"><td style="padding:10px 0">' +
            f'<a href="{a["pubmed_url"]}" style="color:#059669;font-size:13px;font-weight:500">[PMID:{a["pmid"]}]</a> ' +
            f'<span style="font-size:12px;color:#6b7280">({a["year"]})</span><br>' +
            f'<span style="font-size:13px;color:#374151">{a["title"]}</span><br>' +
            f'<span style="font-size:11px;color:#9ca3af">{a["journal"]}</span></td></tr>'
            for a in data.articles[:10]
        ])

        articles_section = f"""
            <div style="margin:20px 0">
              <h2 style="font-size:14px;color:#111;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:12px">Referenced Literature ({len(data.articles)} articles)</h2>
              <table style="width:100%;border-collapse:collapse">{articles_rows}</table>
            </div>
        """ if data.articles else ""

        html = f"""<!DOCTYPE html>
<html>
<body style="font-family:system-ui,sans-serif;max-width:600px;margin:0 auto;padding:24px;color:#1a1a1a;background:#fff">
  <div style="border-bottom:2px solid #059669;padding-bottom:16px;margin-bottom:24px">
    <h1 style="margin:0;font-size:20px;color:#059669">ResistAI Research Report</h1>
    <p style="margin:4px 0 0;color:#6b7280;font-size:13px">Antibiotic Resistance Druggability Platform</p>
  </div>
  <p style="color:#374151">Hi <strong>{data.user_name}</strong>,</p>
  <p style="color:#374151">Research report for: <strong>{data.query}</strong></p>
  <div style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:16px;margin:20px 0">
    <h2 style="margin:0 0 12px;font-size:14px;color:#065f46;text-transform:uppercase">Analysis Summary</h2>
    <p style="margin:0;font-size:14px;color:#065f46;line-height:1.6">{data.answer}</p>
  </div>
  {articles_section}
  <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin:20px 0">
    <h2 style="margin:0 0 8px;font-size:12px;color:#6b7280;text-transform:uppercase">Druggability Scale Reference</h2>
    <table style="width:100%;border-collapse:collapse;margin-top:8px">
      <tr>
        <td style="text-align:center;background:#ecfdf5;border-radius:6px;padding:8px;width:33%"><div style="font-size:16px;font-weight:700;color:#059669">High</div><div style="font-size:11px;color:#6b7280">score &#8805; 0.7</div></td>
        <td style="width:8px"></td>
        <td style="text-align:center;background:#fffbeb;border-radius:6px;padding:8px;width:33%"><div style="font-size:16px;font-weight:700;color:#d97706">Medium</div><div style="font-size:11px;color:#6b7280">0.4 – 0.7</div></td>
        <td style="width:8px"></td>
        <td style="text-align:center;background:#fef2f2;border-radius:6px;padding:8px;width:33%"><div style="font-size:16px;font-weight:700;color:#dc2626">Low</div><div style="font-size:11px;color:#6b7280">score &lt; 0.4</div></td>
      </tr>
    </table>
    <p style="font-size:11px;color:#9ca3af;margin:8px 0 0">Scores computed by fpocket on AlphaFold-predicted structures. ML predictions via XGBoost + ESM-2 embeddings. Experimental validation required.</p>
  </div>
  <div style="border-top:1px solid #e5e7eb;padding-top:16px;margin-top:24px">
    <a href="https://resistai.bio/dashboard" style="display:inline-block;background:#059669;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none;font-size:13px;font-weight:500">Open Dashboard</a>
    <p style="font-size:11px;color:#9ca3af;margin:12px 0 0">ResistAI &middot; resistai.bio &middot; Kagan Saglam &middot; MIT License</p>
  </div>
</body>
</html>"""

        resend.Emails.send({
            "from": "ResistAI <noreply@resistai.bio>",
            "to": data.to_email,
            "subject": f"ResistAI Report: {data.query[:50]}",
            "html": html
        })
        return {"success": True, "message": "Report sent successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/similar-proteins/{uniprot_id}")
def similar_proteins(uniprot_id: str, n: int = 10):
    """Return the n most similar proteins by ESM-2 embedding cosine similarity."""
    uid = uniprot_id.upper()

    collection = _get_protein_collection()
    if collection is None:
        raise HTTPException(
            status_code=503,
            detail="Protein embeddings not available yet. Run scripts/esm_embeddings.py first.",
        )

    # Fetch the query protein's embedding from the collection
    try:
        result = collection.get(ids=[uid], include=["embeddings"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if result["embeddings"] is None or len(result["embeddings"]) == 0:
        raise HTTPException(status_code=404, detail=f"No embedding found for {uid}")

    query_emb = result["embeddings"][0]

    # Query for n+1 to exclude the protein itself
    hits = collection.query(
        query_embeddings=[query_emb],
        n_results=min(n + 1, collection.count()),
        include=["metadatas", "distances"],
    )

    results = []
    for hit_id, meta, dist in zip(
        hits["ids"][0],
        hits["metadatas"][0],
        hits["distances"][0],
    ):
        if hit_id == uid:
            continue
        # ChromaDB cosine distance → similarity
        similarity = round(1.0 - float(dist), 4)
        score = meta.get("best_score", None)
        tier_label = (
            "high" if score is not None and score >= 0.7
            else "medium" if score is not None and score >= 0.4
            else "low"
        )
        results.append({
            "uniprot_id": hit_id,
            "similarity": similarity,
            "gene":       meta.get("gene", ""),
            "organism":   meta.get("organism", ""),
            "family":     meta.get("family", ""),
            "best_score": score,
            "druggability_tier": tier_label,
        })
        if len(results) >= n:
            break

    return {
        "query_protein": uid,
        "n_results":     len(results),
        "results":       results,
    }


class WelcomeEmail(BaseModel):
    to_email: str
    user_name: str

@app.post("/send-welcome")
def send_welcome(data: WelcomeEmail):
    try:
        import resend
        resend.api_key = os.getenv("RESEND_API_KEY")
        resend.Emails.send({
            "from": "ResistAI <noreply@resistai.bio>",
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


@app.get("/similar-proteins/{uniprot_id}")
def similar_proteins(uniprot_id: str, n: int = 10):
    try:
        import chromadb
        import pandas as pd
        import os

        chroma_path = os.path.join(os.path.dirname(__file__), "data", "chroma_esm")
        parquet_path = os.path.join(os.path.dirname(__file__), "data", "embeddings.parquet")

        client = chromadb.PersistentClient(path=chroma_path)
        collection = client.get_collection("esm_embeddings")

        # Get query embedding
        df = pd.read_parquet(parquet_path)
        row = df[df['uniprot_id'] == uniprot_id.upper()]
        if row.empty:
            raise HTTPException(status_code=404, detail=f"No embedding found for {uniprot_id}")

        feat_cols = [c for c in df.columns if c != 'uniprot_id']
        query_vec = row[feat_cols].values[0].tolist()

        results = collection.query(
            query_embeddings=[query_vec],
            n_results=n + 1
        )

        similar = []
        for i, uid in enumerate(results['ids'][0]):
            if uid == uniprot_id.upper():
                continue
            m = results['metadatas'][0][i]
            dist = results['distances'][0][i]
            similar.append({
                "uniprot_id": uid,
                "gene": m.get("gene", ""),
                "organism": m.get("organism", ""),
                "family": m.get("family", ""),
                "best_score": m.get("best_score", 0),
                "similarity": round(1 - dist, 4)
            })

        return {"query": uniprot_id.upper(), "similar_proteins": similar[:n]}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyse")
def analyse_protein(query: SearchQuery):
    """On-demand analysis for any UniProt ID."""
    import subprocess, tempfile, requests as req, numpy as np
    uid = query.query.strip().upper()

    # 1. Check if already in database
    row = df[df["uniprot_id"] == uid]
    if not row.empty:
        r = row.iloc[0]
        tier = "high" if r["best_score"] >= 0.7 else "medium" if r["best_score"] >= 0.4 else "low"
        return {
            "uniprot_id": uid,
            "source": "database",
            "druggability": {
                "best_score": float(r["best_score"]),
                "tier": tier,
                "total_pockets": int(r["total_pockets"]),
                "high_pockets": int(r["high_druggability"]),
            },
            "message": "Found in pre-computed database."
        }

    # 2. Fetch sequence from UniProt
    fasta_r = req.get(f"https://rest.uniprot.org/uniprotkb/{uid}.fasta", timeout=30)
    if fasta_r.status_code != 200:
        raise HTTPException(status_code=404, detail=f"UniProt ID {uid} not found.")
    fasta = fasta_r.text

    # 3. Try AlphaFold DB
    # Try AlphaFold API to get pdbUrl
    af_api = req.get(f"https://alphafold.ebi.ac.uk/api/prediction/{uid}", timeout=30)
    if af_api.status_code != 200 or not af_api.json():
        raise HTTPException(status_code=422, detail=f"No AlphaFold structure available for {uid}.")
    pdb_url = af_api.json()[0]["pdbUrl"]
    af_r = req.get(pdb_url, timeout=60)
    if af_r.status_code != 200:
        raise HTTPException(status_code=422, detail=f"Failed to download AlphaFold structure for {uid}.")

    return {
        "uniprot_id": uid,
        "source": "on_demand",
        "alphafold_structure": pdb_url,
        "sequence_length": len([l for l in fasta.split("\n") if not l.startswith(">")][0]) if fasta else 0,
        "druggability": None,
        "message": "AlphaFold structure found. fpocket analysis requires local installation — run the ResistAI pipeline locally for full druggability scoring.",
        "links": {
            "alphafold": f"https://alphafold.ebi.ac.uk/entry/{uid}",
            "uniprot": f"https://www.uniprot.org/uniprot/{uid}",
            "literature": f"https://resistai.bio/dashboard/search?q={uid}"
        }
    }


class PredictQuery(BaseModel):
    uniprot_id: str

@app.post("/predict-druggability")
def predict_druggability(query: PredictQuery):
    """Predict druggability tier using ESM-2 + XGBoost classifier."""
    try:
        import pickle
        import numpy as np
        import pandas as pd

        uid = query.uniprot_id.strip().upper()

        # Load model
        model_path = os.path.join(os.path.dirname(__file__), "models", "druggability_classifier.pkl")
        if not os.path.exists(model_path):
            raise HTTPException(status_code=503, detail="Model not available.")

        with open(model_path, "rb") as f:
            payload = pickle.load(f)

        clf = payload["model"]
        le = payload["label_encoder"]
        feature_cols = payload["feature_cols"]

        # Load embeddings
        emb_path = os.path.join(os.path.dirname(__file__), "data", "embeddings.parquet")
        emb_df = pd.read_parquet(emb_path)
        row = emb_df[emb_df["uniprot_id"] == uid]

        if row.empty:
            raise HTTPException(status_code=404, detail=f"No embedding found for {uid}. Run ESM-2 pipeline first.")

        X = row[feature_cols].values.astype("float32")
        y_pred = clf.predict(X)[0]
        y_prob = clf.predict_proba(X)[0]

        tier = le.inverse_transform([y_pred])[0]
        confidence = float(y_prob.max())
        probs = {le.classes_[i]: float(y_prob[i]) for i in range(len(le.classes_))}

        return {
            "uniprot_id": uid,
            "predicted_tier": tier,
            "confidence": round(confidence, 4),
            "probabilities": probs,
            "model": "XGBoost + ESM-2 embeddings",
            "note": "ML prediction — not a substitute for experimental validation."
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
