import argparse, os, json, time
from pipeline import run_pipeline
from export import save_markdown, save_pdf_from_markdown
from config import DEFAULT_TOPK
from provenance import log_event

def parse_args():
    ap = argparse.ArgumentParser(description="OSINT multi-agent report generator")
    ap.add_argument("--query", required=True)
    ap.add_argument("--out", default="report.md")
    ap.add_argument("--pdf", default=None)
    ap.add_argument("--topk", type=int, default=DEFAULT_TOPK)
    return ap.parse_args()

def main():
    args = parse_args()
    t0 = time.time()
    log_event("run_start", {"query": args.query, "topk": args.topk})
    md, extra = run_pipeline(args.query, topk=args.topk)
    save_markdown(md, args.out)
    if args.pdf:
        try:
            save_pdf_from_markdown(md, args.pdf)
        except Exception as e:
            print(f"[WARN] PDF fallito: {e}")
    t1 = time.time()
    log_event("run_end", {"secs": round(t1-t0,1), "out": args.out, "pdf": bool(args.pdf)})
    print(f"OK → {args.out} ({round(t1-t0,1)}s)")
    # opzionale: salva diagnostic
    with open("last_run_debug.json","w",encoding="utf-8") as f:
        json.dump(extra, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
