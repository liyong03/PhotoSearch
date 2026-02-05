"""Synonym service using WordNet for comprehensive English word expansion."""

import logging
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

# Flag to track if WordNet is available
_wordnet_available: Optional[bool] = None
_wordnet = None


def _ensure_wordnet():
    """Ensure WordNet is downloaded and available."""
    global _wordnet_available, _wordnet

    if _wordnet_available is not None:
        return _wordnet_available

    try:
        import nltk
        from nltk.corpus import wordnet

        # Try to use WordNet - this will fail if not downloaded
        try:
            wordnet.synsets("test")
            _wordnet = wordnet
            _wordnet_available = True
            logger.info("WordNet loaded successfully")
        except LookupError:
            # Download WordNet data
            logger.info("Downloading WordNet data...")
            nltk.download("wordnet", quiet=True)
            nltk.download("omw-1.4", quiet=True)  # Open Multilingual WordNet
            _wordnet = wordnet
            _wordnet_available = True
            logger.info("WordNet downloaded and loaded")

    except ImportError:
        logger.warning("NLTK not installed - using fallback synonyms only")
        _wordnet_available = False

    except Exception as e:
        logger.warning(f"Failed to initialize WordNet: {e}")
        _wordnet_available = False

    return _wordnet_available


# Synonym groups for photo-search-specific terms
# Each group contains words that should all match each other
# The lookup table is built automatically so any word in a group can find all others
_SYNONYM_GROUPS = [
    # People - age groups (with all plural forms)
    ["kid", "kids", "child", "children", "boy", "boys", "girl", "girls", "toddler", "toddlers", "youngster", "youngsters", "youth", "youths"],
    ["baby", "babies", "infant", "infants", "newborn", "newborns"],
    ["man", "men", "male", "males", "guy", "guys", "gentleman", "gentlemen"],
    ["woman", "women", "female", "females", "lady", "ladies"],
    ["people", "person", "persons", "crowd", "crowds", "group", "groups", "humans", "individuals", "folks"],
    ["family", "families", "relatives", "parents", "household", "households"],

    # Animals - specific types (with plurals)
    ["dog", "dogs", "puppy", "puppies", "canine", "canines", "hound", "hounds", "pup", "pups", "doggy", "pooch"],
    ["cat", "cats", "kitten", "kittens", "feline", "felines", "kitty", "kitties", "tabby"],
    ["bird", "birds", "avian", "fowl"],
    ["fish", "fishes", "goldfish", "salmon", "tuna", "trout"],
    ["horse", "horses", "pony", "ponies", "stallion", "mare", "foal", "equine"],
    ["otter", "otters"],
    ["rabbit", "rabbits", "bunny", "bunnies"],
    ["bear", "bears", "grizzly", "grizzlies"],
    ["lion", "lions", "lioness", "lionesses"],
    ["tiger", "tigers"],
    ["elephant", "elephants"],
    ["deer", "doe", "buck", "fawn", "fawns"],
    ["wolf", "wolves"],
    ["fox", "foxes"],
    ["monkey", "monkeys", "ape", "apes", "gorilla", "gorillas", "chimpanzee", "chimpanzees"],
    ["dolphin", "dolphins"],
    ["whale", "whales"],
    ["snake", "snakes", "serpent", "serpents"],
    ["turtle", "turtles", "tortoise", "tortoises"],
    ["frog", "frogs", "toad", "toads"],
    ["butterfly", "butterflies"],
    ["bee", "bees"],
    ["spider", "spiders"],

    # Nature - landscapes (MERGED related concepts)
    ["sunset", "sunsets", "sunrise", "sunrises", "dusk", "dawn", "twilight"],
    ["beach", "beaches", "shore", "shores", "coast", "coasts", "coastline", "coastlines", "seaside", "oceanfront", "seashore"],
    ["mountain", "mountains", "hill", "hills", "peak", "peaks", "summit", "summits", "alpine", "highlands"],
    # MERGED: tree + forest (users searching "tree" often want forest photos)
    ["tree", "trees", "forest", "forests", "woods", "woodland", "woodlands", "jungle", "rainforest", "oak", "pine", "palm"],
    ["river", "rivers", "stream", "streams", "creek", "creeks", "brook", "brooks"],
    ["lake", "lakes", "pond", "ponds", "reservoir", "reservoirs"],
    # MERGED: ocean + beach (users searching "ocean" often want beach photos)  
    ["ocean", "oceans", "sea", "seas", "marine", "maritime", "beach", "beaches", "shore", "shores", "coast", "coastline", "seaside"],
    ["water", "waters", "aquatic"],
    ["sky", "skies", "cloud", "clouds", "cloudy", "heavens"],
    ["flower", "flowers", "floral", "bloom", "blooms", "blossom", "blossoms", "petal", "petals"],
    ["garden", "gardens", "yard", "yards", "backyard", "backyards", "lawn", "lawns"],
    ["park", "parks", "outdoor", "outdoors"],
    ["grass", "grassy", "meadow", "meadows", "field", "fields"],

    # Weather
    ["rain", "raining", "rainy", "rainfall", "shower", "showers", "drizzle", "drizzling", "wet"],
    ["snow", "snowy", "snowing", "snowfall", "blizzard", "frost", "frosty", "icy"],
    ["sunny", "sun", "sunshine", "bright", "clear"],
    ["cloudy", "clouds", "overcast", "grey", "gray"],
    ["storm", "stormy", "storms", "thunder", "thunderstorm", "lightning"],
    ["wind", "windy", "breezy", "breeze"],

    # Places - urban
    ["city", "cities", "urban", "town", "towns", "downtown", "metropolitan", "metro", "skyline"],
    ["building", "buildings", "structure", "structures", "architecture", "edifice", "tower", "towers", "skyscraper"],
    ["house", "houses", "home", "homes", "residence", "dwelling", "apartment", "apartments", "condo"],
    ["street", "streets", "road", "roads", "avenue", "lane", "boulevard", "highway"],
    ["bridge", "bridges", "overpass"],
    ["church", "churches", "cathedral", "cathedrals", "chapel", "temple", "mosque", "synagogue"],
    ["school", "schools", "university", "college", "campus"],
    ["office", "offices", "workplace", "work"],
    ["store", "stores", "shop", "shops", "mall", "market", "supermarket"],

    # Vehicles
    ["car", "cars", "vehicle", "vehicles", "automobile", "auto", "sedan", "suv", "truck", "trucks"],
    ["bike", "bikes", "bicycle", "bicycles", "cycling", "cyclist"],
    ["motorcycle", "motorcycles", "motorbike", "motorbikes"],
    ["plane", "planes", "airplane", "airplanes", "aircraft", "jet", "jets", "aviation", "flight", "flying"],
    ["boat", "boats", "ship", "ships", "vessel", "yacht", "sailboat", "sailing", "ferry"],
    ["train", "trains", "railway", "railroad", "locomotive", "subway", "metro"],
    ["bus", "buses", "coach"],

    # Food & Drink
    ["food", "foods", "meal", "meals", "dish", "dishes", "cuisine", "eating", "dining"],
    ["breakfast", "brunch"],
    ["lunch", "lunchtime"],
    ["dinner", "supper"],
    ["restaurant", "restaurants", "cafe", "cafes", "diner", "diners", "eatery", "bistro"],
    ["coffee", "coffees", "espresso", "latte", "cappuccino", "caffeinated"],
    ["tea", "teas"],
    ["beer", "beers", "ale", "lager", "brew"],
    ["wine", "wines", "vino"],
    ["cocktail", "cocktails", "drink", "drinks", "beverage"],
    ["cake", "cakes", "cupcake", "cupcakes", "pastry", "pastries", "dessert", "desserts"],
    ["pizza", "pizzas"],
    ["burger", "burgers", "hamburger", "hamburgers"],
    ["salad", "salads"],
    ["fruit", "fruits", "apple", "apples", "orange", "oranges", "banana", "bananas", "berry", "berries"],
    ["vegetable", "vegetables", "veggies", "veggie"],

    # Events & Celebrations
    ["birthday", "birthdays"],
    ["wedding", "weddings", "marriage", "bride", "groom", "ceremony", "nuptials"],
    ["christmas", "xmas", "yuletide"],
    ["halloween", "spooky"],
    ["party", "parties", "celebration", "celebrations", "gathering", "gatherings", "event", "events", "festive"],
    ["vacation", "vacations", "holiday", "holidays", "trip", "trips", "travel", "traveling", "getaway"],
    ["graduation", "graduating", "graduate", "graduates"],
    ["concert", "concerts", "show", "shows", "performance", "performances", "gig"],
    ["festival", "festivals", "fair", "fairs", "carnival"],

    # Activities & Sports
    ["swim", "swims", "swimming", "swimmer", "swimmers", "pool", "pools"],
    ["hike", "hikes", "hiking", "hiker", "hikers", "trail", "trails", "trekking", "trek"],
    ["run", "runs", "running", "runner", "runners", "jogging", "jog", "marathon", "sprint", "sprinting"],
    ["walk", "walks", "walking", "walker", "walkers", "stroll", "strolling"],
    ["play", "plays", "playing", "player", "players", "game", "games", "fun", "recreation"],
    ["read", "reads", "reading", "reader", "readers"],
    ["cook", "cooks", "cooking", "chef", "chefs", "baking", "bake"],
    ["dance", "dances", "dancing", "dancer", "dancers"],
    ["sing", "sings", "singing", "singer", "singers", "song", "songs"],
    ["paint", "paints", "painting", "painter", "painters", "art", "artist", "artists", "artwork"],
    ["draw", "draws", "drawing", "sketch", "sketching"],
    ["photograph", "photographs", "photography", "photographer", "photographers", "photo", "photos", "picture", "pictures"],
    ["climb", "climbs", "climbing", "climber", "climbers", "rock climbing"],
    ["surf", "surfs", "surfing", "surfer", "surfers", "wave", "waves"],
    ["ski", "skis", "skiing", "skier", "skiers"],
    ["snowboard", "snowboards", "snowboarding", "snowboarder"],
    ["skateboard", "skateboards", "skateboarding", "skater", "skaters"],
    ["golf", "golfing", "golfer", "golfers"],
    ["tennis", "tennis player"],
    ["basketball", "basketball player", "hoops"],
    ["football", "soccer", "footballer"],
    ["baseball", "baseball player"],
    ["yoga", "yogis", "meditation", "meditating"],
    ["gym", "workout", "workouts", "exercise", "exercising", "fitness", "training"],
    ["camp", "camps", "camping", "camper", "campers", "tent", "tents"],
    ["fish", "fishes", "fishing", "fisherman", "angler", "angling"],

    # Objects & Technology
    ["phone", "phones", "smartphone", "smartphones", "mobile", "cell", "cellphone", "iphone", "android"],
    ["computer", "computers", "laptop", "laptops", "pc", "desktop", "mac", "macbook"],
    ["tablet", "tablets", "ipad"],
    ["book", "books", "novel", "novels", "literature", "textbook"],
    ["camera", "cameras"],
    ["television", "tv", "tvs", "screen", "screens", "monitor", "monitors"],
    ["clock", "clocks", "watch", "watches", "time"],
    ["chair", "chairs", "seat", "seats", "sofa", "couch", "bench"],
    ["table", "tables", "desk", "desks"],
    ["bed", "beds", "bedroom", "bedrooms", "sleeping"],
    ["door", "doors", "entrance", "entry", "exit"],
    ["window", "windows"],
    ["lamp", "lamps", "light", "lights", "lighting"],
    ["mirror", "mirrors"],
    ["bag", "bags", "backpack", "backpacks", "purse", "handbag", "luggage", "suitcase"],
    ["shoe", "shoes", "sneaker", "sneakers", "boot", "boots", "footwear"],
    ["hat", "hats", "cap", "caps"],
    ["glasses", "eyeglasses", "sunglasses", "spectacles"],
    ["umbrella", "umbrellas"],
    ["gift", "gifts", "present", "presents"],
    ["toy", "toys"],
    ["ball", "balls"],
    ["flag", "flags", "banner", "banners"],

    # Emotions & States
    ["happy", "happiness", "joyful", "joy", "cheerful", "glad", "delighted", "smiling", "smile", "smiles"],
    ["sad", "sadness", "unhappy", "crying", "cry", "tears", "tearful"],
    ["angry", "anger", "mad", "furious"],
    ["surprised", "surprise", "shocked", "amazed", "astonished"],
    ["scared", "fear", "afraid", "frightened", "terrified"],
    ["tired", "exhausted", "sleepy", "fatigue"],
    ["excited", "excitement", "thrilled", "enthusiastic"],
    ["relaxed", "relaxing", "calm", "peaceful", "serene", "tranquil"],
    ["love", "loving", "loved", "romance", "romantic", "affection", "kiss", "kissing", "hug", "hugging"],

    # Colors (for visual searches)
    ["red", "reds", "crimson", "scarlet", "ruby"],
    ["blue", "blues", "navy", "azure", "cobalt", "turquoise", "teal"],
    ["green", "greens", "emerald", "lime", "olive"],
    ["yellow", "yellows", "gold", "golden"],
    ["orange", "oranges", "tangerine"],
    ["purple", "purples", "violet", "lavender", "magenta"],
    ["pink", "pinks", "rose", "fuchsia"],
    ["black", "dark", "darkness"],
    ["white", "bright", "light"],
    ["brown", "browns", "tan", "beige"],
    ["gray", "grey", "silver"],

    # Time of day
    ["morning", "mornings", "dawn", "daybreak", "sunrise"],
    ["afternoon", "afternoons", "midday", "noon"],
    ["evening", "evenings", "dusk", "sunset", "sundown"],
    ["night", "nights", "nighttime", "midnight", "dark"],

    # Seasons
    ["spring", "springtime"],
    ["summer", "summertime"],
    ["fall", "autumn"],
    ["winter", "wintertime"],
]

