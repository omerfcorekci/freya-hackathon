"""Readable text of every file in a case folder, with the standard library only.

A bank hands over what it has: PDFs, Word and Excel files, mails, markdown, JSON. The builder's model reads text, so each
file is rendered to `<out_dir>/<relative path>.txt` and an index lists what was found. Formats:
PDF (FlateDecode streams, Tj/TJ strings), docx/xlsx/pptx (zip + XML), eml (headers and text parts), and plain text
formats as they are. Binary files the builder cannot read (audio, images) are listed by name only.
"""
import email, email.policy, json, os, re, zipfile, zlib

TEXT_EXT = {".md", ".txt", ".json", ".csv", ".tsv", ".yaml", ".yml", ".toml", ".js", ".ts", ".py", ".html", ".xml", ".ini", ".cfg", ".sql"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".wrangler"}


def _pdf_string(raw):
    out = []; i = 0
    while i < len(raw):
        c = raw[i:i + 1]
        if c == b"\\" and i + 1 < len(raw):
            n = raw[i + 1:i + 2]
            if n in b"nrtbf": out.append({b"n": "\n", b"r": "", b"t": "\t", b"b": "", b"f": ""}[n]); i += 2; continue
            if n.isdigit():
                m = re.match(rb"[0-7]{1,3}", raw[i + 1:]); out.append(chr(int(m.group(0), 8))); i += 1 + len(m.group(0)); continue
            out.append(n.decode("latin-1")); i += 2; continue
        out.append(c.decode("latin-1")); i += 1
    return "".join(out)


def pdf_text(data):
    """Text of a PDF: every string drawn with Tj/TJ, one line per text block. Good enough for drawings and documents
    with a text layer; a scanned PDF yields nothing."""
    lines = []
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        try: s = zlib.decompress(m.group(1))
        except Exception: s = m.group(1)
        if b"BT" not in s: continue
        for block in re.findall(rb"BT(.*?)ET", s, re.S):
            words = []
            for mm in re.finditer(rb"\((?:\\.|[^\\)])*\)\s*Tj|\[(.*?)\]\s*TJ|<([0-9A-Fa-f]+)>\s*Tj", block, re.S):
                if mm.group(2):
                    try: words.append(bytes.fromhex(mm.group(2).decode()).decode("utf-16-be" if len(mm.group(2)) % 4 == 0 and b"00" in mm.group(2)[:2] else "latin-1"))
                    except Exception: pass
                elif mm.group(1) is not None:
                    parts = re.findall(rb"\((?:\\.|[^\\)])*\)", mm.group(1))
                    words.append("".join(_pdf_string(p[1:-1]) for p in parts))
                else:
                    words.append(_pdf_string(mm.group(0)[1:mm.group(0).rfind(b")")]))
            text = " ".join(w for w in words if w.strip())
            if text.strip(): lines.append(text)
    return "\n".join(lines)


