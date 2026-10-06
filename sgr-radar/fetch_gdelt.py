#!/usr/bin/env python3
"""SGR Strategy Radar - GitHub Actions GDELT RSS collector.

Fetches the official GDELT Article List RSS feed, keeps a 24-hour rolling pool,
filters Korean/English strategic news, and writes pre-built JSON payloads for
industry / management / global categories. Uses Python standard library only.
"""
from __future__ import annotations

import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
POOL_FILE = DATA_DIR / "pool.json"
GDELT_RSS_URL = "https://data.gdeltproject.org/gdeltv3/gal/feed.rss"
POOL_HOURS = 24
POOL_LIMIT = 2000
DISPLAY_TARGET = 10
TREND_TARGET = 50
KST = timezone(timedelta(hours=9))

NEWS_TERMS = {
    "industry": [
        "artificial intelligence", " ai ", "semiconductor", "chip", "robot", "robotics",
        "data center", "datacenter", "cloud", "gpu", "battery", "energy", "electricity",
        "power grid", "biotech", "bio", "shipbuilding", "manufacturing", "factory",
        "quantum", "advanced manufacturing", "인공지능", "반도체", "칩", "로봇",
        "데이터센터", "클라우드", "배터리", "에너지", "전력", "바이오", "조선",
        "제조", "공장", "양자",
    ],
    "management": [
        "organizational change", "organization redesign", "restructuring", "layoffs", "job cuts",
        "workforce transformation", "workforce planning", "reskill", "upskill", "skill gap",
        "talent strategy", "talent management", "human resources", "future of work", "ai adoption",
        "ai workforce", "employee productivity", "labor productivity", "business transformation",
        "corporate culture", "succession planning", "hybrid work", "leadership", "employee engagement",
        "workplace transformation", "business model", "corporate strategy", "business strategy",
        "corporate governance", "enterprise ai", "workplace ai", "automation at work",
        "labor relations", "labour relations", "job losses", "software development",
        "consumer behavior", "consumer behaviour", "pricing strategy", "hr strategy", "hr strategies",
        "human resources strategy", "workplace productivity", "employee resilience", "operating model",
        "target operating model", "business process automation", "process automation", "workflow automation",
        "enterprise ai adoption", "enterprise ai strategy", "generative ai adoption", "ai copilot",
        "ai copilots", "knowledge work", "knowledge worker", "developer productivity", "developer experience",
        "coding assistant", "shared services", "back office automation", "customer service automation",
        "contact center ai", "ai governance", "responsible ai", "ai spending", "ai budget",
        "employee experience", "work redesign", "job redesign", "조직변화", "조직개편", "구조조정",
        "감원", "인력감축", "인력전환", "인력계획", "인재전략", "인재관리", "재교육", "업스킬링",
        "리스킬링", "미래의 일", "ai 도입", "ai 전환", "업무혁신", "생산성", "기업문화", "승계",
        "하이브리드 근무", "리더십", "직원 몰입", "비즈니스 모델", "경영전략", "기업전략",
        "기업지배구조", "노사관계", "일자리 감소", "소비자 행동", "가격전략", "운영모델",
        "업무 재설계", "직무 재설계", "프로세스 자동화", "업무 자동화", "워크플로 자동화",
        "기업 ai 도입", "생성형 ai 도입", "ai 코파일럿", "개발자 생산성", "직원 경험",
        "공유서비스", "백오피스 자동화", "고객서비스 자동화", "ai 거버넌스",
    ],
    "global": [
        "trade", "tariff", "fta", "export", "import", "supply chain", "critical mineral",
        "economic security", "geopolit", "us china", "u.s. china", "china us", "interest rate",
        "exchange rate", "inflation", "monetary", "central bank", "federal reserve", " fed ",
        "ecb", "cbam", "sanction", "fdi", "foreign direct investment", "asean", "apec", "g20",
        "oil", "energy security", "export control", "무역", "관세", "수출", "수입", "공급망",
        "핵심광물", "경제안보", "미중", "지정학", "금리", "환율", "인플레이션", "통화정책",
        "중앙은행", "제재", "해외투자", "아세안", "에너지안보", "수출통제",
    ],
}

