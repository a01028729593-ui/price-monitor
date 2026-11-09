import time
import re
import json
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st

st.set_page_config(page_title="네이버 쇼핑 최저가 비교", page_icon="🛍️", layout="centered")
st.title("🛍️ 개별 상품 최저가 비교 알리미")

st.info("💡 **안내:** 브랜드스토어 및 스마트스토어 주소의 복잡한 추적 파라미터를 자동 정제하여 순수 상품 주소로 수집합니다.")

num_products = st.number_input("비교할 상품 개수 (2~5개)", min_value=2, max_value=5, value=2, step=1)

urls = []
default_example_url = "https://brand.naver.com/namyang/products/12286394475"

for i in range(int(num_products)):
    init_val = default_example_url if i == 0 else ""
    url_input = st.text_input(
        f"상품 #{i+1} URL",
        value=init_val,
        placeholder="https://brand.naver.com/... 또는 https://smartstore.naver.com/...",
        key=f"product_url_{i}"
    )
    if url_input.strip():
        urls.append(url_input.strip())

col1, col2 = st.columns(2)
with col1:
    target_price = st.number_input("목표 가격 (원)", value=3200, step=100)
with col2:
    ntfy_topic = st.text_input("ntfy 알림 채널명", value="my_milk_alert_777")

HEADERS_MOBILE = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://m.shopping.naver.com/"
}

HEADERS_PC = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://search.shopping.naver.com/"
}

def clean_url(raw_url):
    """Google 광고 및 네이버 브랜드스토어/스마트스토어 추적 파라미터(?nl-query=...) 자동 제거"""
    match = re.search(r'https?://[^\s,"]+', raw_url)
    if not match:
        return raw_url
    url = match.group(0).rstrip('.)]')
    
    # 구글 광고 주소 정제
    if "google.com/aclk" in url or "adurl=" in url:
        adurl_match = re.search(r'adurl=([^&]+)', url)
        if adurl_match:
            import urllib.parse
            url = urllib.parse.unquote(adurl_match.group(1))
            
    # 네이버 상품 번호 기준 순수 URL 추출 (/products/12345678)
    product_match = re.search(r'(https?://[^/]+/products/\d+)', url)
    if product_match:
        url = product_match.group(1)
        
    return url

def fetch_html(url, headers):
    session = requests.Session()
    res = session.get(url, headers=headers, timeout=10, allow_redirects=True)
    if res.status_code == 429:
        time.sleep(2.0)
        res = session.get(url, headers=headers, timeout=10, allow_redirects=True)
    return res

def parse_price_and_title(html):
    soup = BeautifulSoup(html, "html.parser")
    
    title = "네이버 쇼핑 상품"
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].replace(" : 네이버 쇼핑", "").replace(" : 네이버 스마트스토어", "").replace(" : 네이버 브랜드스토어", "").strip()

    price = None

    # 1. OpenGraph 메타 태그
    for prop in ["og:price:amount", "product:price:amount", "product:sale_price:amount"]:
        meta = soup.find("meta", property=prop)
        if meta and meta.get("content"):
            digits = re.sub(r"[^\d]", "", meta["content"])
            if digits and int(digits) >= 100:
                price = int(digits)
                break

    # 2. JSON-LD 파싱
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

    # 3. JSON 정규식 수집
    if price is None:
        matches = re.findall(r'"(?:discountedPrice|salePrice|discountPrice|rawPrice|benefitsViewPrice|mobileDiscountedPrice|price|rawDiscountedPrice)":\s*(\d+)', html)
        if matches:
            valid_prices = [int(p) for p in matches if 100 <= int(p) <= 10000000]
            if valid_prices:
                price = min(valid_prices)

    return title, price

def get_naver_product_info(raw_url):
    url = clean_url(raw_url)
    try:
        # 1차: 모바일 URL 요청
        mobile_url = url.replace("://brand.naver.com", "://m.brand.naver.com").replace("://smartstore.naver.com", "://m.smartstore.naver.com")
        res = fetch_html(mobile_url, HEADERS_MOBILE)
        
        if res.status_code == 200:
            title, price = parse_price_and_title(res.text)
            if price is not None:
                return {"title": title, "price": price, "url": url, "reason": "성공"}

        # 2차: PC URL 요청
        res_pc = fetch_html(url, HEADERS_PC)
        if res_pc.status_code == 429:
            return {"title": "요청 제한", "price": None, "url": url, "reason": "HTTP 429 (1~2분 후 다시 시도)"}
        elif res_pc.status_code == 403:
            return {"title": "접속 거부", "price": None, "url": url, "reason": "HTTP 403 (보안 차단)"}
        elif res_pc.status_code != 200:
            return {"title": "접속 실패", "price": None, "url": url, "reason": f"HTTP 에러 {res_pc.status_code}"}

        title, price = parse_price_and_title(res_pc.text)
        if price is None:
            return {"title": title, "price": None, "url": url, "reason": "가격을 찾을 수 없음"}

        return {"title": title, "price": price, "url": url, "reason": "성공"}

    except Exception as e:
        return {"title": "수집 에러", "price": None, "url": url, "reason": f"네트워크 오류 ({str(e)})"}

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
                status_str = f"{item['price']:,}원" if item["price"] else f"수집 실패 ({item['reason']})"
                table_data.append({
                    "상태": is_lowest,
                    "상품명": item["title"],
                    "가격": status_str,
                    "링크": item["url"]
                })
            st.dataframe(pd.DataFrame(table_data), use_container_width=True)
        else:
            st.error("모든 URL에서 가격 수집에 실패했습니다. 아래 원인을 확인하세요.")
            for r in results:
                st.warning(f"❌ **URL**: {r['url']}\n\n**실패 사유**: {r['reason']}")
