#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
"""
VAHAN Dashboard Scraper
Fetches maker-wise monthly vehicle registration data from VAHAN.
Outputs vahan_data.json which is loaded by dashboard.html.

Usage:
    pip install requests beautifulsoup4
    python scrape_vahan.py

For state-level breakdown, edit FETCH_STATES list below.
"""

import requests
import json
import time
import re
import sys
from datetime import datetime
from xml.etree import ElementTree as ET

# ─── Configuration ────────────────────────────────────────────────────────────

# VAHAN maker names → friendly display names
# Edit these if VAHAN uses a slightly different company name
BRAND_ALIASES = {
    # Bajaj group
    "BAJAJ AUTO LTD":                                "BAJAJ AUTO LTD",
    "BAJAJ AUTO LIMITED":                            "BAJAJ AUTO LTD",
    # KTM (registered as KTM MOTORRAD AG in VAHAN)
    "KTM MOTORRAD AG":                               "KTM MOTORRAD AG",
    "KTM INDIA PVT LTD":                             "KTM MOTORRAD AG",
    "KTM INDIA PRIVATE LIMITED":                     "KTM MOTORRAD AG",
    # Triumph (Bajaj JV — confirmed VAHAN name)
    "TRIUMPH MOTORCYCLES (INDIA) PVT LTD":           "TRIUMPH MOTORCYCLES INDIA",
    "TRIUMPH MOTORCYCLES (INDIA) PRIVATE LIMITED":   "TRIUMPH MOTORCYCLES INDIA",
    "TRIUMPH MOTORCYCLES INDIA PVT LTD":             "TRIUMPH MOTORCYCLES INDIA",
    "TRIUMPH MOTORCYCLES INDIA PRIVATE LIMITED":     "TRIUMPH MOTORCYCLES INDIA",
    "TRIUMPH MOTORCYCLES LIMITED":                   "TRIUMPH MOTORCYCLES INDIA",
    # Husqvarna (Bajaj group, built at Chakan)
    "HUSQVARNA MOTORCYCLES INDIA":                   "HUSQVARNA",
    "HUSQVARNA MOTORCYCLES PVT LTD":                 "HUSQVARNA",
    "HUSQVARNA MOTORCYCLES INDIA PVT LTD":           "HUSQVARNA",
    "HUSQVARNA":                                     "HUSQVARNA",
    # Chetak (Bajaj EV brand, separate subsidiary)
    "CHETAK TECHNOLOGY LIMITED":                     "CHETAK TECHNOLOGY LTD",
    "CHETAK TECHNOLOGY LTD":                         "CHETAK TECHNOLOGY LTD",
    "CHETAK ELECTRIC":                               "CHETAK TECHNOLOGY LTD",
    # Bgauss
    "BGAUSS AUTO PRIVATE LIMITED":                   "BGAUSS AUTO PVT LTD",
    "BGAUSS AUTO PVT LTD":                           "BGAUSS AUTO PVT LTD",
    "BGAUSS AUTO PVT. LTD":                          "BGAUSS AUTO PVT LTD",
    # Ampere / Greaves Electric (Ampere is the brand; VAHAN uses Greaves entity)
    "GREAVES ELECTRIC MOBILITY LTD":                 "AMPERE VEHICLES PVT LTD",
    "GREAVES ELECTRIC MOBILITY LIMITED":             "AMPERE VEHICLES PVT LTD",
    "GREAVES ELECTRIC MOBILITY PRIVATE LIMITED":     "AMPERE VEHICLES PVT LTD",
    "AMPERE VEHICLES PRIVATE LIMITED":               "AMPERE VEHICLES PVT LTD",
    "AMPERE VEHICLES PVT LTD":                       "AMPERE VEHICLES PVT LTD",
    "AMPERE VEHICLES PVT. LTD.":                     "AMPERE VEHICLES PVT LTD",
    # Ather
    "ATHER ENERGY LTD":                              "ATHER ENERGY LTD",
    "ATHER ENERGY PRIVATE LIMITED":                  "ATHER ENERGY LTD",
    "ATHER ENERGY LIMITED":                          "ATHER ENERGY LTD",
    # Piaggio (confirmed VAHAN name)
    "PIAGGIO VEHICLES PVT LTD":                      "PIAGGIO VEHICLES PVT LTD",
    "PIAGGIO VEHICLES PRIVATE LIMITED":              "PIAGGIO VEHICLES PVT LTD",
    "PIAGGIO VEHICLES PVT. LTD.":                    "PIAGGIO VEHICLES PVT LTD",
}

