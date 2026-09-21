from pathlib import Path
import html
import re


def inline(value):
    value = html.escape(value)
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    value = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", value)
    return value


def render(source):
    blocks = []
    paragraph = []
    listing = None

    def flush():
        if paragraph:
            blocks.append("<p>" + inline(" ".join(paragraph)) + "</p>")
            paragraph.clear()

    for line in source.splitlines() + [""]:
        heading = re.match(r"^(#{1,3}) (.+)$", line)
        item = re.match(r"^(?:- |\d+\. )(.+)$", line)
        if not line or heading or item:
            flush()
        if listing and (not line or heading):
            blocks.append(f"</{listing}>")
            listing = None
        if heading:
            level = len(heading[1])
            anchor = re.sub(r"[^a-z0-9 -]", "", heading[2].lower()).replace(" ", "-")
            blocks.append(f'<h{level} id="{anchor}">{inline(heading[2])}</h{level}>')
        elif item:
            kind = "ul" if line.startswith("- ") else "ol"
            if listing != kind:
                if listing:
                    blocks.append(f"</{listing}>")
                blocks.append(f"<{kind}>")
                listing = kind
            blocks.append("<li>" + inline(item[1]) + "</li>")
        elif line:
            if listing and line.startswith("  ") and blocks[-1].endswith("</li>"):
                blocks[-1] = blocks[-1][:-5] + " " + inline(line.strip()) + "</li>"
            else:
                paragraph.append(line.strip())
    return "\n".join(blocks)


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    source = here.parents[2] / "doc/easymesh/guide/wmediumd-console-ng.md"
    target = here / "web/ng/manual.html"
    target.write_text(
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>wmediumd console ng manual</title><link rel="stylesheet" href="/ng/style.css">'
        '</head><body><article class="manual"><nav><a href="/">← Console NG</a>'
        '<a href="#channel-utilization-and-bss-load">Load metrics</a>'
        '<a href="#a-20-client-room-in-a-100-client-lab">Excluded clients</a>'
        '<a href="#freshness-cost-and-exports">Freshness and cost</a></nav>'
        + render(source.read_text()) + '</article></body></html>\n'
    )
