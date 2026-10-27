# Деплой на Render

1. Залей папку `server/` в GitHub-репозиторий.
2. Render → New → Web Service. Build: `pip install -r requirements.txt`
   Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
3. Environment:
   - `BOT_TOKEN` не обязателен: токен уже вшит в `main.py` (если задать, переменная главнее)
   - `DATABASE_URL`  (строка из Neon) — единственное, что обязательно задать
   - `TG_API_BASE` = https://bot.catup.lol
   - `WEBHOOK_SECRET` и `PUBLIC_URL` не нужны: секрет считается сам, адрес Render подставляет сам
   - `ADMIN_IDS` = 1780243247,1780243478,1780243322
4. В `static/index.html` замени `YOUR_BOT_USERNAME` на юзернейм бота (без @).
5. В BotFather → Menu Button / Web App укажи `https://<имя>.onrender.com`.
6. Автовывод: `AUTO_PAYOUT=1`. Выплата идёт через `withdrawStarBalance` (минимум 10 ⭐, комиссия Catugram 10%).
   Звёзды берутся с баланса бота, он пополняется платежами игроков; если там пусто, заявки ждут (`BALANCE_TOO_LOW`).