TOPIC_GROUPS = {
    "industry": {
        "ai": ["artificial intelligence", " ai ", "gpu", "인공지능"],
        "semiconductor": ["semiconductor", "chip", "반도체", "칩"],
        "robotics": ["robot", "robotics", "로봇"],
        "datacenter": ["data center", "datacenter", "cloud", "데이터센터", "클라우드"],
        "energy": ["energy", "electricity", "power grid", "에너지", "전력"],
        "battery": ["battery", "electric vehicle", "배터리", "전기차"],
        "bio": ["biotech", " bio ", "바이오"],
        "shipbuilding": ["shipbuilding", "조선"],
        "manufacturing": ["manufacturing", "factory", "advanced manufacturing", "제조", "공장"],
        "quantum": ["quantum", "양자"],
    },
    "management": {
        "organization": ["organizational change", "organization redesign", "restructuring", "조직변화", "조직개편", "구조조정", "기업문화"],
        "workforce": ["workforce transformation", "workforce planning", "layoffs", "job cuts", "인력전환", "인력계획", "감원", "인력감축"],
        "skills": ["reskill", "upskill", "skill gap", "재교육", "업스킬링", "리스킬링"],
        "talent": ["talent strategy", "talent management", "human resources", "인재전략", "인재관리"],
        "leadership": ["leadership", "succession planning", "리더십", "승계"],
        "productivity": ["employee productivity", "labor productivity", "future of work", "hybrid work", "생산성", "미래의 일", "하이브리드 근무"],
        "ai-work": ["ai adoption", "ai workforce", "ai at work", "artificial intelligence", "ai 도입", "ai 전환", "업무혁신"],
        "culture": ["corporate culture", "employee engagement", "workplace transformation", "기업문화", "직원 몰입"],
        "strategy": ["business model", "corporate strategy", "business strategy", "corporate governance", "consumer behavior", "pricing strategy", "비즈니스 모델", "경영전략", "기업전략", "기업지배구조", "소비자 행동", "가격전략"],
        "operating-model": ["operating model", "target operating model", "shared services", "back office", "운영모델", "공유서비스", "백오피스"],
        "process-automation": ["business process automation", "process automation", "workflow automation", "ai copilot", "프로세스 자동화", "업무 자동화", "ai 코파일럿"],
        "developer-work": ["developer productivity", "developer experience", "coding assistant", "software development", "개발자 생산성"],
        "ai-governance": ["ai governance", "responsible ai", "enterprise ai strategy", "ai spending", "ai budget", "ai 거버넌스", "기업 ai 도입"],
    },
    "global": {
        "uschina": ["us china", "u.s. china", "china us", "미중"],
        "supplychain": ["supply chain", "critical mineral", "공급망", "핵심광물"],
        "rates": ["interest rate", "exchange rate", "inflation", "monetary", "central bank", "federal reserve", "금리", "환율", "인플레이션", "통화정책"],
        "security": ["economic security", "geopolit", "sanction", "export control", "경제안보", "지정학", "제재", "수출통제"],
        "energy": ["oil", "energy security", "에너지안보", "원유"],
        "esg": ["cbam", "carbon border", "environmental regulation", "탄소국경", "환경규제"],
        "regional": ["asean", "apec", "g20", "아세안"],
        "investment": ["fdi", "foreign direct investment", "investment", "해외투자"],
        "trade": ["trade agreement", "trade deal", "tariff", "fta", "export", "import", "무역협정", "관세", "수출", "수입"],
    },
}

BLOCKED_DOMAINS = {
    "prnewswire.com", "openpr.com", "einpresswire.com", "globenewswire.com",
    "newsfilecorp.com", "accesswire.com", "businesswire.com", "newswiretoday.com",
    "insidermonkey.com", "fool.com", "enewschannels.com", "naslovi.net",
    "aol.com", "tmz.com",
}
STRONG_DOMAINS = {
    "reuters.com", "apnews.com", "bloomberg.com", "cnbc.com", "ft.com", "wsj.com",
    "economist.com", "fortune.com", "forbes.com", "hani.co.kr", "mk.co.kr", "sedaily.com",
    "edaily.co.kr", "etnews.com", "zdnet.co.kr", "biz.chosun.com", "koreatimes.co.kr",
    "businesstimes.com.sg", "thediplomat.com", "asia.nikkei.com", "thehindu.com",
}

