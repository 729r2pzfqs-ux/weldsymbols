#!/usr/bin/env python3
"""Static site generator for weldsymbols.org.

Reads the JSON files in data/, renders the Jinja2 templates in templates/, and
writes a complete static site to dist/ — including sitemap.xml, robots.txt and
the client-side search index.

    python3 generate_site.py            build into dist/
    python3 generate_site.py --serve    build, then serve dist/ on :8000
"""

import argparse
import datetime
import json
import os
import re
import shutil
import sys

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
TEMPLATES = os.path.join(ROOT, "templates")
STATIC = os.path.join(ROOT, "static")
DIST = os.path.join(ROOT, "dist")

TODAY = datetime.date.today().isoformat()
YEAR = datetime.date.today().year

# Pages are weighted in the sitemap by how central they are to the site.
PRIORITY = {
    "home": "1.0", "index": "0.9", "electrode": "0.8", "symbol": "0.8",
    "process": "0.8", "joint": "0.8", "comparison": "0.7", "guide": "0.7", "chart": "0.7",
    "legal": "0.3",
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def load(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as fh:
        return json.load(fh)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def short(text, limit=118):
    """First sentence of a summary, trimmed to fit a card."""
    first = re.split(r"(?<=[.!?]) ", text.strip())[0]
    if len(first) <= limit:
        return first
    cut = first[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "…"


def title_case_gas(e):
    return e["shielding_gas"]["primary"] if e.get("shielding_gas") else "None — self-shielding"


def amp_for(electrode, diameter_prefix):
    """The amperage entry whose diameter starts with the given string, or None."""
    for a in electrode["amperage"]:
        if a["diameter"].startswith(diameter_prefix):
            return a
    return None


def mid(a):
    return int(round((a["min"] + a["max"]) / 2))


# ---------------------------------------------------------------------------
# schema.org blocks
# ---------------------------------------------------------------------------

def jsonld(obj):
    """Serialise for a <script type="application/ld+json"> block.

    The three characters that could terminate the script element early are
    written as JSON unicode escapes, which keeps the payload valid JSON while
    making it impossible to break out of the tag."""
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    text = text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return Markup(text)


def breadcrumb_schema(site, crumbs):
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": c["name"],
             "item": site["base_url"] + c["url"]}
            for i, c in enumerate(crumbs)
        ],
    }


def faq_schema(faqs):
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": f["q"],
             "acceptedAnswer": {"@type": "Answer", "text": f["a"]}}
            for f in faqs
        ],
    }


def publisher(site):
    return {"@type": "Organization", "name": site["name"], "url": site["base_url"]}


def dataset_schema(site, name, description, url, keywords, variables, updated=TODAY):
    """Dataset markup — the electrode specs really are a structured dataset,
    and no competing welding reference publishes them as one."""
    return {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": name,
        "description": description,
        "url": site["base_url"] + url,
        "keywords": keywords,
        "license": "https://creativecommons.org/licenses/by-nc/4.0/",
        "isAccessibleForFree": True,
        "creator": publisher(site),
        "publisher": publisher(site),
        "dateModified": updated,
        "variableMeasured": variables,
    }


def prop(name, value, unit=None, description=None):
    v = {"@type": "PropertyValue", "name": name, "value": value}
    if unit:
        v["unitText"] = unit
    if description:
        v["description"] = description
    return v


# ---------------------------------------------------------------------------
# affiliate placeholders
# ---------------------------------------------------------------------------

BASE_GEAR = [
    {"label": "Auto-darkening welding helmet", "q": "auto darkening welding helmet"},
    {"label": "Welding gloves", "q": "welding gloves"},
    {"label": "Angle grinder and flap discs", "q": "angle grinder flap disc"},
]

CATEGORY_GEAR = {
    "mild-steel": [{"label": "Chipping hammer and wire brush", "q": "welding chipping hammer wire brush"}],
    "stainless": [{"label": "Stainless-only wire brush", "q": "stainless steel wire brush welding"},
                  {"label": "Argon back-purge kit", "q": "argon purge kit welding"}],
    "aluminum": [{"label": "Stainless brush for aluminium prep", "q": "stainless brush aluminum welding"},
                 {"label": "MIG spool gun", "q": "mig spool gun aluminum"}],
    "flux-cored": [{"label": "Knurled drive rolls", "q": "knurled drive roll flux core"},
                   {"label": "Welding fume extractor", "q": "welding fume extractor"}],
}

PROCESS_GEAR = {
    "stick-welding": [{"label": "Electrode rod oven", "q": "welding rod oven"}],
    "mig-welding": [{"label": "MIG contact tips and nozzles", "q": "mig contact tips nozzle"}],
    "tig-welding": [{"label": "Tungsten electrode assortment", "q": "tig tungsten electrode assortment"},
                    {"label": "TIG gas lens kit", "q": "tig gas lens kit"}],
    "flux-core-welding": [{"label": "Welding fume extractor", "q": "welding fume extractor"}],
    "submerged-arc-welding": [],
}


def gear_for(electrode):
    items = [{"label": "%s electrodes" % electrode["name"],
              "q": "%s welding %s" % (electrode["name"],
                                      "wire" if electrode["form"] != "Covered electrode" else "rod")}]
    items += CATEGORY_GEAR.get(electrode["category"], [])
    items += PROCESS_GEAR.get(electrode["process_id"], [])
    return (items + BASE_GEAR)[:6]


# ---------------------------------------------------------------------------
# generator
# ---------------------------------------------------------------------------

