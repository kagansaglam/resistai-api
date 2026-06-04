# ResistAI API

REST API and CLI for the [ResistAI](https://github.com/kagansaglam/resistai) antibiotic resistance research platform.

**Live API:** [resistai-api.onrender.com](https://resistai-api.onrender.com)
**Interactive docs:** [resistai-api.onrender.com/docs](https://resistai-api.onrender.com/docs)
**Deploy:** Render (Docker, with fpocket installed in the image)

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/stats` | Platform statistics (total proteins, tiers, best score) |
| `GET` | `/proteins` | List proteins — filter by `tier`, `family`, `limit` |
| `GET` | `/proteins/{uniprot_id}` | Protein details + binding pockets |
| `GET` | `/similar-proteins/{uniprot_id}` | ESM-2 embedding cosine-similarity search |
| `POST` | `/predict-druggability` | ML druggability tier prediction (XGBoost + ESM-2 embeddings) |
| `POST` | `/analyse` | On-demand analysis for any UniProt ID — **runs fpocket live** on the AlphaFold structure |
| `POST` | `/search` | Semantic literature search (RAG over 2,508 PubMed articles) |
| `POST` | `/ask` | AI research assistant (Llama 3.3 70B via Groq) |
| `POST` | `/send-report` | Send druggability report email (Resend) |
| `POST` | `/send-welcome` | Send welcome email (Resend) |

---

## On-Demand fpocket Analysis

`POST /analyse` is the platform's signature capability. For a UniProt ID **not** in the pre-computed database, it:

1. Fetches the sequence from UniProt
2. Retrieves the AlphaFold structure (via the prediction API)
3. Runs **fpocket live** on the structure to detect and rank binding pockets
4. Returns a druggability score, tier, and top pockets in real time

fpocket is installed in the **Docker image** (via conda-forge), so no local install or pipeline run is required. Proteins already in the database short-circuit to their pre-computed scores. Sequences over 1,500 residues are skipped to stay within container memory limits.

```bash
# On-demand example (protein not in the database)
curl -X POST https://resistai-api.onrender.com/analyse \
  -H "Content-Type: application/json" \
  -d '{"query": "P0A7G6"}'
```

---

## Quick Start (local)

```bash
git clone https://github.com/kagansaglam/resistai-api.git
cd resistai-api
pip install -r requirements.txt
# fpocket required on PATH for /analyse (conda-forge: `conda install -c conda-forge fpocket`)
uvicorn main:app --port 8000
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) for interactive Swagger UI.

### Docker (matches production)

```bash
docker build -t resistai-api .
docker run -p 8000:8000 --env-file .env resistai-api
```

The Dockerfile installs fpocket from conda-forge alongside the Python dependencies, so `/analyse` works out of the box.

---

## CLI

```bash
python predict.py --stats
python predict.py --protein Q5U7L7
python predict.py --list --tier high --limit 10
python predict.py --search "VIM-2 metallo-beta-lactamase inhibitor"
python predict.py --protein Q5U7L7 --json
```

---

## Example Responses

```bash
# GET /stats
{
  "total_proteins": 2433,
  "high_druggability": 1198,
  "medium_druggability": 717,
  "best_score": 1.0
}

# GET /proteins/Q5U7L7
{
  "uniprot_id": "Q5U7L7",
  "gene": "VIM-2",
  "organism": "Pseudomonas aeruginosa",
  "family": "Beta-lactamase",
  "druggability": { "best_score": 0.535, "tier": "medium", "total_pockets": 15 }
}

# POST /analyse  {"query": "P0A7G6"}  (on-demand, not in database)
{
  "uniprot_id": "P0A7G6",
  "source": "on_demand",
  "druggability": { "best_score": 0.341, "tier": "low", "total_pockets": 23, "high_pockets": 0 },
  "top_pockets": [ ... ],
  "message": "Computed on-demand by fpocket on the AlphaFold structure."
}

# POST /predict-druggability  {"uniprot_id": "Q840P9"}
{
  "uniprot_id": "Q840P9",
  "predicted_tier": "high",
  "confidence": 0.94,
  "model": "XGBoost + ESM-2 embeddings"
}

# GET /similar-proteins/Q5U7L7
{ "results": [ {"uniprot_id": "...", "gene": "...", "similarity": 0.98}, ... ] }
```

---

## Related Repositories

| Repo | Description |
|---|---|
| [resistai](https://github.com/kagansaglam/resistai) | Pipeline (Nextflow, ESM-2, fpocket, XGBoost) |
| [resistai-web](https://github.com/kagansaglam/resistai-web) | Next.js frontend — [resistai.bio](https://resistai.bio) |

---

## License

MIT
