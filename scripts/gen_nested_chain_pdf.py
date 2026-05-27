"""
Generate a test PDF with nested tables spanning 3-4 pages.

Layout:
  p1: Title page
  p2: Intro text
  p3-p6: Main 5-col table with nested sub-tables inside "Detail" cells
  p7: Summary + simple table

Nested structure: Each "Detail" cell in the main table contains a
mini 3-column sub-table (Sub-Item, Value, Rate).
"""
from fpdf import FPDF

class P(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "", 8)
        self.cell(0, 10, f"- {self.page_no()} -", new_x="LMARGIN", new_y="NEXT", align="C")

pdf = P()
pdf.set_auto_page_break(auto=True, margin=20)

# ── Page 1: Title ──────────────────────────────────────────────────
pdf.add_page()
pdf.set_font("Helvetica", "B", 16)
pdf.cell(0, 10, "Test: Nested Multi-Page Table", new_x="LMARGIN", new_y="NEXT", align="C")
pdf.ln(5)
pdf.set_font("Helvetica", "", 11)
pdf.multi_cell(0, 6,
    "Main table spans p.3-p.6 with nested sub-tables inside 'Detail' cells. "
    "Each sub-table has 3 columns (Sub-Item, Value, Rate).")

# ── Page 2: Intro ─────────────────────────────────────────────────
pdf.add_page()
pdf.set_font("Helvetica", "B", 13)
pdf.cell(0, 10, "1. Document Overview", new_x="LMARGIN", new_y="NEXT")
pdf.ln(3)
pdf.set_font("Helvetica", "", 10)
pdf.multi_cell(0, 6,
    "This document tests nested table extraction. The main table on pages 3-6 "
    "contains a 'Detail' column where each cell holds a 3-column sub-table "
    "breaking down the line item further.")

pdf.ln(8)
pdf.set_font("Helvetica", "B", 13)
pdf.cell(0, 10, "2. Consolidated Balance Sheet (with sub-items)", new_x="LMARGIN", new_y="NEXT")
pdf.ln(3)
pdf.multi_cell(0, 6, "Below: Full-page table with nested detail tables. Continues across pages 3-6.")

# ── Pages 3-6: Main table with nested sub-tables ──────────────────
# Main cols: Category | Account | Prior(M) | Curr(M) | Detail (nested)
MCW = [38, 35, 28, 28, 61]  # main column widths, total = 190

def draw_main_header():
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(219, 234, 254)
    headers = ["Category", "Account", "Prior(M)", "Curr(M)", "Detail (Sub-Table)"]
    for i, h in enumerate(headers):
        pdf.cell(MCW[i], 7, h, border=1, align="C", fill=True)
    pdf.ln()

def draw_subtable(rows, x_start, y_start, available_w):
    """Draw a mini 3-col sub-table at (x_start, y_start)."""
    sw = [available_w * r for r in [0.45, 0.30, 0.25]]
    saved_x, saved_y = pdf.get_x(), pdf.get_y()

    pdf.set_xy(x_start, y_start)
    pdf.set_font("Helvetica", "B", 6.5)
    pdf.set_fill_color(240, 248, 255)
    for i, h in enumerate(["Sub-Item", "Value", "Rate"]):
        pdf.cell(sw[i], 5, h, border=1, align="C", fill=True)
    pdf.ln()

    pdf.set_font("Helvetica", "", 6.5)
    pdf.set_fill_color(255, 255, 255)
    for row in rows:
        pdf.set_x(x_start)
        for i, v in enumerate(row):
            pdf.cell(sw[i], 4.5, v, border=1, align="R" if i >= 1 else "L")
        pdf.ln()

    pdf.set_xy(saved_x, saved_y)

def draw_main_row(cat, acct, prior, curr, detail_rows):
    """Draw one main table row with a nested sub-table in the Detail cell."""
    row_h = 5 + len(detail_rows) * 4.5 + 0.5  # header + rows

    x0 = pdf.get_x()
    y0 = pdf.get_y()
    page_w = pdf.w - pdf.l_margin - pdf.r_margin

    # Check if this row fits on the page
    if y0 + row_h > pdf.h - pdf.b_margin - 5:
        pdf.add_page()
        draw_main_header()
        x0 = pdf.get_x()
        y0 = pdf.get_y()

    # Draw outer cells (text)
    pdf.set_font("Helvetica", "", 8)

    # Category cell
    pdf.set_xy(x0, y0)
    pdf.cell(MCW[0], row_h, cat, border=1, align="L")
    # Account cell
    pdf.set_xy(x0 + MCW[0], y0)
    pdf.cell(MCW[1], row_h, acct, border=1, align="L")
    # Prior cell
    pdf.set_xy(x0 + sum(MCW[:2]), y0)
    pdf.cell(MCW[2], row_h, prior, border=1, align="R")
    # Curr cell
    pdf.set_xy(x0 + sum(MCW[:3]), y0)
    pdf.cell(MCW[3], row_h, curr, border=1, align="R")
    # Detail cell border
    pdf.set_xy(x0 + sum(MCW[:4]), y0)
    pdf.cell(MCW[4], row_h, "", border=1)

    # Draw nested sub-table inside Detail cell
    detail_x = x0 + sum(MCW[:4]) + 1
    detail_y = y0 + 1
    draw_subtable(detail_rows, detail_x, detail_y, MCW[4] - 2)

    pdf.set_xy(x0, y0 + row_h)