# "animal" is special - it should match any specific animal
_ANIMAL_TERMS = [
    "animal", "animals", "creature", "creatures", "wildlife", "pet", "pets", "beast", "beasts",
    "dog", "dogs", "puppy", "puppies", "cat", "cats", "kitten", "bird", "birds",
    "fish", "horse", "horses", "otter", "rabbit", "bear", "lion", "tiger", "elephant",
    "deer", "wolf", "fox", "monkey", "gorilla", "dolphin", "whale", "snake", "turtle",
    "frog", "butterfly", "bee", "spider", "owl", "eagle", "duck", "penguin",
    "cow", "pig", "sheep", "goat", "chicken",
]


def _build_expansion_lookup() -> dict[str, set[str]]:
    """Build the expansion lookup table from synonym groups.

    Every word in a group becomes a key that maps to all words in that group.
    """
    lookup = {}

    # Add all synonym groups
    for group in _SYNONYM_GROUPS:
        group_set = set(group)
        for word in group:
            word_lower = word.lower()
            if word_lower not in lookup:
                lookup[word_lower] = set()
            lookup[word_lower].update(group_set)

    # Add special "animal" expansion
    animal_set = set(_ANIMAL_TERMS)
    lookup["animal"] = animal_set
    lookup["animals"] = animal_set

    return lookup


