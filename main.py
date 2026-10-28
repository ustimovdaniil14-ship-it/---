"""
Бэкенд игрового Mini App: FastAPI + Neon (Postgres) + Telegram-форк.
Всё секретное — только из переменных окружения (Render -> Environment):
  BOT_TOKEN     токен бота (перевыпусти его в BotFather, он светился в чате)
  DATABASE_URL  строка Neon (postgresql://...?sslmode=require)
  TG_API_BASE   Catugram Bot API (по умолчанию https://bot.catup.lol)
  WEBHOOK_SECRET  любая длинная случайная строка
  PUBLIC_URL    https://<твой-сервис>.onrender.com
  ADMIN_IDS     1780243247,1780243478,1780243322
  AUTO_PAYOUT   "1" чтобы выплачивать выводы автоматически (см. payout())
"""
import asyncio, hashlib, hmac, json, os, secrets, time
from datetime import datetime, timezone
from urllib.parse import parse_qsl

import asyncpg, httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

# Токен: переменная окружения BOT_TOKEN главнее, иначе берётся вшитый (по просьбе владельца).
# В присланных сообщениях токен записан двумя чуть разными способами (I/l и Q/q), поэтому при старте
# выбирается тот вариант, который отвечает на getMe.
_TOKEN_CANDIDATES = [t for t in [
    os.environ.get("BOT_TOKEN"),
    "1780243863:mYjbDebtYXtn2wkquvpsZXlvwZjbSRqDMyM",
    "1780243863:mYjbDebtYXtn2wkquvpsZXIvwZjbSRQDMyM",
] if t]
BOT_TOKEN = _TOKEN_CANDIDATES[0]
DATABASE_URL = os.environ["DATABASE_URL"]
def _norm_base(v: str) -> str:
    v = "".join((v or "").split())                      # убираем пробелы, переводы строк, невидимые разделители
    if not v: v = "https://bot.catup.lol"
    if not v.startswith("http"): v = "https://" + v
    return v.rstrip("/")
TG_API_BASE = _norm_base(os.environ.get("TG_API_BASE", ""))
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
# Render сам кладёт адрес сервиса в RENDER_EXTERNAL_URL, отдельно задавать не нужно
PUBLIC_URL = (os.environ.get("PUBLIC_URL") or os.environ.get("RENDER_EXTERNAL_URL") or "").rstrip("/")
import re
# принимает любой формат: "1,2,3", "{1, 2, 3}", "[1 2 3]"; если переменная пустая или в ней нет цифр — берётся список по умолчанию
ADMINS = {int(x) for x in re.findall(r"\d+", os.environ.get("ADMIN_IDS", ""))} or {1780243247, 1780243478, 1780243322}
AUTO_PAYOUT = os.environ.get("AUTO_PAYOUT", "1") == "1"   # автовывод включён по умолчанию

RTP, MAX_BET, DEP_MAX, WD_LIMIT, WD_MIN = 0.85, 5000, 100000, 50000, 10  # мин. вывод 10 ⭐ (правило Catugram)
INIT_BONUS = 0  # стартовый баланс новым игрокам

app = FastAPI()

from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)   # страница 500 КБ -> ~120 КБ по сети

from starlette.exceptions import HTTPException as StarletteHTTPException
import traceback

@app.exception_handler(StarletteHTTPException)
async def http_err(request, exc):          # фронт читает поле "error", а не "detail"
    return JSONResponse({"error": exc.detail, "detail": exc.detail}, status_code=exc.status_code)

@app.exception_handler(Exception)
async def any_err(request, exc):           # причина видна и в игре, и в логах Render
    traceback.print_exc()
    msg = f"{type(exc).__name__}: {str(exc)[:160]}"
    return JSONResponse({"error": msg, "detail": msg}, status_code=500)
pool: asyncpg.Pool
http = httpx.AsyncClient(timeout=20, transport=httpx.AsyncHTTPTransport(retries=3))   # повтор при сбое соединения/DNS

