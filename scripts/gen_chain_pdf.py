from fpdf import FPDF

class P(FPDF):
    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica","",8)
        self.cell(0,10,f"- {self.page_no()} -",new_x="LMARGIN",new_y="NEXT",align="C")

pdf=P()
pdf.set_auto_page_break(auto=True,margin=20)
pdf.add_page()

pdf.set_font("Helvetica","B",16)
pdf.cell(0,10,"Test: Full-Page Table Chain (3+ pages)",new_x="LMARGIN",new_y="NEXT",align="C")
pdf.ln(5)
pdf.set_font("Helvetica","",11)
pdf.multi_cell(0,6,"6-column table spans p.3-p.5 entirely. p.6: 4-col table. p.8: 3-col table.")

pdf.add_page()
pdf.set_font("Helvetica","B",13)
pdf.cell(0,10,"1. Company Overview",new_x="LMARGIN",new_y="NEXT")
pdf.ln(3)
cw2=[50,130]
pdf.set_font("Helvetica","B",10)
pdf.cell(cw2[0],8,"Item",border=1,align="C",fill=True)
pdf.cell(cw2[1],8,"Value",border=1,align="C",fill=True)
pdf.ln()
pdf.set_font("Helvetica","",10)
for r in [("Company","Test Holdings"),("Founded","2020"),("CEO","John Doe"),("Capital","KRW 100B")]:
    pdf.cell(cw2[0],7,r[0],border=1); pdf.cell(cw2[1],7,r[1],border=1); pdf.ln()
pdf.ln(10)
pdf.multi_cell(0,6,"Below: 3-page chain table. No text above/below on p.3-p.5.")

cols=["Item","Code","Prior(M)","Curr(M)","Chg(M)","Note"]
cw=[45,25,30,30,30,30]

pdf.add_page()
pdf.set_font("Helvetica","B",9)
for i,h in enumerate(cols): pdf.cell(cw[i],7,h,border=1,align="C",fill=True)
pdf.ln()
pdf.set_font("Helvetica","",9)

rows=[
("Current Assets","A100","523,450","612,800","89,350",""),
("  Quick Assets","A110","234,100","298,500","64,400","+27.5%"),
("    Cash & Equiv","A111","89,200","102,300","13,100",""),
("    ST Securities","A112","78,400","95,600","17,200",""),
("    Trade Receiv.","A113","66,500","100,600","34,100","+51.3%"),
("    Other Receiv.","A114","12,300","15,600","3,300",""),
("    Short-term Inv.","A115","15,200","18,900","3,700","+24.3%"),
("  Inventory","A120","156,300","178,400","22,100","+14.1%"),
("    Finished Goods","A121","45,200","52,100","6,900",""),
("    Work in Process","A122","34,500","38,900","4,400",""),
("    Raw Materials","A123","43,300","48,000","4,700",""),
("    Supplies","A124","12,400","15,600","3,200",""),
("    Other Inventory","A125","10,200","12,800","2,600",""),
("    Inventory Allow.","A126","-12,300","-15,600","-3,300",""),
("  Other CA","A130","45,600","56,700","11,100","+24.3%"),
("    Prepaid Expenses","A131","23,400","28,900","5,500",""),
("    Advance Payments","A132","12,300","15,600","3,300",""),
("    Other Current","A133","9,900","12,200","2,300",""),
("Non-Current Assets","A200","892,300","945,600","53,300",""),
("  PP&E (gross)","A210","567,800","598,400","30,600","+5.4%"),
("  Accum. Depr.","A211","-111,100","-119,500","-8,400","+7.6%"),
("  PP&E (net)","A212","456,700","478,900","22,200","+4.9%"),
("    Land","A213","123,400","123,400","0","N/C"),
("    Buildings","A214","234,500","245,600","11,100","+4.7%"),
("    Machinery","A215","78,900","89,200","10,300","+13.1%"),
("    Vehicles","A216","23,400","25,600","2,200","+9.4%"),
("    Lease Assets","A217","45,200","56,700","11,500","+25.4%"),
("    Constr. in Prog.","A218","23,400","34,500","11,100","+47.4%"),
("  Intangible Assets","A220","234,500","256,700","22,200","+9.5%"),
("    Goodwill","A221","156,700","167,800","11,100","+7.1%"),
("    Software","A222","45,600","56,700","11,100","+24.3%"),
("    Patents & Lic.","A223","23,400","25,600","2,200","+9.4%"),
("    Other Intang.","A224","8,800","6,600","-2,200","-25%"),
("  Right-of-Use","A230","89,200","95,600","6,400","+7.2%"),
("  Investment Prop.","A240","145,600","156,800","11,200","+7.7%"),
("  LT Financial Inst.","A250","55,500","53,200","-2,300","-4.1%"),
("  Deferred Tax","A260","23,400","28,900","5,500","+23.5%"),
("  Other NCA","A270","12,300","15,600","3,300","+26.8%"),
("TOTAL ASSETS","A999","1,415,750","1,558,400","142,650","+10.1%"),
("Current Liabilities","B100","312,400","356,700","44,300","+14.2%"),
("  Trade Payables","B110","89,500","102,300","12,800","+14.3%"),
("  Short-term Debt","B120","67,800","78,900","11,100","+16.4%"),
("    Bank Overdraft","B121","34,500","45,600","11,100","+32.2%"),
("    ST Loans","B122","33,300","33,300","0","N/C"),
("  Accrued Expenses","B130","45,600","56,700","11,100","+24.3%"),
("    Salary Payable","B131","23,400","28,900","5,500","+23.5%"),
("    Tax Payable","B132","12,300","15,600","3,300","+26.8%"),
("    Other Accrued","B133","9,900","12,200","2,300","+23.2%"),
("  Advance Receipts","B140","23,400","28,900","5,500","+23.5%"),
("  Current Port. LT","B150","34,500","38,900","4,400","+12.8%"),
("  Other CL","B160","51,600","51,000","-600","-1.2%"),
("Non-Current Liab.","B200","234,500","267,800","33,300","+14.2%"),
("  Long-term Debt","B210","156,700","178,900","22,200","+14.2%"),
("    Bank Loans","B211","89,400","102,300","12,900","+14.4%"),
("    Corporate Bonds","B212","45,600","56,700","11,100","+24.3%"),
("    Other LT Debt","B213","21,700","19,900","-1,800","-8.3%"),
("  Lease Liabilities","B220","34,500","38,900","4,400","+12.8%"),
("  Severance Pay","B230","32,200","38,900","6,700","+20.8%"),
("  Deferred Tax Liab.","B240","11,100","11,100","0","N/C"),
("Equity","C100","868,850","933,900","65,050","+7.5%"),
("  Capital Stock","C110","100,000","100,000","0","N/C"),
("  Capital Surplus","C120","234,500","256,700","22,200","+9.5%"),
("    Share Premium","C121","189,400","201,200","11,800","+6.2%"),
("    Other Surplus","C122","45,100","55,500","10,400","+23.1%"),
("  Retained Earnings","C130","478,900","523,400","44,500","+9.3%"),
("    Legal Reserve","C131","23,400","25,600","2,200","+9.4%"),
("    Other RE","C132","455,500","497,800","42,300","+9.3%"),
("  Treasury Stock","C140","-12,300","-15,600","-3,300","+26.8%"),
("  Other Equity","C150","67,750","69,400","1,650","+2.4%"),
("TOTAL LIAB+EQUITY","B+C","1,415,750","1,558,400","142,650","Match"),
]

