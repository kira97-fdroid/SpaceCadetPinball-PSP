from pathlib import Path
import re

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

def load_template(name):
    return (TEMPLATE_DIR / name).read_text(encoding="utf-8")

def read(path):
    return path.read_text(encoding="utf-8")


def write(path, text):
    path.write_text(text, encoding="utf-8")


def replace_once(path, old, new, label):
    s = read(path)
    if new in s:
        print(f"[skip] {label}")
        return
    n = s.count(old)
    if n != 1:
        raise RuntimeError(f"{path}: anchor mismatch for {label}: expected 1, found {n}")
    write(path, s.replace(old, new, 1))
    print(f"[ok]   {label}")


def regex_replace_once(path, pattern, repl, label, flags=0):
    s = read(path)
    if repl in s:
        print(f"[skip] {label}")
        return
    matches = list(re.finditer(pattern, s, flags))
    if len(matches) != 1:
        raise RuntimeError(f"{path}: regex anchor mismatch for {label}: expected 1, found {len(matches)}")
    m = matches[0]
    write(path, s[:m.start()] + repl + s[m.end():])
    print(f"[ok]   {label}")


def insert_after_once(path, anchor, addition, label):
    s = read(path)
    if addition in s:
        print(f"[skip] {label}")
        return
    n = s.count(anchor)
    if n != 1:
        raise RuntimeError(f"{path}: anchor mismatch for {label}: expected 1, found {n}")
    write(path, s.replace(anchor, anchor + addition, 1))
    print(f"[ok]   {label}")


def find_matching_brace(text, open_pos):
    """Return the closing brace matching text[open_pos] in C/C++ source.

    Braces inside comments, quoted literals and raw string literals are ignored.
    This is intentionally lexical rather than whitespace/anchor based so the PSP
    patch remains stable after earlier generated code has been inserted.
    """
    if open_pos < 0 or open_pos >= len(text) or text[open_pos] != "{":
        raise RuntimeError("invalid opening brace position")

    depth = 0
    i = open_pos
    n = len(text)
    state = "code"  # code, line_comment, block_comment, string, char, raw
    escape = False
    raw_end = ""

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        if state == "line_comment":
            if ch == "\n":
                state = "code"
            i += 1
            continue

        if state == "block_comment":
            if ch == "*" and nxt == "/":
                state = "code"
                i += 2
            else:
                i += 1
            continue

        if state in ("string", "char"):
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif (state == "string" and ch == '"') or (state == "char" and ch == "'"):
                state = "code"
            i += 1
            continue

        if state == "raw":
            if raw_end and text.startswith(raw_end, i):
                i += len(raw_end)
                state = "code"
                raw_end = ""
            else:
                i += 1
            continue

        # code
        if ch == "/" and nxt == "/":
            state = "line_comment"
            i += 2
            continue
        if ch == "/" and nxt == "*":
            state = "block_comment"
            i += 2
            continue

        # C++ raw string: R"delimiter(... )delimiter"
        if ch == "R" and nxt == '"':
            delim_start = i + 2
            paren = text.find("(", delim_start, min(n, delim_start + 18))
            if paren != -1:
                delimiter = text[delim_start:paren]
                # Delimiter may be empty; reject characters forbidden by C++.
                if all(c not in " ()\\\t\r\n" for c in delimiter):
                    raw_end = ")" + delimiter + '"'
                    state = "raw"
                    i = paren + 1
                    continue

        if ch == '"':
            state = "string"
            escape = False
        elif ch == "'":
            state = "char"
            escape = False
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
            if depth < 0:
                raise RuntimeError("brace depth became negative")
        i += 1

    raise RuntimeError("matching closing brace not found")