SCHEMA = """
create table if not exists users(
  id bigint primary key, name text, username text,
  balance bigint not null default 0 check (balance >= 0),
  deposited bigint not null default 0, withdrawn bigint not null default 0,
  wagered bigint not null default 0, won_total bigint not null default 0,
  played int not null default 0, won int not null default 0, best bigint not null default 0,
  ban_until bigint not null default 0, freeze_until bigint not null default 0,
  last_seen bigint not null default 0, created_at timestamptz default now());
create table if not exists ops(
  id bigserial primary key, user_id bigint not null references users(id),
  kind text not null, amount bigint not null default 0, ref text unique,
  meta jsonb not null default '{}', ts bigint not null);
create index if not exists ops_user on ops(user_id, id desc);
create table if not exists withdrawals(
  id bigserial primary key, user_id bigint not null references users(id),
  amount bigint not null, status text not null default 'pending',
  created_at bigint not null, processed_at bigint);
create table if not exists promos(code text primary key, stars bigint not null, max_uses int not null, used int not null default 0);
create table if not exists promo_uses(code text, user_id bigint, primary key(code, user_id));
"""

@app.on_event("startup")
async def startup():
    global pool, BOT_TOKEN, WEBHOOK_SECRET
    for t in _TOKEN_CANDIDATES:                       # выбрать рабочий токен
        try:
            r = await api_http("GET", f"/bot{t}/getMe")
            if r.json().get("ok"):
                BOT_TOKEN = t; print("bot ok:", r.json()["result"].get("username")); break
        except Exception as e:
            print("getMe failed:", e)
    else:
        print("ВНИМАНИЕ: ни один токен не прошёл getMe")
    if not WEBHOOK_SECRET:                            # стабильный секрет вебхука, считается из токена
        WEBHOOK_SECRET = hashlib.sha256(("wh:" + BOT_TOKEN).encode()).hexdigest()[:40]
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=8, max_inactive_connection_lifetime=120)   # Neon засыпает: не держим протухшие соединения
    async with pool.acquire() as c:
        await c.execute(SCHEMA)
    if PUBLIC_URL:
        asyncio.create_task(ensure_webhook())      # в фоне: сервер стартует даже если вебхук пока не встал
    async with pool.acquire() as c:   # после рестарта вернуть "зависшие" выплаты в очередь (request_id защищает от двойной выплаты)
        await c.execute("update withdrawals set status='pending' where status='processing'")
    asyncio.create_task(payout_worker())
    asyncio.create_task(deposit_worker())
    asyncio.create_task(keepalive())

# ---------------------------------------------------------------- Telegram
async def ensure_webhook():
    """Ставит вебхук и кнопку меню; при ошибке (напр. CONFLICT: другой бот на этом токене опрашивает getUpdates) повторяет."""
    while True:
        try:
            try: await tg("deleteWebhook")
            except Exception: pass
            await tg("setWebhook", url=f"{PUBLIC_URL}/tg/{WEBHOOK_SECRET}")
            print("webhook ok:", PUBLIC_URL)
            try:
                await tg("setChatMenuButton", menu_button={"type": "web_app", "text": "Играть", "web_app": {"url": PUBLIC_URL}})
            except Exception as e:
                print("setChatMenuButton:", e, "(задай Web App вручную в BotFather)")
            return
        except Exception as e:
            print("setWebhook failed:", e, "- повтор через 20 с. Если CONFLICT: останови старый бот, который опрашивает getUpdates с этим токеном")
            await asyncio.sleep(20)

import urllib.parse as _up
doh_http = httpx.AsyncClient(timeout=6)
_dns_cache: dict[str, tuple[float, str]] = {}

async def doh_resolve(host: str) -> str | None:
    """Если DNS на Render не находит адрес Catugram, спрашиваем его через DNS-over-HTTPS (Cloudflare, затем Google)."""
    hit = _dns_cache.get(host)
    if hit and time.time() - hit[0] < 300:
        return hit[1]
    for url in ("https://1.1.1.1/dns-query", "https://8.8.8.8/resolve"):
        try:
            r = await doh_http.get(url, params={"name": host, "type": "A"}, headers={"accept": "application/dns-json"})
            for a in r.json().get("Answer", []):
                if a.get("type") == 1:
                    _dns_cache[host] = (time.time(), a["data"]); return a["data"]
        except Exception as e:
            print("doh", url, type(e).__name__, e)
    return None

