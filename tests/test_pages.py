"""Page generator (Task 10): builds the Quarto sources in a copy of the repository."""

import re
import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
import yaml

from indicators import bibliography, pages

ROOT = Path(__file__).resolve().parent.parent
RELEASE1 = {"ED1", "EA1", "EA2", "GD1", "CD1"}
TABLE_ROWS = ["What it measures", "Current reading", "Why it matters", "Grid position", "AI link",
              "Leading or lagging", "Latest data", "Calculation", "Coverage", "Data sources"]
INTERNAL_KEYS = ["structural", "ai_native", "exposure", "erosion", "lockin", "tier"]
RETIRED_TERMS = ["AI-specificity", "rival", "direction assumption", "takeaway"]
FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLSdJn9K0revpwU1sWM-WPmqlPtw80JVSuR9lIzcPktXqY7e3Tg/viewform"
TODAY = date(2026, 11, 18)

SYNTHETIC_PAGE = """---
summary: Neutral summary text.
warning_sign: Neutral warning text.
data_sources:
  - name: Source one
    url: https://www.census.gov/hfp/btos
calculation: Neutral calculation text.
coverage: Somewhere · monthly · from 2000
---

## Why this matters for gradual disempowerment

Neutral.

## What it shows

Neutral.

## What it doesn't show

Neutral.

## What would change our reading

### Warning sign

Neutral.

### Alternative explanations

Neutral.

## Data and calculation

Neutral.

## Caveats

Neutral.
"""


def _copy_site_sources(dest: Path) -> None:
    generated = {"_site", ".quarto", "data", "config", "indicators", "_generated"}
    shutil.copytree(ROOT / "site", dest, ignore=lambda d, names: [
        n for n in names if Path(d) == ROOT / "site" and n in generated])


@pytest.fixture
def repo(tmp_path):
    """A copy of config/, the top-level data/ files, content/, references/ and the site sources."""
    shutil.copytree(ROOT / "config", tmp_path / "config")
    shutil.copytree(ROOT / "content", tmp_path / "content")
    shutil.copytree(ROOT / "references", tmp_path / "references")
    (tmp_path / "data").mkdir()
    for f in (ROOT / "data").iterdir():
        if f.is_file():
            shutil.copy(f, tmp_path / "data" / f.name)
    _copy_site_sources(tmp_path / "site")
    return tmp_path


def _page(repo, ind_id):
    return (repo / "site" / "indicators" / f"{ind_id}.qmd").read_text(encoding="utf-8")


def _front_matter(text):
    return yaml.safe_load(text.split("---\n", 2)[1])


def _table(text):
    rows = []
    for line in text.splitlines():
        m = re.match(r"^\| ([^|]+?) \| (.*) \|$", line)
        if m and not set(m.group(1)) <= set("-: "):
            rows.append((m.group(1), m.group(2)))
    return rows


def _value(cell):
    """A summary-table cell without its trailing 'More' link."""
    return re.sub(r"(<br>| )\[More\]\([^)]*\)$", "", cell)


def _index(repo):
    site = repo / "site"
    return (site / "index.qmd").read_text(encoding="utf-8") + (site / "_generated" / "summary.md").read_text(encoding="utf-8")


def _cells(index_text):
    """Grid cells as {(row, domain): body} from the fenced divs in the summary."""
    cells = {}
    for m in re.finditer(r'^::: \{\.keel-cell row="([^"]+)" domain="([^"]+)"\}\n(.*?)\n:::$',
                         index_text, re.M | re.S):
        cells[(m.group(1), m.group(2))] = m.group(3)
    return cells


def test_build_writes_release1_pages_only(repo):
    reg = yaml.safe_load((repo / "config" / "indicators.yaml").read_text())
    extra = dict(reg["indicators"][0], id="E9", release=2)
    reg["indicators"].append(extra)
    (repo / "config" / "indicators.yaml").write_text(yaml.safe_dump(reg, sort_keys=False))
    pages.build(repo, today=TODAY)
    written = {p.stem for p in (repo / "site" / "indicators").glob("*.qmd")}
    assert written == RELEASE1


def test_title_contains_full_indicator_name(repo):
    pages.build(repo, today=TODAY)
    assert _front_matter(_page(repo, "CD1"))["title"] == "Human knowledge-commons activity (CD1)"
    assert _front_matter(_page(repo, "ED1"))["title"] == "Labor share of income (ED1)"


def test_summary_table_has_ten_rows_in_order(repo):
    pages.build(repo, today=TODAY)
    for ind_id in RELEASE1:
        assert [r for r, _ in _table(_page(repo, ind_id))][:10] == TABLE_ROWS, ind_id


def test_page_sections_in_order(repo):
    pages.build(repo, today=TODAY)
    heads = [line[3:] for line in _page(repo, "ED1").splitlines() if line.startswith("## ")]
    assert heads == ["The data over time", "Why this matters for gradual disempowerment", "Reading history",
                     "What it shows", "What it doesn't show", "What would change our reading", "Method",
                     "Caveats", "Data and calculation", "Download the data"]


def test_rows_link_to_the_sections_that_expand_on_them(repo):
    pages.build(repo, today=TODAY)
    rows = dict(_table(_page(repo, "ED1")))
    expected = {"What it measures": " [More](#what-it-shows)", "Why it matters":
                " [More](#why-this-matters-for-gradual-disempowerment)", "AI link": " [More](#method)",
                "Latest data": " [More](#data-and-calculation)", "Calculation": " [More](#data-and-calculation)",
                "Coverage": " [More](#method)", "Data sources": "<br>[More](#data-and-calculation)"}
    for row, link in expected.items():
        assert rows[row].endswith(link), row
    assert "[More]" not in rows["Grid position"] and "[More]" not in rows["Leading or lagging"]