NOISE_PATTERNS = [
    r"crossword|cruciverba|horoscope|lottery",
    r"nfl|fifa|v-league|football match|soccer match|basketball|baseball|cricket|tennis tournament",
    r"prime big deals|deal day|shopping deal|discount|coupon|robot vacuum",
    r"how to trade|trading strateg|forex trader|forex trading|successful forex trader",
    r"stocks? worth watching|stock picks?|which .* stock is a better buy|price target|buy rating|sell rating",
    r"\bstock\s*:", r"\((?:nasdaq|nyse|nysearca):", r"murder|triple murder|police nab|pleads guilty|felon",
    r"job in [a-z]|stellenangebote|vacancy|apply now|hiring now",
    r"why do investors like|what it means for investors|well-positioned to capitalize|investment thesis",
    r"motley fool|insider monkey|seeking alpha|zacks investment",
    r"\blawyer\b|attorney profile|commercial, corporate governance & securities lawyer",
    r"public input on new water tariffs|water tariffs in ",
    r"produces song using instruments|meet .* humanoid robot working at .* repair shop",
    r"sexual battery|sodomy|pleads not guilty|anniversary concert|symphony|orchestra",
    r"wins funding to expand|named to .* next big things|fast company.*next big things",
    r"^after the factory$|cloud symphony|st\. cloud|^ice chips:",
    r"best business laptop|hybrid workday|best time to invest in fixed deposits|fixed deposits",
    r"stocks? rise toward|stocks? poised|all-time high after oil prices|international asparagus summit",
    r"how much does a .* battery storage system cost|capex, revenue and roi explained",
    r"\bstatoil\b",
    r"not sanctioned by law|sanctioned by law|illegally detained|detained for .* after bail",
    r"cloud storage for life|deal.*cloud storage|\b1tb\b.*cloud storage",
    r"chocolate chip|cookie recipe|recipes? for .*cookies|fresh apple cake",
    r"greek life|fraternit|sororit|cease-and-desist",
    r"student loans?|student loan borrowers?|borrowers?.*student loan",
    r"serie a|premier league|loan exit|transfer window|footballer|midfielder|striker|defender",
    r"\[?美?특징주\]?|주가.*(?:급등|급락)|(?:급등|급락).*주가",
    r"how to buy a home|va loans?|mortgage rates?|home loans?|assum(?:e|ing).*loan",
    r"sets reference exchange rate at|reference exchange rate at",
    r"ai hacker|cyberattacks?.*job losses|security & livelihoods",
    r"congress votes to have say in data center discussion|immersion school",
    r"ai 해커|해커.*금융권|보안 취약정보",
    r"fewer homes sell|home sales?.*interest rates?|housing market.*interest rates?",
    r"where are data centers located|what to know about data centers",
    r"what we said about supply chains in 2021",
]
PRESS_PATHS = ["/press-release/", "/press-releases/", "/newswire/", "/globenewswire/", "/pr-newswire/", "/pr-news/", "/business-wire/", "/accesswire/", "/prwire/"]
SPONSORED_PATHS = ["/co-written-partner/", "/sponsored/", "/sponsored-content/", "/partner-content/", "/paid-post/", "/brandvoice/", "/brand-voice/"]

