import time
import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st

st.set_page_config(page_title="네이버 쇼핑 최저가 비교", page_icon="🛍️", layout="centered")
st.title("🛍️ 개별 상품 최저가 비교 알리미")

st.write("비교할 상품 개수를 설정한 뒤, 아래 입력 칸에 각각의 URL을 나누어 입력하세요.")

# 1. 비교할 상품 개수 선택 (2개 ~ 5개)
num_products = st.number_input("비교할 상품 개수 (2~5개)", min_value=2, max_value=5, value=2, step=1)

# 2. 개별 입력 칸 생성
urls = []
default_example_url = "https://m.shopping.naver.com/window-products/cu/11764306439"

for i in range(int(num_products)):
    init_val = default_example_url if i == 0 else ""
    url_input = st.text_input(
        f"상품 #{i+1} URL",
        value=init_val,
        placeholder="https://m.shopping.naver.com/...",
        key=f"product_url_{i}"
    )
    
    # 입력된 텍스트 중 유효한 http(s) 주소만 정제
    if url_input.strip():
        match = re.search(r'https?://[^\s,"]+', url_input.strip())
        if match:
            urls.append(match.group(0).rstrip('.)]'))

st.caption(f"✅ 현재 **{len(urls)}개**의 유효한 상품 URL이 입력되었습니다.")

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

def get_naver_product_info(url):
    """다양한 네이버 상품 페이지 HTML에서 가격 수집"""
    try:
        session = requests.Session()
        res = session.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        res.raise_for_status()
        html = res.text
        soup = BeautifulSoup(html, "html.parser")

        # 1. 상품 제목
        title = "네이버 쇼핑 상품"
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].replace(" : 네이버 쇼핑", "").replace(" : 네이버 스마트스토어", "").strip()

        price = None

        # 2. 메타 태그 검색
        for prop in ["og:price:amount", "product:price:amount", "product:sale_price:amount"]:
            meta = soup.find("meta", property=prop)
            if meta and meta.get("content"):
                digits = re.sub(r"[^\d]", "", meta["content"])
                if digits:
                    price = int(digits)
                    break

        # 3. JSON 구조 내부 가격 파싱
        if price is None:
            matches = re.findall(r'"(?:discountedPrice|salePrice|discountPrice|rawPrice|benefitsViewPrice|mobileDiscountedPrice)":\s*(\d+)', html)
            if matches:
                valid_prices = [int(p) for p in matches if 100 <= int(p) <= 10000000]
                if valid_prices:
                    price = min(valid_prices)

        # 4. HTML 클래스 파싱
        if price is None:
            price_tags = soup.select("._1LY7DqebLu, ._228w0AZ_e3, ._2HP-hn-bWZ, .total_price, .price, .discount_price")
            for tag in price_tags:
                digits = re.sub(r"[^\d]", "", tag.get_text())
                if digits and int(digits) >= 100:
                    price = int(digits)
                    break

        return {"title": title, "price": price, "url": url}
    except Exception:
        return {"title": "수집 불가 (URL 확인 필요)", "price": None, "url": url}

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
        st.warning("비교할 URL을 최소 1개 이상 입력해 주세요.")
    else:
        with st.spinner(f"{len(urls)}개 상품 실시간 데이터 수집 중..."):
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
                    table_data.append({
                        "상태": is_lowest,
                        "상품명": item["title"],
                        "가격": f"{item['price']:,}원" if item["price"] else "수집 실패",
                        "링크": item["url"]
                    })
                st.dataframe(pd.DataFrame(table_data), use_container_width=True)
            else:
                st.error("입력한 URL에서 가격 정보를 불러오지 못했습니다. 올바른 상품 페이지 주소인지 확인해 주세요.")
