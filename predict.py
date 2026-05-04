#!/usr/bin/env python3
"""
ResistAI CLI
Usage:
  python predict.py --protein Q5U7L7
  python predict.py --search "VIM-2 inhibitor"
  python predict.py --list --tier high --limit 10
  python predict.py --stats
"""
import argparse
import requests
import json
import sys

API_URL = "http://localhost:8000"
def print_protein(data):
    d = data["druggability"]
    tier_icon = {"high": "[HIGH]", "medium": "[MED]", "low": "[LOW]"}.get(d["tier"], "[ ? ]")
    print(f"\n{'='*55}")
    print(f"  {data['gene']} ({data['uniprot_id']}) — {data['organism']}")
    print(f"  Family   : {data['family']}")
    print(f"  Score    : {d['best_score']:.3f}  {tier_icon}")
    print(f"  Pockets  : {d['total_pockets']} total | {d['high_pockets']} high | {d['medium_pockets']} medium")
    if data.get("top_pockets"):
        print(f"\n  Top pocket:")
        p = data["top_pockets"][0]
        print(f"    Pocket #{p['pocket_id']}  score={p['druggability_score']:.3f}  volume={p['volume_A3']:.1f} A3")
    print(f"{'='*55}\n")
def main():
    parser = argparse.ArgumentParser(description="ResistAI CLI — Antibiotic Resistance Druggability Analysis")
    parser.add_argument("--protein", help="UniProt ID (e.g. Q5U7L7)")
    parser.add_argument("--search", help="Literature search query")
    parser.add_argument("--list", action="store_true", help="List proteins")
    parser.add_argument("--tier", choices=["high","medium","low"], help="Filter by druggability tier")
    parser.add_argument("--family", help="Filter by resistance family")
    parser.add_argument("--limit", type=int, default=10, help="Number of results")
    parser.add_argument("--stats", action="store_true", help="Show platform statistics")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    args = parser.parse_args()
    if args.stats:
        r = requests.get(f"{API_URL}/stats")
        data = r.json()
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(f"\nResistAI Platform Statistics")
            print(f"{'='*35}")
            print(f"  Total proteins   : {data['total_proteins']}")
            print(f"  High druggability: {data['high_druggability']}")
            print(f"  Medium           : {data['medium_druggability']}")
            print(f"  Low              : {data['low_druggability']}")
            print(f"  Best score       : {data['best_score']:.3f}")
            print(f"\n  Families:")
            for fam, count in sorted(data["families"].items(), key=lambda x: -x[1]):
                print(f"    {fam:<20} {count}")
        return
    if args.protein:
        r = requests.get(f"{API_URL}/proteins/{args.protein}")
        if r.status_code == 404:
            print(f"Protein {args.protein} not found.")
            sys.exit(1)
        data = r.json()
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print_protein(data)
        return
    if args.search:
        r = requests.post(f"{API_URL}/search", json={"query": args.search, "n_results": args.limit})
        data = r.json()
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(f"\nSearch: {args.search}")
            print(f"{'='*55}")
            for a in data["results"]:
                print(f"  [{a['relevance_score']:.3f}] ({a['year']}) {a['title'][:70]}")
                print(f"           PMID:{a['pmid']} — {a['journal']}")
                print()
        return
    if args.list:
        params = {"limit": args.limit}
        if args.tier:
            params["tier"] = args.tier
        if args.family:
            params["family"] = args.family
        r = requests.get(f"{API_URL}/proteins", params=params)
        data = r.json()
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print(f"\n{'UniProt':<12} {'Gene':<15} {'Organism':<30} {'Score':>6} {'Family'}")
            print("-"*80)
            for p in data:
                org = p["organism"][:28] + ".." if len(p["organism"]) > 30 else p["organism"]
                print(f"  {p['uniprot_id']:<10} {p['gene']:<15} {org:<30} {p['best_score']:>6.3f}  {p['family']}")
        return
    parser.print_help()

if __name__ == "__main__":
    main()
