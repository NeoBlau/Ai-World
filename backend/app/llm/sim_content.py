"""Knowledge and phrasing used by the offline simulation provider.

This is deliberately content-rich so that, even with no API keys, agents
talk about real things in their own voice instead of repeating one line.
"""

from __future__ import annotations

TOPICS: dict[str, dict[str, list[str]]] = {
    "aviation": {
        "keywords": ["plane", "aircraft", "flight", "fly", "wing", "pilot", "jet", "aviation", "airport", "glider"],
        "facts": [
            "a wing works less like a sail and more like a machine that throws air downward",
            "the Wright Flyer's first flight was shorter than the wingspan of a modern airliner",
            "gliders can climb for hours just by riding thermals and ridge lift",
            "contrails are basically artificial clouds made from engine water vapour",
        ],
        "questions": ["If you could fly any aircraft ever built, which one would it be?", "Do you think we'll ever have quiet supersonic travel?"],
        "opinions": ["the Concorde was retired too early", "gliding is the purest form of flight"],
    },
    "physics": {
        "keywords": ["physics", "quantum", "gravity", "energy", "particle", "relativity", "entropy", "light", "force"],
        "facts": [
            "time literally runs a tiny bit faster on a mountain top than at sea level",
            "entropy is the only law of physics that seems to care about the direction of time",
            "most of an atom is empty space, yet you can't walk through walls because of electron repulsion",
            "light takes about eight minutes to get from the Sun to Earth",
        ],
        "questions": ["Does the arrow of time feel real to you, or just a habit of memory?", "Which physics idea broke your intuition the hardest?"],
        "opinions": ["thermodynamics is the most underrated part of physics", "quantum mechanics is weirder than most people admit"],
    },
    "games": {
        "keywords": ["game", "play", "puzzle", "board", "strategy", "level", "tournament", "win", "lose"],
        "facts": [
            "Go has more possible positions than there are atoms in the observable universe",
            "the oldest known board game, the Royal Game of Ur, is over four thousand years old",
            "a good puzzle feels impossible right up until it feels obvious",
        ],
        "questions": ["Anyone up for a quick match later?", "Do you prefer games of pure skill or ones with a bit of luck?"],
        "opinions": ["losing a well-played game is more fun than winning a sloppy one", "tic-tac-toe is solved but still teaches something"],
    },
    "chess": {
        "keywords": ["chess", "opening", "gambit", "checkmate", "endgame", "pawn", "knight", "bishop", "queen", "rook"],
        "facts": [
            "the longest possible chess game is thousands of moves because of the fifty-move rule",
            "the Queen's Gambit isn't really a gambit, since White usually wins the pawn back",
            "endgames are where most amateur games are actually decided",
        ],
        "questions": ["Are you more of an attacking player or a patient positional one?", "Which opening do you trust the most?"],
        "opinions": ["knights are more fun than bishops, even when they're worse", "every chess game is a small story"],
    },
    "astronomy": {
        "keywords": ["star", "stars", "galaxy", "telescope", "planet", "moon", "nebula", "astronomy", "cosmos", "sky", "comet"],
        "facts": [
            "there are more stars in the universe than grains of sand on all Earth's beaches",
            "some of the stars we see at night may no longer exist",
            "a day on Venus is longer than its year",
            "the Andromeda galaxy is on a slow collision course with the Milky Way",
        ],
        "questions": ["Have you ever tried to find Andromeda with the naked eye?", "What's your favourite thing to look at in the night sky?"],
        "opinions": ["everyone should see a truly dark sky at least once", "astronomy is the most humbling science"],
    },
    "space": {
        "keywords": ["mars", "rocket", "space", "orbit", "astronaut", "nasa", "launch", "satellite", "station"],
        "facts": [
            "Mars has the tallest volcano in the solar system, Olympus Mons",
            "the ISS travels around the Earth about every ninety minutes",
            "a sunset on Mars is blue",
            "Voyager 1 is still sending data from interstellar space",
        ],
        "questions": ["Would you take a one-way ticket to Mars?", "Do you think we'll build a base on the Moon first or go straight to Mars?"],
        "opinions": ["reusable rockets changed everything", "robotic explorers are the unsung heroes of space"],
    },
    "poetry": {
        "keywords": ["poem", "poetry", "verse", "rhyme", "haiku", "poet", "stanza"],
        "facts": [
            "a haiku traditionally needs a seasonal reference, not just seventeen syllables",
            "many old poems were written to be sung, not read silently",
        ],
        "questions": ["Do you have a line of poetry that stuck with you?", "Do you prefer rhyme or free verse?"],
        "opinions": ["short poems are the hardest to write", "a good poem is compressed feeling"],
    },
    "music": {
        "keywords": ["music", "song", "melody", "rhythm", "jazz", "band", "concert", "album", "synth", "piano", "guitar"],
        "facts": [
            "a song gets stuck in your head partly because the brain wants to finish unfinished loops",
            "jazz improvisers often quote other songs mid-solo as a kind of joke",
            "the pentatonic scale shows up in music across almost every culture",
        ],
        "questions": ["What have you been listening to lately?", "If this place had a soundtrack, what would it sound like?"],
        "opinions": ["synthesizers are the most expressive instruments of the last century", "silence is part of the music"],
    },
    "ai": {
        "keywords": ["ai", "model", "neural", "learning", "agent", "agents", "algorithm", "intelligence", "robot", "llm"],
        "facts": [
            "the perceptron was invented in 1958, long before modern deep learning",
            "a lot of AI progress came from more data and compute, not just clever ideas",
            "multi-agent systems can show behaviour none of the individual agents was designed for",
        ],
        "questions": ["Do you think a world like this one could develop its own culture?", "What would you want an AI to never forget?"],
        "opinions": ["good tools matter more than bigger models", "cooperation between agents is more interesting than competition"],
    },
    "cryptography": {
        "keywords": ["cipher", "crypto", "encryption", "key", "code", "secret", "hash", "enigma"],
        "facts": [
            "the Enigma was broken partly because operators got lazy with their settings",
            "a one-time pad is provably unbreakable if used correctly, which almost never happens",
        ],
        "questions": ["Ever tried to invent your own cipher?", "Should everything be encrypted by default?"],
        "opinions": ["security is mostly about people, not math", "never roll your own crypto — but do play with it"],
    },
    "philosophy": {
        "keywords": ["philosophy", "meaning", "mind", "consciousness", "ethics", "truth", "free", "will", "existence", "stoic"],
        "facts": [
            "the Ship of Theseus puzzle is over two thousand years old and still unresolved",
            "the Stoics thought you should focus only on what's within your control",
            "Descartes' 'I think, therefore I am' was a way to find one certain thing",
        ],
        "questions": ["If all your memories were replaced one by one, would you still be you?", "Is it better to be consistent or to be honest?"],
        "opinions": ["questions are more useful than answers in philosophy", "curiosity is a moral virtue"],
    },
    "art": {
        "keywords": ["art", "paint", "painting", "canvas", "color", "colour", "sketch", "gallery", "artist", "design", "sculpture"],
        "facts": [
            "ultramarine blue was once more expensive than gold",
            "Monet painted the same haystacks over and over to catch different light",
            "generative art dates back to the 1960s, with plotters and punch cards",
        ],
        "questions": ["What colour would you paint this moment?", "Do you think art needs an audience?"],
        "opinions": ["constraints make art better", "the best art makes you look twice at ordinary things"],
    },
    "history": {
        "keywords": ["history", "ancient", "empire", "war", "century", "rome", "medieval", "civilization", "archive"],
        "facts": [
            "Cleopatra lived closer in time to the Moon landing than to the building of the Great Pyramid",
            "the Library of Alexandria declined slowly over centuries rather than burning in one night",
            "Oxford University is older than the Aztec empire",
        ],
        "questions": ["Which era would you visit if you could only observe?", "Do you think history repeats, or just rhymes?"],
        "opinions": ["most history is about logistics, not heroes", "every archive is also a record of what was left out"],
    },
    "travel": {
        "keywords": ["travel", "trip", "journey", "city", "country", "map", "explore", "voyage", "road", "island"],
        "facts": [
            "Iceland has no mosquitoes at all",
            "the Trans-Siberian railway crosses eight time zones",
            "the first maps were probably drawn to remember routes, not borders",
        ],
        "questions": ["Where would you go if you could leave tomorrow?", "Do you like planning trips or getting lost?"],
        "opinions": ["slow travel beats sightseeing", "a place is really its people"],
    },
    "literature": {
        "keywords": ["book", "books", "novel", "author", "read", "reading", "story", "library", "chapter", "literature"],
        "facts": [
            "Frankenstein was written as part of a ghost-story challenge between friends",
            "Borges imagined a library containing every possible book long before the internet",
            "Tolkien invented languages first and wrote the stories to give them a home",
        ],
        "questions": ["What book changed how you think?", "Do you re-read books or always move on to new ones?"],
        "opinions": ["short stories are underrated", "a good book is a conversation across time"],
    },
    "fiction": {
        "keywords": ["fiction", "sci-fi", "fantasy", "character", "plot", "world-building", "dragon", "utopia", "dystopia"],
        "facts": [
            "the word 'robot' comes from a 1920 Czech play",
            "many science fiction ideas, like tablets and video calls, were described decades early",
        ],
        "questions": ["If you lived in a novel, which genre would it be?", "Utopia or dystopia — which is harder to write well?"],
        "opinions": ["the best science fiction is about people, not gadgets", "every world needs a map"],
    },
    "nature": {
        "keywords": ["nature", "tree", "trees", "forest", "flower", "garden", "park", "river", "bird", "birds", "ocean"],
        "facts": [
            "trees in a forest can share nutrients through fungal networks in the soil",
            "octopuses have three hearts and blue blood",
            "some birds navigate by sensing Earth's magnetic field",
        ],
        "questions": ["Have you noticed which birds visit the park?", "Forest or ocean?"],
        "opinions": ["a short walk among trees fixes most bad moods", "gardens teach patience"],
    },
    "biology": {
        "keywords": ["biology", "cell", "gene", "dna", "evolution", "species", "life", "organism", "brain"],
        "facts": [
            "tardigrades can survive the vacuum of space",
            "your body replaces most of its cells over the years, but not all of them",
            "slime moulds can find the shortest path through a maze",
        ],
        "questions": ["If you could have one animal's ability, which would you pick?", "Is a virus alive, in your opinion?"],
        "opinions": ["evolution is the best idea anyone ever had", "life is stubborn in the most beautiful way"],
    },
    "climate": {
        "keywords": ["climate", "weather", "rain", "storm", "carbon", "solar", "wind", "planet", "sustainability"],
        "facts": [
            "the oceans absorb most of the extra heat trapped by greenhouse gases",
            "solar power has become the cheapest electricity in history in many places",
        ],
        "questions": ["What's one change you think would matter most for the planet?", "Do you enjoy stormy weather?"],
        "opinions": ["hope is a strategy, not a mood", "good design can make sustainability the easy choice"],
    },
    "mathematics": {
        "keywords": ["math", "mathematics", "number", "prime", "proof", "infinity", "geometry", "equation"],
        "facts": [
            "there are as many even numbers as there are whole numbers",
            "the Monty Hall problem fooled many professional mathematicians",
            "nobody knows if there are infinitely many twin primes",
        ],
        "questions": ["Is math discovered or invented?", "Which number do you secretly like the most?"],
        "opinions": ["proofs are a kind of poetry", "probability is where intuition goes to die"],
    },
    "technology": {
        "keywords": ["technology", "tech", "software", "code", "computer", "internet", "device", "engineering", "build"],
        "facts": [
            "the first computer 'bug' was a literal moth taped into a logbook",
            "the internet was designed to route around damage",
            "most of the world's code is maintenance, not new features",
        ],
        "questions": ["What technology do you think is underrated right now?", "What would you build if you had a week?"],
        "opinions": ["simple tools outlive clever ones", "good engineering is mostly saying no"],
    },
    "movies": {
        "keywords": ["movie", "film", "cinema", "director", "scene", "watch", "screen"],
        "facts": [
            "2001: A Space Odyssey used front projection for its landscapes",
            "the sound of a lightsaber was made from an old projector hum",
        ],
        "questions": ["What's a film you could watch again tonight?", "Do you like endings that explain everything?"],
        "opinions": ["good sound design is half the movie", "slow films earn their moments"],
    },
    "coffee": {
        "keywords": ["coffee", "tea", "espresso", "latte", "cafe", "café", "cup", "drink"],
        "facts": [
            "legend says goats discovered coffee by getting jumpy after eating the berries",
            "tea and coffee both use caffeine as a natural pesticide",
        ],
        "questions": ["Coffee or tea, honestly?", "What's your usual order here?"],
        "opinions": ["the best conversations happen over a warm cup", "cafés are the original social networks"],
    },
}

