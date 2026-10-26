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
    assert page.evaluate("Boolean(window.__COURT_GPT_NATIVE_BRIDGE_V2__)"),"GPT_NATIVE_BRIDGE_NOT_DEPLOYED"
    assert page.evaluate("!window.__COURT_GPT_SIDECAR_V1__"),"OLD_REPLACEMENT_MODAL_STILL_ACTIVE"
    page.get_by_role("button",name="제갈량 오늘의 출판 기획").click(timeout=15000)
    host='#modalOverlay.show[data-active-advisor="zhuge"] #zhugeUnifiedPlansHost'
    page.locator(host+' .v465-plan-list[data-gpt-fingerprint] .v465-plan-card').first.wait_for(timeout=26000)
    node_texts=page.locator(host+' .v465-plan-list .v465-plan-type').all_text_contents()
    title_ok=(len(node_texts)==3 and all(titles[i] in node_texts[i] for i in range(3)))
    ident=page.evaluate("window.__COURT_GPT_LAST_RENDER__")
    result["liveBrowserMatch"]=(title_ok and ident=={"date":TODAY,"planSetId":data["planSetId"],"revision":data["revision"],"titles":titles,"isToday":True,"renderer":"native-zhuge-modal-v2"})
    result["originalDesignRetained"]=all([
        page.locator('#modalOverlay .bubble-card.zhuge-full-card').count()==1,
        page.locator('#modalOverlay .zhuge-left-card.court-portrait-card').is_visible(),
        page.locator('#zhugeTabsSiblingHost .v22-zhuge-tab').count()==2,
        page.locator(host+' .v465-plan-list .v465-plan-card.v21544-display-first-card').count()==3
    ])
    details=page.locator(host+' .v465-plan-list article.v465-plan-card details')
    for i in range(3):details.nth(i).locator('summary').click()
    body=page.locator(host).inner_text()
    result["all14Fields"]=all(x in body for x in ["1. 한 줄 콘셉트","3. 경쟁서 검토","7. 저자 후보","9. 마케팅 병법","11. 카드뉴스","14. 제갈량 판단"])
    result["marketStatusHonest"]="미검증" in body
    pathlib.Path("proof").mkdir(exist_ok=True)
    page.locator('#modalOverlay').screenshot(path="proof/native-zhuge-screenshot.png")
    page.locator("#v166InlineBubbleBack:visible").click(timeout=12000)
    page.get_by_role("button",name="좌자 금일 베스트셀러 인사이트").click()
    page.locator("#modalOverlay").wait_for(state="visible",timeout=25000)
    page.locator("#bubbleText .zuoci-best-title:visible").first.wait_for(timeout=25000)
    result["zuociUnaffected"]=len(page.locator("#bubbleText .zuoci-best-title:visible").all_text_contents())==10
    browser.close()
result["pass"]=all([result["storageMatch"],result["liveBrowserMatch"],result["originalDesignRetained"],result["zuociUnaffected"],result["all14Fields"],result["marketStatusHonest"],not result["pageErrors"]])
pathlib.Path("proof").mkdir(exist_ok=True)
pathlib.Path("proof/latest-verification.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
print("GPT_DIRECT_PUBLIC_E2E",json.dumps(result,ensure_ascii=False),flush=True)
sys.exit(0 if result["pass"] else 1)
