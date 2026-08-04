 import os
import re
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes, CommandHandler
import pytesseract
from PIL import Image
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ==================== CONFIGURACION ====================

TELEGRAM_TOKEN = "8224897386:AAGyv-f_GqAoyfQGy9Lu-sA3NCSSA8K2LmM"
GOOGLE_SHEET_ID = "1HK27kQ5TvAH4p0Zt6OgNkiUlR6V0JsVxcljw2arV2nI"
SHEET_NAME = "Registro"
FINANZAS_SHEET = "Finanzas"  # Nueva hoja para capital, emergencia e inversiones
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ===== LEE CREDENCIALES DESDE VARIABLE DE RAILWAY =====
cred_json = os.getenv("CREDENTIALS_JSON")
if cred_json:
    creds_dict = json.loads(cred_json)
    with open("credenciales.json", "w") as f:
        json.dump(creds_dict, f)
    CREDENTIALS_FILE = "credenciales.json"
    print("✅ Credenciales cargadas desde variable CREDENTIALS_JSON")
else:
    CREDENTIALS_FILE = os.path.join(BASE_DIR, "credenciales.json")
    print("⚠️ Usando archivo credenciales.json local")
# ========================================================

TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

if TESSERACT_PATH and TESSERACT_PATH.strip():
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# ==================== CLASES Y LISTAS ====================

class ColumnasSheet:
    TIMESTAMP = 0
    FECHA = 1
    COMERCIO = 2
    CATEGORIA = 3
    MONTO = 4
    FORMAS_PAGO = 5
    TIPO = 6

CATEGORIAS_LIST = [
    "Supermercado",
    "Salud",
    "Gasolina",
    "Comidas fuera",
    "Entretenimiento",
    "Hogar",
    "Transporte",
    "Inversion",
    "Emergencia"
]

FORMAS_PAGO_LIST = [
    "Efectivo",
    "Tarjeta debito",
    "Tarjeta credito"
]

# ==================== DATOS EN MEMORIA (respaldo temporal) ====================
datos_usuario = {}

# ==================== CONEXION GOOGLE SHEETS ====================

def conectar_google_sheets():
    """Conecta con Google Sheets y retorna la hoja de gastos"""
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(GOOGLE_SHEET_ID)
    try:
        worksheet = sheet.worksheet(SHEET_NAME)
    except:
        worksheet = sheet.add_worksheet(title=SHEET_NAME, rows=100, cols=20)
        worksheet.append_row(["Timestamp", "Fecha", "Comercio", "Categoria", "Monto", "Forma Pago", "Tipo"])
    return worksheet

def conectar_google_sheets_finanzas():
    """Conecta con Google Sheets y retorna la hoja de finanzas (capital, emergencia, inversiones)"""
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(GOOGLE_SHEET_ID)
    try:
        worksheet = sheet.worksheet(FINANZAS_SHEET)
    except:
        worksheet = sheet.add_worksheet(title=FINANZAS_SHEET, rows=100, cols=20)
        worksheet.append_row(["Fecha", "Concepto", "Categoria", "Monto", "Saldo", "Nota"])
    return worksheet

# ==================== FUNCIONES DE FINANZAS ====================

def obtener_saldo_finanzas(worksheet, categoria):
    """Lee el saldo actual de una categoría desde Google Sheets"""
    try:
        registros = worksheet.get_all_records()
        saldo = 0
        for r in registros:
            if r.get('Categoria') == categoria:
                saldo += float(r.get('Monto', 0))
        return saldo
    except:
        return 0

def guardar_movimiento_finanzas(worksheet, concepto, categoria, monto, nota=""):
    """Guarda un movimiento en la hoja Finanzas"""
    try:
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        fecha = datetime.now().strftime("%d/%m/%Y")
        # Obtener el saldo actual
        saldo_actual = obtener_saldo_finanzas(worksheet, categoria)
        nuevo_saldo = saldo_actual + monto
        fila = [fecha, concepto, categoria, monto, nuevo_saldo, nota]
        worksheet.append_row(fila, value_input_option='USER_ENTERED')
        return True, nuevo_saldo
    except Exception as e:
        print(f"Error al guardar movimiento: {e}")
        return False, 0

