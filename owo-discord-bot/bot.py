import os
import random
import sqlite3
import math
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import commands

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Dummy HTTP server for cloud hosts like Render Web Services (prevents port scan timeout)
class SimpleHealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OwO Bot is Alive and Running!")

    def log_message(self, format, *args):
        # Silence HTTP access logs
        return

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), SimpleHealthHandler)
    print(f"Health server listening on port {port}...")
    server.serve_forever()

if os.environ.get("PORT") or os.environ.get("RENDER"):
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()

# Setup Database — absolute path so it works from any directory
import os as _os
DB_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "owo_bot.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            cash INTEGER DEFAULT 1000000,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            active_title TEXT DEFAULT NULL,
            active_badge TEXT DEFAULT NULL,
            active_weapon TEXT DEFAULT NULL,
            elo INTEGER DEFAULT 1000,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0
        )
    """)
    # Check if columns exist for older DB versions
    cursor.execute("PRAGMA table_info(users)")
    cols = [c[1] for c in cursor.fetchall()]
    if "active_title" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN active_title TEXT DEFAULT NULL")
    if "active_badge" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN active_badge TEXT DEFAULT NULL")
    if "active_weapon" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN active_weapon TEXT DEFAULT NULL")
    if "elo" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN elo INTEGER DEFAULT 1000")
    if "wins" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN wins INTEGER DEFAULT 0")
    if "losses" not in cols:
        cursor.execute("ALTER TABLE users ADD COLUMN losses INTEGER DEFAULT 0")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            item_id TEXT,
            item_name TEXT,
            item_type TEXT,
            icon TEXT,
            purchased_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, item_id)
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT cash, xp, level, active_title, active_badge, active_weapon, elo, wins, losses FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        # Initial cash: 1,000,000 (1 Million) cash, Elo: 1000
        cursor.execute("INSERT INTO users (user_id, cash, xp, level, active_title, active_badge, active_weapon, elo, wins, losses) VALUES (?, 1000000, 0, 1, NULL, NULL, NULL, 1000, 0, 0)", (user_id,))
        conn.commit()
        conn.close()
        return {"cash": 1000000, "xp": 0, "level": 1, "active_title": None, "active_badge": None, "active_weapon": None, "elo": 1000, "wins": 0, "losses": 0, "auto_refilled": False}
    
    cash, xp, level, active_title, active_badge, active_weapon, elo, wins, losses = row
    auto_refilled = False
    
    # Auto-refill rule: Agar cash 0 ya khatam ho jaye to automatic 1 Lakh (100,000) cash add ho jaye (unlimited feature)
    if cash <= 0:
        cash = 100000
        auto_refilled = True
        cursor.execute("UPDATE users SET cash = ? WHERE user_id = ?", (cash, user_id))
        conn.commit()

    conn.close()
    return {
        "cash": cash,
        "xp": xp,
        "level": level,
        "active_title": active_title,
        "active_badge": active_badge,
        "active_weapon": active_weapon,
        "elo": elo if elo is not None else 1000,
        "wins": wins if wins is not None else 0,
        "losses": losses if losses is not None else 0,
        "auto_refilled": auto_refilled
    }

def update_user_stats(user_id, elo_change=0, is_win=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    get_user(user_id)
    cursor.execute("SELECT elo, wins, losses FROM users WHERE user_id = ?", (user_id,))
    elo, wins, losses = cursor.fetchone()
    elo = (elo or 1000) + elo_change
    if elo < 500:
        elo = 500
    if is_win is True:
        wins = (wins or 0) + 1
    elif is_win is False:
        losses = (losses or 0) + 1
    cursor.execute("UPDATE users SET elo = ?, wins = ?, losses = ? WHERE user_id = ?", (elo, wins, losses, user_id))
    conn.commit()
    conn.close()
    return elo, wins, losses

def get_tier_info(elo):
    if elo >= 2400:
        return "👑 Grandmaster", "✨ Mythic Tier (Top 1%)"
    elif elo >= 2000:
        return "🏆 Master", "🔥 Legendary Tier"
    elif elo >= 1600:
        return "💎 Diamond", "💎 High Elo Tier"
    elif elo >= 1300:
        return "🥇 Gold", "⭐ Competitive Tier"
    elif elo >= 1000:
        return "🥈 Silver", "⚔️ Challenger Tier"
    else:
        return "🥉 Bronze", "🌱 Rookie Tier"

def parse_bet_amount(user_id, val):
    """
    Parses user input for bet amount:
    - Supports strings like 'all', 'max', 'half', '50k', '2m', '10,000'
    - Or standard integers/numbers.
    Returns integer bet amount or None if invalid.
    """
    if val is None:
        return None
    
    if isinstance(val, int):
        return val

    val_str = str(val).strip().lower().replace(",", "").replace("_", "")
    user_data = get_user(user_id)
    user_cash = user_data["cash"]

    if val_str in ["all", "allin", "max"]:
        return user_cash
    elif val_str in ["half", "halfway"]:
        return max(1, user_cash // 2)

    # Check k, m, b suffixes (e.g. 10k, 1.5m, 1b)
    mult = 1
    if val_str.endswith("k"):
        mult = 1_000
        val_str = val_str[:-1]
    elif val_str.endswith("m"):
        mult = 1_000_000
        val_str = val_str[:-1]
    elif val_str.endswith("b"):
        mult = 1_000_000_000
        val_str = val_str[:-1]

    try:
        num = float(val_str)
        return int(num * mult)
    except ValueError:
        return None

def update_user_balance(user_id, cash_change, xp_change=0):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Ensure user exists
    get_user(user_id)
    
    cursor.execute("SELECT cash, xp, level FROM users WHERE user_id = ?", (user_id,))
    cash, xp, level = cursor.fetchone()
    
    new_cash = cash + cash_change
    new_xp = xp + xp_change
    
    # Check level up: XP needed = level * 100
    # Reward per level up: level * 1000 OwO cash
    leveled_up = False
    levels_gained = 0
    total_reward = 0
    
    xp_needed = level * 100
    while new_xp >= xp_needed:
        new_xp -= xp_needed
        level += 1
        reward = level * 1000
        new_cash += reward
        total_reward += reward
        levels_gained += 1
        leveled_up = True
        xp_needed = level * 100
        
    auto_refilled = False
    if new_cash <= 0:
        new_cash = 100000
        auto_refilled = True

    cursor.execute("UPDATE users SET cash = ?, xp = ?, level = ? WHERE user_id = ?", (new_cash, new_xp, level, user_id))
    conn.commit()
    conn.close()
    
    return {
        "cash": new_cash,
        "xp": new_xp,
        "level": level,
        "leveled_up": leveled_up,
        "levels_gained": levels_gained,
        "reward": total_reward,
        "auto_refilled": auto_refilled
    }

# Bot Setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=["owo ", "OwO ", "OWO ", "!"], intents=intents, help_command=None)

# ----------------- UI / Interactive Views -----------------

class MinesButton(discord.ui.Button):
    def __init__(self, x, y, is_mine):
        super().__init__(style=discord.ButtonStyle.secondary, label="❓", row=y)
        self.x = x
        self.y = y
        self.is_mine = is_mine

    async def callback(self, interaction: discord.Interaction):
        view: MinesView = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.send_message("❌ Yeh aapki game nahi hai!", ephemeral=True)

        if self.is_mine:
            self.style = discord.ButtonStyle.danger
            self.label = "💣"
            self.disabled = True
            view.game_over = True
            
            # Reveal all
            for child in view.children:
                if isinstance(child, MinesButton):
                    child.disabled = True
                    if child.is_mine:
                        child.style = discord.ButtonStyle.danger
                        child.label = "💣"
                    else:
                        child.style = discord.ButtonStyle.success
                        child.label = "💎"
                elif isinstance(child, CashoutButton):
                    child.disabled = True

            res = update_user_balance(view.user_id, -view.bet, xp_change=10)
            refill_msg = "\n✨ **Unlimited OwO Protection:** Aapka balance 0 hua tha isliye automatically +1,00,000 OwO Cash add ho gaya!" if res["auto_refilled"] else ""
            
            embed = discord.Embed(
                title="💥 BOOM! Mines Game Over",
                description=f"Aapne bomb par click kar diya aur aap **{view.bet:,} OwO Cash** haar gaye!{refill_msg}\nNaya Balance: **{res['cash']:,} OwO**",
                color=discord.Color.red()
            )
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            self.style = discord.ButtonStyle.success
            self.label = "💎"
            self.disabled = True
            view.revealed_diamonds += 1
            
            # Multiplier increases with diamonds
            view.multiplier = round(1.0 + (view.revealed_diamonds * 0.4), 2)
            current_win = int(view.bet * view.multiplier)
            
            # Update Cashout button label
            for child in view.children:
                if isinstance(child, CashoutButton):
                    child.label = f"Cash Out ({current_win:,} OwO)"
                    child.disabled = False

            # Check if all diamonds found
            if view.revealed_diamonds == (view.grid_size * view.grid_size) - view.num_mines:
                view.game_over = True
                for child in view.children:
                    child.disabled = True
                profit = current_win - view.bet
                res = update_user_balance(view.user_id, profit, xp_change=view.revealed_diamonds * 20)
                embed = discord.Embed(
                    title="🎉 ALL DIAMONDS FOUND!",
                    description=f"Kamal kar diya! Saare diamonds nikal liye!\nAap jeete: **+{current_win:,} OwO Cash**!\nTotal Balance: **{res['cash']:,} OwO**",
                    color=discord.Color.gold()
                )
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                embed = discord.Embed(
                    title="💎 Diamond & Mines",
                    description=f"Diamonds Found: **{view.revealed_diamonds}**\nCurrent Multiplier: **{view.multiplier}x**\nClaimable: **{current_win:,} OwO**\n\nClick karte raho ya Cash Out dabao!",
                    color=discord.Color.blue()
                )
                await interaction.response.edit_message(embed=embed, view=view)

class CashoutButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.primary, label="Cash Out (0 OwO)", row=4, disabled=True)

    async def callback(self, interaction: discord.Interaction):
        view: MinesView = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.send_message("❌ Yeh aapki game nahi hai!", ephemeral=True)

        view.game_over = True
        total_payout = int(view.bet * view.multiplier)
        profit = total_payout - view.bet
        
        for child in view.children:
            child.disabled = True
            if isinstance(child, MinesButton):
                if child.is_mine:
                    child.style = discord.ButtonStyle.danger
                    child.label = "💣"
                elif not child.disabled:
                    child.label = "💎"

        res = update_user_balance(view.user_id, profit, xp_change=view.revealed_diamonds * 15)
        level_msg = f"\n🎊 **LEVEL UP!** Aap Level {res['level']} par pahunch gaye! Bonus +{res['reward']:,} OwO Cash mila!" if res["leveled_up"] else ""

        embed = discord.Embed(
            title="💰 Cashed Out Successfully!",
            description=f"Aapne **{total_payout:,} OwO Cash** cash out kiya!\nProfit: **+{profit:,} OwO**{level_msg}\nNaya Balance: **{res['cash']:,} OwO**",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(embed=embed, view=view)

class MinesView(discord.ui.View):
    def __init__(self, user_id, bet, num_mines=3):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.bet = bet
        self.num_mines = num_mines
        self.grid_size = 4 # 4x4 grid (16 tiles)
        self.revealed_diamonds = 0
        self.multiplier = 1.0
        self.game_over = False

        # Place mines
        all_positions = [(x, y) for y in range(self.grid_size) for x in range(self.grid_size)]
        mine_positions = set(random.sample(all_positions, num_mines))

        for x, y in all_positions:
            is_mine = (x, y) in mine_positions
            self.add_item(MinesButton(x, y, is_mine))

        self.add_item(CashoutButton())

# ----------------- EVENTS -----------------

@bot.event
async def on_ready():
    init_db()
    print(f"Logged in as {bot.user.name} ({bot.user.id})")
    print(f"Connected to {len(bot.guilds)} server(s): {[g.name for g in bot.guilds]}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")
    print("OwO Discord Bot is Online and Ready!")

@bot.event
async def on_message(message):
    # Don't respond to ourselves or other bots
    if message.author.bot:
        return
    
    # Debug print incoming message prefix check
    content = message.content.strip()
    if any(content.lower().startswith(p.lower()) for p in ["owo ", "!", "owo"]):
        print(f"Received potential command from {message.author}: {content}")
        
    await bot.process_commands(message)

# ----------------- COMMANDS -----------------

@bot.command(name="help", aliases=["commands"])
async def owo_help(ctx):
    embed = discord.Embed(
        title="✨ OwO Game Bot - Command List ✨",
        description="Aapka custom OwO Casino & Cash Game Bot with Unlimited OwO Cash!",
        color=discord.Color.purple()
    )
    embed.add_field(
        name="💰 Economy & Balance",
        value=(
            "`owo cash` ya `owo bal` - Apna OwO Cash balance aur level dekhein\n"
            "`owo daily` - Rozana free 1,00,000 OwO Cash claim karein\n"
            "`owo give <@user> <amount>` - Dusre user ko OwO transfer karein\n"
            "✨ **Unlimited Protection:** Jab bhi aapka cash 0 ho jayega, automatically +1,00,000 OwO Cash wapas add ho jayega!"
        ),
        inline=False
    )
    embed.add_field(
        name="🏬 OwO Store & Inventory",
        value=(
            "`owo store` - Interactive Luxury Store kholein (dropdown menu)\n"
            "`owo buy <item_id>` - Direct store item khareedein\n"
            "`owo inv` / `owo bag` - Apni inventory aur collection dekhein\n"
            "`owo equip <item_id>` - Title ya badge apne profile par lagayein\n"
            "`owo unequip <title/badge>` - Equipped title ya badge hatayein"
        ),
        inline=False
    )
    embed.add_field(
        name="🎮 Mini Games",
        value=(
            "`owo coinflip <h/t> <amount>` - Head ya Tails game (2x win)\n"
            "`owo mines [amount] [bombs]` - Interactive Diamond & Mines game\n"
            "`owo roulette <color/number> <amount>` - OwO Casino Roulette\n"
            "`owo slots <amount>` - Classic Slot Machine game\n"
            "`owo spin [amount]` - 🎡 **Spin & Win!** Jackpot = **1,000,000 OwO!**"
        ),
        inline=False
    )
    embed.add_field(
        name="⭐ Levels, Ranks & Competitive",
        value=(
            "`owo level` - Level aur XP status dekhein\n"
            "`owo rank` - Apna Competitive Tier aur ELO rating dekhein\n"
            "`owo top` - Richest players ka leaderboard\n"
            "`owo toprank` - Competitive Arena ELO leaderboard (Rankings)"
        ),
        inline=False
    )
    embed.add_field(
        name="⚔️ Multiplayer 1v1, Duo, Trio & Squad Games",
        value=(
            "`owo rps @opponent <bet>` - 1v1 Rock Paper Scissors Duel (Private Choice + Bet + ELO)\n"
            "`owo battle @partner <bet>` - 2-Player Co-op Dungeon Boss Raid (Live Turns)\n"
            "`owo trio @p1 @p2 <bet>` - 3-Player Co-op Elder Dragon Raid (520 HP)\n"
            "`owo squad [bet]` - 4-Player Battle Royale Lobby (Live Round Eliminations)"
        ),
        inline=False
    )
    embed.add_field(
        name="🔍 Check & Info Commands",
        value=(
            "`owo ping` - Bot online status aur latency check karo\n"
            "`owo games` - Saare games ki list aur rules dekho\n"
            "`owo rules <game>` - Kisi game ke detailed rules dekho\n"
            "`owo demo <game>` - Game FREE mein try karo — koi bet nahi!\n"
            "`owo profile [@user]` - Full OwO profile card dekho\n"
            "`owo checkgame` - Saare bot systems ka quick health check"
        ),
        inline=False
    )
    embed.set_footer(text="Tip: owo demo spin se pehle try karo, phir khao! 🎮")
    await ctx.send(embed=embed)

@bot.command(name="cash", aliases=["bal", "balance", "money"])
async def owo_balance(ctx, member: discord.Member = None):
    target = member or ctx.author
    user_data = get_user(target.id)
    
    xp_needed = user_data["level"] * 100
    refill_text = "\n*(✨ Note: Aapka cash khatam ho gaya tha, isliye automatic +1,000 OwO Cash reload ho gaya!)*" if user_data["auto_refilled"] else ""
    
    embed = discord.Embed(
        title=f"💳 {target.display_name}'s OwO Bank",
        color=discord.Color.gold()
    )
    embed.add_field(name="💵 OwO Cash", value=f"**{user_data['cash']:,} OwO**", inline=True)
    embed.add_field(name="🏆 Level", value=f"**Level {user_data['level']}**", inline=True)
    embed.add_field(name="✨ XP", value=f"**{user_data['xp']}/{xp_needed} XP**", inline=True)
    if refill_text:
        embed.description = refill_text
    embed.set_thumbnail(url=target.display_avatar.url)
    await ctx.send(embed=embed)

@bot.command(name="daily")
@commands.cooldown(1, 86400, commands.BucketType.user)
async def owo_daily(ctx):
    daily_reward = 100000  # 1 Lakh daily reward
    res = update_user_balance(ctx.author.id, daily_reward, xp_change=25)
    embed = discord.Embed(
        title="🎁 Daily OwO Claimed!",
        description=f"Aapne aaj ka **+{daily_reward:,} OwO Cash** claim kar liya!\nNaya Balance: **{res['cash']:,} OwO**",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@owo_daily.error
async def owo_daily_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        hours = int(error.retry_after // 3600)
        minutes = int((error.retry_after % 3600) // 60)
        await ctx.send(f"⏳ Aap pehle hi daily reward claim kar chuke hain! Wapas aaiye **{hours}h {minutes}m** baad.")

@bot.command(name="coinflip", aliases=["cf", "flip", "headortails", "ht"])
async def owo_coinflip(ctx, choice: str = None, bet: str = None):
    import asyncio
    if not choice or bet is None:
        return await ctx.send("❓ **Usage:** `owo coinflip <heads/tails> <amount/all/half>`\nExample: `owo coinflip h 500` ya `owo cf h all`")
    
    bet_amount = parse_bet_amount(ctx.author.id, bet)
    if bet_amount is None:
        return await ctx.send("❌ Galat bet amount! Kripya valid number, `all`, ya `half` daalein (e.g. `500`, `10k`, `all`).")

    choice = choice.lower()
    if choice in ["h", "head", "heads"]:
        choice_str = "heads"
    elif choice in ["t", "tail", "tails"]:
        choice_str = "tails"
    else:
        return await ctx.send("❌ Galat choice! Kripya `heads` (h) ya `tails` (t) chunein.")

    if bet_amount <= 0:
        return await ctx.send("❌ Bet amount 0 se zyada honi chahiye!")

    user_data = get_user(ctx.author.id)
    if user_data["cash"] < bet_amount:
        return await ctx.send(f"❌ Aapke paas itna OwO Cash nahi hai! Balance: **{user_data['cash']:,} OwO**")

    # Starting Flip Animation
    flip_embed = discord.Embed(
        title="🪙 Flipping Coin... 💨",
        description=f"Aapne chuna: **{choice_str.upper()}** | Bet: **{bet_amount:,} OwO**\n\n```\n   🪙 Coin hawa mein uchal raha hai...   \n```",
        color=discord.Color.gold()
    )
    msg = await ctx.send(embed=flip_embed)

    frames = [
        ("🪙 [ HEADS ]", "🟡 Coin ghoom raha hai..."),
        ("💿 [ TAILS ]", "⚪ Coin flip ho raha hai..."),
        ("🪙 [ HEADS ]", "🟡 Dheere dheere neeche aa raha hai..."),
        ("💿 [ TAILS ]", "⚪ Zameen par girne wala hai..."),
    ]
    for face, text in frames:
        await asyncio.sleep(0.4)
        anim_embed = discord.Embed(
            title="🪙 Flipping Coin...",
            description=f"Aapne chuna: **{choice_str.upper()}** | Bet: **{bet_amount:,} OwO**\n\n```\n   {face}   \n```\n*{text}*",
            color=discord.Color.gold()
        )
        await msg.edit(embed=anim_embed)

    await asyncio.sleep(0.4)

    # Flip coin
    outcome = random.choice(["heads", "tails"])
    coin_emoji = "🪙" if outcome == "heads" else "💿"

    if outcome == choice_str:
        # Win (2x bet = net +bet)
        res = update_user_balance(ctx.author.id, bet_amount, xp_change=20)
        level_msg = f"\n🎊 **LEVEL UP!** Aap Level {res['level']} par pahunch gaye! (+{res['reward']:,} OwO Bonus)" if res["leveled_up"] else ""
        
        embed = discord.Embed(
            title=f"{coin_emoji} Coinflip Won! 🎉",
            description=(
                f"```\n"
                f"┌─────────────────────────┐\n"
                f"│      WINNER: {outcome.upper():<7}    │\n"
                f"└─────────────────────────┘\n"
                f"```\n"
                f"Aapne chuna tha: **{choice_str.upper()}**\n"
                f"Coin par aaya: **{outcome.upper()}**\n\n"
                f"🎉 Aap jeete: **+{bet_amount:,} OwO Cash**!{level_msg}\n"
                f"Balance: **{res['cash']:,} OwO**"
            ),
            color=discord.Color.green()
        )
    else:
        # Loss
        res = update_user_balance(ctx.author.id, -bet_amount, xp_change=5)
        refill_msg = "\n✨ **Unlimited OwO Protection:** Balance 0 hone par automatically +1,00,000 OwO Cash add ho gaya!" if res["auto_refilled"] else ""
        
        embed = discord.Embed(
            title=f"{coin_emoji} Coinflip Lost! 😢",
            description=(
                f"```\n"
                f"┌─────────────────────────┐\n"
                f"│      RESULT: {outcome.upper():<7}    │\n"
                f"└─────────────────────────┘\n"
                f"```\n"
                f"Aapne chuna tha: **{choice_str.upper()}**\n"
                f"Coin par aaya: **{outcome.upper()}**\n\n"
                f"😢 Aap haar gaye: **-{bet_amount:,} OwO Cash**.{refill_msg}\n"
                f"Balance: **{res['cash']:,} OwO**"
            ),
            color=discord.Color.red()
        )
    await msg.edit(embed=embed)

@bot.command(name="mines", aliases=["mine", "diamond"])
async def owo_mines(ctx, bet: str = "100", bombs: int = 3):
    bet_amount = parse_bet_amount(ctx.author.id, bet)
    if bet_amount is None or bet_amount <= 0:
        return await ctx.send("❌ Galat bet amount! Kripya valid number, `all`, ya `half` daalein (e.g. `100`, `50k`, `all`).")
    
    if bombs < 1 or bombs > 8:
        return await ctx.send("❌ Bombs ki sankhya 1 se 8 ke beech honi chahiye (Default: 3)!")

    user_data = get_user(ctx.author.id)
    if user_data["cash"] < bet_amount:
        return await ctx.send(f"❌ Aapke paas itna OwO Cash nahi hai! Balance: **{user_data['cash']:,} OwO**")

    view = MinesView(user_id=ctx.author.id, bet=bet_amount, num_mines=bombs)
    embed = discord.Embed(
        title="💎 Diamond & Mines Game 💣",
        description=f"Player: {ctx.author.mention}\nBet: **{bet_amount:,} OwO** | Bombs: **{bombs}**\n\nTiles click karke diamond nikalo. Jitne zyada diamonds, utna bada multiplier!\nJab man kare tab **Cash Out** daba do!",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed, view=view)

@bot.command(name="roulette", aliases=["roul", "rl"])
async def owo_roulette(ctx, bet_type: str = None, bet: str = None):
    import asyncio
    if not bet_type or bet is None:
        return await ctx.send(
            "❓ **Usage:** `owo roulette <option> <amount/all/half>`\n\n"
            "**Options:**\n"
            "• `red` / `black` (2x payout)\n"
            "• `even` / `odd` (2x payout)\n"
            "• `green` (14x payout - Number 0)\n"
            "• Number `0` to `36` (36x payout)\n"
            "Example: `owo roulette red 500` ya `owo roulette 7 all`"
        )

    bet_amount = parse_bet_amount(ctx.author.id, bet)
    if bet_amount is None or bet_amount <= 0:
        return await ctx.send("❌ Galat bet amount! Kripya valid number, `all`, ya `half` daalein (e.g. `500`, `25k`, `all`).")

    user_data = get_user(ctx.author.id)
    if user_data["cash"] < bet_amount:
        return await ctx.send(f"❌ Aapke paas itna OwO Cash nahi hai! Balance: **{user_data['cash']:,} OwO**")

    # Initial Roulette Spin Message
    init_embed = discord.Embed(
        title="🎡 Roulette Wheel Spinning... 💨",
        description=f"Aapki Bet: **{bet_type.upper()}** | Amount: **{bet_amount:,} OwO**\n\n```\n  [ 🔴 14 ] [ ⚫ 2 ] [ 🟢 0 ] [ 🔴 9 ] [ ⚫ 28 ]  \n             ▲ Ball Rolling... ▲             \n```",
        color=discord.Color.gold()
    )
    msg = await ctx.send(embed=init_embed)

    # Roulette animation frames
    r_frames = [
        "  [ ⚫ 26 ] [ 🔴 3 ] [ ⚫ 35 ] [ 🔴 12 ] [ ⚫ 28 ]  \n             ▲ Ball Spinning Fast! ▲          ",
        "  [ 🔴 7  ] [ ⚫ 29 ] [ 🟢 0  ] [ ⚫ 2  ] [ 🔴 14 ]  \n             ▲ Ball Bouncing... ▲            ",
        "  [ ⚫ 15 ] [ 🔴 19 ] [ ⚫ 4  ] [ 🔴 21 ] [ ⚫ 2  ]  \n             ▲ Dheere dheere ruk rahi hai... ▲",
        "  [ 🔴 32 ] [ ⚫ 20 ] [ 🔴 1  ] [ ⚫ 33 ] [ 🔴 16 ]  \n             ▲ Almost there... ▲             ",
    ]
    for frame in r_frames:
        await asyncio.sleep(0.4)
        anim_embed = discord.Embed(
            title="🎡 Roulette Wheel Spinning... 💨",
            description=f"Aapki Bet: **{bet_type.upper()}** | Amount: **{bet_amount:,} OwO**\n\n```\n{frame}\n```",
            color=discord.Color.gold()
        )
        await msg.edit(embed=anim_embed)

    await asyncio.sleep(0.4)

    # Roulette logic (European 0-36)
    rolled_num = random.randint(0, 36)
    red_numbers = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
    
    if rolled_num == 0:
        rolled_color = "green"
    elif rolled_num in red_numbers:
        rolled_color = "red"
    else:
        rolled_color = "black"

    won = False
    payout = 0
    bet_type = bet_type.lower()

    if bet_type in ["red", "r"] and rolled_color == "red":
        won = True
        payout = bet_amount * 2
    elif bet_type in ["black", "b"] and rolled_color == "black":
        won = True
        payout = bet_amount * 2
    elif bet_type in ["green", "g"] and rolled_color == "green":
        won = True
        payout = bet_amount * 14
    elif bet_type == "even" and rolled_num != 0 and rolled_num % 2 == 0:
        won = True
        payout = bet_amount * 2
    elif bet_type == "odd" and rolled_num != 0 and rolled_num % 2 == 1:
        won = True
        payout = bet_amount * 2
    elif bet_type.isdigit():
        target_num = int(bet_type)
        if 0 <= target_num <= 36 and target_num == rolled_num:
            won = True
            payout = bet_amount * 36

    color_emoji = "🟢" if rolled_color == "green" else ("🔴" if rolled_color == "red" else "⚫")

    if won:
        profit = payout - bet_amount
        res = update_user_balance(ctx.author.id, profit, xp_change=30)
        level_msg = f"\n🎊 **LEVEL UP!** Aap Level {res['level']} par pahunch gaye! (+{res['reward']:,} OwO Bonus)" if res["leveled_up"] else ""

        embed = discord.Embed(
            title="🎡 Roulette - YOU WON! 🎉",
            description=(
                f"```\n"
                f"┌─────────────────────────────────┐\n"
                f"│     BALL LANDED ON: {rolled_num} {rolled_color.upper():<5}   │\n"
                f"└─────────────────────────────────┘\n"
                f"```\n"
                f"Wheel landed on: {color_emoji} **{rolled_num} ({rolled_color.upper()})**!\n"
                f"Aapki bet thi: **{bet_type.upper()}**\n\n"
                f"🎉 Total Payout: **+{payout:,} OwO** (Profit: +{profit:,}){level_msg}\n"
                f"Naya Balance: **{res['cash']:,} OwO**"
            ),
            color=discord.Color.green()
        )
    else:
        res = update_user_balance(ctx.author.id, -bet_amount, xp_change=10)
        refill_msg = "\n✨ **Unlimited OwO Protection:** Balance 0 hone par automatically +1,00,000 OwO Cash add ho gaya!" if res["auto_refilled"] else ""

        embed = discord.Embed(
            title="🎡 Roulette - YOU LOST! 😢",
            description=(
                f"```\n"
                f"┌─────────────────────────────────┐\n"
                f"│     BALL LANDED ON: {rolled_num} {rolled_color.upper():<5}   │\n"
                f"└─────────────────────────────────┘\n"
                f"```\n"
                f"Wheel landed on: {color_emoji} **{rolled_num} ({rolled_color.upper()})**\n"
                f"Aapki bet thi: **{bet_type.upper()}**\n\n"
                f"😢 Haar gaye: **-{bet_amount:,} OwO Cash**{refill_msg}\n"
                f"Naya Balance: **{res['cash']:,} OwO**"
            ),
            color=discord.Color.red()
        )
    await msg.edit(embed=embed)

@bot.command(name="slots", aliases=["slot", "s"])
async def owo_slots(ctx, bet: str = "100"):
    import asyncio
    bet_amount = parse_bet_amount(ctx.author.id, bet)
    if bet_amount is None or bet_amount <= 0:
        return await ctx.send("❌ Galat bet amount! Kripya valid number, `all`, ya `half` daalein (e.g. `100`, `50k`, `all`).")

    user_data = get_user(ctx.author.id)
    if user_data["cash"] < bet_amount:
        return await ctx.send(f"❌ Aapke paas itna OwO Cash nahi hai! Balance: **{user_data['cash']:,} OwO**")

    # Slot animation start
    slot_embed = discord.Embed(
        title="🎰 Slot Machine Spinning... 💨",
        description=f"Player: {ctx.author.mention} | Bet: **{bet_amount:,} OwO**\n\n```\n   [ 🔄 | 🔄 | 🔄 ]   \n   Reels ghoom rahe hain...   \n```",
        color=discord.Color.gold()
    )
    msg = await ctx.send(embed=slot_embed)

    symbols = ["🍒", "🍋", "🍇", "🔔", "⭐", "💎", "7️⃣"]

    # Reel animation loop
    for i in range(4):
        await asyncio.sleep(0.35)
        r1, r2, r3 = random.choice(symbols), random.choice(symbols), random.choice(symbols)
        anim_embed = discord.Embed(
            title="🎰 Slot Machine Spinning... 💨",
            description=f"Player: {ctx.author.mention} | Bet: **{bet_amount:,} OwO**\n\n```\n   [ {r1} | {r2} | {r3} ]   \n   Spinning Reels...   \n```",
            color=discord.Color.gold()
        )
        await msg.edit(embed=anim_embed)

    await asyncio.sleep(0.4)

    # Final symbols
    s1, s2, s3 = random.choice(symbols), random.choice(symbols), random.choice(symbols)

    multiplier = 0
    if s1 == s2 == s3:
        if s1 == "7️⃣":
            multiplier = 20
        elif s1 == "💎":
            multiplier = 10
        elif s1 == "⭐":
            multiplier = 7
        else:
            multiplier = 5
    elif s1 == s2 or s2 == s3 or s1 == s3:
        multiplier = 2

    if multiplier > 0:
        total_payout = bet_amount * multiplier
        profit = total_payout - bet_amount
        res = update_user_balance(ctx.author.id, profit, xp_change=25)
        level_msg = f"\n🎊 **LEVEL UP!** Level {res['level']}! (+{res['reward']:,} OwO)" if res["leveled_up"] else ""

        embed = discord.Embed(
            title="🎰 OwO Slot Machine - WINNER! 🎉",
            description=(
                f"```\n"
                f"┌───────────────────┐\n"
                f"│   {s1} │ {s2} │ {s3}   │\n"
                f"└───────────────────┘\n"
                f"```\n"
                f"🎉 Multiplier: **{multiplier}x**\n"
                f"Aap jeete: **+{total_payout:,} OwO Cash**!{level_msg}\n"
                f"Naya Balance: **{res['cash']:,} OwO**"
            ),
            color=discord.Color.gold()
        )
    else:
        res = update_user_balance(ctx.author.id, -bet_amount, xp_change=5)
        refill_msg = "\n✨ **Unlimited OwO:** Auto-refill +1,00,000 OwO Cash!" if res["auto_refilled"] else ""

        embed = discord.Embed(
            title="🎰 OwO Slot Machine 😢",
            description=(
                f"```\n"
                f"┌───────────────────┐\n"
                f"│   {s1} │ {s2} │ {s3}   │\n"
                f"└───────────────────┘\n"
                f"```\n"
                f"😢 Match nahi hua! Aap haar gaye **-{bet_amount:,} OwO Cash**.{refill_msg}\n"
                f"Naya Balance: **{res['cash']:,} OwO**"
            ),
            color=discord.Color.red()
        )
    await msg.edit(embed=embed)

@bot.command(name="give", aliases=["pay", "send"])
async def owo_give(ctx, member: discord.Member = None, amount: int = None):
    if not member or amount is None:
        return await ctx.send("❓ **Usage:** `owo give <@user> <amount>`")
    if member.id == ctx.author.id:
        return await ctx.send("❌ Khud ko transfer nahi kar sakte!")
    if member.bot:
        return await ctx.send("❌ Bots ko OwO Cash transfer nahi kar sakte!")
    if amount <= 0:
        return await ctx.send("❌ Amount 0 se zyada honi chahiye!")

    sender = get_user(ctx.author.id)
    if sender["cash"] < amount:
        return await ctx.send(f"❌ Aapke paas paryapt cash nahi hai! Balance: **{sender['cash']:,} OwO**")

    update_user_balance(ctx.author.id, -amount)
    receiver_res = update_user_balance(member.id, amount)

    embed = discord.Embed(
        title="💸 OwO Cash Transfer",
        description=f"{ctx.author.mention} ne {member.mention} ko **{amount:,} OwO Cash** bhej diye! 🎁",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name="top", aliases=["rich", "leaderboard", "lb"])
async def owo_leaderboard(ctx):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, cash, level FROM users ORDER BY cash DESC LIMIT 10")
    top_players = cursor.fetchall()
    conn.close()

    embed = discord.Embed(
        title="🏆 OwO Richest Players Leaderboard",
        color=discord.Color.gold()
    )
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    description = ""
    for idx, (uid, cash, level) in enumerate(top_players):
        user = ctx.guild.get_member(uid)
        username = user.display_name if user else f"User ({uid})"
        medal = medals[idx] if idx < len(medals) else f"#{idx+1}"
        description += f"{medal} **{username}** — {cash:,} OwO *(Lvl {level})*\n"

    embed.description = description or "Abhi tak koi player data nahi hai!"
    embed.set_footer(text="Competitive rank leaderboard dekhne ke liye: owo toprank")
    await ctx.send(embed=embed)

@bot.command(name="toprank", aliases=["leaderboardrank", "topelo", "lbrank", "ranks"])
async def owo_toprank(ctx):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, elo, wins, losses FROM users ORDER BY elo DESC LIMIT 10")
    top_ranked = cursor.fetchall()
    conn.close()

    embed = discord.Embed(
        title="⚔️ OwO Competitive Arena Leaderboard (ELO)",
        description="Top 1v1, Duo & Squad combatants on the server!\n───────────────────────────────",
        color=discord.Color.purple()
    )
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    description = ""
    for idx, (uid, elo, wins, losses) in enumerate(top_ranked):
        user = ctx.guild.get_member(uid)
        username = user.display_name if user else f"User ({uid})"
        medal = medals[idx] if idx < len(medals) else f"#{idx+1}"
        tier, _ = get_tier_info(elo or 1000)
        description += f"{medal} **{username}** — **{elo} ELO** [{tier}] `({wins or 0}W/{losses or 0}L)`\n"

    embed.description = (embed.description or "") + (description or "Abhi tak koi match nahi hua!")
    embed.set_footer(text="Match khelo aur ELO badhao! Command: owo rps / owo battle / owo squad")
    await ctx.send(embed=embed)

@bot.command(name="rank", aliases=["myrank", "elo", "tier"])
async def owo_my_rank(ctx, member: discord.Member = None):
    target = member or ctx.author
    user_data = get_user(target.id)
    tier, desc = get_tier_info(user_data["elo"])
    total = user_data["wins"] + user_data["losses"]
    winrate = round((user_data["wins"] / total * 100), 1) if total > 0 else 0.0

    embed = discord.Embed(
        title=f"⚔️ {target.display_name}'s Arena Rank",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="🎖️ Current Tier", value=f"**{tier}**", inline=True)
    embed.add_field(name="⚡ ELO Rating", value=f"**{user_data['elo']}**", inline=True)
    embed.add_field(name="🏆 Total Matches", value=f"**{total}** ({user_data['wins']}W - {user_data['losses']}L)", inline=True)
    embed.add_field(name="🎯 Winrate", value=f"**{winrate}%**", inline=True)
    embed.add_field(name="📜 Tier Rank Info", value=f"*{desc}*", inline=False)
    embed.set_footer(text="1v1: owo rps | Duo Battle: owo battle | Squad 4v4: owo squad")
    await ctx.send(embed=embed)

@bot.command(name="level", aliases=["lvl", "levels"])
async def owo_level(ctx, member: discord.Member = None):
    target = member or ctx.author
    user_data = get_user(target.id)
    xp_needed = user_data["level"] * 100
    next_level_reward = (user_data["level"] + 1) * 1000

    embed = discord.Embed(
        title=f"⭐ {target.display_name}'s Level & Progress",
        color=discord.Color.blue()
    )
    embed.add_field(name="Current Level", value=f"🏆 **Level {user_data['level']}**", inline=True)
    embed.add_field(name="Experience (XP)", value=f"✨ **{user_data['xp']} / {xp_needed} XP**", inline=True)
    embed.add_field(name="Next Level Reward", value=f"🎁 **+{next_level_reward:,} OwO Cash**", inline=True)
    embed.set_footer(text="Tip: Har game khelne par XP milta hai!")
    await ctx.send(embed=embed)

# ----------------- SPIN AND WIN -----------------

SPIN_SEGMENTS = [
    # (label, multiplier, weight, is_jackpot)
    ("💀 BANKRUPT",    0,     8,  False),
    ("🔸 50 OwO",      0,     10, False),  # fixed tiny win
    ("🎁 2x",          2,     20, False),
    ("🎁 3x",          3,     18, False),
    ("🎁 5x",          5,     14, False),
    ("🎁 10x",         10,    10, False),
    ("🎁 20x",         20,    8,  False),
    ("🎁 50x",         50,    5,  False),
    ("🎁 100x",        100,   4,  False),
    ("🌟 500x",        500,   2,  False),
    ("🏆 JACKPOT 1M!", 0,     1,  True),   # 1 Million fixed jackpot
]

JACKPOT_AMOUNT = 1_000_000  # 10 lakh

def spin_wheel():
    """Weighted random spin. Returns chosen segment tuple."""
    population = []
    for seg in SPIN_SEGMENTS:
        population.extend([seg] * seg[2])
    return random.choice(population)

class SpinButton(discord.ui.Button):
    def __init__(self, bet):
        super().__init__(style=discord.ButtonStyle.success, label="🎡  SPIN!", emoji=None)
        self.bet = bet

    async def callback(self, interaction: discord.Interaction):
        import asyncio
        view: SpinView = self.view
        if interaction.user.id != view.user_id:
            return await interaction.response.send_message("❌ Yeh aapki game nahi hai!", ephemeral=True)

        # Disable button to prevent double-spin
        self.disabled = True
        await interaction.response.edit_message(view=view)

        # Pre-decide result
        segment = spin_wheel()
        label, multiplier, _, is_jackpot = segment

        # ─────────────────────────────────────────
        # WHEEL SEGMENTS displayed in order
        # ─────────────────────────────────────────
        wheel_segments = [
            "💀 BANKRUPT",
            "🎁 2x",
            "🔸 50 OwO",
            "🎁 5x",
            "🎁 3x",
            "🌟 500x",
            "🎁 10x",
            "💀 BANKRUPT",
            "🎁 20x",
            "🎁 50x",
            "🎁 100x",
            "🏆 JACKPOT!",
        ]

        # Find index of winning segment (closest match)
        winning_label = "🏆 JACKPOT!" if is_jackpot else (
            "💀 BANKRUPT" if label == "💀 BANKRUPT" else (
                "🔸 50 OwO" if multiplier == 0 else f"🎁 {multiplier}x" if multiplier <= 100 else "🌟 500x"
            )
        )
        # Find index
        win_idx = 0
        for i, s in enumerate(wheel_segments):
            if winning_label in s or s in winning_label:
                win_idx = i
                break

        total_segments = len(wheel_segments)

        def build_wheel(center_idx):
            """Build a visual wheel with 5 visible slots, center is the pointer"""
            idxs = [(center_idx + i - 2) % total_segments for i in range(5)]
            slots = wheel_segments[idxs[0]], wheel_segments[idxs[1]], wheel_segments[idxs[2]], wheel_segments[idxs[3]], wheel_segments[idxs[4]]
            # Center (index 2) is the pointed slot
            line0 = "┌─────────────────────────────────┐"
            line1 = f"│  {slots[0]:<12}                  │"
            line2 = f"│  {slots[1]:<12}                  │"
            line3 = f"│▶▶ {slots[2]:<12} ◀◀             │"   # <-- pointer
            line4 = f"│  {slots[3]:<12}                  │"
            line5 = f"│  {slots[4]:<12}                  │"
            line6 = "└─────────────────────────────────┘"
            return f"```\n{line0}\n{line1}\n{line2}\n{line3}\n{line4}\n{line5}\n{line6}\n```"

        # ─────────────────────────────────────────
        # PHASE 1: Fast spinning (random positions)
        # ─────────────────────────────────────────
        fast_frames = 10
        fast_delay = 0.18
        pos = random.randint(0, total_segments - 1)

        for i in range(fast_frames):
            pos = (pos + 3) % total_segments
            wheel_art = build_wheel(pos)
            embed = discord.Embed(
                title="🎡 Spin & Win — Spinning Fast! 💨",
                description=f"{wheel_art}\n**Bet:** {self.bet:,} OwO | 🔄 Spinning...",
                color=discord.Color.yellow()
            )
            embed.set_footer(text="▶▶ Wheel spinning fast... ◀◀")
            await interaction.edit_original_response(content=None, embed=embed, view=None)
            await asyncio.sleep(fast_delay)

        # ─────────────────────────────────────────
        # PHASE 2: Slowing down (approach winner)
        # ─────────────────────────────────────────
        # Calculate how many steps to reach win_idx from current pos (going forward)
        steps_needed = (win_idx - pos) % total_segments
        if steps_needed == 0:
            steps_needed = total_segments

        # Add some extra full rotations for effect
        extra_laps = total_segments * 1  # 1 extra full lap
        total_slow_steps = extra_laps + steps_needed

        slow_delays = []
        for i in range(total_slow_steps):
            # Gradually increase delay from 0.22 → 0.65
            progress = i / total_slow_steps
            delay = 0.22 + (0.43 * progress)
            slow_delays.append(delay)

        for i, delay in enumerate(slow_delays):
            pos = (pos + 1) % total_segments
            steps_left = total_slow_steps - i

            if steps_left <= 4:
                title = "🎡 Almost there... 🤞"
                color = discord.Color.orange()
                footer = f"⏳ {steps_left} step(s) bachi hai..."
            elif steps_left <= 8:
                title = "🎡 Slowing down... 🐢"
                color = discord.Color.orange()
                footer = "🐢 Wheel dheemi ho rahi hai..."
            else:
                title = "🎡 Spin & Win — 💨"
                color = discord.Color.yellow()
                footer = "▶▶ Wheel spinning... ◀◀"

            wheel_art = build_wheel(pos)
            embed = discord.Embed(
                title=title,
                description=f"{wheel_art}\n**Bet:** {self.bet:,} OwO",
                color=color
            )
            embed.set_footer(text=footer)
            await interaction.edit_original_response(content=None, embed=embed, view=None)
            await asyncio.sleep(delay)

        # ─────────────────────────────────────────
        # PHASE 3: Final STOP — show result
        # ─────────────────────────────────────────
        # 1 dramatic pause on winning slot
        wheel_art = build_wheel(win_idx)
        embed = discord.Embed(
            title="🛑 Wheel Ruk Gayi!",
            description=f"{wheel_art}\n**Bet:** {self.bet:,} OwO | 🎯 Calculating...",
            color=discord.Color.blurple()
        )
        embed.set_footer(text="✨ Result aa raha hai...")
        await interaction.edit_original_response(content=None, embed=embed, view=None)
        await asyncio.sleep(1.2)

        # ─────────────────────────────────────────
        # PHASE 4: Show result embed
        # ─────────────────────────────────────────
        if is_jackpot:
            winnings = JACKPOT_AMOUNT
            profit = winnings - self.bet
            res = update_user_balance(view.user_id, profit, xp_change=500)
            level_msg = f"\n🎊 **LEVEL UP!** Level {res['level']}! Bonus +{res['reward']:,} OwO!" if res["leveled_up"] else ""

            embed = discord.Embed(
                title="🏆🎉 JACKPOT! 1,000,000 OwO!!!",
                description=(
                    f"{wheel_art}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🎊 **EK MILLION OwO CASH JEETA!** 🎊\n"
                    f"Bet: **{self.bet:,} OwO** → JACKPOT: **+{JACKPOT_AMOUNT:,} OwO**{level_msg}\n"
                    f"💰 **Naya Balance: {res['cash']:,} OwO**"
                ),
                color=discord.Color.gold()
            )
            embed.set_footer(text="🏆 LEGENDARY JACKPOT! Congratulations! 🎉🎉🎉")

        elif label == "💀 BANKRUPT":
            res = update_user_balance(view.user_id, -self.bet, xp_change=5)
            refill_msg = "\n✨ **Unlimited OwO Protection:** +1,00,000 OwO Cash auto-refill ho gaya!" if res["auto_refilled"] else ""

            embed = discord.Embed(
                title="💀 BANKRUPT! Ohhh Nooo!",
                description=(
                    f"{wheel_art}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"💀 **BANKRUPT aa gaya!**\n"
                    f"Aap **{self.bet:,} OwO Cash** haar gaye!{refill_msg}\n"
                    f"💰 **Naya Balance: {res['cash']:,} OwO**"
                ),
                color=discord.Color.red()
            )
            embed.set_footer(text="😢 Bad luck! Dobara try karo — owo spin 1000")

        elif multiplier == 0:
            small_win = 50
            res = update_user_balance(view.user_id, small_win - self.bet, xp_change=5)
            refill_msg = "\n✨ **Unlimited OwO:** Auto +1,00,000 OwO Cash!" if res["auto_refilled"] else ""

            embed = discord.Embed(
                title="🔸 Tiny Win!",
                description=(
                    f"{wheel_art}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔸 **50 OwO mila — thoda toh sahi!**\n"
                    f"Net: **{small_win - self.bet:+,} OwO**{refill_msg}\n"
                    f"💰 **Naya Balance: {res['cash']:,} OwO**"
                ),
                color=discord.Color.orange()
            )
            embed.set_footer(text="Chalo thoda toh mila! Dobara spin karo 🎡")

        else:
            total_payout = self.bet * multiplier
            profit = total_payout - self.bet
            res = update_user_balance(view.user_id, profit, xp_change=multiplier * 5)
            level_msg = f"\n🎊 **LEVEL UP!** Level {res['level']}! Bonus +{res['reward']:,} OwO!" if res["leveled_up"] else ""

            win_color = discord.Color.green() if multiplier < 50 else discord.Color.gold()
            embed = discord.Embed(
                title=f"🎡 Spin & Win — {label} 🎉",
                description=(
                    f"{wheel_art}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🎁 **{multiplier}x Multiplier!**\n"
                    f"Bet: {self.bet:,} OwO → Payout: **{total_payout:,} OwO** (+{profit:,}){level_msg}\n"
                    f"💰 **Naya Balance: {res['cash']:,} OwO**"
                ),
                color=win_color
            )
            embed.set_footer(text=f"🎉 {multiplier}x win! Maza aa gaya! | owo spin se dobara khao")

        await interaction.edit_original_response(content=None, embed=embed, view=None)

class SpinView(discord.ui.View):
    def __init__(self, user_id, bet):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.bet = bet
        self.add_item(SpinButton(bet))

@bot.command(name="spin", aliases=["spinwin", "sw", "wheel"])
async def owo_spin(ctx, bet: str = "1000"):
    """Spin & Win game — jackpot is 1,000,000 OwO Cash!"""
    bet_amount = parse_bet_amount(ctx.author.id, bet)
    if bet_amount is None or bet_amount <= 0:
        return await ctx.send("❌ Galat bet amount! Kripya valid number, `all`, ya `half` daalein (e.g. `1000`, `50k`, `all`).")

    user_data = get_user(ctx.author.id)
    if user_data["cash"] < bet_amount:
        return await ctx.send(f"❌ Aapke paas itna OwO Cash nahi hai! Balance: **{user_data['cash']:,} OwO**")

    segments_display = "\n".join(
        f"{'🏆' if s[3] else '•'} **{s[0]}** — weight {s[2]}"
        for s in SPIN_SEGMENTS
    )

    view = SpinView(user_id=ctx.author.id, bet=bet_amount)
    embed = discord.Embed(
        title="🎡 OwO Spin & Win!",
        description=(
            f"Player: {ctx.author.mention}\n"
            f"Bet: **{bet_amount:,} OwO Cash**\n\n"
            f"**Possible Prizes:**\n"
            f"💀 BANKRUPT | 🔸 50 OwO | 🎁 2x–100x | 🌟 500x\n"
            f"🏆 **JACKPOT = 1,00,000 OwO!!!**\n\n"
            f"Neeche **SPIN** dabao!"
        ),
        color=discord.Color.purple()
    )
    embed.set_footer(text="Jackpot Odds: 1 in 100 | Good Luck! 🍀")
    await ctx.send(embed=embed, view=view)

# ----------------- CHECK / INFO COMMANDS -----------------

import time
import datetime

@bot.command(name="ping", aliases=["status", "online"])
async def owo_ping(ctx):
    """Bot ka status aur latency check karo"""
    latency = round(bot.latency * 1000)
    emoji = "🟢" if latency < 100 else ("🟡" if latency < 200 else "🔴")
    embed = discord.Embed(
        title="🏓 OwO Bot — Pong!",
        color=discord.Color.green()
    )
    embed.add_field(name="📡 Bot Status", value="🟢 **Online & Ready!**", inline=True)
    embed.add_field(name="⚡ Latency", value=f"{emoji} **{latency}ms**", inline=True)
    embed.add_field(name="🤖 Bot Name", value=f"**{bot.user.name}**", inline=True)
    embed.set_footer(text="OwO Bot chal raha hai! Khelo aur OwO kamao! 🎮")
    await ctx.send(embed=embed)

@bot.command(name="games", aliases=["gamelist", "gl", "game"])
async def owo_games(ctx):
    """Saare available games ki list aur rules dekho"""
    embed = discord.Embed(
        title="🎮 OwO Bot — Saare Games ki Poori List",
        description="Yeh sab games available hain aur OwO Cash se khele ja sakte hain!",
        color=discord.Color.purple()
    )
    embed.add_field(
        name="🪙 1. Coinflip (Head & Tails)",
        value=(
            "**Command:** `owo coinflip <h/t> <bet>` ya `owo cf h 500`\n"
            "**Kaise Khelo:** Heads ya Tails choose karo. Sahi hue toh 2x bet milega!\n"
            "**Win:** `+bet` | **Lose:** `-bet`\n"
            "**XP:** Win pe +20, Lose pe +5"
        ),
        inline=False
    )
    embed.add_field(
        name="💎 2. Diamond & Mines",
        value=(
            "**Command:** `owo mines <bet> [bombs]` (Default bombs: 3)\n"
            "**Kaise Khelo:** 4×4 grid mein tiles click karo. Har diamond se multiplier badhe.\n"
            "**Multiplier:** 1.4x → 1.8x → 2.2x → ... jitne zyada diamonds utna bada\n"
            "**Cash Out:** Jab man kare tab `Cash Out` dabao!\n"
            "**Risk:** Bomb click = sab kuch kho do 💣"
        ),
        inline=False
    )
    embed.add_field(
        name="🎡 3. Roulette",
        value=(
            "**Command:** `owo roulette <option> <bet>`\n"
            "**Options & Payouts:**\n"
            "• `red` / `black` → **2x payout**\n"
            "• `even` / `odd` → **2x payout**\n"
            "• `green` → **14x payout** (sirf number 0)\n"
            "• `0` to `36` (exact number) → **36x payout**"
        ),
        inline=False
    )
    embed.add_field(
        name="🎰 4. Slot Machine",
        value=(
            "**Command:** `owo slots <bet>`\n"
            "**Symbols:** 🍒🍋🍇🔔⭐💎7️⃣\n"
            "**Payouts:**\n"
            "• Any 2 same → **2x** | Any 3 same → **5x**\n"
            "• ⭐⭐⭐ → **7x** | 💎💎💎 → **10x** | 7️⃣7️⃣7️⃣ → **20x JACKPOT**"
        ),
        inline=False
    )
    embed.add_field(
        name="🎡 5. Spin & Win ⭐ (JACKPOT!)",
        value=(
            "**Command:** `owo spin <bet>`\n"
            "**Prizes:** 💀 Bankrupt | 🔸 50 OwO | 🎁 2x/3x/5x/10x/20x/50x/100x | 🌟 500x\n"
            "🏆 **JACKPOT = 1,000,000 OwO Cash!!** (Odds: 1 in 100)\n"
            "**Interactive button UI** ke saath animated spin!"
        ),
        inline=False
    )
    embed.set_footer(text="💡 Tip: 'owo demo <game>' se free mein try karo! | 'owo rules <game>' se detail dekhein")
    await ctx.send(embed=embed)

@bot.command(name="rules", aliases=["rule", "info", "gameinfo"])
async def owo_rules(ctx, game: str = None):
    """Kisi specific game ke rules aur payouts detail mein dekho"""
    if not game:
        return await ctx.send(
            "❓ **Usage:** `owo rules <game>`\n"
            "**Games:** `coinflip` | `mines` | `roulette` | `slots` | `spin`\n"
            "Example: `owo rules spin`"
        )

    game = game.lower()

    if game in ["coinflip", "cf", "flip", "headortails", "ht"]:
        embed = discord.Embed(title="🪙 Coinflip — Full Rules", color=discord.Color.yellow())
        embed.add_field(name="📌 Command", value="`owo coinflip <heads/h OR tails/t> <bet>`", inline=False)
        embed.add_field(name="🎯 Objective", value="Coin flip ka result predict karo!", inline=False)
        embed.add_field(name="💰 Payouts", value="✅ Sahi predict: **+bet (2x total)** \n❌ Galat: **-bet**", inline=False)
        embed.add_field(name="📊 Odds", value="50% Win / 50% Lose (fair coin!)", inline=False)
        embed.add_field(name="✨ XP Reward", value="Win: +20 XP | Lose: +5 XP", inline=False)

    elif game in ["mines", "mine", "diamond"]:
        embed = discord.Embed(title="💎 Diamond & Mines — Full Rules", color=discord.Color.blue())
        embed.add_field(name="📌 Command", value="`owo mines <bet> [bombs 1-8]`", inline=False)
        embed.add_field(name="🎯 Objective", value="4×4 grid (16 tiles) mein diamonds dhundo, bombs se bachte raho!", inline=False)
        embed.add_field(
            name="💰 Multiplier System",
            value=(
                "1st diamond: **1.4x**\n2nd: **1.8x**\n3rd: **2.2x**\n"
                "4th: **2.6x** ... aur aage badhta jata hai\n"
                "Formula: `1.0 + (diamonds × 0.4)`"
            ),
            inline=False
        )
        embed.add_field(name="💣 Bombs", value="Jitne zyada bombs, utna zyada risk aur reward!", inline=False)
        embed.add_field(name="🛑 Cash Out", value="`Cash Out` button dabao jab bhi nikalna ho — safe payout milega!", inline=False)

    elif game in ["roulette", "roul", "rl"]:
        embed = discord.Embed(title="🎡 Roulette — Full Rules", color=discord.Color.red())
        embed.add_field(name="📌 Command", value="`owo roulette <option> <bet>`", inline=False)
        embed.add_field(
            name="🎯 Options & Payouts",
            value=(
                "🔴 `red` → **2x** (18/37 numbers)\n"
                "⚫ `black` → **2x** (18/37 numbers)\n"
                "🟢 `green` → **14x** (only number 0)\n"
                "🔢 `even` → **2x** (1,3,5,...)\n"
                "🔢 `odd` → **2x** (2,4,6,...)\n"
                "🎯 Exact number 0-36 → **36x**"
            ),
            inline=False
        )
        embed.add_field(name="📊 House Edge", value="European style (0-36), 37 total numbers", inline=False)

    elif game in ["slots", "slot", "s"]:
        embed = discord.Embed(title="🎰 Slot Machine — Full Rules", color=discord.Color.gold())
        embed.add_field(name="📌 Command", value="`owo slots <bet>`", inline=False)
        embed.add_field(name="🎲 Symbols", value="🍒 🍋 🍇 🔔 ⭐ 💎 7️⃣ (7 symbols, equal chance each)", inline=False)
        embed.add_field(
            name="💰 Win Conditions",
            value=(
                "Any **2 same** (pair) → **2x bet**\n"
                "Any **3 same** → **5x bet**\n"
                "⭐⭐⭐ → **7x bet**\n"
                "💎💎💎 → **10x bet**\n"
                "7️⃣7️⃣7️⃣ → **20x bet JACKPOT!**"
            ),
            inline=False
        )

    elif game in ["spin", "spinwin", "sw", "wheel"]:
        embed = discord.Embed(title="🎡 Spin & Win — Full Rules", color=discord.Color.purple())
        embed.add_field(name="📌 Command", value="`owo spin <bet>`", inline=False)
        embed.add_field(name="🎯 How it Works", value="Button dabao, wheel spin hoti hai, prize milta hai!", inline=False)
        embed.add_field(
            name="🏆 All Prizes & Odds",
            value=(
                "💀 **BANKRUPT** → Bet kho do *(8% chance)*\n"
                "🔸 **50 OwO** → Thoda milta hai *(10% chance)*\n"
                "🎁 **2x** → *(20% chance)*\n"
                "🎁 **3x** → *(18% chance)*\n"
                "🎁 **5x** → *(14% chance)*\n"
                "🎁 **10x** → *(10% chance)*\n"
                "🎁 **20x** → *(8% chance)*\n"
                "🎁 **50x** → *(5% chance)*\n"
                "🎁 **100x** → *(4% chance)*\n"
                "🌟 **500x** → *(2% chance)*\n"
                "🏆 **JACKPOT = 1,000,000 OwO!!!** → *(1% chance)*"
            ),
            inline=False
        )
        embed.add_field(name="🎁 Jackpot", value="**1,000,000 (10 Lakh) OwO Cash** — Fixed Jackpot!", inline=False)

    else:
        return await ctx.send(
            f"❓ `{game}` game nahi pehchana!\n"
            "**Available games:** `coinflip` | `mines` | `roulette` | `slots` | `spin`"
        )

    embed.set_footer(text="OwO Bot | Unlimited OwO Cash — Kabhi bhi khalo! 🎮")
    await ctx.send(embed=embed)

@bot.command(name="demo", aliases=["try", "practice", "free"])
async def owo_demo(ctx, game: str = None):
    """Koi bhi game FREE mein try karo — koi bet nahi, koi loss nahi!"""
    if not game:
        return await ctx.send(
            "❓ **Usage:** `owo demo <game>`\n"
            "**Games:** `coinflip` | `slots` | `spin` | `roulette`\n"
            "Example: `owo demo spin`\n"
            "*(Demo mein koi actual cash nahi lagta — sirf try karo!)*"
        )

    game = game.lower()
    embed = discord.Embed(color=discord.Color.blurple())
    embed.set_footer(text="🎮 DEMO MODE — Koi actual cash nahi kata/mila! Sirf preview hai.")

    if game in ["coinflip", "cf", "flip"]:
        outcome = random.choice(["HEADS 🪙", "TAILS 💿"])
        embed.title = "🪙 [DEMO] Coinflip"
        embed.description = (
            f"Agar aapne HEADS choose kiya hota:\n\n"
            f"Coin result: **{outcome}**\n"
            f"{'✅ JEETE (2x bet mila hota)!' if 'HEADS' in outcome else '❌ HAARE (-bet katta)'}\n\n"
            f"*Real mein khelne ke liye:* `owo coinflip h 1000`"
        )

    elif game in ["slots", "slot"]:
        symbols = ["🍒", "🍋", "🍇", "🔔", "⭐", "💎", "7️⃣"]
        s1, s2, s3 = random.choice(symbols), random.choice(symbols), random.choice(symbols)
        if s1 == s2 == s3:
            result = f"🎰 **TRIPLE! [ {s1} | {s2} | {s3} ]** — 5x ya zyada jeete!"
        elif s1 == s2 or s2 == s3 or s1 == s3:
            result = f"🎰 **PAIR! [ {s1} | {s2} | {s3} ]** — 2x jeete!"
        else:
            result = f"🎰 **NO MATCH [ {s1} | {s2} | {s3} ]** — Haare."
        embed.title = "🎰 [DEMO] Slot Machine"
        embed.description = f"{result}\n\n*Real mein khelne ke liye:* `owo slots 1000`"

    elif game in ["spin", "spinwin", "wheel"]:
        seg = spin_wheel()
        label, mult, _, is_jp = seg
        if is_jp:
            result_text = "🏆 **JACKPOT!! 1,000,000 OwO Cash milta!!**"
        elif label == "💀 BANKRUPT":
            result_text = "💀 **BANKRUPT — Bet doob jaati!**"
        elif mult == 0:
            result_text = "🔸 **50 OwO milte (tiny win)**"
        else:
            result_text = f"🎁 **{label} — Bet ka {mult}x milta!**"
        embed.title = "🎡 [DEMO] Spin & Win"
        embed.description = (
            f"Wheel ruki: **{label}**\n"
            f"{result_text}\n\n"
            f"*Real mein khelne ke liye:* `owo spin 1000`"
        )

    elif game in ["roulette", "roul"]:
        num = random.randint(0, 36)
        red_numbers = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
        color = "🟢 GREEN" if num == 0 else ("🔴 RED" if num in red_numbers else "⚫ BLACK")
        embed.title = "🎡 [DEMO] Roulette"
        embed.description = (
            f"Wheel landed on: **{num} — {color}**\n\n"
            f"Agar aapne `red` bet kiya hota: {'✅ 2x jeete!' if '🔴' in color else '❌ Haare'}\n"
            f"Agar `{num}` exact bet kiya hota: ✅ **36x payout!**\n\n"
            f"*Real mein khelne ke liye:* `owo roulette red 1000`"
        )
    else:
        return await ctx.send(
            f"❓ `{game}` game nahi pehchana!\n"
            "**Demo available for:** `coinflip` | `slots` | `spin` | `roulette`"
        )

    await ctx.send(embed=embed)

@bot.command(name="profile", aliases=["prof", "me", "myinfo"])
async def owo_profile(ctx, member: discord.Member = None):
    """Apna ya kisi aur ka full OwO profile card dekho"""
    target = member or ctx.author
    user_data = get_user(target.id)
    
    xp_needed = user_data["level"] * 100
    xp_percent = int((user_data["xp"] / xp_needed) * 20)
    xp_bar = "█" * xp_percent + "░" * (20 - xp_percent)
    
    # Rank from DB
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users WHERE cash > ?", (user_data["cash"],))
    rank = cursor.fetchone()[0] + 1
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    conn.close()

    # Title based on level or custom equipped title
    default_title = "🌱 OwO Newbie"
    if user_data["level"] >= 50:
        default_title = "👑 OwO Legend"
    elif user_data["level"] >= 30:
        default_title = "🏆 OwO Master"
    elif user_data["level"] >= 20:
        default_title = "💎 OwO Diamond"
    elif user_data["level"] >= 10:
        default_title = "⭐ OwO Star"
    elif user_data["level"] >= 5:
        default_title = "🎖️ OwO Veteran"

    title_badge = user_data.get("active_title") or default_title
    equipped_badge = user_data.get("active_badge") or "None"

    tier_name, tier_desc = get_tier_info(user_data["elo"])
    total_matches = user_data["wins"] + user_data["losses"]
    winrate = round((user_data["wins"] / total_matches * 100), 1) if total_matches > 0 else 0.0

    embed = discord.Embed(
        title=f"👤 {target.display_name}'s OwO Profile",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="🏅 Title", value=f"**{title_badge}**", inline=True)
    embed.add_field(name="🔰 Equipped Badge", value=f"**{equipped_badge}**", inline=True)
    embed.add_field(name="⚔️ Competitive Rank", value=f"**{tier_name}** ({user_data['elo']} ELO)", inline=True)
    embed.add_field(name="💵 OwO Cash", value=f"**{user_data['cash']:,} OwO**", inline=True)
    embed.add_field(name="🏆 Wealth Rank", value=f"**#{rank}** / {total_users}", inline=True)
    embed.add_field(name="📊 Win/Loss", value=f"**{user_data['wins']}W / {user_data['losses']}L** ({winrate}%)", inline=True)
    embed.add_field(name="⭐ Level", value=f"**Level {user_data['level']}**", inline=True)
    embed.add_field(name="✨ XP Progress", value=f"**{user_data['xp']} / {xp_needed} XP**", inline=True)
    embed.add_field(name="📊 XP Bar", value=f"`[{xp_bar}]`", inline=False)
    next_reward = (user_data["level"] + 1) * 1000
    embed.add_field(name="🎁 Level-Up Reward", value=f"Next level pe: **+{next_reward:,} OwO Cash**", inline=False)
    embed.set_footer(text=f"Tier: {tier_desc} | owo rps / owo battle / owo squad khelo!")
    await ctx.send(embed=embed)

@bot.command(name="checkgame", aliases=["cg", "verify", "botcheck"])
async def owo_checkgame(ctx):
    """Bot ke saare games ek saath quick check karo"""
    # Quick simulation of all games
    symbols = ["🍒", "🍋", "🍇", "🔔", "⭐", "💎", "7️⃣"]
    s1, s2, s3 = random.choice(symbols), random.choice(symbols), random.choice(symbols)
    slot_result = "WIN 🎉" if (s1==s2 or s2==s3 or s1==s3) else "MISS ❌"
    
    coin = random.choice(["HEADS 🪙", "TAILS 💿"])
    
    roul_num = random.randint(0, 36)
    red_numbers = {1,3,5,7,9,12,14,16,18,19,21,23,25,27,30,32,34,36}
    roul_color = "🟢" if roul_num == 0 else ("🔴" if roul_num in red_numbers else "⚫")
    
    spin_seg = spin_wheel()
    
    user_data = get_user(ctx.author.id)
    
    embed = discord.Embed(
        title="✅ OwO Bot — Full System Check",
        description="Saare systems aur games test ho rahe hain...",
        color=discord.Color.green()
    )
    embed.add_field(name="🤖 Bot Status", value="🟢 Online", inline=True)
    embed.add_field(name="🗄️ Database", value="🟢 Connected", inline=True)
    embed.add_field(name="⚡ Latency", value=f"🟢 {round(bot.latency*1000)}ms", inline=True)
    embed.add_field(
        name="💵 Your Balance",
        value=f"**{user_data['cash']:,} OwO** | Level {user_data['level']}",
        inline=False
    )
    embed.add_field(
        name="🎮 Game Status",
        value=(
            f"🪙 Coinflip: 🟢 Working → Sample: **{coin}**\n"
            f"🎰 Slots: 🟢 Working → `[{s1}|{s2}|{s3}]` **{slot_result}**\n"
            f"🎡 Roulette: 🟢 Working → **{roul_num} {roul_color}**\n"
            f"💎 Mines: 🟢 Working → Interactive Buttons Active\n"
            f"🎡 Spin & Win: 🟢 Working → Sample: **{spin_seg[0]}**\n"
            f"🌟 Jackpot System: 🟢 Active (1,000,000 OwO)"
        ),
        inline=False
    )
    embed.add_field(
        name="💫 Unlimited OwO System",
        value="🟢 Auto-Refill Active → Khatam hone pe **+1,00,000 OwO** milega",
        inline=False
    )
    embed.set_footer(text="Sab kuch theek chal raha hai! | owo games se poori list dekho 🎮")
    await ctx.send(embed=embed)

# ----------------- OWO STORE & INVENTORY -----------------

STORE_ITEMS = {
    # Badges
    "vip": {
        "id": "vip",
        "name": "VIP Badge",
        "type": "badge",
        "icon": "💎",
        "price": 250000,
        "description": "Show off your elite VIP status on your profile card."
    },
    "crown": {
        "id": "crown",
        "name": "Golden Crown",
        "type": "badge",
        "icon": "👑",
        "price": 500000,
        "description": "Exclusive crown badge for top rollers."
    },
    "fire": {
        "id": "fire",
        "name": "Fire Streak",
        "type": "badge",
        "icon": "🔥",
        "price": 100000,
        "description": "A hot flame badge for lucky players."
    },
    "ghost": {
        "id": "ghost",
        "name": "Phantom Ghost",
        "type": "badge",
        "icon": "👻",
        "price": 150000,
        "description": "Mysterious ghost badge to flex in server."
    },
    # Custom Titles
    "title_billionaire": {
        "id": "title_billionaire",
        "name": "OwO Billionaire",
        "type": "title",
        "icon": "💵",
        "price": 1000000,
        "description": "Equip the prestigious '💸 OwO Billionaire' title."
    },
    "title_casino_king": {
        "id": "title_casino_king",
        "name": "Casino King",
        "type": "title",
        "icon": "🎰",
        "price": 750000,
        "description": "Equip the royal '🎰 Casino King' title."
    },
    "title_lucky": {
        "id": "title_lucky",
        "name": "Lucky Legend",
        "type": "title",
        "icon": "🍀",
        "price": 400000,
        "description": "Equip the blessed '🍀 Lucky Legend' title."
    },
    "title_demon": {
        "id": "title_demon",
        "name": "High Roller",
        "type": "title",
        "icon": "⚡",
        "price": 300000,
        "description": "Equip the energetic '⚡ High Roller' title."
    },
    # Weapons for Dragon Raids
    "sword_dragon": {
        "id": "sword_dragon",
        "name": "Dragon Slayer Greatsword",
        "type": "weapon",
        "icon": "🗡️",
        "price": 350000,
        "bonus_dmg": 45,
        "description": "Boosts Slash attack by +45 DMG in Dragon Raids!"
    },
    "staff_void": {
        "id": "staff_void",
        "name": "Void Archmage Staff",
        "type": "weapon",
        "icon": "🔮",
        "price": 500000,
        "bonus_dmg": 65,
        "description": "Empowers Arcane Magic by +65 CRIT DMG in Dragon Raids!"
    },
    "hammer_titan": {
        "id": "hammer_titan",
        "name": "Titan Thunder Hammer",
        "type": "weapon",
        "icon": "🔨",
        "price": 750000,
        "bonus_dmg": 90,
        "description": "Massive Titan weapon: +90 DMG to all strikes in Dragon Raids!"
    },
    "scythe_reaper": {
        "id": "scythe_reaper",
        "name": "Mythic Soul Scythe",
        "type": "weapon",
        "icon": "⚔️",
        "price": 1200000,
        "bonus_dmg": 130,
        "description": "Legendary weapon: grants +130 DMG & ultimate dragon slaying power!"
    },
    # Collectibles / Flex
    "ring": {
        "id": "ring",
        "name": "Diamond Ring",
        "type": "collectible",
        "icon": "💍",
        "price": 200000,
        "description": "A sparkling diamond ring for your luxury collection."
    },
    "trophy": {
        "id": "trophy",
        "name": "Golden Trophy",
        "type": "collectible",
        "icon": "🏆",
        "price": 600000,
        "description": "A glorious golden trophy for the hall of fame."
    },
    "rocket": {
        "id": "rocket",
        "name": "OwO Spaceship",
        "type": "collectible",
        "icon": "🚀",
        "price": 2000000,
        "description": "Fly to the moon! The ultimate OwO flex item."
    }
}

class StoreSelect(discord.ui.Select):
    def __init__(self, user_id):
        self.user_id = user_id
        options = []
        for k, v in STORE_ITEMS.items():
            options.append(
                discord.SelectOption(
                    label=f"{v['name']} ({v['price']:,} OwO)",
                    value=k,
                    emoji=v["icon"],
                    description=v["description"][:100]
                )
            )
        super().__init__(placeholder="🛒 Store se ek item khareedne ke liye chunein...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Yeh aapka store menu nahi hai!", ephemeral=True)

        item_id = self.values[0]
        item = STORE_ITEMS[item_id]

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM inventory WHERE user_id = ? AND item_id = ?", (interaction.user.id, item_id))
        already_owned = cursor.fetchone()

        if already_owned:
            conn.close()
            return await interaction.response.send_message(f"❌ Aapke paas **{item['icon']} {item['name']}** pehle se hi inventory mein hai!", ephemeral=True)

        user_data = get_user(interaction.user.id)
        if user_data["cash"] < item["price"]:
            conn.close()
            return await interaction.response.send_message(f"❌ Aapke paas itna OwO Cash nahi hai! Price: **{item['price']:,} OwO** | Aapke paas: **{user_data['cash']:,} OwO**", ephemeral=True)

        # Deduct cash & insert inventory
        res = update_user_balance(interaction.user.id, -item["price"])
        cursor.execute(
            "INSERT INTO inventory (user_id, item_id, item_name, item_type, icon) VALUES (?, ?, ?, ?, ?)",
            (interaction.user.id, item_id, item["name"], item["type"], item["icon"])
        )

        # If it's a title, badge or weapon, auto-equip if not set
        if item["type"] == "title" and not user_data.get("active_title"):
            cursor.execute("UPDATE users SET active_title = ? WHERE user_id = ?", (f"{item['icon']} {item['name']}", interaction.user.id))
        elif item["type"] == "badge" and not user_data.get("active_badge"):
            cursor.execute("UPDATE users SET active_badge = ? WHERE user_id = ?", (f"{item['icon']} {item['name']}", interaction.user.id))
        elif item["type"] == "weapon" and not user_data.get("active_weapon"):
            cursor.execute("UPDATE users SET active_weapon = ? WHERE user_id = ?", (item_id, interaction.user.id))

        conn.commit()
        conn.close()

        embed = discord.Embed(
            title="🛍️ Purchase Successful!",
            description=(
                f"Badhai ho {interaction.user.mention}! Aapne **{item['icon']} {item['name']}** khareed liya hai!\n\n"
                f"💵 Price: **{item['price']:,} OwO Cash**\n"
                f"💳 Naya Balance: **{res['cash']:,} OwO**\n\n"
                f"💡 *Apni inventory dekhne ke liye `owo inv` use karein.*\n"
                f"💡 *Equip karne ke liye `owo equip {item_id}` use karein!*"
            ),
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

class StoreView(discord.ui.View):
    def __init__(self, user_id):
        super().__init__(timeout=120)
        self.add_item(StoreSelect(user_id))

@bot.command(name="store", aliases=["shop", "market"])
async def owo_store(ctx):
    """OwO Store — titles, badges aur luxury collectibles khareedein!"""
    user_data = get_user(ctx.author.id)

    embed = discord.Embed(
        title="🏬 Welcome to the OwO Luxury Store 🏬",
        description=(
            f"Player: {ctx.author.mention} | Aapka Cash: **{user_data['cash']:,} OwO**\n"
            f"Neeche drop-down menu se item select karke khareedein!\n"
            f"───────────────────────────────"
        ),
        color=discord.Color.gold()
    )

    badges_text = ""
    titles_text = ""
    weapons_text = ""
    collectibles_text = ""

    for k, v in STORE_ITEMS.items():
        line = f"{v['icon']} **{v['name']}** (`{k}`) — **{v['price']:,} OwO**\n*{v['description']}*\n"
        if v["type"] == "badge":
            badges_text += line
        elif v["type"] == "title":
            titles_text += line
        elif v["type"] == "weapon":
            weapons_text += line
        else:
            collectibles_text += line

    embed.add_field(name="⚔️ Dragon Raid Weapons", value=weapons_text or "None", inline=False)
    embed.add_field(name="🔰 Profile Badges", value=badges_text or "None", inline=False)
    embed.add_field(name="👑 Custom Titles", value=titles_text or "None", inline=False)
    embed.add_field(name="💎 Luxury Collectibles", value=collectibles_text or "None", inline=False)
    embed.set_footer(text="Tip: Khareedne ke liye dropdown use karein ya 'owo buy <item_id>' type karein!")

    view = StoreView(ctx.author.id)
    await ctx.send(embed=embed, view=view)

@bot.command(name="buy")
async def owo_buy(ctx, item_id: str = None):
    """Store se item khareedein: owo buy <item_id>"""
    if not item_id:
        return await ctx.send("❓ **Usage:** `owo buy <item_id>`\nItem IDs dekhne ke liye `owo store` check karein! Example: `owo buy crown`")

    item_id = item_id.lower()
    if item_id not in STORE_ITEMS:
        return await ctx.send(f"❌ `{item_id}` naam ka koi item store mein nahi hai! `owo store` check karein.")

    item = STORE_ITEMS[item_id]
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM inventory WHERE user_id = ? AND item_id = ?", (ctx.author.id, item_id))
    if cursor.fetchone():
        conn.close()
        return await ctx.send(f"❌ Aapke paas **{item['icon']} {item['name']}** pehle se hi hai! `owo inv` se dekhein.")

    user_data = get_user(ctx.author.id)
    if user_data["cash"] < item["price"]:
        conn.close()
        return await ctx.send(f"❌ Aapke paas paryapt cash nahi hai! Price: **{item['price']:,} OwO** | Balance: **{user_data['cash']:,} OwO**")

    res = update_user_balance(ctx.author.id, -item["price"])
    cursor.execute(
        "INSERT INTO inventory (user_id, item_id, item_name, item_type, icon) VALUES (?, ?, ?, ?, ?)",
        (ctx.author.id, item_id, item["name"], item["type"], item["icon"])
    )

    if item["type"] == "title" and not user_data.get("active_title"):
        cursor.execute("UPDATE users SET active_title = ? WHERE user_id = ?", (f"{item['icon']} {item['name']}", ctx.author.id))
    elif item["type"] == "badge" and not user_data.get("active_badge"):
        cursor.execute("UPDATE users SET active_badge = ? WHERE user_id = ?", (f"{item['icon']} {item['name']}", ctx.author.id))
    elif item["type"] == "weapon" and not user_data.get("active_weapon"):
        cursor.execute("UPDATE users SET active_weapon = ? WHERE user_id = ?", (item_id, ctx.author.id))

    conn.commit()
    conn.close()

    embed = discord.Embed(
        title="🛍️ Item Purchased!",
        description=(
            f"🎉 Badhai ho {ctx.author.mention}! Aapne **{item['icon']} {item['name']}** khareed liya!\n\n"
            f"💵 Cost: **{item['price']:,} OwO Cash**\n"
            f"💳 Naya Balance: **{res['cash']:,} OwO**\n\n"
            f"💡 *Equip karne ke liye: `owo equip {item_id}`*"
        ),
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)

@bot.command(name="inventory", aliases=["inv", "bag", "items"])
async def owo_inventory(ctx, member: discord.Member = None):
    """Apni ya kisi user ki inventory dekhein"""
    target = member or ctx.author
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT item_id, item_name, item_type, icon, purchased_at FROM inventory WHERE user_id = ?", (target.id,))
    rows = cursor.fetchall()
    conn.close()

    user_data = get_user(target.id)

    embed = discord.Embed(
        title=f"🎒 {target.display_name}'s OwO Inventory",
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=target.display_avatar.url)

    if not rows:
        embed.description = f"Inventory bilkul khaali hai! `owo store` se shopping karein!"
        return await ctx.send(embed=embed)

    badges = []
    titles = []
    weapons = []
    collectibles = []

    for item_id, name, itype, icon, pdate in rows:
        line = f"{icon} **{name}** (`{item_id}`)"
        if itype == "badge":
            badges.append(line)
        elif itype == "title":
            titles.append(line)
        elif itype == "weapon":
            bonus = STORE_ITEMS.get(item_id, {}).get("bonus_dmg", 0)
            weapons.append(f"{icon} **{name}** (`{item_id}`) — *+{bonus} DMG*")
        else:
            collectibles.append(line)

    if weapons:
        embed.add_field(name="🗡️ Raid Weapons", value="\n".join(weapons), inline=False)
    if badges:
        embed.add_field(name="🔰 Badges", value="\n".join(badges), inline=False)
    if titles:
        embed.add_field(name="👑 Titles", value="\n".join(titles), inline=False)
    if collectibles:
        embed.add_field(name="💎 Collectibles", value="\n".join(collectibles), inline=False)

    equipped_weapon_name = "Default Dagger (+0 DMG)"
    if user_data.get("active_weapon"):
        w_item = STORE_ITEMS.get(user_data["active_weapon"])
        if w_item:
            equipped_weapon_name = f"{w_item['icon']} {w_item['name']} (+{w_item.get('bonus_dmg', 0)} DMG)"

    equipped_info = (
        f"🗡️ Weapon: **{equipped_weapon_name}**\n"
        f"🏅 Title: **{user_data.get('active_title') or 'Default'}**\n"
        f"🔰 Badge: **{user_data.get('active_badge') or 'None'}**"
    )
    embed.add_field(name="✨ Currently Equipped", value=equipped_info, inline=False)
    embed.set_footer(text="Equip karne ke liye: owo equip <item_id> | Unequip ke liye: owo unequip <weapon/title/badge>")
    await ctx.send(embed=embed)

@bot.command(name="equip", aliases=["use", "wear"])
async def owo_equip(ctx, item_id: str = None):
    """Inventory se weapon, title ya badge equip karein: owo equip <item_id>"""
    if not item_id:
        return await ctx.send("❓ **Usage:** `owo equip <item_id>`\nApni items dekhne ke liye `owo inv` check karein!")

    item_id = item_id.lower()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT item_name, item_type, icon FROM inventory WHERE user_id = ? AND item_id = ?", (ctx.author.id, item_id))
    row = cursor.fetchone()

    if not row:
        conn.close()
        return await ctx.send(f"❌ Aapke paas `{item_id}` item nahi hai! `owo store` se khareedein.")

    name, itype, icon = row
    full_str = f"{icon} {name}"

    if itype == "title":
        cursor.execute("UPDATE users SET active_title = ? WHERE user_id = ?", (full_str, ctx.author.id))
        conn.commit()
        conn.close()
        await ctx.send(f"✅ Aapne **{full_str}** title successfully equip kar liya! Ab yeh `owo profile` par dikhega.")
    elif itype == "badge":
        cursor.execute("UPDATE users SET active_badge = ? WHERE user_id = ?", (full_str, ctx.author.id))
        conn.commit()
        conn.close()
        await ctx.send(f"✅ Aapne **{full_str}** badge successfully equip kar liya! Ab yeh `owo profile` par dikhega.")
    elif itype == "weapon":
        cursor.execute("UPDATE users SET active_weapon = ? WHERE user_id = ?", (item_id, ctx.author.id))
        conn.commit()
        conn.close()
        bonus = STORE_ITEMS.get(item_id, {}).get("bonus_dmg", 0)
        await ctx.send(f"🗡️ Aapne **{full_str}** (+{bonus} DMG) equip kar liya! Dragon raids mein aapka attack significantly boost hoga! 🔥")
    else:
        conn.close()
        await ctx.send(f"ℹ️ **{full_str}** ek collectible item hai, isse direct inventory (`owo inv`) mein flex kiya ja sakta hai!")

@bot.command(name="unequip", aliases=["remove"])
async def owo_unequip(ctx, target_type: str = None):
    """Equipped weapon, title ya badge hatayein: owo unequip weapon / title / badge"""
    if not target_type or target_type.lower() not in ["title", "badge", "weapon"]:
        return await ctx.send("❓ **Usage:** `owo unequip weapon` / `owo unequip title` / `owo unequip badge`")

    target_type = target_type.lower()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if target_type == "title":
        cursor.execute("UPDATE users SET active_title = NULL WHERE user_id = ?", (ctx.author.id,))
        conn.commit()
        conn.close()
        await ctx.send("✅ Title unequip kar diya gaya hai! Default level title wapas active ho gaya.")
    elif target_type == "weapon":
        cursor.execute("UPDATE users SET active_weapon = NULL WHERE user_id = ?", (ctx.author.id,))
        conn.commit()
        conn.close()
        await ctx.send("✅ Weapon unequip kar diya gaya hai! Default dagger active ho gaya.")
    else:
        cursor.execute("UPDATE users SET active_badge = NULL WHERE user_id = ?", (ctx.author.id,))
        conn.commit()
        conn.close()
        await ctx.send("✅ Badge unequip kar diya gaya hai!")

# ----------------- 1v1, DUO & SQUAD COMPETITIVE GAMES -----------------

# 1. 1v1 ROCK PAPER SCISSORS (RPS) DUEL WITH BET & ELO
class RPSButton(discord.ui.Button):
    def __init__(self, choice_name, emoji, custom_id):
        super().__init__(style=discord.ButtonStyle.primary, label=choice_name, emoji=emoji, custom_id=custom_id)
        self.choice_name = choice_name

    async def callback(self, interaction: discord.Interaction):
        view: RPSDuelView = self.view
        uid = interaction.user.id
        if uid not in (view.p1_id, view.p2_id):
            return await interaction.response.send_message("❌ Yeh aapka duel nahi hai!", ephemeral=True)

        if uid == view.p1_id:
            if view.p1_choice:
                return await interaction.response.send_message("❌ Aapne pehle hi apna move select kar liya hai!", ephemeral=True)
            view.p1_choice = self.choice_name
        else:
            if view.p2_choice:
                return await interaction.response.send_message("❌ Aapne pehle hi apna move select kar liya hai!", ephemeral=True)
            view.p2_choice = self.choice_name

        await interaction.response.send_message(f"✅ Aapne **{self.choice_name}** select kiya! Opponent ke move ka intezar...", ephemeral=True)

        # Check if both played
        if view.p1_choice and view.p2_choice:
            await view.resolve_match()

class RPSDuelView(discord.ui.View):
    def __init__(self, ctx, p1, p2, bet):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.p1 = p1
        self.p2 = p2
        self.p1_id = p1.id
        self.p2_id = p2.id
        self.bet = bet
        self.p1_choice = None
        self.p2_choice = None
        self.msg = None

        self.add_item(RPSButton("Rock", "🪨", "rps_rock"))
        self.add_item(RPSButton("Paper", "📄", "rps_paper"))
        self.add_item(RPSButton("Scissors", "✂️", "rps_scissors"))

    async def resolve_match(self):
        for child in self.children:
            child.disabled = True

        import asyncio
        # Animation phase
        anim_frames = [
            "⚔️ **Round 1:** Weapons Clashing... 💥",
            "🪨 vs 📄 vs ✂️ Calculating Strategy... ⚡",
            "🔥 Deciding the Arena Champion... 🏆"
        ]
        for f in anim_frames:
            anim_embed = discord.Embed(
                title="⚔️ 1v1 Duel In Progress! ⚔️",
                description=f"{self.p1.mention} vs {self.p2.mention}\nBet: **{self.bet:,} OwO**\n\n```\n{f}\n```",
                color=discord.Color.gold()
            )
            await self.msg.edit(embed=anim_embed, view=None)
            await asyncio.sleep(0.7)

        c1 = self.p1_choice
        c2 = self.p2_choice
        emojis = {"Rock": "🪨", "Paper": "📄", "Scissors": "✂️"}

        # Win conditions for p1
        if c1 == c2:
            # Draw
            embed = discord.Embed(
                title="🤝 1v1 Duel — DRAW / TIE!",
                description=(
                    f"```\n"
                    f"┌───────────────────────────────┐\n"
                    f"│  {self.p1.display_name[:10]:<10}: {emojis[c1]} {c1:<8}   │\n"
                    f"│  {self.p2.display_name[:10]:<10}: {emojis[c2]} {c2:<8}   │\n"
                    f"│           MATCH TIED!         │\n"
                    f"└───────────────────────────────┘\n"
                    f"```\n"
                    f"Dono players ko unka bet (**{self.bet:,} OwO**) wapas de diya gaya!\n"
                    f"ELO ratings remain unchanged."
                ),
                color=discord.Color.light_grey()
            )
        elif (c1 == "Rock" and c2 == "Scissors") or (c1 == "Paper" and c2 == "Rock") or (c1 == "Scissors" and c2 == "Paper"):
            # P1 Wins
            res1 = update_user_balance(self.p1_id, self.bet, xp_change=50)
            res2 = update_user_balance(self.p2_id, -self.bet, xp_change=15)
            elo1, w1, l1 = update_user_stats(self.p1_id, elo_change=+25, is_win=True)
            elo2, w2, l2 = update_user_stats(self.p2_id, elo_change=-20, is_win=False)
            t1, _ = get_tier_info(elo1)
            t2, _ = get_tier_info(elo2)

            embed = discord.Embed(
                title="🏆 1v1 DUEL VICTORY! 🏆",
                description=(
                    f"```\n"
                    f"┌───────────────────────────────┐\n"
                    f"│  WINNER: {self.p1.display_name[:18]:<18}   │\n"
                    f"│  {emojis[c1]} {c1:<8} BEATS {emojis[c2]} {c2:<8}      │\n"
                    f"└───────────────────────────────┘\n"
                    f"```\n"
                    f"👑 **{self.p1.mention}** won **+{self.bet:,} OwO Cash**! (+25 ELO ⚡ | {t1})\n"
                    f"💀 **{self.p2.mention}** lost **-{self.bet:,} OwO Cash**! (-20 ELO 📉 | {t2})\n\n"
                    f"💳 {self.p1.display_name}'s Balance: **{res1['cash']:,} OwO**\n"
                    f"💳 {self.p2.display_name}'s Balance: **{res2['cash']:,} OwO**"
                ),
                color=discord.Color.green()
            )
        else:
            # P2 Wins
            res2 = update_user_balance(self.p2_id, self.bet, xp_change=50)
            res1 = update_user_balance(self.p1_id, -self.bet, xp_change=15)
            elo2, w2, l2 = update_user_stats(self.p2_id, elo_change=+25, is_win=True)
            elo1, w1, l1 = update_user_stats(self.p1_id, elo_change=-20, is_win=False)
            t2, _ = get_tier_info(elo2)
            t1, _ = get_tier_info(elo1)

            embed = discord.Embed(
                title="🏆 1v1 DUEL VICTORY! 🏆",
                description=(
                    f"```\n"
                    f"┌───────────────────────────────┐\n"
                    f"│  WINNER: {self.p2.display_name[:18]:<18}   │\n"
                    f"│  {emojis[c2]} {c2:<8} BEATS {emojis[c1]} {c1:<8}      │\n"
                    f"└───────────────────────────────┘\n"
                    f"```\n"
                    f"👑 **{self.p2.mention}** won **+{self.bet:,} OwO Cash**! (+25 ELO ⚡ | {t2})\n"
                    f"💀 **{self.p1.mention}** lost **-{self.bet:,} OwO Cash**! (-20 ELO 📉 | {t1})\n\n"
                    f"💳 {self.p2.display_name}'s Balance: **{res2['cash']:,} OwO**\n"
                    f"💳 {self.p1.display_name}'s Balance: **{res1['cash']:,} OwO**"
                ),
                color=discord.Color.green()
            )

        embed.set_footer(text="Rankings dekhne ke liye: owo toprank | owo rank")
        await self.msg.edit(embed=embed, view=None)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.msg:
            try:
                await self.msg.edit(content="⏱️ **Duel Expired!** Dono players ne samay par move nahi chuna.", view=None)
            except:
                pass

@bot.command(name="rps", aliases=["1v1", "duel"])
async def owo_rps_duel(ctx, opponent: discord.Member = None, bet: str = "10000"):
    """1v1 Rock Paper Scissors Duel bet aur ELO rating ke sath!"""
    if not opponent:
        return await ctx.send("❓ **Usage:** `owo rps @opponent <bet>`\nExample: `owo rps @Friend 50000` ya `owo rps @Friend all`")
    if opponent.id == ctx.author.id:
        return await ctx.send("❌ Khud ke sath duel nahi khel sakte!")
    if opponent.bot:
        return await ctx.send("❌ Bots ke sath duel nahi khel sakte!")

    bet_amount = parse_bet_amount(ctx.author.id, bet)
    if bet_amount is None or bet_amount <= 0:
        return await ctx.send("❌ Galat bet amount! Kripya valid number, `all`, ya `half` daalein.")

    p1_data = get_user(ctx.author.id)
    p2_data = get_user(opponent.id)

    if p1_data["cash"] < bet_amount:
        return await ctx.send(f"❌ Aapke paas paryapt OwO Cash nahi hai! Balance: **{p1_data['cash']:,} OwO**")
    if p2_data["cash"] < bet_amount:
        return await ctx.send(f"❌ {opponent.mention} ke paas itna cash nahi hai! Balance: **{p2_data['cash']:,} OwO**")

    view = RPSDuelView(ctx, ctx.author, opponent, bet_amount)
    embed = discord.Embed(
        title="⚔️ 1v1 ARENA DUEL CHALLENGE ⚔️",
        description=(
            f"**Challenger:** {ctx.author.mention}\n"
            f"**Opponent:** {opponent.mention}\n"
            f"💰 Stake Bet: **{bet_amount:,} OwO Cash** each (Winner gets **{bet_amount*2:,} OwO**!)\n"
            f"⚡ ELO at stake: **+25 / -20 ELO**\n\n"
            f"👉 **Dono players neeche ke buttons se apna secret move chunein!**"
        ),
        color=discord.Color.orange()
    )
    embed.set_footer(text="60 seconds time limit | Moves are kept private until both choose!")
    msg = await ctx.send(f"{ctx.author.mention} vs {opponent.mention}", embed=embed, view=view)
    view.msg = msg


# ----------------- DRAGON DUNGEON LEVELS & DIFFICULTY -----------------
DRAGON_LEVELS = {
    1: {
        "name": "Infant Hatchling Wyrm",
        "title": "Level 1: Hatchling",
        "emoji": "🐉",
        "duo_hp": 250,
        "trio_hp": 380,
        "base_min_dmg": 18,
        "base_max_dmg": 35,
        "payout_mult": 1.6,
        "xp": 50,
        "min_level": 1
    },
    2: {
        "name": "Armored Cavern Drake",
        "title": "Level 2: Cavern Drake",
        "emoji": "🐲",
        "duo_hp": 350,
        "trio_hp": 520,
        "base_min_dmg": 25,
        "base_max_dmg": 45,
        "payout_mult": 1.8,
        "xp": 75,
        "min_level": 1
    },
    3: {
        "name": "Ancient Shadow Dragon",
        "title": "Level 3: Shadow Dragon",
        "emoji": "👹",
        "duo_hp": 480,
        "trio_hp": 700,
        "base_min_dmg": 35,
        "base_max_dmg": 60,
        "payout_mult": 2.2,
        "xp": 110,
        "min_level": 3
    },
    4: {
        "name": "Volcanic Inferno Dragon",
        "title": "Level 4: Inferno Dragon",
        "emoji": "🔥",
        "duo_hp": 650,
        "trio_hp": 950,
        "base_min_dmg": 45,
        "base_max_dmg": 75,
        "payout_mult": 2.8,
        "xp": 160,
        "min_level": 5
    },
    5: {
        "name": "Mythic Astral Cataclysm God",
        "title": "Level 5: Astral Dragon God",
        "emoji": "🌌",
        "duo_hp": 900,
        "trio_hp": 1350,
        "base_min_dmg": 60,
        "base_max_dmg": 95,
        "payout_mult": 3.8,
        "xp": 250,
        "min_level": 10
    }
}

# 2. DUO & TRIO CO-OP DUNGEON BOSS RAID WITH VISUAL ANIMATIONS
class DungeonRaidView(discord.ui.View):
    def __init__(self, ctx, players, bet, mode_title="DUO", dragon_level=2):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.players = players # list of 2 or 3 players
        self.bet = bet
        self.mode_title = mode_title
        self.dragon_level = dragon_level
        self.dragon_info = DRAGON_LEVELS.get(dragon_level, DRAGON_LEVELS[2])
        num_p = len(players)

        # Scale boss HP based on dragon level and party size
        if num_p == 2:
            self.max_boss_hp = self.dragon_info["duo_hp"]
        else:
            self.max_boss_hp = self.dragon_info["trio_hp"]

        self.boss_hp = self.max_boss_hp

        # Player HP tracking
        self.player_hp = {p.id: 100 for p in players}
        self.turn_index = 0
        self.current_turn = players[0].id
        self.msg = None
        self.log = []
        self.in_action = False

    def make_hp_bar(self, cur, max_v):
        pct = max(0, min(10, int((cur / max_v) * 10)))
        return "❤️" * pct + "🖤" * (10 - pct)

    def get_player_weapon(self, user_id):
        user_data = get_user(user_id)
        w_id = user_data.get("active_weapon")
        if w_id and w_id in STORE_ITEMS:
            return STORE_ITEMS[w_id]
        return None

    def get_battle_arena_art(self, animation_type=None, actor=None, target=None):
        names = [p.display_name[:7] for p in self.players]
        roster_str = " ".join([f"⚔️ {n:<7}" for n in names])

        if animation_type == "slash":
            art = (
                f"   [HEROES ROSTER]                     [DRAGON BOSS]        \n"
                f"   {roster_str:<25}   🔥🔥   /\\_^_/\\  🔥🔥   \n"
                f"          \\====[ ⚔️ SLASH! ]====>      ( 👁️ ᴥ 👁️ )     \n"
                f"            💥💥 CRITICAL HIT! 💥💥        /  ==W==  \\    \n"
                f"                                        / / |   | \\ \\   "
            )
        elif animation_type == "magic":
            art = (
                f"   [HEROES ROSTER]                     [DRAGON BOSS]        \n"
                f"   {roster_str:<25}  ✨⚡⚡  /\\_^_/\\  ⚡⚡✨  \n"
                f"         🔮~~(( ⚡ ARCANE BLAST! ))~~>> ( > ᴥ < ) !!   \n"
                f"          🌟🌟 ARCANE DETONATION! 🌟🌟    /  ==W==  \\    \n"
                f"                                        / / |   | \\ \\   "
            )
        elif animation_type == "heal":
            art = (
                f"   [HEROES ROSTER]                     [DRAGON BOSS]        \n"
                f"    ✨💚  [ DIVINE BLESSING ]  💚✨        🔥🔥   /\\_^_/\\  🔥🔥   \n"
                f"   {roster_str:<25}        ( 👁️ ᴥ 👁️ )     \n"
                f"    💖 +HP RESTORED TO TEAM! 💖          /  ==W==  \\    \n"
                f"   ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~   / / |   | \\ \\   "
            )
        elif animation_type == "dragon_attack":
            art = (
                f"   [HEROES ROSTER]                     [DRAGON BOSS]        \n"
                f"   {roster_str:<25}        🔥🔥   /\\_^_/\\  🔥🔥   \n"
                f"     <<<====[ 🔥 DRAGON BREATH! ]=====( ◣ ᴥ ◢ ) ROAAAR!   \n"
                f"     💥 INFERNO BURNING {target.display_name[:7]}! 💥        /  ==W==  \\    \n"
                f"                                        / / |   | \\ \\   "
            )
        elif animation_type == "victory":
            art = (
                f"      👑 VICTORY ROYALE 👑             [DRAGON DEFEATED]     \n"
                f"   🎉 {roster_str:<25}             💀 ( x ᴥ x ) 💀     \n"
                f"       \\(^o^)/       \\(^o^)/            /  ==W==  \\    \n"
                f"    💰 GOLD CHEST UNLOCKED! 💰         / / |   | \\ \\   "
            )
        elif animation_type == "defeat":
            art = (
                f"      💀 TEAM WIPED OUT 💀              [DRAGON VICTORIOUS]  \n"
                f"   ☠️ {roster_str:<25}        🔥🔥   /\\_^_/\\  🔥🔥   \n"
                f"        ( x _ x )     ( x _ x )        ( ◣ ᴥ ◢ ) HAHAHA!    \n"
                f"      Dungeon Darkness Consumed All...  /  ==W==  \\    "
            )
        else:
            current_p = discord.utils.get(self.players, id=self.current_turn)
            cname = current_p.display_name[:8] if current_p else "Hero"
            art = (
                f"   [HEROES ROSTER]                     [DRAGON BOSS]        \n"
                f"   {roster_str:<25}        🔥🔥   /\\_^_/\\  🔥🔥   \n"
                f"            vs                          ( 👁️ ᴥ 👁️ )     \n"
                f"   ▶▶ Current Turn: {cname:<8} ◀◀          /  ==W==  \\    \n"
                f"   =================================    / / |   | \\ \\   "
            )

        return f"```\n{art}\n```"

    def get_embed(self, status="Combat Ongoing", anim_type=None, target=None):
        num_p = len(self.players)
        total_pool = self.bet * num_p
        embed = discord.Embed(
            title=f"🐉 {self.mode_title} RAID: {self.dragon_info['title']} 🐉",
            description=(
                f"⚔️ **Dungeon Status:** {status}\n"
                f"⭐ Dragon Difficulty: **Level {self.dragon_level}** | Multiplier: **{self.dragon_info['payout_mult']}x**\n"
                f"💰 Stake Pool: **{total_pool:,} OwO Cash** ({self.bet:,} OwO each)\n"
                f"{self.get_battle_arena_art(anim_type, target=target)}"
            ),
            color=discord.Color.dark_red() if self.boss_hp > 0 else discord.Color.gold()
        )
        embed.add_field(
            name=f"{self.dragon_info['emoji']} {self.dragon_info['name']} (HP: {max(0, self.boss_hp)}/{self.max_boss_hp})",
            value=f"`[{self.make_hp_bar(self.boss_hp, self.max_boss_hp)}]`",
            inline=False
        )

        role_emojis = ["🛡️", "🏹", "🔮"]
        for i, p in enumerate(self.players):
            hp = self.player_hp.get(p.id, 0)
            w_item = self.get_player_weapon(p.id)
            w_str = f" | {w_item['icon']} +{w_item.get('bonus_dmg',0)} DMG" if w_item else ""
            embed.add_field(
                name=f"{role_emojis[i % len(role_emojis)]} {p.display_name} (HP: {max(0, hp)}/100){w_str}",
                value=f"`[{self.make_hp_bar(hp, 100)}]`",
                inline=True
            )

        alive_players = [p for p in self.players if self.player_hp.get(p.id, 0) > 0]
        if self.boss_hp > 0 and alive_players:
            turn_p = discord.utils.get(self.players, id=self.current_turn)
            embed.add_field(name="🎯 Active Turn", value=f"**{turn_p.mention}'s Turn to Strike!**", inline=False)

        if self.log:
            embed.add_field(name="📜 Combat Log", value="\n".join(self.log[-4:]), inline=False)

        return embed

    @discord.ui.button(label="Slash Attack", style=discord.ButtonStyle.danger, emoji="⚔️")
    async def attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.current_turn:
            return await interaction.response.send_message("❌ Abhi aapki turn nahi hai!", ephemeral=True)
        if self.in_action:
            return await interaction.response.send_message("⏳ Action chal raha hai, kripya intezar karein!", ephemeral=True)

        self.in_action = True
        import asyncio
        user = interaction.user
        base_dmg = random.randint(50, 85)
        w_item = self.get_player_weapon(user.id)
        bonus = w_item.get("bonus_dmg", 0) if w_item else 0
        dmg = base_dmg + bonus

        self.boss_hp -= dmg
        weapon_text = f" with **{w_item['name']}** (+{bonus} Weapon Bonus)" if w_item else ""
        self.log.append(f"⚔️ **{user.display_name}** lunged with sword slash{weapon_text} for **{dmg} DMG**!")

        slash_embed = self.get_embed(f"⚔️ {user.display_name} attacks with Slash!", anim_type="slash")
        await interaction.response.edit_message(embed=slash_embed, view=self)
        await asyncio.sleep(1.2)

        await self.handle_boss_turn()

    @discord.ui.button(label="Magic Blast", style=discord.ButtonStyle.primary, emoji="✨")
    async def magic_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.current_turn:
            return await interaction.response.send_message("❌ Abhi aapki turn nahi hai!", ephemeral=True)
        if self.in_action:
            return await interaction.response.send_message("⏳ Action chal raha hai, kripya intezar karein!", ephemeral=True)

        self.in_action = True
        import asyncio
        user = interaction.user
        if random.random() < 0.20:
            self.log.append(f"💨 **{user.display_name}'s** Arcane Spell fizzled and MISSED!")
            dmg = 0
        else:
            base_dmg = random.randint(75, 120)
            w_item = self.get_player_weapon(user.id)
            bonus = w_item.get("bonus_dmg", 0) if w_item else 0
            dmg = base_dmg + bonus
            self.boss_hp -= dmg
            weapon_text = f" using **{w_item['name']}** (+{bonus} Weapon Boost)" if w_item else ""
            self.log.append(f"✨ **{user.display_name}** channeled Arcane Blast{weapon_text} for **{dmg} CRIT DMG**!")

        magic_embed = self.get_embed(f"✨ {user.display_name} cast Arcane Magic!", anim_type="magic")
        await interaction.response.edit_message(embed=magic_embed, view=self)
        await asyncio.sleep(1.2)

        await self.handle_boss_turn()

    @discord.ui.button(label="Heal Team", style=discord.ButtonStyle.success, emoji="🧪")
    async def heal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.current_turn:
            return await interaction.response.send_message("❌ Abhi aapki turn nahi hai!", ephemeral=True)
        if self.in_action:
            return await interaction.response.send_message("⏳ Action chal raha hai, kripya intezar karein!", ephemeral=True)

        self.in_action = True
        import asyncio
        user = interaction.user
        heal_amt = random.randint(30, 50)
        for p in self.players:
            if self.player_hp[p.id] > 0:
                self.player_hp[p.id] = min(100, self.player_hp[p.id] + heal_amt)

        self.log.append(f"🧪 **{user.display_name}** cast Divine Blessing: healed alive teammates for **+{heal_amt} HP**!")

        heal_embed = self.get_embed(f"💚 {user.display_name} healed the entire party!", anim_type="heal")
        await interaction.response.edit_message(embed=heal_embed, view=self)
        await asyncio.sleep(1.2)

        await self.handle_boss_turn()

    async def handle_boss_turn(self):
        import asyncio
        if self.boss_hp <= 0:
            for child in self.children:
                child.disabled = True
            mult = self.dragon_info["payout_mult"]
            prize = int(self.bet * mult)
            xp_reward = self.dragon_info["xp"]
            reward_lines = []
            for p in self.players:
                res = update_user_balance(p.id, prize, xp_change=xp_reward)
                elo, _, _ = update_user_stats(p.id, elo_change=+25 + (self.dragon_level * 5), is_win=True)
                reward_lines.append(f"👑 {p.mention}: **+{prize:,} OwO Cash** (+{25 + (self.dragon_level * 5)} ELO ⚡ | Balance: **{res['cash']:,}**)")

            win_embed = self.get_embed(f"🎉 VICTORY! {self.dragon_info['name']} Slain!", anim_type="victory")
            win_embed.color = discord.Color.gold()
            win_embed.add_field(
                name="💰 Dungeon Rewards Collected!",
                value="\n".join(reward_lines),
                inline=False
            )
            await self.msg.edit(embed=win_embed, view=None)
            self.in_action = False
            return

        # Target an alive player
        alive_players = [p for p in self.players if self.player_hp[p.id] > 0]
        if not alive_players:
            # Wipe
            for child in self.children:
                child.disabled = True
            for p in self.players:
                update_user_balance(p.id, -self.bet, xp_change=10)
                update_user_stats(p.id, elo_change=-15, is_win=False)

            defeat_embed = self.get_embed("💀 DEFEAT! All Heroes Fallen!", anim_type="defeat")
            defeat_embed.color = discord.Color.red()
            defeat_embed.add_field(
                name="☠️ Dungeon Raid Failed",
                value=f"Saare players **-{self.bet:,} OwO Cash** aur **-15 ELO** haar gaye!",
                inline=False
            )
            await self.msg.edit(embed=defeat_embed, view=None)
            self.in_action = False
            return

        boss_target = random.choice(alive_players)
        boss_dmg = random.randint(self.dragon_info["base_min_dmg"], self.dragon_info["base_max_dmg"])
        self.player_hp[boss_target.id] = max(0, self.player_hp[boss_target.id] - boss_dmg)

        self.log.append(f"🔥 **{self.dragon_info['name']}** roared INFERNO on **{boss_target.display_name}** for **{boss_dmg} DMG**!")

        dragon_embed = self.get_embed(f"🔥 {self.dragon_info['name'].upper()} ATTACK!", anim_type="dragon_attack", target=boss_target)
        await self.msg.edit(embed=dragon_embed, view=self)
        await asyncio.sleep(1.2)

        # Re-check alive players
        alive_players = [p for p in self.players if self.player_hp[p.id] > 0]
        if not alive_players:
            for child in self.children:
                child.disabled = True
            for p in self.players:
                update_user_balance(p.id, -self.bet, xp_change=10)
                update_user_stats(p.id, elo_change=-15, is_win=False)

            defeat_embed = self.get_embed("💀 DEFEAT! All Heroes Fallen!", anim_type="defeat")
            defeat_embed.color = discord.Color.red()
            defeat_embed.add_field(
                name="☠️ Dungeon Raid Failed",
                value=f"Saare players **-{self.bet:,} OwO Cash** aur **-15 ELO** haar gaye!",
                inline=False
            )
            await self.msg.edit(embed=defeat_embed, view=None)
            self.in_action = False
            return

        # Advance turn to next alive player
        attempts = len(self.players)
        while attempts > 0:
            self.turn_index = (self.turn_index + 1) % len(self.players)
            candidate = self.players[self.turn_index]
            if self.player_hp[candidate.id] > 0:
                self.current_turn = candidate.id
                break
            attempts -= 1

        normal_embed = self.get_embed("Combat Ongoing - Turn Passed")
        await self.msg.edit(embed=normal_embed, view=self)
        self.in_action = False

# Duo command alias/wrapper with Dragon Level selector
@bot.command(name="battle", aliases=["duo", "duobattle", "raid"])
async def owo_duo_battle(ctx, partner: discord.Member = None, bet: str = "15000", level: int = 2):
    """2-Player Co-Op Duo Dungeon Raid vs Boss with difficulty level!
    Usage: owo battle @partner [bet] [level: 1-5]"""
    if not partner:
        return await ctx.send(
            "❓ **Usage:** `owo battle @partner [bet] [dragon_level 1-5]`\n"
            "Example: `owo battle @Friend 20000 3`\n"
            "💡 Dragon levels dekhne ke liye: `owo dragonlevels`"
        )
    if partner.id == ctx.author.id:
        return await ctx.send("❌ Apne sath duo nahi bana sakte!")
    if partner.bot:
        return await ctx.send("❌ Bots ke sath duo raid nahi kar sakte!")

    bet_amount = parse_bet_amount(ctx.author.id, bet)
    if bet_amount is None or bet_amount <= 0:
        return await ctx.send("❌ Galat bet amount! Kripya valid number, `all`, ya `half` daalein.")

    if level not in DRAGON_LEVELS:
        return await ctx.send("❌ Dragon Level 1 se 5 ke beech chunein! Details: `owo dragonlevels`")

    dragon_info = DRAGON_LEVELS[level]
    p1_data = get_user(ctx.author.id)
    p2_data = get_user(partner.id)

    if p1_data["level"] < dragon_info["min_level"]:
        return await ctx.send(f"❌ Is Dragon ko face karne ke liye aapka Player Level kam se kam **Level {dragon_info['min_level']}** hona chahiye!")

    if p1_data["cash"] < bet_amount:
        return await ctx.send(f"❌ Aapke paas paryapt OwO Cash nahi hai! Balance: **{p1_data['cash']:,} OwO**")
    if p2_data["cash"] < bet_amount:
        return await ctx.send(f"❌ {partner.mention} ke paas paryapt cash nahi hai! Balance: **{p2_data['cash']:,} OwO**")

    view = DungeonRaidView(ctx, [ctx.author, partner], bet_amount, mode_title="DUO", dragon_level=level)
    msg = await ctx.send(
        f"⚔️ **DUO RAID INITIATED:** {ctx.author.mention} & {partner.mention} vs **{dragon_info['name']} (Lvl {level})**!",
        embed=view.get_embed(),
        view=view
    )
    view.msg = msg

# Trio command with Dragon Level selector
@bot.command(name="trio", aliases=["triobattle", "trioraid"])
async def owo_trio_battle(ctx, partner1: discord.Member = None, partner2: discord.Member = None, bet: str = "15000", level: int = 2):
    """3-Player Co-Op Trio Dungeon Raid vs Boss with difficulty level!
    Usage: owo trio @partner1 @partner2 [bet] [level: 1-5]"""
    if not partner1 or not partner2:
        return await ctx.send(
            "❓ **Usage:** `owo trio @partner1 @partner2 [bet] [dragon_level 1-5]`\n"
            "Example: `owo trio @Friend1 @Friend2 25000 3`\n"
            "💡 Dragon levels dekhne ke liye: `owo dragonlevels`"
        )
    
    unique_ids = {ctx.author.id, partner1.id, partner2.id}
    if len(unique_ids) < 3:
        return await ctx.send("❌ Teen alag-alag players hone chahiye!")

    if partner1.bot or partner2.bot:
        return await ctx.send("❌ Bots ke sath trio raid nahi kar sakte!")

    bet_amount = parse_bet_amount(ctx.author.id, bet)
    if bet_amount is None or bet_amount <= 0:
        return await ctx.send("❌ Galat bet amount! Kripya valid number, `all`, ya `half` daalein.")

    if level not in DRAGON_LEVELS:
        return await ctx.send("❌ Dragon Level 1 se 5 ke beech chunein! Details: `owo dragonlevels`")

    dragon_info = DRAGON_LEVELS[level]
    players = [ctx.author, partner1, partner2]
    for p in players:
        p_data = get_user(p.id)
        if p_data["cash"] < bet_amount:
            return await ctx.send(f"❌ {p.mention} ke paas paryapt OwO Cash nahi hai! Balance: **{p_data['cash']:,} OwO**")
        if p_data["level"] < dragon_info["min_level"]:
            return await ctx.send(f"❌ {p.mention} ka player level kam hai! Required: **Level {dragon_info['min_level']}**")

    view = DungeonRaidView(ctx, players, bet_amount, mode_title="TRIO", dragon_level=level)
    msg = await ctx.send(
        f"⚔️ **TRIO RAID INITIATED:** {ctx.author.mention}, {partner1.mention} & {partner2.mention} vs **{dragon_info['name']} (Lvl {level})**!",
        embed=view.get_embed(),
        view=view
    )
    view.msg = msg

@bot.command(name="dragonlevels", aliases=["dragons", "bosses", "dlevels"])
async def owo_dragon_levels(ctx):
    """Dragon Raid ke saare levels, HP aur rewards dekhein!"""
    embed = discord.Embed(
        title="🐉 Dragon Raid Difficulty & HP Tiers 🐉",
        description="Raid start karte waqt level specify karein: `owo battle @partner <bet> [level]`\n───────────────────────────────",
        color=discord.Color.dark_red()
    )
    for lvl, d in DRAGON_LEVELS.items():
        embed.add_field(
            name=f"{d['emoji']} Level {lvl}: {d['name']}",
            value=(
                f"🛡️ **Duo HP:** `{d['duo_hp']} HP` | **Trio HP:** `{d['trio_hp']} HP`\n"
                f"🔥 **Attack Range:** `{d['base_min_dmg']} - {d['base_max_dmg']} DMG`\n"
                f"💰 **Reward:** `{d['payout_mult']}x Cash` | ✨ `+{d['xp']} XP`\n"
                f"🔒 **Req Player Level:** `Level {d['min_level']}+`"
            ),
            inline=False
        )
    embed.set_footer(text="Tip: Powerful weapons lene ke liye 'owo store' check karein!")
    await ctx.send(embed=embed)


# 3. SQUAD BATTLE ROYALE (4 PLAYERS FFA WITH LIVE ELIMINATION ANIMATIONS)
class SquadLobbyView(discord.ui.View):
    def __init__(self, host, bet):
        super().__init__(timeout=90)
        self.host = host
        self.bet = bet
        self.players = [host]
        self.msg = None

    def get_lobby_embed(self):
        embed = discord.Embed(
            title="🛡️ SQUAD ARENA BATTLE ROYALE (4 Players) 🛡️",
            description=(
                f"**Host:** {self.host.mention}\n"
                f"**Entry Fee:** **{self.bet:,} OwO Cash** per player\n"
                f"💰 Total Winner Prize: **+{int(self.bet * 3.6):,} OwO Cash**! (90% of pool)\n"
                f"⚡ Competitive ELO Reward: **+50 ELO** to winner!\n\n"
                f"Lobby ko join karne ke liye **'Join Squad'** button dabayein!\n"
                f"Slot count: **{len(self.players)} / 4 Players**\n"
                f"───────────────────────────────"
            ),
            color=discord.Color.purple()
        )
        player_list = "\n".join([f"• {p.mention} `({get_tier_info(get_user(p.id)['elo'])[0]})`" for p in self.players])
        embed.add_field(name="👥 Squad Roster", value=player_list or "No players", inline=False)
        embed.set_footer(text="4 players join hone par match automatically start ho jayega!")
        return embed

    @discord.ui.button(label="Join Squad", style=discord.ButtonStyle.success, emoji="⚔️")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if user in self.players:
            return await interaction.response.send_message("❌ Aap pehle se hi squad lobby mein hain!", ephemeral=True)

        user_data = get_user(user.id)
        if user_data["cash"] < self.bet:
            return await interaction.response.send_message(f"❌ Aapke paas paryapt cash nahi hai! Chahiye: **{self.bet:,} OwO**", ephemeral=True)

        self.players.append(user)

        if len(self.players) == 4:
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(embed=self.get_lobby_embed(), view=self)
            await self.start_squad_match()
        else:
            await interaction.response.edit_message(embed=self.get_lobby_embed(), view=self)

    async def start_squad_match(self):
        import asyncio
        for p in self.players:
            update_user_balance(p.id, -self.bet)

        start_embed = discord.Embed(
            title="🔥 SQUAD MATCH COMMENCING! 🔥",
            description=(
                f"4 Warriors enter the OwO Colosseum!\n\n"
                + "\n".join([f"⚡ {p.mention}" for p in self.players])
                + f"\n\nTotal Pot: **{self.bet * 4:,} OwO Cash**\n*Dropping into the arena...*"
            ),
            color=discord.Color.gold()
        )
        await self.msg.edit(embed=start_embed, view=None)
        await asyncio.sleep(2.0)

        # Simulation rounds with elimination animation
        remaining = list(self.players)
        round_num = 1
        kill_reasons = [
            "sniper headshot se eliminate ho gaye 🎯",
            "lava pit mein gir gaye 🌋",
            "poison storm mein phas gaye ☠️",
            "close-quarters shotgun blast kha gaye 💥",
            "frag grenade ke blast se ud gaye 💣",
            "hidden trap wire trigger kar diya ⚡"
        ]

        while len(remaining) > 1:
            await asyncio.sleep(1.8)
            victim = random.choice(remaining)
            remaining.remove(victim)
            killer = random.choice(remaining)
            reason = random.choice(kill_reasons)

            update_user_stats(victim.id, elo_change=-10, is_win=False)

            round_embed = discord.Embed(
                title=f"⚔️ SQUAD ARENA: ROUND {round_num} ELIMINATION!",
                description=(
                    f"💀 **{victim.mention}** ko **{killer.mention}** ne {reason}!\n\n"
                    f"🛡️ **Remaining Alive ({len(remaining)}/4):**\n"
                    + "\n".join([f"• {p.mention}" for p in remaining])
                ),
                color=discord.Color.red()
            )
            await self.msg.edit(embed=round_embed)
            round_num += 1

        # Final Winner
        winner = remaining[0]
        total_pool = self.bet * 4
        winner_prize = int(total_pool * 0.9)
        res = update_user_balance(winner.id, winner_prize, xp_change=120)
        elo, wins, _ = update_user_stats(winner.id, elo_change=+50, is_win=True)
        tier, _ = get_tier_info(elo)

        await asyncio.sleep(1.5)
        win_embed = discord.Embed(
            title="👑 SQUAD BATTLE ROYALE CHAMPION! 👑",
            description=(
                f"```\n"
                f"┌───────────────────────────────────────┐\n"
                f"│        VICTORY ROYALE #1 SQUAD        │\n"
                f"│  CHAMPION: {winner.display_name[:20]:<20}       │\n"
                f"└───────────────────────────────────────┘\n"
                f"```\n"
                f"🎉 **{winner.mention}** ne saare opponents ko eliminate kar diya!\n\n"
                f"💰 Total Payout: **+{winner_prize:,} OwO Cash**!\n"
                f"⚡ Competitive ELO: **+50 ELO** (New ELO: **{elo}** | {tier})\n"
                f"💳 Naya Balance: **{res['cash']:,} OwO**"
            ),
            color=discord.Color.gold()
        )
        win_embed.set_footer(text="Competitive Ranks check karne ke liye: owo toprank | owo rank")
        await self.msg.edit(embed=win_embed)

@bot.command(name="squad", aliases=["squads", "br", "battleroyale", "4v4"])
async def owo_squad_game(ctx, bet: str = "25000"):
    """4-Player Squad Battle Royale lobby with elimination animations!"""
    bet_amount = parse_bet_amount(ctx.author.id, bet)
    if bet_amount is None or bet_amount <= 0:
        return await ctx.send("❌ Galat bet amount! Kripya valid number, `all`, ya `half` daalein.")

    host_data = get_user(ctx.author.id)
    if host_data["cash"] < bet_amount:
        return await ctx.send(f"❌ Aapke paas paryapt OwO Cash nahi hai! Entry fee: **{bet_amount:,} OwO** | Balance: **{host_data['cash']:,} OwO**")

    view = SquadLobbyView(ctx.author, bet_amount)
    msg = await ctx.send(embed=view.get_lobby_embed(), view=view)
    view.msg = msg

# ----------------- SLASH COMMANDS (/cash, /flip, /mines, etc.) -----------------

@bot.tree.command(name="cash", description="Check your OwO cash balance and level")
async def slash_cash(interaction: discord.Interaction):
    user_data = get_user(interaction.user.id)
    xp_needed = user_data["level"] * 100
    embed = discord.Embed(
        title=f"💳 {interaction.user.display_name}'s OwO Bank",
        color=discord.Color.gold()
    )
    embed.add_field(name="💵 OwO Cash", value=f"**{user_data['cash']:,} OwO**", inline=True)
    embed.add_field(name="🏆 Level", value=f"**Level {user_data['level']}**", inline=True)
    embed.add_field(name="✨ XP", value=f"**{user_data['xp']}/{xp_needed} XP**", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="mines", description="Play interactive Diamond and Mines game")
@app_commands.describe(bet="Amount of OwO Cash to bet", bombs="Number of bombs (1-8)")
async def slash_mines(interaction: discord.Interaction, bet: int = 100, bombs: int = 3):
    if bet <= 0:
        return await interaction.response.send_message("❌ Bet amount 0 se zyada honi chahiye!", ephemeral=True)
    if bombs < 1 or bombs > 8:
        return await interaction.response.send_message("❌ Bombs 1 se 8 ke beech hone chahiye!", ephemeral=True)

    user_data = get_user(interaction.user.id)
    if user_data["cash"] < bet:
        return await interaction.response.send_message(f"❌ Balance kam hai! Current: **{user_data['cash']:,} OwO**", ephemeral=True)

    view = MinesView(user_id=interaction.user.id, bet=bet, num_mines=bombs)
    embed = discord.Embed(
        title="💎 Diamond & Mines Game 💣",
        description=f"Player: {interaction.user.mention}\nBet: **{bet:,} OwO** | Bombs: **{bombs}**\n\nTiles click karke diamond nikalo aur multiplier badhao!",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed, view=view)

@bot.event
async def on_command_error(ctx, error):
    """Global error handler so the bot never crashes and gives friendly messages."""
    if isinstance(error, commands.CommandOnCooldown):
        return # Handled in command error handler
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Galat input! Kripya command arguments check karein (e.g., valid number ya user mention).")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: `{error.param.name}`! Sahi syntax dekhne ke liye `owo help` check karein.")
    elif isinstance(error, commands.CommandNotFound):
        pass # Ignore unknown commands
    else:
        print(f"Ignored error in command {ctx.command}: {error}")

# Run Bot
if __name__ == "__main__":
    if not TOKEN or TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("ERROR: Kripya .env file me apna DISCORD_TOKEN daalein!")
    else:
        bot.run(TOKEN)
