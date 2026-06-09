# Procfile — Railway / Heroku process definitions
#
# Railway Project setup (3 services):
#
#   Service 1 — telegram-bot
#     Start command : python main_bot.py
#     Type          : Web (or Worker)
#
#   Service 2 — cron-runner
#     Start command : python main_runner.py --run-due-monitors --run-queued
#     Cron schedule : 0 */6 * * *   (every 6 hours)
#     NOTE: cron only runs monitors with schedule_mode=scheduled
#           Manual monitors are NEVER touched by cron
#
#   Service 3 — PostgreSQL
#     Add via Railway Dashboard → New → Database → PostgreSQL
#     Reference in both Python services as:
#       DATABASE_URL=${{Postgres.DATABASE_URL}}
#
# For local development:
#   foreman start telegram-bot

telegram-bot: python main_bot.py
cron-runner: python main_runner.py --run-due-monitors --run-queued
