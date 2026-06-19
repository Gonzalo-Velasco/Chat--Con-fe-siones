# Chat en Tiempo Real con Telegram

Chat en tiempo real que integra Flask-SocketIO con Telegram Bot.

## Variables de entorno requeridas

| Variable | Descripción |
|----------|-------------|
| `TELEGRAM_TOKEN` | Token del bot (lo da @BotFather) |
| `TELEGRAM_CHAT_ID` | ID del chat de Telegram |

## Deploy en Render

1. Sube este proyecto a GitHub
2. Ve a [render.com](https://render.com) → New + → Web Service
3. Conecta tu repo
4. Environment: **Docker**
5. Agrega las variables de entorno
6. Create Web Service

## Correr localmente

```bash
cp .env.example .env
# Edita .env con tus credenciales

pip install -r requirements.txt
python app.py
```

Abre http://localhost:8080
