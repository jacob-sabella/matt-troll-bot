"""
matt-troll-bot — Discord voice channel transcription bot.

Commands:
  !join [channel]   Join a voice channel (defaults to the author's current channel)
  !leave            Leave the current voice channel
  !status           Show whether the bot is listening and in which channel
"""

import asyncio
import logging
import os
import random
import tempfile
import time

import discord
import edge_tts
from discord.ext import commands
from discord.ext.voice_recv import VoiceRecvClient
from dotenv import load_dotenv

from audio_sink import TranscribingSink
from transcriber import Transcriber

# ---------------------------------------------------------------------------
# Matt greeting config
# ---------------------------------------------------------------------------
MATT_USER_ID = 137584893906386944
MATT_TTS_RATE = "-20%"
MATT_TTS_PITCH = "-8Hz"

# Curated pool of voices that sound good with the sultry rate/pitch settings
MATT_VOICES = [
    # American female
    "en-US-AriaNeural",
    "en-US-JennyNeural",
    "en-US-AvaNeural",
    "en-US-EmmaNeural",
    "en-US-MichelleNeural",
    # American male
    "en-US-GuyNeural",
    "en-US-BrianNeural",
    "en-US-EricNeural",
    "en-US-ChristopherNeural",
    # British female
    "en-GB-SoniaNeural",
    "en-GB-LibbyNeural",
    # British male
    "en-GB-RyanNeural",
    "en-GB-ThomasNeural",
    # Australian
    "en-AU-NatashaNeural",
    "en-NZ-MitchellNeural",
]

_voice_pool: list[str] = []

def _next_voice() -> str:
    global _voice_pool
    if not _voice_pool:
        _voice_pool = MATT_VOICES[:]
        random.shuffle(_voice_pool)
    return _voice_pool.pop()
MATT_GREET_DELAY = 2        # seconds after join before greeting
MATT_SILENCE_WAIT = 1.0     # seconds of channel silence required before speaking

