import os
import re
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CallbackQueryHandler, filters, ContextTypes, CommandHandler
import pytesseract
from PIL import Image
import gspread
from oauth2client.service_account import ServiceAccountCredentials

TELEGRAM_TOKEN = "8224897386:AAGyv-f_GqAoyfQGy9Lu-sA3NCSSA8K2LmM"
GOOGLE_SHEET_ID = "1HK27kQ5TvAH4p0Zt6OgNkiUlR6V0JsVxcljw2arV2nI"
SHEET_NAME = "Registro"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credenciales.json")
TESSERACT_PATH = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

if TESSERACT_PATH and TESSERACT_PATH.strip():
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

class ColumnasSheet:
    TIMESTAMP = 0
    FECHA = 1
    COMERCIO = 2
    CATEGORIA = 3
    MONTO = 4
    FORMAS_PAGO = 5

CATEGORIAS_LIST = [
    "Supermercado",
    "Salud",
    "Gasolina",
    "Comidas fuera",
    "Entretenimiento",
    "Hogar",
    "Transporte"
]

FORMAS_PAGO_LIST = [
    "Efectivo",
    "Tarjeta debito",
    "Tarjeta credito",
    "Yappy",
    "Otro"
]

datos_usuario = {}
capital_usuario = {}

def conectar_google_sheets():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(GOOGLE_SHEET_ID)
    worksheet = sheet.worksheet(SHEET_NAME)
    return worksheet

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

def guardar_en_sheets(worksheet, fecha, comercio, monto, categoria, formas_pago):
    try:
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        fila = [''] * 6
        fila[ColumnasSheet.FECHA] = fecha
        fila[ColumnasSheet.COMERCIO] = comercio
        fila[ColumnasSheet.CATEGORIA] = categoria
        fila[ColumnasSheet.FORMAS_PAGO] = formas_pago
        fila[ColumnasSheet.MONTO] = float(monto)
        fila[ColumnasSheet.TIMESTAMP] = timestamp
        worksheet.append_row(fila, value_input_option='USER_ENTERED')
        return True
    except Exception as e:
        print(f"Error al guardar en Google Sheets: {e}")
        return False

def crear_teclado_confirmacion():
    keyboard = [[InlineKeyboardButton("Si, guardar", callback_data="confirmar_si"), InlineKeyboardButton("No, editar", callback_data="confirmar_no")]]
    return InlineKeyboardMarkup(keyboard)

def crear_teclado_continuar():
    keyboard = [[InlineKeyboardButton("Si, Continuar", callback_data="continuar"), InlineKeyboardButton("No, editar", callback_data="confirmar_no")]]
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
        [InlineKeyboardButton("Fecha", callback_data="editar_fecha")],
        [InlineKeyboardButton("Comercio", callback_data="editar_comercio")],
        [InlineKeyboardButton("Monto", callback_data="editar_monto")],
        [InlineKeyboardButton("Categoria", callback_data="editar_categoria")],
        [InlineKeyboardButton("Forma de pago", callback_data="editar_forma_pago")],
        [InlineKeyboardButton("Cancelar", callback_data="cancelar")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Bienvenido a tu bot financiero!\n\n"
        "Comandos disponibles:\n"
        "/start - Mostrar este mensaje\n"
        "/hola - Saludo\n"
        "/capital - Guardar tu saldo inicial\n"
        "/gasto - Registrar un gasto manual\n"
        "/balance - Ver tu saldo actual\n"
        "/total - Ver total gastado\n"
        "/ayuda - Mostrar todos los comandos\n\n"
        "Tambien puedes enviar una foto de un ticket y lo procesare."
    )

