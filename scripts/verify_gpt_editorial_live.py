#!/usr/bin/env python3
"""Independent read-only checker for GPT direct feed and live Emperor Court UI.
No secrets, no write actions, no Cloudflare Worker requirements.
"""
import json,sys,urllib.request,shutil,datetime,hashlib,pathlib
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright
BASE="https://raw.githubusercontent.com/treesky0103-dot/emperor-court-feed/main/gpt-editorial/"
PAGE="https://emperor-court-web.pages.dev/"
TODAY=datetime.datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
def fetch(path):
    url=BASE+path+"?independent_check="+str(datetime.datetime.now().timestamp())
    req=urllib.request.Request(url,headers={"Cache-Control":"no-cache","User-Agent":"ZhugeDirectFeedIndependentVerifier/1"})
    with urllib.request.urlopen(req,timeout=35) as res:return res.read()
latest=fetch("latest.json")
daily=fetch("daily/"+TODAY+".json")
assert latest==daily,"GPT_CANONICAL_AND_DAILY_NOT_BYTE_IDENTICAL"
data=json.loads(latest)
assert data.get("schema")=="court-gpt-editorial-v1","GPT_SCHEMA"
assert data.get("date")==TODAY,"GPT_NOT_TODAY"
assert data.get("publisher")=="chatgpt-scheduled-editor","GPT_PUBLISHER_WRONG"
assert data.get("marketValidation")=="NOT_VERIFIED","GPT_MARKET_VERIFICATION_MISREPRESENTED"
assert data.get("planSetId") and data.get("revision"),"GPT_IDENTITY_MISSING"
plans=data.get("plans") or []
assert len(plans)==3 and [p.get("rank") for p in plans]==[1,2,3],"GPT_3_ORDER"
titles=[p.get("title") for p in plans]
assert all(isinstance(t,str) and t.strip() for t in titles) and len(set(titles))==3,"GPT_TITLE_EMPTY_OR_DUPLICATE"
result={"day":TODAY,"feedSha256":hashlib.sha256(latest).hexdigest(),"planSetId":data["planSetId"],
 "revision":data["revision"],"titles":titles,"storageMatch":True,"liveBrowserMatch":False,"zuociUnaffected":False,"pageErrors":[]}
with sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,executable_path=shutil.which("google-chrome") or shutil.which("chromium"),args=["--no-sandbox"])
    page=browser.new_page(locale="ko-KR",timezone_id="Asia/Seoul",viewport={"width":1440,"height":1000})
    page.on("pageerror",lambda e:result["pageErrors"].append(str(e)))
    response=page.goto(PAGE,wait_until="domcontentloaded",timeout=65000)
    assert response and response.status==200,"PAGES_NOT_200"
    assert page.evaluate("Boolean(window.__COURT_GPT_SIDECAR_V1__)"),"GPT_SIDECAR_NOT_DEPLOYED"
    page.get_by_role("button",name="제갈량 오늘의 출판 기획").click(timeout=15000)
    page.locator("#court-gpt-editorial-overlay-v1 .cg-card").first.wait_for(timeout=25000)
    text_nodes=page.locator("#court-gpt-editorial-overlay-v1 .cg-card h3").all_text_contents()
    dom_titles=[x.split(". ",1)[1] for x in text_nodes]
    ident=page.evaluate("window.__COURT_GPT_LAST_RENDER__")
    result["liveBrowserMatch"]=(dom_titles==titles and ident=={"date":TODAY,"planSetId":data["planSetId"],"revision":data["revision"],"titles":titles,"isToday":True})
    body=page.locator("#court-gpt-editorial-overlay-v1").inner_text()
    result["all14Fields"]=all(x in body for x in ["1. 한 줄 콘셉트","3. 경쟁서 검토","7. 저자 후보","9. 마케팅 병법","11. 카드뉴스","14. 제갈량 최종 판단"])
    result["marketStatusHonest"]="시장 검증 미완료" in body
    page.get_by_role("button",name="GPT 기획 닫기").click()
    page.get_by_role("button",name="좌자 금일 베스트셀러 인사이트").click()
    page.locator("#modalOverlay").wait_for(state="visible",timeout=25000)
    page.locator("#bubbleText .zuoci-best-title:visible").first.wait_for(timeout=25000)
    result["zuociUnaffected"]=len(page.locator("#bubbleText .zuoci-best-title:visible").all_text_contents())==10
    browser.close()
result["pass"]=all([result["storageMatch"],result["liveBrowserMatch"],result["zuociUnaffected"],result["all14Fields"],result["marketStatusHonest"],not result["pageErrors"]])
pathlib.Path("proof").mkdir(exist_ok=True)
pathlib.Path("proof/latest-verification.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
print("GPT_DIRECT_PUBLIC_E2E",json.dumps(result,ensure_ascii=False),flush=True)
sys.exit(0 if result["pass"] else 1)