# ── Data ───────────────────────────────────────────────────────────
ROWS = [
    ("Assets", "A100", "523,450", "612,800", [
        ("Cash & Equiv", "102,300", "+14.7%"),
        ("ST Securities", "95,600", "+21.9%"),
        ("Trade Receiv.", "100,600", "+51.3%"),
        ("Other Receiv.", "15,600", "+26.8%"),
    ]),
    ("Assets", "A110", "156,300", "178,400", [
        ("Finished Goods", "52,100", "+15.3%"),
        ("Work in Process", "38,900", "+12.8%"),
        ("Raw Materials", "48,000", "+10.9%"),
    ]),
    ("Assets", "A120", "89,200", "95,600", [
        ("Operating Lease", "56,700", "+25.4%"),
        ("Finance Lease", "38,900", "+12.8%"),
    ]),
    ("Assets", "A200", "892,300", "945,600", [
        ("Land", "123,400", "N/C"),
        ("Buildings", "245,600", "+4.7%"),
        ("Machinery", "89,200", "+13.1%"),
        ("Vehicles", "25,600", "+9.4%"),
    ]),
    ("Assets", "A210", "456,700", "478,900", [
        ("Gross PP&E", "598,400", "+5.4%"),
        ("Accum. Depr.", "-119,500", "+7.6%"),
    ]),
    ("Assets", "A220", "234,500", "256,700", [
        ("Goodwill", "167,800", "+7.1%"),
        ("Software", "56,700", "+24.3%"),
        ("Patents & Lic.", "25,600", "+9.4%"),
    ]),
    ("Assets", "A230", "145,600", "156,800", [
        ("Office Buildings", "89,400", "+7.2%"),
        ("Retail Space", "67,400", "+10.1%"),
    ]),
    ("Assets", "A240", "55,500", "53,200", [
        ("LT Bonds", "34,500", "-4.3%"),
        ("LT Equities", "18,700", "+2.1%"),
    ]),
    ("Assets", "A300", "1,415,750", "1,558,400", [
        ("Total Current", "612,800", "+17.1%"),
        ("Total Non-Curr", "945,600", "+6.0%"),
    ]),
    ("Liabilities", "B100", "312,400", "356,700", [
        ("Trade Payables", "102,300", "+14.3%"),
        ("ST Debt", "78,900", "+16.4%"),
        ("Accrued Exp.", "56,700", "+24.3%"),
    ]),
    ("Liabilities", "B110", "156,700", "178,900", [
        ("Bank Loans", "102,300", "+14.4%"),
        ("Corp. Bonds", "56,700", "+24.3%"),
        ("Other LT Debt", "19,900", "-8.3%"),
    ]),
    ("Liabilities", "B120", "234,500", "267,800", [
        ("LT Debt Total", "178,900", "+14.2%"),
        ("Lease Liab.", "38,900", "+12.8%"),
        ("Severance", "38,900", "+20.8%"),
    ]),
    ("Liabilities", "B130", "546,900", "624,500", [
        ("Current Liab.", "356,700", "+14.2%"),
        ("Non-Current", "267,800", "+14.2%"),
    ]),
    ("Equity", "C100", "868,850", "933,900", [
        ("Capital Stock", "100,000", "N/C"),
        ("Capital Surplus", "256,700", "+9.5%"),
        ("Retained Earn.", "523,400", "+9.3%"),
        ("Treasury Stock", "-15,600", "+26.8%"),
    ]),
    ("Equity", "C110", "478,900", "523,400", [
        ("Legal Reserve", "25,600", "+9.4%"),
        ("Other RE", "497,800", "+9.3%"),
    ]),
    ("Equity", "C120", "234,500", "256,700", [
        ("Share Premium", "201,200", "+6.2%"),
        ("Other Surplus", "55,500", "+23.1%"),
    ]),
    ("Total", "Z999", "1,415,750", "1,558,400", [
        ("Total Liab.", "624,500", "+14.2%"),
        ("Total Equity", "933,900", "+7.5%"),
    ]),
    ("Revenue", "D100", "1,234,500", "1,456,700", [
        ("Product Sales", "987,600", "+17.5%"),
        ("Service Rev.", "312,300", "+19.8%"),
        ("Licensing", "156,800", "+22.1%"),
    ]),
    ("COGS", "D200", "890,200", "1,023,400", [
        ("Materials", "456,700", "+16.2%"),
        ("Labor", "312,300", "+12.8%"),
        ("Overhead", "178,900", "+10.5%"),
        ("Depreciation", "75,500", "+8.9%"),
    ]),
    ("Gross Profit", "D300", "344,300", "433,300", [
        ("Margin %", "29.1%", "30.4%"),
    ]),
    ("SG&A", "D400", "123,400", "145,600", [
        ("Salaries", "67,800", "+14.2%"),
        ("Marketing", "34,500", "+18.9%"),
        ("Rent & Utilities", "23,400", "+8.7%"),
        ("Other SG&A", "19,900", "+12.3%"),
    ]),
    ("Op. Profit", "D500", "220,900", "287,700", [
        ("EBIT Margin", "17.9%", "19.7%"),
    ]),
    ("Net Income", "D600", "161,200", "214,800", [
        ("Tax Expense", "45,600", "+28.3%"),
        ("Net Margin", "13.1%", "14.7%"),
    ]),
    ("Cash Flow", "E100", "189,400", "234,500", [
        ("Operating", "234,500", "+23.8%"),
        ("Investing", "-95,600", "+21.2%"),
        ("Financing", "-67,800", "+48.7%"),
    ]),
    ("Segment A", "F100", "456,700", "534,200", [
        ("Product A1", "189,400", "+18.9%"),
        ("Product A2", "145,600", "+15.6%"),
        ("Product A3", "123,400", "+22.3%"),
        ("Returns", "-23,200", "+12.1%"),
    ]),
    ("Segment B", "F200", "389,200", "445,600", [
        ("Product B1", "167,800", "+19.3%"),
        ("Product B2", "134,500", "+14.7%"),
        ("Product B3", "98,700", "+21.8%"),
        ("Warranty", "-15,400", "+8.9%"),
        ("Other", "20,000", "+5.2%"),
    ]),
    ("Segment C", "F300", "234,500", "289,700", [
        ("Consulting", "123,400", "+16.8%"),
        ("Maintenance", "78,900", "+12.3%"),
        ("Training", "45,600", "+28.9%"),
        ("Support", "41,800", "+19.7%"),
    ]),
    ("Segment D", "F400", "154,100", "187,200", [
        ("Domestic", "98,700", "+14.5%"),
        ("Export", "67,400", "+26.8%"),
        ("Licensing", "21,100", "+18.3%"),
    ]),
    ("Region Asia", "G100", "567,800", "654,300", [
        ("Korea", "234,500", "+12.8%"),
        ("Japan", "145,600", "+18.9%"),
        ("China", "123,400", "+22.3%"),
        ("SE Asia", "98,700", "+19.7%"),
        ("Other Asia", "52,100", "+15.6%"),
    ]),
    ("Region Europe", "G200", "345,600", "389,200", [
        ("Germany", "134,500", "+14.7%"),
        ("UK", "98,700", "+16.8%"),
        ("France", "67,400", "+12.3%"),
        ("Nordics", "34,600", "+19.7%"),
    ]),
    ("Region Americas", "G300", "321,400", "413,200", [
        ("USA", "189,400", "+23.8%"),
        ("Canada", "67,800", "+18.9%"),
        ("Brazil", "45,600", "+28.3%"),
        ("Other", "110,400", "+31.2%"),
    ]),
]