async def api_http(verb: str, path: str, **kw):
    """HTTP-запрос к Catugram: обычный, а при сбое DNS/соединения повтор по IP из DNS-over-HTTPS (с верным именем сервера для TLS)."""
    try:
        return await http.request(verb, f"{TG_API_BASE}{path}", **kw)
    except httpx.TransportError as first:
        host = _up.urlparse(TG_API_BASE).hostname or ""
        ip = await doh_resolve(host)
        if not ip:
            raise first
        print(f"api_http: {type(first).__name__}, повтор по IP {ip}")
        headers = {**(kw.pop("headers", None) or {}), "Host": host}
        return await http.request(verb, f"https://{ip}{path}", headers=headers, extensions={"sni_hostname": host}, **kw)

async def tg(method: str, **params):
    last = None
    for attempt in range(4):                       # временный сбой DNS/сети: повторяем с паузой
        try:
            r = await api_http("POST", f"/bot{BOT_TOKEN}/{method}", json={k: v for k, v in params.items() if v is not None})
            break
        except httpx.TransportError as e:
            last = e; print(f"tg {method}: сетевой сбой ({type(e).__name__}: {e}), попытка {attempt + 1}")
            await asyncio.sleep(0.7 * (attempt + 1))
    else:
        raise RuntimeError(f"Нет связи с {TG_API_BASE} ({type(last).__name__}). Проверь /health/api")
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(f"{method}: {j.get('description')}")
    return j["result"]

def check_init_data(raw: str) -> dict:
    """Проверка подписи initData (алгоритм Telegram WebApp). Возвращает dict user."""
    if not raw:
        raise HTTPException(401, "Нет данных запуска (initData пуст). Открой игру через бота в Catugram")
    data = dict(parse_qsl(raw, keep_blank_values=True))
    got = data.pop("hash", "")
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(hmac.new(secret, check.encode(), hashlib.sha256).hexdigest(), got):
        raise HTTPException(401, "Неверная подпись")
    if time.time() - int(data.get("auth_date", 0)) > 86400:
        raise HTTPException(401, "Сессия устарела, перезапусти игру")
    return json.loads(data["user"])

async def auth(c: asyncpg.Connection, init: str):
    u = check_init_data(init)
    now = int(time.time() * 1000)
    await c.execute(
        """insert into users(id,name,username,balance,last_seen) values($1,$2,$3,$4,$5)
           on conflict(id) do update set name=$2, username=$3, last_seen=$5""",
        u["id"], " ".join(filter(None, [u.get("first_name"), u.get("last_name")])) or "Игрок",
        (u.get("username") or "").lower(), INIT_BONUS, now)
    return u["id"]

def err(msg, code=400):
    raise HTTPException(code, msg)

def today_start_ms():
    d = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(d.timestamp() * 1000)

# ---------------------------------------------------------------- состояние
async def build_state(c, uid):
    u = await c.fetchrow("select * from users where id=$1", uid)
    ops = await c.fetch("select * from ops where user_id=$1 order by id desc limit 100", uid)
    used = await c.fetchval(
        "select coalesce(sum(amount),0) from withdrawals where user_id=$1 and status<>'rejected' and created_at>=$2",
        uid, today_start_ms())
    out_ops, wh = [], []
    for o in ops:
        m = json.loads(o["meta"]) if isinstance(o["meta"], str) else o["meta"]
        if o["kind"] == "game":
            out_ops.append({"k": "game", "g": m.get("g"), "b": m.get("b"), "p": m.get("p"), "x": m.get("x"), "ts": o["ts"]})
            if m.get("g") == "wheel" and len(wh) < 7:
                wh.append({"w": 1 if m.get("p", 0) > 0 else 0, "x": m.get("x")})
        else:
            out_ops.append({"k": o["kind"], "a": o["amount"], "id": o["ref"] or f"op{o['id']}", "ts": o["ts"], "promo": m.get("promo")})
    top = await c.fetch("select id,name,best from users where best>0 order by best desc limit 10")
    now = int(time.time() * 1000)
    online = await c.fetchval("select count(*) from users where last_seen>$1", now - 120000)
    return {
        "online": online,
        "state": {
            "balance": u["balance"], "deposited": u["deposited"], "withdrawn": u["withdrawn"],
            "wonTotal": u["won_total"], "played": u["played"], "won": u["won"], "wagered": u["wagered"], "best": u["best"],
            "ops": out_ops, "wh": wh,
            "wd": {"d": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "u": int(used)},
            "ban": -1 if u["ban_until"] == -1 else (u["ban_until"] if u["ban_until"] > now else 0),
            "freeze": u["freeze_until"] if u["freeze_until"] > now else 0,
            "top_list": [{"id": r["id"], "n": ((r["name"] or "Игрок").split() or ["Игрок"])[0][:16], "w": r["best"]} for r in top],
            "is_admin": uid in ADMINS,   # только для показа панели; права проверяются на каждый /admin запрос
        }}

