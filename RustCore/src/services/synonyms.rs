use std::collections::{HashMap, HashSet};
use std::sync::LazyLock;

static SYNONYM_MAP: LazyLock<HashMap<&'static str, &'static [&'static str]>> = LazyLock::new(|| {
    let mut map = HashMap::new();
    let groups: &[&[&str]] = &[
        // People - age groups (with plurals)
        &["kid", "kids", "child", "children", "boy", "boys", "girl", "girls", "toddler", "toddlers", "youngster", "youngsters", "youth", "youths"],
        &["baby", "babies", "infant", "infants", "newborn", "newborns"],
        &["man", "men", "male", "males", "guy", "guys", "gentleman", "gentlemen"],
        &["woman", "women", "female", "females", "lady", "ladies"],
        &["people", "person", "persons", "crowd", "crowds", "group", "groups", "humans", "individuals", "folks"],
        &["family", "families", "relatives", "parents", "household", "households"],

        // Animals - specific types (with plurals)
        &["dog", "dogs", "puppy", "puppies", "canine", "canines", "hound", "hounds", "pup", "pups", "doggy", "pooch"],
        &["cat", "cats", "kitten", "kittens", "feline", "felines", "kitty", "kitties", "tabby"],
        &["bird", "birds", "avian", "fowl"],
        &["fish", "fishes", "goldfish", "salmon", "tuna", "trout"],
        &["horse", "horses", "pony", "ponies", "stallion", "mare", "foal", "equine"],
        &["otter", "otters"],
        &["rabbit", "rabbits", "bunny", "bunnies"],
        &["bear", "bears", "grizzly", "grizzlies"],
        &["lion", "lions", "lioness", "lionesses"],
        &["tiger", "tigers"],
        &["elephant", "elephants"],
        &["deer", "doe", "buck", "fawn", "fawns"],
        &["wolf", "wolves"],
        &["fox", "foxes"],
        &["monkey", "monkeys", "ape", "apes", "gorilla", "gorillas", "chimpanzee", "chimpanzees"],
        &["dolphin", "dolphins"],
        &["whale", "whales"],
        &["snake", "snakes", "serpent", "serpents"],
        &["turtle", "turtles", "tortoise", "tortoises"],
        &["frog", "frogs", "toad", "toads"],
        &["butterfly", "butterflies"],
        &["bee", "bees"],
        &["spider", "spiders"],

        // Nature - landscapes
        &["sunset", "sunsets", "sunrise", "sunrises", "dusk", "dawn", "twilight"],
        &["beach", "beaches", "shore", "shores", "coast", "coasts", "coastline", "coastlines", "seaside", "oceanfront", "seashore", "ocean", "oceans", "sea", "seas", "marine", "maritime"],
        &["mountain", "mountains", "hill", "hills", "peak", "peaks", "summit", "summits", "alpine", "highlands"],
        &["tree", "trees", "forest", "forests", "woods", "woodland", "woodlands", "jungle", "rainforest", "oak", "pine", "palm"],
        &["river", "rivers", "stream", "streams", "creek", "creeks", "brook", "brooks"],
        &["lake", "lakes", "pond", "ponds", "reservoir", "reservoirs"],
        &["water", "waters", "aquatic"],
        &["sky", "skies", "cloud", "clouds", "cloudy", "heavens"],
        &["flower", "flowers", "floral", "bloom", "blooms", "blossom", "blossoms", "petal", "petals"],
        &["garden", "gardens", "yard", "yards", "backyard", "backyards", "lawn", "lawns"],
        &["park", "parks", "outdoor", "outdoors"],
        &["grass", "grassy", "meadow", "meadows", "field", "fields"],

        // Weather
        &["rain", "raining", "rainy", "rainfall", "shower", "showers", "drizzle", "drizzling", "wet"],
        &["snow", "snowy", "snowing", "snowfall", "blizzard", "frost", "frosty", "icy"],
        &["sunny", "sun", "sunshine", "bright", "clear"],
        &["cloudy", "clouds", "overcast", "grey", "gray"],
        &["storm", "stormy", "storms", "thunder", "thunderstorm", "lightning"],
        &["wind", "windy", "breezy", "breeze"],

        // Places - urban
        &["city", "cities", "urban", "town", "towns", "downtown", "metropolitan", "metro", "skyline"],
        &["building", "buildings", "structure", "structures", "architecture", "edifice", "tower", "towers", "skyscraper", "house", "houses", "home", "homes"],
        &["house", "houses", "home", "homes", "residence", "dwelling", "apartment", "apartments", "condo"],
        &["street", "streets", "road", "roads", "avenue", "lane", "boulevard", "highway"],
        &["bridge", "bridges", "overpass"],
        &["church", "churches", "cathedral", "cathedrals", "chapel", "temple", "mosque", "synagogue"],
        &["school", "schools", "university", "college", "campus"],
        &["office", "offices", "workplace", "work"],
        &["store", "stores", "shop", "shops", "mall", "market", "supermarket"],

        // Vehicles
        &["car", "cars", "vehicle", "vehicles", "automobile", "auto", "sedan", "suv", "truck", "trucks"],
        &["bike", "bikes", "bicycle", "bicycles", "cycling", "cyclist"],
        &["motorcycle", "motorcycles", "motorbike", "motorbikes"],
        &["plane", "planes", "airplane", "airplanes", "aircraft", "jet", "jets", "aviation", "flight", "flying"],
        &["boat", "boats", "ship", "ships", "vessel", "yacht", "sailboat", "sailing", "ferry"],
        &["train", "trains", "railway", "railroad", "locomotive", "subway"],
        &["bus", "buses", "coach"],

        // Food & Drink
        &["food", "foods", "meal", "meals", "dish", "dishes", "cuisine", "eating", "dining"],
        &["breakfast", "brunch"],
        &["lunch", "lunchtime"],
        &["dinner", "supper"],
        &["restaurant", "restaurants", "cafe", "cafes", "diner", "diners", "eatery", "bistro"],
        &["coffee", "coffees", "espresso", "latte", "cappuccino", "caffeinated"],
        &["tea", "teas"],
        &["beer", "beers", "ale", "lager", "brew"],
        &["wine", "wines", "vino"],
        &["cocktail", "cocktails", "drink", "drinks", "beverage"],
        &["cake", "cakes", "cupcake", "cupcakes", "pastry", "pastries", "dessert", "desserts"],
        &["pizza", "pizzas"],
        &["burger", "burgers", "hamburger", "hamburgers"],
        &["salad", "salads"],
        &["fruit", "fruits", "apple", "apples", "orange", "oranges", "banana", "bananas", "berry", "berries"],
        &["vegetable", "vegetables", "veggies", "veggie"],

        // Events & Celebrations
        &["birthday", "birthdays"],
        &["wedding", "weddings", "marriage", "bride", "groom", "ceremony", "nuptials"],
        &["christmas", "xmas", "yuletide"],
        &["halloween", "spooky"],
        &["party", "parties", "celebration", "celebrations", "gathering", "gatherings", "event", "events", "festive"],
        &["vacation", "vacations", "holiday", "holidays", "trip", "trips", "travel", "traveling", "getaway"],
        &["graduation", "graduating", "graduate", "graduates"],
        &["concert", "concerts", "show", "shows", "performance", "performances", "gig"],
        &["festival", "festivals", "fair", "fairs", "carnival"],

        // Activities & Sports
        &["swim", "swims", "swimming", "swimmer", "swimmers", "pool", "pools"],
        &["hike", "hikes", "hiking", "hiker", "hikers", "trail", "trails", "trekking", "trek"],
        &["run", "runs", "running", "runner", "runners", "jogging", "jog", "marathon", "sprint", "sprinting"],
        &["walk", "walks", "walking", "walker", "walkers", "stroll", "strolling"],
        &["play", "plays", "playing", "player", "players", "game", "games", "fun", "recreation"],
        &["read", "reads", "reading", "reader", "readers"],
        &["cook", "cooks", "cooking", "chef", "chefs", "baking", "bake"],
        &["dance", "dances", "dancing", "dancer", "dancers"],
        &["sing", "sings", "singing", "singer", "singers", "song", "songs"],
        &["paint", "paints", "painting", "painter", "painters", "art", "artist", "artists", "artwork"],
        &["draw", "draws", "drawing", "sketch", "sketching"],
        &["photograph", "photographs", "photography", "photographer", "photographers", "photo", "photos", "picture", "pictures"],
        &["climb", "climbs", "climbing", "climber", "climbers"],
        &["surf", "surfs", "surfing", "surfer", "surfers", "wave", "waves"],
        &["ski", "skis", "skiing", "skier", "skiers"],
        &["snowboard", "snowboards", "snowboarding", "snowboarder"],
        &["skateboard", "skateboards", "skateboarding", "skater", "skaters"],
        &["golf", "golfing", "golfer", "golfers"],
        &["tennis"],
        &["basketball", "hoops"],
        &["football", "soccer", "footballer"],
        &["baseball"],
        &["yoga", "yogis", "meditation", "meditating"],
        &["gym", "workout", "workouts", "exercise", "exercising", "fitness", "training"],
        &["camp", "camps", "camping", "camper", "campers", "tent", "tents"],
        &["fishing", "fisherman", "angler", "angling"],

        // Objects & Technology
        &["phone", "phones", "smartphone", "smartphones", "mobile", "cell", "cellphone", "iphone", "android"],
        &["computer", "computers", "laptop", "laptops", "pc", "desktop", "mac", "macbook"],
        &["tablet", "tablets", "ipad"],
        &["book", "books", "novel", "novels", "literature", "textbook"],
        &["camera", "cameras"],
        &["television", "tv", "tvs", "screen", "screens", "monitor", "monitors"],
        &["clock", "clocks", "watch", "watches"],
        &["chair", "chairs", "seat", "seats", "sofa", "couch", "bench"],
        &["table", "tables", "desk", "desks"],
        &["bed", "beds", "bedroom", "bedrooms", "sleeping"],
        &["door", "doors", "entrance", "entry", "exit"],
        &["window", "windows"],
        &["lamp", "lamps", "light", "lights", "lighting"],
        &["mirror", "mirrors"],
        &["bag", "bags", "backpack", "backpacks", "purse", "handbag", "luggage", "suitcase"],
        &["shoe", "shoes", "sneaker", "sneakers", "boot", "boots", "footwear"],
        &["hat", "hats", "cap", "caps"],
        &["glasses", "eyeglasses", "sunglasses", "spectacles"],
        &["umbrella", "umbrellas"],
        &["gift", "gifts", "present", "presents"],
        &["toy", "toys"],
        &["ball", "balls"],
        &["flag", "flags", "banner", "banners"],

        // Emotions & States
        &["happy", "happiness", "joyful", "joy", "cheerful", "glad", "delighted", "smiling", "smile", "smiles"],
        &["sad", "sadness", "unhappy", "crying", "cry", "tears", "tearful"],
        &["angry", "anger", "mad", "furious"],
        &["surprised", "surprise", "shocked", "amazed", "astonished"],
        &["scared", "fear", "afraid", "frightened", "terrified"],
        &["tired", "exhausted", "sleepy", "fatigue"],
        &["excited", "excitement", "thrilled", "enthusiastic"],
        &["relaxed", "relaxing", "calm", "peaceful", "serene", "tranquil"],
        &["love", "loving", "loved", "romance", "romantic", "affection", "kiss", "kissing", "hug", "hugging"],

        // Colors
        &["red", "reds", "crimson", "scarlet", "ruby"],
        &["blue", "blues", "navy", "azure", "cobalt", "turquoise", "teal"],
        &["green", "greens", "emerald", "lime", "olive"],
        &["yellow", "yellows", "gold", "golden"],
        &["orange", "oranges", "tangerine"],
        &["purple", "purples", "violet", "lavender", "magenta"],
        &["pink", "pinks", "rose", "fuchsia"],
        &["black", "dark", "darkness"],
        &["white", "bright"],
        &["brown", "browns", "tan", "beige"],
        &["gray", "grey", "silver"],

        // Time of day
        &["morning", "mornings", "dawn", "daybreak", "sunrise"],
        &["afternoon", "afternoons", "midday", "noon"],
        &["evening", "evenings", "dusk", "sunset", "sundown"],
        &["night", "nights", "nighttime", "midnight"],

        // Seasons
        &["spring", "springtime"],
        &["summer", "summertime"],
        &["fall", "autumn"],
        &["winter", "wintertime"],
    ];

    for group in groups {
        for &word in *group {
            map.insert(word, *group);
        }
    }
    map
});

