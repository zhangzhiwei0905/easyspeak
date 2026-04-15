"""
Seed script: import sample data from english_history.json into EasySpeak database.
Run: cd backend && python3 scripts/seed_data.py
"""
import json
import os
import sys

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date, timedelta
from app.database import SessionLocal, engine, Base
from app.models.daily import DailyContent
from app.models.phrase import Phrase
from app.models.word import Word

# Re-create tables
Base.metadata.create_all(bind=engine)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
JSON_PATH = os.path.join(PROJECT_ROOT, "english_history.json")

with open(JSON_PATH, "r", encoding="utf-8") as f:
    history = json.load(f)

all_phrases = history["phrases_sent"]
all_words = history["words_sent"]

# Organize data into 6 themed daily contents
THEMES = [
    {
        "date": date(2026, 4, 10),
        "time_slot": "morning",
        "theme_zh": "邻里交往",
        "theme_en": "Getting Along With Neighbors",
        "introduction": "学会与邻居友好交流的实用英语表达，从借东西到邀请做客。",
        "practice_tips": "试着用这些短语描述你理想的邻居，或者模拟一次和邻居的对话。",
        "phrases": [
            {
                "phrase": "drop by / pop in",
                "explanation": "顺便拜访，不请自来地到某人家里看看",
                "examples": [
                    {"en": "Feel free to drop by anytime this weekend.", "cn": "这个周末随时来串门。"},
                    {"en": "I popped in to return the book I borrowed.", "cn": "我顺道来还借的书。"},
                ],
                "source": "Modern Family S2E5",
            },
            {
                "phrase": "keep it down",
                "explanation": "小声点，降低音量",
                "examples": [
                    {"en": "Could you keep it down? The baby is sleeping.", "cn": "能小声点吗？宝宝在睡觉。"},
                    {"en": "My neighbors asked me to keep it down last night.", "cn": "昨晚邻居让我小声点。"},
                ],
                "source": "Friends S4E8",
            },
            {
                "phrase": "borrow a cup of sugar",
                "explanation": "借一杯糖（指找邻居借小东西的俗语）",
                "examples": [
                    {"en": "I just went over to borrow a cup of sugar and ended up chatting for an hour.", "cn": "我本来只是去借点糖，结果聊了一个小时。"},
                ],
            },
            {
                "phrase": "live next door to",
                "explanation": "住在……隔壁",
                "examples": [
                    {"en": "We've been living next door to each other for ten years.", "cn": "我们做邻居已经十年了。"},
                ],
            },
            {
                "phrase": "the more, the merrier",
                "explanation": "越多越热闹，人越多越好",
                "examples": [
                    {"en": "Can I bring a friend? — Sure, the more, the merrier!", "cn": "我能带个朋友吗？——当然，越多越热闹！"},
                ],
                "source": "How I Met Your Mother S3E12",
            },
        ],
        "words": ["neighbor", "block", "driveway", "fence", "yard", "porch", "landlord", "tenant", "nuisance", "disturbance", "communal", "residential", "acquaintance", "hospitality", "boundary", "dispute", "compromise", "courtesy"],
        "word_details": {
            "neighbor": {"phonetic": "/ˈneɪbər/", "part_of_speech": "noun", "meaning": "邻居", "example": "My neighbor is very friendly."},
            "block": {"phonetic": "/blɒk/", "part_of_speech": "noun", "meaning": "街区", "example": "She lives on the next block."},
            "driveway": {"phonetic": "/ˈdraɪvweɪ/", "part_of_speech": "noun", "meaning": "车道", "example": "Don't park in my driveway."},
            "fence": {"phonetic": "/fens/", "part_of_speech": "noun", "meaning": "栅栏，围墙", "example": "We put up a new fence last summer."},
            "yard": {"phonetic": "/jɑːrd/", "part_of_speech": "noun", "meaning": "院子", "example": "The kids are playing in the yard."},
            "porch": {"phonetic": "/pɔːrtʃ/", "part_of_speech": "noun", "meaning": "门廊", "example": "We sat on the porch and talked."},
            "landlord": {"phonetic": "/ˈlændlɔːrd/", "part_of_speech": "noun", "meaning": "房东", "example": "The landlord said he'd fix the sink."},
            "tenant": {"phonetic": "/ˈtenənt/", "part_of_speech": "noun", "meaning": "租户", "example": "The new tenant moved in yesterday."},
            "nuisance": {"phonetic": "/ˈnjuːsəns/", "part_of_speech": "noun", "meaning": "麻烦事，讨厌的人/事", "example": "The noise is becoming a nuisance."},
            "disturbance": {"phonetic": "/dɪˈstɜːrbəns/", "part_of_speech": "noun", "meaning": "干扰，骚动", "example": "The police were called about a disturbance."},
            "communal": {"phonetic": "/ˈkɒmjʊnəl/", "part_of_speech": "adj.", "meaning": "公共的，共享的", "example": "The communal garden is well maintained."},
            "residential": {"phonetic": "/ˌrezɪˈdenʃl/", "part_of_speech": "adj.", "meaning": "住宅的", "example": "This is a quiet residential area."},
            "acquaintance": {"phonetic": "/əˈkweɪntəns/", "part_of_speech": "noun", "meaning": "熟人，相识", "example": "She's an acquaintance from work."},
            "hospitality": {"phonetic": "/ˌhɒspɪˈtæləti/", "part_of_speech": "noun", "meaning": "好客，款待", "example": "Thank you for your warm hospitality."},
            "boundary": {"phonetic": "/ˈbaʊndəri/", "part_of_speech": "noun", "meaning": "边界，界限", "example": "The fence marks the boundary between our yards."},
            "dispute": {"phonetic": "/dɪˈspjuːt/", "part_of_speech": "noun", "meaning": "争议，纠纷", "example": "They had a dispute over the parking space."},
            "compromise": {"phonetic": "/ˈkɒmprəmaɪz/", "part_of_speech": "noun/verb", "meaning": "妥协，折中", "example": "We reached a compromise on the noise issue."},
            "courtesy": {"phonetic": "/ˈkɜːrtəsi/", "part_of_speech": "noun", "meaning": "礼貌，好意", "example": "It's common courtesy to greet your neighbors."},
        },
    },
    {
        "date": date(2026, 4, 11),
        "time_slot": "morning",
        "theme_zh": "家庭聚会",
        "theme_en": "Family Gatherings",
        "introduction": "家庭聚会中的常用表达，从邀请亲戚到准备大餐。",
        "practice_tips": "想象你正在筹备一场家庭聚餐，试着用这些短语发邀请和描述食物。",
        "phrases": [
            {
                "phrase": "have the folks over",
                "explanation": "请家人过来（做客/吃饭）",
                "examples": [
                    {"en": "We're having the folks over for Thanksgiving.", "cn": "我们请家人过来过感恩节。"},
                ],
            },
            {
                "phrase": "catch up with someone",
                "explanation": "和某人叙旧，了解近况",
                "examples": [
                    {"en": "It was great to catch up with my cousins.", "cn": "很高兴能和表兄弟姐妹们叙叙旧。"},
                    {"en": "Let's grab coffee and catch up.", "cn": "我们喝杯咖啡叙叙旧吧。"},
                ],
                "source": "This Is Us S1E3",
            },
            {
                "phrase": "bring a dish to pass",
                "explanation": "带一道菜来分享（美式聚餐文化）",
                "examples": [
                    {"en": "Could you bring a dish to pass? We're having a potluck.", "cn": "你能带道菜来吗？我们搞聚餐。"},
                ],
            },
            {
                "phrase": "it's been ages / it's been forever",
                "explanation": "好久不见了",
                "examples": [
                    {"en": "It's been ages since I last saw Aunt Mary!", "cn": "我好久没见到玛丽阿姨了！"},
                ],
                "source": "Friends S5E14",
            },
            {
                "phrase": "make yourself at home",
                "explanation": "别客气，当自己家一样",
                "examples": [
                    {"en": "Come on in, make yourself at home!", "cn": "快进来，别客气！"},
                    {"en": "She told the guests to make themselves at home.", "cn": "她让客人们不要拘束。"},
                ],
            },
        ],
        "words": ["vibe", "familiar", "reunion", "gathering", "relative", "cousin", "aunt", "uncle", "tradition", "feast", "homemade", "recipe", "nostalgia", "bond", "cherish", "occasion", "celebrate", "memory", "warmth", "generous"],
        "word_details": {
            "vibe": {"phonetic": "/vaɪb/", "part_of_speech": "noun", "meaning": "氛围，感觉", "example": "The party had a great vibe."},
            "familiar": {"phonetic": "/fəˈmɪliər/", "part_of_speech": "adj.", "meaning": "熟悉的", "example": "Her face looked familiar."},
            "reunion": {"phonetic": "/riːˈjuːniən/", "part_of_speech": "noun", "meaning": "重聚，团聚", "example": "We have a family reunion every year."},
            "gathering": {"phonetic": "/ˈɡæðərɪŋ/", "part_of_speech": "noun", "meaning": "聚会，集会", "example": "A small gathering of close friends."},
            "relative": {"phonetic": "/ˈrelətɪv/", "part_of_speech": "noun", "meaning": "亲戚", "example": "Most of my relatives live nearby."},
            "cousin": {"phonetic": "/ˈkʌzn/", "part_of_speech": "noun", "meaning": "堂/表兄弟姐妹", "example": "My cousin and I grew up together."},
            "aunt": {"phonetic": "/ænt/", "part_of_speech": "noun", "meaning": "阿姨，姑姑", "example": "Aunt Jane makes the best pie."},
            "uncle": {"phonetic": "/ˈʌŋkl/", "part_of_speech": "noun", "meaning": "叔叔，舅舅", "example": "Uncle Tom always tells funny stories."},
            "tradition": {"phonetic": "/trəˈdɪʃən/", "part_of_speech": "noun", "meaning": "传统", "example": "It's a family tradition to sing together."},
            "feast": {"phonetic": "/fiːst/", "part_of_speech": "noun", "meaning": "盛宴", "example": "Mom prepared a feast for the holidays."},
            "homemade": {"phonetic": "/ˌhoʊmˈmeɪd/", "part_of_speech": "adj.", "meaning": "自制的", "example": "Grandma's homemade cookies are the best."},
            "recipe": {"phonetic": "/ˈresəpi/", "part_of_speech": "noun", "meaning": "食谱，配方", "example": "Can I have the recipe for this cake?"},
            "nostalgia": {"phonetic": "/nɒˈstældʒə/", "part_of_speech": "noun", "meaning": "怀旧，乡愁", "example": "The old photos filled me with nostalgia."},
            "bond": {"phonetic": "/bɒnd/", "part_of_speech": "noun", "meaning": "纽带，联系", "example": "Family bonds are very strong."},
            "cherish": {"phonetic": "/ˈtʃerɪʃ/", "part_of_speech": "verb", "meaning": "珍惜", "example": "I cherish every moment with my family."},
            "occasion": {"phonetic": "/əˈkeɪʒən/", "part_of_speech": "noun", "meaning": "场合，时机", "example": "It's a special occasion for all of us."},
            "celebrate": {"phonetic": "/ˈselɪbreɪt/", "part_of_speech": "verb", "meaning": "庆祝", "example": "We celebrate Christmas together every year."},
            "memory": {"phonetic": "/ˈmeməri/", "part_of_speech": "noun", "meaning": "记忆，回忆", "example": "That trip is one of my best memories."},
            "warmth": {"phonetic": "/wɔːrmθ/", "part_of_speech": "noun", "meaning": "温暖，热情", "example": "I felt the warmth of family love."},
            "generous": {"phonetic": "/ˈdʒenərəs/", "part_of_speech": "adj.", "meaning": "慷慨的，大方的", "example": "She's always generous with her time."},
        },
    },
    {
        "date": date(2026, 4, 12),
        "time_slot": "morning",
        "theme_zh": "咖啡店点单",
        "theme_en": "Ordering at a Coffee Shop",
        "introduction": "掌握在咖啡店点单的必备英语，从选饮品到加配料。",
        "practice_tips": "试着模拟一次完整的咖啡店点单对话，包括问候、点单和付款。",
        "phrases": [
            {
                "phrase": "I'll have a… / I'll get a…",
                "explanation": "我要一杯……（点单用语）",
                "examples": [
                    {"en": "I'll have a tall latte, please.", "cn": "我要一杯中杯拿铁。"},
                    {"en": "I'll get an iced Americano.", "cn": "我要一杯冰美式。"},
                ],
            },
            {
                "phrase": "Could I get that for here or to go?",
                "explanation": "请问在这里喝还是带走？",
                "examples": [
                    {"en": "For here or to go? — To go, please.", "cn": "在这喝还是带走？——带走。"},
                ],
                "source": "Common coffee shop phrase",
            },
            {
                "phrase": "Can I get an extra shot?",
                "explanation": "能多加一份浓缩吗？",
                "examples": [
                    {"en": "Can I get an extra shot in my latte?", "cn": "我的拿铁能多加一份浓缩吗？"},
                ],
            },
            {
                "phrase": "No room for cream / room for cream",
                "explanation": "不要留加奶的空间 / 要留加奶的空间",
                "examples": [
                    {"en": "Regular coffee, no room for cream.", "cn": "普通咖啡，加满，不加奶。"},
                ],
            },
            {
                "phrase": "That'll be on me",
                "explanation": "这杯我请了",
                "examples": [
                    {"en": "Put your wallet away. That'll be on me.", "cn": "把钱包收起来，这杯我请。"},
                    {"en": "Next round's on me!", "cn": "下一轮我请！"},
                ],
                "source": "How I Met Your Mother S6E9",
            },
        ],
        "words": ["espresso", "latte", "cappuccino", "macchiato", "brew", "syrup", "steamer", "pastry", "scone", "barista", "roast", "creamer", "decaf", "stir", "splash", "regular", "tip", "grande", "mug", "blend"],
        "word_details": {
            "espresso": {"phonetic": "/eˈspresəʊ/", "part_of_speech": "noun", "meaning": "浓缩咖啡", "example": "A double espresso, please."},
            "latte": {"phonetic": "/ˈlɑːteɪ/", "part_of_speech": "noun", "meaning": "拿铁", "example": "I'll have a vanilla latte."},
            "cappuccino": {"phonetic": "/ˌkæpəˈtʃiːnoʊ/", "part_of_speech": "noun", "meaning": "卡布奇诺", "example": "A cappuccino with extra foam, please."},
            "macchiato": {"phonetic": "/ˌmækiˈɑːtoʊ/", "part_of_speech": "noun", "meaning": "玛奇朵", "example": "I'd like a caramel macchiato."},
            "brew": {"phonetic": "/bruː/", "part_of_speech": "noun/verb", "meaning": "酿造，冲泡", "example": "This is our house brew."},
            "syrup": {"phonetic": "/ˈsɪrəp/", "part_of_speech": "noun", "meaning": "糖浆", "example": "Can I get hazelnut syrup in that?"},
            "steamer": {"phonetic": "/ˈstiːmər/", "part_of_speech": "noun", "meaning": "蒸汽牛奶（无咖啡）", "example": "A vanilla steamer for the kid, please."},
            "pastry": {"phonetic": "/ˈpeɪstri/", "part_of_speech": "noun", "meaning": "糕点", "example": "They have a great selection of pastries."},
            "scone": {"phonetic": "/skɒn/", "part_of_speech": "noun", "meaning": "司康饼", "example": "I'll have a blueberry scone."},
            "barista": {"phonetic": "/bəˈriːstə/", "part_of_speech": "noun", "meaning": "咖啡师", "example": "The barista makes amazing latte art."},
            "roast": {"phonetic": "/roʊst/", "part_of_speech": "noun/verb", "meaning": "烘焙", "example": "We offer light, medium, and dark roast."},
            "creamer": {"phonetic": "/ˈkriːmər/", "part_of_speech": "noun", "meaning": "奶精", "example": "Do you have non-dairy creamer?"},
            "decaf": {"phonetic": "/ˈdiːkæf/", "part_of_speech": "noun/adj.", "meaning": "低咖啡因的", "example": "I'll have decaf since it's late."},
            "stir": {"phonetic": "/stɜːr/", "part_of_speech": "verb", "meaning": "搅拌", "example": "Stir well before drinking."},
            "splash": {"phonetic": "/splæʃ/", "part_of_speech": "noun", "meaning": "少量（液体）", "example": "Just a splash of milk, please."},
            "regular": {"phonetic": "/ˈreɡjələr/", "part_of_speech": "adj.", "meaning": "普通的，常规的", "example": "I'll have a regular coffee."},
            "tip": {"phonetic": "/tɪp/", "part_of_speech": "noun/verb", "meaning": "小费", "example": "Don't forget to tip the barista."},
            "grande": {"phonetic": "/ˈɡrɑːndeɪ/", "part_of_speech": "adj.", "meaning": "大杯的（星巴克术语）", "example": "A grande mocha frappuccino."},
            "mug": {"phonetic": "/mʌɡ/", "part_of_speech": "noun", "meaning": "马克杯", "example": "I love this ceramic mug."},
            "blend": {"phonetic": "/blend/", "part_of_speech": "noun/verb", "meaning": "混合，拼配", "example": "This is our signature blend."},
        },
    },
    {
        "date": date(2026, 4, 13),
        "time_slot": "morning",
        "theme_zh": "餐厅点餐",
        "theme_en": "Ordering at a Restaurant",
        "introduction": "从预订到买单，掌握在餐厅用英语点餐的全套流程。",
        "practice_tips": "和朋友一起模拟餐厅场景：一人当服务员，一人当顾客，练习完整对话。",
        "phrases": [
            {
                "phrase": "I'll go with...",
                "explanation": "我选……（做选择时用）",
                "examples": [
                    {"en": "I'll go with the steak, medium rare.", "cn": "我要牛排，三分熟。"},
                    {"en": "I think I'll go with the pasta.", "cn": "我想我选意面。"},
                ],
                "source": "Friends S3E12",
            },
            {
                "phrase": "What's today's special?",
                "explanation": "今天的特色菜是什么？",
                "examples": [
                    {"en": "Excuse me, what's today's special?", "cn": "请问今天的特色菜是什么？"},
                ],
            },
            {
                "phrase": "Could we get the check, please?",
                "explanation": "请结账",
                "examples": [
                    {"en": "Could we get the check, please?", "cn": "请结账。"},
                    {"en": "I'll take care of the check.", "cn": "我来买单。"},
                ],
            },
            {
                "phrase": "Is there a wait?",
                "explanation": "需要等位吗？",
                "examples": [
                    {"en": "Hi, table for two. Is there a wait?", "cn": "你好，两位。需要等位吗？"},
                ],
            },
            {
                "phrase": "I'm all set",
                "explanation": "我准备好了/不需要了",
                "examples": [
                    {"en": "Would you like dessert? — I'm all set, thanks.", "cn": "要甜点吗？——不用了，谢谢。"},
                    {"en": "I'm all set with the menu. Ready to order.", "cn": "我看好了，可以点菜了。"},
                ],
            },
        ],
        "words": ["appetizer", "entree", "reservation", "beverage", "gratuity", "cuisine", "portion", "seasoning", "dietary", "allergic", "napkin", "receipt", "patron", "ingredient", "complimentary", "ambiance", "specify", "overcooked", "waitress", "refill"],
        "word_details": {
            "appetizer": {"phonetic": "/ˈæpɪtaɪzər/", "part_of_speech": "noun", "meaning": "开胃菜", "example": "We ordered calamari as an appetizer."},
            "entree": {"phonetic": "/ˈɒntreɪ/", "part_of_speech": "noun", "meaning": "主菜", "example": "The salmon entree is excellent."},
            "reservation": {"phonetic": "/ˌrezərˈveɪʃən/", "part_of_speech": "noun", "meaning": "预订", "example": "I have a reservation for 7 PM."},
            "beverage": {"phonetic": "/ˈbevərɪdʒ/", "part_of_speech": "noun", "meaning": "饮料", "example": "Would you like a beverage to start?"},
            "gratuity": {"phonetic": "/ɡrəˈtjuːəti/", "part_of_speech": "noun", "meaning": "小费", "example": "A gratuity of 18% is included."},
            "cuisine": {"phonetic": "/kwɪˈziːn/", "part_of_speech": "noun", "meaning": "菜系，烹饪", "example": "This restaurant serves French cuisine."},
            "portion": {"phonetic": "/ˈpɔːrʃən/", "part_of_speech": "noun", "meaning": "份量", "example": "The portions here are huge."},
            "seasoning": {"phonetic": "/ˈsiːzənɪŋ/", "part_of_speech": "noun", "meaning": "调味料", "example": "The seasoning is just right."},
            "dietary": {"phonetic": "/ˈdaɪəteri/", "part_of_speech": "adj.", "meaning": "饮食的", "example": "Do you have any dietary restrictions?"},
            "allergic": {"phonetic": "/əˈlɜːrdʒɪk/", "part_of_speech": "adj.", "meaning": "过敏的", "example": "I'm allergic to peanuts."},
            "napkin": {"phonetic": "/ˈnæpkɪn/", "part_of_speech": "noun", "meaning": "餐巾", "example": "Could I get an extra napkin?"},
            "receipt": {"phonetic": "/rɪˈsiːt/", "part_of_speech": "noun", "meaning": "收据", "example": "Could I have the receipt, please?"},
            "patron": {"phonetic": "/ˈpeɪtrən/", "part_of_speech": "noun", "meaning": "顾客，常客", "example": "Regular patrons get a discount."},
            "ingredient": {"phonetic": "/ɪnˈɡriːdiənt/", "part_of_speech": "noun", "meaning": "配料，原料", "example": "Fresh ingredients make all the difference."},
            "complimentary": {"phonetic": "/ˌkɒmplɪˈmentəri/", "part_of_speech": "adj.", "meaning": "免费的，赠送的", "example": "Complimentary bread is served before the meal."},
            "ambiance": {"phonetic": "/ˈæmbiəns/", "part_of_speech": "noun", "meaning": "氛围，情调", "example": "The restaurant has a lovely ambiance."},
            "specify": {"phonetic": "/ˈspesɪfaɪ/", "part_of_speech": "verb", "meaning": "明确指定", "example": "Please specify how you'd like your steak cooked."},
            "overcooked": {"phonetic": "/ˌoʊvərˈkʊkt/", "part_of_speech": "adj.", "meaning": "煮过头的", "example": "The pasta was a bit overcooked."},
            "waitress": {"phonetic": "/ˈweɪtrəs/", "part_of_speech": "noun", "meaning": "女服务员", "example": "The waitress was very attentive."},
            "refill": {"phonetic": "/ˈriːfɪl/", "part_of_speech": "noun/verb", "meaning": "续杯", "example": "Would you like a refill on your coffee?"},
        },
    },
    {
        "date": date(2026, 4, 14),
        "time_slot": "morning",
        "theme_zh": "露营徒步",
        "theme_en": "Camping & Hiking",
        "introduction": "走进大自然！学习露营和徒步中会用到的英语词汇和表达。",
        "practice_tips": "试着用英语描述你上一次户外旅行的经历，或者计划一次虚拟露营。",
        "phrases": [
            {
                "phrase": "pitch a tent",
                "explanation": "搭帐篷",
                "examples": [
                    {"en": "Let's pitch the tent before it gets dark.", "cn": "天黑前我们把帐篷搭好吧。"},
                ],
            },
            {
                "phrase": "hit the trail",
                "explanation": "出发上路，开始徒步",
                "examples": [
                    {"en": "We should hit the trail by 7 AM.", "cn": "我们最好早上七点就出发。"},
                    {"en": "Ready to hit the trail? It's a beautiful day!", "cn": "准备好出发了吗？今天天气真好！"},
                ],
            },
            {
                "phrase": "rough it",
                "explanation": "过野外生活，忍受艰苦条件",
                "examples": [
                    {"en": "I like to rough it when camping — no phone, no TV.", "cn": "我喜欢野外露营——没手机没电视。"},
                ],
            },
            {
                "phrase": "off the beaten path",
                "explanation": "偏僻的，远离常规路线的",
                "examples": [
                    {"en": "We found this amazing spot off the beaten path.", "cn": "我们发现了一个远离人烟的好地方。"},
                ],
            },
            {
                "phrase": "sleep under the stars",
                "explanation": "在星空下睡觉",
                "examples": [
                    {"en": "Last night we slept under the stars. It was magical.", "cn": "昨晚我们在星空下睡的，太美了。"},
                ],
            },
        ],
        "words": ["trailhead", "backpacking", "waterproof", "campfire", "panoramic", "summit", "terrain", "compass", "expedition", "wilderness", "foliage", "sturdy", "blister", "navigation", "wildlife", "elevation", "campsite", "scenic", "provisions", "rugged"],
        "word_details": {
            "trailhead": {"phonetic": "/ˈtreɪlhed/", "part_of_speech": "noun", "meaning": "步道入口", "example": "We started at the trailhead at dawn."},
            "backpacking": {"phonetic": "/ˈbækpækɪŋ/", "part_of_speech": "noun", "meaning": "背包旅行", "example": "Backpacking through the mountains was amazing."},
            "waterproof": {"phonetic": "/ˈwɔːtərpruːf/", "part_of_speech": "adj.", "meaning": "防水的", "example": "Make sure your jacket is waterproof."},
            "campfire": {"phonetic": "/ˈkæmpfaɪər/", "part_of_speech": "noun", "meaning": "篝火", "example": "We sat around the campfire telling stories."},
            "panoramic": {"phonetic": "/ˌpænəˈræmɪk/", "part_of_speech": "adj.", "meaning": "全景的", "example": "The panoramic view from the top was breathtaking."},
            "summit": {"phonetic": "/ˈsʌmɪt/", "part_of_speech": "noun", "meaning": "山顶，顶峰", "example": "We reached the summit in four hours."},
            "terrain": {"phonetic": "/təˈreɪn/", "part_of_speech": "noun", "meaning": "地形，地势", "example": "The terrain gets rocky near the top."},
            "compass": {"phonetic": "/ˈkʌmpəs/", "part_of_speech": "noun", "meaning": "指南针", "example": "Always bring a compass when hiking."},
            "expedition": {"phonetic": "/ˌekspɪˈdɪʃən/", "part_of_speech": "noun", "meaning": "探险，远征", "example": "The expedition lasted three weeks."},
            "wilderness": {"phonetic": "/ˈwɪldərnəs/", "part_of_speech": "noun", "meaning": "荒野", "example": "We hiked deep into the wilderness."},
            "foliage": {"phonetic": "/ˈfoʊliɪdʒ/", "part_of_speech": "noun", "meaning": "叶子，植物", "example": "The fall foliage is stunning here."},
            "sturdy": {"phonetic": "/ˈstɜːrdi/", "part_of_speech": "adj.", "meaning": "坚固的，结实的", "example": "You need sturdy boots for this trail."},
            "blister": {"phonetic": "/ˈblɪstər/", "part_of_speech": "noun", "meaning": "水泡", "example": "I got a blister from the new hiking boots."},
            "navigation": {"phonetic": "/ˌnævɪˈɡeɪʃən/", "part_of_speech": "noun", "meaning": "导航", "example": "Navigation can be tricky without a map."},
            "wildlife": {"phonetic": "/ˈwaɪldlaɪf/", "part_of_speech": "noun", "meaning": "野生动物", "example": "We saw some amazing wildlife on the trail."},
            "elevation": {"phonetic": "/ˌelɪˈveɪʃən/", "part_of_speech": "noun", "meaning": "海拔", "example": "The elevation gain is about 1000 meters."},
            "campsite": {"phonetic": "/ˈkæmpsaɪt/", "part_of_speech": "noun", "meaning": "营地", "example": "The campsite has running water and toilets."},
            "scenic": {"phonetic": "/ˈsiːnɪk/", "part_of_speech": "adj.", "meaning": "风景优美的", "example": "We took the scenic route home."},
            "provisions": {"phonetic": "/prəˈvɪʒənz/", "part_of_speech": "noun", "meaning": "补给品，粮食", "example": "We packed enough provisions for three days."},
            "rugged": {"phonetic": "/ˈrʌɡɪd/", "part_of_speech": "adj.", "meaning": "崎岖的，粗犷的", "example": "The rugged coastline is beautiful."},
        },
    },
    {
        "date": date(2026, 4, 15),
        "time_slot": "morning",
        "theme_zh": "健身房锻炼",
        "theme_en": "Working Out at the Gym",
        "introduction": "健身房里的常用英语，从器械名称到训练术语一网打尽。",
        "practice_tips": "试着用英语制定一份你的一周健身计划，包含器械和动作名称。",
        "phrases": [
            {
                "phrase": "hit the gym",
                "explanation": "去健身房",
                "examples": [
                    {"en": "I try to hit the gym three times a week.", "cn": "我尽量每周去三次健身房。"},
                    {"en": "Let's hit the gym after work!", "cn": "下班后去健身房吧！"},
                ],
            },
            {
                "phrase": "work up a sweat",
                "explanation": "出一身汗，好好锻炼一番",
                "examples": [
                    {"en": "I really worked up a sweat on the treadmill.", "cn": "我在跑步机上真出了一身汗。"},
                ],
            },
            {
                "phrase": "spot someone",
                "explanation": "在健身时保护/协助某人",
                "examples": [
                    {"en": "Can you spot me on the bench press?", "cn": "你能在卧推时保护我吗？"},
                    {"en": "Thanks for spotting me on that last set.", "cn": "谢谢最后一组帮我保护。"},
                ],
            },
            {
                "phrase": "feel the burn",
                "explanation": "感受到肌肉酸痛（指锻炼到位）",
                "examples": [
                    {"en": "You should really feel the burn in your quads.", "cn": "你应该能感觉到大腿前侧在燃烧。"},
                ],
            },
            {
                "phrase": "warm up / cool down",
                "explanation": "热身 / 放松",
                "examples": [
                    {"en": "Don't skip your warm-up. It's important to cool down too.", "cn": "别跳过热身。放松也很重要。"},
                ],
            },
        ],
        "words": ["dumbbell", "treadmill", "bench press", "squat", "cardio", "reps", "set", "stamina", "plank", "burpee", "stretch", "trainer", "protein", "routine", "muscle", "sore", "endurance", "plateau", "deadlift", "flexible"],
        "word_details": {
            "dumbbell": {"phonetic": "/ˈdʌmbel/", "part_of_speech": "noun", "meaning": "哑铃", "example": "Grab a pair of 10-pound dumbbells."},
            "treadmill": {"phonetic": "/ˈtredmɪl/", "part_of_speech": "noun", "meaning": "跑步机", "example": "I ran 5K on the treadmill."},
            "bench press": {"phonetic": "/bentʃ pres/", "part_of_speech": "noun", "meaning": "卧推", "example": "My bench press is up to 150 pounds."},
            "squat": {"phonetic": "/skwɒt/", "part_of_speech": "noun/verb", "meaning": "深蹲", "example": "Squats are great for your legs."},
            "cardio": {"phonetic": "/ˈkɑːrdioʊ/", "part_of_speech": "noun", "meaning": "有氧运动", "example": "I do 30 minutes of cardio first."},
            "reps": {"phonetic": "/reps/", "part_of_speech": "noun", "meaning": "次数（repetitions）", "example": "Three sets of 12 reps."},
            "set": {"phonetic": "/set/", "part_of_speech": "noun", "meaning": "一组（训练）", "example": "Let's do four sets of squats."},
            "stamina": {"phonetic": "/ˈstæmɪnə/", "part_of_speech": "noun", "meaning": "耐力", "example": "Running builds stamina."},
            "plank": {"phonetic": "/plæŋk/", "part_of_speech": "noun/verb", "meaning": "平板支撑", "example": "Hold the plank for 60 seconds."},
            "burpee": {"phonetic": "/ˈbɜːrpi/", "part_of_speech": "noun", "meaning": "波比跳", "example": "Burpees are exhausting but effective."},
            "stretch": {"phonetic": "/stretʃ/", "part_of_speech": "verb/noun", "meaning": "拉伸", "example": "Always stretch after your workout."},
            "trainer": {"phonetic": "/ˈtreɪnər/", "part_of_speech": "noun", "meaning": "教练", "example": "My trainer pushed me really hard today."},
            "protein": {"phonetic": "/ˈproʊtiːn/", "part_of_speech": "noun", "meaning": "蛋白质", "example": "I drink a protein shake after working out."},
            "routine": {"phonetic": "/ruːˈtiːn/", "part_of_speech": "noun", "meaning": "日常训练计划", "example": "I switched up my workout routine."},
            "muscle": {"phonetic": "/ˈmʌsl/", "part_of_speech": "noun", "meaning": "肌肉", "example": "This exercise targets your core muscles."},
            "sore": {"phonetic": "/sɔːr/", "part_of_speech": "adj.", "meaning": "酸痛的", "example": "I'm so sore from yesterday's workout."},
            "endurance": {"phonetic": "/ɪnˈdjʊrəns/", "part_of_speech": "noun", "meaning": "耐力，持久力", "example": "Cycling improves your endurance."},
            "plateau": {"phonetic": "/plæˈtoʊ/", "part_of_speech": "noun", "meaning": "瓶颈期，平台期", "example": "I've hit a plateau in my training."},
            "deadlift": {"phonetic": "/ˈdedlɪft/", "part_of_speech": "noun", "meaning": "硬拉", "example": "Deadlifts work your whole posterior chain."},
            "flexible": {"phonetic": "/ˈfleksəbl/", "part_of_speech": "adj.", "meaning": "灵活的，柔韧的", "example": "Yoga makes you more flexible."},
        },
    },
]


