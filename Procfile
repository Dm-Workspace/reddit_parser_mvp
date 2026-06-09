# Procfile — Railway / Heroku process definitions
#
# Railway Services setup:
#   Service 1 (telegram-bot):  web: python main_bot.py
#   Service 2 (cron-runner):   cron: python main_runner.py --run-due-monitors --run-queued
#
# For local development:
#   foreman start

telegram-bot: python main_bot.py
cron-runner: python main_runner.py --run-due-monitors --run-queued