/// "animal" is special — it should match any specific animal.
static ANIMAL_TERMS: LazyLock<HashSet<&'static str>> = LazyLock::new(|| {
    [
        "animal", "animals", "creature", "creatures", "wildlife", "pet", "pets", "beast", "beasts",
        "dog", "dogs", "puppy", "puppies", "cat", "cats", "kitten", "bird", "birds",
        "fish", "horse", "horses", "otter", "rabbit", "bear", "lion", "tiger", "elephant",
        "deer", "wolf", "fox", "monkey", "gorilla", "dolphin", "whale", "snake", "turtle",
        "frog", "butterfly", "bee", "spider", "owl", "eagle", "duck", "penguin",
        "cow", "pig", "sheep", "goat", "chicken",
    ].into_iter().collect()
});

/// Generate simple plural/singular variants of a word.
fn get_plural_variants(word: &str) -> HashSet<String> {
    let word = word.to_lowercase();
    let mut variants = HashSet::new();
    variants.insert(word.clone());

    // Add plural forms
    if !word.ends_with('s') {
        variants.insert(format!("{}s", word));
        // -y -> -ies (baby -> babies), but not for vowel+y
        if word.ends_with('y') && word.len() > 2 {
            let second_last = word.as_bytes()[word.len() - 2];
            if !b"aeiou".contains(&second_last) {
                variants.insert(format!("{}ies", &word[..word.len() - 1]));
            }
        }
        // -ch, -sh, -x, -z -> -es
        else if word.ends_with("ch") || word.ends_with("sh") || word.ends_with('x') || word.ends_with('z') {
            variants.insert(format!("{}es", word));
        }
    }

    // Add singular forms
    if word.ends_with("ies") && word.len() > 4 {
        variants.insert(format!("{}y", &word[..word.len() - 3])); // babies -> baby
    } else if word.ends_with("es") && word.len() > 3 {
        let stem = &word[..word.len() - 2];
        if stem.ends_with("ch") || stem.ends_with("sh") || stem.ends_with('x') || stem.ends_with('z') {
            variants.insert(stem.to_string()); // beaches -> beach
        } else {
            variants.insert(word[..word.len() - 1].to_string()); // horses -> horse
        }
    } else if word.ends_with('s') && word.len() > 2 && !word.ends_with("ss") {
        variants.insert(word[..word.len() - 1].to_string()); // dogs -> dog
    }

    variants
}

