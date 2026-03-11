###################################################### FIXED GOLDEN CODE-working code below ######################################################

import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
from datetime import date
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle,
    Paragraph, Spacer
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.pdfgen import canvas as pdf_canvas


# =====================================================
# PAGE CONFIG
# =====================================================
st.set_page_config(page_title="Quotation / Invoice Generator", layout="wide")
st.title("📄 Quotation / Invoice Generator")


# =====================================================
# PATHS
# =====================================================
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"
#OUTPUT_DIR = BASE_DIR / "output" / "documents"
OUTPUT_DIR = Path(__file__).parent / "output"
DB_FILE = BASE_DIR / "billing.db"

DATA_DIR.mkdir(exist_ok=True)
ASSETS_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# PRODUCT_FILE = DATA_DIR / "NT_V.xlsx"
LETTERHEAD_IMG = ASSETS_DIR / "letterhead.jpg"
# =====================================================
# EXCEL FILE SELECTION (NEW)
# =====================================================

excel_files = [f for f in DATA_DIR.glob("*.xlsx") if not f.name.startswith("~$")]

if not excel_files:
    st.error("No Excel files found in data folder.")
    st.stop()

excel_names = [f.name for f in excel_files]

selected_excel_name = st.selectbox(
    "📂 Select Product Excel File",
    excel_names
)

PRODUCT_FILE = DATA_DIR / selected_excel_name

