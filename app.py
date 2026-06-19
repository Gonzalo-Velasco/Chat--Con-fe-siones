from flask import Flask, render_template
from flask_socketio import SocketIO, send
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes
)

import threading
import requests
import os
from dotenv import load_dotenv
import google.generativeai as genai

# Cargar variables de entorno
load_dotenv()

# CONFIGURACION TELEGRAM
tokenTelegram = os.getenv("TELEGRAM_TOKEN")
chatID = os.getenv("TELEGRAM_CHAT_ID")

# CONFIGURACION GEMINI
geminiApiKey = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=geminiApiKey)
modeloGemini = genai.GenerativeModel("gemini-2.5-flash")

# CREAR APP
app = Flask(__name__)

# CONFIGURAR SOCKETIO
socket = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading'
)

# CREAR BOT TELEGRAM
botTelegram = ApplicationBuilder().token(tokenTelegram).build()

# CONTADOR DE CONFESIONES (solo para /estadisticas)
contadorConfesiones = 0


# ====================================================
# GEMINI (IA)
# ====================================================
def cargarContextoIA():
    try:
        with open("configuracion.txt", "r", encoding="utf-8") as archivo:
            return archivo.read()
    except Exception:
        return ""


def consultarGemini(texto):
    contexto = cargarContextoIA()

    prompt = f"""
{contexto}

Usuario:
{texto}

Respuesta:
"""

    try:
        respuesta = modeloGemini.generate_content(prompt)
        return respuesta.text
    except Exception as e:
        print("Error Gemini:", e)
        return "Error al consultar la IA"


# ====================================================
# PALABRAS CLAVE DE ALERTA
# ====================================================
palabrasClave = {
    "ayuda": "/ayuda",
    "emergencia": "/emergencia",
    "urgente": "/urgente",
    "reserva": "/reserva",
    "comprar": "/comprar",
    "producto": "/producto",
    "productos": "/producto"
}


def detectarPalabrasClave(texto):
    textoMinuscula = texto.lower()

    for palabra, comando in palabrasClave.items():
        if palabra in textoMinuscula:
            mensaje = (
                f"🚨 ALERTA AUTOMATICA\n\n"
                f"Comando:\n{comando}\n\n"
                f"Mensaje:\n{texto}\n\n"
                f"Estado:\nPendiente de revisión."
            )

            with app.app_context():
                socket.emit("emergencia", mensaje)

            threading.Thread(
                target=enviarTelegram,
                args=(mensaje,),
                daemon=True
            ).start()

            print("Alerta enviada")
            break


# ====================================================
# TEXTOS DE LOS COMANDOS (compartidos entre Telegram y Web)
# ====================================================
def obtenerTextoComando(comando):
    comando = comando.lower().strip()

    if comando == "/inicio":
        return (
            "Bienvenido al Chat de Confesiones\n\n"
            "Aquí puedes leer y enviar confesiones en tiempo real.\n"
            "Usa /ayuda para ver los comandos disponibles."
        )

    if comando == "/ayuda":
        return (
            "Comandos disponibles:\n\n"
            "/inicio - Iniciar el bot\n"
            "/ayuda - Ver esta ayuda\n"
            "/reglas - Reglas del chat\n"
            "/estadisticas - Ver estadísticas del chat"
        )

    if comando == "/reglas":
        return (
            "Reglas del Chat de Confesiones:\n\n"
            "1. Respeta a los demás usuarios\n"
            "2. No compartas datos personales tuyos ni de terceros\n"
            "3. Prohibido el spam o publicidad\n"
            "4. No se permite contenido ilegal o de odio\n"
            "5. El equipo puede moderar mensajes inapropiados"
        )

    if comando == "/estadisticas":
        return f"Confesiones enviadas desde la web: {contadorConfesiones}"

    return None


# PAGINA PRINCIPAL
@app.route("/")
def index():
    return render_template('index.html')