/// Get synonyms for a word. Returns a set including the word itself and plural variants.
pub fn get_synonyms(word: &str) -> HashSet<String> {
    let lower = word.to_lowercase();
    let mut synonyms = HashSet::new();

    // Start with plural/singular variants
    let variants = get_plural_variants(&lower);
    synonyms.extend(variants.iter().cloned());

    // Check manual expansions for all variants
    for variant in &variants {
        if let Some(group) = SYNONYM_MAP.get(variant.as_str()) {
            synonyms.extend(group.iter().map(|s| s.to_string()));
        }
    }

    // Special expansion: broad animal terms match any specific animal
    const BROAD_ANIMAL_TERMS: &[&str] = &[
        "animal", "animals", "creature", "creatures", "wildlife",
        "pet", "pets", "beast", "beasts",
    ];
    if BROAD_ANIMAL_TERMS.contains(&lower.as_str()) {
        synonyms.extend(ANIMAL_TERMS.iter().map(|s| s.to_string()));
    }

    // If no synonyms found, at least return the word itself
    if synonyms.is_empty() {
        synonyms.insert(lower);
    }

    synonyms
}

/// Expand a query into all synonym variants of its terms.
/// Returns a set of all expanded terms.
pub fn expand_query(query: &str) -> HashSet<String> {
    let mut expanded = HashSet::new();
    for word in query.split(|c: char| !c.is_alphanumeric()) {
        let lower = word.to_lowercase();
        if lower.is_empty() {
            continue;
        }
        // Skip very short words and common stop words
        if lower.len() <= 2
            || matches!(
                lower.as_str(),
                "the" | "and" | "for" | "are" | "but" | "not" | "you" | "all"
                    | "can" | "had" | "her" | "was" | "one" | "our" | "out"
                    | "has" | "his" | "how" | "its" | "may" | "who" | "did"
                    | "get" | "let" | "say" | "she" | "too" | "use" | "with"
                    | "from" | "that" | "this" | "will" | "have" | "been"
                    | "some" | "them" | "than" | "each" | "which" | "their"
                    | "there" | "about" | "would" | "photo" | "picture" | "image"
            )
        {
            continue;
        }
        expanded.extend(get_synonyms(&lower));
    }
    expanded
}

