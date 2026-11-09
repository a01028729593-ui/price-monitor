import time
import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st

st.set_page_config(page_title="최저가 비교 모니터링", page_icon="🛍️", layout="centered")
st.title("🛍️ 다중 상품 최저가 비교 알리미")

default_urls = (
    "https://m.shopping.naver.com/window-products/cu/11764306439\n"
    "https://m.shopping.naver.com/window-products/cu/11764306439"
)

urls_input = st.text_area(
    "1. 비교할 상품 URL 목록 (자유롭게 붙여넣기 가능)",
    value=default_urls,
    height=120
)

extracted_urls = re.findall(r'https?://[^\s,]+', urls_input)

if extracted_urls:
    st.caption(f"✅ 총 **{len(extracted_urls)}개**의 URL이 인식되었습니다.")
else:
    st.caption("⚠️ 인식된 URL이 없습니다.")

target_price = st.number_input("2. 목표 가격 (원)", value=3200, step=100)
ntfy_topic = st.text_input("3. ntfy 알림 채널명", value="my_milk_alert_777")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
}

def get_naver_product_info(url):
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        html = res.text
        soup = BeautifulSoup(html, "html.parser")
        
        title = "상품 (제목 읽기 불가)"
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()

        price = None
        for prop in ["og:price:amount", "product:price:amount"]:
            meta = soup.find("meta", property=prop)
            if meta and meta.get("content"):
                digits = re.sub(r"[^\d]", "", meta["content"])
                if digits:
                    price = int(digits)
                    break

        if price is None:
            matches = re.findall(r'"(?:discountedPrice|salePrice|price|rawPrice)":\s*(\d+)', html)
            if matches:
                valid = [int(p) for p in matches if int(p) >= 500]
                if valid:
                    price = min(valid)

        return {"title": title, "price": price, "url": url}
    except Exception:
        return {"title": "수집 실패", "price": None, "url": url}

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
    if not extracted_urls:
        st.warning("분석할 URL을 입력해 주세요.")
    else:
        with st.spinner(f"{len(extracted_urls)}개 상품 수집 중..."):
            results = [get_naver_product_info(u) for u in extracted_urls]
            valid_items = [r for r in results if r["price"] is not None]
            
            if valid_items:
                min_item = min(valid_items, key=lambda x: x["price"])
                st.subheader("👑 최저가 상품")
                st.success(f"**[{min_item['title']}]**\n\n💰 가격: **{min_item['price']:,}원** (목표가: {target_price:,}원)")
                
                if min_item["price"] <= target_price:
                    st.balloons()
                    msg = f"🏆 최저가 달성!\n{min_item['title']}\n가격: {min_item['price']:,}원"
                    send_push(ntfy_topic, "🎉 최저가 달성!", msg)
                    st.info("📲 ntfy 푸시 알림을 전송했습니다.")

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
                st.error("가격 정보를 가져오지 못했습니다.")

