# ResistAI API

REST API and CLI for the [ResistAI](https://github.com/kagansaglam/resistai) antibiotic resistance research platform.

**Live API:** [resistai-api.onrender.com](https://resistai-api.onrender.com)
**Interactive docs:** [resistai-api.onrender.com/docs](https://resistai-api.onrender.com/docs)
**Deploy:** Render

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/stats` | Platform statistics (total proteins, tiers, best score) |
| `GET` | `/proteins` | List proteins — filter by `tier`, `family`, `limit` |
| `GET` | `/proteins/{uniprot_id}` | Protein details + binding pockets |
| `POST` | `/search` | Semantic literature search (RAG over 2,508 PubMed articles) |
| `POST` | `/ask` | AI research assistant (Llama 3.3 70B via Groq) |
| `POST` | `/send-welcome` | Send welcome email via Resend |
| `POST` | `/send-report` | Send druggability report email |
| `GET` | `/similar-proteins/{uniprot_id}` | ESM-2 embedding similarity search |

---

## Quick Start

```bash
git clone https://github.com/kagansaglam/resistai-api.git
cd resistai-api
pip install -r requirements.txt
uvicorn main:app --port 8000
```

Open [http://localhost:8000/docs](http://localhost:8000/docs) for interactive Swagger UI.

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
  "best_score": 1.0,
  "pubmed_articles": 2508
}

# GET /proteins/Q5U7L7
{
  "uniprot_id": "Q5U7L7",
  "gene": "VIM-2",
  "organism": "Pseudomonas aeruginosa",
  "family": "Beta-lactamase",
  "druggability": {
    "best_score": 0.535,
    "tier": "medium",
    "total_pockets": 15
  }
}

# POST /search
{"query": "KPC carbapenemase inhibitor", "n_results": 5}

# POST /ask
{"question": "Which efflux pumps have the highest druggability scores?"}

# GET /similar-proteins/Q5U7L7
[
  {"uniprot_id": "P00811", "gene": "AmpC", "similarity": 0.94},
  ...
]
```

---

## License

MIT