@app.get("/health/api")
async def health_api():
    """Диагностика связи сервера с Catugram: адрес, DNS и getMe. Токен не показывается."""
    import socket, urllib.parse
    host = urllib.parse.urlparse(TG_API_BASE).hostname or ""
    out = {"base": TG_API_BASE, "host": host}
    try:
        out["dns"] = sorted({a[4][0] for a in socket.getaddrinfo(host, 443)})
    except Exception as e:
        out["dns_error"] = f"{type(e).__name__}: {e}"
    out["doh"] = await doh_resolve(host)
    try:
        me = await tg("getMe"); out["ok"] = True; out["bot"] = me.get("username")
    except Exception as e:
        out["ok"] = False; out["error"] = str(e)
    return out

@app.get("/health")
async def health():
    return {"ok": True}

async def keepalive():
    """Render (бесплатный тариф) усыпляет сервис через ~15 минут без запросов. Пока он бодрствует, пингуем сам себя."""
    if not PUBLIC_URL: return
    while True:
        await asyncio.sleep(240)
        try: await http.get(f"{PUBLIC_URL}/health")
        except Exception as e: print("keepalive:", e)

@app.get("/state")
async def state(x_init_data: str = Header("")):
    async with pool.acquire() as c:
        uid = await auth(c, x_init_data)
        return await build_state(c, uid)

# ---------------------------------------------------------------- игры
def blocked(u):
    now = int(time.time() * 1000)
    if u["ban_until"] == -1 or u["ban_until"] > now: err("Аккаунт заблокирован", 403)
    if u["freeze_until"] > now: err("Аккаунт заморожен", 403)

async def play(c, uid, game, bet, x, win: bool):
    """Атомарно: списать ставку, начислить выигрыш, записать раунд. Возвращает (баланс, payout)."""
    payout = int(bet * x) if win else 0
    async with c.transaction():
        u = await c.fetchrow("select * from users where id=$1 for update", uid)
        blocked(u)
        if bet < 1 or bet > MAX_BET: err(f"Ставка от 1 до {MAX_BET}")
        if u["balance"] < bet: err("Не хватает звёзд")
        bal = u["balance"] - bet + payout
        await c.execute(
            """update users set balance=$2, wagered=wagered+$3, won_total=won_total+$4, played=played+1,
               won=won+$5, best=greatest(best,$6) where id=$1""",
            uid, bal, bet, payout, 1 if payout > bet else 0, max(0, payout - bet))
        await c.execute("insert into ops(user_id,kind,amount,meta,ts) values($1,'game',$2,$3,$4)",
                        uid, payout - bet, json.dumps({"g": game, "b": bet, "p": payout, "x": x}), int(time.time() * 1000))
    return bal, payout

def roll_win(x: float) -> bool:
    return secrets.randbelow(1_000_000) / 1_000_000 < RTP / x

