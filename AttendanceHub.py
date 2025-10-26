# streamlit_app.py — Superette Caisse (Barcode-compatible, Epson ESC/POS)
# -----------------------------------------------------------------------
# ✅ Features
# - Scan barcodes with a USB "douchette" (acts like keyboard + Enter)
# - Digits-only parsing (أي نص يرجّع أرقام فقط)
# - Auto-qty: 3*<barcode>  → يضيف 3 قطع من نفس الكود
# - Live cart + totals (Sous-total / TVA / Total)
# - Payments: Cash / Carte / Mixte + monnaie
# - Products CRUD + stock decrement on sale
# - Cash movements (IN/OUT)
# - Daily reports + CSV export
# - HTML receipt (download)
# - ESC/POS thermal print: Epson TM-T20/TM-T88 (USB) preset
# - SQLite local DB
# -----------------------------------------------------------------------

import json
import os
import sqlite3
from datetime import datetime, date
from typing import Dict, List, Tuple

import pandas as pd
import streamlit as st

# --- Page config early to avoid blank pages ---
st.set_page_config(page_title="Caisse Superette (Barcode)", layout="wide", initial_sidebar_state="expanded")

DB_PATH = os.environ.get("CAISSE_DB", "caisse_superette.db")

# ---------------------- DB LAYER ----------------------

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            barcode TEXT PRIMARY KEY,
            name   TEXT NOT NULL,
            price  REAL NOT NULL,
            stock  REAL DEFAULT 0,
            tva    REAL DEFAULT 0
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            items_json TEXT NOT NULL,
            subtotal REAL NOT NULL,
            tva_total REAL NOT NULL,
            total REAL NOT NULL,
            paid_cash REAL DEFAULT 0,
            paid_card REAL DEFAULT 0,
            change REAL DEFAULT 0,
            payment_method TEXT NOT NULL,
            note TEXT
        )
        """
    )

    c.execute(
        """
        CREATE TABLE IF NOT EXISTS cash_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            type TEXT NOT NULL, -- IN or OUT
            amount REAL NOT NULL,
            reason TEXT
        )
        """
    )

    conn.commit()
    conn.close()


# ---------------------- HELPERS ----------------------

@st.cache_data(show_spinner=False)
def _products_df_cache():
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM products ORDER BY name", conn)
    conn.close()
    return df


def refresh_products_cache():
    _products_df_cache.clear()


def find_product(barcode: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE barcode = ?", (barcode,))
    row = c.fetchone()
    conn.close()
    return row


def upsert_product(barcode: str, name: str, price: float, stock: float, tva: float = 0):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO products (barcode, name, price, stock, tva)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(barcode) DO UPDATE SET
            name=excluded.name,
            price=excluded.price,
            stock=excluded.stock,
            tva=excluded.tva
        """,
        (barcode, name, price, stock, tva),
    )
    conn.commit()
    conn.close()
    refresh_products_cache()


def adjust_stock(items: List[Dict[str, float]]):
    conn = get_conn()
    c = conn.cursor()
    for it in items:
        c.execute(
            "UPDATE products SET stock = COALESCE(stock,0) - ? WHERE barcode = ?",
            (it["qty"], it["barcode"]),
        )
    conn.commit()
    conn.close()
    refresh_products_cache()


def record_cash_movement(mtype: str, amount: float, reason: str = ""):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO cash_movements (ts, type, amount, reason) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), mtype, amount, reason),
    )
    conn.commit()
    conn.close()


def record_sale(items: List[Dict], subtotal: float, tva_total: float, total: float,
                paid_cash: float, paid_card: float, change: float, payment_method: str, note: str = "") -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO sales (ts, items_json, subtotal, tva_total, total, paid_cash, paid_card, change, payment_method, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().isoformat(timespec="seconds"),
            json.dumps(items, ensure_ascii=False),
            subtotal,
            tva_total,
            total,
            paid_cash,
            paid_card,
            change,
            payment_method,
            note,
        ),
    )
    sale_id = c.lastrowid
    conn.commit()
    conn.close()
    return sale_id


# ---------------------- UI STATE ----------------------