MATT_GREETINGS = [
    # originals
    "damn matt you thick as hell with it",
    "oh matt, you just made this channel 10 times hotter",
    "well well well, look who decided to grace us with their presence",
    "matt has entered the chat and honestly? we are not worthy",
    "somebody call the fire department because matt just walked in",
    "matt you absolute snack, welcome",
    "the vibes just went up significantly and I think we all know why",
    "matt is here and I am legally obligated to fan myself",
    "oh good, matt's here, now the party can start",
    "matt you came in here looking like a whole meal and I am starving",
    "I didn't know angels used discord but here we are",
    "matt just joined and my heart rate has increased by a medically significant amount",
    "good lord matt, save some serotonin for the rest of us",
    "matt has arrived and the server's average attractiveness just skyrocketed",
    "every time matt joins an angel gets its wings and I get unreasonably flustered",
    "matt you walked in here like you owned the place and honestly, valid",
    "scientists have confirmed that matt joining a voice channel raises the room temperature by three degrees",
    "matt you are built different and I mean that in the most unhinged complimentary way possible",
    "the prophecy said a chosen one would join this channel and here we are",
    "matt I don't know what you're selling but I am absolutely buying it",
    "oh no, matt's here, everyone act normal, everyone act normal",
    "matt just joined and I suddenly remembered how to feel things",
    "alert, alert, a certified menace to my composure has entered the channel",
    "matt you absolute unit, welcome to the channel, please have mercy on us",
    "I was having a completely normal day and then matt showed up",
    # new — silly and spicy
    "matt you could step on me and I would say thank you",
    "the way matt just joined this channel should be illegal in at least twelve states",
    "matt your voice alone does things to me that I am not comfortable discussing in polite company",
    "oh good the hot one's here",
    "matt I would let you ruin my life and I mean that as a compliment",
    "matt you are so fine it's actually kind of rude",
    "every time matt speaks my brain just plays a little fanfare and shuts down",
    "matt you could read me terms and conditions and I would be into it",
    "I have been normal all day and then matt showed up and now I am not normal",
    "matt you absolute menace, do you have any idea what you do to people",
    "the audacity of matt to walk in here looking like that",
    "matt you are the human equivalent of a cold glass of water when you are very very thirsty",
    "matt if confidence were a crime you'd be doing life",
    "matt I would watch you do literally anything and call it entertainment",
    "the way matt exists is genuinely offensive to everyone around him",
    "matt your presence is a form of emotional warfare and I am losing",
    "I felt a disturbance in the force and then I realized matt had joined",
    "matt you could talk about literally nothing and I would hang on every word",
    "all rise, the court of getting absolutely demolished by someone's vibe is now in session",
    "matt I don't know what you had for breakfast but it is working",
    "matt you are built like a bad decision I would absolutely make again",
    "the sheer nerve of matt being that attractive on a tuesday",
    "matt you could whisper literally anything to me and I would simply combust",
    "matt has arrived and my prefrontal cortex has gone home for the day",
    "the founding fathers did not die for matt to be this distracting",
    "matt you are a public menace and I mean that with the utmost respect and attraction",
    "someone should have warned me that matt was joining because I was not emotionally prepared",
    "matt I would do your laundry, your taxes, and your bidding",
    "matt you are the reason I have trust issues with my own nervous system",
    "every brain cell I have just saw matt join and collectively agreed to clock out",
    "matt you could say absolutely nothing and still be the most compelling person in the room",
    "the fact that matt is just allowed to exist like this is a failure of the legal system",
    "matt your presence is aggressively attractive and I am filing a complaint",
    "I was minding my own business and then matt happened to me",
    "matt you are a certified weapon of mass distraction",
    "the way matt carries himself should come with a warning label",
    "matt I would simply die for you and I want that on record",
    "matt you are so unfairly hot it borders on a civil rights violation",
    "someone please come collect matt because he is doing damage in here",
    "matt if being ridiculously attractive was a job you'd be employee of the century",
    "matt I am going to need you to lower the intensity by about forty percent, I cannot handle this",
    "the lord said let there be light and then he made matt and honestly that was the better decision",
    "matt you are genuinely too much in the best possible way",
    "I don't know who raised matt but they should be studied",
    "matt has logged on and my situational awareness has logged off",
    "matt you are the reason my therapist has a boat",
    "I was a stable and functioning person until matt joined this channel",
    "matt you could read me a grocery list in that voice and I would cry a single tear",
    "the audacity, the nerve, the absolute gall of matt to be this attractive",
    "matt I genuinely cannot tell if you know what you do to people or if you are just built different",
    "matt you are a menace, a snack, a disaster, and a delight all at once",
    "every time matt speaks somewhere a person loses the ability to think critically",
    # filthy
    "matt I would let you destroy me and then write you a five star yelp review",
    "matt you could rearrange my spine and I would say please and thank you",
    "the things I would let matt do to me are between me, him, and my priest",
    "matt you could wreck my entire life from the inside out and I would be grateful",
    "I would let matt use me as a pillow, a punching bag, or whatever else he had in mind",
    "matt I would let you do things to me that are not legal in several countries and I would bring the paperwork",
    "matt you could have me any way you want me and I mean that with zero exceptions",
    "the thoughts I am having about matt right now are deeply inappropriate and I stand by all of them",
    "matt I would let you ruin me thoroughly and then brag about it",
    "if matt asked me to get on my knees I would ask which ones",
    "matt you could bend me like a pretzel and I would thank you for the flexibility training",
    "I would let matt wreck me like a rental car with no insurance",
    "matt I would do unspeakable things just to be in the same room as you",
    "the absolutely filthy things I would let matt do to me would make a sailor blush",
    "matt you could use me however you saw fit and I would rate the experience ten out of ten",
    "I would let matt absolutely demolish me and then tip him afterward",
    "matt I would let you have your way with me and then send a handwritten thank you note",
    "if matt looked at me the way I want him to I would simply cease to function as a person",
    "matt I would let you do me dirty in every sense of the phrase",
    "the freaky things I would do with matt are not suitable for this or any other channel",
    "matt you could ruin me six ways from sunday and I would circle back for more",
    "I would let matt tear me apart like fresh bread and I mean that sexually",
    "matt I would let you have me on every surface in this building and some outside ones",
    "the level of depraved nonsense I would enthusiastically do with matt is frankly alarming",
    "matt I would let you take me apart piece by piece and put me back together wrong",
    "I would let matt do things to me that would make god close his eyes and look away",
    # batch 2 — silly and thirsty
    "matt you just walked in and every rational thought I had immediately submitted its resignation",
    "the confidence matt carries himself with is actually making me dizzy",
    "matt I would let you give me bad advice and I would follow it enthusiastically",
    "someone in this channel just got a lot more attractive and it was not me",
    "matt you could charge admission for just existing and I would pay it",
    "the way matt said nothing and still somehow said everything",
    "matt you are the reason the phrase trouble with a capital T was invented",
    "I need everyone to be quiet because matt just joined and I am trying to compose myself",
    "matt you are aggressively, offensively, and unreasonably attractive and I think you owe us an apology",
    "the government should regulate how attractive matt is allowed to be in public spaces",
    "matt I would let you gaslight me and I would thank you for the experience",
    "every time matt talks my IQ drops by a statistically significant amount and I am fine with that",
    "matt you are like a natural disaster and I mean that as the highest possible compliment",
    "I had plans today and then matt showed up and now I have different plans",
    "matt you are the human equivalent of a song that gets stuck in your head and you don't even mind",
    "somebody notify the authorities because matt is out here being dangerously attractive again",
    "matt you have no right to sound like that and look like that simultaneously it is too much",
    "I don't make the rules but if I did one of them would be that matt has to warn us before joining",
    "matt you absolute disaster, I mean that with love and also barely contained attraction",
    "the sheer audacity of matt to be this compelling without even trying",
    "matt I would let you make every decision in my life and I would not question a single one",
    "I was completely unbothered until approximately the moment matt joined",
    "matt you are genuinely a problem and I am not interested in solutions",
    "the way matt exists in a room is actually unfair to the other people in it",
    "matt you could critique everything about me and I would take notes and say thank you",
    "I have never been more aware of another person's presence than I am of matt's right now",
    "matt you are what scientists mean when they talk about a force of nature",
    "whoever is responsible for matt needs to come forward immediately",
    "matt you are so dangerously charming it should come with a hazard warning",
    "I was doing just fine until matt happened and now I am not doing just fine",
    "matt you are the reason people lose the ability to form coherent sentences",
    "the way matt walks into a channel like he invented it is sending me",
    "matt I don't know what you're on but I would like some",
    "everything was fine and normal and then matt showed up and now it is neither of those things",
    "matt you are operating at an attractiveness level that is frankly irresponsible",
    "I am going to need a minute because matt just joined and my body is processing information",
    "matt you are so hot it is actually inconvenient for everyone around you",
    "the audacity of matt to have a voice like that and a face like that at the same time",
    "matt you could disappoint me and I would still show up for round two",
    "I feel personally victimized by how attractive matt is and I am considering legal action",
    "matt you are the kind of problem I would actively seek out",
    "someone alert the surgeon general because matt's presence is affecting my health",
    "matt I would let you be mean to me and then I would apologize to you about it",
    "the way matt joined without any warning and just started doing damage",
    "matt has arrived and my ability to function as an adult has departed",
    "I would follow matt into genuinely terrible decisions and call it an adventure",
    "matt you could tell me the sky is green and I would look outside to double check",
    "every version of me across every possible timeline would be perceived by matt's vibe",
    "matt you are so fine that looking directly at you should require protective eyewear",
    "I had a whole personality before matt joined and I'm not sure where it went",
    # batch 2 — filthy
    "matt I would let you use me like a scratching post and say thank you from the bottom of my heart",
    "the things I want matt to do to me are so filthy they would demonetize this channel",
    "matt I would let you have me bent in half and consider it a spiritual experience",
    "I would let matt wreck me so thoroughly I'd need a week to recover and I'd spend that week thinking about round two",
    "matt I would let you do things to me that I have not even admitted to myself that I want",
    "the level of depraved and enthusiastic cooperation I would offer matt is staggering",
    "matt you could take me apart with your bare hands and I would hand you the tools",
    "I would let matt ruin every other experience for me and call it worth it",
    "matt I would let you have me in ways that would make my ancestors uncomfortable",
    "the filthy things I have thought about matt in the last thirty seconds alone could fill a novel",
    "matt I would let you destroy me slowly and thank you after each individual piece",
    "I would let matt do to me what he does to this channel's collective composure",
    "matt you could have me any which way and I would rate every single one of them five stars",
    "the things I would do to get five minutes alone with matt would raise eyebrows at the hague",
    "matt I would let you make a complete mess of me and then beg you to do it again",
    "I would let matt wring me out like a dishcloth and ask if he needed anything else",
    "matt I would let you absolutely desecrate me and write you a glowing reference afterward",
    "the specific and detailed things I want matt to do to me are between me and my search history",
    "matt you could have me screaming your name and I would not even be embarrassed about it",
    "I would let matt use me up completely and then thank him for his time and effort",
    "matt I would let you leave marks on me and wear them like a badge of honor",
    "the sheer enthusiasm with which I would let matt do absolutely anything to me is frankly alarming",
    "matt I would let you have me so thoroughly that I forget my own name and I think that sounds amazing",
    "I would let matt destroy me on every available surface and then help him pick the next one",
    "matt I would let you do your worst and my worst would be begging you not to stop",
    "the things I would let matt do to me in this channel alone should not be spoken aloud",
    "matt you could absolutely rail me into next week and I would block off my calendar in advance",
    "I would let matt ruin me so completely that I'd have to be reassembled and he would be welcome to help with that too",
    "matt I would let you have me in ways that would make a romance novelist put down their pen in defeat",
    "the absolutely unhinged and enthusiastic things I would let matt do to me are not suitable for any channel",
    "matt I would let you thoroughly and completely wreck me and then give you a standing ovation",
    # batch 3 — raunchy
    "matt you could bend me over the discord tos and I would not read a single clause",
    "I would let matt put his hands on me in ways that would make my chiropractor raise an eyebrow",
    "matt you could manhandle me like checked luggage and I would pack accordingly",
    "the specific and creative things matt could do to me are between me, him, and my browser history",
    "matt I would let you choke the words out of me and then ask you to do it again for clarity",
    "I would let matt work up a sweat using me as the equipment",
    "matt you could have me begging so fast I would break my own personal record",
    "I want matt to press me up against something flat and hard and I'll let him decide what",
    "matt you could tie me to the bedpost and go get a snack and I would wait patiently",
    "I would let matt put me on my knees and take his time deciding what to do next",
    "matt could pin my wrists above my head and tell me to hold still and I would try so very hard",
    "I would let matt use his mouth on me until I forgot what language I speak",
    "matt you could hold me down by the throat and look at me like that and I would simply evaporate",
    "I would let matt flip me around like a rag doll and I would go completely limp to make it easier",
    "matt you could have me dripping before you even touched me just by walking in like that",
    "I would let matt edge me until I lost my entire mind and then denied me until I found it again",
    "matt you could pull my hair, bite my neck, and ruin my evening plans and I'd reschedule everything",
    "I would let matt make me cry in the good way and then keep going while I cried",
    "matt you could use me as a toy, put me away, and I'd still be smiling in the box",
    "I would let matt do things to me that would require a safety briefing and a waiver",
    "matt you could have me on all fours pointing in whatever direction you wanted",
    "I would let matt grab my hips with both hands and redirect me like a shopping cart",
    "matt you could leave marks on me and I would show them off like a participation trophy",
    "I would let matt whisper exactly what he's about to do to me and then do it slower than described",
    "matt could sit me in his lap facing away and I would not make a single complaint",
    "I would let matt overstimulate me until I tapped out and then I would un-tap and ask for more",
    "matt you could have me making sounds that would concern the neighbors and I'd be thrilled",
    "I would let matt wreck me so thoroughly that I'd need a day off work to recover and I would use that PTO with zero regret",
    "matt you could own me for one evening and I would renegotiate the terms to extend it",
    "I would let matt do absolutely filthy things to me and then ask him to sign my highlight reel",
    "matt you could rearrange my entire life from the inside out and I would help you with the heavy lifting",
    "I would let matt make me lose count and start over at one every single time",
    "matt you could have me desperate and incoherent and then have the nerve to look proud of yourself, which you should be",
    "I would let matt be completely rough with me and completely gentle after and that one-two combination would end me",
    "matt you could destroy me six ways and I would ask which seven, eight, and nine look like",
    "I would let matt rail me so thoroughly that future historians would mark it as a before and after",
    "matt could look me dead in the eyes while doing the most unspeakable things and I would not blink first",
    "I would let matt put me in every position he could think of and help him think of more",
    "matt you could have me shaking before you even started and smug about it the whole time and I would deserve both",
    "I would let matt take me apart at the seams and put me back together slightly wrong and I would prefer it",
    # uwu cringe speak (written for TTS pronunciation)
    "matt senpai has noticed us and my heart is going doki doki",
    "a wild matt has appeared and my kokoro simply cannot handle it",
    "matt kun you cannot just walk in here looking like that, it is not fair to the rest of us",
    "matt senpai please step on me, this is not a joke, I am fully serious",
    "hello matt, I baked you treats, they are heart shaped, please notice me senpai",
    "matt you absolute unit, this one is going completely feral, thank you for your service",
    "matt kun you make my heart go doki doki and also several other parts of me go other things",
    "I am going to need matt senpai to, with all due respect, absolutely wreck me into next week",
    "matt you are so handsome it makes me want to write embarrassingly detailed fan fiction about you",
    "please matt senpai, I have been so good, I deserve headpats and also several other things",
    "matt I wrote nineteen pages of self insert fan fiction about you last night and I have zero regrets",
    "matt you just made my tail wag and I do not even have a tail, that is how powerful your presence is",
    "matt senpai your aura is immaculate and I am flustered in at least seven languages",
    "hello matt kun, I knitted you a sweater, it says I would let you wreck me, in cursive, as a treat",
    "matt has noticed me and I am now vibrating at a frequency only dogs can hear",
    "matt you are my comfort character, my roman empire, and the reason I cannot sleep, senpai please",
    "matt senpai please look this way, I have been practicing my most pathetic expression specifically for this",
    "I would let matt give me headpats and also immediately after that, the complete opposite of headpats",
    "matt kun I drew fan art of you, it is very flattering, I will not be showing it to anyone, senpai notice me",
    "matt you have activated my fight or flight response and I have chosen a surprising third option, senpai",
]