MANAGEMENT_SIGNAL_PATTERNS = [
    r"organizational change", r"organization redesign", r"restructur", r"\blayoffs?\b", r"lay[s]? off", r"job cuts?",
    r"workforce transformation", r"workforce planning", r"reskill", r"upskill", r"talent strategy", r"talent management",
    r"future of work", r"ai adoption", r"ai workforce", r"employee productivity", r"labor productivity", r"business transformation",
    r"corporate culture", r"succession planning", r"hybrid work", r"employee engagement", r"workplace transformation",
    r"operating model", r"target operating model", r"business process automation", r"process automation", r"workflow automation",
    r"enterprise ai (?:adoption|strategy|deployment|rollout)", r"generative ai (?:adoption|deployment|rollout)", r"ai copilots?",
    r"coding assistants?", r"developer productivity", r"developer experience", r"knowledge work(?:er)?s?", r"shared services",
    r"back[ -]office automation", r"customer service automation", r"contact cent(?:er|re).*ai", r"ai governance", r"responsible ai",
    r"ai (?:spending|budget)", r"employee experience", r"work redesign", r"job redesign", r"business model", r"corporate strategy",
    r"business strategy", r"corporate governance", r"labor relations", r"labour relations",
    r"조직변화", r"조직개편", r"구조조정", r"감원", r"인력감축", r"인력전환", r"인력계획", r"인재전략", r"인재관리",
    r"재교육", r"업무혁신", r"생산성", r"기업문화", r"승계", r"하이브리드", r"직원 몰입", r"운영모델", r"업무 재설계",
    r"직무 재설계", r"프로세스 자동화", r"업무 자동화", r"워크플로 자동화", r"기업 ai 도입", r"생성형 ai 도입",
    r"ai 코파일럿", r"개발자 생산성", r"직원 경험", r"공유서비스", r"백오피스 자동화", r"고객서비스 자동화", r"ai 거버넌스",
]
MANAGEMENT_BROAD_PATTERNS = [
    r"business model", r"corporate strategy", r"business strategy", r"corporate governance", r"enterprise ai", r"workplace ai",
    r"automation.*work", r"software development", r"labor relations", r"labour relations", r"job losses?",
    r"consumer behavio(?:u)?r", r"pricing strategy", r"\bhr strateg(?:y|ies)\b", r"human resources strategy", r"workplace.*productivity",
    r"employee resilience", r"operating model", r"target operating model", r"business process automation", r"process automation",
    r"workflow automation", r"generative ai (?:adoption|deployment|rollout)", r"ai copilots?", r"coding assistants?", r"developer productivity",
    r"developer experience", r"knowledge work(?:er)?s?", r"shared services", r"back[ -]office automation", r"customer service automation",
    r"contact cent(?:er|re).*ai", r"ai governance", r"responsible ai", r"ai (?:spending|budget)", r"employee experience",
    r"work redesign", r"job redesign", r"비즈니스 모델", r"경영전략", r"기업전략", r"기업지배구조", r"노사관계", r"일자리 감소",
    r"소비자 행동", r"가격전략", r"운영모델", r"업무 재설계", r"직무 재설계", r"프로세스 자동화", r"업무 자동화",
    r"워크플로 자동화", r"기업 ai 도입", r"생성형 ai 도입", r"ai 코파일럿", r"개발자 생산성", r"직원 경험", r"공유서비스",
    r"백오피스 자동화", r"고객서비스 자동화", r"ai 거버넌스",
]
GLOBAL_SIGNAL_PATTERNS = [
    r"tariff", r"trade agreement", r"trade deal", r"free trade", r"\bfta\b", r"supply chain", r"critical minerals?",
    r"export control", r"economic security", r"geopolit", r"sanction", r"foreign direct investment", r"\bfdi\b",
    r"interest rates?", r"exchange rates?", r"inflation", r"monetary policy", r"central bank", r"federal reserve", r"\becb\b",
    r"\bcbam\b", r"energy security", r"oil prices?", r"\bg20\b", r"\basean\b", r"\bapec\b", r"관세", r"무역협정",
    r"자유무역", r"공급망", r"핵심광물", r"수출통제", r"경제안보", r"지정학", r"제재", r"해외직접투자", r"금리", r"환율",
    r"인플레이션", r"통화정책", r"중앙은행", r"에너지안보", r"유가", r"아세안",
]

def now_korea() -> str:
    d = datetime.now(KST)
    ampm = "오전" if d.hour < 12 else "오후"
    hour = d.hour % 12 or 12
    return f"{d.year}. {d.month:02d}. {d.day:02d}. {ampm} {hour:02d}:{d.minute:02d}:{d.second:02d}"

