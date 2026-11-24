# 🎲 OwO Discord Game Bot (Unlimited Cash & Mini-Games)

Yeh ek complete Discord bot hai jo bilkul **OwO bot** ki tarah kaam karta hai aur isme aapki sari demand poori ki gayi hain:
1. **1 Million OwO Cash** (10 Lakh): Har naye user ko shuru mein **1,000,000 OwO Cash** milta hai!
2. **Unlimited OwO Cash**: Jab bhi kisi ka cash 0 ya negative hoga, bot automatically **+1,00,000 OwO Cash** (1 Lakh) reload kar dega!
3. **Head & Tails (Coinflip)**: `owo coinflip <heads/tails> <amount>` ya `owo cf h 500`.
4. **Diamond & Mines**: Interactive Discord Buttons wala Mines game (`owo mines <bet> <bombs>`).
5. **OwO Roulette**: Casino Roulette (`owo roulette <red/black/green/even/odd/0-36> <amount>`).
6. **🎡 Spin & Win (NEW!)**: `owo spin <amount>` — Jackpot = **1,000,000 OwO Cash!** (10 Lakh)
7. **Level & Rewards System**: Har game khelne par XP milta hai. Level-up hone par Level * 1,000 OwO Cash bonus milta hai.
8. **Daily Cash**: `owo daily` → Roz **1,00,000 OwO Free** milega!
9. **Slots, Leaderboard & Transfers**: `owo slots`, `owo top`, `owo give`.

---

## 🚀 Setup & Run Kaise Karein (Step-by-Step)

### Step 1: Discord Bot Token Nikalein
1. [Discord Developer Portal](https://discord.com/developers/applications) par jayein.
2. **New Application** create karein aur name dein (e.g. `OwO Game Bot`).
3. Left menu se **Bot** par click karein.
4. **Reset Token** par click karke token copy kar lein.
5. Usi page par neeche scroll karein aur **Privileged Gateway Intents** ke andar:
   - ✅ **Message Content Intent** (On karein)
   - ✅ **Server Members Intent** (On karein)
6. Save Changes karein.

### Step 2: Bot ko Server me Invite Karein
1. Left menu me **OAuth2 -> URL Generator** par jayein.
2. Scopes me select karein: `bot` aur `applications.commands`.
3. Bot Permissions me select karein: `Administrator` (ya Send Messages, Embed Links, Read Message History, Use Slash Commands).
4. Generated URL ko browser me khol kar apne server me invite kar lein.

### Step 3: Bot Configure & Start Karein
1. Bot ke folder me `.env` file ko Notepad me open karein.
2. `YOUR_DISCORD_BOT_TOKEN_HERE` ki jagah apna copied Token daal kar save karein:
   ```env
   DISCORD_TOKEN=your_actual_token_here
   ```
3. `run_bot.bat` par double-click karein! Yeh dependencies install karke bot ko start kar dega.

---

## 🎮 Commands List

| Command | Description | Example |
|---|---|---|
| `owo help` | Sabhi commands ki list dekhein | `owo help` |
| `owo cash` / `owo bal` | Apna OwO Cash balance aur level check karein | `owo cash` |
| `owo daily` | Rozana 1,00,000 OwO free cash claim karein | `owo daily` |
| `owo coinflip <h/t> <bet>` | Head and Tails game khelein (2x payout) | `owo cf h 500` |
| `owo mines <bet> [bombs]` | Interactive Mines & Diamonds game (Button UI) | `owo mines 200 3` |
| `owo roulette <option> <bet>` | Roulette khelein (red/black/odd/even/0-36) | `owo roulette red 500` |
| `owo slots <bet>` | Slot machine game khelein | `owo slots 100` |
| `owo spin [bet]` | 🎡 **Spin & Win** — Jackpot 1,000,000 OwO! | `owo spin 5000` |
| `owo store` | 🏬 **OwO Luxury Store** (interactive dropdown) | `owo store` |
| `owo buy <item_id>` | Store se item khareedein | `owo buy crown` |
| `owo inv` | Apni Inventory / Bag dekhein | `owo inv` |
| `owo equip <item_id>` | Badge ya Title apne Profile par lagayein | `owo equip crown` |
| `owo unequip <title/badge>` | Equipped Title ya Badge hatayein | `owo unequip title` |
| `owo rps @user <bet>` | ⚔️ **1v1 Rock Paper Scissors Duel** (Private Buttons + Bet + ELO) | `owo rps @Friend 50000` |
| `owo battle @user <bet>` | 🐉 **Duo Co-Op Dungeon Raid** vs Ancient Dragon | `owo battle @Friend 25000` |
| `owo trio @p1 @p2 <bet>` | 🐉 **Trio Co-Op Dungeon Raid** vs 520 HP Elder Dragon (3 Players) | `owo trio @Friend1 @Friend2 30000` |
| `owo squad [bet]` | 🛡️ **4-Player Squad Battle Royale** (Live Elimination Animation) | `owo squad 20000` |
| `owo rank` | Apna Arena ELO Rating, Tier aur Winrate dekhein | `owo rank` |
| `owo toprank` | Server ka **Competitive ELO Leaderboard** | `owo toprank` |
| `owo level` | Current Level aur XP progress dekhein | `owo level` |
| `owo give <@user> <amount>` | Kisi dost ko OwO Cash send karein | `owo give @user 1000` |
| `owo top` | Richest players ka server leaderboard | `owo top` |
