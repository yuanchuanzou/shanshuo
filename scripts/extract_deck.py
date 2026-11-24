#!/usr/bin/env python3
"""Extract slide order, text, speaker notes and every image from a .pptx.

Slide <-> notes and slide <-> media are resolved through relationship parts,
never by matching part numbers (see hermes powerpoint skill: part numbering is
independent of display order and silently mixes notes between slides).

Output: data/slides.json

  {"deck": path, "slide_count": N, "slides": [
     {"index": 1, "part": "ppt/slides/slide12.xml", "page_label": "107/132",
      "title": "...", "texts": ["..."], "notes": "...",
      "images": [{"media": "ppt/media/image119.png", "rel": "rId3",
                  "exported": "media/s001_rId3_image119.png"}]}]}
"""
import json
import posixpath
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "p": "http://schemas.openxmlformats.org/presentationml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def rels_for(z, part):
    """Return {rId: (Type, absolute Target)} for a part."""
    d, f = posixpath.split(part)
    rp = posixpath.join(d, "_rels", f + ".rels")
    if rp not in z.namelist():
        return {}
    root = ET.fromstring(z.read(rp))
    out = {}
    for rel in root.findall("pr:Relationship", NS):
        tgt = rel.get("Target")
        if rel.get("TargetMode") == "External":
            continue
        out[rel.get("Id")] = (
            rel.get("Type", "").rsplit("/", 1)[-1],
            posixpath.normpath(posixpath.join(d, tgt)),
        )
    return out


def slide_order(z):
    pres = "ppt/presentation.xml"
    rels = rels_for(z, pres)
    root = ET.fromstring(z.read(pres))
    out = []
    for sld in root.find("p:sldIdLst", NS).findall("p:sldId", NS):
        rid = sld.get("{%s}id" % NS["r"])
        if rid in rels:
            out.append(rels[rid][1])
    return out


def texts_of(root):
    out = []
    for sp in root.iter("{%s}sp" % NS["p"]):
        buf = []
        for para in sp.iter("{%s}p" % NS["a"]):
            line = "".join(t.text or "" for t in para.iter("{%s}t" % NS["a"]))
            if line.strip():
                buf.append(line.strip())
        if buf:
            out.append("\n".join(buf))
    for tbl in root.iter("{%s}tbl" % NS["p"]):
        for tr in tbl.iter("{%s}tr" % NS["a"]):
            cells = [
                "".join(t.text or "" for t in tc.iter("{%s}t" % NS["a"])).strip()
                for tc in tr.iter("{%s}tc" % NS["a"])
            ]
            if any(cells):
                out.append(" | ".join(cells))
    return out


def main(deck, outdir):
    deck = Path(deck)
    outdir = Path(outdir)
    (outdir / "media").mkdir(parents=True, exist_ok=True)
    z = zipfile.ZipFile(deck)
    slides = []
    for i, part in enumerate(slide_order(z), 1):
        root = ET.fromstring(z.read(part))
        rels = rels_for(z, part)
        notes = ""
        for rid, (kind, target) in rels.items():
            if kind == "notesSlide" and target in z.namelist():
                notes = "\n".join(texts_of(ET.fromstring(z.read(target))))
        images = []
        for rid, (kind, target) in rels.items():
            if kind == "image" and target in z.namelist():
                ext = posixpath.splitext(target)[1]
                name = f"s{i:03d}_{rid}{ext}"
                (outdir / "media" / name).write_bytes(z.read(target))
                images.append({"media": target, "rel": rid, "exported": f"media/{name}"})
        texts = texts_of(root)
        title = texts[0] if texts else ""
        m = re.search(r"(\d+\s*/\s*\d+)", "\n".join(texts))
        slides.append({
            "index": i, "part": part, "page_label": m.group(1) if m else "",
            "title": title.replace("\n", " ")[:200], "texts": texts,
            "notes": notes, "images": images,
        })
    data = {"deck": str(deck), "slide_count": len(slides), "slides": slides}
    (outdir / "slides.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
    nimg = sum(len(s["images"]) for s in slides)
    nnotes = sum(1 for s in slides if s["notes"].strip())
    print(f"slides={len(slides)} images={nimg} notes={nnotes} -> {outdir/'slides.json'}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "data")