async def hola(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hola! Como estas? Envia una foto de tu factura o usa /gasto para registrar manualmente.")

async def capital(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        monto = float(context.args[0].replace('$', '').replace(',', ''))
        capital_usuario[user_id] = monto
        await update.message.reply_text(f"Capital inicial guardado: ${monto:,.2f}")
    except:
        await update.message.reply_text("Uso correcto: /capital 25000")

async def gasto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        texto = ' '.join(context.args)
        monto_match = re.search(r'(\d{1,}[.,]\d{0,2})', texto)
        monto = float(monto_match.group(1).replace(',', ''))
        concepto = texto.replace(monto_match.group(1), '').strip()
        if not concepto:
            concepto = "Gasto manual"
        datos_usuario[user_id] = {
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
        await update.message.reply_text("Uso correcto: /gasto 350 Comida")

async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in capital_usuario:
        await update.message.reply_text("No has registrado tu capital. Usa /capital 25000")
        return
    try:
        worksheet = conectar_google_sheets()
        registros = worksheet.get_all_records()
        total_gastos = sum(float(r['Monto']) for r in registros)
        saldo = capital_usuario[user_id] - total_gastos
        await update.message.reply_text(
            f"Resumen financiero:\n"
            f"Capital inicial: ${capital_usuario[user_id]:,.2f}\n"
            f"Total gastado: ${total_gastos:,.2f}\n"
            f"Saldo actual: ${saldo:,.2f}"
        )
    except Exception as e:
        await update.message.reply_text(f"Error al calcular: {str(e)}")

async def total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        worksheet = conectar_google_sheets()
        registros = worksheet.get_all_records()
        total_gastos = sum(float(r['Monto']) for r in registros)
        categorias = {}
        for r in registros:
            cat = r.get('Categoria', 'Sin categoria')
            categorias[cat] = categorias.get(cat, 0) + float(r['Monto'])
        msg = f"Total gastado: ${total_gastos:,.2f}\n\nPor categoria:\n"
        for cat, monto in categorias.items():
            msg += f"{cat}: ${monto:,.2f}\n"
        await update.message.reply_text(msg)
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)

async def manejar_foto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        foto = update.message.photo[-1]
        archivo = await foto.get_file()
        tmp_dir = os.path.join(BASE_DIR, "tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        imagen_path = os.path.join(tmp_dir, f"factura_{foto.file_id}.jpg")
        await archivo.download_to_drive(imagen_path)
        mensaje_procesando = await update.message.reply_text("Procesando factura...")
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
            await mensaje_procesando.edit_text("No se pudo detectar la fecha. Escribe la fecha (DD/MM/YYYY):")
            return
        print(f"Datos extraidos - Fecha: {fecha}, Comercio: {comercio}, Monto: {monto}")
        mensaje = f"Datos extraidos de la factura:\nFecha: {fecha}\nComercio: {comercio}\nMonto: ${monto}\n\nSon correctos?"
        await mensaje_procesando.edit_text(mensaje, reply_markup=crear_teclado_continuar())
    except Exception as e:
        await update.message.reply_text(f"Error al procesar la factura: {str(e)}")
        print(f"Error completo: {e}")

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
        await query.edit_message_text(f"Categoria: {categoria_seleccionada}\nSelecciona la forma de pago:", reply_markup=crear_teclado_formas_pago())
        return
    if query.data.startswith("fp_"):
        forma_pago_seleccionada = query.data[3:]
        datos_usuario[user_id]['formas_pago'] = forma_pago_seleccionada
        mensaje = f"""Datos finales:
Fecha: {datos['fecha']}
Comercio: {datos['comercio']}
Monto: ${datos['monto']}
Categoria: {datos['categoria']}
Forma de pago: {forma_pago_seleccionada}

Son correctos?"""
        await query.edit_message_text(mensaje, reply_markup=crear_teclado_confirmacion())
        return
    if query.data == "continuar":
        if datos['categoria'] is None:
            await query.edit_message_text("Selecciona la categoria:", reply_markup=crear_teclado_categorias())
            return
        elif datos['formas_pago'] is None:
            await query.edit_message_text("Selecciona la forma de pago:", reply_markup=crear_teclado_formas_pago())
            return
    if query.data == "confirmar_si":
        try:
            worksheet = conectar_google_sheets()
            if guardar_en_sheets(worksheet, datos['fecha'], datos['comercio'], datos['monto'], datos['categoria'], datos['formas_pago']):
                await query.edit_message_text(f"Factura guardada exitosamente!\n\nFecha: {datos['fecha']}\nComercio: {datos['comercio']}\nMonto: ${datos['monto']}\nCategoria: {datos['categoria']}\nForma de pago: {datos['formas_pago']}")
            else:
                await query.edit_message_text("Error al guardar en Google Sheets.")
            if datos['imagen_path'] and os.path.exists(datos['imagen_path']):
                os.remove(datos['imagen_path'])
            del datos_usuario[user_id]
        except Exception as e:
            await query.edit_message_text(f"Error: {str(e)}")
    elif query.data == "confirmar_no":
        await query.edit_message_text("Que dato deseas cambiar?", reply_markup=crear_teclado_campos())
    elif query.data == "editar_fecha":
        datos_usuario[user_id]['editando'] = 'fecha'
        await query.edit_message_text(f"Fecha actual: {datos['fecha']}\nEscribe la nueva fecha (DD/MM/YYYY):")
    elif query.data == "editar_comercio":
        datos_usuario[user_id]['editando'] = 'comercio'
        await query.edit_message_text(f"Comercio actual: {datos['comercio']}\nEscribe el nuevo comercio:")
    elif query.data == "editar_monto":
        datos_usuario[user_id]['editando'] = 'monto'
        await query.edit_message_text(f"Monto actual: ${datos['monto']}\nEscribe el nuevo monto (ej: 45.50):")
    elif query.data == "editar_categoria":
        await query.edit_message_text("Selecciona la nueva categoria:", reply_markup=crear_teclado_categorias())
    elif query.data == "editar_forma_pago":
        await query.edit_message_text("Selecciona la nueva forma de pago:", reply_markup=crear_teclado_formas_pago())
    elif query.data == "cancelar":
        if datos['imagen_path'] and os.path.exists(datos['imagen_path']):
            os.remove(datos['imagen_path'])
        del datos_usuario[user_id]
        await query.edit_message_text("Operacion cancelada.")

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
    mensaje = f"""Datos actualizados:
Fecha: {datos['fecha']}
Comercio: {datos['comercio']}
Monto: ${datos['monto']}
Categoria: {datos['categoria']}
Forma de pago: {datos['formas_pago']}

Son correctos?"""
    await update.message.reply_text(mensaje, reply_markup=crear_teclado_confirmacion())

def main():
    print("Iniciando bot de facturas...")
    if not TELEGRAM_TOKEN:
        print("ERROR: Debes configurar tu TELEGRAM_TOKEN")
        return
    if not GOOGLE_SHEET_ID:
        print("ERROR: Debes configurar tu GOOGLE_SHEET_ID")
        return
    if not os.path.exists(CREDENTIALS_FILE):
        print("ERROR: No se encuentra el archivo credenciales.json")
        return
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("hola", hola))
    app.add_handler(CommandHandler("capital", capital))
    app.add_handler(CommandHandler("gasto", gasto))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("total", total))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(MessageHandler(filters.PHOTO, manejar_foto))
    app.add_handler(CallbackQueryHandler(manejar_botones))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, manejar_texto))
    print("Bot iniciado correctamente")
    print("Esperando fotos de facturas...")
    print("Presiona Ctrl+C para detener el bot\n")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
