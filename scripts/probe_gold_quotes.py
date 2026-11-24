"""Probe public gold quote sources from GitHub Actions (no trading, no credentials)."""
import json
from pathlib import Path
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

REPO = "zhou2533/GoldAccumulationRealTimeMonitor"
HEADERS = {"User-Agent": "AutoTrader-QuoteProbe/0.1", "Accept": "application/vnd.github+json"}
TARGET_BANKS = ["兴业", "浙商", "民生", "广发"]

def fetch(url, *, timeout=15, method="GET", data=None, headers=None):
    start = time.monotonic()
    req = urllib.request.Request(url, data=data, method=method, headers={**HEADERS, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            body = res.read(300000)
            return {"status": res.status, "elapsed_ms": round((time.monotonic()-start)*1000), "body": body.decode("utf-8", "replace"), "content_type": res.headers.get("Content-Type", "")}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "elapsed_ms": round((time.monotonic()-start)*1000), "error": str(exc)}
    except Exception as exc:
        return {"status": None, "elapsed_ms": round((time.monotonic()-start)*1000), "error": str(exc)[:200]}

def main():
    output = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "source_repo": REPO, "banks": TARGET_BANKS, "checks": []}
    local = Path(os.environ.get("UPSTREAM_SOURCE_DIR", "upstream-gold-monitor"))
    local_files = sorted(p for p in local.rglob("*") if p.is_file() and p.suffix.lower() in (".js", ".ts") and ".git" not in p.parts)[:30]
    meta = {} if local_files else fetch(f"https://api.github.com/repos/{REPO}")
    default_branch = "main"
    if meta.get("status") == 200:
        default_branch = json.loads(meta["body"]).get("default_branch", "main")
    output["upstream_default_branch"] = default_branch
    api = {} if local_files else fetch(f"https://api.github.com/repos/{REPO}/git/trees/{default_branch}?recursive=1")
    files = []
    if api.get("status") == 200:
        try:
            files = [x["path"] for x in json.loads(api["body"]).get("tree", []) if x.get("type")=="blob" and x["path"].lower().endswith((".js",".user.js",".ts"))][:30]
        except Exception as exc:
            output["tree_parse_error"] = str(exc)
    output["source_tree_status"] = api.get("status")
    output["source_tree_error"] = api.get("error")
    if not files:
        output["warning"] = "No upstream JavaScript source files discovered; this is not a successful endpoint verification"
    if local_files:
        files = [str(p.relative_to(local)) for p in local_files]
        output["source_mode"] = "local checkout"
        output.pop("warning", None)
    output["source_files"] = files
    endpoints = {}
    for path in files:
        raw = "https://raw.githubusercontent.com/" + REPO + "/" + default_branch + "/" + urllib.parse.quote(path)
        src = {"status": 200, "body": (local / path).read_text(encoding="utf-8", errors="replace")} if local_files else fetch(raw)
        if src.get("status") != 200:
            continue
        for url in re.findall(r'https?://[^\s\x22\x27\x60<>\\]+', src["body"]):
            url = url.rstrip("),;}")
            parsed = urllib.parse.urlparse(url)
            if parsed.hostname and any(x in parsed.hostname for x in ("github.com", "githubusercontent.com", "google.com", "baidu.com", "jsdelivr.net")):
                continue
            if parsed.hostname and not any(x in parsed.hostname for x in ("example.com", "localhost")):
                endpoints.setdefault(url, path)
    output["discovered_endpoints"] = [{"url":u,"source_file":p} for u,p in list(endpoints.items())[:30]]
    # Probe only HTTPS endpoints, never POST unknown endpoints or follow credentialed flows.
    for url, path in list(endpoints.items())[:12]:
        if not url.startswith("https://"):
            continue
        result = fetch(url, timeout=12)
        body = result.pop("body", "")
        output["checks"].append({"source":path,"url":url,"http_status":result.get("status"),"elapsed_ms":result["elapsed_ms"],"content_type":result.get("content_type"),"error":result.get("error"),"sample":body[:350]})
        time.sleep(0.6)
    os.makedirs("artifacts", exist_ok=True)
    with open("artifacts/gold_quote_probe.json","w",encoding="utf-8") as f:
        json.dump(output,f,ensure_ascii=False,indent=2)
    print(json.dumps({k:v for k,v in output.items() if k != "discovered_endpoints"},ensure_ascii=False,indent=2))
    print("NOTE: HTTP 200 does not establish that quotes are live, two-sided, or executable.")
    if not files:
        raise SystemExit("Probe inconclusive: upstream source files not discovered")
    if not output["checks"]:
        raise SystemExit("Probe inconclusive: no eligible HTTPS endpoints tested")

if __name__ == "__main__":
    main()
