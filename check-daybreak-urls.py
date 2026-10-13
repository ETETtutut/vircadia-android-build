import json
import subprocess
from pathlib import Path
from urllib.parse import urlparse, unquote

root = Path("/storage/emulated/0/GLB/vircadia-content-master/Bazaar/Worlds/Daybreak")
data = json.loads((root / "models.json").read_text())
urls = sorted({
    e.get("modelURL", "").split("?")[0]
    for e in data.get("Entities", [])
    if e.get("modelURL", "").startswith("http")
})

missing = []
for url in urls:
    path = unquote(urlparse(url).path)
    if "/content/" in path:
        local = root / "content" / path.split("/content/", 1)[1]
    else:
        local = root / path.lstrip("/")
    if not local.is_file():
        missing.append(url)

print("Checking", len(missing), "external URLs")
for i, url in enumerate(missing, 1):
    print(f"\n[{i}/{len(missing)}] {url}")
    try:
        result = subprocess.run(
            ["curl", "-sS", "-L", "-I", "--max-time", "12",
             "-o", "/dev/null", "-w",
             "HTTP=%{http_code} | Type=%{content_type} | Size=%{size_download}",
             url],
            capture_output=True, text=True, timeout=15
        )
        print(result.stdout.strip() or result.stderr.strip() or "No response")
    except Exception as e:
        print("CHECK ERROR:", e)