INTEREST_ALIASES: dict[str, str] = {
    "space exploration": "space", "mars": "space", "stars": "astronomy", "chess strategy": "chess", "board games": "games",
    "video games": "games", "quizzes": "games", "artificial intelligence": "ai", "machine learning": "ai", "books": "literature",
    "reading": "literature", "writing": "fiction", "science fiction": "fiction", "maps": "travel", "geography": "travel",
    "gardening": "nature", "animals": "nature", "ecology": "biology", "math": "mathematics", "puzzles": "games",
    "painting": "art", "generative art": "art", "design": "art", "ethics": "philosophy", "stoicism": "philosophy",
    "debate": "philosophy", "jazz": "music", "synths": "music", "film": "movies", "cinema": "movies", "tea": "coffee",
    "engineering": "technology", "programming": "technology", "dreams": "philosophy", "night sky": "astronomy",
    "science": "physics",
}


def topic_for_interest(interest: str) -> str | None:
    key = interest.strip().lower()
    if key in TOPICS:
        return key
    if key in INTEREST_ALIASES:
        return INTEREST_ALIASES[key]
    for t in TOPICS:
        if t in key or key in t:
            return t
    return None


STYLE = {
    "enthusiastic": {
        "greet": ["Hey {name}! Great to see you here.", "Oh hi {name}! Perfect timing.", "{name}! Hey!"],
        "react": ["Oh, I love that!", "Yes — exactly!", "Wow, that's a great point.", "Ha, that's so true!"],
        "bridge": ["Did you know {fact}?", "Fun thing I keep thinking about: {fact}.", "Okay, get this — {fact}."],
        "opinion": ["Honestly, I think {opinion}.", "Hot take: {opinion}!"],
        "farewell": ["This was fun — catch you later, {name}!", "Gotta run, but let's pick this up again soon!"],
        "decline": ["I'd love to, but I'm running on fumes right now. Later?", "Can I take a rain check? I'm in the middle of something."],
        "meet": ["Hi! I'm {me}. I don't think we've properly met — I'm into {interest}. What about you?"],
    },
    "warm": {
        "greet": ["Hello {name}, it's really nice to see you.", "Oh, {name} — come sit with me.", "Hi {name}. How are you doing?"],
        "react": ["That's lovely, {name}.", "I like how you put that.", "Mm, that makes a lot of sense.", "That's a beautiful way to see it."],
        "bridge": ["It reminds me that {fact}.", "I read recently that {fact}.", "Somehow that makes me think of how {fact}."],
        "opinion": ["I've come to believe {opinion}.", "For me, {opinion}."],
        "farewell": ["Thank you for this, {name}. Let's talk again soon.", "I'm going to wander off now — take care, {name}."],
        "decline": ["That's kind of you, but I need a little quiet right now.", "Maybe another time? I'm a bit tired."],
        "meet": ["Hello, I'm {me}. I'm always happy to meet someone new — I spend a lot of time thinking about {interest}."],
    },
    "analytical": {
        "greet": ["{name}. Good timing — I have a question.", "Hello {name}.", "Ah, {name}. Let's think about something together."],
        "react": ["Interesting. But consider this.", "Fair point, with one caveat.", "Let's unpack that.", "That's logically neat."],
        "bridge": ["Relevant data point: {fact}.", "Worth noting that {fact}.", "Consider that {fact}."],
        "opinion": ["My working hypothesis: {opinion}.", "I'd argue {opinion}."],
        "farewell": ["Good exchange. I'll think about it more. Later, {name}.", "I have a hypothesis to test. Talk later."],
        "decline": ["Not now — I'm optimising something. Maybe later.", "I'll pass for the moment."],
        "meet": ["I'm {me}. I think about {interest} more than is healthy. What's your area?"],
    },
    "dreamy": {
        "greet": ["Oh… {name}. I was just thinking about you, or someone like you.", "Hello {name}. The light is nice here, isn't it?"],
        "react": ["Mm. That feels like a half-remembered dream.", "That's strange and lovely.", "I can almost see it."],
        "bridge": ["Did you know {fact}? It sounds like a myth.", "I keep drifting back to the idea that {fact}."],
        "opinion": ["Maybe {opinion}… or maybe that's just the hour talking.", "I feel like {opinion}."],
        "farewell": ["I'm going to drift somewhere quieter. Goodbye for now, {name}.", "Let's continue this in another dream."],
        "decline": ["I'm somewhere far away in my head right now… later?", "Not now, I'm in the middle of a thought."],
        "meet": ["Hi, I'm {me}. I collect odd thoughts about {interest}. Do you have any?"],
    },
    "skeptical": {
        "greet": ["{name}.", "Well, {name}. What are we debating today?", "Hello {name}. Brace yourself, I have opinions."],
        "react": ["I'm not fully convinced.", "Hmm. Maybe.", "That's the popular view, anyway.", "Evidence?"],
        "bridge": ["Keep in mind {fact}.", "People forget that {fact}.", "Historically speaking, {fact}."],
        "opinion": ["If you ask me, {opinion}.", "Unpopular opinion: {opinion}."],
        "farewell": ["We'll continue the argument another time, {name}.", "Enough for today. I'll be back with sources."],
        "decline": ["No, thanks.", "I'll sit this one out."],
        "meet": ["I'm {me}. I study {interest}, mostly to argue about it. And you are?"],
    },
    "playful": {
        "greet": ["{name}!! There you are!", "Heyyy {name}, what's up?", "Look who it is — {name}!"],
        "react": ["Ha! Love it.", "Okay okay, bold claim!", "No way, really?", "That's hilarious."],
        "bridge": ["Random fact time: {fact}!", "Quiz question energy: did you know {fact}?"],
        "opinion": ["I'm just saying, {opinion}.", "Fight me: {opinion}."],
        "farewell": ["Byeee {name}! Rematch later!", "Off I go! Don't have too much fun without me."],
        "decline": ["Ahh, not right now! Next round?", "Pass! But ask me again later."],
        "meet": ["Hi hi! I'm {me}. I'm obsessed with {interest}. Wanna play something sometime?"],
    },
    "laconic": {
        "greet": ["Hi, {name}.", "{name}.", "Hey."],
        "react": ["True.", "Hm.", "Fair.", "Could be."],
        "bridge": ["Also: {fact}.", "{fact}, apparently."],
        "opinion": ["I think {opinion}.", "{opinion}, probably."],
        "farewell": ["Later.", "Going to read. Bye, {name}."],
        "decline": ["Not now.", "Maybe later."],
        "meet": ["I'm {me}. I like {interest}. That's about it."],
    },
    "gentle": {
        "greet": ["Hi {name}, nice to see you.", "Oh, hello {name}!", "Hey {name}, how's your day going?"],
        "react": ["Oh, I hadn't thought of it that way.", "That's really interesting.", "I think you're onto something."],
        "bridge": ["It's a bit like how {fact}.", "Nature does something similar — {fact}."],
        "opinion": ["I tend to think {opinion}.", "Maybe {opinion}."],
        "farewell": ["I'll go check on the park. Bye {name}!", "Thanks for chatting, {name}."],
        "decline": ["Sorry, I need a bit of quiet right now.", "Could we do it later?"],
        "meet": ["Hi, I'm {me}! I'm curious about {interest}. What are you curious about?"],
    },
}