def init_state():
    if "cart" not in st.session_state:
        st.session_state.cart = {}  # barcode -> {name, price, tva, qty}
    if "barcode_input" not in st.session_state:
        st.session_state.barcode_input = ""
    if "auto_qty" not in st.session_state:
        st.session_state.auto_qty = 1


# ---------------------- CART LOGIC ----------------------

def parse_quantity_barcode(s: str) -> Tuple[float, str]:
    """
    يدعم: 3*<code> → كمية 3.
    ويرجّع من الكود أرقام فقط (يحذف أي حروف/رموز).
    """
    s = s.strip()
    if "*" in s:
        q_str, bc = s.split("*", 1)
        try:
            q = float(q_str.replace(",", "."))
        except Exception:
            q = 1.0
        digits = "".join(ch for ch in str(bc) if ch.isdigit())
        return (q if q > 0 else 1.0, digits)
    digits = "".join(ch for ch in str(s) if ch.isdigit())
    return (1.0, digits or s)


def add_scan_to_cart():
    raw = st.session_state.get("barcode_input", "").strip()
    if not raw:
        return
    qty, bc = parse_quantity_barcode(raw)

    row = find_product(bc)
    if row is None:
        # Unknown product: ask for quick add
        with st.sidebar:
            st.warning(f"Barcode inconnu: {bc}")
            with st.expander("Ajouter produit rapide"):
                name = st.text_input("Nom", key=f"quick_name_{bc}")
                price = st.number_input("Prix (TND)", min_value=0.0, step=0.1, key=f"quick_price_{bc}")
                tva = st.number_input("TVA %", min_value=0.0, max_value=100.0, step=1.0, value=0.0, key=f"quick_tva_{bc}")
                stock = st.number_input("Stock initial", min_value=0.0, step=1.0, value=0.0, key=f"quick_stk_{bc}")
                if st.button("Enregistrer produit", key=f"quick_save_{bc}"):
                    upsert_product(bc, name or f"Prod {bc}", float(price), float(stock), float(tva))
                    st.success("Produit ajouté. Re-scanner pour ajouter au panier.")
    else:
        bc = row["barcode"]
        if bc not in st.session_state.cart:
            st.session_state.cart[bc] = {
                "barcode": bc,
                "name": row["name"],
                "price": float(row["price"]),
                "tva": float(row["tva"] or 0.0),
                "qty": 0.0,
            }
        st.session_state.cart[bc]["qty"] += max(qty, 0.0)
    # clear input to be ready for next scan
    st.session_state.barcode_input = ""


def cart_totals(cart: Dict[str, Dict]) -> Tuple[float, float, float]:
    subtotal = 0.0
    tva_total = 0.0
    for it in cart.values():
        line_ht = it["price"] * it["qty"]
        line_tva = line_ht * (it["tva"] / 100.0)
        subtotal += line_ht
        tva_total += line_tva
    total = subtotal + tva_total
    return subtotal, tva_total, total


# ---------------------- RECEIPT (HTML) ----------------------