def _xml_text(xml, para_tags=("w:p", "a:p", "row")):
    s = xml.decode("utf-8", "replace")
    for t in para_tags: s = re.sub(r"</%s>" % re.escape(t), "\n", s)
    s = re.sub(r"</(w:tab)>|<w:tab/>", "\t", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'")
    return "\n".join(line.rstrip() for line in s.splitlines() if line.strip())


def office_text(path):
    out = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if "word/document.xml" in names: out.append(_xml_text(z.read("word/document.xml")))
        for n in sorted(x for x in names if re.match(r"ppt/slides/slide\d+\.xml$", x)):
            out.append("--- " + n + "\n" + _xml_text(z.read(n)))
        if "xl/workbook.xml" in names:
            shared = []
            if "xl/sharedStrings.xml" in names:
                for si in re.findall(rb"<si>(.*?)</si>", z.read("xl/sharedStrings.xml"), re.S): shared.append(_xml_text(si, ()).replace("\n", " "))
            for n in sorted(x for x in names if re.match(r"xl/worksheets/sheet\d+\.xml$", x)):
                rows = []
                for row in re.findall(rb"<row[^>]*>(.*?)</row>", z.read(n), re.S):
                    cells = []
                    for c in re.finditer(rb"<c([^>]*)>(.*?)</c>", row, re.S):
                        attrs, inner = c.group(1), c.group(2)
                        v = re.search(rb"<v>(.*?)</v>", inner, re.S); t = re.search(rb'<is>(.*?)</is>', inner, re.S)
                        if t: cells.append(_xml_text(t.group(1), ()).replace("\n", " "))
                        elif v:
                            val = v.group(1).decode("utf-8", "replace")
                            if b't="s"' in attrs:
                                try: val = shared[int(val)]
                                except Exception: pass
                            cells.append(val)
                    if cells: rows.append(" | ".join(cells))
                out.append("--- " + n + "\n" + "\n".join(rows))
    return "\n\n".join(x for x in out if x)


def eml_text(path):
    with open(path, "rb") as f: msg = email.message_from_binary_file(f, policy=email.policy.default)
    head = [f"{h}: {msg.get(h)}" for h in ("From", "To", "Cc", "Date", "Subject") if msg.get(h)]
    body, attachments = [], []
    for part in msg.walk():
        if part.get_content_disposition() == "attachment": attachments.append(part.get_filename() or "attachment"); continue
        if part.get_content_type() == "text/plain":
            try: body.append(part.get_content())
            except Exception: pass
        elif part.get_content_type() == "text/html" and not body:
            try: body.append(re.sub(r"<[^>]+>", " ", part.get_content()))
            except Exception: pass
    return "\n".join(head) + ("\nAttachments: " + ", ".join(attachments) if attachments else "") + "\n\n" + "\n".join(body)


def file_text(path):
    """(kind, text) for one file. kind is 'text', 'pdf', 'office', 'eml' or 'binary'."""
    ext = os.path.splitext(path)[1].lower()
    if ext in TEXT_EXT or ext == "":
        with open(path, "rb") as f: data = f.read()
        return "text", data.decode("utf-8", "replace")
    if ext == ".pdf":
        with open(path, "rb") as f: return "pdf", pdf_text(f.read())
    if ext in (".docx", ".xlsx", ".pptx", ".dotx", ".xlsm"):
        try: return "office", office_text(path)
        except Exception as e: return "binary", f"(could not read {ext}: {e})"
    if ext in (".eml", ".msg"):
        try: return "eml", eml_text(path)
        except Exception as e: return "binary", f"(could not read mail: {e})"
    return "binary", ""


def extract_folder(folder, out_dir):
    """Render every file under `folder` into `out_dir`; returns the index (list of dicts) and writes INDEX.md there."""
    index = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if name.startswith("."): continue
            path = os.path.join(root, name); rel = os.path.relpath(path, folder)
            kind, text = file_text(path)
            entry = {"file": rel, "kind": kind, "bytes": os.path.getsize(path), "chars": len(text), "modified": int(os.path.getmtime(path))}
            if text.strip():
                out_path = os.path.join(out_dir, rel + ".txt"); os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with open(out_path, "w", encoding="utf-8") as f: f.write(text)
                entry["text"] = os.path.relpath(out_path, out_dir)
            index.append(entry)
    os.makedirs(out_dir, exist_ok=True)
    lines = ["# Case folder index", "", f"Source folder: `{os.path.abspath(folder)}`. Rendered text lives next to this file; paths are relative to it.", "",
             "| file | kind | size | text |", "|---|---|---|---|"]
    for e in index:
        lines.append(f"| {e['file']} | {e['kind']} | {e['bytes']} B | {e.get('text') or '(no text: ' + e['kind'] + ')'} |")
    with open(os.path.join(out_dir, "INDEX.md"), "w", encoding="utf-8") as f: f.write("\n".join(lines) + "\n")
    return index


if __name__ == "__main__":
    import sys
    idx = extract_folder(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "out/case-text")
    print(json.dumps(idx, indent=1, ensure_ascii=False))
