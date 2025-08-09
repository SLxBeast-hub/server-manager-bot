import discord
from discord.ext import commands, tasks
import re
import datetime

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==== CONFIG ====
VOICE_LOG_CHANNEL_ID = 1381914817656393891  # Put your voice log channel ID here
LEAVE_LOG_CHANNEL_ID = 1381914817656393891  # Put your leave log channel ID here
MUTE_DURATION = 60  # seconds

# Track muted users: user_id -> unmute_time (datetime)
muted_users = {}

# === UTILITIES ===

def clean_mentions(content):
    return re.sub(r"<@!?[0-9]+>", "", content).strip()

def now_utc():
    return datetime.datetime.utcnow()

def seconds_left(unmute_time):
    delta = (unmute_time - now_utc()).total_seconds()
    return max(0, int(delta))

# === MUTE MANAGEMENT ===

async def mute_user(user_id: int):
    unmute_time = now_utc() + datetime.timedelta(seconds=MUTE_DURATION)
    muted_users[user_id] = unmute_time

async def unmute_user(user_id: int):
    if user_id in muted_users:
        muted_users.pop(user_id)

@tasks.loop(seconds=5)
async def check_unmutes():
    to_unmute = [user_id for user_id, unmute_time in muted_users.items() if unmute_time <= now_utc()]
    for user_id in to_unmute:
        await unmute_user(user_id)
        # Find a guild and member to announce unmute
        for guild in bot.guilds:
            member = guild.get_member(user_id)
            if member:
                try:
                    await member.send(f"✅ You have been unmuted! You can send messages now.")
                except:
                    # Cannot DM member, ignore
                    pass
                # Optionally announce in a general channel or skip
                break

@bot.event
async def on_ready():
    print(f"✅ Bot reborn and online as {bot.user}")
    check_unmutes.start()

# === MAIN MESSAGE HANDLING ===

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    author = message.author
    author_id = author.id

    # Check if muted - block message + remind
    if author_id in muted_users:
        remaining = seconds_left(muted_users[author_id])
        if remaining > 0:
            await message.delete()
            await message.channel.send(
                f"{author.mention} 🚫 You are muted for another **{remaining} seconds** due to rule violation. Please wait patiently.",
                delete_after=8
            )
            return
        else:
            # Time expired, unmute user
            await unmute_user(author_id)

    # Mention detection (no reason given)
    if message.mentions:
        clean_content = clean_mentions(message.content)
        if len(clean_content) <= 6:  # no proper message after mention
            if author.guild_permissions.administrator:
                # Admin special: can't mute, but delete messages and warn
                if author_id not in muted_users:
                    # Temporarily "mute" admin by deleting messages for duration
                    muted_users[author_id] = now_utc() + datetime.timedelta(seconds=MUTE_DURATION)
                await message.channel.send(
                    f"# 🚫 {author.mention} STOP THAT SH*T!\n"
                    "You mentioned someone without giving a reason.\n"
                    f"⚠️ You're an admin, so I can't mute you, but your messages will be deleted for **{MUTE_DURATION} seconds**."
                )
                return
            else:
                # Normal user: mute them, delete message, send warning
                if author_id not in muted_users:
                    muted_users[author_id] = now_utc() + datetime.timedelta(seconds=MUTE_DURATION)
                await message.delete()
                await message.channel.send(
                    f"# 🚫 {author.mention} STOP THAT SH*T!\n"
                    "You mentioned someone without giving a reason.\n"
                    f"⏳ You are muted for **{MUTE_DURATION} seconds**."
                )
                return

    await bot.process_commands(message)

# === COMMANDS ===

@bot.command(name="say")
@commands.has_permissions(manage_messages=True)
async def say(ctx, *, msg: str):
    await ctx.message.delete()
    await ctx.send(msg)

@bot.command(name="embed")
@commands.has_permissions(manage_messages=True)
async def embed(ctx, color: str, *, msg: str):
    await ctx.message.delete()
    try:
        if color.startswith("#") and len(color) == 7:
            c = discord.Color(int(color[1:], 16))
        else:
            c = getattr(discord.Color, color.lower())()
    except Exception:
        c = discord.Color.blurple()
    embed_msg = discord.Embed(description=msg, color=c)
    await ctx.send(embed=embed_msg)

@bot.command(name="unmute")
@commands.has_permissions(administrator=True)
async def unmute(ctx, member: discord.Member):
    if member.id in muted_users:
        await unmute_user(member.id)
        await ctx.send(f"✅ {member.mention} has been unmuted early by {ctx.author.mention}.")
    else:
        await ctx.send(f"ℹ️ {member.mention} is not muted.")

# === VOICE LOGGING ===

@bot.event
async def on_voice_state_update(member, before, after):
    channel = bot.get_channel(VOICE_LOG_CHANNEL_ID)
    if channel is None:
        return

    if before.channel is None and after.channel is not None:
        await channel.send(f"🔊 {member.display_name} joined voice channel **{after.channel.name}**.")
    elif before.channel is not None and after.channel is None:
        await channel.send(f"🔇 {member.display_name} left voice channel **{before.channel.name}**.")
    elif before.channel != after.channel:
        await channel.send(f"🔄 {member.display_name} moved from **{before.channel.name}** to **{after.channel.name}**.")

# === MEMBER LEAVE LOG ===

@bot.event
async def on_member_remove(member):
    channel = bot.get_channel(LEAVE_LOG_CHANNEL_ID)
    if channel:
        await channel.send(f"❌ {member.display_name} left the server.")

# === RUN BOT ===

bot.run("BOT_TOKEN_HERE")