# Display config for each canonical brand
BRANDS = {
    "BAJAJ AUTO LTD":               {"label": "Bajaj Auto",    "group": "bajaj",  "color": "#f97316"},
    "KTM MOTORRAD AG":              {"label": "PB-KTM",        "group": "bajaj",  "color": "#ef4444"},
    "TRIUMPH MOTORCYCLES INDIA":    {"label": "Triumph",       "group": "bajaj",  "color": "#06b6d4"},
    "HUSQVARNA":                    {"label": "Husqvarna",     "group": "bajaj",  "color": "#8b5cf6"},
    "CHETAK TECHNOLOGY LTD":        {"label": "Chetak",        "group": "bajaj",  "color": "#22c55e"},
    "BGAUSS AUTO PVT LTD":          {"label": "Bgauss",        "group": "ev",     "color": "#ec4899"},
    "AMPERE VEHICLES PVT LTD":      {"label": "Ampere",        "group": "ev",     "color": "#3b82f6"},
    "ATHER ENERGY LTD":             {"label": "Ather Energy",  "group": "ev",     "color": "#eab308"},
    "PIAGGIO VEHICLES PVT LTD":     {"label": "Piaggio",       "group": "other",  "color": "#14b8a6"},
}

# Vehicle category groups to fetch — VhCatg checkbox values sent as a list
VEH_CATEGORIES = {
    "2W": ["2WIC", "2WN", "2WT"],
    "3W": ["3WIC", "3WN", "3WT"],
}

# States to fetch breakdown for (add/remove as needed; '' = all India)
FETCH_STATES = [
    ("-1", "All India"),
    # Uncomment below for state-level breakdown (adds ~70 more requests)
    # ("MH", "Maharashtra"), ("RJ", "Rajasthan"), ("UP", "Uttar Pradesh"),
    # ("KA", "Karnataka"), ("TN", "Tamil Nadu"), ("GJ", "Gujarat"),
    # ("HR", "Haryana"), ("AP", "Andhra Pradesh"), ("TG", "Telangana"),
    # ("MP", "Madhya Pradesh"), ("WB", "West Bengal"), ("BR", "Bihar"),
    # ("DL", "Delhi"), ("KL", "Kerala"), ("PB", "Punjab"),
    # ("OR", "Odisha"), ("JH", "Jharkhand"), ("CG", "Chhattisgarh"),
    # ("UK", "Uttarakhand"), ("HP", "Himachal Pradesh"), ("JK", "Jammu and Kashmir"),
    # ("AS", "Assam"), ("GA", "Goa"), ("CH", "Chandigarh"),
]

YEARS_TO_FETCH = [2025, 2026]
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

# ─── Scraper ──────────────────────────────────────────────────────────────────

VAHAN_URL = "https://vahan.parivahan.gov.in/vahan4dashboard/vahan/view/reportview.xhtml"

class VAHANScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self.view_state = None

    def init_session(self):
        print("→ Connecting to VAHAN…")
        resp = self.session.get(VAHAN_URL, timeout=30)
        resp.raise_for_status()
        # Match name="javax.faces.ViewState" with optional attributes (e.g. id=) between name and value
        m = re.search(r'name="javax\.faces\.ViewState"[^>]*?value="([^"]+)"', resp.text)
        if not m:
            # Fallback: match value first, then name on same input tag
            m = re.search(r'value="([^"]+)"[^>]*?name="javax\.faces\.ViewState"', resp.text)
        if not m:
            raise RuntimeError("Could not extract ViewState — VAHAN layout may have changed.")
        self.view_state = m.group(1)
        print(f"  Session OK. ViewState: {self.view_state[:20]}…")

    # ── POST helpers ──────────────────────────────────────────────────────────

    def _base_params(self, year, state, veh_cat):
        params = {
            "javax.faces.partial.ajax": "true",
            "javax.faces.source": "j_idt70",
            "javax.faces.partial.execute": "@all",
            "javax.faces.partial.render":
                "VhCatg norms fuel VhClass combTablePnl groupingTable msg vhCatgPnl",
            "j_idt70": "j_idt70",
            "masterLayout_formlogin": "masterLayout_formlogin",
            "j_idt31_focus": "", "j_idt31_input": "A",
            "j_idt39_focus": "", "j_idt39_input": state,
            "selectedRto_focus": "", "selectedRto_input": "-1",
            "yaxisVar_focus": "", "yaxisVar_input": "Maker",
            "xaxisVar_focus": "", "xaxisVar_input": "Month Wise",
            "selectedYearType_focus": "", "selectedYearType_input": "C",
            "selectedYear_focus": "", "selectedYear_input": str(year),
            "VhCatg": VEH_CATEGORIES[veh_cat],  # list of checkbox values
            "javax.faces.ViewState": self.view_state,
        }
        return params

    def _paginator_params(self, first_row):
        return {
            "javax.faces.partial.ajax": "true",
            "javax.faces.source": "groupingTable",
            "javax.faces.partial.execute": "groupingTable",
            "javax.faces.partial.render": "groupingTable",
            "masterLayout_formlogin": "masterLayout_formlogin",
            "groupingTable_pagination": "true",
            "groupingTable_first": str(first_row),
            "groupingTable_rows": "25",
            "groupingTable_encodeFeature": "true",
            "javax.faces.ViewState": self.view_state,
        }

    def _ajax_headers(self):
        return {
            "Accept": "application/xml, text/xml, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Faces-Request": "partial/ajax",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://vahan.parivahan.gov.in",
            "Referer": VAHAN_URL,
        }

    def _post(self, params):
        resp = self.session.post(VAHAN_URL, data=params,
                                  headers=self._ajax_headers(), timeout=60)
        resp.raise_for_status()
        return resp.text

    # ── XML / HTML parsing ────────────────────────────────────────────────────

    def _extract_from_xml(self, xml_text):
        """Return (table_html, new_view_state) from JSF partial response.

        Initial load returns groupingTable inside combTablePnl CDATA;
        pagination requests return groupingTable as a direct update element.
        """
        # Update ViewState via regex first (works regardless of XML parse success)
        new_vs = None
        vs_m = re.search(r'<update id="j_id1:javax\.faces\.ViewState:0"[^>]*><!\[CDATA\[(.*?)\]\]>', xml_text, re.DOTALL)
        if not vs_m:
            vs_m = re.search(r'<update id="javax\.faces\.ViewState"[^>]*><!\[CDATA\[(.*?)\]\]>', xml_text, re.DOTALL)
        if vs_m:
            new_vs = vs_m.group(1).strip()

        # Try direct groupingTable update (pagination responses)
        m = re.search(r'<update id="groupingTable"[^>]*><!\[CDATA\[(.*?)\]\]>', xml_text, re.DOTALL)
        if m:
            return m.group(1), new_vs

        # Initial load: groupingTable is inside combTablePnl CDATA
        m = re.search(r'<update id="combTablePnl"[^>]*><!\[CDATA\[(.*?)\]\]>', xml_text, re.DOTALL)
        if m:
            return m.group(1), new_vs

        # Fallback: XML parse
        xml_text_safe = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#)", "&amp;", xml_text)
        try:
            root = ET.fromstring(xml_text_safe)
            for el in root.iter():
                eid = el.get("id", "")
                if eid in ("groupingTable", "combTablePnl"):
                    return el.text or "", new_vs
        except ET.ParseError:
            pass

        return "", new_vs

    def _parse_table(self, html):
        """Extract {maker_name: {MON: count, …}} from table HTML."""
        makers = {}
        # Match data rows (have class with "ui-widget-content")
        row_pat = re.compile(
            r'<tr[^>]+class="[^"]*ui-widget-content[^"]*"[^>]*>(.*?)</tr>',
            re.DOTALL | re.IGNORECASE
        )
        cell_pat = re.compile(r'<td[^>]*>(.*?)</td>', re.DOTALL | re.IGNORECASE)
        tag_pat  = re.compile(r'<[^>]+>')

        for row_m in row_pat.finditer(html):
            raw_cells = cell_pat.findall(row_m.group(1))
            cells = [tag_pat.sub("", c).replace(",", "").replace("\xa0", "").strip()
                     for c in raw_cells]
            cells = [c for c in cells if c]

            if len(cells) < 3:
                continue
            # cells: [serial, maker, JAN, FEB, …, TOTAL]
            maker = cells[1].strip().upper()
            if maker in ("MAKER", "S NO", "TOTAL", ""):
                continue

            month_vals = cells[2:-1]  # strip serial, maker, total
            month_data = {}
            for i, mon in enumerate(MONTHS[:len(month_vals)]):
                try:
                    v = month_vals[i]
                    month_data[mon] = int(v) if v.lstrip("-").isdigit() else 0
                except (ValueError, IndexError):
                    month_data[mon] = 0
            makers[maker] = month_data

        return makers

    def _has_next_page(self, html):
        """Return True if the paginator Next button is not disabled."""
        # Match class="... ui-paginator-next ..." on the <a> element
        m = re.search(r'<a[^>]*class="([^"]*ui-paginator-next[^"]*)"', html)
        if m:
            return "ui-state-disabled" not in m.group(1)
        return False

    # ── Public API ────────────────────────────────────────────────────────────

    def fetch_year(self, year, state, veh_cat):
        """Return all maker data for one year/state/category.

        Uses the Next-button state on the initial page, then row count
        (25 rows = more pages; <25 = last page) on subsequent pages.
        """
        print(f"  Fetching {veh_cat} / {year} / state={state} …", end=" ", flush=True)

        xml  = self._post(self._base_params(year, state, veh_cat))
        html, new_vs = self._extract_from_xml(xml)
        if new_vs:
            self.view_state = new_vs

        all_makers = self._parse_table(html)
        has_more = self._has_next_page(html)
        page_idx = 1

        while has_more:
            time.sleep(0.8)
            first_row = page_idx * 25
            xml  = self._post(self._paginator_params(first_row))
            html, new_vs = self._extract_from_xml(xml)
            if new_vs:
                self.view_state = new_vs
            new_rows = self._parse_table(html)
            if not new_rows:
                break
            all_makers.update(new_rows)
            page_idx += 1
            if page_idx % 20 == 0:
                print(f"…{page_idx}", end="", flush=True)
            # Pagination responses don't include paginator HTML;
            # keep going while we get a full page of 25 rows
            has_more = len(new_rows) >= 25

        print(f"{page_idx} pages → {len(all_makers)} makers total")
        return all_makers

    def normalise_maker(self, raw_name):
        """Map raw VAHAN name to canonical brand name (or None if not a target)."""
        up = raw_name.upper().strip()
        # Exact match first
        if up in BRAND_ALIASES:
            return BRAND_ALIASES[up]
        # Partial match
        for alias, canonical in BRAND_ALIASES.items():
            if alias in up or up in alias:
                return canonical
        return None


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    scraper = VAHANScraper()
    scraper.init_session()

    result = {
        "generated_at": datetime.now().isoformat(),
        "brands": {name: {"label": cfg["label"], "color": cfg["color"],
                          "group": cfg["group"],
                          "monthly": {"2025": {}, "2026": {}},
                          "states": {}}
                   for name, cfg in BRANDS.items()},
        "states_fetched": [],
    }

    for veh_cat in VEH_CATEGORIES:
        for state_code, state_name in FETCH_STATES:
            for year in YEARS_TO_FETCH:
                time.sleep(1.0)
                # Always re-init before each fetch — session expires after many pages
                try:
                    scraper.init_session()
                except Exception as e:
                    print(f"  Session init failed: {e}")

                for attempt in range(3):
                    try:
                        raw = scraper.fetch_year(year, state_code, veh_cat)
                        break
                    except Exception as e:
                        print(f"  ERROR (attempt {attempt+1}/3): {e}")
                        if attempt < 2:
                            print(f"  Retrying in 5s…")
                            time.sleep(5)
                            try:
                                scraper.init_session()
                            except Exception:
                                pass
                        else:
                            raw = {}
                            break

                for raw_name, month_data in raw.items():
                    canonical = scraper.normalise_maker(raw_name)
                    if not canonical or canonical not in result["brands"]:
                        continue

                    brand = result["brands"][canonical]

                    if state_code == "-1":
                        # All India monthly totals
                        existing = brand["monthly"][str(year)]
                        for mon, val in month_data.items():
                            existing[mon] = existing.get(mon, 0) + val
                    else:
                        # State totals (sum across months)
                        total = sum(month_data.values())
                        brand["states"][state_name] = \
                            brand["states"].get(state_name, 0) + total

    if FETCH_STATES:
        result["states_fetched"] = [s for _, s in FETCH_STATES if s != "All India"]

    out = "vahan_data.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n✓ Saved to {out}")
    print("  Open dashboard.html in a browser (or run: python -m http.server 8080)")

    # Quick summary
    for canonical, brand in result["brands"].items():
        totals_25 = sum(brand["monthly"]["2025"].values())
        totals_26 = sum(brand["monthly"]["2026"].values())
        if totals_25 or totals_26:
            print(f"  {brand['label']:20s} 2025: {totals_25:>8,}   2026 YTD: {totals_26:>8,}")


if __name__ == "__main__":
    main()