@app.post("/wheel")
async def wheel(req: Request, x_init_data: str = Header("")):
    b = await req.json(); bet, x = int(b.get("bet", 0)), float(b.get("x", 0))
    if not 1.1 <= x <= 100: err("Неверный множитель")
    async with pool.acquire() as c:
        uid = await auth(c, x_init_data)
        win = roll_win(x)
        bal, _ = await play(c, uid, "wheel", bet, x, win)
        return {"win": win, "balance": bal}

@app.post("/upgrade")
async def upgrade(req: Request, x_init_data: str = Header("")):
    b = await req.json(); bet, x = int(b.get("bet", 0)), float(b.get("x", 0))
    if not 1.1 <= x <= 100: err("Неверный множитель")
    async with pool.acquire() as c:
        uid = await auth(c, x_init_data)
        win = roll_win(x)
        bal, _ = await play(c, uid, "upgrade", bet, x, win)
        return {"win": win, "balance": bal}

@app.post("/dice")
async def dice(req: Request, x_init_data: str = Header("")):
    b = await req.json(); bet, pick = int(b.get("bet", 0)), b.get("pick")
    if pick not in ("even", "odd"): err("Выбери чёт или нечёт")
    n = secrets.randbelow(6) + 1
    win = (pick == "even") == (n % 2 == 0)
    async with pool.acquire() as c:
        uid = await auth(c, x_init_data)
        bal, _ = await play(c, uid, "dice", bet, 1.9, win)
        return {"n": n, "balance": bal}

# ---------------------------------------------------------------- пополнение (звёзды)
@app.post("/deposit")
async def deposit(req: Request, x_init_data: str = Header("")):
    a = int((await req.json()).get("amount", 0))
    if not 1 <= a <= DEP_MAX: err(f"Сумма от 1 до {DEP_MAX}")
    async with pool.acquire() as c:
        uid = await auth(c, x_init_data)
    link = await tg("createInvoiceLink", title="Пополнение", description=f"{a} игровых звёзд",
                    payload=f"dep:{uid}:{a}:{secrets.token_hex(6)}", currency="XTR", prices=[{"label": "Звёзды", "amount": a}])
    return {"link": link}

@app.post("/deposit_chat")
async def deposit_chat(req: Request, x_init_data: str = Header("")):
    a = int((await req.json()).get("amount", 0))
    if not 1 <= a <= DEP_MAX: err(f"Сумма от 1 до {DEP_MAX}")
    async with pool.acquire() as c:
        uid = await auth(c, x_init_data)
    await tg("sendInvoice", chat_id=uid, title="Пополнение", description=f"{a} игровых звёзд",
             payload=f"dep:{uid}:{a}:{secrets.token_hex(6)}", currency="XTR", prices=[{"label": "Звёзды", "amount": a}])
    return {"ok": True}

def deposit_ref(payload: str, charge_id: str) -> str:
    """Ключ единственного зачисления: код из счёта (n:...) либо id платежа для старых счетов."""
    p = str(payload or "").split(":")
    return f"n:{p[3]}" if len(p) >= 4 and p[3] else str(charge_id)

async def credit_deposit(uid: int, amount: int, ref: str) -> bool:
    """Начисляет пополнение ровно один раз (ref уникален: вебхук и сверка вместе не задвоят)."""
    async with pool.acquire() as c, c.transaction():
        await c.execute("insert into users(id,name,username,balance,last_seen) values($1,'Игрок','',0,0) on conflict(id) do nothing", uid)
        ins = await c.execute("insert into ops(user_id,kind,amount,ref,ts) values($1,'dep',$2,$3,$4) on conflict(ref) do nothing",
                              uid, amount, ref, int(time.time() * 1000))
        if ins.endswith("1"):
            await c.execute("update users set balance=balance+$2, deposited=deposited+$2 where id=$1", uid, amount)
            print(f"DEPOSIT credited user={uid} amount={amount} ref={ref}")
            return True
        return False

