# ResistAI API

REST API and CLI for the [ResistAI](https://github.com/kagansaglam/resistai) antibiotic resistance research platform.

## Endpoints
GET  /stats                        Platform statistics
GET  /proteins                     List proteins (filter by tier, family)
GET  /proteins/{uniprot_id}        Protein details + binding pockets
POST /search                       Semantic literature search
## Quick Start

```bash
git clone https://github.com/kagansaglam/resistai-api.git
cd resistai-api
pip install fastapi uvicorn pandas chromadb sentence-transformers groq requests
uvicorn main:app --port 8000
```

## CLI

```bash
python predict.py --stats
python predict.py --protein Q5U7L7
python predict.py --list --tier high --limit 10
python predict.py --search "VIM-2 metallo-beta-lactamase inhibitor"
python predict.py --protein Q5U7L7 --json
```

## Example Responses

```bash
# GET /proteins/Q5U7L7
{
  "uniprot_id": "Q5U7L7",
  "gene": "VIM-2",
  "organism": "Escherichia coli",
  "family": "Beta-lactamase",
  "druggability": {
    "best_score": 0.535,
    "tier": "medium",
    "total_pockets": 15
  }
}

# GET /stats
{
  "total_proteins": 144,
  "high_druggability": 48,
  "best_score": 0.983
}
```

## API Docs

Interactive docs available at `http://localhost:8000/docs`

## License

MIT
