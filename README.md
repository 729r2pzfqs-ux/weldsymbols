# weldsymbols.org

A static welding reference database: electrode specifications, AWS A2.4 weld symbols,
joint types and arc welding process guides. Built from JSON data files with a small
Jinja2 generator — no framework, no runtime dependencies, no JavaScript required to
read any page.

## Build

```bash
pip install -r requirements.txt
python3 generate_site.py            # builds into dist/
python3 generate_site.py --serve    # builds, then serves dist/ on :8000
```

The build is deterministic and takes well under a second. `dist/` is disposable and
is not committed.

## What it generates

| Page type | Count | URL pattern |
|---|---|---|
| Homepage | 1 | `/` |
| Electrode pages | 20 | `/electrodes/e7018/` |
| Electrode comparisons | 35 | `/electrodes/e6010-vs-e7018/` |
| Weld symbol pages | 11 | `/symbols/fillet-weld/` |
| Joint type pages | 5 | `/joints/butt-joint/` |
| Process pages | 5 | `/processes/mig-welding/` |
| Process comparisons | 6 | `/processes/gmaw-vs-gtaw/` |
| Reference guides | 7 | `/guides/welding-rod-storage/` |
| Amperage chart | 1 | `/charts/amperage/` |
| Index pages | 9 | `/electrodes/`, `/symbols/`, … |
| Legal | 3 | `/about/`, `/privacy/`, `/terms/` |

Plus `sitemap.xml`, `robots.txt`, `search-index.json`, `favicon.svg` and a `404.html`.

## Layout

```
data/                      content, as JSON — edit these, not the HTML
  site.json                site config, categories, ad slots, analytics IDs
  electrodes.json          20 electrodes and filler wires
  comparisons.json         35 curated electrode pairings
  welding_symbols.json     11 weld symbols + anatomy + supplementary symbols
  joints.json              5 joint types
  processes.json           5 arc welding processes
  process_comparisons.json 6 process pairings
  guides.json              7 reference guides + 3 legal pages
templates/                 Jinja2 templates, one per page type
static/
  css/style.css            the entire stylesheet
  js/search.js             client-side search (the only JavaScript on the site)
  symbols/*.svg            22 generated weld symbol drawings
  joints/*.svg             5 generated joint cross-sections
scripts/
  make_symbol_svgs.py      regenerates static/symbols/
  make_joint_svgs.py       regenerates static/joints/
generate_site.py           the generator
```

## Adding content

Adding an electrode means adding one object to `data/electrodes.json` and rebuilding.
The generator derives the detail page, the index entry, the amperage chart row, the
search index entry, the sitemap entry and the schema markup from that one object.
Comparison pages are declared in `data/comparisons.json` by electrode id; the
side-by-side tables are computed from the electrode data, so only the written
judgement — headline, verdict, when-to-choose — lives in the comparison file.

The SVG drawings are generated rather than hand-drawn so that the reference line,
leader and arrowhead stay identical across every symbol. Edit the shape functions in
`scripts/make_symbol_svgs.py` and re-run it.

## SEO

Every page carries a unique title and answer-first meta description, a canonical URL,
breadcrumbs with `BreadcrumbList` markup, and proper heading hierarchy. Electrode,
comparison, symbol, process and chart pages also carry `Dataset` markup — the
specifications genuinely are a structured dataset, and no competing welding reference
publishes them as one. Pages with a Q&A section carry `FAQPage` markup.

`python3 generate_site.py` is checked against duplicate titles and descriptions,
meta description length, single-`h1`, heading-level jumps, JSON-LD validity and
broken internal links.

## Monetisation placeholders

| What | Where | Status |
|---|---|---|
| Google AdSense | `data/site.json` → `adsense_client` | Client ID live, ad slot IDs are placeholders |
| Google Analytics | `data/site.json` → `analytics_id` | Empty — the tag is omitted until an ID is set |
| Ahrefs Analytics | `data/site.json` → `ahrefs_key` | Empty — the tag is omitted until a key is set |
| Amazon Associates | `data/site.json` → `amazon_tag` | Empty — links fall back to untagged search URLs |

Set the value in `data/site.json` and rebuild; nothing else needs editing. Real
AdSense ad-unit IDs replace the placeholders in `adsense_slots`.

## Deploying

Pushing to `main` builds and publishes automatically via
`.github/workflows/deploy.yml` — it installs Jinja2, runs `generate_site.py`,
checks the expected files exist, and uploads `dist/` to GitHub Pages. The
workflow can also be re-run by hand from the Actions tab.

The custom domain is `weldsymbols.org`. The generator writes `dist/CNAME` from
the `domain` field in `data/site.json`, because `dist/` is a build artefact and
is not committed — GitHub Pages needs that file present in the published output
or it drops the custom domain on every deploy.

### DNS

The apex domain needs these records at the registrar:

```
A     @   185.199.108.153
A     @   185.199.109.153
A     @   185.199.110.153
A     @   185.199.111.153
```

Add `CNAME www 729r2pzfqs-ux.github.io` if the `www` subdomain should redirect.
Once DNS resolves, enable HTTPS:

```bash
gh api repos/729r2pzfqs-ux/weldsymbols/pages -X PUT -F https_enforced=true
```

`dist/` is also a plain static directory, so Netlify, Cloudflare Pages, S3 or
nginx work just as well. Serve directories with `index.html` and set
`404.html` as the not-found page.

## Sources

Classification systems and minimum property requirements are factual data from the AWS
filler metal specifications (A5.1, A5.3, A5.4, A5.9, A5.10, A5.18, A5.20); symbol
conventions follow AWS A2.4. Process and joint background draws on US Army TC 9-237, a
public-domain military welding manual. Operating ranges are typical figures consistent
with manufacturer-published data from Lincoln Electric, Miller Electric and ESAB. All
prose and all drawings are original.

Amperage ranges on this site are starting points. For coded work the governing welding
procedure specification and the manufacturer's data sheet take precedence.

## Contact

info@weldsymbols.org