/// Check if a document (description + tags) matches a query using synonym expansion.
/// Returns true if any expanded query term appears in the document text.
pub fn check_match(query: &str, description: Option<&str>, tags: Option<&str>) -> bool {
    let expanded = expand_query(query);
    if expanded.is_empty() {
        return true; // Empty meaningful terms = match everything
    }

    // Tokenize document text
    let mut doc_terms = HashSet::new();
    if let Some(desc) = description {
        for word in desc.split(|c: char| !c.is_alphanumeric()) {
            let lower = word.to_lowercase();
            if !lower.is_empty() {
                doc_terms.insert(lower);
            }
        }
    }
    if let Some(t) = tags {
        for word in t.split(|c: char| !c.is_alphanumeric()) {
            let lower = word.to_lowercase();
            if !lower.is_empty() {
                doc_terms.insert(lower);
            }
        }
    }

    // Check for intersection
    !expanded.is_disjoint(&doc_terms)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_known_synonym() {
        let syns = get_synonyms("dog");
        assert!(syns.contains("puppy"));
        assert!(syns.contains("canine"));
        assert!(syns.contains("dog"));
        assert!(syns.contains("dogs")); // plural
        assert!(syns.contains("puppies")); // plural in group
    }

    #[test]
    fn test_unknown_word() {
        let syns = get_synonyms("xyzabc");
        assert!(syns.contains("xyzabc"));
        assert!(syns.contains("xyzabcs")); // auto-generated plural
    }

    #[test]
    fn test_case_insensitive() {
        let syns = get_synonyms("DOG");
        assert!(syns.contains("puppy"));
    }

    #[test]
    fn test_plural_to_singular() {
        // Looking up "dogs" should find the "dog" group
        let syns = get_synonyms("dogs");
        assert!(syns.contains("puppy"));
        assert!(syns.contains("canine"));
    }

    #[test]
    fn test_plural_variants() {
        let v = get_plural_variants("baby");
        assert!(v.contains("baby"));
        assert!(v.contains("babies"));
        assert!(v.contains("babys")); // naive plural also generated

        let v = get_plural_variants("beach");
        assert!(v.contains("beach"));
        assert!(v.contains("beachs"));
        assert!(v.contains("beaches"));
    }

    #[test]
    fn test_animal_expansion() {
        let syns = get_synonyms("animal");
        assert!(syns.contains("dog"));
        assert!(syns.contains("cat"));
        assert!(syns.contains("bird"));
        assert!(syns.contains("wildlife"));
    }

    #[test]
    fn test_check_match_direct() {
        assert!(check_match("dog", Some("a cute dog playing"), None));
    }

    #[test]
    fn test_check_match_synonym() {
        assert!(check_match("dog", Some("a cute puppy playing"), None));
    }

    #[test]
    fn test_check_match_plural() {
        assert!(check_match("dogs", Some("a cute puppy playing"), None));
    }

    #[test]
    fn test_check_match_tags() {
        assert!(check_match("cat", None, Some("kitten,cute,small")));
    }

    #[test]
    fn test_check_match_no_match() {
        assert!(!check_match(
            "airplane",
            Some("a beautiful sunset over the ocean"),
            None
        ));
    }

    #[test]
    fn test_check_match_empty_query() {
        assert!(check_match("", Some("anything"), None));
    }

    #[test]
    fn test_expand_query() {
        let expanded = expand_query("sunset beach");
        assert!(expanded.contains("dusk"));
        assert!(expanded.contains("shore"));
        assert!(expanded.contains("sunset"));
        assert!(expanded.contains("beach"));
    }

    #[test]
    fn test_synonym_group_count() {
        // Verify we have a substantial number of entries
        assert!(SYNONYM_MAP.len() > 500, "Should have 500+ entries, got {}", SYNONYM_MAP.len());
    }
}
