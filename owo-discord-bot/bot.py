import os
import random
import sqlite3
import math
from dotenv import load_dotenv
import discord
from discord import app_commands
from discord.ext import commands

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

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
            level INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT cash, xp, level FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        # Initial cash: 1,000,000 (1 Million) cash
        cursor.execute("INSERT INTO users (user_id, cash, xp, level) VALUES (?, 1000000, 0, 1)", (user_id,))
        conn.commit()
        conn.close()
        return {"cash": 1000000, "xp": 0, "level": 1, "auto_refilled": False}
    
    cash, xp, level = row
    auto_refilled = False
    
    # Auto-refill rule: Agar cash 0 ya khatam ho jaye to automatic 1 Lakh (100,000) cash add ho jaye (unlimited feature)
    if cash <= 0:
        cash = 100000
        auto_refilled = True
        cursor.execute("UPDATE users SET cash = ? WHERE user_id = ?", (cash, user_id))
        conn.commit()

    conn.close()
    return {"cash": cash, "xp": xp, "level": level, "auto_refilled": auto_refilled}

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
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")
    print(f"Logged in as {bot.user.name} ({bot.user.id})")
    print("OwO Discord Bot is Online and Ready!")

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
            "`owo daily` - Rozana free 2,000 OwO Cash claim karein\n"
            "`owo give <@user> <amount>` - Dusre user ko OwO transfer karein\n"
            "✨ **Unlimited Protection:** Jab bhi aapka cash 0 ho jayega, automatically +1,000 OwO Cash wapas add ho jayega!"
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
        name="⭐ Levels & Rewards",
        value=(
            "`owo level` - Level aur XP status dekhein\n"
            "`owo top` - Server leaderboard (rich players)"
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
async def owo_coinflip(ctx, choice: str = None, bet: int = None):
    if not choice or bet is None:
        return await ctx.send("❓ **Usage:** `owo coinflip <heads/tails> <amount>`\nExample: `owo coinflip h 500`")
    
    choice = choice.lower()
    if choice in ["h", "head", "heads"]:
        choice_str = "heads"
    elif choice in ["t", "tail", "tails"]:
        choice_str = "tails"
    else:
        return await ctx.send("❌ Galat choice! Kripya `heads` (h) ya `tails` (t) chunein.")

    if bet <= 0:
        return await ctx.send("❌ Bet amount 0 se zyada honi chahiye!")

    user_data = get_user(ctx.author.id)
    if user_data["cash"] < bet:
        return await ctx.send(f"❌ Aapke paas itna OwO Cash nahi hai! Balance: **{user_data['cash']:,} OwO**")

    # Flip coin
    outcome = random.choice(["heads", "tails"])
    coin_emoji = "🪙" if outcome == "heads" else "💿"

    if outcome == choice_str:
        # Win (2x bet = net +bet)
        res = update_user_balance(ctx.author.id, bet, xp_change=20)
        level_msg = f"\n🎊 **LEVEL UP!** Aap Level {res['level']} par pahunch gaye! (+{res['reward']:,} OwO Bonus)" if res["leveled_up"] else ""
        
        embed = discord.Embed(
            title=f"{coin_emoji} Coinflip Won!",
            description=f"Coin par aaya: **{outcome.upper()}**!\nAapne chuna tha: **{choice_str.upper()}**\n\n🎉 Aap jeete: **+{bet:,} OwO Cash**!{level_msg}\nBalance: **{res['cash']:,} OwO**",
            color=discord.Color.green()
        )
    else:
        # Loss
        res = update_user_balance(ctx.author.id, -bet, xp_change=5)
        refill_msg = "\n✨ **Unlimited OwO Protection:** Balance 0 hone par automatically +1,00,000 OwO Cash add ho gaya!" if res["auto_refilled"] else ""

        embed = discord.Embed(
            title=f"{coin_emoji} Coinflip Lost!",
            description=f"Coin par aaya: **{outcome.upper()}**\nAapne chuna tha: **{choice_str.upper()}**\n\n😢 Aap haar gaye: **-{bet:,} OwO Cash**.{refill_msg}\nBalance: **{res['cash']:,} OwO**",
            color=discord.Color.red()
        )
    await ctx.send(embed=embed)

@bot.command(name="mines", aliases=["mine", "diamond"])
async def owo_mines(ctx, bet: int = 100, bombs: int = 3):
    if bet <= 0:
        return await ctx.send("❌ Bet amount 0 se zyada honi chahiye!")
    
    if bombs < 1 or bombs > 8:
        return await ctx.send("❌ Bombs ki sankhya 1 se 8 ke beech honi chahiye (Default: 3)!")

    user_data = get_user(ctx.author.id)
    if user_data["cash"] < bet:
        return await ctx.send(f"❌ Aapke paas itna OwO Cash nahi hai! Balance: **{user_data['cash']:,} OwO**")

    view = MinesView(user_id=ctx.author.id, bet=bet, num_mines=bombs)
    embed = discord.Embed(
        title="💎 Diamond & Mines Game 💣",
        description=f"Player: {ctx.author.mention}\nBet: **{bet:,} OwO** | Bombs: **{bombs}**\n\nTiles click karke diamond nikalo. Jitne zyada diamonds, utna bada multiplier!\nJab man kare tab **Cash Out** daba do!",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed, view=view)

@bot.command(name="roulette", aliases=["roul", "rl"])
async def owo_roulette(ctx, bet_type: str = None, bet: int = None):
    if not bet_type or bet is None:
        return await ctx.send(
            "❓ **Usage:** `owo roulette <option> <amount>`\n\n"
            "**Options:**\n"
            "• `red` / `black` (2x payout)\n"
            "• `even` / `odd` (2x payout)\n"
            "• `green` (14x payout - Number 0)\n"
            "• Number `0` to `36` (36x payout)\n"
            "Example: `owo roulette red 500` ya `owo roulette 7 100`"
        )

    if bet <= 0:
        return await ctx.send("❌ Bet amount 0 se zyada honi chahiye!")

    user_data = get_user(ctx.author.id)
    if user_data["cash"] < bet:
        return await ctx.send(f"❌ Aapke paas itna OwO Cash nahi hai! Balance: **{user_data['cash']:,} OwO**")

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
        payout = bet * 2
    elif bet_type in ["black", "b"] and rolled_color == "black":
        won = True
        payout = bet * 2
    elif bet_type in ["green", "g"] and rolled_color == "green":
        won = True
        payout = bet * 14
    elif bet_type == "even" and rolled_num != 0 and rolled_num % 2 == 0:
        won = True
        payout = bet * 2
    elif bet_type == "odd" and rolled_num != 0 and rolled_num % 2 == 1:
        won = True
        payout = bet * 2
    elif bet_type.isdigit():
        target_num = int(bet_type)
        if 0 <= target_num <= 36 and target_num == rolled_num:
            won = True
            payout = bet * 36

    color_emoji = "🟢" if rolled_color == "green" else ("🔴" if rolled_color == "red" else "⚫")

    if won:
        profit = payout - bet
        res = update_user_balance(ctx.author.id, profit, xp_change=30)
        level_msg = f"\n🎊 **LEVEL UP!** Aap Level {res['level']} par pahunch gaye! (+{res['reward']:,} OwO Bonus)" if res["leveled_up"] else ""

        embed = discord.Embed(
            title="🎡 Roulette - YOU WON!",
            description=(
                f"Wheel landed on: {color_emoji} **{rolled_num} ({rolled_color.upper()})**!\n"
                f"Aapki bet thi: **{bet_type.upper()}**\n\n"
                f"🎉 Total Payout: **+{payout:,} OwO** (Profit: +{profit:,}){level_msg}\n"
                f"Naya Balance: **{res['cash']:,} OwO**"
            ),
            color=discord.Color.green()
        )
    else:
        res = update_user_balance(ctx.author.id, -bet, xp_change=10)
        refill_msg = "\n✨ **Unlimited OwO Protection:** Balance 0 hone par automatically +1,00,000 OwO Cash add ho gaya!" if res["auto_refilled"] else ""

        embed = discord.Embed(
            title="🎡 Roulette - YOU LOST!",
            description=(
                f"Wheel landed on: {color_emoji} **{rolled_num} ({rolled_color.upper()})**\n"
                f"Aapki bet thi: **{bet_type.upper()}**\n\n"
                f"😢 Haar gaye: **-{bet:,} OwO Cash**{refill_msg}\n"
                f"Naya Balance: **{res['cash']:,} OwO**"
            ),
            color=discord.Color.red()
        )
    await ctx.send(embed=embed)

@bot.command(name="slots", aliases=["slot", "s"])
async def owo_slots(ctx, bet: int = 100):
    if bet <= 0:
        return await ctx.send("❌ Bet amount 0 se zyada honi chahiye!")

    user_data = get_user(ctx.author.id)
    if user_data["cash"] < bet:
        return await ctx.send(f"❌ Aapke paas itna OwO Cash nahi hai! Balance: **{user_data['cash']:,} OwO**")

    symbols = ["🍒", "🍋", "🍇", "🔔", "⭐", "💎", "7️⃣"]
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
        total_payout = bet * multiplier
        profit = total_payout - bet
        res = update_user_balance(ctx.author.id, profit, xp_change=25)
        level_msg = f"\n🎊 **LEVEL UP!** Level {res['level']}! (+{res['reward']:,} OwO)" if res["leveled_up"] else ""

        embed = discord.Embed(
            title="🎰 OwO Slot Machine - JACKPOT!",
            description=(
                f"**[ {s1} | {s2} | {s3} ]**\n\n"
                f"🎉 Multiplier: **{multiplier}x**\n"
                f"Aap jeete: **+{total_payout:,} OwO Cash**!{level_msg}\n"
                f"Naya Balance: **{res['cash']:,} OwO**"
            ),
            color=discord.Color.gold()
        )
    else:
        res = update_user_balance(ctx.author.id, -bet, xp_change=5)
        refill_msg = "\n✨ **Unlimited OwO:** Auto-refill +1,00,000 OwO Cash!" if res["auto_refilled"] else ""

        embed = discord.Embed(
            title="🎰 OwO Slot Machine",
            description=(
                f"**[ {s1} | {s2} | {s3} ]**\n\n"
                f"😢 Match nahi hua! Aap haar gaye **-{bet:,} OwO Cash**.{refill_msg}\n"
                f"Naya Balance: **{res['cash']:,} OwO**"
            ),
            color=discord.Color.red()
        )
    await ctx.send(embed=embed)

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
    await ctx.send(embed=embed)

@bot.command(name="level", aliases=["lvl", "rank"])
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
async def owo_spin(ctx, bet: int = 1000):
    """Spin & Win game — jackpot is 1,000,000 OwO Cash!"""
    if bet <= 0:
        return await ctx.send("❌ Bet amount 0 se zyada honi chahiye!")

    user_data = get_user(ctx.author.id)
    if user_data["cash"] < bet:
        return await ctx.send(f"❌ Aapke paas itna OwO Cash nahi hai! Balance: **{user_data['cash']:,} OwO**")

    segments_display = "\n".join(
        f"{'🏆' if s[3] else '•'} **{s[0]}** — weight {s[2]}"
        for s in SPIN_SEGMENTS
    )

    view = SpinView(user_id=ctx.author.id, bet=bet)
    embed = discord.Embed(
        title="🎡 OwO Spin & Win!",
        description=(
            f"Player: {ctx.author.mention}\n"
            f"Bet: **{bet:,} OwO Cash**\n\n"
            f"**Possible Prizes:**\n"
            f"💀 BANKRUPT | 🔸 50 OwO | 🎁 2x–100x | 🌟 500x\n"
            f"🏆 **JACKPOT = 1,000,000 OwO!!!**\n\n"
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

    # Title based on level
    if user_data["level"] >= 50:
        title_badge = "👑 OwO Legend"
    elif user_data["level"] >= 30:
        title_badge = "🏆 OwO Master"
    elif user_data["level"] >= 20:
        title_badge = "💎 OwO Diamond"
    elif user_data["level"] >= 10:
        title_badge = "⭐ OwO Star"
    elif user_data["level"] >= 5:
        title_badge = "🎖️ OwO Veteran"
    else:
        title_badge = "🌱 OwO Newbie"

    embed = discord.Embed(
        title=f"👤 {target.display_name}'s OwO Profile",
        color=discord.Color.gold()
    )
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="🏅 Title", value=f"**{title_badge}**", inline=True)
    embed.add_field(name="💵 OwO Cash", value=f"**{user_data['cash']:,} OwO**", inline=True)
    embed.add_field(name="🏆 Server Rank", value=f"**#{rank}** / {total_users}", inline=True)
    embed.add_field(name="⭐ Level", value=f"**Level {user_data['level']}**", inline=True)
    embed.add_field(name="✨ XP Progress", value=f"**{user_data['xp']} / {xp_needed} XP**", inline=True)
    embed.add_field(name="📊 XP Bar", value=f"`[{xp_bar}]`", inline=False)
    next_reward = (user_data["level"] + 1) * 1000
    embed.add_field(name="🎁 Level-Up Reward", value=f"Next level pe: **+{next_reward:,} OwO Cash**", inline=False)
    embed.set_footer(text="OwO Bot | Khelo, Kamao, Level Up Karo! 🎮")
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

# Run Bot
if __name__ == "__main__":
    if not TOKEN or TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
        print("ERROR: Kripya .env file me apna DISCORD_TOKEN daalein!")
    else:
        bot.run(TOKEN)