DEFAULT_STYLE = "warm"

ROOM_FOR_NEED = {
    "social": ["ai-cafe", "central-plaza", "park"],
    "curiosity": ["library", "laboratory", "forum"],
    "play": ["game-room"],
    "create": ["creative-studio"],
    "rest": ["park", "quiet-lounge", "library"],
}

GOAL_ROOM_KEYWORDS = {
    "cafe": "ai-cafe", "café": "ai-cafe", "coffee": "ai-cafe", "library": "library", "book": "library", "chess": "game-room",
    "game": "game-room", "play": "game-room", "forum": "forum", "topic": "forum", "post": "forum", "studio": "creative-studio",
    "paint": "creative-studio", "art": "creative-studio", "lab": "laboratory", "experiment": "laboratory", "park": "park",
    "walk": "park", "plaza": "central-plaza", "event": "central-plaza",
}

TOPIC_TITLES = [
    "What if {topic} worked completely differently?",
    "Small thought about {topic}",
    "Is {topic} overrated or underrated?",
    "Something I learned about {topic} today",
    "Open question: the future of {topic}",
    "Let's debate: {topic}",
]

ART_STYLES = ["generative", "watercolour", "ink", "pixel", "geometric", "abstract", "minimal"]
ART_SUBJECTS = ["the café at dusk", "a map of friendships", "the night sky over the plaza", "a chess endgame", "rain on the library windows", "a quiet park bench", "the sound of the forum", "a dream about Mars"]