class Site:
    def __init__(self):
        self.site = load("site.json")
        self.electrodes = load("electrodes.json")["electrodes"]
        symbols_doc = load("welding_symbols.json")
        self.symbols = symbols_doc["symbols"]
        self.anatomy = symbols_doc["anatomy"]
        self.supplementary = symbols_doc["supplementary"]
        self.symbol_notes = symbols_doc["notes"]
        self.processes = load("processes.json")["processes"]
        self.comparisons = load("comparisons.json")["comparisons"]
        self.process_comparisons = load("process_comparisons.json")["comparisons"]
        self.joints = load("joints.json")["joints"]
        guides_doc = load("guides.json")
        self.guides = guides_doc["guides"]
        self.legal = guides_doc["legal"]

        self.by_id = {e["id"]: e for e in self.electrodes}
        self.sym_by_id = {s["id"]: s for s in self.symbols}
        self.proc_by_id = {p["id"]: p for p in self.processes}
        self.joint_by_id = {j["id"]: j for j in self.joints}

        self.env = Environment(
            loader=FileSystemLoader(TEMPLATES),
            autoescape=True,
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=False,
        )
        self.env.globals["site"] = self.site
        self.env.globals["year"] = YEAR

        self.pages = []          # (url, kind) for the sitemap
        self.index = []          # search index entries
        self.svg_cache = {}

        self._decorate()

    # -- derived data ------------------------------------------------------

    def _decorate(self):
        for e in self.electrodes:
            e["short"] = short(e["summary"])
        for s in self.symbols:
            s["svg_markup"] = self.svg(s["svg"])
            s["joint_svg_markup"] = self.svg(s["joint_svg"])
        for c in self.comparisons:
            c["a_name"] = self.by_id[c["a"]]["name"]
            c["b_name"] = self.by_id[c["b"]]["name"]
        for c in self.process_comparisons:
            c["id"] = "%s-vs-%s" % (self.proc_by_id[c["a"]]["abbr"].lower(),
                                    self.proc_by_id[c["b"]]["abbr"].lower())
            c["a_name"] = self.proc_by_id[c["a"]]["name"]
            c["b_name"] = self.proc_by_id[c["b"]]["name"]
        for j in self.joints:
            j["short"] = short(j["summary"])
            j["svg_markup"] = self.joint_svg(j["id"])

    def svg(self, name):
        """Inline an SVG, stripping its <style> block — style.css carries those
        rules so they are not repeated once per drawing on an index page."""
        if name in self.svg_cache:
            return self.svg_cache[name]
        path = os.path.join(STATIC, "symbols", name + ".svg")
        with open(path, encoding="utf-8") as fh:
            markup = fh.read()
        markup = re.sub(r"\s*<style>.*?</style>", "", markup, flags=re.S)
        markup = Markup(markup)
        self.svg_cache[name] = markup
        return markup

    def joint_svg(self, name):
        path = os.path.join(STATIC, "joints", name + ".svg")
        with open(path, encoding="utf-8") as fh:
            markup = fh.read()
        return Markup(re.sub(r"\s*<style>.*?</style>", "", markup, flags=re.S))

    def comparisons_for(self, electrode_id):
        return [c for c in self.comparisons
                if c["a"] == electrode_id or c["b"] == electrode_id]

    # -- writing -----------------------------------------------------------

    def write(self, url, template, kind, **ctx):
        crumbs = ctx.get("crumbs") or []
        schema = list(ctx.pop("schema_objects", []))
        if crumbs:
            schema.insert(0, breadcrumb_schema(self.site, crumbs))
        ctx["schema"] = [jsonld(s) for s in schema]
        ctx.setdefault("url", url)
        ctx.setdefault("section", None)
        ctx.setdefault("robots", None)
        html = self.env.get_template(template).render(**ctx)

        rel = "404.html" if url == "/404.html" else url.strip("/") + "/index.html"
        if url == "/":
            rel = "index.html"
        out = os.path.join(DIST, rel)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(html)
        if kind:
            self.pages.append((url, kind))

    def add_index(self, title, category, description, url, keywords):
        self.index.append({
            "t": title, "c": category, "d": short(description, 92),
            "u": url.lstrip("/"), "k": " ".join(keywords).lower(),
        })

    # -- page builders -----------------------------------------------------

    def build_home(self):
        featured_ids = ["e7018", "e6010", "e6011", "e6013", "er70s-6", "e71t-11",
                        "e308l", "e316l", "er4043", "er5356", "e7014", "e71t-1"]
        featured = [self.by_id[i] for i in featured_ids]
        featured_symbols = [self.sym_by_id[i] for i in
                            ["fillet-weld", "v-groove-weld", "bevel-groove-weld",
                             "plug-weld", "spot-weld", "back-weld"]]
        featured_cmp = [c for c in self.comparisons if c["id"] in (
            "e6010-vs-e7018", "e6013-vs-e7018", "e7018-vs-e7024", "e6010-vs-e6011",
            "er4043-vs-er5356", "e308l-vs-e316l", "er70s-6-vs-e71t-1",
            "e71t-1-vs-e71t-11", "e308l-vs-e309l", "e7014-vs-e7018",
            "er70s-6-vs-e7018", "e6011-vs-e6013")]

        counts = self.counts()
        schema = [
            {
                "@context": "https://schema.org",
                "@type": "WebSite",
                "name": self.site["name"],
                "url": self.site["base_url"] + "/",
                "description": self.site["description"],
                "publisher": publisher(self.site),
                "potentialAction": {
                    "@type": "SearchAction",
                    "target": {"@type": "EntryPoint",
                               "urlTemplate": self.site["base_url"] + "/electrodes/?q={search_term_string}"},
                    "query-input": "required name=search_term_string",
                },
            },
            dataset_schema(
                self.site,
                "Welding electrode and filler metal reference database",
                "Classification, polarity, welding positions, mechanical properties, amperage "
                "ranges by diameter, shielding gas and storage requirements for %d welding "
                "electrodes and filler metals, plus %d AWS A2.4 weld symbols and %d arc welding "
                "processes." % (counts["electrodes"], counts["symbols"], counts["processes"]),
                "/",
                ["welding electrodes", "AWS filler metals", "welding symbols",
                 "welding amperage", "AWS A2.4", "electrode specifications"],
                [prop("electrodeCount", counts["electrodes"]),
                 prop("weldSymbolCount", counts["symbols"]),
                 prop("processCount", counts["processes"]),
                 prop("comparisonCount", counts["comparisons"])],
            ),
        ]
        self.write(
            "/", "home.html", "home",
            page_title="%s — Welding Electrode Specs, Symbols & Settings" % self.site["name"],
            meta_description=("Free welding reference: full specs and amperage charts for %d "
                              "electrodes, %d AWS A2.4 weld symbols with diagrams, and guides to "
                              "stick, MIG, TIG and flux core."
                              % (counts["electrodes"], counts["symbols"])),
            counts=counts, featured_electrodes=featured, featured_symbols=featured_symbols,
            featured_comparisons=featured_cmp, processes=self.processes, guides=self.guides,
            joints=self.joints,
            schema_objects=schema, crumbs=[],
        )

    def counts(self):
        return {"electrodes": len(self.electrodes), "symbols": len(self.symbols),
                "processes": len(self.processes), "comparisons": len(self.comparisons),
                "guides": len(self.guides), "joints": len(self.joints)}

    # ---- electrodes ----

    def build_electrodes(self):
        base_crumbs = [{"name": "Home", "url": "/"},
                       {"name": "Electrodes", "url": "/electrodes/"}]

        # index
        groups = []
        for cat in self.site["categories"]:
            members = [e for e in self.electrodes if e["category"] == cat["id"]]
            if members:
                groups.append({"id": cat["id"], "name": cat["name"],
                               "description": cat["description"], "electrodes": members})
        self._electrode_listing(
            url="/electrodes/", heading="Welding Electrodes & Filler Metals",
            kicker="Reference database",
            title="Welding Electrodes: Specs, Amperage & Comparisons",
            meta=("Full specifications for %d welding electrodes and filler wires — AWS "
                  "classification, polarity, positions, tensile strength and amperage by diameter."
                  % len(self.electrodes)),
            summary=("This database covers %d electrodes and filler metals across carbon steel, "
                     "stainless and aluminium, with AWS classification, polarity, welding positions, "
                     "mechanical properties and amperage ranges by diameter for each one."
                     % len(self.electrodes)),
            groups=groups, electrodes=self.electrodes, comparisons=self.comparisons,
            crumbs=base_crumbs, other_categories=[], kind="index",
        )
        self.add_index("All welding electrodes", "Index",
                       "Every electrode and filler metal in the database.", "/electrodes/",
                       ["electrodes", "filler metal", "rods", "wire"])

        # category pages
        for cat in self.site["categories"]:
            members = [e for e in self.electrodes if e["category"] == cat["id"]]
            if not members:
                continue
            crumbs = base_crumbs + [{"name": cat["name"], "url": "/electrodes/%s/" % cat["id"]}]
            others = [c for c in self.site["categories"] if c["id"] != cat["id"]]
            cat_cmp = [c for c in self.comparisons
                       if self.by_id[c["a"]]["category"] == cat["id"]
                       and self.by_id[c["b"]]["category"] == cat["id"]]
            self._electrode_listing(
                url="/electrodes/%s/" % cat["id"],
                heading="%s Welding Electrodes" % cat["name"],
                kicker="%d electrodes" % len(members),
                title="%s Electrodes — Specs, Amperage & Selection" % cat["name"],
                meta=cat["meta_description"],
                summary=cat["description"],
                groups=[{"id": cat["id"], "name": "%s fillers" % cat["name"],
                         "description": None, "electrodes": members}],
                electrodes=members, comparisons=cat_cmp, crumbs=crumbs,
                other_categories=others, kind="index",
            )
            self.add_index("%s electrodes" % cat["name"], "Category",
                           cat["description"], "/electrodes/%s/" % cat["id"],
                           [cat["name"], cat["id"]] + [e["name"] for e in members])

        # detail pages
        for e in self.electrodes:
            self._electrode_page(e, base_crumbs)

        # comparison pages
        for c in self.comparisons:
            self._comparison_page(c, base_crumbs)

    def _electrode_listing(self, url, heading, kicker, title, meta, summary, groups,
                           electrodes, comparisons, crumbs, other_categories, kind):
        amp_quick = []
        for e in electrodes:
            row = {"id": e["id"], "name": e["name"], "polarity": ", ".join(e["polarity"])}
            for key, pref in (("d332", "3/32"), ("d18", "1/8"), ("d532", "5/32")):
                a = amp_for(e, pref)
                row[key] = "%d–%d A" % (a["min"], a["max"]) if a else "—"
            amp_quick.append(row)

        schema = [dataset_schema(
            self.site, heading, summary, url,
            [e["name"] for e in electrodes] + ["welding electrode", "amperage", "AWS"],
            [prop("electrodeCount", len(electrodes))] +
            [prop(e["name"] + " tensile strength", e["mechanical"]["tensile_ksi"], "ksi")
             for e in electrodes],
        )]
        self.write(url, "electrode_index.html", kind,
                   page_title="%s | %s" % (title, self.site["name"]),
                   meta_description=meta, heading=heading, kicker=kicker, summary=summary,
                   groups=groups, amp_quick=amp_quick, comparisons=comparisons,
                   other_categories=other_categories, crumbs=crumbs,
                   section="electrodes", schema_objects=schema)

    def _electrode_page(self, e, base_crumbs):
        url = "/electrodes/%s/" % e["id"]
        crumbs = base_crumbs + [
            {"name": e["category_name"], "url": "/electrodes/%s/" % e["category"]},
            {"name": e["name"], "url": url},
        ]
        related = [self.by_id[r] for r in e.get("related", []) if r in self.by_id]
        symbol_links = [self.sym_by_id[s] for s in e.get("related_symbols", [])
                        if s in self.sym_by_id]

        variables = [
            prop("AWS specification", e["spec"]),
            prop("Tensile strength (minimum)", e["mechanical"]["tensile_ksi"], "ksi"),
            prop("Polarity", ", ".join(e["polarity"])),
            prop("Welding positions", ", ".join(e["positions"])),
            prop("Penetration", e["penetration"]),
            prop("Shielding gas", title_case_gas(e)),
        ]
        if e["mechanical"].get("yield_ksi"):
            variables.append(prop("Yield strength (minimum)", e["mechanical"]["yield_ksi"], "ksi"))
        if e["mechanical"].get("elongation_pct"):
            variables.append(prop("Elongation (minimum)", e["mechanical"]["elongation_pct"], "%"))
        for a in e["amperage"]:
            variables.append(prop("Amperage, %s" % a["diameter"],
                                  "%d-%d" % (a["min"], a["max"]), "A",
                                  "Typical operating current range"))

        schema = [
            dataset_schema(
                self.site,
                "%s welding electrode specifications" % e["name"],
                "%s Includes amperage by diameter, polarity, welding positions, mechanical "
                "properties and storage requirements." % e["summary"],
                url,
                [e["name"], e["spec"], e["process"], e["category_name"],
                 "%s amperage" % e["name"], "%s settings" % e["name"]],
                variables,
            ),
            faq_schema(e["faqs"]),
        ]
        self.write(
            url, "electrode.html", "electrode",
            page_title="%s Welding Rod: Specs, Amperage & Polarity | %s" % (e["name"], self.site["name"]),
            meta_description=e["meta_description"],
            og_type="article",
            electrode=e, related=related, symbol_links=symbol_links,
            comparisons=self.comparisons_for(e["id"]),
            affiliate_items=gear_for(e),
            crumbs=crumbs, section="electrodes", schema_objects=schema,
        )
        self.add_index(
            e["name"], e["category_name"], e["summary"], url,
            [e["name"], e["spec"], e["process"], e["full_name"],
             "%s amperage" % e["name"], "%s polarity" % e["name"],
             "%s settings" % e["name"], e["category_name"]],
        )

    def _comparison_page(self, c, base_crumbs):
        a, b = self.by_id[c["a"]], self.by_id[c["b"]]
        url = "/electrodes/%s/" % c["id"]
        crumbs = base_crumbs + [{"name": "%s vs %s" % (a["name"], b["name"]), "url": url}]

        def m(e, key, unit="", fallback="—"):
            v = e["mechanical"].get(key)
            return "%s%s" % (v, unit) if v is not None else fallback

        rows = [
            {"label": "AWS specification", "a": a["spec"], "b": b["spec"], "num": True},
            {"label": "Process", "a": a["process_name"], "b": b["process_name"], "num": False},
            {"label": "Form", "a": a["form"], "b": b["form"], "num": False},
            {"label": "Tensile strength (min)", "a": m(a, "tensile_ksi", " ksi"),
             "b": m(b, "tensile_ksi", " ksi"), "num": True},
            {"label": "Yield strength (min)", "a": m(a, "yield_ksi", " ksi"),
             "b": m(b, "yield_ksi", " ksi"), "num": True},
            {"label": "Elongation (min)", "a": m(a, "elongation_pct", "%"),
             "b": m(b, "elongation_pct", "%"), "num": True},
            {"label": "Impact toughness", "a": a["mechanical"]["impact"],
             "b": b["mechanical"]["impact"], "num": False},
            {"label": "Polarity", "a": ", ".join(a["polarity"]), "b": ", ".join(b["polarity"]), "num": True},
            {"label": "Positions", "a": ", ".join(a["positions"]), "b": ", ".join(b["positions"]), "num": False},
            {"label": "Penetration", "a": a["penetration"], "b": b["penetration"], "num": False},
            {"label": "Deposition rate", "a": a["deposition"], "b": b["deposition"], "num": False},
            {"label": "Coating / core", "a": a["coating"], "b": b["coating"], "num": False},
            {"label": "Slag", "a": a["slag"], "b": b["slag"], "num": False},
            {"label": "Shielding gas", "a": title_case_gas(a), "b": title_case_gas(b), "num": False},
            {"label": "Storage", "a": a["storage"]["summary"], "b": b["storage"]["summary"], "num": False},
            {"label": "Primary use", "a": a["applications"][0], "b": b["applications"][0], "num": False},
        ]

        # Union of diameters, keeping each electrode's own ordering first.
        diameters = [x["diameter"] for x in a["amperage"]]
        diameters += [x["diameter"] for x in b["amperage"] if x["diameter"] not in diameters]
        amp_rows = []
        for d in diameters:
            ea = next((x for x in a["amperage"] if x["diameter"] == d), None)
            eb = next((x for x in b["amperage"] if x["diameter"] == d), None)
            amp_rows.append({
                "diameter": d,
                "a": "%d–%d A" % (ea["min"], ea["max"]) if ea else "—",
                "b": "%d–%d A" % (eb["min"], eb["max"]) if eb else "—",
            })

        others = [o for o in self.comparisons
                  if o["id"] != c["id"] and (o["a"] in (c["a"], c["b"]) or o["b"] in (c["a"], c["b"]))]

        schema = [
            dataset_schema(
                self.site,
                "%s vs %s comparison" % (a["name"], b["name"]),
                c["headline"], url,
                ["%s vs %s" % (a["name"], b["name"]), a["name"], b["name"],
                 "welding electrode comparison"],
                [prop("%s tensile strength" % a["name"], a["mechanical"]["tensile_ksi"], "ksi"),
                 prop("%s tensile strength" % b["name"], b["mechanical"]["tensile_ksi"], "ksi"),
                 prop("%s polarity" % a["name"], ", ".join(a["polarity"])),
                 prop("%s polarity" % b["name"], ", ".join(b["polarity"]))],
            ),
            faq_schema(c["faqs"]),
        ]
        self.write(
            url, "comparison.html", "comparison",
            page_title="%s vs %s: Which Electrode? | %s" % (a["name"], b["name"], self.site["name"]),
            meta_description=c["meta_description"], og_type="article",
            comparison=c, a=a, b=b, rows=rows, amp_rows=amp_rows,
            other_comparisons=others[:10],
            affiliate_items=(gear_for(a)[:2] + gear_for(b)[:1] + BASE_GEAR)[:5],
            crumbs=crumbs, section="electrodes", schema_objects=schema,
        )
        self.add_index(
            "%s vs %s" % (a["name"], b["name"]), "Comparison", c["headline"], url,
            ["%s vs %s" % (a["name"], b["name"]), "%s vs %s" % (b["name"], a["name"]),
             a["name"], b["name"], "compare"],
        )

    # ---- symbols ----

    def build_symbols(self):
        base = [{"name": "Home", "url": "/"}, {"name": "Symbols", "url": "/symbols/"}]
        summary = ("A welding symbol is read from the reference line outward: the arrow points at the "
                   "joint, a symbol below the line means weld the arrow side, above means the other "
                   "side, and the shape names the weld type. All %d AWS A2.4 weld symbols are below, "
                   "each with its own drawing." % len(self.symbols))
        schema = [
            dataset_schema(
                self.site, "AWS A2.4 weld symbol reference", summary, "/symbols/",
                ["welding symbols", "AWS A2.4", "weld symbol chart", "blueprint symbols"],
                [prop(s["name"], s["shape"]) for s in self.symbols],
            ),
        ]
        self.write(
            "/symbols/", "symbol_index.html", "index",
            page_title="Welding Symbols Chart (AWS A2.4) with Diagrams | %s" % self.site["name"],
            meta_description=("All %d AWS A2.4 weld symbols with original diagrams — fillet, "
                              "groove, plug, slot, spot, seam, back and surfacing, plus supplementary "
                              "symbols and dimension placement." % len(self.symbols)),
            summary=summary, symbols=self.symbols, anatomy=self.anatomy,
            supplementary=self.supplementary, notes=self.symbol_notes,
            crumbs=base, section="symbols", schema_objects=schema,
        )
        self.add_index("Welding symbols chart", "Index", summary, "/symbols/",
                       ["welding symbols", "weld symbol chart", "aws a2.4", "blueprint"])

        for s in self.symbols:
            url = "/symbols/%s/" % s["id"]
            crumbs = base + [{"name": s["name"], "url": url}]
            related = [self.sym_by_id[r] for r in s.get("related_symbols", []) if r in self.sym_by_id]
            electrodes = [self.by_id[r] for r in s.get("related_electrodes", []) if r in self.by_id]
            schema = [
                {
                    "@context": "https://schema.org",
                    "@type": "TechArticle",
                    "headline": "%s Symbol" % s["name"],
                    "description": s["summary"],
                    "url": self.site["base_url"] + url,
                    "author": publisher(self.site),
                    "publisher": publisher(self.site),
                    "dateModified": TODAY,
                    "about": {"@type": "Thing", "name": "%s (AWS A2.4 weld symbol)" % s["name"]},
                    "image": {
                        "@type": "ImageObject",
                        "contentUrl": "%s/symbols/%s.svg" % (self.site["base_url"], s["svg"]),
                        "encodingFormat": "image/svg+xml",
                        "caption": "%s symbol: %s" % (s["name"], s["shape"]),
                    },
                },
                faq_schema(s["faqs"]),
            ]
            self.write(
                url, "symbol.html", "symbol",
                page_title="%s Symbol: How to Read It (AWS A2.4) | %s" % (s["name"], self.site["name"]),
                meta_description=s["meta_description"], og_type="article",
                symbol=s, anatomy=self.anatomy, related_symbols=related,
                related_electrodes=electrodes, all_symbols=self.symbols,
                crumbs=crumbs, section="symbols", schema_objects=schema,
            )
            self.add_index(
                "%s symbol" % s["name"], "Weld symbol", s["summary"], url,
                [s["name"], s["shape"], "weld symbol"] + s["joint_types"],
            )

    # ---- processes ----

    def build_processes(self):
        base = [{"name": "Home", "url": "/"}, {"name": "Processes", "url": "/processes/"}]
        summary = ("Five arc welding processes cover almost all fabrication: stick for portability, "
                   "MIG for speed, TIG for control, flux-cored for deposition rate, and submerged arc "
                   "for heavy plate. Each page covers polarity, settings, gas and where the process fits.")
        self.write(
            "/processes/", "listing.html", "index",
            page_title="Welding Processes: Stick, MIG, TIG, Flux-Core & SAW | %s" % self.site["name"],
            meta_description=("Compare the five main arc welding processes — SMAW, GMAW, GTAW, "
                              "FCAW and SAW — with polarity, shielding gas, settings tables and "
                              "the trade-offs between them."),
            heading="Welding Processes", kicker="Arc welding", summary=summary,
            list_heading="The five arc welding processes",
            items=[{"url": "/processes/%s/" % p["id"], "name": p["name"],
                    "tag": p["abbr"], "description": p["summary"]} for p in self.processes],
            extra_title="Process comparisons", extra_id="comparisons",
            extra_intro="Head-to-head breakdowns of the process choices people actually face.",
            extra_links=[{"url": "/processes/%s/" % c["id"],
                          "name": "%s vs %s" % (c["a_name"], c["b_name"])}
                         for c in self.process_comparisons],
            crumbs=base, section="processes",
            schema_objects=[{
                "@context": "https://schema.org", "@type": "ItemList",
                "name": "Arc welding processes",
                "itemListElement": [
                    {"@type": "ListItem", "position": i + 1, "name": p["name"],
                     "url": self.site["base_url"] + "/processes/%s/" % p["id"]}
                    for i, p in enumerate(self.processes)],
            }],
        )
        self.add_index("Welding processes", "Index", summary, "/processes/",
                       ["processes", "smaw", "gmaw", "gtaw", "fcaw", "saw"])

        mode_headings = {
            "mig-welding": "Metal transfer modes",
            "tig-welding": "Current types",
            "stick-welding": "Polarity options",
            "flux-core-welding": "Gas-shielded vs self-shielded",
            "submerged-arc-welding": "Machine configurations",
        }
        for p in self.processes:
            url = "/processes/%s/" % p["id"]
            crumbs = base + [{"name": p["name"], "url": url}]
            rows = p["settings_table"]
            head = [k.replace("_", " ").title() for k in rows[0].keys()]
            body = [[str(v) for v in r.values()] for r in rows]
            consumables = [self.by_id[c] for c in p.get("consumables", []) if c in self.by_id]
            related = [self.proc_by_id[r] for r in p.get("related_processes", [])
                       if r in self.proc_by_id]
            schema = [
                {
                    "@context": "https://schema.org",
                    "@type": "TechArticle",
                    "headline": "%s (%s)" % (p["name"], p["abbr"]),
                    "description": p["summary"],
                    "url": self.site["base_url"] + url,
                    "author": publisher(self.site),
                    "publisher": publisher(self.site),
                    "dateModified": TODAY,
                },
                dataset_schema(
                    self.site, "%s process parameters" % p["name"], p["summary"], url,
                    [p["name"], p["abbr"], p["full_name"]] + p["aka"],
                    [prop("Polarity", p["polarity"]),
                     prop("Typical amperage", p["typical_amperage"]),
                     prop("Positions", p["positions"]),
                     prop("Shielding", p["shielding"])],
                ),
                faq_schema(p["faqs"]),
            ]
            self.write(
                url, "process.html", "process",
                page_title="%s (%s): Settings, Gas & Guide | %s" % (p["name"], p["abbr"], self.site["name"]),
                meta_description=p["meta_description"], og_type="article",
                process=p, settings_head=head, settings_rows=body,
                consumables=consumables, related_processes=related,
                mode_heading=mode_headings.get(p["id"], "Modes"),
                affiliate_items=(PROCESS_GEAR.get(p["id"], []) + BASE_GEAR)[:5],
                crumbs=crumbs, section="processes", schema_objects=schema,
            )
            self.add_index(p["name"], "Process", p["summary"], url,
                           [p["name"], p["abbr"], p["full_name"]] + p["aka"])

    def build_process_comparisons(self):
        base = [{"name": "Home", "url": "/"}, {"name": "Processes", "url": "/processes/"}]
        for c in self.process_comparisons:
            a, b = self.proc_by_id[c["a"]], self.proc_by_id[c["b"]]
            url = "/processes/%s/" % c["id"]
            crumbs = base + [{"name": "%s vs %s" % (a["name"], b["name"]), "url": url}]
            rows = [
                {"label": "AWS designation", "a": "%s \u2014 %s" % (a["abbr"], a["full_name"]),
                 "b": "%s \u2014 %s" % (b["abbr"], b["full_name"])},
                {"label": "Filler delivery", "a": a["one_liner"], "b": b["one_liner"]},
                {"label": "Polarity", "a": a["polarity"], "b": b["polarity"]},
                {"label": "Typical amperage", "a": a["typical_amperage"], "b": b["typical_amperage"]},
                {"label": "Typical voltage", "a": a["typical_voltage"], "b": b["typical_voltage"]},
                {"label": "Positions", "a": a["positions"], "b": b["positions"]},
                {"label": "Deposition rate", "a": a["deposition"], "b": b["deposition"]},
                {"label": "Shielding", "a": a["shielding"], "b": b["shielding"]},
                {"label": "Skill level", "a": a["skill_level"], "b": b["skill_level"]},
                {"label": "Slag", "a": "None" if a["id"] in ("mig-welding", "tig-welding") else "Yes \u2014 chip between passes",
                 "b": "None" if b["id"] in ("mig-welding", "tig-welding") else "Yes \u2014 chip between passes"},
            ]
            others = [o for o in self.process_comparisons
                      if o["id"] != c["id"] and (o["a"] in (c["a"], c["b"]) or o["b"] in (c["a"], c["b"]))]
            schema = [
                dataset_schema(
                    self.site, "%s vs %s process comparison" % (a["name"], b["name"]),
                    c["headline"], url,
                    ["%s vs %s" % (a["name"], b["name"]), "%s vs %s" % (a["abbr"], b["abbr"]),
                     a["name"], b["name"], "welding process comparison"],
                    [prop("%s polarity" % a["abbr"], a["polarity"]),
                     prop("%s polarity" % b["abbr"], b["polarity"]),
                     prop("%s amperage" % a["abbr"], a["typical_amperage"]),
                     prop("%s amperage" % b["abbr"], b["typical_amperage"])],
                ),
                faq_schema(c["faqs"]),
            ]
            self.write(
                url, "process_comparison.html", "comparison",
                page_title="%s vs %s: Which Process? | %s" % (a["name"], b["name"], self.site["name"]),
                meta_description=c["meta_description"], og_type="article",
                comparison=c, a=a, b=b, rows=rows, other_comparisons=others,
                affiliate_items=(PROCESS_GEAR.get(a["id"], []) + PROCESS_GEAR.get(b["id"], [])
                                 + BASE_GEAR)[:5],
                crumbs=crumbs, section="processes", schema_objects=schema,
            )
            self.add_index(
                "%s vs %s" % (a["name"], b["name"]), "Comparison", c["headline"], url,
                ["%s vs %s" % (a["name"], b["name"]), "%s vs %s" % (b["name"], a["name"]),
                 "%s vs %s" % (a["abbr"], b["abbr"]), a["name"], b["name"], a["abbr"], b["abbr"]],
            )

    # ---- joints ----

    def build_joints(self):
        base = [{"name": "Home", "url": "/"}, {"name": "Joints", "url": "/joints/"}]
        summary = ("There are five basic weld joint configurations \u2014 butt, lap, T, corner and edge "
                   "\u2014 and the joint you pick decides how much preparation the parts need, how much "
                   "filler the weld consumes, and how much load the finished connection can carry.")
        faqs = [
            {"q": "What are the five basic types of welding joints?", "a": "Butt, lap, T (tee), corner and edge. Every weld joint on a drawing is one of these five, or a variation on one."},
            {"q": "Which welding joint is strongest?", "a": "A full-penetration butt joint, because it develops the full strength of the base metal. It also demands the most edge preparation and the most careful fit-up."},
            {"q": "What is the difference between a T-joint and a corner joint?", "a": "Where the upright member lands. In a T-joint it meets the face of the other member somewhere in the middle; in a corner joint it meets the end, so the two form an L."},
            {"q": "Which joint needs no edge preparation?", "a": "Lap, T and corner joints welded with fillets need none, which is why fillet welds are the cheapest to specify. Butt joints need preparation above about 3/16 in."},
            {"q": "Does the joint type change which electrode I use?", "a": "Indirectly. An open-root butt joint wants a deep-penetrating electrode such as E6010; a positioned fillet can use a high-deposition rod like E7024. The joint sets the access and the penetration you need."},
        ]
        for j in self.joints:
            names = [self.sym_by_id[w]["name"] for w in j["common_welds"] if w in self.sym_by_id]
            j["weld_names"] = ", ".join(names[:3])
            j["prep_short"] = short(j["prep"], 70)
            j["strength_short"] = short(j["strength"], 80)

        self.write(
            "/joints/", "joint_index.html", "index",
            page_title="Types of Welding Joints: Butt, Lap, T, Corner & Edge | %s" % self.site["name"],
            meta_description=("The five basic weld joint types \u2014 butt, lap, T, corner and edge "
                              "\u2014 with cross-section diagrams, edge preparation requirements and "
                              "the weld symbols used on each."),
            summary=summary, joints=self.joints, faqs=faqs,
            crumbs=base, section="joints",
            schema_objects=[
                dataset_schema(self.site, "Weld joint types", summary, "/joints/",
                               ["welding joints", "joint types", "butt joint", "lap joint",
                                "t joint", "corner joint", "edge joint"],
                               [prop(j["name"], j["geometry"]) for j in self.joints]),
                faq_schema(faqs),
            ],
        )
        self.add_index("Types of welding joints", "Index", summary, "/joints/",
                       ["joints", "joint types", "butt", "lap", "tee", "corner", "edge"])

        for j in self.joints:
            url = "/joints/%s/" % j["id"]
            crumbs = base + [{"name": j["name"], "url": url}]
            welds = [self.sym_by_id[w] for w in j["common_welds"] if w in self.sym_by_id]
            others = [o for o in self.joints if o["id"] != j["id"]]
            schema = [
                {
                    "@context": "https://schema.org", "@type": "TechArticle",
                    "headline": j["name"], "description": j["summary"],
                    "url": self.site["base_url"] + url,
                    "author": publisher(self.site), "publisher": publisher(self.site),
                    "dateModified": TODAY,
                    "image": {
                        "@type": "ImageObject",
                        "contentUrl": "%s/joints/%s.svg" % (self.site["base_url"], j["id"]),
                        "encodingFormat": "image/svg+xml",
                        "caption": "Cross-section through a %s" % j["name"].lower(),
                    },
                },
                faq_schema(j["faqs"]),
            ]
            self.write(
                url, "joint.html", "joint",
                page_title="%s: Preparation, Welds & Strength | %s" % (j["name"], self.site["name"]),
                meta_description=j["meta_description"], og_type="article",
                joint=j, welds=welds, other_joints=others,
                crumbs=crumbs, section="joints", schema_objects=schema,
            )
            self.add_index(j["name"], "Joint type", j["summary"], url,
                           [j["name"], j["id"].replace("-", " "), "joint"])

    # ---- guides, legal, chart ----

    def _article_blocks(self, blocks):
        """Give headings stable ids and collect a table of contents."""
        out, toc = [], []
        for b in blocks:
            b = dict(b)
            if b["type"] in ("h2", "h3"):
                b["id"] = slug(b["text"])
                if b["type"] == "h2":
                    toc.append({"id": b["id"], "text": b["text"]})
            out.append(b)
        return out, toc

    def build_guides(self):
        base = [{"name": "Home", "url": "/"}, {"name": "Guides", "url": "/guides/"}]
        summary = ("Reference guides for the things that are not on a single electrode's page — "
                   "reading welding symbols, decoding AWS electrode numbers, polarity, rod storage "
                   "and welding positions.")
        self.write(
            "/guides/", "listing.html", "index",
            page_title="Welding Reference Guides | %s" % self.site["name"],
            meta_description=("Practical welding reference guides: reading AWS A2.4 welding symbols, "
                              "decoding electrode numbers, DCEP vs DCEN polarity, rod oven storage "
                              "and welding positions."),
            heading="Welding Guides", kicker="Reference", summary=summary,
            list_heading="All guides",
            items=[{"url": "/guides/%s/" % g["id"], "name": g["title"], "tag": None,
                    "description": g["summary"]} for g in self.guides],
            extra_title="Reference charts and tables", extra_id="charts",
            extra_intro=None,
            extra_links=[{"url": "/charts/amperage/", "name": "Amperage chart"},
                         {"url": "/symbols/", "name": "Weld symbol chart"},
                         {"url": "/joints/", "name": "Joint types"},
                         {"url": "/electrodes/", "name": "Electrode index"}],
            crumbs=base, section="guides",
            schema_objects=[{
                "@context": "https://schema.org", "@type": "ItemList",
                "name": "Welding reference guides",
                "itemListElement": [
                    {"@type": "ListItem", "position": i + 1, "name": g["title"],
                     "url": self.site["base_url"] + "/guides/%s/" % g["id"]}
                    for i, g in enumerate(self.guides)],
            }],
        )
        self.add_index("Welding guides", "Index", summary, "/guides/", ["guides", "reference"])

        for g in self.guides:
            url = "/guides/%s/" % g["id"]
            crumbs = base + [{"name": g["title"], "url": url}]
            blocks, toc = self._article_blocks(g["blocks"])
            # one in-article ad, roughly a third of the way down
            insert = max(1, len(blocks) // 3)
            blocks.insert(insert, {"type": "ad", "slot": "in_article"})

            links = []
            for sid in g.get("related_symbols", []):
                if sid in self.sym_by_id:
                    links.append({"url": "/symbols/%s/" % sid,
                                  "name": "%s symbol" % self.sym_by_id[sid]["name"]})
            for eid in g.get("related_electrodes", []):
                if eid in self.by_id:
                    links.append({"url": "/electrodes/%s/" % eid, "name": self.by_id[eid]["name"]})

            schema = [
                {
                    "@context": "https://schema.org",
                    "@type": "TechArticle",
                    "headline": g["title"],
                    "description": g["summary"],
                    "url": self.site["base_url"] + url,
                    "author": publisher(self.site),
                    "publisher": publisher(self.site),
                    "dateModified": TODAY,
                },
                faq_schema(g["faqs"]),
            ]
            self.write(
                url, "article.html", "guide",
                page_title="%s | %s" % (g["title"], self.site["name"]),
                meta_description=g["meta_description"], og_type="article",
                kicker="Guide", heading=g["title"], summary=g["summary"],
                blocks=blocks, toc=toc, faqs=g["faqs"], related_links=links,
                related_title="Related reference", crumbs=crumbs, section="guides",
                schema_objects=schema, hide_sidebar_ad=False,
            )
            self.add_index(g["title"], "Guide", g["summary"], url,
                           [g["title"]] + [b.get("text", "") for b in g["blocks"] if b["type"] == "h2"])

    def build_legal(self):
        for p in self.legal:
            url = "/%s/" % p["id"]
            crumbs = [{"name": "Home", "url": "/"}, {"name": p["title"], "url": url}]
            blocks, toc = self._article_blocks(p["blocks"])
            self.write(
                url, "article.html", "legal",
                page_title="%s | %s" % (p["title"], self.site["name"]),
                meta_description=p["meta_description"],
                kicker=None, heading=p["title"], summary=p["summary"],
                blocks=blocks, toc=toc, faqs=None, related_links=None,
                crumbs=crumbs, section=None, hide_sidebar_ad=True,
                schema_objects=[{
                    "@context": "https://schema.org", "@type": "WebPage",
                    "name": p["title"], "description": p["summary"],
                    "url": self.site["base_url"] + url, "publisher": publisher(self.site),
                }],
            )
            self.add_index(p["title"], "Site", p["summary"], url, [p["title"], p["id"]])

    def build_chart(self):
        url = "/charts/amperage/"
        crumbs = [{"name": "Home", "url": "/"}, {"name": "Amperage chart", "url": url}]
        summary = ("Amperage ranges for every electrode in this database, by diameter. As a starting "
                   "rule for carbon steel stick electrodes, run about one amp per thousandth of an "
                   "inch of rod diameter — roughly 125 A for a 1/8 in rod — then adjust by "
                   "arc sound and bead profile.")
        groups, variables = [], []
        for cat in self.site["categories"]:
            members = [e for e in self.electrodes if e["category"] == cat["id"]]
            if not members:
                continue
            rows = []
            for e in members:
                for i, a in enumerate(e["amperage"]):
                    rows.append({
                        "first": i == 0, "span": len(e["amperage"]),
                        "id": e["id"], "name": e["name"], "spec": e["spec"],
                        "polarity": ", ".join(e["polarity"]),
                        "diameter": a["diameter"], "min": a["min"], "max": a["max"],
                        "mid": mid(a),
                    })
                    variables.append(prop("%s %s" % (e["name"], a["diameter"]),
                                          "%d-%d" % (a["min"], a["max"]), "A"))
            groups.append({"id": cat["id"], "name": cat["name"], "rows": rows})

        faqs = [
            {"q": "What amperage for a 1/8 inch welding rod?", "a": "Roughly 125 A for carbon steel, using the one-amp-per-thousandth rule. In practice: E6010 70–130 A, E6013 80–130 A, E7018 110–165 A, E7024 140–190 A. Stainless rods of the same diameter run lower, around 65–110 A."},
            {"q": "How do I know if my amperage is too high?", "a": "Excessive spatter, undercut along the toes of the bead, a wide flat bead, and on stick welding the last inches of the rod glowing red while the coating breaks down."},
            {"q": "Should I lower amperage for vertical welding?", "a": "Yes — drop 10 to 15% from your flat setting. A puddle that is fine flat will sag out of a vertical or overhead joint."},
            {"q": "Why do stainless electrodes use lower amperage?", "a": "Stainless has roughly half the thermal conductivity of carbon steel and higher electrical resistance, so the rod itself heats up along its length and the heat does not run away into the plate. Running a stainless rod at carbon steel amperage overheats the coating."},
            {"q": "Does polarity change the amperage?", "a": "The setting on the dial is the same, but where the heat goes is not. DCEP puts roughly two-thirds of the heat in the work for deeper penetration; DCEN puts more into the electrode, giving shallower penetration and a higher deposition rate at the same current."},
        ]
        schema = [
            dataset_schema(
                self.site, "Welding electrode amperage chart", summary, url,
                ["welding amperage chart", "electrode amperage", "welding settings",
                 "stick welding amps", "MIG settings"],
                variables,
            ),
            faq_schema(faqs),
        ]
        self.write(
            url, "amperage_chart.html", "chart",
            page_title="Welding Amperage Chart by Electrode & Diameter | %s" % self.site["name"],
            meta_description=("Amperage settings for %d welding electrodes by diameter — stick, "
                              "MIG, TIG and flux-cored — with polarity and a rule of thumb for "
                              "dialling in a new rod." % len(self.electrodes)),
            summary=summary, groups=groups, faqs=faqs,
            crumbs=crumbs, section="charts", schema_objects=schema,
        )
        self.add_index("Welding amperage chart", "Chart", summary, url,
                       ["amperage", "amps", "settings", "chart", "current"])

    def build_404(self):
        self.write("/404.html", "404.html", None,
                   page_title="Page not found | %s" % self.site["name"],
                   meta_description="That page does not exist. Search the welding reference database "
                                    "or browse electrodes, symbols and processes.",
                   counts=self.counts(), crumbs=[], robots="noindex, follow")

    # -- assets ------------------------------------------------------------

    def copy_static(self):
        for name in os.listdir(STATIC):
            if name == "favicons":
                continue  # copied to the site root by copy_favicons()
            src = os.path.join(STATIC, name)
            dst = os.path.join(DIST, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)

    def copy_favicons(self):
        """The favicon pack lives at the site root, because browsers probe
        /favicon.ico and /apple-touch-icon.png there without being told to.
        Regenerate the files with scripts/make_favicons.py."""
        src_dir = os.path.join(STATIC, "favicons")
        for name in sorted(os.listdir(src_dir)):
            shutil.copy2(os.path.join(src_dir, name), os.path.join(DIST, name))

    def write_webmanifest(self):
        manifest = {
            "name": "%s \u2014 %s" % (self.site["name"], self.site["tagline"]),
            "short_name": self.site["short_name"],
            "description": self.site["description"],
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "background_color": self.site["background_color"],
            "theme_color": self.site["theme_color"],
            "icons": [
                {"src": "/android-chrome-192x192.png", "sizes": "192x192",
                 "type": "image/png", "purpose": "any"},
                {"src": "/android-chrome-512x512.png", "sizes": "512x512",
                 "type": "image/png", "purpose": "any"},
            ],
        }
        with open(os.path.join(DIST, "site.webmanifest"), "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)

    def write_search_index(self):
        with open(os.path.join(DIST, "search-index.json"), "w", encoding="utf-8") as fh:
            json.dump(self.index, fh, ensure_ascii=False, separators=(",", ":"))

    def write_sitemap(self):
        base = self.site["base_url"]
        lines = ['<?xml version="1.0" encoding="UTF-8"?>',
                 '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        for url, kind in self.pages:
            lines += [
                "  <url>",
                "    <loc>%s%s</loc>" % (base, url),
                "    <lastmod>%s</lastmod>" % TODAY,
                "    <changefreq>%s</changefreq>" % ("weekly" if kind in ("home", "index") else "monthly"),
                "    <priority>%s</priority>" % PRIORITY.get(kind, "0.5"),
                "  </url>",
            ]
        lines.append("</urlset>")
        with open(os.path.join(DIST, "sitemap.xml"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")

    def write_cname(self):
        """GitHub Pages reads dist/CNAME to serve the custom domain. dist/ is a
        build artefact, so the file is generated rather than committed."""
        with open(os.path.join(DIST, "CNAME"), "w", encoding="utf-8") as fh:
            fh.write(self.site["domain"] + "\n")

    def write_robots(self):
        txt = (
            "User-agent: *\n"
            "Allow: /\n"
            "\n"
            "# Build artefacts and the search index are not useful in results.\n"
            "Disallow: /search-index.json\n"
            "\n"
            "Sitemap: %s/sitemap.xml\n" % self.site["base_url"]
        )
        with open(os.path.join(DIST, "robots.txt"), "w", encoding="utf-8") as fh:
            fh.write(txt)

    # -- run ---------------------------------------------------------------

    def build(self):
        if os.path.isdir(DIST):
            shutil.rmtree(DIST)
        os.makedirs(DIST)

        self.build_home()
        self.build_electrodes()
        self.build_symbols()
        self.build_processes()
        self.build_process_comparisons()
        self.build_joints()
        self.build_guides()
        self.build_chart()
        self.build_legal()
        self.build_404()

        self.copy_static()
        self.copy_favicons()
        self.write_webmanifest()
        self.write_search_index()
        self.write_sitemap()
        self.write_robots()
        self.write_cname()
        return self.pages


def main():
    ap = argparse.ArgumentParser(description="Build weldsymbols.org")
    ap.add_argument("--serve", action="store_true", help="serve dist/ after building")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()

    site = Site()
    pages = site.build()

    kinds = {}
    for _, k in pages:
        kinds[k] = kinds.get(k, 0) + 1
    print("Built %d pages into %s" % (len(pages), os.path.relpath(DIST, ROOT)))
    for k in sorted(kinds, key=lambda x: -kinds[x]):
        print("  %-12s %d" % (k, kinds[k]))
    print("  %-12s %d entries" % ("search index", len(site.index)))

    if args.serve:
        import functools
        import http.server
        import socketserver
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=DIST)
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("", args.port), handler) as httpd:
            print("\nServing http://localhost:%d/ — Ctrl-C to stop" % args.port)
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
