"""Cut a small, shareable fixture out of an HOI4 text save (SR0).

The fixture is itself a valid mini-save holding one country:
  - the header (plain key=value lines and the small blocks before the big sections), with player names redacted;
  - countries={ TAG={...} };
  - the top-level equipments created by TAG, division_templates of TAG, and states owned by TAG.

Usage:
    python tools/cut_save_fixture.py <text save> <TAG> <output file>

Standard library only. It refuses binary saves and anything over --max-bytes (default 1,000,000).
"""
import argparse
import re
import sys

REDACT = re.compile(rb'(\n\s*(?:user|player_name|name_of_player|steam_id|pdx_id|account)\s*=\s*)"[^"]*"')


def block_end(buf, j):
    """buf[j] is just after an opening '{'; return the index just after its matching '}'."""
    depth, k, in_str = 1, j, False
    n = len(buf)
    while depth and k < n:
        c = buf[k]
        if in_str:
            in_str = c != 0x22
        elif c == 0x22:
            in_str = True
        elif c == 0x7B:
            depth += 1
        elif c == 0x7D:
            depth -= 1
        k += 1
    if depth:
        raise ValueError("unbalanced braces")
    return k


def top_blocks(buf, indent=b""):
    """(key, line_start, inner_start, end) for each `key={` at the given indentation."""
    pat = re.compile(rb"\n" + re.escape(indent) + rb"([^\s=\t{}]+)=\{")
    pos, out = 0, []
    while True:
        m = pat.search(buf, pos)
        if not m:
            return out
        end = block_end(buf, m.end())
        out.append((m.group(1).decode(errors="replace"), m.start() + 1, m.end(), end))
        pos = end


def children(buf, start, end, indent):
    """Child blocks `name={` of the block buf[start:end] at the given indentation."""
    pat = re.compile(rb"\n" + re.escape(indent) + rb"([^\s=\t{}]+)=\{")
    pos, out = start, []
    while True:
        m = pat.search(buf, pos, end)
        if not m:
            return out
        stop = block_end(buf, m.end())
        out.append((m.group(1).decode(errors="replace"), m.start() + 1, m.end(), stop))
        pos = stop


def cut(data, tag):
    if not data.startswith(b"HOI4txt"):
        raise SystemExit("not a text save (does not start with HOI4txt): set save_as_binary=no, see docs/queue/SR0.md")
    tops = top_blocks(data)
    big = [t for t in tops if t[3] - t[1] > 10_000]
    header_end = big[0][1] if big else len(data)
    header = REDACT.sub(rb'\1"REDACTED"', data[:header_end]).rstrip() + b"\n"

    by_key = {}
    for key, ls, inner, end in tops:
        by_key.setdefault(key, (ls, inner, end))

    parts = [header]
    if "countries" in by_key:
        _, inner, end = by_key["countries"]
        for name, ls, cinner, cend in children(data, inner, end, b"\t"):
            if name == tag:
                parts.append(b"countries={\n" + data[ls:cend] + b"\n}\n")
                break
        else:
            raise SystemExit(f"country {tag} not found")

    q = b'"' + tag.encode() + b'"'
    filters = {
        "equipments": rb"\n\t\tcreator=" + re.escape(q),
        "division_templates": rb"\n\t\tcountry=" + re.escape(q),
        "states": rb"\n\t\towner=" + re.escape(q),
    }
    for section, needle in filters.items():
        if section not in by_key:
            continue
        _, inner, end = by_key[section]
        kept = [data[ls:cend] for _, ls, cinner, cend in children(data, inner, end, b"\t")
                if re.search(needle, data[ls:cend])]
        parts.append(section.encode() + b"={\n" + b"\n".join(kept) + b"\n}\n")
    return b"".join(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("save")
    ap.add_argument("tag")
    ap.add_argument("out")
    ap.add_argument("--max-bytes", type=int, default=1_000_000)
    args = ap.parse_args()
    data = open(args.save, "rb").read()
    fixture = cut(data, args.tag)
    if len(fixture) > args.max_bytes:
        raise SystemExit(f"fixture is {len(fixture):,} bytes, over --max-bytes {args.max_bytes:,}")
    leftover = REDACT.findall(fixture)
    if any(not v.endswith(b"=") for v in leftover):
        raise SystemExit("a player-name field survived redaction")
    with open(args.out, "wb") as f:
        f.write(fixture)
    print(f"wrote {args.out}: {len(fixture):,} bytes from a {len(data):,}-byte save")


if __name__ == "__main__":
    sys.exit(main())