async def reconcile(uid: int | None = None) -> int:
    """
    Сверка с журналом звёзд бота (getStarTransactions): находит оплаченные счета пополнения и зачисляет их.
    Работает независимо от вебхука, поэтому баланс пополняется сразу после оплаты.
    """
    credited, offset = 0, 0
    for _ in range(10):                                   # до 1000 последних операций
        res = await tg("getStarTransactions", offset=offset, limit=100)
        txs = res.get("transactions") or []
        if not txs: break
        for t in txs:
            src = t.get("source") or {}
            payload = src.get("invoice_payload") or ""
            parts = str(payload).split(":")
            if len(parts) < 3 or parts[0] != "dep" or not parts[1].isdigit(): continue
            puid, amount = int(parts[1]), int(t.get("amount") or 0)
            if (uid is not None and puid != uid) or amount <= 0: continue
            payer = (src.get("user") or {}).get("id")
            if payer and int(payer) != puid: continue     # платил тот же человек, чей id в счёте
            if await credit_deposit(puid, amount, deposit_ref(payload, t.get("id"))):
                credited += amount
        if len(txs) < 100: break
        offset += len(txs)
    return credited

_last_check: dict[int, float] = {}

@app.post("/deposit/check")
async def deposit_check(x_init_data: str = Header("")):
    async with pool.acquire() as c:
        uid = await auth(c, x_init_data)
    if time.time() - _last_check.get(uid, 0) < 0.8:       # не чаще раза в ~секунду на игрока
        return {"credited": 0}
    _last_check[uid] = time.time()
    return {"credited": await reconcile(uid)}

async def deposit_worker():
    """Подстраховка: раз в 30 секунд сверяет журнал звёзд, даже если игрок закрыл игру."""
    while True:
        await asyncio.sleep(30)
        try: await reconcile()
        except Exception as e: print("deposit_worker:", e)

@app.post("/tg/{secret}")
async def tg_webhook(secret: str, req: Request):
    if not WEBHOOK_SECRET or not hmac.compare_digest(secret, WEBHOOK_SECRET):
        return JSONResponse({"ok": False}, 403)
    try:
        up = await req.json()
        msg = up.get("message") or {}
        print("UPDATE:", [k for k in up.keys() if k != "update_id"], "payment" if msg.get("successful_payment") else "")
        if "pre_checkout_query" in up:
            await tg("answerPreCheckoutQuery", pre_checkout_query_id=up["pre_checkout_query"]["id"], ok=True)
        sp = msg.get("successful_payment")
        if sp:
            print("PAYMENT:", json.dumps(sp, ensure_ascii=False)[:400])
            parts = str(sp.get("invoice_payload", "")).split(":")
            uid = int(parts[1]) if len(parts) >= 3 and parts[1].isdigit() else int((msg.get("from") or {}).get("id") or 0)
            amount = int(sp.get("total_amount") or (parts[2] if len(parts) >= 3 else 0))   # сумма из платежа, не из клиента
            charge = sp.get("telegram_payment_charge_id") or sp.get("provider_payment_charge_id") or f"upd{up.get('update_id')}"
            ref = deposit_ref(sp.get("invoice_payload"), charge)
            if uid and amount > 0:
                await credit_deposit(uid, amount, str(ref))
            else:
                print("PAYMENT ignored: нет uid/amount", uid, amount)
        elif (msg.get("text") or "").startswith("/start"):
            await tg("sendMessage", chat_id=msg["chat"]["id"], text="Нажми кнопку «Играть», чтобы открыть игры.")
    except Exception:
        traceback.print_exc()      # всегда отвечаем 200, ошибка видна в логах Render
    return {"ok": True}


# ---------------------------------------------------------------- вывод
@app.post("/withdraw")
async def withdraw(req: Request, x_init_data: str = Header("")):
    a = int((await req.json()).get("amount", 0))
    async with pool.acquire() as c:
        uid = await auth(c, x_init_data)
        async with c.transaction():
            u = await c.fetchrow("select * from users where id=$1 for update", uid)
            blocked(u)
            used = await c.fetchval("select coalesce(sum(amount),0) from withdrawals where user_id=$1 and status<>'rejected' and created_at>=$2",
                                    uid, today_start_ms())
            if a < WD_MIN: err("Слишком маленькая сумма")
            if a > u["balance"]: err("Не хватает звёзд")
            if used + a > WD_LIMIT: err("Дневной лимит вывода исчерпан")
            now = int(time.time() * 1000)
            await c.execute("update users set balance=balance-$2, withdrawn=withdrawn+$2 where id=$1", uid, a)
            wid = await c.fetchval("insert into withdrawals(user_id,amount,created_at) values($1,$2,$3) returning id", uid, a, now)
            ref = f"wd{wid}"
            await c.execute("insert into ops(user_id,kind,amount,ref,ts) values($1,'wd',$2,$3,$4)", uid, a, ref, now)
        return {"op": {"k": "wd", "a": a, "id": ref, "ts": now}}