# ==================== GUARDAR GASTOS ====================

def guardar_en_sheets(worksheet, fecha, comercio, monto, categoria, formas_pago, tipo="gasto"):
    try:
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        fila = [''] * 7
        fila[ColumnasSheet.FECHA] = fecha
        fila[ColumnasSheet.COMERCIO] = comercio
        fila[ColumnasSheet.CATEGORIA] = categoria
        fila[ColumnasSheet.MONTO] = float(monto)
        fila[ColumnasSheet.FORMAS_PAGO] = formas_pago
        fila[ColumnasSheet.TIMESTAMP] = timestamp
        fila[ColumnasSheet.TIPO] = tipo
        worksheet.append_row(fila, value_input_option='USER_ENTERED')
        return True
    except Exception as e:
        print(f"Error al guardar en Google Sheets: {e}")
        return False

# ==================== EXTRACCION DE DATOS DE FACTURA ====================

def extraer_datos_factura(imagen_path):
    try:
        img = Image.open(imagen_path)
        texto = pytesseract.image_to_string(img, lang='spa')
        print(f"Texto extraido:\n{texto}\n")
        monto_match = re.search(r'\$?\s*(\d{1,}[.,]\d{2})\b', texto)
        monto = monto_match.group(1) if monto_match else "No detectado"
        lineas = [l.strip() for l in texto.split('\n') if l.strip()]
        comercio = lineas[0] if lineas else "No detectado"
        comercio = comercio[:50]
        fecha = datetime.now().strftime("%d/%m/%Y")
        return fecha, comercio, monto
    except Exception as e:
        print(f"Error al procesar imagen: {e}")
        return "Error", "Error", "Error"

# ==================== TECLADOS ====================

def crear_teclado_confirmacion():
    keyboard = [[InlineKeyboardButton("✅ Sí, guardar", callback_data="confirmar_si"), InlineKeyboardButton("✏️ No, editar", callback_data="confirmar_no")]]
    return InlineKeyboardMarkup(keyboard)

def crear_teclado_continuar():
    keyboard = [[InlineKeyboardButton("➡️ Sí, Continuar", callback_data="continuar"), InlineKeyboardButton("✏️ No, editar", callback_data="confirmar_no")]]
    return InlineKeyboardMarkup(keyboard)

def crear_teclado_categorias():
    keyboard = []
    for categoria in CATEGORIAS_LIST:
        keyboard.append([InlineKeyboardButton(categoria, callback_data=f"cat_{categoria}")])
    return InlineKeyboardMarkup(keyboard)

def crear_teclado_formas_pago():
    keyboard = []
    for forma in FORMAS_PAGO_LIST:
        keyboard.append([InlineKeyboardButton(forma, callback_data=f"fp_{forma}")])
    return InlineKeyboardMarkup(keyboard)

