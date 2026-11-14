import sys, re, subprocess, time
for path in sys.argv[1:]:
    t0 = time.time()
    out = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True).stdout.decode("utf-8", "replace")
    dt = time.time() - t0
    pages = out.split("\f")
    chars = [len(p.strip()) for p in pages]
    print(f"== {path.split('/')[-1]}: pdftotext {dt:.1f}s pages={len(pages)} chars={sum(chars):,} ~tokens={sum(chars)//4:,} near-empty pages={sum(1 for c in chars if c < 40)} median chars/page={sorted(chars)[len(chars)//2]}")
    for i in (0, 3):
        if i < len(pages):
            body = [re.sub(r"\s+", " ", l).strip() for l in pages[i].splitlines() if l.strip()]
            print(f"  --- page {i+1} ({len(body)} lines) ---")
            for l in body[:7]: print("    ", l[:140])