def render_receipt_html(sale_id: int, items: List[Dict], subtotal: float, tva_total: float, total: float,
                        paid_cash: float, paid_card: float, change: float, store_name: str, store_addr: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = "".join(
        f"<tr><td>{it['name']}</td><td style='text-align:right'>{it['qty']}</td><td style='text-align:right'>{it['price']:.3f}</td><td style='text-align:right'>{(it['qty']*it['price']):.3f}</td></tr>"
        for it in items
    )
    html = f"""
    <html>
    <head>
      <meta charset='utf-8'/>
      <style>
        body {{ font-family: monospace; width: 280px; margin: 0 auto; }}
        h2, h4 {{ text-align: center; margin: 4px 0; }}
        table {{ width: 100%; border-collapse: collapse; }}
        td {{ padding: 2px 0; font-size: 12px; }}
        .totals td {{ font-weight: bold; }}
        hr {{ border: 0; border-top: 1px dashed #aaa; margin: 6px 0; }}
      </style>
    </head>
    <body>
      <h2>{store_name}</h2>
      <h4>{store_addr}</h4>
      <hr/>
      <div>Ticket N° {sale_id} — {now}</div>
      <table>
        {rows}
        <tr class='totals'><td>Sous-total</td><td></td><td></td><td style='text-align:right'>{subtotal:.3f}</td></tr>
        <tr class='totals'><td>TVA</td><td></td><td></td><td style='text-align:right'>{tva_total:.3f}</td></tr>
        <tr class='totals'><td>Total</td><td></td><td></td><td style='text-align:right'>{total:.3f}</td></tr>
        <tr><td>Cash</td><td></td><td></td><td style='text-align:right'>{paid_cash:.3f}</td></tr>
        <tr><td>Carte</td><td></td><td></td><td style='text-align:right'>{paid_card:.3f}</td></tr>
        <tr><td>Monnaie</td><td></td><td></td><td style='text-align:right'>{change:.3f}</td></tr>
      </table>
      <hr/>
      <div style='text-align:center'>Merci et à bientôt!</div>
    </body>
    </html>
    """
    return html


# ---------------------- ESC/POS PRINTING ----------------------
try:
    from escpos.printer import Usb, Serial, Network
    ESC_POS_AVAILABLE = True
except Exception:
    ESC_POS_AVAILABLE = False


def get_escpos_printer():
    """Build and return an ESC/POS printer instance from sidebar settings."""
    if not ESC_POS_AVAILABLE:
        raise RuntimeError("python-escpos غير مثبّت. ثبّت: pip install python-escpos")
    mode = st.session_state.get("printer_mode", "USB")
    if mode == "USB":
        # Default to Epson TM-T20/TM-T88 IDs (can be changed from sidebar)
        vid = int(str(st.session_state.get("usb_vid", "0x04b8")).replace("0x", ""), 16)
        pid = int(str(st.session_state.get("usb_pid", "0x0e15")).replace("0x", ""), 16)
        in_ep = st.session_state.get("usb_in_ep") or None
        out_ep = st.session_state.get("usb_out_ep") or None
        return Usb(vid, pid, in_ep=in_ep, out_ep=out_ep)
    elif mode == "Network":
        host = st.session_state.get("net_host", "192.168.0.123")
        port = int(st.session_state.get("net_port", 9100))
        return Network(host, port=port, timeout=3)
    elif mode == "Serial":
        dev = st.session_state.get("ser_dev", "/dev/ttyUSB0")
        baud = int(st.session_state.get("ser_baud", 9600))
        return Serial(devfile=dev, baudrate=baud)
    else:
        raise RuntimeError("وضع الطابعة غير مفعّل.")


def print_ticket_thermal(items, subtotal, tva_total, total, paid_cash, paid_card, change, store_name, store_addr):
    """Send formatted receipt to ESC/POS thermal printer according to selected mode."""
    if not st.session_state.get("print_enabled", False):
        return
    try:
        p = get_escpos_printer()
        # Header
        p.set(align='center', bold=True)
        p.textln(store_name)
        p.textln(store_addr)
        p.textln(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        p.textln("-" * 32)
        # Body
        p.set(align='left', bold=False)
        for it in items:
            name = (it['name'] or '')[:20]
            qty = it['qty']
            price = it['price']
            p.textln(f"{name:20} {qty:>4.0f} x {price:>7.3f}")
        p.textln("-" * 32)
        p.set(bold=True)
        p.textln(f"Sous-total: {subtotal:.3f} TND")
        p.textln(f"TVA:        {tva_total:.3f} TND")
        p.textln(f"TOTAL:      {total:.3f} TND")
        p.textln("-" * 32)
        p.set(bold=False)
        p.textln(f"Cash:   {paid_cash:.3f}")
        p.textln(f"Carte:  {paid_card:.3f}")
        p.textln(f"Rendu:  {change:.3f}")
        p.textln("-" * 32)
        p.set(align='center')
        p.textln("Merci et à bientôt!")
        p.cut()
        try:
            p.close()
        except Exception:
            pass
        st.success("🖨️ تمّت الطباعة على الطابعة الحرارية.")
    except Exception as e:
        st.error(f"⚠️ خطأ في الطباعة الحرارية: {e}")


# ---------------------- PAGES ----------------------

def page_caisse():
    st.header("🧾 Caisse — Vente")
    colL, colR = st.columns([2, 1])

    with colL:
        st.caption("Scannez un code-barres (la douchette écrit le texte et tape Enter). Pour quantité: 3*<barcode>.")
        st.text_input(
            "Scan / Saisie code-barres",
            key="barcode_input",
            placeholder="ex: 6191234567890 ou 2*6191234567890",
            on_change=add_scan_to_cart,
        )

        # Cart table
        if not st.session_state.cart:
            st.info("Panier vide — scannez un article.")
        else:
            vals = list(st.session_state.cart.values())
            df = pd.DataFrame(vals) if vals else pd.DataFrame(columns=["barcode","name","qty","price","tva","total_ligne"])
            if not df.empty:
                df["total_ligne"] = df["qty"] * df["price"]
            st.dataframe(df[["barcode", "name", "qty", "price", "tva", "total_ligne"]] if not df.empty else df,
                         use_container_width=True)

            # qty controls
            c1, c2, c3 = st.columns(3)
            with c1:
                bc_minus = st.text_input("- Qte (barcode)", key="minus_bc", placeholder="code-barres")
                if st.button("−1") and bc_minus in st.session_state.cart:
                    st.session_state.cart[bc_minus]["qty"] = max(0.0, st.session_state.cart[bc_minus]["qty"] - 1)
                    if st.session_state.cart[bc_minus]["qty"] == 0:
                        st.session_state.cart.pop(bc_minus)
            with c2:
                bc_plus = st.text_input("+ Qte (barcode)", key="plus_bc", placeholder="code-barres")
                if st.button("+1") and bc_plus:
                    if bc_plus in st.session_state.cart:
                        st.session_state.cart[bc_plus]["qty"] += 1
                    else:
                        row = find_product(bc_plus)
                        if row:
                            st.session_state.cart[bc_plus] = {
                                "barcode": bc_plus,
                                "name": row["name"],
                                "price": float(row["price"]),
                                "tva": float(row["tva"] or 0.0),
                                "qty": 1.0,
                            }
            with c3:
                if st.button("🗑️ Vider panier"):
                    st.session_state.cart = {}

    with colR:
        subtotal, tva_total, total = cart_totals(st.session_state.cart)
        st.metric("Sous-total", f"{subtotal:.3f} TND")
        st.metric("TVA", f"{tva_total:.3f} TND")
        st.metric("Total", f"{total:.3f} TND")

        st.divider()
        st.subheader("Paiement")
        pay_method = st.selectbox("Méthode", ["Cash", "Carte", "Mixte"], index=0)
        paid_cash = 0.0
        paid_card = 0.0
        if pay_method == "Cash":
            paid_cash = st.number_input("Montant cash", min_value=0.0, step=1.0, value=float(total))
        elif pay_method == "Carte":
            paid_card = st.number_input("Montant carte", min_value=0.0, step=1.0, value=float(total))
        else:
            paid_cash = st.number_input("Cash", min_value=0.0, step=1.0, value=0.0)
            paid_card = st.number_input("Carte", min_value=0.0, step=1.0, value=float(total))

        note = st.text_input("Note (optionnel)")

        if st.button("✅ Encaisser", use_container_width=True, disabled=(total <= 0)):
            if total <= 0 or not st.session_state.cart:
                st.warning("Panier vide.")
            else:
                paid_total = (paid_cash or 0) + (paid_card or 0)
                if paid_total + 1e-9 < total:
                    st.error("Montant payé insuffisant.")
                else:
                    change = max(0.0, paid_cash - max(0.0, total - paid_card))
                    items = list(st.session_state.cart.values())
                    sale_id = record_sale(
                        items,
                        subtotal,
                        tva_total,
                        total,
                        float(paid_cash or 0),
                        float(paid_card or 0),
                        float(change),
                        pay_method,
                        note,
                    )
                    adjust_stock(items)
                    if paid_cash:
                        record_cash_movement("IN", float(paid_cash), f"Vente #{sale_id}")
                    st.success(f"Vente #{sale_id} enregistrée. Monnaie: {change:.3f} TND")

                    # Thermal print (optional)
                    store_name = st.session_state.get("store_name", "MA SUPERETTE")
                    store_addr = st.session_state.get("store_addr", "Adresse .. Téléphone ..")
                    print_ticket_thermal(items, subtotal, tva_total, total,
                                         float(paid_cash or 0), float(paid_card or 0), float(change),
                                         store_name, store_addr)

                    # HTML receipt download
                    html = render_receipt_html(
                        sale_id, items, subtotal, tva_total, total,
                        float(paid_cash or 0), float(paid_card or 0), float(change),
                        store_name, store_addr
                    )
                    st.download_button(
                        "🖨️ Télécharger ticket (HTML)",
                        data=html,
                        file_name=f"ticket_{sale_id}.html",
                        mime="text/html",
                        use_container_width=True,
                    )
                    st.session_state.cart = {}


def page_products():
    st.header("📦 Produits & Stock")

    # List
    df = _products_df_cache()
    st.dataframe(df, use_container_width=True)

    st.subheader("Ajouter / Modifier produit")
    with st.form("prod_form", clear_on_submit=True):
        c1, c2 = st.columns([2, 3])
        with c1:
            barcode = st.text_input("Code-barres", placeholder="ex: 6191234567890", help="Scannez avec la douchette ici")
            price = st.number_input("Prix (TND)", min_value=0.0, step=0.1)
            stock = st.number_input("Stock", min_value=0.0, step=1.0)
        with c2:
            name = st.text_input("Nom du produit")
            tva = st.number_input("TVA %", min_value=0.0, max_value=100.0, step=1.0, value=0.0)
        submitted = st.form_submit_button("Enregistrer produit")
        if submitted:
            if not barcode or not name:
                st.error("Code-barres et Nom sont obligatoires.")
            else:
                upsert_product(barcode.strip(), name.strip(), float(price), float(stock), float(tva))
                st.success("Produit enregistré.")


def page_cash_movements():
    st.header("💵 Mouvements de caisse")
    c1, c2 = st.columns(2)
    with c1:
        mtype = st.selectbox("Type", ["IN", "OUT"])
        amount = st.number_input("Montant", min_value=0.0, step=1.0)
        reason = st.text_input("Motif")
        if st.button("Ajouter mouvement"):
            if amount <= 0:
                st.error("Montant invalide")
            else:
                record_cash_movement(mtype, float(amount), reason)
                st.success("Mouvement enregistré.")
    with c2:
        conn = get_conn()
        df = pd.read_sql_query("SELECT * FROM cash_movements ORDER BY ts DESC", conn)
        conn.close()
        st.dataframe(df, use_container_width=True)


def page_reports():
    st.header("📊 Rapports (X/Z)")

    day = st.date_input("Jour", value=date.today())
    d0 = datetime.combine(day, datetime.min.time()).isoformat()
    d1 = datetime.combine(day, datetime.max.time()).isoformat()

    conn = get_conn()
    df = pd.read_sql_query(
        "SELECT * FROM sales WHERE ts BETWEEN ? AND ? ORDER BY ts DESC",
        conn,
        params=(d0, d1),
    )
    conn.close()

    st.subheader("Ventes du jour")
    if df.empty:
        st.info("Aucune vente pour ce jour.")
    else:
        st.dataframe(df[["id", "ts", "subtotal", "tva_total", "total", "paid_cash", "paid_card", "payment_method"]], use_container_width=True)
        st.download_button("⬇️ Export CSV", data=df.to_csv(index=False).encode("utf-8"), file_name=f"ventes_{day}.csv", mime="text/csv")

        total_ttc = df["total"].sum()
        total_cash = df["paid_cash"].sum()
        total_card = df["paid_card"].sum()
        nbr_tickets = len(df)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Chiffre d'affaires", f"{total_ttc:.3f} TND")
        c2.metric("Cash encaissé", f"{total_cash:.3f} TND")
        c3.metric("Carte encaissée", f"{total_card:.3f} TND")
        c4.metric("Tickets", str(nbr_tickets))

    st.subheader("Caisse (mouvements)")
    conn = get_conn()
    dfm = pd.read_sql_query(
        "SELECT * FROM cash_movements WHERE ts BETWEEN ? AND ? ORDER BY ts DESC",
        conn,
        params=(d0, d1),
    )
    conn.close()
    if dfm.empty:
        st.info("Aucun mouvement.")
    else:
        st.dataframe(dfm, use_container_width=True)
        solde = (dfm[dfm["type"] == "IN"]["amount"].sum() - dfm[dfm["type"] == "OUT"]["amount"].sum())
        st.metric("Solde net mouvements", f"{solde:.3f} TND")


# ---------------------- MAIN APP ----------------------

def config_sidebar():
    st.sidebar.subheader("Paramètres boutique")
    st.session_state.store_name = st.sidebar.text_input("Nom boutique", value=st.session_state.get("store_name", "Ma Superette"))
    st.session_state.store_addr = st.sidebar.text_input("Adresse/Contact", value=st.session_state.get("store_addr", "Rue xx, Tél: xx"))

    st.sidebar.divider()
    st.sidebar.subheader("🖨️ Impression thermique (ESC/POS)")
    if not ESC_POS_AVAILABLE:
        st.sidebar.warning("python-escpos غير مثبّت. نفّذ: pip install python-escpos")
    # Preset: Epson USB
    preset = st.sidebar.selectbox("Preset", ["Epson TM-T20/TM-T88 (USB)", "Aucun"], index=0)
    st.session_state.print_enabled = st.sidebar.checkbox("تفعيل الطباعة الحرارية", value=st.session_state.get("print_enabled", False))
    st.session_state.printer_mode = st.sidebar.selectbox(
        "وضع الاتصال",
        ["USB", "Network", "Serial", "None"],
        index=["USB","Network","Serial","None"].index(st.session_state.get("printer_mode", "USB"))
    )

    mode = st.session_state.printer_mode
    if mode == "USB":
        # Apply Epson defaults if preset chosen
        if preset == "Epson TM-T20/TM-T88 (USB)":
            st.session_state["usb_vid"] = st.session_state.get("usb_vid", "0x04b8")
            st.session_state["usb_pid"] = st.session_state.get("usb_pid", "0x0e15")
        st.session_state.usb_vid = st.sidebar.text_input("USB Vendor ID", value=st.session_state.get("usb_vid", "0x04b8"))
        st.session_state.usb_pid = st.sidebar.text_input("USB Product ID", value=st.session_state.get("usb_pid", "0x0e15"))
        st.session_state.usb_in_ep = st.sidebar.text_input("IN endpoint (optionnel)", value=st.session_state.get("usb_in_ep", ""))
        st.session_state.usb_out_ep = st.sidebar.text_input("OUT endpoint (optionnel)", value=st.session_state.get("usb_out_ep", ""))
    elif mode == "Network":
        st.session_state.net_host = st.sidebar.text_input("IP de l'imprimante", value=st.session_state.get("net_host", "192.168.0.123"))
        st.session_state.net_port = st.sidebar.number_input("Port", value=int(st.session_state.get("net_port", 9100)), step=1)
    elif mode == "Serial":
        st.session_state.ser_dev = st.sidebar.text_input("Périphérique (ex: /dev/ttyUSB0)", value=st.session_state.get("ser_dev", "/dev/ttyUSB0"))
        st.session_state.ser_baud = st.sidebar.number_input("Baudrate", value=int(st.session_state.get("ser_baud", 9600)), step=100)

    colA, colB = st.sidebar.columns(2)
    with colA:
        if st.button("🧪 Test print", use_container_width=True):
            try:
                print_ticket_thermal(
                    [{"name": "Test Item", "qty": 1, "price": 1.000}],
                    1.000, 0.000, 1.000, 1.000, 0.000, 0.000,
                    st.session_state.get("store_name",""), st.session_state.get("store_addr","")
                )
            except Exception as e:
                st.error(f"فشل الاختبار: {e}")
    with colB:
        st.sidebar.caption("Astuce: gardez le focus sur la zone de scan toute la journée.")


def main():
    init_db()
    init_state()

    st.title("🛒 Superette — Gestion Caisse (Code-barres)")
    tabs = st.tabs(["Caisse", "Produits", "Caisse (IN/OUT)", "Rapports"])

    with st.sidebar:
        config_sidebar()

    with tabs[0]:
        page_caisse()
    with tabs[1]:
        page_products()
    with tabs[2]:
        page_cash_movements()
    with tabs[3]:
        page_reports()


# --- Safe runner: surface exceptions instead of a white page ---
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error("⚠️ صار خطأ خلا الصفحة تبيّض. شوف التفاصيل:")
        st.exception(e)
        st.stop()
