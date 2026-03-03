"""
matt-troll-bot — Discord voice channel transcription bot.

Commands:
  !join [channel]   Join a voice channel (defaults to the author's current channel)
  !leave            Leave the current voice channel
  !hate_matt        Send a playful roast aimed at Matt
  !hate_matt_voice  Play a playful roast in voice chat only
  !matt_moan        Play a chaotic Matt moan line in voice chat only
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
MATT_ROAST_TTS_RATE = "-5%"
MATT_ROAST_TTS_PITCH = "-4Hz"
MATT_MOAN_TTS_RATE = "-10%"
MATT_MOAN_TTS_PITCH = "+6Hz"

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
    # batch 4 — uncomfortably loving
    "matt we are way past a crush, this is a full-scale emotional occupation",
    "matt we love you so much it has become a public infrastructure issue",
    "matt the devotion levels in this channel are now legally suspicious",
    "matt we did not choose this level of affection, it chose us and it is violent",
    "matt we want you bad, respectfully, chaotically, and with full civic commitment",
    "matt you are the reason we all believe in destiny and poor judgment",
    "matt if love was a sport we would all retire your jersey",
    "matt this is no longer admiration, this is a full department with a budget",
    "matt we would write your name into every song if we could hold a note",
    "matt we are one compliment away from forming a cult in your honor",
    "matt we would cross oceans, deserts, and group chats just to hear you say hi",
    "matt you have ruined our standards and we are not seeking recovery",
    "matt we carry your memory like a password we use every day",
    "matt the level of yearning in here could power a small city",
    "matt we are profoundly, aggressively, and permanently down bad for you",
    "matt this channel has become a fan club and nobody remembers voting on it",
    "matt we rehearse fake conversations with you and still get flustered",
    "matt we talk about you like a historical event with chapters",
    "matt we would let you interrupt us mid sentence and thank you for the privilege",
    "matt every version of us in every timeline is still obsessed with you",
    "matt we would frame your text messages like museum artifacts",
    "matt this is not a phase, this is a lifestyle and a scheduling conflict",
    "matt we would happily be emotionally inconvenienced by you forever",
    "matt we are down catastrophic and still somehow asking for more",
    "matt we love you with the intensity of people who have not slept enough",
    "matt we would fight destiny itself for one extra minute of your attention",
    "matt this level of affection should come with a warning siren",
    "matt we built a whole emotional ecosystem around your existence",
    "matt we are deeply unwell about you and calling it character development",
    "matt we are not just into you, we are writing policy around it",
    "matt we would memorize your grocery list like sacred poetry",
    "matt if devotion had a leaderboard this channel would be permanently first place",
    "matt we are so attached we treat your online status like weather alerts",
    "matt one hello from you and our entire week gets reassigned to joy",
    "matt this love is so loud it should have its own push notification sound",
    "matt we are spiritually clingy and emotionally booked for the rest of your life",
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


MATT_ROASTS = [
    "matt has the confidence of a man who has never read his own typo-ridden texts.",
    "matt's strongest skill is turning a good plan into a group project.",
    "matt brings big main-character energy and side-quest execution.",
    "matt argues with autocorrect and still loses.",
    "matt is proof that charisma can exist without attention to detail.",
    "matt talks in bullet points and somehow still forgets the point.",
    "matt has premium taste and free-trial follow-through.",
    "matt enters a room like a keynote speaker and leaves like a software update.",
    "matt can make any topic about himself in under two business minutes.",
    "matt has a PhD in confidence and a minor in avoidable mistakes.",
    "matt gives strong final-boss dialogue with tutorial-level decisions.",
    "matt thinks out loud and calls it a strategy meeting.",
    "matt is the kind of person who says no offense right before proving otherwise.",
    "matt could get lost in a one-way hallway and still blame the architect.",
    "matt is wildly consistent at being almost right.",
    "matt has the aura of a genius and the browser history of a confused intern.",
    "matt's plans come with excellent branding and optional realism.",
    "matt has perfect timing for all the wrong moments.",
    "matt can turn constructive feedback into a dramatic monologue.",
    "matt is like a plot twist nobody asked for but everyone now has to process.",
    "matt has elite confidence and public beta judgment.",
    "matt treats common sense like an optional plugin.",
    "matt is what happens when momentum outruns quality control.",
    "matt could overcomplicate a sandwich order and call it optimization.",
    "matt always brings ideas, just not always the finished version.",
    "matt treats feedback like a loading icon and waits for it to disappear.",
    "matt has elite confidence and clearance-rack execution.",
    "matt's ideas arrive with a trailer and no actual movie.",
    "matt is living proof that loud does not mean right.",
    "matt could fumble a slam dunk in an empty gym.",
    "matt gives inspirational quote energy and expired coupon outcomes.",
    "matt turns easy tasks into cautionary tales with timestamps.",
    "matt speaks in certainty and delivers in maybe.",
    "matt has the strategic depth of a puddle in july.",
    "matt can miss the point from any distance.",
    "matt's confidence is first class and his results are carry-on only.",
    "matt runs his mouth like a marathon and his logic like a sprint to nowhere.",
    "matt is the only person who can overthink and underperform simultaneously.",
    "matt's takes have the shelf life of warm sushi.",
    "matt has the vibe of a mastermind and the receipts of a guess.",
    "matt makes simple look difficult and difficult look impossible.",
    "matt would lose a debate with his own search history.",
    "matt has premium swagger and economy-class judgment.",
    "matt's follow-through is on vacation with no return date.",
    "matt talks like a blueprint and builds like loose parts.",
    "matt has all the confidence of a prophet and all the accuracy of a coin flip.",
    "matt shows up with an empire mindset and intern-level outcomes.",
    "matt's consistency is impressive if the target is avoidable mistakes.",
    "matt overpromises like it is cardio.",
    "matt has the precision of a dart thrown in the dark.",
    "matt could derail a one-sentence plan.",
]

_roast_pool: list[str] = []


def _next_roast() -> str:
    global _roast_pool
    if not _roast_pool:
        _roast_pool = MATT_ROASTS[:]
        random.shuffle(_roast_pool)
    return _roast_pool.pop()


MATT_VOICE_ROASTS = [
    "matt your aura is in the negatives and the graph is still dropping.",
    "matt you are built like a bad update with no patch notes.",
    "matt your takes are so cooked even air fryers are judging you.",
    "matt is the CEO of talking first and thinking never.",
    "matt you are all confidence and zero receipts.",
    "matt is giving premium delusion with budget execution.",
    "matt your vibe is off brand and out of stock.",
    "matt you are chronically loud and historically wrong.",
    "matt got that unskippable ad personality.",
    "matt you are not the main character, you are the buffering icon.",
    "matt your decisions look AI generated in a bad way.",
    "matt you have the reaction speed of internet explorer on hotel wifi.",
    "matt you are a walking L with subtitles.",
    "matt your whole strategy is vibes and avoidable errors.",
    "matt is the human version of a typo in a tattoo.",
    "matt your confidence writes checks your talent keeps bouncing.",
    "matt got that no thoughts, just volume build.",
    "matt your logic is fan fiction with plot holes.",
    "matt you are one more bad take away from a fraud documentary.",
    "matt your brain is on airplane mode during conversations.",
    "matt you move like an NPC that lost its quest marker.",
    "matt your clapbacks come in 240p.",
    "matt you got ratioed by your own common sense.",
    "matt your aura took a personal day and never came back.",
    "matt talks like he is him and performs like he is a maybe.",
    "matt your plans are basically trust me bro in powerpoint form.",
    "matt your last three takes were all jump scares.",
    "matt is all gas, no steering wheel.",
    "matt your social battery is full and your judgment is dead.",
    "matt you are proof that volume is not intelligence.",
    "matt your comebacks have loading screens.",
    "matt got that final boss ego and tutorial level skill tree.",
    "matt your entire personality is a push notification nobody opened.",
    "matt you are what happens when confidence outruns competence.",
    "matt your ideas arrive half baked and still overcooked.",
    "matt is yapping in 4k and thinking in 144p.",
    "matt your vibe check failed with critical damage.",
    "matt you are all cap with extra cap on the side.",
    "matt your emotional intelligence is in power saving mode.",
    "matt you are peak cornball behavior with deluxe packaging.",
    "matt your attention span loses fistfights with doorbells.",
    "matt you got that fake deep podcast energy.",
    "matt your takes are so mid they are underground.",
    "matt your confidence is loud because your results are quiet.",
    "matt is somehow both extra and underwhelming at once.",
    "matt your thought process has pop up ads.",
    "matt you are giving group project ghoster energy.",
    "matt your humility got evicted years ago.",
    "matt is built like a red flag starter pack.",
    "matt your aura score is a decimal.",
    "matt your brain keeps buffering at the important parts.",
    "matt you are one podcast mic away from full delulu.",
    "matt your opinions are loud, wrong, and weirdly rehearsed.",
    "matt got that motivational speaker voice with cautionary tale outcomes.",
    "matt your confidence is sponsored by denial.",
    "matt is a professional at missing the point with passion.",
    "matt your decisions need adult supervision.",
    "matt you are a beta test nobody signed up for.",
    "matt your self awareness logged out.",
    "matt your best argument is just repeating yourself louder.",
    "matt you talk like a threat and execute like a warning label.",
    "matt your brain is basically running background apps only.",
    "matt got that off brand sigma energy from temu.",
    "matt you are the reason instructions say read carefully.",
    "matt your comeback game is weak and delayed.",
    "matt your aura is in airplane mode and still causing turbulence.",
    "matt is all plot armor and no skill points.",
    "matt your confidence is a straight up clerical error.",
    "matt your takes sound like they were approved by no one.",
    "matt you are permanently one step behind and two steps louder.",
    "matt your personality is a chain email from 2009.",
    "matt you are yappuccino supreme with no substance foam.",
    "matt got that try hard menace energy with beginner outcomes.",
    "matt you speak fluent nonsense with a fake accent of authority.",
    "matt your vibe is walmart villain arc.",
    "matt your thought process is a maze with no cheese.",
    "matt you are aggressively average with elite self marketing.",
    "matt your aura expired and nobody renewed it.",
    "matt is speedrunning bad impressions.",
    "matt your entire brand is confidence without quality control.",
    "matt got dragged by reality and still asked for round two.",
    "matt your common sense is in witness protection.",
    "matt you are the definition of loud wrong.",
    "matt your takes are so stale they crunch.",
    "matt got that villain monologue with side character impact.",
    "matt your patience is low and your ego is overclocked.",
    "matt your brain has too many tabs and none are useful.",
    "matt is a certified yapper with counterfeit wisdom.",
    "matt your aura has unpaid parking tickets.",
    "matt your logic is duct tape and vibes.",
    "matt you are a walking red flag with bluetooth speakers.",
    "matt your timing is elite if the goal is maximum cringe.",
    "matt you are emotionally sponsored by bad decisions.",
    "matt your ideas look confident until anyone asks why.",
    "matt got that no filter, no framework combo.",
    "matt your whole thing is giving rejected reality show finalist.",
    "matt your strategy is panic with branding.",
    "matt your communication style is volume based warfare.",
    "matt you are a cautionary tale with good hair.",
    "matt your aura score just got ratioed by silence.",
    "matt got no chill and negative shame.",
    "matt your ego is writing fan mail to itself.",
    "matt you are one terrible take away from a jump scare compilation.",
    "matt your self confidence should come with a legal disclaimer.",
    "matt your plot is thick but your character development is thin.",
    "matt you are confidently incorrect as a full time profession.",
    "matt your opinions age like milk in a hot car.",
    "matt got that walmart philosopher starter kit.",
    "matt your flex is mostly noise pollution.",
    "matt your brain is running on free trial mode.",
    "matt you are allergic to nuance and obsessed with theatrics.",
    "matt your argument style is copy, paste, and pray.",
    "matt got that fake alpha subscription with ads.",
    "matt your aura got repoed.",
    "matt your confidence is all-terrain, your accuracy is not.",
    "matt you are a glitch in the social feed.",
    "matt your takes arrive pre-wrong and somehow get worse live.",
    "matt you are all headline and no article.",
    "matt your confidence got forged in denial and bad wifi.",
    "matt your brain clocks in late and still asks for overtime.",
    "matt you sound certain the way traffic sounds organized.",
    "matt your opinions are loud enough to hide how empty they are.",
    "matt your strategy is vibes, panic, and a missing step.",
    "matt you are one ego boost away from a safety memo.",
    "matt your logic is held together by wishful thinking and volume.",
    "matt your whole act is confidence cosplay.",
    "matt you got keynote energy and typo execution.",
    "matt your aura keeps taking Ls in high definition.",
    "matt your thought process looks like tabs left open overnight.",
    "matt you are the tutorial for what not to do next.",
    "matt your takes are so stale they should come with preservatives.",
    "matt your confidence writes fan fiction about your competence.",
    "matt you got full-sentence confidence and half-sentence facts.",
    "matt your judgment is running on emergency backup only.",
    "matt you are the group project risk everyone warned us about.",
    "matt your humility is a deleted file.",
    "matt your decisions keep filing for extensions.",
    "matt you got maximum bravado and minimum checksum.",
    "matt your aura got audited and failed compliance.",
    "matt your arguments are just echoes with branding.",
    "matt you are a software update that fixed nothing and broke trust.",
    "matt your confidence has a louder mic than your brain.",
    "matt you are the reason people ask for a second opinion immediately.",
    "matt your takes come with a built-in fact-check warning.",
    "matt your plan is a screenshot of a thought.",
    "matt you are out here freelancing misinformation about yourself.",
    "matt your vibe is unresolved support ticket.",
    "matt your self-awareness got timed out for inactivity.",
    "matt you are all momentum and no map.",
    "matt your comebacks hit like weak signal bars.",
    "matt your process is improvisation wearing a tie.",
    "matt your aura got put on hold indefinitely.",
]

_voice_roast_pool: list[str] = []


def _next_voice_roast() -> str:
    global _voice_roast_pool
    if not _voice_roast_pool:
        _voice_roast_pool = MATT_VOICE_ROASTS[:]
        random.shuffle(_voice_roast_pool)
    return _voice_roast_pool.pop()


MATT_MOAN_SYLLABLES = [
    "ahh",
    "uhh",
    "ohh",
    "mmm",
    "hnn",
    "nnh",
    "mmh",
    "aah",
    "unf",
]
MATT_MOAN_CHARS = "ahmno"


def _build_matt_moan_line() -> str:
    name = random.choice(
        [
            "matt",
            "maaatt",
            "matttt",
            "maaaattt",
        ]
    )
    parts: list[str] = [name]
    for _ in range(random.randint(5, 10)):
        if random.random() < 0.4:
            char_noise = "".join(
                random.choice(MATT_MOAN_CHARS) for _ in range(random.randint(2, 6))
            )
            if random.random() < 0.5:
                char_noise += random.choice(["~", "!", ".."])
            parts.append(char_noise)
            continue
        syllable = random.choice(MATT_MOAN_SYLLABLES)
        if random.random() < 0.5:
            syllable += random.choice(["~", "..", "!"])
        parts.append(syllable)
    return " ".join(parts)

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
# Suppress noisy INFO spam from library internals
logging.getLogger("discord.ext.voice_recv.gateway").setLevel(logging.WARNING)
logging.getLogger("discord.ext.voice_recv.reader").setLevel(logging.WARNING)

log = logging.getLogger(__name__)

# The router thread raises OpusError("corrupted stream") on corrupted/dropped packets
# (e.g. a user disconnecting mid-packet). Normally this kills the PacketRouter thread
# and stops transcription permanently. Monkey-patch run() to catch OpusError and restart
# _do_run() so the thread survives — effectively skipping the bad packet.
import discord.ext.voice_recv.router as _vr_router
from discord.opus import OpusError as _OpusError


def _resilient_router_run(self) -> None:
    while True:
        try:
            self._do_run()
            return  # normal exit (voice client disconnected/stopped)
        except _OpusError as e:
            log.debug("PacketRouter: ignoring corrupted Opus packet, resuming: %s", e)


_vr_router.PacketRouter.run = _resilient_router_run

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
transcriber: Transcriber | None = None
transcriber_recovery_lock = asyncio.Lock()

# guild_id → TranscribingSink, so the voice-state event can reach the active sink
active_sinks: dict[int, TranscribingSink] = {}
# guild_id → periodic greeter task
active_periodic_tasks: dict[int, asyncio.Task] = {}
# guild_id → lock that serializes TTS playback so requests queue up instead of dropping
_tts_locks: dict[int, asyncio.Lock] = {}

MATT_PERIODIC_INTERVAL = 600  # seconds between periodic greetings (10 minutes)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

async def _build_transcriber() -> Transcriber | None:
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(None, Transcriber)
    except Exception:
        log.exception("Failed to initialize transcriber.")
        return None


async def _recover_transcriber(failed: Transcriber | None = None) -> bool:
    """Rebuild the transcriber after an error; serialize rebuilds across tasks."""
    global transcriber
    async with transcriber_recovery_lock:
        # If another task already healed it, avoid rebuilding again.
        if failed is not None and transcriber is not None and transcriber is not failed:
            return True

        log.warning("Transcriber error detected; attempting self-heal.")
        rebuilt = await _build_transcriber()
        if rebuilt is None:
            transcriber = None
            log.error("Transcriber self-heal failed; transcription temporarily unavailable.")
            return False
        transcriber = rebuilt
        log.info("Transcriber self-heal succeeded.")
        return True


@bot.event
async def on_ready():
    global transcriber
    log.info("Logged in as %s (id=%s)", bot.user, bot.user.id)
    if transcriber is None:
        transcriber = await _build_transcriber()
        if transcriber is None:
            log.error("Bot is online, but transcriber failed to initialize.")


# ---------------------------------------------------------------------------
# Utterance handler — called by the sink for each completed utterance
# ---------------------------------------------------------------------------

async def handle_utterance(user, pcm_bytes: bytes) -> None:
    name = getattr(user, "display_name", str(getattr(user, "id", "unknown")))
    log.info("Transcribing utterance from %s (%d bytes)...", name, len(pcm_bytes))

    if transcriber is None and not await _recover_transcriber():
        return

    text: str | None = None
    loop = asyncio.get_running_loop()
    for attempt in range(2):
        current = transcriber
        if current is None:
            return
        try:
            text = await loop.run_in_executor(None, current.transcribe, pcm_bytes)
            break
        except Exception:
            if attempt == 0:
                log.exception("Transcription failed for %s; attempting self-heal and retry.", name)
                if not await _recover_transcriber(current):
                    return
                continue
            log.exception("Transcription retry failed for %s; skipping utterance.", name)
            return

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


async def _speak_text(
    vc: VoiceRecvClient,
    guild_id: int,
    text: str,
    *,
    rate: str,
    pitch: str,
    voice: str | None = None,
) -> bool:
    """Wait for channel silence, queue behind any current playback, then play TTS.
    Returns True after playback completes, False if the voice client is not connected."""
    await _wait_for_silence(guild_id)

    if not vc.is_connected():
        return False

    lock = _tts_locks.setdefault(guild_id, asyncio.Lock())
    async with lock:
        if not vc.is_connected():
            return False

        # Wait for any in-progress playback (greeting, prior roast, etc.) to finish.
        while vc.is_playing():
            await asyncio.sleep(0.1)

        if not vc.is_connected():
            return False

        chosen_voice = voice or _next_voice()
        audio_path = await _generate_tts(text, chosen_voice, rate, pitch)

        loop = asyncio.get_running_loop()
        done = asyncio.Event()

        def _cleanup(err):
            try:
                os.unlink(audio_path)
            except OSError:
                pass
            if err:
                log.error("Error playing TTS audio: %s", err)
            loop.call_soon_threadsafe(done.set)

        try:
            vc.play(discord.FFmpegPCMAudio(audio_path), after=_cleanup)
        except discord.ClientException:
            _cleanup(None)
            return False

        await done.wait()

    return True


async def _play_greeting(vc: VoiceRecvClient, guild_id: int) -> None:
    """Wait for silence, then generate and play the next greeting from the pool."""
    greeting = _next_greeting()
    voice = _next_voice()
    log.info("Playing greeting [%s]: %s", voice, greeting)
    await _speak_text(
        vc,
        guild_id,
        greeting,
        rate=MATT_TTS_RATE,
        pitch=MATT_TTS_PITCH,
        voice=voice,
    )


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
    _tts_locks.pop(ctx.guild.id, None)
    await ctx.send(f"Left **{channel_name}**.")
    log.info("Left voice channel: %s", channel_name)


@bot.command(name="love_matt")
async def love_matt(ctx: commands.Context):
    """Manually fire a greeting at Matt right now."""
    if not ctx.voice_client or not ctx.voice_client.is_connected():
        await ctx.send("I'm not in a voice channel.")
        return
    asyncio.create_task(_play_greeting(ctx.voice_client, ctx.guild.id))


@bot.command(name="hate_matt")
async def hate_matt(ctx: commands.Context):
    """Send a playful roast for Matt."""
    text_roast = _next_roast()
    await ctx.send(text_roast)
    log.info("Sent roast via !hate_matt: %s", text_roast)
    if ctx.voice_client and ctx.voice_client.is_connected():
        voice_roast = _next_voice_roast()
        await _speak_text(
            ctx.voice_client,
            ctx.guild.id,
            voice_roast,
            rate=MATT_ROAST_TTS_RATE,
            pitch=MATT_ROAST_TTS_PITCH,
        )


@bot.command(name="hate_matt_voice")
async def hate_matt_voice(ctx: commands.Context):
    """Play a playful roast in voice chat without posting the roast text."""
    if not ctx.voice_client or not ctx.voice_client.is_connected():
        await ctx.send("I'm not in a voice channel.")
        return
    roast = _next_voice_roast()
    started = await _speak_text(
        ctx.voice_client,
        ctx.guild.id,
        roast,
        rate=MATT_ROAST_TTS_RATE,
        pitch=MATT_ROAST_TTS_PITCH,
    )
    if not started:
        await ctx.send("Couldn't play voice roast (not connected to a voice channel).")
        return
    log.info("Played voice-only roast via !hate_matt_voice: %s", roast)


@bot.command(name="matt_moan", aliases=["mattmoan", "moan_matt", "moan"])
async def matt_moan(ctx: commands.Context):
    """Play a chaotic Matt moan line in voice chat without posting text."""
    if not ctx.voice_client or not ctx.voice_client.is_connected():
        await ctx.send("I'm not in a voice channel.")
        return
    await ctx.send("Playing Matt moan line now.")
    moan_line = _build_matt_moan_line()
    try:
        started = await _speak_text(
            ctx.voice_client,
            ctx.guild.id,
            moan_line,
            rate=MATT_MOAN_TTS_RATE,
            pitch=MATT_MOAN_TTS_PITCH,
        )
    except Exception:
        log.exception("Failed to play Matt moan line.")
        await ctx.send("Matt moan failed due to a TTS/playback error. Check bot logs.")
        return
    if not started:
        await ctx.send("Couldn't play Matt moan line (not connected to a voice channel).")
        return
    log.info("Played voice-only Matt moan via !matt_moan: %s", moan_line)


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