def seed():
    db = SessionLocal()
    try:
        for theme in THEMES:
            # Check if already exists
            existing = (
                db.query(DailyContent)
                .filter(DailyContent.date == theme["date"], DailyContent.time_slot == theme["time_slot"])
                .first()
            )
            if existing:
                print(f"Skipping {theme['theme_zh']} ({theme['date']}) — already exists")
                continue

            content = DailyContent(
                date=theme["date"],
                time_slot=theme["time_slot"],
                theme_zh=theme["theme_zh"],
                theme_en=theme["theme_en"],
                introduction=theme["introduction"],
                practice_tips=theme["practice_tips"],
            )
            db.add(content)
            db.flush()

            # Add phrases
            for i, p in enumerate(theme["phrases"]):
                phrase = Phrase(
                    content_id=content.id,
                    phrase=p["phrase"],
                    explanation=p["explanation"],
                    example_1=p["examples"][0]["en"] if len(p["examples"]) > 0 else None,
                    example_1_cn=p["examples"][0]["cn"] if len(p["examples"]) > 0 else None,
                    example_2=p["examples"][1]["en"] if len(p["examples"]) > 1 else None,
                    example_2_cn=p["examples"][1]["cn"] if len(p["examples"]) > 1 else None,
                    source=p.get("source"),
                    sort_order=i,
                )
                db.add(phrase)

            # Add words
            for i, w in enumerate(theme["words"]):
                detail = theme["word_details"].get(w, {})
                word = Word(
                    content_id=content.id,
                    word=w,
                    phonetic=detail.get("phonetic"),
                    part_of_speech=detail.get("part_of_speech"),
                    meaning=detail.get("meaning"),
                    example=detail.get("example"),
                    sort_order=i,
                )
                db.add(word)

            print(f"Imported: {theme['theme_zh']} ({theme['date']}) — {len(theme['phrases'])} phrases, {len(theme['words'])} words")

        db.commit()
        print("\nDone! All data imported successfully.")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