def test_latest_data_row_is_series_then_value_then_fetch_date(repo):
    pages.build(repo, today=TODAY)
    table = _table(_page(repo, "ED1"))
    assert table[6][0] == "Latest data"
    name, value, fetched = _value(table[6][1]).split("<br>")
    assert name == "Labor share of income, nonfarm business sector"
    assert value.endswith("Readings will compare its change with same-length changes in 2010 to 2019.") and "percent" in value
    assert re.fullmatch(r"Data last fetched \d{1,2} [A-Z][a-z]+ \d{4}", fetched)
    assert "own recent path" in dict(_table(_page(repo, "EA1")))["Latest data"]


def test_rating_rows_show_a_bold_value_over_an_explanation(repo):
    pages.build(repo, today=TODAY)
    rows = dict(_table(_page(repo, "ED1")))
    assert rows["AI link"].startswith("**Weak**<br>A draft rating on four criteria")
    assert rows["Leading or lagging"] == "**Lagging**<br>Likely to move only after a change is well under way."


def test_current_reading_is_label_only_without_ai_link(repo):
    pages.build(repo, today=TODAY)
    cell = dict(_table(_page(repo, "ED1")))["Current reading"]
    assert cell.strip() == "**Not yet reviewed**<br>[History](#reading-history)"
    assert "AI link" not in cell


def test_interpretation_on_second_line_without_ai_link(repo):
    with open(repo / "config" / "readings.yaml", "a", encoding="utf-8") as f:
        f.write("  - {indicator_id: ED1, state: below, date: 2026-11-18, kind: current, "
                "interpretation: 'If AI-driven, consistent with workers losing leverage'}\n")
    pages.build(repo, today=TODAY)
    cell = dict(_table(_page(repo, "ED1")))["Current reading"]
    lines = cell.split("<br>")
    assert len(lines) == 3 and lines[0].strip().startswith("**")
    assert lines[1].strip() == "If AI-driven, consistent with workers losing leverage"
    assert lines[2] == "[History](#reading-history)"
    assert "AI link" not in cell


def test_data_sources_render_as_links(repo):
    pages.build(repo, today=TODAY)
    cell = dict(_table(_page(repo, "CD1")))["Data sources"]
    assert "[Stack Exchange API (new questions per month)](../sources.qmd#stackexchange_api)" in cell
    assert "(../sources.qmd#wikimedia_analytics_api)" in cell


def test_data_source_not_in_bibliography_fails_the_build(repo):
    path = repo / "content" / "indicators" / "CD1.md"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "https://api.stackexchange.com/docs/questions", "https://example.org/unlisted"), encoding="utf-8")
    with pytest.raises(ValueError, match="not in the bibliography"):
        pages.build(repo, today=TODAY)


def test_sources_licenses_and_fetch_dates_sit_in_data_and_calculation(repo):
    pages.build(repo, today=TODAY)
    text = _page(repo, "CD1")
    data = text[text.index("## Data and calculation"):text.index("## Download the data")]
    method = text[text.index("## Method"):text.index("## Caveats")]
    assert "    - [Stack Exchange API](../sources.qmd#stackexchange_api). License: CC BY-SA." in data
    assert "- **Last fetched.**" in data
    assert "License:" not in method and "Last fetched" not in method


def test_method_section_cites_chart_markers(repo):
    pages.build(repo, today=TODAY)
    text = _page(repo, "CD1")
    method = text[text.index("## Method"):text.index("## Caveats")]
    assert "    - 29 June 2021: GitHub Copilot technical preview announced [(Friedman 2021)](../sources.qmd#friedman2021)" in method
    assert "[(OpenAI 2022)](../sources.qmd#openai2022)" in method
    ea1 = _page(repo, "EA1")
    assert "[(U.S. Census Bureau 2026)](../sources.qmd#census2026)" in ea1


def _set_meta(repo, sid, **fields):
    """Fix a series' metadata in the test's copy: the live values move with each weekly refresh."""
    path = repo / "data" / f"{sid}.meta.json"
    meta = json.loads(path.read_text(encoding="utf-8"))
    meta.update(fields)
    path.write_text(json.dumps(meta), encoding="utf-8")


def test_grid_position_and_coverage_filled_automatically(repo):
    _set_meta(repo, "us_labor_tax_share", data_through="2026-04-01")
    pages.build(repo, today=TODAY)
    rows = dict(_table(_page(repo, "GD1")))
    assert rows["Grid position"] == "**Displacement · Government**"
    assert "data through 2026 Q2" in rows["Coverage"]
    assert dict(_table(_page(repo, "EA1")))["Grid position"] == "**Adoption · Economic**"


def test_e3_page_has_caveat_and_disclosure(repo):
    pages.build(repo, today=TODAY)
    text = _page(repo, "EA2")
    assert "One vendor, one product: Claude usage only" in text
    assert "These data are published by Anthropic" in text
    # One box, titled Disclosure, holding both (owner, 2026-11-19).
    assert ('::: {.callout-note title="Disclosure"}\n**One vendor, one product: Claude usage only.** '
            "These data are published by Anthropic") in text
    assert 'title="Caveat"' not in text


def test_generated_latest_data_bullet_in_data_and_calculation(repo):
    """Owner, 2026-11-19: every page's Data and calculation has one 'Latest data' bullet, generated
    from the primary series, so the Latest data row's More link always lands on it."""
    pages.build(repo, today=TODAY)
    for ind_id in RELEASE1:
        text = _page(repo, ind_id)
        section = text[text.index("## Data and calculation"):text.index("## Download the data")]
        assert section.count("- **Latest data.**") == 1, ind_id
        assert text.count("- **Latest data.**") == 1, ind_id
    ea2 = _page(repo, "EA2")
    assert "(May 2026). The value before it was" in ea2  # sample-window label, not a day
    assert "standard error" in _page(repo, "EA1")