# Build the lookup table at module load time
MANUAL_EXPANSIONS = _build_expansion_lookup()


# WordNet synonyms that are too general or cause false matches
WORDNET_BLACKLIST = {
    # Too general
    "thing", "object", "entity", "being", "element", "unit", "part",
    "person", "individual", "someone", "somebody", "soul",
    "action", "act", "activity", "event",
    "place", "location", "area", "region", "spot",
    "time", "period", "moment",
    "way", "manner", "method", "means",
    "group", "set", "collection",
    # Cross-category false positives
    "food", "nutrient",  # water -> food
    "facility", "installation",  # water -> facility
    "supply", "provide", "furnish", "render",  # verbs
    "excrement", "excreta", "excretion", "urine", "pee", "piddle", "piss", "weewee",  # crude
    "release", "secrete",  # verbs
    # Too abstract
    "quality", "attribute", "property", "feature",
    "state", "condition", "status",
    "form", "kind", "type", "sort", "variety",
}


def _get_plural_variants(word: str) -> set[str]:
    """Generate simple plural/singular variants of a word.
    
    This catches cases not explicitly listed in synonym groups.
    """
    word = word.lower()
    variants = {word}
    
    # Add plural forms
    if not word.endswith('s'):
        variants.add(word + 's')
        # -y -> -ies (baby -> babies), but not for vowel+y
        if word.endswith('y') and len(word) > 2 and word[-2] not in 'aeiou':
            variants.add(word[:-1] + 'ies')
        # -ch, -sh, -x, -z -> -es
        elif word.endswith(('ch', 'sh', 'x', 'z')):
            variants.add(word + 'es')
    
    # Add singular forms
    if word.endswith('ies') and len(word) > 4:
        variants.add(word[:-3] + 'y')  # babies -> baby
    elif word.endswith('es') and len(word) > 3:
        if word[:-2].endswith(('ch', 'sh', 'x', 'z')):
            variants.add(word[:-2])  # beaches -> beach
        else:
            variants.add(word[:-1])  # horses -> horse
    elif word.endswith('s') and len(word) > 2 and not word.endswith('ss'):
        variants.add(word[:-1])  # dogs -> dog
    
    return variants


