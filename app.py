from flask import Flask, render_template
from flask_socketio import SocketIO, send
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    filters,
    ContextTypes
)

import google.generativeai as genai
import threading
import asyncio
import requests
import os
from dotenv import load_dotenv

# ==================================================
# CONFIGURACION
# ==================================================

load_dotenv()

tokenTelegram = os.getenv("TELEGRAM_TOKEN")
chatID = os.getenv("TELEGRAM_CHAT_ID")
geminiApiKey = os.getenv("GEMINI_API_KEY")


# ==================================================
# GEMINI
# ==================================================

genai.configure(api_key=geminiApiKey)

modeloIA = genai.GenerativeModel("gemini-2.5-flash")


def cargarContexto():
    try:
        with open("configuracion.txt", "r", encoding="utf-8") as archivo:
            return archivo.read()
    except Exception:
        return ""


def consultarGemini(texto):
    contexto = cargarContexto()

    prompt = f"""
{contexto}

Usuario:
{texto}

Respuesta:
"""

    try:
        respuesta = modeloIA.generate_content(prompt)
        return respuesta.text
    except Exception as e:
        print("Error Gemini:", e)
        return "Error al consultar la IA"


# ==================================================
# PALABRAS CLAVE / ALERTAS
# ==================================================

palabrasClave = {
    "ayuda": "/ayuda",
    "emergencia": "/emergencia",
    "urgente": "/urgente",
    "reserva": "/reserva",
    "comprar": "/comprar",
    "producto": "/producto",
    "productos": "/producto"
}


def detectarComandos(texto):
    textoMinuscula = texto.lower()

    for palabra, comando in palabrasClave.items():
        if palabra in textoMinuscula:
            mensaje = (
                "🚨 ALERTA AUTOMATICA\n\n"
                f"Comando:\n{comando}\n\n"
                f"Mensaje:\n{texto}\n\n"
                "Estado:\nPendiente de revisión."
            )

            socket.emit("emergencia", mensaje)

            threading.Thread(
                target=enviarTelegram,
                args=(mensaje,),
                daemon=True
            ).start()

            print("Alerta enviada")
            break


# ==================================================
# FLASK / SOCKETIO
# ==================================================

app = Flask(__name__)

socket = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="threading"
)


# ==================================================
# BOT TELEGRAM
# ==================================================

botTelegram = ApplicationBuilder().token(tokenTelegram).build()


# ==================================================
# PAGINA PRINCIPAL
# ==================================================

@app.route("/")
def index():
    return render_template("index.html")


# ==================================================
# MENSAJES DESDE WEB
# ==================================================

@socket.on("message")
def recibirMensaje(mensaje):
    print("Mensaje WEB:", mensaje)

    send(mensaje, broadcast=True)

    detectarComandos(mensaje)

    # Mensajes internos de join/leave no se envian a la IA
    if mensaje.startswith("__join__") or mensaje.startswith("__leave__"):
        return

    pregunta = mensaje
    if ":" in mensaje:
        pregunta = mensaje.split(":", 1)[1].strip()

    threading.Thread(
        target=responderConIA,
        args=(pregunta,),
        daemon=True
    ).start()


def responderConIA(pregunta):
    respuesta = consultarGemini(pregunta)
    send(f"🤖 IA: {respuesta}", broadcast=True)


# ==================================================
# ENVIAR A TELEGRAM
# ==================================================

def enviarTelegram(mensaje):
    url = f"https://api.telegram.org/bot{tokenTelegram}/sendMessage"

    data = {
        "chat_id": chatID,
        "text": mensaje
    }

    try:
        requests.post(url, data=data, timeout=10)
    except Exception as e:
        print("Error Telegram:", e)


# ==================================================
# RECIBIR DESDE TELEGRAM
# ==================================================

async def recibirTelegram(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    try:
        usuario = update.message.from_user.first_name
        mensaje = update.message.text
        texto = f"{usuario}: {mensaje}"

        print("Telegram:", texto)

        socket.emit("telegram_message", texto)

        detectarComandos(texto)

        respuestaIA = consultarGemini(mensaje)

        await update.message.reply_text(respuestaIA)

        socket.emit("message", f"🤖 IA: {respuestaIA}")

    except Exception as e:
        print("Error al procesar mensaje de Telegram:", e)


# ==================================================
# INICIAR BOT
# ==================================================

def iniciarBot():
    loop = None
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

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
        except Exception:
            pass


# ==================================================
# MAIN
# ==================================================

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