async def payout(user_id: int, amount: int, request_id: str) -> bool:
    """
    Выплата через Catugram: withdrawStarBalance(user_id, star_count, request_id).
    С баланса бота списывается amount, игроку приходит 90% (комиссия 10%). Минимум 10 ⭐.
    request_id делает повтор запроса безопасным: второй раз с тем же id не заплатит.
    Бросает RuntimeError(описание ошибки), если выплата не прошла (напр. BALANCE_TOO_LOW).
    """
    await tg("withdrawStarBalance", user_id=user_id, star_count=amount, request_id=request_id)
    return True

async def payout_worker():
    while True:
        await asyncio.sleep(10)
        if not AUTO_PAYOUT: continue
        try:
            async with pool.acquire() as c:
                rows = await c.fetch("select id,user_id,amount from withdrawals where status='pending' order by id limit 10")
                for r in rows:
                    got = await c.fetchval("update withdrawals set status='processing' where id=$1 and status='pending' returning id", r["id"])
                    if not got: continue
                    try:
                        await payout(r["user_id"], r["amount"], f"wd{r['id']}")
                    except Exception as e:
                        # не отклоняем и не возвращаем звёзды автоматически: заявка остаётся в очереди и повторится
                        # (чаще всего BALANCE_TOO_LOW — на балансе бота не хватает звёзд, или 429)
                        print(f"payout wd{r['id']} failed: {e}")
                        await c.execute("update withdrawals set status='pending' where id=$1", r["id"])
                        await asyncio.sleep(3); continue
                    await finish_withdrawal(c, r["id"], True)
        except Exception as e:
            print("payout_worker:", e)

async def finish_withdrawal(c, wid, ok: bool):
    async with c.transaction():
        w = await c.fetchrow("select * from withdrawals where id=$1 for update", wid)
        if w["status"] in ("paid", "rejected"): return
        if ok:
            await c.execute("update withdrawals set status='paid', processed_at=$2 where id=$1", wid, int(time.time()*1000))
        else:  # отказ/ошибка -> вернуть звёзды
            await c.execute("update withdrawals set status='rejected', processed_at=$2 where id=$1", wid, int(time.time()*1000))
            await c.execute("update users set balance=balance+$2, withdrawn=withdrawn-$2 where id=$1", w["user_id"], w["amount"])

# ---------------------------------------------------------------- промокоды
@app.post("/promo")
async def promo(req: Request, x_init_data: str = Header("")):
    code = str((await req.json()).get("code", "")).strip().upper()
    async with pool.acquire() as c:
        uid = await auth(c, x_init_data)
        async with c.transaction():
            p = await c.fetchrow("select * from promos where code=$1 for update", code)
            if not p: err("Промокод не найден")
            if p["used"] >= p["max_uses"]: err("Лимит активаций исчерпан")
            if await c.fetchval("select 1 from promo_uses where code=$1 and user_id=$2", code, uid): err("Ты уже использовал этот промокод")
            await c.execute("insert into promo_uses values($1,$2)", code, uid)
            await c.execute("update promos set used=used+1 where code=$1", code)
            await c.execute("update users set balance=balance+$2 where id=$1", uid, p["stars"])
            await c.execute("insert into ops(user_id,kind,amount,meta,ts) values($1,'dep',$2,'{\"promo\":1}',$3)", uid, p["stars"], int(time.time()*1000))
        return {"ok": True, "stars": p["stars"]}