def test_latest_data_bullet_names_a_break_and_a_missing_value():
    import pandas as pd
    from types import SimpleNamespace
    meta = SimpleNamespace(title="X", units="percent", frequency="quarterly")
    frame = pd.DataFrame({"date": pd.to_datetime(["2026-01-01", "2026-04-01"]), "value": [1.0, 2.0], "segment": [0, 1]})
    ind = SimpleNamespace(primary_series="x")
    line = pages.latest_data_bullet(ind, {"x": (frame, meta)})
    assert line == ("- **Latest data.** X: 2.0 percent (2026 Q2). The value before it was 1.0 percent (2026 Q1), "
                    "before a series break, so the two are not directly comparable.")
    assert pages.latest_data_bullet(ind, {}) == "- **Latest data.** Latest value not yet available (data still being collected)."


def test_ea2_method_groups_sit_inside_method_with_anchor(repo):
    """Owner, 2026-11-19: the full group definitions are part of Method; the chart links to them."""
    pages.build(repo, today=TODAY)
    text = _page(repo, "EA2")
    method, after = text.index("## Method\n"), text.index("## Caveats")
    anchor = text.index("### Method groups {#method-groups}")
    assert method < anchor < after
    assert "- **Group D: release of 26 June 2026" in text[anchor:after]
    assert "[Method groups](#method-groups)" in text  # pointer from What it shows
    assert '"groupsLink": "#method-groups"' in text


def test_every_indicator_page_ends_with_feedback_line(repo):
    """Owner decision (2026-11-19): the feedback line is the last line, after the downloads."""
    pages.build(repo, today=TODAY)
    for ind_id in RELEASE1:
        text = _page(repo, ind_id)
        assert text.rstrip().splitlines()[-1] == pages.FEEDBACK_LINE
        assert text.count("**Feedback.**") == 1
        assert text.index("## Download the data") < text.index("**Feedback.**")


def test_stale_badge_rendered_when_stale(repo):
    pages.build(repo, today=TODAY)
    assert "Stale since" not in _page(repo, "EA1")
    # The due date moves with each refresh, so fix the data's end here: 1 November 2026 + 45 days.
    _set_meta(repo, "btos_ai_use", data_through="2026-11-01", max_lag_days=45)
    pages.build(repo, today=date(2030, 1, 1))
    assert "Stale since 16 December 2026" in _page(repo, "EA1")


def test_all_pages_show_not_yet_reviewed(repo):
    pages.build(repo, today=TODAY)
    for ind_id in RELEASE1:
        assert "Not yet reviewed" in _page(repo, ind_id)
        assert "No reviewed readings yet" in _page(repo, ind_id)
    cells = _cells(_index(repo))
    for (row, _), body in cells.items():
        if row in ("Adoption", "Displacement") and "indicators/" in body:
            assert "Not yet reviewed" in body


def test_change_csv_for_change_views_only(repo):
    """Owner decision 2026-11-19: no 2010-19 trend line or deviation view; the change view's data."""
    pages.build(repo, today=TODAY)
    data = repo / "site" / "data"
    for sid in ("labor_share_nfb", "profit_share", "us_labor_tax_share", "oecd_labor_tax_share_avg"):
        frame = pd.read_csv(data / f"{sid}_changes.csv")
        assert list(frame.columns) == ["date", "window_years", "change", "segment", "base_mean", "base_sd", "base_n"]
        assert set(frame["window_years"]) == {1, 3, 5}
    for sid in ("btos_ai_use", "btos_ai_use_by_size", "aei_automation_share", "so_relative_index"):
        assert not (data / f"{sid}_changes.csv").exists()
    assert not list(data.glob("*_trend.csv"))
    assert (data / "btos_ai_use.csv").exists() and (data / "btos_ai_use.meta.json").exists()


def test_index_lockin_row_says_no_public_measure(repo):
    pages.build(repo, today=TODAY)
    cells = _cells(_index(repo))
    lockin = {d: body for (r, d), body in cells.items() if r == "Lock-in"}
    assert set(lockin) == {"Economic", "Government", "Cultural"}
    assert all("No public measure yet" in body for body in lockin.values())
    assert "No public measure yet" in cells[("Adoption", "Government")]
    assert "indicators/EA1.qmd" in cells[("Adoption", "Economic")]


def test_index_has_oversight_row_with_citation(repo):
    pages.build(repo, today=TODAY)
    text = _index(repo)
    block = text[text.index("Human deferral and oversight"):]
    block = block[:block.index("\n:::\n")]
    assert "No public measure yet" in block
    assert ("Nearest evidence: How AI agents shape experts' judgment calls, Anthropic Research, 27 October 2026 "
            "[(Herdağdelen et al. 2026a)](sources.qmd#herdagdelen2026a).") in block
    assert "https://www.anthropic.com" not in block


def test_counter_evidence_sources_link_the_sources_page(repo):
    pages.build(repo, today=TODAY)
    text = _index(repo)
    block = text[text.index("## Counter-evidence"):]
    assert "OECD Revenue Statistics" not in block  # the OECD item was removed from the panel 2026-11-19
    assert ("Source: Stanford HAI, AI Index Report 2026, Chapter 8 Policy and Governance (data from Digital Policy "
            "Alert and the AI Index) [(Sajadieh et al. 2026, 341, 343)](sources.qmd#sajadieh2026).") in block
    assert "https://hai.stanford.edu" not in block and "https://sdmx.oecd.org" not in block


def test_index_has_scales_note_placeholder_counter_evidence_and_archive(repo):
    pages.build(repo, today=TODAY)
    text = _index(repo)
    assert "**Rising**" in text and "**Within baseline**" in text
    assert "Laws about AI enacted: 25 US national laws" in text
    assert "The inclusion criteria were written before any items were added." in text
    assert "archive.qmd" in text


