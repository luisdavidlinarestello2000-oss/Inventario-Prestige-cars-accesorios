import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import json
import io
import traceback
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Prestige Cars Accesorios - Cloud",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CLAVE DE SEGURIDAD ---
CLAVE_ADMIN = "admin123"

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .main {background-color: #000000 !important;}
    h1, h2, h3, p, label, div, span, li, a, td, th {color: #ffffff !important;}
    h1, h2, h3 {color: #FFD700 !important; font-family: 'Segoe UI', sans-serif;}
    section[data-testid="stSidebar"] {background-color: #111111 !important; border-right: 1px solid #333;}
    .stButton > button {
        background-color: #FFD700 !important; color: #000000 !important;
        border: none !important; border-radius: 8px !important; font-weight: bold !important; width: 100% !important; margin-top: 10px;
    }
    .stButton > button:hover {background-color: #DAA520 !important; color: white !important;}
    input, select, textarea {background-color: #222222 !important; color: #ffffff !important; border: 1px solid #FFD700 !important;}
    div[data-testid="stDataFrame"] {background-color: #1a1a1a !important; color: white !important;}
    #MainMenu {visibility: hidden;} footer {visibility: hidden;}
    
    .socio-card {
        background-color: #1f2229; border: 2px solid #FFD700; border-radius: 15px;
        padding: 20px; text-align: center; color: white !important; margin-bottom: 10px;
    }
    .socio-name { font-size: 20px; font-weight: bold; color: #ffffff !important; }
    .socio-amount { font-size: 36px; font-weight: bold; color: #FFD700 !important; margin: 5px 0; }
    </style>
    """, unsafe_allow_html=True)

# --- CONEXIÓN A GOOGLE SHEETS ---
def get_gsheet_client():
    try:
        # Intentar leer de Streamlit Secrets (para la nube) o archivo local (para pruebas)
        if "GSA_CREDS" in st.secrets:
            creds_dict = st.secrets["GSA_CREDS"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, ["https://www.googleapis.com/auth/spreadsheets"])
        else:
            # Fallback para pruebas locales si tienes el archivo credentials.json
            if os.path.exists("credentials.json"):
                creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", ["https://www.googleapis.com/auth/spreadsheets"])
            else:
                return None
        
        client = gspread.authorize(creds)
        return client.open("PrestigeCarsDB") # Nombre exacto de tu hoja
    except Exception as e:
        st.error(f"Error conectando a Google Sheets: {e}")
        return None

def load_data_from_cloud():
    sh = get_gsheet_client()
    if not sh:
        # Si falla la conexión, retornar datos vacíos o por defecto
        return [], [], {"Diana Reina": 0.0, "Eduardo": 0.0}, 0, 0
    
    try:
        # Cargar Productos
        ws_prod = sh.worksheet("Productos")
        df_prod = pd.DataFrame(ws_prod.get_all_records())
        productos = df_prod.to_dict('records') if not df_prod.empty else []
        
        # Cargar Ventas
        ws_vent = sh.worksheet("Ventas")
        df_vent = pd.DataFrame(ws_vent.get_all_records())
        ventas = df_vent.to_dict('records') if not df_vent.empty else []
        
        # Convertir items_json de string a lista
        for v in ventas:
            if isinstance(v.get('items_json'), str):
                try:
                    v['items'] = json.loads(v['items_json'])
                except:
                    v['items'] = []
            else:
                v['items'] = []
            
            # Asegurar tipos numéricos
            v['total_cobrado'] = float(v.get('total_cobrado', 0))
            v['ganancia_diana'] = float(v.get('ganancia_diana', 0))
            v['ganancia_eduardo'] = float(v.get('ganancia_eduardo', 0))

        # Cargar Consecutivos
        ws_conf = sh.worksheet("Config")
        conf_data = ws_conf.get_all_records()
        consec_recibo = 0
        consec_factura = 0
        for row in conf_data:
            if str(row.get('clave', '')).strip() == 'consecutivo_recibo':
                consec_recibo = int(row.get('valor', 0))
            if str(row.get('clave', '')).strip() == 'consecutivo_factura':
                consec_factura = int(row.get('valor', 0))
        
        # Recalcular ganancias totales
        ganancias = {"Diana Reina": 0.0, "Eduardo": 0.0}
        for v in ventas:
            ganancias["Diana Reina"] += v.get('ganancia_diana', 0)
            ganancias["Eduardo"] += v.get('ganancia_eduardo', 0)
            
        return productos, ventas, ganancias, consec_recibo, consec_factura
    except Exception as e:
        st.error(f"Error cargando datos: {e}")
        return [], [], {"Diana Reina": 0.0, "Eduardo": 0.0}, 0, 0

def save_sale_to_cloud(venta):
    sh = get_gsheet_client()
    if not sh: return False
    
    try:
        ws_vent = sh.worksheet("Ventas")
        items_json = json.dumps(venta['items'])
        
        ws_vent.append_row([
            venta['id'],
            venta['fecha'],
            venta['tipo_documento'],
            venta['consecutivo'],
            venta['metodo'],
            venta['total_cobrado'],
            items_json,
            venta['ganancia_diana'],
            venta['ganancia_eduardo'],
            venta['mes']
        ])
        
        # Actualizar consecutivo en Config
        ws_conf = sh.worksheet("Config")
        rows = ws_conf.get_all_values()
        for i, row in enumerate(rows):
            if row[0] == 'consecutivo_recibo' and venta['tipo_documento'] == 'RECIBO':
                ws_conf.update_cell(i+1, 2, int(venta['consecutivo'].split('-')[1]))
            elif row[0] == 'consecutivo_factura' and venta['tipo_documento'] == 'FACTURA':
                ws_conf.update_cell(i+1, 2, int(venta['consecutivo'].split('-')[1]))
        
        # Actualizar Stock en Productos (opcional, pero recomendado)
        ws_prod = sh.worksheet("Productos")
        df_prod = pd.DataFrame(ws_prod.get_all_records())
        for item in venta['items']:
            idx = df_prod[df_prod['id'] == item['id']].index
            if not idx.empty:
                row_idx = idx[0] + 2 # +2 porque empieza en fila 2 y dataframe es 0-indexed
                current_stock = int(ws_prod.cell(row_idx, 5).value)
                new_stock = current_stock - item['qty']
                ws_prod.update_cell(row_idx, 5, new_stock)
                
        return True
    except Exception as e:
        st.error(f"Error guardando: {e}")
        return False

# --- INICIALIZACIÓN SEGURA DE DATOS ---
def init_data():
    if 'productos' not in st.session_state:
        prods, vents, gains, rec, fac = load_data_from_cloud()
        if not prods: # Si falla la carga, usar datos por defecto
            prods = [
                {"id": 1, "nombre": "Bombillo LED H4 Premium", "costo": 50000, "precio": 100000, "stock": 10, "minimo": 5, "inst": 15000},
                {"id": 2, "nombre": "Plumillas Bosch Aerotwin", "costo": 25000, "precio": 60000, "stock": 15, "minimo": 5, "inst": 10000},
                {"id": 3, "nombre": "Kit Limpieza Interior Lujo", "costo": 15000, "precio": 40000, "stock": 8, "minimo": 3, "inst": 0}
            ]
        st.session_state.productos = prods
        st.session_state.ventas = vents
        st.session_state.ganancias_totales = gains
        st.session_state.consecutivo_recibo = rec
        st.session_state.consecutivo_factura = fac
        st.session_state.carrito = []
        st.session_state.historial_meses = []
        st.session_state.last_document = ""
        st.session_state.last_doc_type = ""

init_data()

# ... (El resto del código de funciones auxiliares generate_document_text, etc., se mantiene igual que tu versión anterior) ...
def get_backup_data():
    return {
        "fecha": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "productos": st.session_state.productos,
        "ventas": st.session_state.ventas,
        "ganancias_totales": st.session_state.ganancias_totales,
        "consecutivo_recibo": st.session_state.consecutivo_recibo,
        "consecutivo_factura": st.session_state.consecutivo_factura,
        "historial_meses": st.session_state.historial_meses
    }

def generate_document_text(carrito, total_final, metodo, doc_type, consec_num, iva_incluido=False):
    lines = []
    lines.append("=" * 34)
    if doc_type == "FACTURA":
        lines.append(f"      FACTURA DE VENTA No. {consec_num}")
        lines.append("   PRESTIGE CARS ACCESORIOS")
        lines.append("   NIT: 900.000.000-0")
    else:
        lines.append(f"      RECIBO DE CAJA No. {consec_num}")
        lines.append("   PRESTIGE CARS ACCESORIOS")
        lines.append("   Cra 29a N 70 80 Bogotá")
    lines.append("=" * 34)
    lines.append(f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    lines.append("-" * 34)
    for item in carrito:
        precio_mostrar = item['precio'] + (item['inst'] if item.get('con_inst') else 0)
        total_item = precio_mostrar * item['qty']
        name = item['nombre'][:22] + ".." if len(item['nombre']) > 24 else item['nombre']
        lines.append(f"{name:<24} x{item['qty']:<2} ${total_item:>10,.0f}")
    lines.append("-" * 34)
    if doc_type == "FACTURA" and iva_incluido:
        base_sin_iva = total_final / 1.19
        iva_val = total_final - base_sin_iva
        lines.append(f"SUBTOTAL:        ${base_sin_iva:>10,.0f}")
        lines.append(f"IVA (19%):       ${iva_val:>10,.0f}")
        lines.append(f"TOTAL:           ${total_final:>10,.0f}")
    else:
        lines.append(f"TOTAL A PAGAR:   ${total_final:>10,.0f}")
    lines.append(f"MÉTODO: {metodo:<24}")
    lines.append("=" * 34)
    lines.append("   Gracias por tu compra")
    lines.append("=" * 34)
    return "\n".join(lines)

# --- BARRA LATERAL ---
with st.sidebar:
    st.markdown("""
    <div style="text-align: center; margin-bottom: 20px; border-bottom: 2px solid #FFD700; padding-bottom: 10px;">
        <h1 style="color: #FFD700; margin: 0; font-style: italic;">Prestige</h1>
        <h4 style="color: white; margin: 0; letter-spacing: 2px;">CARS ACCESORIOS</h4>
    </div>
    """, unsafe_allow_html=True)
    st.info(f"Próximo Recibo: RC-{st.session_state.consecutivo_recibo + 1:03d}\nPróxima Factura: FV-{st.session_state.consecutivo_factura + 1:03d}")
    
    opcion = st.radio("Menú Principal:", [
        "💰 Punto de Venta", 
        "➕ Agregar Ítem", 
        "📦 Inventario", 
        "📊 Estadísticas", 
        " Socios",
        "🔒 Administración"
    ], index=0)

# ============================================================
# 1. PUNTO DE VENTA (MODIFICADO PARA GUARDAR EN NUBE)
# ============================================================
if opcion == "💰 Punto de Venta":
    try:
        st.title(" Nueva Venta")
        col_izq, col_der = st.columns([2, 1])
        
        with col_izq:
            st.subheader("1. Agregar Productos")
            nombres = [p['nombre'] for p in st.session_state.productos]
            prod_sel = st.selectbox("Buscar...", [""] + nombres)
            
            if prod_sel:
                prod = next((p for p in st.session_state.productos if p['nombre'] == prod_sel), None)
                if prod:
                    c1, c2 = st.columns(2)
                    c1.metric("Precio Base", f"${prod['precio']:,.0f}")
                    c2.metric("Stock", f"{prod['stock']}")
                    
                    qty = st.number_input("Cantidad", 1, prod['stock'], 1)
                    inst = st.checkbox("¿Lleva Instalación?")
                    
                    if st.button("➕ Agregar al Carrito"):
                        found = False
                        for item in st.session_state.carrito:
                            if item['id'] == prod['id']:
                                if item['qty'] + qty <= prod['stock']:
                                    item['qty'] += qty
                                    if inst: item['con_inst'] = True
                                    st.toast("Actualizado")
                                else: st.error("Sin stock")
                                found = True; break
                        if not found and qty <= prod['stock']:
                            st.session_state.carrito.append({
                                "id": prod['id'], "nombre": prod['nombre'], "precio": prod['precio'],
                                "costo": prod['costo'], "inst": prod['inst'], "qty": qty, "con_inst": inst
                            })
                            st.toast("Agregado")
                        st.rerun()

            st.divider()
            st.subheader("2. Carrito Actual")
            if st.session_state.carrito:
                total_real = sum((i['precio'] + (i['inst'] if i.get('con_inst') else 0)) * i['qty'] for i in st.session_state.carrito)
                
                for idx, item in enumerate(st.session_state.carrito):
                    precio_unit_final = item['precio'] + (item['inst'] if item.get('con_inst') else 0)
                    sub = precio_unit_final * item['qty']
                    icon = " 🔧" if item.get('con_inst') else ""
                    with st.expander(f"{item['nombre']} x{item['qty']}{icon} - ${sub:,.0f}"):
                        if st.button("️ Quitar", key=f"del_{idx}"):
                            st.session_state.carrito.pop(idx); st.rerun()
                
                st.markdown(f"## TOTAL A COBRAR: ${total_real:,.0f}")
                
                st.divider()
                st.subheader("3. Tipo de Documento")
                
                tipo_ajuste = st.radio("Ajuste", ["Sin Descuento", "Descuento (%)", "Precio Final"], horizontal=True)
                base_pago = total_real
                
                if tipo_ajuste == "Descuento (%)":
                    pct = st.slider("% Descuento", 0, 100, 0)
                    base_pago = total_real * (1 - pct/100)
                elif tipo_ajuste == "Precio Final":
                    base_pago = st.number_input("Precio Acordado ($)", 0, int(total_real), int(total_real))
                
                metodo = st.selectbox("Método Pago", ["Efectivo", "Nequi", "DaviPlata", "Tarjeta", "Breme"])
                
                col_btn1, col_btn2 = st.columns(2)
                
                with col_btn1:
                    if st.button(" GENERAR RECIBO DE CAJA", type="primary", use_container_width=True, key="btn_recibo"):
                        st.session_state.consecutivo_recibo += 1
                        consec_num = f"RC-{st.session_state.consecutivo_recibo:03d}"
                        gan_base = sum((i['precio'] - i['costo']) * i['qty'] for i in st.session_state.carrito)
                        gan_inst = sum(i['inst'] * i['qty'] for i in st.session_state.carrito if i.get('con_inst'))
                        
                        st.session_state.ganancias_totales["Diana Reina"] += gan_base / 2
                        st.session_state.ganancias_totales["Eduardo"] += (gan_base / 2) + gan_inst
                        
                        # Descontar stock localmente
                        for item in st.session_state.carrito:
                            p_real = next(p for p in st.session_state.productos if p['id'] == item['id'])
                            p_real['stock'] -= item['qty']
                        
                        nueva_venta = {
                            "id": len(st.session_state.ventas)+1, "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
                            "items": st.session_state.carrito.copy(), "total_cobrado": base_pago, "metodo": metodo,
                            "tipo_documento": "RECIBO", "consecutivo": consec_num,
                            "ganancia_diana": gan_base / 2, "ganancia_eduardo": (gan_base / 2) + gan_inst,
                            "mes": datetime.now().strftime("%Y-%m"), "tiene_iva": False
                        }
                        
                        # GUARDAR EN LA NUBE (GOOGLE SHEETS)
                        if save_sale_to_cloud(nueva_venta):
                            st.session_state.ventas.append(nueva_venta)
                            doc_text = generate_document_text(st.session_state.carrito, base_pago, metodo, "RECIBO", consec_num, False)
                            st.session_state.last_document = doc_text
                            st.session_state.last_doc_type = "RECIBO"
                            st.session_state.carrito = []
                            st.balloons(); st.success(f"¡Recibo {consec_num} generado y guardado en la nube!"); st.rerun()
                        else:
                            st.error("No se pudo guardar en la nube. Revisa la conexión.")
                
                with col_btn2:
                    total_con_iva = base_pago * 1.19
                    if st.button(" GENERAR FACTURA DE VENTA", type="primary", use_container_width=True, key="btn_factura"):
                        st.session_state.consecutivo_factura += 1
                        consec_num = f"FV-{st.session_state.consecutivo_factura:03d}"
                        gan_base = sum((i['precio'] - i['costo']) * i['qty'] for i in st.session_state.carrito)
                        gan_inst = sum(i['inst'] * i['qty'] for i in st.session_state.carrito if i.get('con_inst'))
                        
                        st.session_state.ganancias_totales["Diana Reina"] += gan_base / 2
                        st.session_state.ganancias_totales["Eduardo"] += (gan_base / 2) + gan_inst
                        
                        for item in st.session_state.carrito:
                            p_real = next(p for p in st.session_state.productos if p['id'] == item['id'])
                            p_real['stock'] -= item['qty']
                        
                        nueva_venta = {
                            "id": len(st.session_state.ventas)+1, "fecha": datetime.now().strftime("%d/%m/%Y %H:%M"),
                            "items": st.session_state.carrito.copy(), "total_cobrado": total_con_iva, "metodo": metodo,
                            "tipo_documento": "FACTURA", "consecutivo": consec_num,
                            "ganancia_diana": gan_base / 2, "ganancia_eduardo": (gan_base / 2) + gan_inst,
                            "mes": datetime.now().strftime("%Y-%m"), "tiene_iva": True
                        }
                        
                        # GUARDAR EN LA NUBE
                        if save_sale_to_cloud(nueva_venta):
                            st.session_state.ventas.append(nueva_venta)
                            doc_text = generate_document_text(st.session_state.carrito, total_con_iva, metodo, "FACTURA", consec_num, True)
                            st.session_state.last_document = doc_text
                            st.session_state.last_doc_type = "FACTURA"
                            st.session_state.carrito = []
                            st.balloons(); st.success(f"¡Factura {consec_num} generada y guardada en la nube!"); st.rerun()
                        else:
                            st.error("No se pudo guardar en la nube.")
            else: 
                st.info("Carrito vacío.")

        with col_der:
            st.subheader(" Documento Generado")
            if st.session_state.last_document:
                st.success(f"**{st.session_state.last_doc_type}** listo.")
                st.text_area("Vista Previa", value=st.session_state.last_document, height=500)
                c1, c2 = st.columns(2)
                with c1:
                    fname = f"{st.session_state.last_doc_type}_{st.session_state.last_document.split('No. ')[1].split()[0]}.txt"
                    st.download_button(" Descargar", st.session_state.last_document, fname, "text/plain", use_container_width=True)
                with c2:
                    if st.button(" Imprimir", use_container_width=True): st.js_run_script("window.print();")
                if st.button("Limpiar"): del st.session_state.last_document; del st.session_state.last_doc_type; st.rerun()
            else:
                st.info("Realiza una venta.")
    except Exception as e:
        st.error(f"❌ Error en Punto de Venta: {e}")
        st.code(traceback.format_exc())

# ... (Aquí debes pegar el resto de tus secciones: Agregar Ítem, Inventario, Estadísticas, Socios, Admin exactamente como las tenías antes, solo asegúrate de que no sobrescriban la lógica de init_data) ...
# Para ahorrar espacio, asumo que copiarás las secciones 2 a 6 de tu código anterior aquí tal cual están, ya que la lógica de lectura/escritura ya está manejada en init_data y save_sale_to_cloud.

# ============================================================
# 2. AGREGAR ÍTEM (Debes agregar lógica para guardar en Sheets si quieres persistencia de productos también, pero por ahora basta con el backup manual o recargar)
# ============================================================
elif opcion == "➕ Agregar Ítem":
    try:
        st.title("➕ Nuevo Producto")
        with st.form("new_item_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                nom = st.text_input("Nombre")
                costo = st.number_input("Costo Real ($)", 0, step=1000)
                precio = st.number_input("Precio Venta ($)", 0, step=1000)
            with c2:
                stock = st.number_input("Stock", 0, 10)
                minimo = st.number_input("Mínimo", 1, 5)
                inst_cost = st.number_input("Costo Inst. ($)", 0, step=1000)
            
            if st.form_submit_button(" Guardar"):
                if nom and precio > costo:
                    new_id = max([p['id'] for p in st.session_state.productos], default=0) + 1
                    nuevo_prod = {
                        "id": new_id, "nombre": nom, "costo": int(costo), "precio": int(precio),
                        "stock": int(stock), "minimo": int(minimo), "inst": int(inst_cost)
                    }
                    st.session_state.productos.append(nuevo_prod)
                    # Aquí podrías llamar a una función save_product_to_cloud(nuevo_prod) si implementaras esa lógica
                    st.success("Guardado (Localmente. Usa Backup para persistencia en nube si no configuras Sheets para productos)"); st.rerun()
                else: st.error("Datos inválidos")
    except Exception as e:
        st.error(f"❌ Error al agregar ítem: {e}")

# ... (PEGA AQUÍ EL RESTO DE TU CÓDIGO ORIGINAL: SECCIONES 3, 4, 5, 6 EXACTAMENTE IGUALES) ...
# Para asegurar que funcione, simplemente pega todo el código desde "# ============================================================ # 3. INVENTARIO..." hasta el final de tu archivo original aquí abajo.
# La clave es que init_data() al principio ya carga todo desde Sheets si está disponible.
