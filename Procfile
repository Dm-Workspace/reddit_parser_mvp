# Procfile — Railway / Heroku process definitions
#
# Railway Project setup (recommended: 3 services):
#
#   Service 1 — api (web)
#     Start command : python main_api.py
#     Type          : Web
#     Exposes       : FastAPI backend + Telegram Mini App static files
#
#   Service 2 — telegram-bot
#     Start command : python main_bot.py
#     Type          : Web (or Worker)
#
#   Service 3 — cron-runner
#     Start command : python main_runner.py --run-due-monitors --run-queued
#     Cron schedule : 0 */6 * * *   (every 6 hours)
#     NOTE: cron only runs monitors with schedule_mode=scheduled
#           Manual monitors are NEVER touched by cron
#
#   Service 4 — PostgreSQL
#     Add via Railway Dashboard → New → Database → PostgreSQL
#     Reference in all Python services as:
#       DATABASE_URL=${{Postgres.DATABASE_URL}}
#
# For local development:
#   python main_api.py   # FastAPI + Mini App on :8000
#   python main_bot.py   # Telegram bot

web: python main_api.py
telegram-bot: python main_bot.py
cron-runner: python main_runner.py --run-due-monitors --run-queued
