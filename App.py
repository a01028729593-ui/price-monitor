import time
import re
import json
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st

st.set_page_config(page_title="네이버 쇼핑 최저가 비교", page_icon="🛍️", layout="centered")
st.title("🛍️ 개별 상품 최저가 비교 알리미")

st.info("💡 **팁:** Google 광고 링크(`google.com/aclk...`) 대신, 상품 페이지에 직접 들어간 뒤 주소창의 진짜 네이버 주소를 복사해 넣으면 수집 성공률이 훨씬 높아집니다.")

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
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate"
}

def clean_target_url(raw_input_url):
    """구글 광고 링크 등 리다이렉트 주소에서 진짜 URL을 추출하고 정제"""
    match = re.search(r'https?://[^\s,"]+', raw_input_url)
    if not match:
        return raw_input_url
    url = match.group(0).rstrip('.)]')
    
    # google ad추적 주소 내부의 진짜 url 추출 시도
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
        
        if res.status_code != 200:
            return {"title": f"접속 실패 (HTTP {res.status_code})", "price": None, "url": url}
            
        html = res.text
        soup = BeautifulSoup(html, "html.parser")

        # 1. 제목 추출
        title = "네이버 쇼핑 상품"
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].replace(" : 네이버 쇼핑", "").replace(" : 네이버 스마트스토어", "").strip()

        price = None

        # 2. OpenGraph / Meta 태그 우선 수집
        for prop in ["og:price:amount", "product:price:amount", "product:sale_price:amount"]:
            meta = soup.find("meta", property=prop)
            if meta and meta.get("content"):
                digits = re.sub(r"[^\d]", "", meta["content"])
                if digits and int(digits) >= 100:
                    price = int(digits)
                    break

        # 3. ld+json 구조 파싱
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

        # 4. 정규식 JSON 키값 매칭
        if price is None:
            matches = re.findall(r'"(?:discountedPrice|salePrice|discountPrice|rawPrice|benefitsViewPrice|mobileDiscountedPrice|price)":\s*(\d+)', html)
            if matches:
                valid_prices = [int(p) for p in matches if 100 <= int(p) <= 10000000]
                if valid_prices:
                    price = min(valid_prices)

        if price is None:
            return {"title": title, "price": None, "url": url, "err": "가격을 찾을 수 없음"}

        return {"title": title, "price": price, "url": url, "err": None}

    except Exception as e:
        return {"title": "수집 에러", "price": None, "url": url, "err": str(e)}

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
        with st.spinner(f"{len(urls)}개 상품 분석 중..."):
            results = [get_naver_product_info(u) for u in urls]
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
                st.error("입력한 URL에서 가격 정보를 읽지 못했습니다.")
                for r in results:
                    st.caption(f"❌ {r['url'][:60]}... -> {r['title']}")