for row in rows:
    for i, val in enumerate(row):
        pdf.cell(cw[i], 6, val, border=1, align="R" if i>=2 else "L")
    pdf.ln()

pdf.ln(5)
pdf.set_font("Helvetica","",11)
pdf.multi_cell(0,6,"End of balance sheet (should span 3 pages: p.3-p.5).")

# Page 6 (or wherever auto-break ends): Income Statement
pdf.add_page()
pdf.set_font("Helvetica","B",13)
pdf.cell(0,10,"3. Income Statement",new_x="LMARGIN",new_y="NEXT")
pdf.ln(3)
cw4=[60,40,40,40]
pdf.set_font("Helvetica","B",10)
for i,h in enumerate(["Item","Prior(M)","Curr(M)","Chg%"]):
    pdf.cell(cw4[i],7,h,border=1,align="C",fill=True)
pdf.ln()
pdf.set_font("Helvetica","",10)
for r in [("Revenue","1,234,500","1,456,700","+18.0%"),("COGS","890,200","1,023,400","+14.9%"),("Gross Profit","344,300","433,300","+25.8%"),("SG&A","123,400","145,600","+18.0%"),("Op. Profit","220,900","287,700","+30.2%"),("Net Income","161,200","214,800","+33.3%")]:
    for i,v in enumerate(r): pdf.cell(cw4[i],7,v,border=1,align="R" if i>=1 else "L")
    pdf.ln()

pdf.add_page()
pdf.set_font("Helvetica","B",13)
pdf.cell(0,10,"4. Notes",new_x="LMARGIN",new_y="NEXT")
pdf.ln(3)
pdf.set_font("Helvetica","",11)
pdf.multi_cell(0,6,"K-IFRS applied. PP&E: cost model. Inventory: specific ID. Fictional document for testing.")

pdf.add_page()
pdf.set_font("Helvetica","B",13)
pdf.cell(0,10,"5. Cash Flow Summary",new_x="LMARGIN",new_y="NEXT")
pdf.ln(3)
cw3=[70,50,50]
pdf.set_font("Helvetica","B",10)
for i,h in enumerate(["Item","Prior(M)","Curr(M)"]):
    pdf.cell(cw3[i],7,h,border=1,align="C",fill=True)
pdf.ln()
pdf.set_font("Helvetica","",10)
for r in [("Operating CF","189,400","234,500"),("Investing CF","-78,900","-95,600"),("Financing CF","-45,600","-67,800"),("Opening Cash","45,200","110,100"),("Closing Cash","110,100","181,200")]:
    for i,v in enumerate(r): pdf.cell(cw3[i],7,v,border=1,align="R" if i>=1 else "L")
    pdf.ln()

out="/Users/a452779/Desktop/agent/corp/pdftablesearch/test_multipage_chain.pdf"
pdf.output(out)
print(f"Created: {out}, Pages: {pdf.pages_count}")