pdf.add_page()
draw_main_header()

for cat, acct, prior, curr, detail in ROWS:
    draw_main_row(cat, acct, prior, curr, detail)

pdf.ln(5)
pdf.set_font("Helvetica", "", 11)
pdf.multi_cell(0, 6, "End of consolidated balance sheet with nested sub-tables.")

# ── Page 7: Summary ───────────────────────────────────────────────
pdf.add_page()
pdf.set_font("Helvetica", "B", 13)
pdf.cell(0, 10, "3. Summary", new_x="LMARGIN", new_y="NEXT")
pdf.ln(3)
pdf.set_font("Helvetica", "", 10)

cw4 = [50, 40, 40, 40]
pdf.set_font("Helvetica", "B", 10)
pdf.set_fill_color(219, 234, 254)
for i, h in enumerate(["Item", "Prior(M)", "Curr(M)", "Chg"]):
    pdf.cell(cw4[i], 7, h, border=1, align="C", fill=True)
pdf.ln()
pdf.set_font("Helvetica", "", 10)
for r in [
    ("Total Assets", "1,415,750", "1,558,400", "+10.1%"),
    ("Total Liab.", "546,900", "624,500", "+14.2%"),
    ("Total Equity", "868,850", "933,900", "+7.5%"),
    ("Net Income", "161,200", "214,800", "+33.3%"),
]:
    for i, v in enumerate(r):
        pdf.cell(cw4[i], 7, v, border=1, align="R" if i >= 1 else "L")
    pdf.ln()

out = "/Users/a452779/Desktop/agent/corp/pdftablesearch/test_nested_chain.pdf"
pdf.output(out)
print(f"Created: {out}, Pages: {pdf.pages_count}")
