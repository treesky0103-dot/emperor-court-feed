#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SGR GLOBAL THINK TANK AUTO15
Official-source collector for 15 institutions.
No paid API, search API, LLM API, API key, or user-managed token.
Runs in GitHub Actions and preserves each institution's last-good JSON on failure.
"""
from __future__ import annotations
import argparse, json, re, time, subprocess, shutil
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "sgr-radar" / "data" / "thinktanks"
STATUS = OUT / "status.json"
MAX_ITEMS = 10
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36"
MONTH = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}

# id, display name, default kind, official source pages, official hosts
CFG = [
("mgi","McKinsey Global Institute","연구",
 ["https://www.mckinsey.com/mgi/overview?no_head=1","https://www.mckinsey.com/mgi/","https://www.mckinsey.com/mgi/overview?content_language=English"],
 ["mckinsey.com"]),
("bhi","BCG Henderson Institute","이슈",
 ["https://www.bcg.com/bcg-institute"],
 ["bcg.com"]),
("nri","Nomura Research Institute","연구",
 ["https://www.nri.com/en/knowledge","https://www.nri.com/en/media/latest/index.html"],
 ["nri.com"]),
("csis","Center for Strategic and International Studies","이슈",
 ["https://www.csis.org/analysis"],
 ["csis.org"]),
("rand","RAND Corporation","연구",
 ["https://www.rand.org/pubs.html"],
 ["rand.org"]),
("drc","Development Research Center of the State Council","소식",
 ["https://en.drc.gov.cn/"],
 ["en.drc.gov.cn"]),
("mri","Mitsubishi Research Institute","연구",
 ["https://ir.mri.co.jp/ja/news.html","https://dx.mri.co.jp/column/"],
 ["mri.co.jp"]),
("chatham","Chatham House","연구",
 ["https://www.chathamhouse.org/path/whatsnew.xml","https://www.chathamhouse.org/publications/research-publications"],
 ["chathamhouse.org"]),
("bruegel","Bruegel","연구",
 ["https://www.bruegel.org/publications?page=0","https://www.bruegel.org/publications","https://www.bruegel.org/search?keyword=&page=0"],
 ["bruegel.org"]),
("cfr","Council on Foreign Relations","이슈",
 ["https://www.cfr.org/latest"],
 ["cfr.org"]),
("orf","Observer Research Foundation","이슈",
 ["https://www.orfonline.org/all-updates","https://www.orfonline.org/content-type/issue-briefs"],
 ["orfonline.org"]),
("lowy","Lowy Institute","연구",
 ["https://www.lowyinstitute.org/publications","https://www.lowyinstitute.org/"],
 ["lowyinstitute.org"]),
("fgv","Fundação Getulio Vargas","소식",
 ["https://portal.fgv.br/en/news","https://portal.fgv.br/noticias/todas","https://portal.fgv.br/en"],
 ["portal.fgv.br","fgv.br"]),
("iss","Institute for Security Studies","이슈",
 ["https://issafrica.org/iss-today","https://issafrica.org/"],
 ["issafrica.org"]),
("cigi","Centre for International Governance Innovation","연구",
 ["https://portal.cigionline.org/research/","https://www.cigionline.org/publications/cigi-papers/","https://www.cigionline.org/publications/"],
 ["cigionline.org"]),
]
BY_ID = {x[0]: x for x in CFG}
BAD = re.compile(r"^(home|about|contact|search|menu|close|next|previous|back|more|read more|view all|see all|load more|subscribe|sign in|login|careers?|events?|topics?|programs?|experts?|publications?|research|analysis|news)$",re.I)
BAD2 = re.compile(r"privacy policy|cookie policy|terms of use|accessibility|all rights reserved|follow us|newsletter|skip to|site map",re.I)
MEDIA = re.compile(r"\.(?:jpg|jpeg|png|gif|svg|webp|zip|mp4|mp3)(?:$|\?)",re.I)

def clean(v):
    return re.sub(r"\s+"," ",str(v or "")).strip()

def textify(s):
    s = re.sub(r"<script\b[\s\S]*?</script>"," ",s or "",flags=re.I)
    s = re.sub(r"<style\b[\s\S]*?</style>"," ",s,flags=re.I)
    return clean(unescape(re.sub(r"<[^>]+>"," ",s)))

def mkdate(y,m,d):
    try:
        x=datetime(int(y),int(m),int(d))
        if x.year < 2015 or x.date() > (datetime.now(KST)+timedelta(days=1)).date():
            return ""
        return x.strftime("%Y-%m-%d")
    except Exception:
        return ""

def getdate(s):
    s=clean(s)
    if not s: return ""
    m=re.search(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b",s)
    if m:
        x=mkdate(*m.groups())
        if x:return x
    m=re.search(r"\b(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",s)
    if m:
        x=mkdate(*m.groups())
        if x:return x
    m=re.search(r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+(\d{1,2})(?:st|nd|rd|th)?[,]?\s+(20\d{2})\b",s,re.I)
    if m:
        mm=MONTH.get(m.group(1).lower()[:3])
        if mm:
            x=mkdate(m.group(3),mm,m.group(2))
            if x:return x
    m=re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?[,]?\s+(20\d{2})\b",s,re.I)
    if m:
        mm=MONTH.get(m.group(2).lower()[:3])
        if mm:
            x=mkdate(m.group(3),mm,m.group(1))
            if x:return x
    return ""

def getdate_dmy(s):
    s=clean(s)
    if not s:return ""
    m=re.search(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b",s)
    if m:return mkdate(m.group(3),m.group(2),m.group(1))
    return ""

def date_url(url):
    p=urlparse(url).path
    for pat in (r"/(20\d{2})/(\d{1,2})/(\d{1,2})(?:/|$)",r"/(20\d{2})(\d{2})(\d{2})(?:/|[-_.])"):
        m=re.search(pat,p)
        if m:
            x=mkdate(*m.groups())
            if x:return x
    return ""

def hostok(host, hosts):
    host=(host or "").lower()
    return any(host==h or host.endswith("."+h) for h in hosts)

def official(raw,base,hosts):
    raw=clean(unescape(raw))
    if not raw or re.match(r"^(?:javascript:|mailto:|tel:|#)",raw,re.I):return ""
    try:u=urlparse(urljoin(base,raw))
    except Exception:return ""
    if u.scheme not in ("http","https") or not hostok(u.hostname,hosts):return ""
    return urlunparse(("https",u.netloc,u.path or "/",u.params,u.query,""))

def source_page(url,sources):
    try:
        u=urlparse(url)
        a=((u.hostname or "").lower(),(u.path.rstrip("/") or "/").lower())
        for s in sources:
            q=urlparse(s)
            if a==((q.hostname or "").lower(),(q.path.rstrip("/") or "/").lower()):return True
    except Exception:pass
    return False

def kindof(s,default):
    s=clean(s).lower()
    if re.search(r"research paper|research report|working paper|policy paper|policy brief|report\b|publication|study\b|survey\b|monograph|white paper|연구|보고서|調査|研究|提言",s):return "연구"
    if re.search(r"news release|press release|press\b|news\b|announcement|update\b|소식|보도|공지|ニュース|お知らせ",s):return "소식"
    if re.search(r"analysis|commentary|insight|opinion|expert speak|critical questions|brief\b|podcast|column|이슈|분석|칼럼|コラム",s):return "이슈"
    return default

def good(title,url,date,sources,hosts):
    title=clean(title)
    if not url or len(title)<12 or len(title)>260 or not date:return False
    if BAD.match(title.lower()) or BAD2.search(title.lower()) or MEDIA.search(url):return False
    if source_page(url,sources) or not hostok(urlparse(url).hostname,hosts):return False
    return True

def item(cfg,title,url,date,src,n,note=""):
    iid,name,default,sources,hosts=cfg
    k=kindof(f"{title} {url} {note}",default)
    return {"id":url,"kind":k,"title":clean(title),"note":clean(note) or f"공식 {k} 페이지에서 자동 수집","date":date,
            "publishedAt":f"{date}T00:00:00.000Z","url":url,"source":name,"sourceUrl":src,"official":True,"order":n}

def walk(x):
    if isinstance(x,dict):
        yield x
        for v in x.values():yield from walk(v)
    elif isinstance(x,list):
        for v in x:yield from walk(v)

def parse_jsonld(html,cfg,src):
    iid,name,default,sources,hosts=cfg
    out=[]; n=0
    for raw in re.findall(r'<script\b[^>]*type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>',html,re.I):
        try:data=json.loads(unescape(raw.strip()))
        except Exception:continue
        for x in walk(data):
            title=textify(str(x.get("headline") or x.get("name") or ""))
            ru=x.get("url") or x.get("@id") or x.get("mainEntityOfPage") or ""
            if isinstance(ru,dict):ru=ru.get("@id") or ru.get("url") or ""
            url=official(str(ru),src,hosts)
            date=getdate(x.get("datePublished") or x.get("dateCreated") or x.get("dateModified") or "") or date_url(url)
            if not good(title,url,date,sources,hosts):continue
            note=textify(str(x.get("description") or x.get("abstract") or ""))[:260]
            out.append(item(cfg,title,url,date,src,n,note)); n+=1
    return out

def parse_feed_xml(xml,cfg,src):
    iid,name,default,sources,hosts=cfg
    out=[]; n=500
    blocks=re.findall(r"<(?:item|entry)\b[\s\S]*?</(?:item|entry)>",xml or "",re.I)
    for b in blocks:
        tm=re.search(r"<title\b[^>]*>([\s\S]*?)</title>",b,re.I)
        title=textify(tm.group(1) if tm else "")
        lm=re.search(r"<link\b[^>]*href=[\"']([^\"']+)[\"'][^>]*/?>",b,re.I)
        if not lm:
            lm=re.search(r"<link\b[^>]*>([\s\S]*?)</link>",b,re.I)
        raw=clean(unescape(lm.group(1) if lm else ""))
        url=official(raw,src,hosts)
        dm=re.search(r"<(?:pubDate|published|updated|dc:date)\b[^>]*>([\s\S]*?)</(?:pubDate|published|updated|dc:date)>",b,re.I)
        date=getdate(textify(dm.group(1) if dm else "")) or date_url(url)
        desc=""
        xm=re.search(r"<(?:description|summary|content:encoded)\b[^>]*>([\s\S]*?)</(?:description|summary|content:encoded)>",b,re.I)
        if xm: desc=textify(xm.group(1))[:260]
        if not good(title,url,date,sources,hosts):continue
        out.append(item(cfg,title,url,date,src,n,desc)); n+=1
    return out

def parse_anchors(html,cfg,src):
    iid,name,default,sources,hosts=cfg
    out=[]; n=1000
    rg=re.compile(r'<a\b([^>]*?\bhref\s*=\s*["\']([^"\']+)["\'][^>]*)>([\s\S]*?)</a>',re.I)
    for m in rg.finditer(html):
        title=textify(m.group(3)); url=official(m.group(2),src,hosts)
        lo=max(0,m.start()-500); hi=min(len(html),m.end()+700)
        near=html[lo:hi].replace(m.group(0),f" {title} ",1)
        # Other links are removed so their dates cannot contaminate this item.
        near=re.sub(r'<a\b[^>]*>[\s\S]*?</a>',' ',near,flags=re.I)
        near_text=textify(near)
        date=(getdate_dmy(near_text) if iid=="fgv" else "") or getdate(near_text) or date_url(url)
        if not good(title,url,date,sources,hosts):continue
        p=re.search(r'<p\b[^>]*>([\s\S]*?)</p>',near,re.I)
        note=textify(p.group(1))[:260] if p else ""
        out.append(item(cfg,title,url,date,src,n,note)); n+=1
        if n>2200:break
    return out

def dedupe(xs):
    seen_u=set();seen_t=set();out=[]
    for x in xs:
        u=clean(x.get("url"));t=clean(x.get("title"))
        uk=re.sub(r"[?#].*$","",u).rstrip("/").lower()
        tk=re.sub(r"[^0-9a-z가-힣一-龥ぁ-んァ-ン]+","",t.lower())
        if not u or not t or uk in seen_u or (tk and tk in seen_t):continue
        seen_u.add(uk);seen_t.add(tk);out.append(x)
    out.sort(key=lambda x:(clean(x.get("date")),-int(x.get("order") or 0)),reverse=True)
    return out

def fetch_browser(url):
    exe=shutil.which("google-chrome") or shutil.which("google-chrome-stable") or shutil.which("chromium") or shutil.which("chromium-browser")
    if not exe:raise RuntimeError("headless Chrome not available on runner")
    try:
        p=subprocess.run(
            [exe,"--headless=new","--no-sandbox","--disable-gpu","--disable-dev-shm-usage",
             "--disable-background-networking","--dump-dom",url],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False,timeout=28
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("headless Chrome timed out")
    if p.returncode==0 and len(p.stdout)>=200:
        return p.stdout.decode("utf-8",errors="replace")
    err=p.stderr.decode("utf-8",errors="replace").strip()
    raise RuntimeError(err or f"headless Chrome exit {p.returncode}")

def fetch(url):
    err=None
    for i in range(1):
        try:
            r=Request(url,headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml,application/xml,application/rss+xml,application/atom+xml;q=0.9,*/*;q=0.8","Accept-Language":"en-US,en;q=0.8,ja;q=0.6,pt-BR;q=0.5","Cache-Control":"no-cache"})
            with urlopen(r,timeout=10) as z:
                b=z.read()
                enc=z.headers.get_content_charset() or "utf-8"
                text=b.decode(enc,errors="replace")
                if len(text)<200:raise RuntimeError("response too short")
                return text
        except Exception as e:
            err=e
    # GitHub runner curl fallback: still fetches only the same official source URL.
    try:
        p=subprocess.run(
            ["curl","-L","--fail","--silent","--show-error","--compressed","--http1.1",
             "-A",UA,"-H","Accept-Language: en-US,en;q=0.8,ja;q=0.6,pt-BR;q=0.5",
             "--connect-timeout","8","--max-time","15",url],
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False
        )
        if p.returncode==0 and len(p.stdout)>=200:
            return p.stdout.decode("utf-8",errors="replace")
        cerr=p.stderr.decode("utf-8",errors="replace").strip()
        if cerr: err=RuntimeError(cerr)
    except Exception as e:
        err=e
    try:
        return fetch_browser(url)
    except Exception as e:
        err=e
    raise RuntimeError(str(err))

def load(path):
    try:
        x=json.loads(path.read_text(encoding="utf-8"))
        return x if isinstance(x,dict) else None
    except Exception:return None

def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    s=json.dumps(obj,ensure_ascii=False,indent=2)+"\n"
    if not path.exists() or path.read_text(encoding="utf-8")!=s:path.write_text(s,encoding="utf-8")

def one(cfg):
    iid,name,default,sources,hosts=cfg
    path=OUT/f"{iid}.json"; old=load(path)
    old_items=old.get("items",[]) if old and isinstance(old.get("items"),list) else []
    got=[];errors=[];winner=""
    for src in sources:
        try:
            h=fetch(src); p=dedupe(parse_feed_xml(h,cfg,src)+parse_jsonld(h,cfg,src)+parse_anchors(h,cfg,src))
            if not p and iid in ("mgi","bruegel","cigi"):
                try:
                    hb=fetch_browser(src)
                    p=dedupe(parse_feed_xml(hb,cfg,src)+parse_jsonld(hb,cfg,src)+parse_anchors(hb,cfg,src))
                except Exception:
                    pass
            if p:
                winner=winner or src;got.extend(p)
            if len(dedupe(got))>=MAX_ITEMS:break
        except Exception as e:errors.append(f"{src}: {e}")
    live=dedupe(got)
    if not live:return False,old," | ".join(errors) or "official parser returned no dated items"
    merged=dedupe(live+old_items)[:MAX_ITEMS]
    now=datetime.now(timezone.utc)
    payload={"ok":True,"id":iid,"institution":name,"provider":"OFFICIAL-WEB-GITHUB-ACTIONS","officialOnly":True,
             "sourceUrl":winner or sources[0],"fetchedAt":now.isoformat().replace("+00:00","Z"),
             "fetchedAtKorea":now.astimezone(KST).strftime("%Y. %m. %d. %H:%M:%S KST"),
             "itemCount":len(merged),"items":merged}
    save(path,payload);return True,payload,""

def targets(mode,prev):
    if mode!="retry":return CFG[:]
    today=datetime.now(KST).strftime("%Y-%m-%d")
    if not prev or prev.get("runDateKst")!=today:return CFG[:]
    bad={x.get("id") for x in prev.get("institutions",[]) if not x.get("fetchOk",x.get("ok"))}
    return [x for x in CFG if x[0] in bad]

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--mode",choices=("primary","retry"),default="primary");ap.add_argument("--only",default="");ap.add_argument("--no-sleep",action="store_true")
    a=ap.parse_args();OUT.mkdir(parents=True,exist_ok=True);prev=load(STATUS);todo=targets(a.mode,prev)
    if a.only:
        ids={x.strip().lower() for x in a.only.split(",") if x.strip()};todo=[x for x in CFG if x[0] in ids]
    rows={x.get("id"):x for x in (prev or {}).get("institutions",[]) if isinstance(x,dict)}
    print(f"[AUTO15] mode={a.mode} targets={len(todo)}")
    for i,cfg in enumerate(todo):
        iid,name,default,sources,hosts=cfg;started=datetime.now(timezone.utc)
        try:ok,payload,error=one(cfg)
        except Exception as e:ok,payload,error=False,load(OUT/f"{iid}.json"),str(e)
        item_count=len((payload or {}).get("items",[])) if isinstance(payload,dict) else 0
        has_data=item_count>0
        rows[iid]={"id":iid,"institution":name,"ok":bool(ok or has_data),"fetchOk":bool(ok),"hasData":has_data,
                   "stale":bool((not ok) and has_data),"itemCount":item_count,
                   "fetchedAt":(payload or {}).get("fetchedAt","") if isinstance(payload,dict) else "",
                   "sourceUrl":(payload or {}).get("sourceUrl",sources[0]) if isinstance(payload,dict) else sources[0],
                   "lastAttemptAt":started.isoformat().replace("+00:00","Z"),"error":error}
        print(f"[AUTO15] {iid:7s} {'OK' if ok else 'FAIL'} items={rows[iid]['itemCount']} {error[:160]}")
        if not a.no_sleep and i+1<len(todo):time.sleep(.8)
    ordered=[rows.get(c[0],{"id":c[0],"institution":c[1],"ok":False,"itemCount":0,"fetchedAt":"","sourceUrl":c[3][0],"lastAttemptAt":"","error":"not attempted yet"}) for c in CFG]
    now=datetime.now(timezone.utc)
    st={"ok":all(bool(x.get("ok")) for x in ordered),"version":"1.0.0","provider":"OFFICIAL-WEB-GITHUB-ACTIONS","officialOnly":True,
        "paidApi":False,"searchApi":False,"aiTokens":False,"mode":a.mode,"runDateKst":now.astimezone(KST).strftime("%Y-%m-%d"),
        "updatedAt":now.isoformat().replace("+00:00","Z"),"updatedAtKorea":now.astimezone(KST).strftime("%Y. %m. %d. %H:%M:%S KST"),
        "count":15,"successCount":sum(1 for x in ordered if x.get("ok")),
        "freshSuccessCount":sum(1 for x in ordered if x.get("fetchOk",x.get("ok"))),
        "staleCount":sum(1 for x in ordered if x.get("stale")),"institutions":ordered}
    save(STATUS,st);print(f"[AUTO15] complete success={st['successCount']}/15")
    return 0

if __name__=="__main__":raise SystemExit(main())