# =====================================================
# DATABASE
# =====================================================
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS counters (
    doc_type TEXT PRIMARY KEY,
    last_no INTEGER
)
""")
conn.commit()


def get_next_number(doc_type):
    cur.execute("SELECT last_no FROM counters WHERE doc_type=?", (doc_type,))
    row = cur.fetchone()

    if row:
        num = row[0] + 1
        cur.execute("UPDATE counters SET last_no=? WHERE doc_type=?", (num, doc_type))
    else:
        num = 1
        cur.execute("INSERT INTO counters VALUES (?,?)", (doc_type, num))

    conn.commit()

    prefix = "KOG-Q" if doc_type == "Quotation" else "KOG-I"
    return f"{prefix}-{num:04d}"


# =====================================================
# LOAD PRODUCTS
# =====================================================
@st.cache_data
def load_products(file_path):
    xl = pd.ExcelFile(file_path)
    sheets = {}

    for s in xl.sheet_names:
        df = xl.parse(s)
        df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
        df = df.fillna(0)

        numeric_cols = ["switches", "fan_modules", "sockets", "dimmers", "gang_box"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        sheets[s] = df
 
    return sheets


products = load_products(PRODUCT_FILE)


# =====================================================
# SESSION STATE
# =====================================================
if "cart" not in st.session_state:
    st.session_state.cart = []

if "add_qty" not in st.session_state:
    st.session_state.add_qty = 1

if "placement_input" not in st.session_state:
    st.session_state.placement_input = ""

def refresh_sno():
    for i, r in enumerate(st.session_state.cart):
        r["sno"] = i + 1


# =====================================================
# DOCUMENT TYPE
# =====================================================
doc_type = st.radio(
    "Document Type",
    ["Quotation", "Invoice"],
    horizontal=True
)


# =====================================================
# CUSTOMER DETAILS
# =====================================================
with st.expander("👤 Customer Details", expanded=True):
    c1, c2, c3, c4 = st.columns(4)
    cust_name = c1.text_input("Customer Name")
    mobile = c2.text_input("Mobile")
    email = c3.text_input("Email")
    address = c4.text_input("Address")


# =====================================================
# PRODUCT CONFIGURATION (CRASH PROOF)
# =====================================================
st.markdown("---")
st.subheader("🔎 Product Configuration")


def get_product_name(index_loc):
    base_product_name = "KOG "
    row = df.iloc[index_loc]
    # switches,fans,sockets,dimmers= row.get("switches"), row.get("fan_modules"), row.get("sockets"), row.get("dimmers")
    switches = row.get("switches",0) or 0
    fans = row.get("fan_modules",0) or 0
    sockets = row.get("sockets",0) or 0
    dimmers = row.get("dimmers",0) or 0
    if switches>0:
        base_product_name = base_product_name +"S"+ str(switches)
    if fans>0:
        base_product_name = base_product_name +"F"+ str(fans)
    if sockets>0:
        base_product_name = base_product_name +"P"+ str(sockets)
    if dimmers>0:
        base_product_name = base_product_name +"D"+ str(dimmers)
    return base_product_name

sheet = st.selectbox("Select Series / Sheet", list(products.keys()))
df = products[sheet]
for i1 in range(len(df)):
    df['product_name'][i1] = get_product_name(i1)
# -----------------------------------------------------
# STRUCTURE VALIDATION
# -----------------------------------------------------
required_cols = [
    "gang_box", "switches", "fan_modules",
    "sockets", "dimmers", "product_name", "mrp"
]

missing_cols = [c for c in required_cols if c not in df.columns]

if missing_cols:
    st.error(f"Excel structure mismatch. Missing columns: {missing_cols}")
    st.stop()

if df.empty:
    st.error("Selected sheet contains no data.")
    st.stop()

# -----------------------------------------------------
# FILTER CHAIN (SAFE)
# -----------------------------------------------------
f1, f2, f3, f4, f5 = st.columns(5)

# Gang Box
gang_options = sorted(df["gang_box"].dropna().unique())
if not gang_options:
    st.warning("No Gang Box values available.")
    st.stop()

gang_filter = f1.selectbox("Gang Box", gang_options)
df1 = df[df["gang_box"] == gang_filter]

if df1.empty:
    st.warning("No products found for selected Gang Box.")
    st.stop()

# Switches
switch_options = sorted(df1["switches"].dropna().unique())
if not switch_options:
    st.warning("No Switch values available.")
    st.stop()

switch_filter = f2.selectbox("Switches", switch_options)
df2 = df1[df1["switches"] == switch_filter]

if df2.empty:
    st.warning("No products found for selected Switch count.")
    st.stop()

# Fan Modules
fan_options = sorted(df2["fan_modules"].dropna().unique())
if not fan_options:
    st.warning("No Fan Module values available.")
    st.stop()

fan_filter = f3.selectbox("Fan Modules", fan_options)
df3 = df2[df2["fan_modules"] == fan_filter]

if df3.empty:
    st.warning("No products found for selected Fan Modules.")
    st.stop()

# Sockets
socket_options = sorted(df3["sockets"].dropna().unique())
if not socket_options:
    st.warning("No Socket values available.")
    st.stop()

socket_filter = f4.selectbox("Sockets", socket_options)
df4 = df3[df3["sockets"] == socket_filter]

if df4.empty:
    st.warning("No products found for selected Sockets.")
    st.stop()

# Dimmers
dimmer_options = sorted(df4["dimmers"].dropna().unique())
if not dimmer_options:
    st.warning("No Dimmer values available.")
    st.stop()

dimmer_filter = f5.selectbox("Dimmers", dimmer_options)
filtered_df = df4[df4["dimmers"] == dimmer_filter]

# -----------------------------------------------------
# MATCHING PRODUCT SELECT
# -----------------------------------------------------
product_selected = None

if not filtered_df.empty:
    product_selected = st.selectbox(
        "Select Matching Product",
        ["-- Select --"] + sorted(filtered_df["product_name"].dropna().unique())
    )
else:
    st.warning("No product found for selected configuration.")

# -----------------------------------------------------
# DIRECT PRODUCT SELECT
# -----------------------------------------------------
product_direct = st.selectbox(
    "All Products in Sheet",
    ["-- Select --"] + sorted(df["product_name"].dropna().unique())
)
#$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$

# =====================================================
# QUANTITY & PRICING
# =====================================================
st.markdown("---")
st.subheader("🧮 Quantity & Pricing")

qty = st.number_input(
    "Quantity",
    min_value=1,
    step=1,
    value=st.session_state.add_qty
)

st.session_state.add_qty = qty

placement = st.text_input(
    "Placement (e.g., Living Room / Bedroom 1)",
    key="placement_input"
)

# Default display pricing (clean UI, no override logic)
display_row = None

if product_direct != "-- Select --":
    display_row = df[df["product_name"] == product_direct].iloc[0]
elif product_selected and product_selected != "-- Select --":
    display_row = filtered_df[
        filtered_df["product_name"] == product_selected
    ].iloc[0]
else:
    display_row = df.iloc[0]

unit_price = float(display_row.get("mrp", 0))
total_price = unit_price * qty

st.write(f"**Unit:**  ₹ {int(unit_price)}")
st.write(f"**Total:**  ₹ {int(total_price)}")


# ✅ FINAL FIX — DECIDE PRODUCT ONLY WHEN ADDING
if st.button("Add to Cart"):

    if product_direct != "-- Select --":
        final_row = df[df["product_name"] == product_direct].iloc[0]

    elif product_selected and product_selected != "-- Select --":
        final_row = filtered_df[
            filtered_df["product_name"] == product_selected
        ].iloc[0]
    else:
        st.warning("Please select a product.")
        st.stop()
    
 
    st.session_state.cart.append({
        "sno": len(st.session_state.cart) + 1,
        "product": final_row.get("product_name",""),
        "desc": final_row.get("product_description", ""),
        "placement": placement,
        "qty": qty,
        "unit_price": float(final_row.get("mrp", 0)),   # ✅ use only this
        "total": float(final_row.get("mrp", 0)) * qty
    })

    st.session_state.add_qty = 1
    
    st.rerun()

# Backward compatibility fix
for item in st.session_state.cart:
    if "unit_price" not in item and "unit" in item:
        item["unit_price"] = item["unit"]

# =====================================================
# CART (UI ENHANCED ONLY)
# =====================================================
st.markdown("---")
st.subheader("🛒 Cart")

if st.session_state.cart:

    header_cols = st.columns([0.6, 2, 2, 2, 1.2, 1.2, 1.2, 0.7])
    header_cols[0].markdown("**S.No**")
    header_cols[1].markdown("**Product**")
    header_cols[2].markdown("**Description**")
    header_cols[3].markdown("**Placement**")
    header_cols[4].markdown("**Qty**")
    header_cols[5].markdown("**Unit INR**")
    header_cols[6].markdown("**Total INR**")
    header_cols[7].markdown("")

    st.markdown("---")

for i, r in enumerate(st.session_state.cart):

    # Zebra striping
    bg_color = "#f7f9fc" if i % 2 == 0 else "#ffffff"

    row_container = st.container()
    with row_container:
        st.markdown(
            f"""
            <div style="background-color:{bg_color};
                        padding:8px;
                        border-radius:6px;">
            """,
            unsafe_allow_html=True
        )

        cols = st.columns([0.6, 2, 2, 2, 1.2, 1.2, 1.2, 0.7])

        cols[0].write(r["sno"])
        cols[1].write(r["product"])
        cols[2].write(r["desc"])
        cols[3].write(r["placement"])

        minus, qty_col, plus = cols[4].columns([1,1,1])

        if minus.button("−", key=f"m{i}", use_container_width=True):
            if r["qty"] > 1:
                r["qty"] -= 1

        qty_col.markdown(
            f"<div style='text-align:center'>{r['qty']}</div>",
            unsafe_allow_html=True
        )

        if plus.button("+", key=f"p{i}", use_container_width=True):
            r["qty"] += 1

        r["total"] = r["qty"] * r["unit_price"]

        cols[5].markdown(
            f"<div style='text-align:right'> {int(r['unit_price']):,}</div>",
            unsafe_allow_html=True
        )

        cols[6].markdown(
            f"<div style='text-align:right'> {int(r['total']):,}</div>",
            unsafe_allow_html=True
        )

        if cols[7].button("❌", key=f"d{i}", use_container_width=True):
            st.session_state.cart.pop(i)
            refresh_sno()
            st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

# =====================================================
# CALCULATIONS (UNCHANGED)
# =====================================================
st.markdown("---")
st.subheader("💰 Calculation")

subtotal = sum(r["total"] for r in st.session_state.cart)

discount_pct = st.number_input("Discount (%)", 0.0, 100.0, 0.0)
discount_amt = round(subtotal * (discount_pct / 100))
discounted_subtotal = subtotal - discount_amt

use_install = st.checkbox("Add Installation (10%)")
use_gst = st.checkbox("Add GST (18%)")

installation = round(discounted_subtotal * 0.10) if use_install else 0
gst = round((discounted_subtotal + installation) * 0.18) if use_gst else 0

grand_total = discounted_subtotal + installation + gst

# st.write(f"Subtotal: {subtotal}")
# st.write(f"Grand Total: {grand_total}")
#####BELOW CODE IS REPLACEMENT OF ABOVE TWO LINES####################
st.markdown("---")

st.markdown(
    f"""
    <div style="
        background: linear-gradient(90deg, #1f4e79, #163a5c);
        padding:18px;
        border-radius:10px;
        color:white;
        text-align:right;
        font-size:20px;
        font-weight:bold;
        box-shadow:0 4px 10px rgba(0,0,0,0.15);
    ">
        Grand Total :  {grand_total:,.0f}
    </div>
    """,
    unsafe_allow_html=True
)


# =====================================================
# CUSTOM CANVAS (NEW)
# =====================================================
class NumberedCanvas(pdf_canvas.Canvas):
    def __init__(self, *args, doc_type=None, prepared_by=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self.doc_type = doc_type
        self.prepared_by = prepared_by

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_footer(total_pages)
            super().showPage()
        super().save()

    def draw_footer(self, total_pages):
        w, h = A4

        # Prepared By (left)
        if self.prepared_by:
            self.setFont("Helvetica", 9)
            self.setFillColor(colors.black)
            self.drawString(1.5*cm, 1.2*cm, f"Prepared By: {self.prepared_by}")

        # Page number (right)
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.grey)
        self.drawRightString(
            w - 1.5*cm,
            1.2*cm,
            f"Page {self._pageNumber} of {total_pages}"
        )

        # Signatory only for Invoice & only last page
        if self.doc_type == "Invoice" and self._pageNumber == total_pages:
            self.setFont("Helvetica-Bold", 10)
            self.setFillColor(colors.black)
            self.drawRightString(w - 1.5*cm, 3.2*cm, "Authorized Signatory")
            self.setFont("Helvetica", 9)
            self.drawRightString(w - 1.5*cm, 2.7*cm, "For Kognitive Studios")


# =====================================================
# LETTERHEAD
# =====================================================
def draw_letterhead(canvas, doc):
    w, h = A4
    if LETTERHEAD_IMG.exists():
        canvas.drawImage(str(LETTERHEAD_IMG), 0, 0, width=w, height=h)


def fmt(n):
    return f"{int(round(n)):,}"


# =====================================================
# ENTERPRISE PDF GENERATION + BOQ EXPORT
# =====================================================
def generate_pdf(doc_number):

    # ✅ Ensure output directory exists (FIX 1: Excel not saving)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fname = OUTPUT_DIR / f"{doc_number}.pdf"

    doc = SimpleDocTemplate(
        str(fname),
        pagesize=A4,
        topMargin=5*cm,
        bottomMargin=2*cm,
        leftMargin=1.5*cm,
        rightMargin=1.5*cm
    )

    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    bold = styles["Heading2"]

    elements = []

    # ✅ FIX 2: Always pull customer details from session_state
    st.text_input("Customer Name", key="cust_name")
    st.text_input("Mobile", key="mobile")
    st.text_input("Email", key="email")
    st.text_area("Address", key="address")

    # -------------------------------------------------
    # HEADER
    # -------------------------------------------------
    elements.append(Paragraph(
        f"<b>{doc_type.upper()}</b> : {doc_number}",
        styles["Title"]
    ))
    elements.append(Spacer(1, 10))

    elements.append(Paragraph(
        f"<b>Customer:</b> {cust_name}<br/>"
        f"<b>Mobile:</b> {mobile}<br/>"
        f"<b>Email:</b> {email}<br/>"
        f"<b>Address:</b> {address}<br/>"
        f"<b>Date:</b> {date.today()}",
        normal
    ))
    elements.append(Spacer(1, 18))

    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

    center_style = ParagraphStyle(
        name="CenterWrap",
        parent=styles["Normal"],
        alignment=TA_CENTER,
        fontSize=9,
    )

    left_style = ParagraphStyle(
        name="LeftWrap",
        parent=styles["Normal"],
        alignment=TA_LEFT,
        fontSize=9,
    )

    right_style = ParagraphStyle(
        name="RightAlign",
        parent=styles["Normal"],
        alignment=TA_RIGHT,
        fontSize=9,
    )

    semi_bold_style = ParagraphStyle(
        name="SemiBold",
        parent=styles["Normal"],
        alignment=TA_RIGHT,
        fontName="Helvetica-Bold",
        fontSize=9,
    )

    grand_total_style = ParagraphStyle(
        name="GrandTotal",
        parent=styles["Normal"],
        alignment=TA_RIGHT,
        fontName="Helvetica-Bold",
        fontSize=11,
    )

    # -------------------------------------------------
    # WIDTH CALCULATION
    # -------------------------------------------------
    total_available_width = A4[0] - doc.leftMargin - doc.rightMargin

    colWidths = [
        1.2*cm,
        total_available_width*0.22,
        total_available_width*0.25,
        total_available_width*0.17,
        1.2*cm,
        total_available_width*0.11,
        total_available_width*0.13
    ]

    # -------------------------------------------------
    # TABLE (Products + Totals Combined)
    # -------------------------------------------------
    table_data = [[
        "S.No", "Product", "Description",
        "Placement", "Qty", "Unit Price", "Total"
    ]]

    item_row_count = 0

    for r in st.session_state.cart:
        table_data.append([
            Paragraph(str(r["sno"]), center_style),
            Paragraph(str(r["product"]), left_style),
            Paragraph(str(r.get("desc","")), left_style),
            Paragraph(str(r.get("placement","")), left_style),
            Paragraph(str(r["qty"]), center_style),
            Paragraph(fmt(r["unit_price"]), right_style),
            Paragraph(fmt(r["total"]), right_style)
        ])
        item_row_count += 1

    # Totals rows
    def total_row(label, value, style):
        table_data.append([
            "", "", "", "", "",
            Paragraph(label, style),
            Paragraph(fmt(value), style)
        ])

    total_row("Subtotal", subtotal, semi_bold_style)
    total_row("Discount", discount_amt, right_style)

    if use_install:
        total_row("Installation", installation, right_style)

    if use_gst:
        total_row("CGST", gst/2, right_style)
        total_row("SGST", gst/2, right_style)

    total_row("Grand Total", grand_total, grand_total_style)

    table = Table(
        table_data,
        repeatRows=1,
        colWidths=colWidths
    )

    # -------------------------------------------------
    # TABLE STYLE
    # -------------------------------------------------
    style_commands = [

        ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#EAEAEA")),
        ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),

        ("GRID",(0,0),(-1,-1),0.6,colors.grey),

        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("ALIGN",(0,1),(4,-1),"CENTER"),
        ("ALIGN",(5,1),(-1,-1),"RIGHT"),

        ("LEFTPADDING",(0,0),(-1,-1),6),
        ("RIGHTPADDING",(0,0),(-1,-1),6),
        ("TOPPADDING",(0,0),(-1,-1),6),
        ("BOTTOMPADDING",(0,0),(-1,-1),6),
    ]

    # ✅ FIX 3: Zebra striping only for product rows
    for i in range(1, item_row_count + 1):
        if i % 2 == 0:
            style_commands.append(
                ("BACKGROUND",(0,i),(-1,i),colors.HexColor("#F7F7F7"))
            )

    # Accounting double underline for Grand Total
    grand_index = len(table_data) - 1

    style_commands.append(
        ("LINEABOVE",(0,grand_index),(6,grand_index),1.5,colors.black)
    )
    style_commands.append(
        ("LINEABOVE",(0,grand_index),(6,grand_index),0.6,colors.black)
    )

    table.setStyle(TableStyle(style_commands))

    elements.append(table)
    elements.append(Spacer(1, 30))

    # -------------------------------------------------
    # TERMS
    # -------------------------------------------------
    elements.append(Paragraph("<b>Terms & Conditions</b>", bold))
    elements.append(Spacer(1, 10))

    terms = [
        "1. Warranty: 2 Years from handover.",
        "2. Delivery: 3–4 weeks for custom panels.",
        "3. Installation outside city is chargeable.",
        "4. Electrical wiring not included.",
        "5. Quotation valid for 30 days.",
        "6. Payment: 60% advance, 40% before dispatch."
    ]

    for t in terms:
        elements.append(Paragraph(t, normal))

    prepared_by = st.session_state.get("username", "")

    doc.build(
        elements,
        onFirstPage=draw_letterhead,
        onLaterPages=draw_letterhead,
        canvasmaker=lambda *args, **kwargs: NumberedCanvas(
            *args,
            doc_type=doc_type,
            prepared_by=prepared_by,
            **kwargs
        )
    )


        # =====================================================
    # BOQ EXCEL GENERATION (SAFE – WILL NOT BREAK PDF)
    # =====================================================
    try:
        import pandas as pd
        from pathlib import Path

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        boq_data = []
        for r in st.session_state.cart:
            boq_data.append({
                "Product": r["product"],
                "Quantity": r["qty"]
            })

        boq_df = pd.DataFrame(boq_data)

        boq_path = OUTPUT_DIR / f"{doc_number}_BOQ.xlsx"

        with pd.ExcelWriter(str(boq_path), engine="openpyxl") as writer:
            boq_df.to_excel(writer, index=False, startrow=4, sheet_name="BOQ")

            ws = writer.sheets["BOQ"]
            ws["A1"] = "Kognitive IoT Solutions"
            ws["A3"] = "BOQ"

        print("BOQ Saved At:", boq_path.resolve())

    except Exception as e:
        print("Excel Generation Failed:", e)

    # ✅ ALWAYS return PDF path no matter what
    return fname
# =====================================================
# ACTION
# =====================================================
if st.button("📄 Generate PDF"):

    if not st.session_state.cart:
        st.warning("Cart is empty.")
        st.stop()

    doc_number = get_next_number(doc_type)
    pdf = generate_pdf(doc_number)

    with open(pdf, "rb") as f:
        st.download_button("⬇ Download PDF", f, file_name=pdf.name)

