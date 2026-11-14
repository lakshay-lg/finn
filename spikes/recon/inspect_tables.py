import sys, re, html
def clean(s): return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()
for path in sys.argv[1:]:
    t = open(path, encoding="utf-8", errors="replace").read()
    print("=" * 6, path.split("/")[-1])
    top = re.search(r'<ul id="top-ratios">.*?</ul>', t, re.S)
    if top:
        print("top ratios:", [clean(li)[:60] for li in re.findall(r"<li.*?</li>", top.group(0), re.S)])
    for sid in ["quarters", "profit-loss", "balance-sheet", "cash-flow", "ratios"]:
        m = re.search(r'<section[^>]*\bid="%s".*?</section>' % sid, t, re.S)
        if not m: print(f"[{sid}] MISSING"); continue
        tb = re.search(r"<table.*?</table>", m.group(0), re.S)
        if not tb: print(f"[{sid}] no table"); continue
        rows = [[clean(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", r, re.S)] for r in re.findall(r"<tr.*?</tr>", tb.group(0), re.S)]
        hdr = rows[0]
        print(f"[{sid}] periods={len(hdr)-1} first={hdr[1] if len(hdr)>1 else None} last={hdr[-1]} rows={len(rows)-1}")
        for r in rows[1:]:
            print(f"     {r[0][:28]:28s} last3={r[-3:]}")
