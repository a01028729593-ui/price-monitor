import time
import re
import json
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st

st.set_page_config(page_title="네이버 쇼핑 최저가 비교", page_icon="🛍️", layout="centered")
st.title("🛍️ 개별 상품 최저가 비교 알리미")

st.info("💡 **안내:** 네이버 서버 트래픽 제한(HTTP 429)을 방지하기 위해 상품 간 1.5초의 간격을 두고 순차 수집합니다.")

num_products = st.number_input("비교할 상품 개수 (2~5개)", min_value=2, max_value=5, value=2, step=1)

urls = []
default_example_url = "https://m.shopping.naver.com/window-products/cu/11764306439"

for i in range(int(num_products)):
    init_val = default_example_url if i == 0 else ""
    url_input = st.text_input(
        f"상품 #{i+1} URL",
        value=init_val,
        placeholder="https://smartstore.naver.com/...",
        key=f"product_url_{i}"
    )
    if url_input.strip():
        urls.append(url_input.strip())

col1, col2 = st.columns(2)
with col1:
    target_price = st.number_input("목표 가격 (원)", value=3200, step=100)
with col2:
    ntfy_topic = st.text_input("ntfy 알림 채널명", value="my_milk_alert_777")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://search.shopping.naver.com/"
}

def clean_target_url(raw_input_url):
    """URL 내 불필요한 인자 정제"""
    match = re.search(r'https?://[^\s,"]+', raw_input_url)
    if not match:
        return raw_input_url
    url = match.group(0).rstrip('.)]')
    
    if "google.com/aclk" in url or "adurl=" in url:
        adurl_match = re.search(r'adurl=([^&]+)', url)
        if adurl_match:
            import urllib.parse
            return urllib.parse.unquote(adurl_match.group(1))
    return url

def get_naver_product_info(raw_url):
    url = clean_target_url(raw_url)
    try:
        session = requests.Session()
        res = session.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        
        # 429(요청 과다) 발생 시 2초 대기 후 1회 재시도
        if res.status_code == 429:
            time.sleep(2.0)
            res = session.get(url, headers=HEADERS, timeout=10, allow_redirects=True)

        if res.status_code == 429:
            return {"title": "요청 제한 (HTTP 429: 잠시 후 다시 시도)", "price": None, "url": url}
        elif res.status_code != 200:
            return {"title": f"접속 불가 (HTTP {res.status_code})", "price": None, "url": url}
            
        html = res.text
        soup = BeautifulSoup(html, "html.parser")

        # 상품 제목 추출
        title = "네이버 쇼핑 상품"
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].replace(" : 네이버 쇼핑", "").replace(" : 네이버 스마트스토어", "").strip()

        price = None

        # 1. OpenGraph / Meta 태그 우선 수집
        for prop in ["og:price:amount", "product:price:amount", "product:sale_price:amount"]:
            meta = soup.find("meta", property=prop)
            if meta and meta.get("content"):
                digits = re.sub(r"[^\d]", "", meta["content"])
                if digits and int(digits) >= 100:
                    price = int(digits)
                    break

        # 2. ld+json 구조 파싱
        if price is None:
            scripts = soup.find_all("script", type="application/ld+json")
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        offers = data.get("offers", {})
                        if isinstance(offers, dict) and "price" in offers:
                            price = int(offers["price"])
                            break
                        elif isinstance(offers, list) and len(offers) > 0 and "price" in offers[0]:
                            price = int(offers[0]["price"])
                            break
                except Exception:
                    pass

        # 3. 정규식 패턴 탐색
        if price is None:
            matches = re.findall(r'"(?:discountedPrice|salePrice|discountPrice|rawPrice|benefitsViewPrice|mobileDiscountedPrice|price)":\s*(\d+)', html)
            if matches:
                valid_prices = [int(p) for p in matches if 100 <= int(p) <= 10000000]
                if valid_prices:
                    price = min(valid_prices)

        return {"title": title, "price": price, "url": url}

    except Exception:
        return {"title": "수집 에러 (네이버 차단 또는 네트워크 에러)", "price": None, "url": url}

def send_push(topic, title, message):
    try:
        requests.post(
            f"https://ntfy.sh/{topic}",
            data=message.encode('utf-8'),
            headers={"Title": title.encode('utf-8').decode('latin-1'), "Priority": "high", "Tags": "tada"},
            timeout=5
        )
    except Exception:
        pass

if st.button("📊 실시간 가격 비교하기", use_container_width=True):
    if not urls:
        st.warning("비교할 URL을 입력해 주세요.")
    else:
        results = []
        progress_bar = st.progress(0)
        
        for idx, u in enumerate(urls):
            # 429 차단 방지를 위해 2번째 요청부터 1.5초 간격 추가
            if idx > 0:
                time.sleep(1.5)
                
            info = get_naver_product_info(u)
            results.append(info)
            progress_bar.progress((idx + 1) / len(urls))
            
        valid_items = [r for r in results if r["price"] is not None]

        if valid_items:
            min_item = min(valid_items, key=lambda x: x["price"])
            st.subheader("👑 최저가 상품")
            st.success(f"**[{min_item['title']}]**\n\n💰 최저가: **{min_item['price']:,}원** (목표가: {target_price:,}원)")

            if min_item["price"] <= target_price:
                st.balloons()
                msg = f"🏆 최저가 달성!\n{min_item['title']}\n가격: {min_item['price']:,}원"
                send_push(ntfy_topic, "🎉 최저가 달성!", msg)
                st.info("📲 ntfy 푸시 알림을 발송했습니다.")

            st.subheader("📋 전체 비교표")
            table_data = []
            for item in results:
                is_lowest = "🏆 최저가" if (item["price"] and item["price"] == min_item["price"]) else ""
                status_str = f"{item['price']:,}원" if item["price"] else "수집 실패"
                table_data.append({
                    "상태": is_lowest,
                    "상품명": item["title"],
                    "가격": status_str,
                    "링크": item["url"]
                })
            st.dataframe(pd.DataFrame(table_data), use_container_width=True)
        else:
            st.error("모든 URL에서 가격 수집에 실패했습니다. (HTTP 429 차단 시 1~2분 후 다시 시도해 보세요.)")
