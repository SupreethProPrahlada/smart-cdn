#!/usr/bin/env python3
"""Highlight srv1's shared switch-to-server link on the route map."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent
page = ROOT / "tools" / "route_map.html"
text = page.read_text(encoding="utf-8")


def replace_once(old, new, label):
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"Expected one section for {label}; found {count}. No files changed.")
    text = text.replace(old, new, 1)


replace_once(
    '        <path id="line-srv1-backup" class="route" d="M330 310 L455 490 L590 310"/>\n',
    '        <path id="line-srv1-backup" class="route" d="M330 310 L455 490 L590 310"/>\n'
    '        <path id="line-srv1-access" class="route" d="M650 310 L900 310"/>\n',
    "shared srv1 access overlay",
)
replace_once(
    "    const cards = document.getElementById('cards'); cards.replaceChildren();\n",
    "    const accessLine = document.getElementById('line-srv1-access');\n"
    "    const lastChoice = displayData.last_route;\n"
    "    const srv1Route = routes.find(route => route.name ===\n"
    "      (lastChoice && lastChoice.server === 'srv1' ? lastChoice.route : 'srv1-direct'))\n"
    "      || routes.find(route => route.server === 'srv1');\n"
    "    if (srv1Route) {\n"
    "      accessLine.style.stroke = colorFor(srv1Route);\n"
    "      if (lastChoice && lastChoice.server === 'srv1') accessLine.classList.add('selected');\n"
    "    }\n"
    "    const cards = document.getElementById('cards'); cards.replaceChildren();\n",
    "shared srv1 access coloring",
)

page.write_text(text, encoding="utf-8")
print("The s2-to-srv1 server-access link will now follow srv1 route colors and selection.")