def crear_teclado_campos():
    keyboard = [
        [InlineKeyboardButton("📅 Fecha", callback_data="editar_fecha")],
        [InlineKeyboardButton("🏪 Comercio", callback_data="editar_comercio")],
        [InlineKeyboardButton("💰 Monto", callback_data="editar_monto")],
        [InlineKeyboardButton("🏷️ Categoria", callback_data="editar_categoria")],
        [InlineKeyboardButton("💳 Forma de pago", callback_data="editar_forma_pago")],
        [InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ==================== COMANDOS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏦 *Bienvenido a tu Asistente Financiero Personal!*\n\n"
        "Comandos disponibles:\n"
        "/start - Mostrar este mensaje\n"
        "/hola - Saludo\n"
        "/gasto - Registrar un gasto manual\n"
        "/capital_inicial - Registrar tu saldo inicial\n"
        "/ingreso - Sumar dinero a tu saldo\n"
        "/retiro - Restar dinero de tu saldo\n"
        "/balance - Ver tu saldo actual\n"
        "/total - Ver total gastado\n"
        "/emergencia - Ver fondo de emergencia\n"
        "/emergencia_ingresar - Agregar al fondo de emergencia\n"
        "/emergencia_retirar - Retirar del fondo de emergencia\n"
        "/inversiones - Ver tus inversiones\n"
        "/inversiones_ingresar - Agregar a inversiones\n"
        "/inversiones_retirar - Retirar de inversiones\n"
        "/ayuda - Mostrar todos los comandos\n\n"
        "📸 Tambien puedes enviar una foto de un ticket y lo procesare."
    )

async def hola(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("¡Hola! ¿Cómo estás? Envía una foto de tu factura o usa /gasto para registrar manualmente.")

# ---------- CAPITAL ----------
async def capital_inicial(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Registra el capital inicial (solo si no existe)"""
    try:
        monto = float(context.args[0].replace('$', '').replace(',', ''))
        worksheet = conectar_google_sheets_finanzas()
        saldo_actual = obtener_saldo_finanzas(worksheet, "capital")
        if saldo_actual > 0:
            await update.message.reply_text("⚠️ Ya tienes un capital registrado. Usa /ingreso para sumar o /retiro para restar.")
            return
        ok, nuevo_saldo = guardar_movimiento_finanzas(worksheet, "Capital inicial", "capital", monto, "Primer registro")
        if ok:
            await update.message.reply_text(f"✅ Capital inicial guardado: ${monto:,.2f}\n💰 Saldo actual: ${nuevo_saldo:,.2f}")
        else:
            await update.message.reply_text("❌ Error al guardar en Google Sheets.")
    except:
        await update.message.reply_text("📌 Uso correcto: /capital_inicial 25000")

async def ingreso(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Suma dinero al capital (ingresos)"""
    try:
        monto = float(context.args[0].replace('$', '').replace(',', ''))
        worksheet = conectar_google_sheets_finanzas()
        saldo_actual = obtener_saldo_finanzas(worksheet, "capital")
        ok, nuevo_saldo = guardar_movimiento_finanzas(worksheet, "Ingreso", "capital", monto, "Ingreso registrado")
        if ok:
            await update.message.reply_text(f"✅ Ingreso registrado: +${monto:,.2f}\n💰 Nuevo saldo: ${nuevo_saldo:,.2f}")
        else:
            await update.message.reply_text("❌ Error al guardar en Google Sheets.")
    except:
        await update.message.reply_text("📌 Uso correcto: /ingreso 1500")

async def retiro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Resta dinero del capital (retiros)"""
    try:
        monto = float(context.args[0].replace('$', '').replace(',', ''))
        worksheet = conectar_google_sheets_finanzas()
        saldo_actual = obtener_saldo_finanzas(worksheet, "capital")
        if monto > saldo_actual:
            await update.message.reply_text(f"❌ No tienes suficiente saldo. Saldo actual: ${saldo_actual:,.2f}")
            return
        ok, nuevo_saldo = guardar_movimiento_finanzas(worksheet, "Retiro", "capital", -monto, "Retiro registrado")
        if ok:
            await update.message.reply_text(f"✅ Retiro registrado: -${monto:,.2f}\n💰 Nuevo saldo: ${nuevo_saldo:,.2f}")
        else:
            await update.message.reply_text("❌ Error al guardar en Google Sheets.")
    except:
        await update.message.reply_text("📌 Uso correcto: /retiro 500")

# ---------- EMERGENCIA ----------
async def emergencia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ver el fondo de emergencia"""
    worksheet = conectar_google_sheets_finanzas()
    saldo = obtener_saldo_finanzas(worksheet, "emergencia")
    await update.message.reply_text(f"🆘 *Fondo de Emergencia:* ${saldo:,.2f}")

async def emergencia_ingresar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Agregar al fondo de emergencia"""
    try:
        monto = float(context.args[0].replace('$', '').replace(',', ''))
        worksheet = conectar_google_sheets_finanzas()
        ok, nuevo_saldo = guardar_movimiento_finanzas(worksheet, "Ingreso a emergencia", "emergencia", monto, "Agregado a emergencia")
        if ok:
            await update.message.reply_text(f"✅ Emergencia +${monto:,.2f}\n🆘 Total: ${nuevo_saldo:,.2f}")
        else:
            await update.message.reply_text("❌ Error al guardar en Google Sheets.")
    except:
        await update.message.reply_text("📌 Uso correcto: /emergencia_ingresar 1000")

async def emergencia_retirar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retirar del fondo de emergencia"""
    try:
        monto = float(context.args[0].replace('$', '').replace(',', ''))
        worksheet = conectar_google_sheets_finanzas()
        saldo_actual = obtener_saldo_finanzas(worksheet, "emergencia")
        if monto > saldo_actual:
            await update.message.reply_text(f"❌ No tienes suficiente en emergencia. Saldo: ${saldo_actual:,.2f}")
            return
        ok, nuevo_saldo = guardar_movimiento_finanzas(worksheet, "Retiro de emergencia", "emergencia", -monto, "Retiro de emergencia")
        if ok:
            await update.message.reply_text(f"✅ Retiro de emergencia: -${monto:,.2f}\n🆘 Total: ${nuevo_saldo:,.2f}")
        else:
            await update.message.reply_text("❌ Error al guardar en Google Sheets.")
    except:
        await update.message.reply_text("📌 Uso correcto: /emergencia_retirar 500")

# ---------- INVERSIONES ----------
async def inversiones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ver las inversiones"""
    worksheet = conectar_google_sheets_finanzas()
    saldo = obtener_saldo_finanzas(worksheet, "inversion")
    await update.message.reply_text(f"📈 *Inversiones:* ${saldo:,.2f}")

async def inversiones_ingresar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Agregar a inversiones"""
    try:
        monto = float(context.args[0].replace('$', '').replace(',', ''))
        worksheet = conectar_google_sheets_finanzas()
        ok, nuevo_saldo = guardar_movimiento_finanzas(worksheet, "Ingreso a inversiones", "inversion", monto, "Agregado a inversiones")
        if ok:
            await update.message.reply_text(f"✅ Inversión +${monto:,.2f}\n📈 Total: ${nuevo_saldo:,.2f}")
        else:
            await update.message.reply_text("❌ Error al guardar en Google Sheets.")
    except:
        await update.message.reply_text("📌 Uso correcto: /inversiones_ingresar 1000")

async def inversiones_retirar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Retirar de inversiones"""
    try:
        monto = float(context.args[0].replace('$', '').replace(',', ''))
        worksheet = conectar_google_sheets_finanzas()
        saldo_actual = obtener_saldo_finanzas(worksheet, "inversion")
        if monto > saldo_actual:
            await update.message.reply_text(f"❌ No tienes suficiente en inversiones. Saldo: ${saldo_actual:,.2f}")
            return
        ok, nuevo_saldo = guardar_movimiento_finanzas(worksheet, "Retiro de inversiones", "inversion", -monto, "Retiro de inversiones")
        if ok:
            await update.message.reply_text(f"✅ Retiro de inversión: -${monto:,.2f}\n📈 Total: ${nuevo_saldo:,.2f}")
        else:
            await update.message.reply_text("❌ Error al guardar en Google Sheets.")
    except:
        await update.message.reply_text("📌 Uso correcto: /inversiones_retirar 500")

# ---------- GASTO MANUAL ----------
async def gasto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Registra un gasto manual"""
    try:
        texto = ' '.join(context.args)
        monto_match = re.search(r'(\d{1,}[.,]\d{0,2})', texto)
        monto = float(monto_match.group(1).replace(',', ''))
        concepto = texto.replace(monto_match.group(1), '').strip()
        if not concepto:
            concepto = "Gasto manual"
        datos_usuario[update.effective_user.id] = {
            'fecha': datetime.now().strftime("%d/%m/%Y"),
            'comercio': concepto,
            'monto': str(monto),
            'categoria': None,
            'formas_pago': None,
            'imagen_path': None
        }
        mensaje = f"Gasto detectado: ${monto:,.2f} en {concepto}\nSelecciona la categoria:"
        await update.message.reply_text(mensaje, reply_markup=crear_teclado_categorias())
    except:
        await update.message.reply_text("📌 Uso correcto: /gasto 350 Comida")

# ---------- BALANCE ----------
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el resumen financiero completo"""
    worksheet_finanzas = conectar_google_sheets_finanzas()
    capital = obtener_saldo_finanzas(worksheet_finanzas, "capital")
    emergencia = obtener_saldo_finanzas(worksheet_finanzas, "emergencia")
    inversion = obtener_saldo_finanzas(worksheet_finanzas, "inversion")
    
    try:
        worksheet_gastos = conectar_google_sheets()
        registros = worksheet_gastos.get_all_records()
        total_gastos = sum(float(r['Monto']) for r in registros if r.get('Tipo', 'gasto') == 'gasto')
        
        await update.message.reply_text(
            f"📊 *Resumen Financiero*\n\n"
            f"💰 Capital: ${capital:,.2f}\n"
            f"💸 Gastos: ${total_gastos:,.2f}\n"
            f"🟢 Saldo disponible: ${capital - total_gastos:,.2f}\n\n"
            f"🆘 Emergencia: ${emergencia:,.2f}\n"
            f"📈 Inversiones: ${inversion:,.2f}"
        )
    except Exception as e:
        await update.message.reply_text(f"Error al calcular: {str(e)}")

# ---------- TOTAL GASTADO ----------
async def total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra el total gastado y por categoría"""
    try:
        worksheet = conectar_google_sheets()
        registros = worksheet.get_all_records()
        total_gastos = sum(float(r['Monto']) for r in registros if r.get('Tipo', 'gasto') == 'gasto')
        categorias = {}
        for r in registros:
            if r.get('Tipo', 'gasto') != 'gasto':
                continue
            cat = r.get('Categoria', 'Sin categoria')
            categorias[cat] = categorias.get(cat, 0) + float(r['Monto'])
        msg = f"💸 *Total gastado:* ${total_gastos:,.2f}\n\n📂 *Por categoria:*\n"
        for cat, monto in categorias.items():
            msg += f"{cat}: ${monto:,.2f}\n"
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

# ---------- AYUDA ----------
async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

# ==================== MANEJADOR DE FOTOS ====================

async def manejar_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        foto = update.message.photo[-1]
        archivo = await foto.get_file()
        tmp_dir = os.path.join(BASE_DIR, "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        imagen_path = os.path.join(tmp_dir, f"factura_{foto.file_id}.jpg")
        await archivo.download_to_drive(imagen_path)
        mensaje_procesando = await update.message.reply_text("⏳ Procesando factura...")
        fecha, comercio, monto = extraer_datos_factura(imagen_path)
        datos_usuario[user_id] = {
            'fecha': fecha,
            'comercio': comercio,
            'monto': monto,
            'categoria': None,
            'formas_pago': None,
            'imagen_path': imagen_path
        }
        if fecha == "No detectada":
            datos_usuario[user_id]['editando'] = 'fecha'
            await mensaje_procesando.edit_text("📅 No se pudo detectar la fecha. Escribe la fecha (DD/MM/YYYY):")
            return
        print(f"Datos extraidos - Fecha: {fecha}, Comercio: {comercio}, Monto: {monto}")
        mensaje = f"📋 Datos extraidos de la factura:\n📅 Fecha: {fecha}\n🏪 Comercio: {comercio}\n💰 Monto: ${monto}\n\n¿Son correctos?"
        await mensaje_procesando.edit_text(mensaje, reply_markup=crear_teclado_continuar())
    except Exception as e:
        await update.message.reply_text(f"❌ Error al procesar la factura: {str(e)}")
        print(f"Error completo: {e}")

# ==================== MANEJADOR DE BOTONES ====================

async def manejar_botones(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    if user_id not in datos_usuario:
        await query.edit_message_text("No hay datos de factura. Envia una foto nuevamente.")
        return
    datos = datos_usuario[user_id]
    
    if query.data.startswith("cat_"):
        categoria_seleccionada = query.data[4:]
        datos_usuario[user_id]['categoria'] = categoria_seleccionada
        await query.edit_message_text(f"🏷️ Categoria: {categoria_seleccionada}\nSelecciona la forma de pago:", reply_markup=crear_teclado_formas_pago())
        return
    
    if query.data.startswith("fp_"):
        forma_pago_seleccionada = query.data[3:]
        datos_usuario[user_id]['formas_pago'] = forma_pago_seleccionada
        mensaje = f"""📋 Datos finales:
📅 Fecha: {datos['fecha']}
🏪 Comercio: {datos['comercio']}
💰 Monto: ${datos['monto']}
🏷️ Categoria: {datos['categoria']}
💳 Forma de pago: {forma_pago_seleccionada}

¿Son correctos?"""
        await query.edit_message_text(mensaje, reply_markup=crear_teclado_confirmacion())
        return
    
    if query.data == "continuar":
        if datos['categoria'] is None:
            await query.edit_message_text("Selecciona la categoria:", reply_markup=crear_teclado_categorias())
            return
        elif datos['formas_pago'] is None:
            await query.edit_message_text("Selecciona la forma de pago:", reply_markup=crear_teclado_formas_pago())
            return
        # Si ya tiene ambos, mostrar confirmación
        mensaje = f"""📋 Datos finales:
📅 Fecha: {datos['fecha']}
🏪 Comercio: {datos['comercio']}
💰 Monto: ${datos['monto']}
🏷️ Categoria: {datos['categoria']}
💳 Forma de pago: {datos['formas_pago']}

¿Son correctos?"""
        await query.edit_message_text(mensaje, reply_markup=crear_teclado_confirmacion())
        return
    
    if query.data == "confirmar_si":
        try:
            worksheet = conectar_google_sheets()
            # Guardar el gasto
            if guardar_en_sheets(worksheet, datos['fecha'], datos['comercio'], datos['monto'], datos['categoria'], datos['formas_pago'], "gasto"):
                # Restar del capital
                worksheet_finanzas = conectar_google_sheets_finanzas()
                guardar_movimiento_finanzas(worksheet_finanzas, f"Gasto: {datos['comercio']}", "capital", -float(datos['monto']), f"Categoria: {datos['categoria']}")
                await query.edit_message_text(f"✅ Factura guardada exitosamente!\n\n📅 Fecha: {datos['fecha']}\n🏪 Comercio: {datos['comercio']}\n💰 Monto: ${datos['monto']}\n🏷️ Categoria: {datos['categoria']}\n💳 Forma de pago: {datos['formas_pago']}")
            else:
                await query.edit_message_text("❌ Error al guardar en Google Sheets.")
            if datos['imagen_path'] and os.path.exists(datos['imagen_path']):
                os.remove(datos['imagen_path'])
            del datos_usuario[user_id]
        except Exception as e:
            await query.edit_message_text(f"❌ Error: {str(e)}")
    
    elif query.data == "confirmar_no":
        await query.edit_message_text("¿Qué dato deseas cambiar?", reply_markup=crear_teclado_campos())
    
    elif query.data == "editar_fecha":
        datos_usuario[user_id]['editando'] = 'fecha'
        await query.edit_message_text(f"📅 Fecha actual: {datos['fecha']}\nEscribe la nueva fecha (DD/MM/YYYY):")
    elif query.data == "editar_comercio":
        datos_usuario[user_id]['editando'] = 'comercio'
        await query.edit_message_text(f"🏪 Comercio actual: {datos['comercio']}\nEscribe el nuevo comercio:")
    elif query.data == "editar_monto":
        datos_usuario[user_id]['editando'] = 'monto'
        await query.edit_message_text(f"💰 Monto actual: ${datos['monto']}\nEscribe el nuevo monto (ej: 45.50):")
    elif query.data == "editar_categoria":
        await query.edit_message_text("Selecciona la nueva categoria:", reply_markup=crear_teclado_categorias())
    elif query.data == "editar_forma_pago":
        await query.edit_message_text("Selecciona la nueva forma de pago:", reply_markup=crear_teclado_formas_pago())
    elif query.data == "cancelar":
        if datos['imagen_path'] and os.path.exists(datos['imagen_path']):
            os.remove(datos['imagen_path'])
        del datos_usuario[user_id]
        await query.edit_message_text("❌ Operación cancelada.")

# ==================== MANEJADOR DE TEXTO ====================

async def manejar_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    texto = update.message.text.strip()
    if texto.lower() == "hola":
        await hola(update, context)
        return
    if user_id not in datos_usuario or 'editando' not in datos_usuario[user_id]:
        return
    datos = datos_usuario[user_id]
    campo_editando = datos['editando']
    nuevo_valor = update.message.text.strip()
    if campo_editando == 'fecha':
        datos['fecha'] = nuevo_valor
    elif campo_editando == 'comercio':
        datos['comercio'] = nuevo_valor
    elif campo_editando == 'monto':
        nuevo_valor = nuevo_valor.replace('$', '').replace(',', '').strip()
        datos['monto'] = nuevo_valor
    del datos['editando']
    if datos['categoria'] is None:
        await update.message.reply_text("Selecciona la categoria:", reply_markup=crear_teclado_categorias())
        return
    elif datos['formas_pago'] is None:
        await update.message.reply_text("Selecciona la forma de pago:", reply_markup=crear_teclado_formas_pago())
        return
    mensaje = f"""📋 Datos actualizados:
📅 Fecha: {datos['fecha']}
🏪 Comercio: {datos['comercio']}
💰 Monto: ${datos['monto']}
🏷️ Categoria: {datos['categoria']}
💳 Forma de pago: {datos['formas_pago']}

¿Son correctos?"""
    await update.message.reply_text(mensaje, reply_markup=crear_teclado_confirmacion())

# ==================== MAIN ====================

def main():
    print("🤖 Iniciando bot de facturas...")
    if not TELEGRAM_TOKEN:
        print("❌ ERROR: Debes configurar tu TELEGRAM_TOKEN")
        return
    if not GOOGLE_SHEET_ID:
        print("❌ ERROR: Debes configurar tu GOOGLE_SHEET_ID")
        return
    if not os.path.exists(CREDENTIALS_FILE):
        print("❌ ERROR: No se encuentra el archivo credenciales.json")
        return
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Comandos principales
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hola", hola))
    app.add_handler(CommandHandler("gasto", gasto))
    app.add_handler(CommandHandler("capital_inicial", capital_inicial))
    app.add_handler(CommandHandler("ingreso", ingreso))
    app.add_handler(CommandHandler("retiro", retiro))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("total", total))
    app.add_handler(CommandHandler("ayuda", ayuda))
    
    # Emergencia
    app.add_handler(CommandHandler("emergencia", emergencia))
    app.add_handler(CommandHandler("emergencia_ingresar", emergencia_ingresar))
    app.add_handler(CommandHandler("emergencia_retirar", emergencia_retirar))
    
    # Inversiones
    app.add_handler(CommandHandler("inversiones", inversiones))
    app.add_handler(CommandHandler("inversiones_ingresar", inversiones_ingresar))
    app.add_handler(CommandHandler("inversiones_retirar", inversiones_retirar))
    
    # Manejadores
    app.add_handler(MessageHandler(filters.PHOTO, manejar_foto))
    app.add_handler(CallbackQueryHandler(manejar_botones))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_texto))
    
    print("✅ Bot iniciado correctamente")
    print("📸 Esperando fotos de facturas...")
    print("Presiona Ctrl+C para detener el bot\n")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