def test_unverified_curated_items_absent(repo):
    path = repo / "config" / "curated" / "counter_evidence.yaml"
    data = yaml.safe_load(path.read_text())
    data["items"].append(dict(data["items"][0], id="unverified_x", label="UNVERIFIED TEST ITEM",
                              verified=False, verified_on=None))
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    opath = repo / "config" / "curated" / "oversight.yaml"
    odata = yaml.safe_load(opath.read_text())
    odata["items"].append(dict(odata["items"][0], id="unverified_o", label="UNVERIFIED OVERSIGHT ITEM",
                               verified=False, verified_on=None))
    opath.write_text(yaml.safe_dump(odata, sort_keys=False, allow_unicode=True))
    pages.build(repo, today=TODAY)
    text = _index(repo)
    assert "UNVERIFIED TEST ITEM" not in text
    assert "UNVERIFIED OVERSIGHT ITEM" not in text
    assert "Laws about AI enacted: 25 US national laws" in text


def test_about_has_claude_disclosure():
    text = (ROOT / "site" / "about.qmd").read_text(encoding="utf-8")
    assert "built with assistance from Claude (Anthropic)" in text


def test_about_has_author_section_and_acronym():
    text = (ROOT / "site" / "about.qmd").read_text(encoding="utf-8")
    assert "## About the author" in text
    assert "Jeremy Richardson, Ph.D." in text
    assert "[OWNER TO EDIT]" not in text  # owner has written the bio (Task 10b)
    assert "https://richardsonlj.substack.com/" in text
    assert text.count("Key Evidence on Eroding Leverage") == 1
    assert "https://github.com/richardsonlj12/keel/issues/new?template=error-report.md" in text
    assert "https://github.com/richardsonlj12/keel/discussions" in text


def test_footer_and_substack_link_on_every_page():
    config = yaml.safe_load((ROOT / "site" / "_quarto.yml").read_text(encoding="utf-8"))
    footer = config["website"]["page-footer"]
    footer_text = yaml.safe_dump(footer)
    assert "by Jeremy Richardson" in footer_text
    assert "[Substack](https://richardsonlj.substack.com/)" in footer_text
    for qmd in (ROOT / "site").glob("*.qmd"):
        assert "page-footer" not in qmd.read_text(encoding="utf-8"), qmd.name


def test_site_url_uses_keel_base_path():
    config = yaml.safe_load((ROOT / "site" / "_quarto.yml").read_text(encoding="utf-8"))
    assert config["website"]["site-url"] == "https://richardsonlj12.github.io/keel/"
    assert config["website"]["navbar"]["title"] == "KEEL"
    for qmd in (ROOT / "site").glob("[!_]*.qmd"):
        assert "pagetitle:" in qmd.read_text(encoding="utf-8") and " · KEEL" in qmd.read_text(encoding="utf-8"), qmd.name
    assert config["project"]["output-dir"] == "_site"


def test_no_angle_bracket_placeholders_in_generated_qmd(repo):
    pages.build(repo, today=TODAY)
    generated = list((repo / "site" / "indicators").glob("*.qmd")) + [repo / "site" / "_generated" / "summary.md"]
    for path in generated:
        text = path.read_text(encoding="utf-8")
        tags = set(re.findall(r"<([^<>\s/]+)[^<>]*>", text))
        assert tags <= {"br"}, (path.name, tags)
        assert "%%" not in text, path.name


def _assert_no_internal_terms(name, text):
    for key in INTERNAL_KEYS:
        assert not re.search(rf"\b{key}\b", text, re.I), (name, key)
    for term in RETIRED_TERMS:
        assert not re.search(rf"\b{re.escape(term)}\b", text, re.I), (name, term)


def _synthetic_content(repo):
    for ind_id in RELEASE1:
        (repo / "content" / "indicators" / f"{ind_id}.md").write_text(SYNTHETIC_PAGE, encoding="utf-8")
    (repo / "content" / "methodology.md").write_text("Neutral methodology text.\n", encoding="utf-8")


def test_no_internal_keys_in_generated_text(repo):
    _synthetic_content(repo)
    pages.build(repo, today=TODAY)
    generated = list((repo / "site" / "indicators").glob("*.qmd")) + [repo / "site" / "_generated" / "summary.md"]
    for path in generated:
        _assert_no_internal_terms(path.name, re.sub(r"```\{ojs\}.*?```", "", path.read_text(encoding="utf-8"), flags=re.S))


QUARTO = shutil.which("quarto") or next((str(p) for p in [Path.home() / ".local/bin/quarto"] if p.exists()), None)


@pytest.mark.skipif(QUARTO is None, reason="Quarto is not installed")
def test_no_internal_keys_in_rendered_html(repo):
    """Render the whole site (generator text and static pages, synthetic prose) and check visible text."""
    _synthetic_content(repo)
    pages.build(repo, today=TODAY)
    subprocess.run([QUARTO, "render", str(repo / "site"), "--quiet"], check=True, capture_output=True)
    htmls = list((repo / "site" / "_site").rglob("*.html"))
    assert len(htmls) >= 9
    for path in htmls:
        html = path.read_text(encoding="utf-8")
        html = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
        visible = re.sub(r"<[^>]+>", " ", html)
        _assert_no_internal_terms(path.name, visible)


