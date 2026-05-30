"""Generate a test PDF with a table spanning 3+ pages for multi-page table detection testing.

Layout:
  p1: title + intro text
  p2: a small table + text
  p3: large table STARTS near bottom (rows 1-5)
  p4: large table CONTINUES (rows 6-20)
  p5: large table CONTINUES near top (rows 21-30)
  p6: different table + text
  p7: text only
  p8: another table
"""
from fpdf import FPDF

FONT = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"

class TestPDF(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font("gothic", "", 8)
        self.cell(0, 10, f"- {self.page_no()} -", align="C")


pdf = TestPDF()
pdf.add_font("gothic", "", FONT, uni=True)
pdf.add_font("gothic", "B", FONT, uni=True)
pdf.set_auto_page_break(auto=True, margin=20)
pdf.add_page()

# === Page 1: Title + intro ===
pdf.set_font("gothic", "B", 16)
pdf.cell(0, 10, "테스트 문서: 다중 페이지 표 연속 테스트", ln=True, align="C")
pdf.ln(5)
pdf.set_font("gothic", "", 11)
pdf.multi_cell(0, 6, "이 문서는 3페이지에 걸쳐진 표를 포함하고 있습니다. p.3~p.5에 걸쳐 하나의 큰 표가 배치되어 있으며, 다중 페이지 표 탐지 로직을 테스트하기 위한 용도입니다.")
pdf.ln(5)
pdf.multi_cell(0, 6, "표의 구조: 6열(항목, 항목코드, 전기, 당기, 증감, 비고)로 구성되어 있으며, 총 30개의 항목이 포함되어 있습니다.")
pdf.ln(5)
pdf.multi_cell(0, 6, "이 외에도 p.2에 작은 표, p.6에 다른 표, p.8에 또 다른 표가 배치되어 있어 다양한 시나리오를 테스트할 수 있습니다.")


# === Page 2: Small table + text ===
pdf.add_page()
pdf.set_font("gothic", "B", 13)
pdf.cell(0, 10, "1. 회사 개요", ln=True)
pdf.ln(3)

pdf.set_font("gothic", "", 10)
headers = ["항목", "내용"]
data = [
    ["회사명", "(주)테스트홀딩스"],
    ["설립일", "2020년 3월 15일"],
    ["대표이사", "홍길동"],
    ["자본금", "1,000억원"],
    ["직원수", "1,234명"],
    ["본사소재지", "서울특별시 강남구 테헤란로 123"],
]

col_widths = [50, 130]
pdf.set_font("gothic", "B", 10)
for i, h in enumerate(headers):
    pdf.cell(col_widths[i], 8, h, border=1, align="C", fill=True)
pdf.ln()

pdf.set_font("gothic", "", 10)
for row in data:
    for i, val in enumerate(row):
        pdf.cell(col_widths[i], 7, val, border=1)
    pdf.ln()

pdf.ln(10)
pdf.set_font("gothic", "", 11)
pdf.multi_cell(0, 6, "위 표는 회사의 기본 정보를 나타냅니다. 본 문서의 핵심은 다음 페이지부터 시작되는 대규모 재무 데이터 표입니다.")


# === Page 3: Large table START (near bottom) ===
pdf.add_page()
pdf.set_font("gothic", "B", 13)
pdf.cell(0, 10, "2. 재무상태표 (연속표 테스트)", ln=True)
pdf.ln(3)

# Fill space before table to push it near bottom
pdf.set_font("gothic", "", 10)
pdf.multi_cell(0, 6, "아래 표는 3페이지(p.3~p.5)에 걸쳐 연속되는 대규모 재무상태표입니다. 이 표는 다중 페이지 표 탐지 알고리즘이 3개 이상의 페이지를 하나의 체인으로 인식하는지 테스트하기 위해 작성되었습니다. 표의 구조는 모든 페이지에서 동일한 6개 열을 가지고 있으며, 총 30개의 행으로 구성됩니다.")
pdf.ln(3)
pdf.multi_cell(0, 6, "이 테스트에서 중요한 점은 p.3의 표가 페이지 하단에 위치하고, p.4에서는 거의 전체 페이지를 차지하며, p.5에서는 페이지 상단에 위치한다는 것입니다. 이렇게 하면 A→B→C 형태의 체인이 감지되어야 합니다.")
pdf.ln(3)

# Table header
cols = ["항목", "항목코드", "전기(백만원)", "당기(백만원)", "증감(백만원)", "비고"]
col_w = [45, 25, 30, 30, 30, 30]

pdf.set_font("gothic", "B", 9)
for i, h in enumerate(cols):
    pdf.cell(col_w[i], 7, h, border=1, align="C", fill=True)
pdf.ln()

rows = [
    ("유동자산", "A100", "523,450", "612,800", "89,350", ""),
    ("  당좌자산", "A110", "234,100", "298,500", "64,400", "+27.5%"),
    ("    현금및현금성자산", "A111", "89,200", "102,300", "13,100", ""),
    ("    단기금융상품", "A112", "78,400", "95,600", "17,200", ""),
    ("    매출채권", "A113", "66,500", "100,600", "34,100", "+51.3%"),
]

pdf.set_font("gothic", "", 9)
for row in rows:
    for i, val in enumerate(row):
        pdf.cell(col_w[i], 6, val, border=1, align="R" if i >= 2 else "L")
    pdf.ln()


# === Page 4: Large table CONTINUE ===
pdf.add_page()
# No title - just continue the table
pdf.set_font("gothic", "B", 9)
for i, h in enumerate(cols):
    pdf.cell(col_w[i], 7, h, border=1, align="C", fill=True)
pdf.ln()

rows_p4 = [
    ("  재고자산", "A120", "156,300", "178,400", "22,100", "+14.1%"),
    ("    상품", "A121", "45,200", "52,100", "6,900", ""),
    ("    제품", "A122", "67,800", "78,300", "10,500", ""),
    ("    원재료", "A123", "43,300", "48,000", "4,700", ""),
    ("비유동자산", "A200", "892,300", "945,600", "53,300", ""),
    ("  유형자산", "A210", "456,700", "478,900", "22,200", ""),
    ("    토지", "A211", "123,400", "123,400", "0", "변동없음"),
    ("    건물", "A212", "234,500", "245,600", "11,100", ""),
    ("    기계장치", "A213", "98,800", "109,900", "11,100", ""),
    ("  무형자산", "A220", "234,500", "256,700", "22,200", ""),
    ("    영업권", "A221", "156,700", "167,800", "11,100", ""),
    ("    소프트웨어", "A222", "77,800", "88,900", "11,100", ""),
    ("  투자부동산", "A230", "145,600", "156,800", "11,200", ""),
    ("  장기금융상품", "A240", "55,500", "53,200", "-2,300", "-4.1%"),
    ("유동부채", "B100", "312,400", "356,700", "44,300", ""),
    ("  매입채무", "B110", "89,500", "102,300", "12,800", ""),
]

pdf.set_font("gothic", "", 9)
for row in rows_p4:
    for i, val in enumerate(row):
        pdf.cell(col_w[i], 6, val, border=1, align="R" if i >= 2 else "L")
    pdf.ln()


# === Page 5: Large table CONTINUE (near top, then text below) ===
pdf.add_page()
# Continue table from top
pdf.set_font("gothic", "B", 9)
for i, h in enumerate(cols):
    pdf.cell(col_w[i], 7, h, border=1, align="C", fill=True)
pdf.ln()

rows_p5 = [
    ("  단기차입금", "B120", "67,800", "78,900", "11,100", ""),
    ("  미지급금", "B130", "45,600", "56,700", "11,100", ""),
    ("  미지급비용", "B140", "34,200", "38,900", "4,700", ""),
    ("비유동부채", "B200", "234,500", "267,800", "33,300", ""),
    ("  장기차입금", "B210", "156,700", "178,900", "22,200", ""),
    ("  사채", "B220", "45,600", "56,700", "11,100", ""),
    ("  퇴직급여충당부채", "B230", "32,200", "32,200", "0", "변동없음"),
    ("자본", "C100", "868,850", "933,900", "65,050", ""),
    ("  자본금", "C110", "100,000", "100,000", "0", "변동없음"),
]

pdf.set_font("gothic", "", 9)
for row in rows_p5:
    for i, val in enumerate(row):
        pdf.cell(col_w[i], 6, val, border=1, align="R" if i >= 2 else "L")
    pdf.ln()

pdf.ln(8)
pdf.set_font("gothic", "", 11)
pdf.multi_cell(0, 6, "위 재무상태표는 3페이지(p.3~p.5)에 걸쳐 표시된 연속 표입니다. 다중 페이지 표 탐지 시스템이 이 표를 하나의 체인으로 올바르게 감지하는지 확인합니다.")


# === Page 6: Different table ===
pdf.add_page()
pdf.set_font("gothic", "B", 13)
pdf.cell(0, 10, "3. 손익계산서 요약", ln=True)
pdf.ln(3)

cols2 = ["항목", "전기(백만원)", "당기(백만원)", "증감률"]
col_w2 = [60, 40, 40, 40]

pdf.set_font("gothic", "B", 10)
for i, h in enumerate(cols2):
    pdf.cell(col_w2[i], 7, h, border=1, align="C", fill=True)
pdf.ln()

rows_p6 = [
    ("매출액", "1,234,500", "1,456,700", "+18.0%"),
    ("매출원가", "890,200", "1,023,400", "+14.9%"),
    ("매출총이익", "344,300", "433,300", "+25.8%"),
    ("판매관리비", "123,400", "145,600", "+18.0%"),
    ("영업이익", "220,900", "287,700", "+30.2%"),
    ("영업외수익", "23,400", "34,500", "+47.4%"),
    ("영업외비용", "12,300", "15,600", "+26.8%"),
    ("법인세비용", "46,700", "61,320", "+31.3%"),
]

pdf.set_font("gothic", "", 10)
for row in rows_p6:
    for i, val in enumerate(row):
        pdf.cell(col_w2[i], 7, val, border=1, align="R" if i >= 1 else "L")
    pdf.ln()


# === Page 7: Text only ===
pdf.add_page()
pdf.set_font("gothic", "B", 13)
pdf.cell(0, 10, "4. 주석사항", ln=True)
pdf.ln(3)
pdf.set_font("gothic", "", 11)
pdf.multi_cell(0, 6, "본 재무제표은 K-IFRS에 따라 작성되었습니다. 주요 회계정책은 다음과 같습니다.\n\n1. 유형자산은 취득원가로 측정되며, 내용연수에 따라 정액법으로 상각됩니다.\n2. 재고자산은 개별법으로 평가됩니다.\n3. 투자부동산은 공정가치로 측정됩니다.\n\n본 문서는 다중 페이지 표 탐지 테스트를 위해 작성된 가상의 재무제표입니다.")


# === Page 8: Another table ===
pdf.add_page()
pdf.set_font("gothic", "B", 13)
pdf.cell(0, 10, "5. 현금흐름표 요약", ln=True)
pdf.ln(3)

cols3 = ["항목", "전기(백만원)", "당기(백만원)"]
col_w3 = [70, 50, 50]

pdf.set_font("gothic", "B", 10)
for i, h in enumerate(cols3):
    pdf.cell(col_w3[i], 7, h, border=1, align="C", fill=True)
pdf.ln()

rows_p8 = [
    ("영업활동 현금흐름", "189,400", "234,500"),
    ("투자활동 현금흐름", "-78,900", "-95,600"),
    ("재무활동 현금흐름", "-45,600", "-67,800"),
    ("기초 현금잔액", "45,200", "110,100"),
    ("기말 현금잔액", "110,100", "181,200"),
]

pdf.set_font("gothic", "", 10)
for row in rows_p8:
    for i, val in enumerate(row):
        pdf.cell(col_w3[i], 7, val, border=1, align="R" if i >= 1 else "L")
    pdf.ln()


out = "/Users/a452779/Desktop/agent/corp/pdftablesearch/test_multipage_3pages.pdf"
pdf.output(out)
print(f"Created: {out}")
print(f"Pages: {pdf.pages_count}")
