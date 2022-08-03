import typing
import discord

import mysql.connector as mysql

from discord.ext import commands
from mysql.connector.cursor import MySQLCursor

# Edit before running the file
DATABASE_INFO: dict = {"host": ..., "database": ..., "user": ..., "password": ...}
TOKEN: str = ... # type: ignore
BOT_ID: int = ... # type: ignore
COMMAND_PREFIX: str = ... # type: ignore

class CounterBot(commands.Bot):

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        self.db: mysql.MySQLConnection = mysql.connect(**DATABASE_INFO)
        self.cursor: MySQLCursor = self.db.cursor()

        super().__init__(command_prefix=COMMAND_PREFIX, intents=intents, application_id=BOT_ID, case_insensitive=True)
    
    @property
    def channels(self) -> list:
        """
        Returns all active Counter channels
        """
        self.cursor.execute('SELECT `channel_id` FROM `counter`')
        return list(i[0] for i in self.cursor.fetchall())

    async def setup_hook(self) -> None:
        self.add_command(_scoreboard)
        self.add_command(_start)
        self.add_command(_stop)

    async def on_ready(self) -> None:
        print(f"Bot Ready: {self.user.name}")

    async def on_message(self, msg: discord.Message, /) -> None:

        if msg.author.bot:
            return

        await self.process_commands(msg)
        
        if msg.channel.id not in self.channels:
            return
        
        if not msg.content.isdigit():
            return await msg.delete() # Non numerical messages are deleted
        
        self.cursor.execute("SELECT `count`, `last_user_id` FROM `counter` WHERE `channel_id` = %s;", (msg.channel.id,))
        (count, last_user_id) = self.cursor.fetchone()

        if last_user_id == msg.author.id: # Not allowed to count by yourself
            return await msg.delete()

        sub_count = int(msg.content)

        if count + 1 == sub_count:
            self.cursor.execute("INSERT INTO `counter` (`channel_id`, `count`, `last_user_id`) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE `count` = `count` + 1, `last_user_id` = %s;", (msg.channel.id, count + 1, msg.author.id, msg.author.id))
            self.db.commit()
            self.cursor.execute("INSERT INTO `leaderboard` (`channel_id`, `user_id`, `score`) VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE `score` = `score` + 1;", (msg.channel.id, msg.author.id, 1))
            self.db.commit()
        else:
            await msg.delete() # Counting increments by one
    
    async def on_command_error(self, context: commands.Context, exception: commands.errors.CommandError, /) -> None:
        """
        Command Error Handler; ignoring a few common irrelevant errors
        """
        
        if isinstance(exception, commands.errors.CommandNotFound):
            return
        
        elif isinstance(exception, commands.errors.MissingPermissions):
            return 
        
        elif isinstance(exception, commands.errors.MissingRequiredArgument):
            return
        
        else:
            raise exception

class CounterBotContext(commands.Context):
    """
    Custom Context for commands.Context.bot type annotation
    """

    @property
    def bot(self) -> CounterBot:
        return self.bot

@commands.command(name='start')
@commands.has_permissions(manage_messages=True)
async def _start(ctx: CounterBotContext, slowmode: bool = True):
    """
    Initiate channel for Counting, CounterBot replies with '0' as confirmation
    """
    if ctx.channel.id in ctx.bot.channels:
        return
    
    if slowmode:
        try:
            await ctx.channel.edit(slowmode_delay=1, reason='Initiating Counter Channel, adding slowmode against spam')
        except discord.errors.Forbidden:
            pass

    ctx.bot.cursor.execute("INSERT `counter` (`channel_id`, `count`, `last_user_id`) VALUES (%s, %s, %s)", (ctx.channel.id, 0, ctx.bot.user.id))
    ctx.bot.db.commit()
    await ctx.send('0')

@commands.command(name='stop')
@commands.has_permissions(manage_messages=True)
async def _stop(ctx: CounterBotContext):
    """
    Remove channel for Counter, CounterBot replies with '👌' as confirmation
    """

    if ctx.channel.id not in ctx.bot.channels:
        return

    try:
        await ctx.channel.edit(slowmode_delay=0, reason='Removing Counter Channel, removing slowmode')
    except discord.errors.Forbidden:
        pass
    
    ctx.bot.cursor.execute("DELETE FROM `counter` WHERE `channel_id` = %s;", (ctx.channel.id,))
    ctx.bot.db.commit()
    await ctx.send('\U0001f44c')

@commands.command(name='leaderboard', aliases=['lb', 'sc', 'leaderboard'])
async def _scoreboard(ctx: CounterBotContext, channel: typing.Optional[discord.TextChannel]):
    """
    Display leaderboard for a Counter channel.
    param channel: defaults to ctx.channel
    """

    channel = channel or ctx.channel

    ctx.bot.cursor.execute("SELECT `user_id`,`score` FROM `leaderboard` WHERE `channel_id` = %s ORDER BY score DESC LIMIT 15;", (channel.id,))
    scores = ctx.bot.cursor.fetchall()

    if not scores:
        return

    author_score = False
    lb_prefix = ['🥇', '🥈', '🥉'] + [str(i) for i in range(4, 16)]
    e = discord.Embed(title=f'Scoreboard for {channel.name}', colour=0x8a2be2)

    desc = ""
    
    for index, (user_id, score) in enumerate(scores):
        desc += f'{lb_prefix[index]}: <@{user_id}> - **{score}**\n'
        if user_id == ctx.author.id:
            author_score = True
    
    if not author_score: # If author isn't in the top 15 -> add extra line with score
        ctx.bot.cursor.execute("SELECT `score` FROM `leaderboard` WHERE `channel_id`  = %s AND `user_id` = %s;", (ctx.channel.id, ctx.author.id))
        score = ctx.bot.cursor.fetchone()

        if score:
            desc += f'Your score: {score}'
    
    e.description = desc

    await ctx.send(embed=e)

bot = CounterBot()
bot.run(TOKEN)