# MENSAJES DESDE WEB
@socket.on("message")
def recibirMensaje(mensaje):
    global contadorConfesiones

    # Mensajes de sistema (entrar/salir) -> solo se reenvían a la web
    if mensaje.startswith("__join__") or mensaje.startswith("__leave__"):
        send(mensaje, broadcast=True)
        return

    # Separar "Usuario: texto"
    idx = mensaje.find(": ")
    texto = mensaje[idx + 2:] if idx != -1 else mensaje

    # Si el texto escrito es un comando, respondemos solo en el chat
    if texto.strip().startswith("/"):
        comando = texto.strip().split()[0]
        respuesta = obtenerTextoComando(comando)
        if respuesta:
            send(f"Bot: {respuesta}", broadcast=True)
        else:
            send(
                "Bot: Comando no reconocido. Usa /ayuda para ver los comandos disponibles.",
                broadcast=True
            )
        return

    contadorConfesiones += 1
    print("Mensaje WEB:", mensaje)
    send(mensaje, broadcast=True)

    detectarPalabrasClave(texto)

    threading.Thread(
        target=enviarTelegram,
        args=(mensaje,)
    ).start()

    respuestaIA = consultarGemini(texto)
    send(f"🤖 IA: {respuestaIA}", broadcast=True)

# ENVIAR A TELEGRAM
def enviarTelegram(mensaje):
    url = (
        f"https://api.telegram.org/bot"
        f"{tokenTelegram}/sendMessage"
    )
    data = {
        "chat_id": chatID,
        "text": mensaje
    }
    try:
        requests.post(url, data=data)
    except Exception as e:
        print("Error Telegram:", e)

# RECIBIR DESDE TELEGRAM
async def recibirTelegram(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        usuario = update.message.from_user.first_name
        mensaje = update.message.text
        texto = f"{usuario}: {mensaje}"
        print("Telegram:", texto)

        with app.app_context():
            socket.send(texto, broadcast=True)

        detectarPalabrasClave(texto)

        respuestaIA = consultarGemini(mensaje)
        await update.message.reply_text(respuestaIA)

        with app.app_context():
            socket.emit("message", f"🤖 IA: {respuestaIA}")

    except Exception as e:
        print("Error en recibirTelegram:", e)


# COMANDOS DESDE TELEGRAM (cualquier usuario del chat puede usarlos)
async def manejarComandoTelegram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    comando = "/" + update.message.text.split()[0].lstrip("/").split("@")[0]
    respuesta = obtenerTextoComando(comando)
    if respuesta:
        await update.message.reply_text(respuesta)

# INICIAR BOT
def iniciarBot():
    import asyncio
    loop = None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        botTelegram.add_handler(CommandHandler("inicio", manejarComandoTelegram))
        botTelegram.add_handler(CommandHandler("ayuda", manejarComandoTelegram))
        botTelegram.add_handler(CommandHandler("reglas", manejarComandoTelegram))
        botTelegram.add_handler(CommandHandler("estadisticas", manejarComandoTelegram))

        botTelegram.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                recibirTelegram
            )
        )

        print("BOT TELEGRAM ACTIVO")

        loop.run_until_complete(botTelegram.initialize())
        loop.run_until_complete(botTelegram.start())
        loop.run_until_complete(botTelegram.updater.start_polling())
        loop.run_forever()

    except Exception as e:
        print(f"Error en bot de Telegram: {e}")
    finally:
        try:
            if loop and not loop.is_closed():
                loop.run_until_complete(botTelegram.updater.stop())
                loop.run_until_complete(botTelegram.stop())
                loop.run_until_complete(botTelegram.shutdown())
                loop.close()
        except:
            pass

# MAIN
if __name__ == "__main__":
    hiloBot = threading.Thread(target=iniciarBot, daemon=True)
    hiloBot.start()

    print("Servidor iniciado")

    port = int(os.getenv("PORT", 8080))
    host = os.getenv("HOST", "0.0.0.0")

    socket.run(
        app,
        host=host,
        port=port,
        allow_unsafe_werkzeug=True
    )