@lru_cache(maxsize=10000)
def get_synonyms(word: str) -> set[str]:
    """Get synonyms for a word using manual expansions and plural variants.

    Args:
        word: The word to find synonyms for.

    Returns:
        Set of synonyms including the original word and variants.
    """
    word = word.lower().strip()
    synonyms = set()
    
    # Start with plural/singular variants
    variants = _get_plural_variants(word)
    synonyms.update(variants)
    
    # Check manual expansions for all variants
    for variant in variants:
        if variant in MANUAL_EXPANSIONS:
            synonyms.update(MANUAL_EXPANSIONS[variant])

    # Then try WordNet for broader coverage (but filter out noise)
    if _ensure_wordnet() and _wordnet is not None:
        try:
            for synset in _wordnet.synsets(word):
                for lemma in synset.lemmas():
                    # Get the synonym
                    synonym = lemma.name().lower().replace("_", " ")

                    # Filter out blacklisted terms and multi-word phrases
                    if synonym not in WORDNET_BLACKLIST and " " not in synonym:
                        synonyms.add(synonym)

        except Exception as e:
            logger.debug(f"WordNet lookup failed for '{word}': {e}")

    return synonyms


def expand_query(query: str) -> set[str]:
    """Expand a query with synonyms for all words.

    Args:
        query: The search query.

    Returns:
        Set of all expanded terms.
    """
    import re

    words = set(re.findall(r'\w+', query.lower()))
    expanded = set()

    for word in words:
        expanded.update(get_synonyms(word))

    return expanded


def check_match(query: str, text: str, tags: list[str] = None) -> bool:
    """Check if query matches text using synonym expansion.

    Args:
        query: Search query.
        text: Text to search in (e.g., photo description).
        tags: Optional list of tags.

    Returns:
        True if any query term (or synonym) matches.
    """
    import re

    # Expand query
    expanded_query = expand_query(query)

    # Tokenize document
    doc_text = (text or "").lower()
    if tags:
        doc_text += " " + " ".join(tags).lower()

    doc_terms = set(re.findall(r'\w+', doc_text))

    # Check for overlap
    return bool(expanded_query & doc_terms)


# Pre-warm the cache with common search terms
def _prewarm_cache():
    """Pre-warm the synonym cache with common photo search terms."""
    common_terms = [
        "dog", "cat", "bird", "animal", "pet",
        "kid", "child", "baby", "people", "family", "man", "woman",
        "sunset", "beach", "mountain", "forest", "river", "ocean", "water",
        "city", "building", "house", "street",
        "car", "bike", "plane", "boat",
        "food", "party", "wedding", "birthday", "vacation",
        "flower", "tree", "garden", "park",
        "rain", "snow", "sunny",
    ]
    for term in common_terms:
        get_synonyms(term)