def _add_c1_index(repo):
    """Write a small so_relative_index series (as the Stack Exchange source would) into the copy."""
    (repo / "data" / "so_relative_index.csv").write_text(
        "date,value\n2019-12-01,100.0\n2026-09-01,61.5\n", encoding="utf-8")
    meta = json.loads((repo / "data" / "wiki_active_editors_en.meta.json").read_text(encoding="utf-8"))
    meta.update(series_id="so_relative_index", title="Stack Overflow activity relative to comparison sites "
                "(index, 2019 = 100)", units="index (2019 = 100)", data_through="2026-09-01", breaks=[])
    (repo / "data" / "so_relative_index.meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_c1_baseline_is_its_2012_to_2019_history(repo):
    _add_c1_index(repo)
    pages.build(repo, today=TODAY)
    desc = _value(dict(_table(_page(repo, "CD1")))["Latest data"]).split("<br>")[1]
    assert desc.endswith("compare its change with same-length changes in June 2012 to December 2019.")
    assert desc.startswith("61.5 (September 2026).")  # units already in the series title (owner, 2026-11-20)
    text = _page(repo, "CD1")
    method = text[text.index("## Method"):text.index("## Caveats")]
    # No 2010-19 trend baseline (the owner-approved timing line mentions "the mid-2010s", which is fine).
    assert "June 2012 to December 2019" in method and "2010 to 2019" not in method and "2010–19" not in method


def _drop_c1_index(repo):
    """Remove the Stack Exchange outputs, as before the backfill finished."""
    for pattern in ("so_*", "se_*"):
        for f in (repo / "data").glob(pattern):
            f.unlink()


def test_no_baseline_clause_without_a_value(repo):
    _drop_c1_index(repo)
    pages.build(repo, today=TODAY)
    line = _value(dict(_table(_page(repo, "CD1")))["Latest data"])
    assert line == "Latest value not yet available (data still being collected)"


def test_magnitude_line_names_the_series(repo):
    pages.build(repo, today=TODAY)
    line = dict(_table(_page(repo, "EA2")))["Latest data"]
    assert line.startswith("Automation share of categorized Claude.ai conversations<br>")


def test_oecd_annual_series_not_stale_today(repo):
    pages.build(repo, today=TODAY)
    assert "Stale" not in _page(repo, "GD1")


def test_split_content_rejects_unknown_sections_and_preamble():
    with pytest.raises(ValueError, match="unknown sections"):
        pages.split_content(SYNTHETIC_PAGE + "\n## Something else\n\nText.\n")
    front, body = SYNTHETIC_PAGE.split("---\n", 2)[1:]
    with pytest.raises(ValueError, match="before its first"):
        pages.split_content(f"---\n{front}---\nStray text.\n{body}")


def test_release2_readings_do_not_break_build(repo):
    reg_path = repo / "config" / "indicators.yaml"
    reg = yaml.safe_load(reg_path.read_text())
    reg["indicators"].append(dict(reg["indicators"][0], id="E9", release=2))
    reg_path.write_text(yaml.safe_dump(reg, sort_keys=False))
    with open(repo / "config" / "readings.yaml", "a", encoding="utf-8") as f:
        f.write("  - {indicator_id: E9, state: not_yet_reviewed, date: 2026-11-17, kind: current}\n")
    pages.build(repo, today=TODAY)
    assert not (repo / "site" / "indicators" / "E9.qmd").exists()


def test_caveat_has_single_period(repo):
    pages.build(repo, today=TODAY)
    text = _page(repo, "EA2")
    assert "**One vendor, one product: Claude usage only.**" in text
    assert "only..**" not in text


def test_e3_disclosure_names_keel(repo):
    pages.build(repo, today=TODAY)
    text = _page(repo, "EA2")
    assert ("These data are published by Anthropic, and KEEL is built with assistance from Claude. "
            "Treat them as data from an interested party.") in text
    assert text.count("published by Anthropic") == 1, "the disclosure appears once (owner decision)"
    assert "this site is built" not in text


def test_navbar_names_match_registry():
    config = yaml.safe_load((ROOT / "site" / "_quarto.yml").read_text(encoding="utf-8"))
    menu = next(i for i in config["website"]["navbar"]["left"] if i.get("text") == "Indicators")["menu"]
    reg = yaml.safe_load((ROOT / "config" / "indicators.yaml").read_text(encoding="utf-8"))
    names = {i["id"]: i["name"] for i in reg["indicators"] if i["release"] == 1}
    grid_order = [i for cell in reg["grid"] for i in cell["indicator_ids"]]
    expected = [(f"indicators/{i}.qmd", f"{names[i]} ({i})") for i in grid_order]
    assert [(m["href"], m["text"]) for m in menu] == expected


def test_navbar_has_sources_after_methodology():
    config = yaml.safe_load((ROOT / "site" / "_quarto.yml").read_text(encoding="utf-8"))
    hrefs = [i.get("href") for i in config["website"]["navbar"]["left"]]
    assert hrefs.index("sources.qmd") == hrefs.index("methodology.qmd") + 1
    item = config["website"]["navbar"]["left"][hrefs.index("sources.qmd")]
    assert item["text"] == "Sources"


def test_build_writes_sources_page(repo):
    pages.build(repo, today=TODAY)
    text = (repo / "site" / "_generated" / "sources.md").read_text(encoding="utf-8")
    assert "::: {#kulveit2025 .keel-ref}" in text


def test_feedback_form_link_on_about_page():
    text = (ROOT / "site" / "about.qmd").read_text(encoding="utf-8")
    assert f"({FORM_URL})" in text  # link text may vary; the URL must be there
    assert "[feedback form link]" not in text


def test_counter_evidence_intro_not_repeated(repo):
    pages.build(repo, today=TODAY)
    assert _index(repo).count("Inclusion says nothing about whether") == 1


def test_c1_says_data_still_being_collected_when_series_absent(repo):
    for f in (repo / "data").glob("s[oe]_*"):
        f.unlink()
    pages.build(repo, today=TODAY)
    text = _page(repo, "CD1")
    assert "Data still being collected" in text
    assert "Wikipedia" in text


def test_c1_views_listed_in_chart_spec(repo):
    pages.build(repo, today=TODAY)
    text = _page(repo, "CD1")
    for label in ("Relative activity index (2019 = 100)", "Change since November 2022",
                  "Year-over-year gap (alternative view)", "Monthly questions", "Wikipedia"):
        assert label in text
    assert "By firm size" in _page(repo, "EA1")
    for ind_id in ("ED1", "GD1"):
        text = _page(repo, ind_id)
        assert '"label": "Change over time"' in text and '"windows": [' in text
        assert "Deviation from" not in text and '"trend": true' not in text


def test_csv_links_relative(repo):
    pages.build(repo, today=TODAY)
    text = _page(repo, "ED1")
    assert "](../data/labor_share_nfb.csv)" in text
    assert "](../data/labor_share_nfb_changes.csv)" in text
    assert "](../archive.qmd)" in text


# ---- summary layout (owner-requested)

def test_layer_definitions_in_registry():
    from indicators import registry as r
    assert r.LAYER_DEFINITIONS == {
        "exposure": "Is AI entering the system, and how far?",
        "erosion": "Is the system's dependence on human participation falling, and by how much?",
        "lockin": "Is that reduced dependence becoming hard to restore?",
    }
    assert r.CROSS_CUTTING_DEFINITION == (
        "Are people handing decisions to AI? This applies across all three domains.")


def test_row_headers_have_accessible_definitions(repo):
    pages.build(repo, today=TODAY)
    text = _index(repo)
    for label, tip in (("Adoption", "Is AI entering the system, and how far?"),
                       ("Displacement", "Is the system's dependence on human participation falling, and by how much?"),
                       ("Lock-in", "Is that reduced dependence becoming hard to restore?"),
                       ("Cross-cutting", "Are people handing decisions to AI? This applies across all three domains.")):
        m = re.search(r'::: \{\.keel-rowhead\}\n\[\*\*' + re.escape(label) + r'\*\*\]\{([^}]*)\}\[([^\]]*)\]\{([^}]*)\}\n:::', text)
        assert m, label
        assert 'tabindex="0"' in m.group(1)
        tip_id = re.search(r'aria-describedby="([^"]+)"', m.group(1)).group(1)
        assert m.group(2) == tip
        assert f"#{tip_id}" in m.group(3) and 'role="tooltip"' in m.group(3)


def test_cross_cutting_row_has_title_then_content(repo):
    pages.build(repo, today=TODAY)
    text = _index(repo)
    i = text.index("**Cross-cutting**")
    j = text.index("::: {.keel-oversight}")
    assert i < j
    assert text[j:].split("\n", 2)[1].startswith("**Human deferral and oversight**")


def test_counter_evidence_directly_after_oversight_inside_grid(repo):
    pages.build(repo, today=TODAY)
    text = _index(repo)
    ov = text.index("::: {.keel-oversight}")
    after = text[text.index("\n:::\n", ov) + len("\n:::\n"):]
    assert after.lstrip().startswith(":::: {.keel-counter}")
    start = text.index(":::: {.keel-counter}")
    assert text.index("## Counter-evidence", start) - start < 60
    assert text.index("Inclusion criteria", start) > start
    assert "Two sets of labels" not in text[ov:text.index("archive.qmd")]


def test_no_data_are_telling_us_on_summary(repo):
    pages.build(repo, today=TODAY)
    text = _index(repo)
    assert "What the data are telling us" not in text
    assert "telling us" not in text


def test_about_the_indicators_callout_after_heading(repo):
    pages.build(repo, today=TODAY)
    text = _index(repo)
    m = re.search(r'^## Indicators \{#indicators\}\n\n'
                  r'::: \{#about-the-indicators \.callout-note collapse="true" title="About the indicators"\}\n', text, re.M)
    assert m, text[:1500]
    assert "About the labels" not in text
    box = text[m.end():text.index("\n:::\n", m.end())]
    assert box.startswith((repo / "content" / "summary-about-indicators.md").read_text(encoding="utf-8").strip()[:60])
    assert box.count("| Reading | Meaning |") == 3
    for name in ("Low", "Rising", "Pervasive", "Within baseline", "Above baseline", "Far below baseline",
                 "No signal / insufficient data", "Not yet reviewed"):
        assert f"**{name}**" in box


def test_about_box_text_comes_from_content_file(repo):
    (repo / "content" / "summary-about-indicators.md").write_text("Owner-edited box text.\n", encoding="utf-8")
    pages.build(repo, today=TODAY)
    assert 'title="About the indicators"}\nOwner-edited box text.\n:::' in _index(repo)


def test_summary_opens_with_intro_from_content_file(repo):
    """Owner, 2026-11-19: the welcome paragraph is content the owner edits directly."""
    (repo / "content" / "summary-intro.md").write_text("Owner-edited welcome.\n", encoding="utf-8")
    pages.build(repo, today=TODAY)
    generated = (repo / "site" / "_generated" / "summary.md").read_text(encoding="utf-8")
    assert generated.startswith("Owner-edited welcome.\n\n## Indicators {#indicators}")


def test_indicators_heading_accessible_text_is_plain(repo):
    pages.build(repo, today=TODAY)
    heading = next(l for l in _index(repo).splitlines() if l.startswith("## Indicators"))
    assert heading == "## Indicators {#indicators}"


def test_tooltip_ids_generated_by_rowhead():
    html = pages._rowhead("Lock-in", "Def.")
    assert 'aria-describedby="tip-lock-in"' in html and '#tip-lock-in .keel-tipbody role="tooltip"' in html


# ---- review fixes A

def _grouped_series(groups):
    frame = pd.DataFrame({"date": ["2020-01-01"] * len(groups), "value": [1.0] * len(groups), "group": groups})
    meta = type("M", (), {"title": "t", "units": "u", "frequency": "monthly", "breaks": []})()
    return {"so_questions_monthly": (frame, meta)}


def test_group_labels_only_for_groups_in_the_plotted_series():
    ind = type("I", (), {"id": "CD1", "chart_title": None, "name": "n"})()
    views = [{"label": "V", "kind": "multi", "series": ["so_questions_monthly"], "available": True}]
    labels = {"diy": "DIY", "travel": "Travel", "rpg": "RPG"}
    spec = pages.chart_spec(ind, views, _grouped_series(["diy", "rpg"]), [], labels)
    assert spec["groupLabels"] == {"diy": "DIY", "rpg": "RPG"}


def test_group_labels_absent_from_pages_without_groups(repo):
    pages.build(repo, today=TODAY)
    assert '"groupLabels": {}' in _page(repo, "ED1")
    assert "scifi" not in _page(repo, "ED1")


def test_retrospective_caveat_uses_the_indicators_own_frequency(repo):
    pages.build(repo, today=TODAY)
    assert "rule to every month from" in _page(repo, "CD1")
    assert "rule to every quarter from" in _page(repo, "ED1")
    assert "rule to every quarter from" in _page(repo, "GD1")  # its quarterly US series drives the reading


def test_ed1_profit_share_is_selectable_not_alongside(repo):
    pages.build(repo, today=TODAY)
    text = _page(repo, "ED1")
    assert "The profit share, selectable in the chart, is" in text
    assert "shown alongside" not in text


def test_pages_import_the_chart_module_with_data_table_support(repo):
    pages.build(repo, today=TODAY)
    assert 'from "../js/charts.js"' in _page(repo, "ED1")
    assert "Data table" in (ROOT / "site" / "js" / "charts.js").read_text(encoding="utf-8")


def test_cd1_default_view_is_first_available(repo):
    _drop_c1_index(repo)
    pages.build(repo, today=TODAY)
    text = _page(repo, "CD1")
    assert '"defaultView": "Wikipedia"' in text
    assert "The Stack Overflow index will appear here once its data download is complete." in text
    assert '"defaultView": "Level"' in _page(repo, "ED1")
    assert "will appear here once" not in _page(repo, "ED1")


def test_cd1_default_view_is_the_index_once_its_data_exist(repo):
    _add_c1_index(repo)
    for sid in ("so_relative_index_loo_min", "so_relative_index_loo_max"):
        shutil.copy(repo / "data" / "so_relative_index.csv", repo / "data" / f"{sid}.csv")
        shutil.copy(repo / "data" / "so_relative_index.meta.json", repo / "data" / f"{sid}.meta.json")
    pages.build(repo, today=TODAY)
    text = _page(repo, "CD1")
    assert '"defaultView": "Relative activity index (2019 = 100)"' in text
    assert "will appear here once" not in text


def test_series_breaks_listed_once_naming_every_affected_series(repo):
    pages.build(repo, today=TODAY)
    text = _page(repo, "EA2")
    block = text[text.index("- **Series breaks.**"):text.index("- **Chart markers.**")]
    lines = [l for l in block.splitlines() if re.match(r"\s+- \d", l)]
    assert len(lines) == 3
    assert all(" and " in l.split("): ", 1)[0] for l in lines)


def test_curated_caveat_renders_as_italic_line_under_counter_item(repo):
    path = repo / "config" / "curated" / "counter_evidence.yaml"
    data = yaml.safe_load(path.read_text())
    data["items"][0]["caveat"] = "A TEST CAVEAT sentence."
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    pages.build(repo, today=TODAY)
    block = _index(repo)
    block = block[block.index("## Counter-evidence"):]
    lines = block.split("\n")
    i = next(n for n, line in enumerate(lines) if "A TEST CAVEAT sentence." in line)
    assert lines[i] == "  *A TEST CAVEAT sentence.*"  # indented, so it belongs to the item above it
    assert lines[i - 1] == ""
    assert lines[i - 2].startswith("- **")


def test_items_without_caveat_render_no_italic_line(repo):
    path = repo / "config" / "curated" / "counter_evidence.yaml"
    data = yaml.safe_load(path.read_text())
    for item in data["items"]:
        item.pop("caveat", None)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
    pages.build(repo, today=TODAY)
    block = _index(repo)
    block = block[block.index("## Counter-evidence"):block.index("inclusion-criteria")]
    assert not [l for l in block.split("\n") if l.startswith("  *")]


def test_ai_law_item_has_new_label_and_caveat(repo):
    pages.build(repo, today=TODAY)
    block = _index(repo)
    block = block[block.index("## Counter-evidence"):]
    assert ("**Laws about AI enacted: 25 US national laws, 2016 to 2025, and 150 US state laws in 2025 "
            "(Stanford AI Index 2026)**") in block
    assert ("  *These are laws whose subject is AI, not laws drafted or generated by AI. The count includes laws that "
            "promote or fund AI as well as laws that restrict it, so it shows policy activity, not how far these laws "
            "keep human control. Included as policy activity; whether it counts as pushback is uncertain.*") in block


def test_oecd_item_removed_from_panel_but_kept_in_removed_list(repo):
    pages.build(repo, today=TODAY)
    text = _index(repo)
    assert "Labor-based taxes remain about half of OECD tax revenue" not in text
    raw = yaml.safe_load((repo / "config" / "curated" / "counter_evidence.yaml").read_text())
    assert "oecd_labor_tax_share" not in {i["id"] for i in raw["items"]}
    removed = raw["removed"]
    assert removed[0]["id"] == "oecd_labor_tax_share"
    assert removed[0]["reason"] == ("Removed 2026-11-19 (owner): a level, not data moving the opposite way "
                                    "(criterion 4); GD1 already shows these data.")


def test_panel_line_sits_after_items_before_inclusion_criteria(repo):
    pages.build(repo, today=TODAY)
    block = _index(repo)
    block = block[block.index("## Counter-evidence"):]
    line = "*Few items meet all four criteria so far; the panel will grow as evidence does.*"
    assert block.count(line) == 1
    assert block.rindex("\n- **") < block.index(line) < block.index("inclusion-criteria")


def test_oversight_row_shows_new_metric_and_caveat(repo):
    pages.build(repo, today=TODAY)
    text = _index(repo)
    block = text[text.index("Human deferral and oversight"):]
    block = block[:block.index("\n:::\n")]
    assert ("Share of analysts' decisions that matched the AI agent's randomly assigned lean, across four analytical "
            "decisions each (one study, 50 analysts; 50 percent expected by chance): 86 percent.") in block
    assert ("*The researchers deliberately strengthened the agent's lean, so this shows influence under a strong "
            "nudge. The pre-registered effect on analysts' final recommendations was not statistically significant. "
            "The 11 of 61 analysts who chose not to use the agent are excluded.*") in block


# --- Indicator codes linked on first mention per section (owner, 2026-11-20) ---

HREFS = {c: f"indicators/{c}.qmd" for c in ("EA1", "EA2", "ED1", "GD1", "CD1")}


def test_link_codes_first_mention_per_section():
    md = "Intro EA1 and EA1 again.\n\n## Next\n\nEA1 here, ED1 too, ED1 twice.\n\n### Sub\n\nEA1."
    out = pages.link_codes(md, HREFS)
    assert out.count("[EA1](indicators/EA1.qmd)") == 3
    assert out.count("[ED1](indicators/ED1.qmd)") == 1
    assert "Intro [EA1](indicators/EA1.qmd) and EA1 again." in out
    assert "## Next" in out and "### Sub" in out


def test_link_codes_skips_self_unknown_headings_code_attrs_and_fences():
    md = ("## About EA1 {#ea1-note}\n\nEA2 itself, CD2 later, `EA1` code, [x]{.keel EA1}.\n\n"
          "```\nEA1 in a fence\n```\nThen EA1.")
    out = pages.link_codes(md, HREFS, self_id="EA2")
    assert out.startswith("## About EA1 {#ea1-note}")
    assert "[EA2]" not in out and "[CD2]" not in out
    assert "`EA1`" in out and "{.keel EA1}" in out and "EA1 in a fence" in out
    assert out.endswith("Then [EA1](indicators/EA1.qmd).")


def test_link_codes_existing_link_counts_as_first_and_possessive():
    out = pages.link_codes("The [CD1 page](indicators/CD1.qmd) and CD1 again. GD1's base.", HREFS)
    assert out == "The [CD1 page](indicators/CD1.qmd) and CD1 again. [GD1](indicators/GD1.qmd)'s base."


def test_build_links_codes_in_methodology_and_indicator_pages(repo):
    pages.build(repo, today=TODAY)
    meth = (repo / "site" / "_generated" / "methodology.md").read_text(encoding="utf-8")
    assert "[EA1](indicators/EA1.qmd)" in meth and "[ED1](indicators/ED1.qmd)" in meth
    ea2 = _page(repo, "EA2")
    # EA2 mentions EA1 only as "Firm AI adoption (EA1)": shown with its name, so not linked.
    assert "Firm AI adoption (EA1)" in ea2 and "[EA1](EA1.qmd)" not in ea2 and "[EA2](EA2.qmd)" not in ea2
    for text in (meth, ea2):
        assert "[[" not in text and not re.search(r"\[[^\]]*\[[A-Z]{2}\d\]\(", text)


def test_break_note_url_becomes_a_citation():
    """Owner, 2026-11-20: a break note's source URL is cited on the Sources page, not shown raw."""
    from indicators.sources import wikimedia
    cites = bibliography.Citations(bibliography.load(Path(__file__).resolve().parents[1] / bibliography.BIB_PATH))
    text, key = pages.cited_note(wikimedia.BREAKS[0]["note"], cites)
    assert key == "miller2025" and "http" not in text and text.endswith("old classification.")
    assert pages.cited_note("Note. See: https://example.com/x", cites) == ("Note. See: https://example.com/x", None)
    assert pages.cited_note("No source.", cites) == ("No source.", None)


def test_code_shown_with_its_name_is_not_linked():
    """Owner, 2026-11-20: an abbreviation shown with its indicator's name needs no link."""
    names = {"ED1": ["labor share of income", "labor share"], "EA2": ["automation vs. augmentation", "how ai is used"]}
    hrefs = {"ED1": "ED1.qmd", "EA2": "EA2.qmd"}
    out = pages.link_codes("Labor share of income (ED1) falls. Then ED1 again.", hrefs, names=names)
    assert out == "Labor share of income (ED1) falls. Then [ED1](ED1.qmd) again."
    assert pages.link_codes("| ED1 Labor share |", hrefs, names=names) == "| ED1 Labor share |"
    assert pages.link_codes("indicators (ED1, labor share; EA2)", hrefs, names=names) == \
        "indicators (ED1, labor share; [EA2](EA2.qmd))"
    assert pages.link_codes("how AI is used (EA2), is", hrefs, names=names) == "how AI is used (EA2), is"
    assert pages.link_codes("2025 (EA1; x)", {"EA1": "EA1.qmd"}, names={"EA1": ["firm ai adoption"]}) == \
        "2025 ([EA1](EA1.qmd); x)"


def test_value_under_title_drops_units_the_title_already_names():
    from indicators.pages import fmt_value_under_title
    title = "Stack Overflow activity relative to comparison sites (index, 2019 = 100)"
    assert fmt_value_under_title(12.599, "index (2019 = 100)", title) == "12.6"
    assert fmt_value_under_title(53.0, "percent", "Labor share of income, nonfarm business sector") == "53.0 percent"