def clean(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()

def domain_from_url(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""

def infer_language(title: str) -> str:
    t = clean(title)
    if not t:
        return ""
    if re.search(r"[가-힣]", t):
        return "Korean"
    if re.search(r"[\u3040-\u30ff\u3400-\u9fff\u0400-\u052f\u0370-\u03ff\u0590-\u06ff\u0900-\u097f\u0e00-\u0e7f]", t):
        return ""
    letters = re.findall(r"[A-Za-z]", t)
    if len(letters) < 8:
        return ""
    tokens = re.findall(r"[^\W_]+", t.lower(), flags=re.UNICODE)
    if len(tokens) < 2:
        return ""
    funcs = {"the","and","to","of","in","for","on","as","with","from","by","amid","after","before","into","over","at","is","are","will","new","how","why","what","could","can","its","their","against","across","through","under","without","more","than"}
    strategic = {"ai","artificial","intelligence","business","company","corporate","workforce","employee","workers","jobs","layoffs","leadership","management","strategy","market","trade","tariff","supply","chain","energy","oil","data","center","semiconductor","chip","robotics","manufacturing","investment","growth","productivity","consumer","technology","software","development","economy","inflation","rate"}
    foreign = {"aktie","kurs","und","der","die","das","mit","fuer","il","lo","gli","della","delle","che","nel","danno","el","los","las","del","para","por","autoriza","le","les","des","avec","dans","uma","dos","com","pela","offese","agli","alla","dell","degli"}
    token_set = set(tokens)
    english_score = len(token_set & funcs)
    strategic_score = len(token_set & strategic)
    foreign_score = len(token_set & foreign)
    accented_latin = len(re.findall(r"[À-ɏ]", t))
    if foreign_score >= 1 and english_score == 0:
        return ""
    if accented_latin >= 2 and english_score < 2:
        return ""
    if english_score >= 2:
        return "English"
    if english_score >= 1 and strategic_score >= 1 and foreign_score == 0:
        return "English"
    if strategic_score >= 2 and foreign_score == 0 and accented_latin == 0:
        return "English"
    return ""

def fetch_rss() -> tuple[list[dict], int]:
    req = urllib.request.Request(
        GDELT_RSS_URL,
        headers={
            "User-Agent": "SGR-Strategy-Radar/2.0 (+https://github.com/treesky0103-dot/emperor-court-feed)",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        raw = resp.read(16 * 1024 * 1024 + 1)
    if len(raw) > 16 * 1024 * 1024:
        raise RuntimeError("GDELT RSS exceeds 16MB guard")
    root = ET.fromstring(raw)
    items = []
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    for node in root.findall(".//item"):
        title = clean(html.unescape(node.findtext("title") or ""))
        url = clean(html.unescape(node.findtext("link") or ""))
        if not title or not url:
            continue
        pub = clean(node.findtext("pubDate") or "")
        try:
            dt = parsedate_to_datetime(pub) if pub else datetime.now(timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            date_raw = dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            date_raw = now_iso
        items.append({
            "id": url, "title": title, "source": domain_from_url(url),
            "language": infer_language(title), "sourceCountry": "",
            "date": date_raw[:10], "dateRaw": date_raw, "publishedAt": date_raw,
            "summary": "", "url": url,
        })
    return items, len(raw)

def contains_term(text: str, term: str) -> bool:
    t, q = text.lower(), clean(term).lower()
    if not q:
        return False
    if re.fullmatch(r"[a-z0-9]+", q, re.I) and len(q) <= 3:
        return re.search(r"\b" + re.escape(q) + r"\b", t, re.I) is not None
    return q in t

def relevance_score(title: str, terms: list[str]) -> int:
    return sum(1 for term in terms if contains_term(title, term))

def pattern_score(title: str, patterns: list[str]) -> int:
    return sum(1 for p in patterns if re.search(p, title, re.I))

def industry_signal(title: str) -> int:
    t = clean(title).lower()
    if re.search(r"sexual battery|sodomy|anniversary concert|symphony|orchestra|st\\. cloud", t, re.I):
        return 0
    strong = [
        r"\bartificial intelligence\b", r"\bai\b", r"semiconductor", r"\bchip(?:s)?\b",
        r"data cent(?:er|re)", r"datacenter", r"\bgpu(?:s)?\b", r"biotech", r"shipbuilding",
        r"manufacturing", r"advanced manufacturing", r"quantum", r"power grid",
        r"인공지능", r"반도체", r"\b칩\b", r"데이터센터", r"바이오", r"조선", r"제조", r"양자", r"전력망",
    ]
    if any(re.search(p, t, re.I) for p in strong):
        return 2
    weak = [r"\brobot(?:s|ics)?\b", r"\bbattery\b", r"\benergy\b", r"\bfactory\b", r"\bcloud\b",
            r"\belectricity\b", r"로봇", r"배터리", r"에너지", r"공장", r"클라우드", r"전력"]
    context = [r"investment", r"invest", r"market", r"industry", r"technology", r"infrastructure", r"plant",
               r"production", r"supply", r"strategy", r"storage", r"grid", r"capacity", r"startup", r"company",
               r"투자", r"시장", r"산업", r"기술", r"인프라", r"생산", r"공급", r"전략", r"저장", r"설비", r"기업"]
    if any(re.search(p, t, re.I) for p in weak) and any(re.search(p, t, re.I) for p in context):
        return 1
    return 0

def management_signal(title: str) -> int:
    t = clean(title).lower()
    score = pattern_score(t, MANAGEMENT_SIGNAL_PATTERNS)
    if re.search(r"\bai\b|artificial intelligence|인공지능", t, re.I) and re.search(r"employee|workforce|workplace|organization|productivity|developer|coding|enterprise|operating model|process|workflow|shared services|back office|customer service|governance|spending|budget|직원|인력|조직|업무|생산성|기업|운영모델|프로세스|자동화|개발자|거버넌스", t, re.I):
        score += 1
    return score

def management_broad_signal(title: str) -> int:
    t = clean(title).lower()
    score = pattern_score(t, MANAGEMENT_BROAD_PATTERNS)
    if re.search(r"\bai\b|artificial intelligence|인공지능", t, re.I) and re.search(r"\bworkplace\b|\bworkforce\b|\bemployees?\b|\bworkers?\b|\bjobs?\b|software development|coding|developer|productivity|enterprise|operating model|process|workflow|shared services|back office|customer service|governance|spending|budget|직원|인력|업무|일자리|기업|운영모델|프로세스|자동화|개발자|거버넌스", t, re.I):
        score += 1
    return score

def global_signal(title: str) -> int:
    t = clean(title).lower()
    if re.search(r"student loans?|student loan borrowers?|greek life|fraternit|sororit|serie a|premier league|loan exit|transfer window|footballer|midfielder|striker|defender", t, re.I):
        return 0
    if any(re.search(p, t, re.I) for p in GLOBAL_SIGNAL_PATTERNS):
        return 1
    if re.search(r"\btrade\b", t, re.I) and re.search(r"global|international|minister|government|policy|exports?|imports?|talks?|negotiat|agreement|deal|tariff", t, re.I):
        return 1
    if re.search(r"\btrade\b", t, re.I) and re.search(r"(u\.s\.|united states|us).*china|china.*(u\.s\.|united states|us)", t, re.I):
        return 1
    return 0

def url_embedded_date_is_stale(url: str, max_age_days: int = 3) -> bool:
    """Reject obviously resurfaced old articles when the URL itself carries an old publication date."""
    path = urlparse(clean(url)).path
    match = re.search(r"/(20\\d{2})/(0?[1-9]|1[0-2])/(0?[1-9]|[12]\\d|3[01])(?:/|$)", path)
    if not match:
        match = re.search(r"/(20\\d{2})-(0?[1-9]|1[0-2])-(0?[1-9]|[12]\\d|3[01])(?:/|$)", path)
    if not match:
        return False
    try:
        embedded = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)), tzinfo=timezone.utc)
    except ValueError:
        return False
    return embedded < datetime.now(timezone.utc) - timedelta(days=max_age_days)

def is_noise(item: dict) -> bool:
    title, url = clean(item.get("title")).lower(), clean(item.get("url")).lower()
    source = domain_from_url(url) or clean(item.get("source")).lower().removeprefix("www.")
    if source in BLOCKED_DOMAINS or any(re.search(p, title, re.I) for p in NOISE_PATTERNS):
        return True
    if url_embedded_date_is_stale(url):
        return True
    if any(x in url for x in ["/stellenangebote", "/jobs/", "/job/", "/careers/", "/horoscope/", "/crossword/", "/shopping/", "/deals/"]):
        return True
    if any(x in url for x in PRESS_PATHS + SPONSORED_PATHS):
        return True
    if re.search(r"sponsored content|partner content|paid post|brand voice", title, re.I):
        return True
    if any(x in url for x in ["/paid-content/", "/advertorial/", "/sponsored-article/"]):
        return True
    if re.search(r"^\||^home$|^news$|^index$|letters to the editor|photo gallery|daily horoscope|lottery results|weather forecast|press release$|^eqs\s*-?\s*news\s*:", title, re.I):
        return True
    return False

def is_management_routine(item: dict) -> bool:
    title, url = clean(item.get("title")), clean(item.get("url")).lower()
    if re.search(r"\bappoints?\b.*\b(ceo|cfo|coo|chro|director|managing director|md)\b|\bnames?\b.*\b(ceo|cfo|coo|chro|director|managing director|md)\b|\bnew\s+(ceo|cfo|coo|chro|director)\b|career opportunities|career fair|job fair|promotion system for employees|employee promotion system|market rally|stocks? rise|stocks? fall|buy zone|stock market|fiscal plan|taxpayers? union", title, re.I):
        return True
    return any(x in url for x in ["/careers/", "/jobs/", "/job-fair/"])

def potential(item: dict) -> bool:
    title = clean(item.get("title"))
    if len(title) < 14 or infer_language(title) not in {"Korean", "English"} or is_noise(item):
        return False
    if industry_signal(title) >= 1:
        return True
    if management_signal(title) >= 1 or management_broad_signal(title) >= 1:
        return True
    if global_signal(title) >= 1:
        return True
    return False

def clearly_local_low_value(key: str, item: dict) -> bool:
    title = clean(item.get("title")).lower()
    if key == "management":
        return re.search(r"school board|assistant superintendent|school district|public school|teachers?'? union|educators?|city council|county board|local charity|career fair|job fair|municipal|red cross unveils employer brand|state workforce summit|민선\d+기 조직개편|구청|시청|군청|지자체|도시환경국|미래정책실", title, re.I) is not None
    if key == "global":
        return re.search(r"\|\s*[a-z -]+news\s*$", clean(item.get("title")), re.I) is not None or re.search(r"public input on new water tariffs|county|municipal|local council", title, re.I) is not None
    return False

def quality(key: str, item: dict) -> bool:
    title = clean(item.get("title"))
    if len(title) < 14 or infer_language(title) not in {"Korean", "English"} or is_noise(item):
        return False
    if clearly_local_low_value(key, item):
        return False
    if key == "management":
        return (not is_management_routine(item)) and (management_signal(title) >= 1 or management_broad_signal(title) >= 1)
    if key == "global":
        return global_signal(title) >= 1
    if key == "industry":
        return "cloud seeding" not in title.lower() and industry_signal(title) >= 1
    return relevance_score(title, NEWS_TERMS[key]) >= 1

def topic_for(key: str, title: str) -> str:
    for topic, terms in TOPIC_GROUPS[key].items():
        if any(contains_term(title, x) for x in terms):
            return topic
    return "other"

def normalized_title(title: str) -> str:
    return re.sub(r"[^a-z0-9가-힣]+", " ", title.lower()).strip()

def title_tokens(title: str) -> set[str]:
    toks = re.findall(r"[a-z0-9가-힣]+", normalized_title(title))
    ignored = {"the","and","for","with","from","after","before","says","said","new","more","amid","into","about","this","that","기업","회사","시장","사업","관련","종합"}
    return {x for x in toks if len(x) >= 2 and x not in ignored}

def near_duplicate(a: str, b: str) -> bool:
    sa, sb = title_tokens(a), title_tokens(b)
    if len(sa) < 3 or len(sb) < 3:
        return False
    inter, union = len(sa & sb), len(sa | sb)
    return bool(union and inter / union >= 0.62)

def dedupe(items: list[dict]) -> list[dict]:
    out, urls, titles = [], set(), set()
    for item in items:
        url, title_key = clean(item.get("url")).lower(), normalized_title(clean(item.get("title")))
        if not url or not title_key or url in urls or title_key in titles:
            continue
        if any(near_duplicate(item["title"], prev["title"]) for prev in out):
            continue
        urls.add(url); titles.add(title_key); out.append(item)
    return out

def score_item(key: str, item: dict) -> int:
    title = clean(item.get("title"))
    score = relevance_score(title, NEWS_TERMS[key]) * 2
    domain = clean(item.get("source")).lower().removeprefix("www.")
    if domain in {"insidermonkey.com","fool.com","seekingalpha.com","zacks.com"}:
        score -= 20
    if re.search(r"investors?|stock|shares?|buy rating|sell rating|price target", title, re.I):
        score -= 8
    if topic_for(key, title) != "other": score += 2
    if clean(item.get("source")).lower().removeprefix("www.") in STRONG_DOMAINS: score += 4
    if item.get("language") == "Korean": score += 1
    if key == "industry" and re.search(r"investment|invest|factory|plant|production|strategy|partnership|supply|infrastructure|launch|expansion|투자|공장|생산|전략|협력|공급|인프라|출시|확대", title, re.I): score += 3
    if key == "industry" and re.search(r"staffing|employment|layoffs?|hybrid work", title, re.I): score -= 5
    if key == "management": score += management_signal(title) * 3 + management_broad_signal(title) * 2
    if key == "global" and global_signal(title): score += 4
    return score

def same_global_event(a: str, b: str) -> bool:
    x, y = clean(a).lower(), clean(b).lower()
    pairs = [
        (r"u\.?s\.?|united states", r"trade (?:balance|deficit)|imports?"),
        (r"federal reserve|\bfed\b", r"interest rates?|monetary policy"),
        (r"oil", r"prices?|barrel"),
    ]
    for country_or_actor, event in pairs:
        if re.search(country_or_actor, x, re.I) and re.search(country_or_actor, y, re.I) and re.search(event, x, re.I) and re.search(event, y, re.I):
            return True
    return False

def select_diverse(key: str, items: list[dict], limit: int, strict: bool) -> list[dict]:
    ranked = sorted(items, key=lambda x: (score_item(key, x), clean(x.get("dateRaw"))), reverse=True)
    selected, topic_counts, domain_counts = [], {}, {}
    topic_cap, domain_cap = (2, 1) if strict else (5, 3)
    for pass_no in range(2):
        for item in ranked:
            if any(item["id"] == x["id"] for x in selected): continue
            topic, domain = topic_for(key, item["title"]), clean(item.get("source")).lower().removeprefix("www.") or "unknown"
            tc, dc = topic_counts.get(topic, 0), domain_counts.get(domain, 0)
            if topic != "other" and tc >= topic_cap + pass_no: continue
            if dc >= domain_cap + pass_no: continue
            if any(near_duplicate(item["title"], x["title"]) for x in selected): continue
            if key == "global" and any(same_global_event(item["title"], x["title"]) for x in selected): continue
            selected.append(item); topic_counts[topic] = tc + 1; domain_counts[domain] = dc + 1
            if len(selected) >= limit: return selected
    for item in ranked:
        if len(selected) >= limit: break
        if any(item["id"] == x["id"] for x in selected): continue
        if any(near_duplicate(item["title"], x["title"]) for x in selected): continue
        if key == "global" and any(same_global_event(item["title"], x["title"]) for x in selected): continue
        selected.append(item)
    return selected

def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default

def parse_dt(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None

def merge_pool(incoming: list[dict], existing: list[dict]) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=POOL_HOURS)
    kept = []
    for item in dedupe(incoming + existing):
        dt = parse_dt(clean(item.get("dateRaw")) or clean(item.get("publishedAt")))
        if dt and dt < cutoff: continue
        if potential(item):
            item["language"] = infer_language(item.get("title", ""))
            item["source"] = domain_from_url(item.get("url", "")) or clean(item.get("source"))
            kept.append(item)
    kept.sort(key=lambda x: clean(x.get("dateRaw")), reverse=True)
    return kept[:POOL_LIMIT]

def stable_item_signature(items: list[dict]) -> list[tuple[str, str]]:
    return [(clean(x.get("id")), clean(x.get("title"))) for x in items]

def build_payload(key: str, pool: list[dict], fetched_count: int, relevant_count: int, feed_bytes: int) -> dict:
    candidates = dedupe([x for x in pool if quality(key, x)])
    display = select_diverse(key, candidates, DISPLAY_TARGET, True)
    trend = select_diverse(key, candidates, TREND_TARGET, False)
    previous = load_json(DATA_DIR / f"{key}.json", {})
    same = stable_item_signature(previous.get("items", [])) == stable_item_signature(display) and stable_item_signature(previous.get("trendItems", [])) == stable_item_signature(trend)
    updated = previous.get("updatedAt") if same and previous.get("updatedAt") else now_korea()
    return {
        "ok": True, "category": key, "provider": "GDELT-RSS-GITHUB-ACTIONS",
        "updatedAt": updated, "stale": False, "cache": "GITHUB-ACTIONS",
        "quality": {
            "policy": "STRICT KO-EN + RSS NOISE GATE + STRATEGIC GATE + SOURCE QUALITY + DEDUPE + DISPLAY DIVERSITY",
            "raw": len(pool), "passed": len(candidates), "deduped": len(candidates), "eventDeduped": len(candidates),
            "displayed": len(display), "displayTarget": DISPLAY_TARGET, "floorAdded": 0, "targetMet": len(display) >= DISPLAY_TARGET,
        },
        "items": display, "trendItems": trend,
        "rss": {
            "endpoint": GDELT_RSS_URL, "mode": "RSS-FETCHED-GITHUB-ACTIONS", "poolSize": len(pool),
            "fetchedItems": fetched_count, "relevantItems": relevant_count, "feedBytes": feed_bytes,
            "rollingWindowHours": POOL_HOURS, "displayTarget": DISPLAY_TARGET,
        },
    }

def write_json_if_changed(path: Path, value) -> bool:
    rendered = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if old == rendered: return False
    path.write_text(rendered, encoding="utf-8")
    return True

def main() -> int:
    incoming, feed_bytes = fetch_rss()
    relevant = [x for x in incoming if potential(x)]
    existing = load_json(POOL_FILE, [])
    if not isinstance(existing, list): existing = []
    pool = merge_pool(relevant, existing)
    changes = []
    if write_json_if_changed(POOL_FILE, pool): changes.append("pool")
    for key in ("industry", "management", "global"):
        payload = build_payload(key, pool, len(incoming), len(relevant), feed_bytes)
        if write_json_if_changed(DATA_DIR / f"{key}.json", payload): changes.append(key)
    print(json.dumps({
        "ok": True, "fetched": len(incoming), "relevant": len(relevant), "pool": len(pool), "changed": changes,
        "display": {k: len(load_json(DATA_DIR / f"{k}.json", {}).get("items", [])) for k in ("industry","management","global")},
    }, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"SGR collector failed: {exc}", file=sys.stderr)
        raise