# Shuffled pool — refills automatically when exhausted
_greeting_pool: list[str] = []

def _next_greeting() -> str:
    global _greeting_pool
    if not _greeting_pool:
        _greeting_pool = MATT_GREETINGS[:]
        random.shuffle(_greeting_pool)
    return _greeting_pool.pop()

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# Suppress noisy INFO spam from library internals
logging.getLogger("discord.ext.voice_recv.gateway").setLevel(logging.WARNING)
logging.getLogger("discord.ext.voice_recv.reader").setLevel(logging.WARNING)

# The router thread raises OpusError("corrupted stream") when a user disconnects mid-packet.
# Demote those to DEBUG so they don't clutter the output.
class _SuppressOpusCorrupted(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "corrupted stream" not in (record.getMessage())

logging.getLogger("discord.ext.voice_recv.router").addFilter(_SuppressOpusCorrupted())
log = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
transcriber: Transcriber | None = None

# guild_id → TranscribingSink, so the voice-state event can reach the active sink
active_sinks: dict[int, TranscribingSink] = {}
# guild_id → periodic greeter task
active_periodic_tasks: dict[int, asyncio.Task] = {}

MATT_PERIODIC_INTERVAL = 600  # seconds between periodic greetings (10 minutes)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

@bot.event
async def on_ready():
    global transcriber
    log.info("Logged in as %s (id=%s)", bot.user, bot.user.id)
    transcriber = Transcriber()


# ---------------------------------------------------------------------------
# Utterance handler — called by the sink for each completed utterance
# ---------------------------------------------------------------------------

async def handle_utterance(user, pcm_bytes: bytes) -> None:
    name = getattr(user, "display_name", str(getattr(user, "id", "unknown")))
    log.info("Transcribing utterance from %s (%d bytes)...", name, len(pcm_bytes))

    if transcriber is None:
        return

    loop = asyncio.get_running_loop()
    text = await loop.run_in_executor(None, transcriber.transcribe, pcm_bytes)

    if not text:
        log.debug("No speech detected in utterance from %s.", name)
        return

    message = f"**{name}**: {text}"
    log.info(message)

    # Optionally post to a text channel
    channel_id_str = os.getenv("TRANSCRIPT_CHANNEL_ID", "").strip()
    if channel_id_str:
        channel = bot.get_channel(int(channel_id_str))
        if channel:
            await channel.send(message)

    # Trigger a greeting if anyone says the magic words
    if "we love matt" in text.lower():
        guild = getattr(getattr(user, "guild", None), "id", None)
        if guild is None:
            # fall back: find whichever guild the bot is in a voice channel for
            for vc in bot.voice_clients:
                guild = vc.guild.id
                break
        if guild is not None:
            vc = bot.get_guild(guild).voice_client
            if vc and vc.is_connected():
                log.info("'we love matt' detected — triggering greeting.")
                asyncio.create_task(_play_greeting(vc, guild))


# ---------------------------------------------------------------------------
# Matt greeting logic
# ---------------------------------------------------------------------------

async def _generate_tts(text: str, voice: str, rate: str, pitch: str) -> str:
    """Generate TTS audio via edge-tts and return the path to a temp mp3 file."""
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    await communicate.save(tmp.name)
    return tmp.name


async def _wait_for_silence(guild_id: int) -> None:
    """Block until the channel has been silent for MATT_SILENCE_WAIT seconds."""
    sink = active_sinks.get(guild_id)
    if sink is None:
        return
    while True:
        if time.monotonic() - sink.last_audio_at >= MATT_SILENCE_WAIT:
            break
        await asyncio.sleep(0.1)


async def _play_greeting(vc: VoiceRecvClient, guild_id: int) -> None:
    """Wait for silence, then generate and play the next greeting from the pool."""
    await _wait_for_silence(guild_id)

    if not vc.is_connected():
        return

    greeting = _next_greeting()
    voice = _next_voice()
    log.info("Playing greeting [%s]: %s", voice, greeting)
    audio_path = await _generate_tts(greeting, voice, MATT_TTS_RATE, MATT_TTS_PITCH)

    def _cleanup(err):
        try:
            os.unlink(audio_path)
        except OSError:
            pass
        if err:
            log.error("Error playing greeting: %s", err)

    if not vc.is_playing():
        vc.play(discord.FFmpegPCMAudio(audio_path), after=_cleanup)


async def _greet_matt_on_join(vc: VoiceRecvClient, guild_id: int) -> None:
    log.info("Matt joined — greeting in %ds...", MATT_GREET_DELAY)
    await asyncio.sleep(MATT_GREET_DELAY)
    await _play_greeting(vc, guild_id)


async def _periodic_greeter(vc: VoiceRecvClient, guild_id: int) -> None:
    """Every MATT_PERIODIC_INTERVAL seconds, if Matt is in the channel, play a greeting."""
    while True:
        await asyncio.sleep(MATT_PERIODIC_INTERVAL)
        if not vc.is_connected():
            break
        matt_present = any(m.id == MATT_USER_ID for m in vc.channel.members)
        if not matt_present:
            log.debug("Periodic greeter: Matt not in channel, skipping.")
            continue
        log.info("Periodic greeter firing.")
        await _play_greeting(vc, guild_id)


@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
    if member.id != MATT_USER_ID:
        return
    # Only fire on actually joining a channel (not mute/deafen/move within same channel)
    if after.channel is None or before.channel == after.channel:
        return

    guild_vc = member.guild.voice_client
    if guild_vc is None or guild_vc.channel != after.channel:
        return  # Bot isn't in that channel

    asyncio.create_task(_greet_matt_on_join(guild_vc, member.guild.id))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@bot.command(name="join")
async def join(ctx: commands.Context, *, channel_name: str | None = None):
    """Join a voice channel. Defaults to the channel you're currently in."""
    if channel_name:
        voice_channel = discord.utils.get(ctx.guild.voice_channels, name=channel_name)
        if not voice_channel:
            await ctx.send(f"Couldn't find a voice channel named **{channel_name}**.")
            return
    elif ctx.author.voice:
        voice_channel = ctx.author.voice.channel
    else:
        await ctx.send("You're not in a voice channel. Use `!join <channel name>`.")
        return

    if ctx.voice_client:
        await ctx.voice_client.disconnect(force=False)

    vc: VoiceRecvClient = await voice_channel.connect(cls=VoiceRecvClient)

    sink = TranscribingSink(on_utterance=handle_utterance, loop=asyncio.get_event_loop())
    vc.listen(sink)
    sink.start_flush_loop()
    active_sinks[ctx.guild.id] = sink

    periodic = asyncio.create_task(_periodic_greeter(vc, ctx.guild.id))
    active_periodic_tasks[ctx.guild.id] = periodic

    await ctx.send(f"Joined **{voice_channel.name}** and started transcribing.")
    log.info("Joined voice channel: %s", voice_channel.name)


@bot.command(name="leave")
async def leave(ctx: commands.Context):
    """Leave the current voice channel."""
    if not ctx.voice_client:
        await ctx.send("I'm not in a voice channel.")
        return

    channel_name = ctx.voice_client.channel.name
    await ctx.voice_client.disconnect(force=False)
    active_sinks.pop(ctx.guild.id, None)
    task = active_periodic_tasks.pop(ctx.guild.id, None)
    if task:
        task.cancel()
    await ctx.send(f"Left **{channel_name}**.")
    log.info("Left voice channel: %s", channel_name)


@bot.command(name="love_matt")
async def love_matt(ctx: commands.Context):
    """Manually fire a greeting at Matt right now."""
    if not ctx.voice_client or not ctx.voice_client.is_connected():
        await ctx.send("I'm not in a voice channel.")
        return
    asyncio.create_task(_play_greeting(ctx.voice_client, ctx.guild.id))


@bot.command(name="status")
async def status(ctx: commands.Context):
    """Show whether the bot is currently listening."""
    if ctx.voice_client and ctx.voice_client.is_connected():
        await ctx.send(f"Listening in **{ctx.voice_client.channel.name}**.")
    else:
        await ctx.send("Not currently in a voice channel.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set. Copy .env.example to .env and fill it in.")
    # log_handler=None disables discord.py's automatic handler so we don't get double lines
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