# ---------------------------------------------------------------- админка (только ADMINS)
@app.post("/admin")
async def admin(req: Request, x_init_data: str = Header("")):
    async with pool.acquire() as c:
        uid = await auth(c, x_init_data)
        if uid not in ADMINS:                       # проверка по подписанному initData, не по тому, что прислал клиент
            err("Нет доступа", 403)
        b = await req.json(); a = b.get("action")
        now = int(time.time() * 1000)
        if a == "promo":
            await c.execute("insert into promos(code,stars,max_uses) values($1,$2,$3) on conflict(code) do update set stars=$2,max_uses=$3",
                            str(b["code"]).upper(), int(b["stars"]), int(b["max"]))
            return {"ok": True}
        if a == "zeroall":
            await c.execute("update users set balance=0"); return {"ok": True}
        if a == "withdrawals":
            rows = await c.fetch("select * from withdrawals where status='pending' order by id limit 100")
            return {"items": [dict(r) for r in rows]}
        if a in ("wd_ok", "wd_no"):
            await finish_withdrawal(c, int(b["id"]), a == "wd_ok"); return {"ok": True}
        target = int(b.get("id") or 0)
        if not target or not await c.fetchval("select 1 from users where id=$1", target):
            err("Игрок не найден (он должен хотя бы раз открыть игру)")
        amt, days = int(b.get("amt") or 0), int(b.get("days") or 0)
        if a in ("give", "me"):
            await c.execute("update users set balance=balance+$2 where id=$1", target, amt)
        elif a == "zero":   await c.execute("update users set balance=0 where id=$1", target)
        elif a == "freeze": await c.execute("update users set freeze_until=$2 where id=$1", target, now + days * 86400000)
        elif a == "ban":    await c.execute("update users set ban_until=$2 where id=$1", target, now + days * 86400000)
        elif a == "banf":   await c.execute("update users set ban_until=-1 where id=$1", target)
        elif a == "unban":  await c.execute("update users set ban_until=0, freeze_until=0 where id=$1", target)
        else: err("Неизвестное действие")
        return {"ok": True}

# ---------------------------------------------------------------- аватарки из Catugram
from fastapi.responses import Response
import mimetypes
_av_cache: dict[int, tuple[float, bytes | None, str]] = {}
AV_TTL = 120   # секунд: сменил фото в Catugram, в игре оно обновится в течение пары минут

@app.get("/avatar/{uid}")
async def avatar(uid: int):
    """Текущая фотография профиля из Catugram (через getUserProfilePhotos). Токен бота наружу не отдаётся."""
    hit = _av_cache.get(uid)
    if hit and time.time() - hit[0] < (AV_TTL if hit[1] else 60):
        data, ctype = hit[1], hit[2]
    else:
        async with pool.acquire() as c:
            known = await c.fetchval("select 1 from users where id=$1", uid)
        if not known:
            raise HTTPException(404, "Нет такого игрока")
        data, ctype = None, "image/jpeg"
        try:
            ph = await tg("getUserProfilePhotos", user_id=uid, limit=1)
            if ph.get("total_count") and ph.get("photos"):
                sizes = ph["photos"][0]
                pick = next((x for x in sizes if x.get("width", 0) >= 160), sizes[-1])   # не самый тяжёлый размер
                f = await tg("getFile", file_id=pick["file_id"])
                r = await api_http("GET", f"/file/bot{BOT_TOKEN}/{f['file_path']}")
                if r.status_code == 200 and r.content:
                    data = r.content
                    ctype = (r.headers.get("content-type") or mimetypes.guess_type(f["file_path"])[0] or "image/jpeg").split(";")[0]
        except Exception as e:
            print("avatar:", uid, e)
        _av_cache[uid] = (time.time(), data, ctype)
    if not data:
        raise HTTPException(404, "Нет фото")
    return Response(content=data, media_type=ctype, headers={"Cache-Control": f"public, max-age={AV_TTL}"})

# ---------------------------------------------------------------- статика
@app.get("/")
async def index():
    base = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(base, "index.html"), os.path.join(base, "static", "index.html")):  # лежит рядом с main.py или в static/
        if os.path.exists(p):
            return FileResponse(p)
    raise HTTPException(404, "index.html не найден рядом с main.py")
