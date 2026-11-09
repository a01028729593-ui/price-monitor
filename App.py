import time
import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st

st.set_page_config(page_title="다중 최저가 비교 모니터링", page_icon="🛍️", layout="centered")

st.title("🛍️ 다중 상품 최저가 비교 알리미")
st.write("여러 개의 네이버 쇼핑 URL을 입력하면 실시간 가격을 비교하여 **최고 가성비 최저가 상품**을 찾아냅니다.")

# 1. 사용자 입력 부분 (여러 URL을 줄바꿈으로 입력)
default_urls = (
    "https://m.shopping.naver.com/window-products/cu/11764306439\n"
    "https://m.shopping.naver.com/window-products/cu/11764306439"
)

urls_input = st.text_area(
    "1. 비교할 네이버 쇼핑 URL 목록 (한 줄에 1개씩 입력)",
    value=default_urls,
    height=120
)

target_price = st.number_input("2. 목표 가격 (원)", value=3200, step=100)
ntfy_topic = st.text_input("3. 핸드폰 ntfy 알림 채널명", value="my_milk_alert_777")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
    )
}

def get_naver_product_info(url: str):
    """단일 URL에서 상품명과 가격을 수집하는 함수"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        html_text = response.text
        soup = BeautifulSoup(html_text, "html.parser")
        
        # 상품 제목 파싱
        title = "상품 (제목 읽기 불가)"
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].strip()

        # 가격 파싱 (1차: OpenGraph)
        price = None
        for meta_prop in ["og:price:amount", "product:price:amount"]:
            meta_tag = soup.find("meta", property=meta_prop)
            if meta_tag and meta_tag.get("content"):
                digits = re.sub(r"[^\d]", "", meta_tag["content"])
                if digits:
                    price = int(digits)
                    break

        # 가격 파싱 (2차: JSON regex)
        if price is None:
            price_matches = re.findall(r'"(?:discountedPrice|salePrice|price|rawPrice)":\s*(\d+)', html_text)
            if price_matches:
                valid_prices = [int(p) for p in price_matches if int(p) >= 500]
                if valid_prices:
                    price = min(valid_prices)

        # 가격 파싱 (3차: HTML selector)
        if price is None:
            selectors = ["._1LY7DqebLu", "._228w0AZ_e3", "._2HP-hn-bWZ", ".total_price", ".price"]
            for sel in selectors:
                tag = soup.select_one(sel)
                if tag:
                    digits = re.sub(r"[^\d]", "", tag.get_text())
                    if digits:
                        price = int(digits)
                        break

        return {"title": title, "price": price, "url": url}
    except Exception:
        return {"title": "수집 실패", "price": None, "url": url}

def send_push(topic: str, title: str, message: str):
    """ntfy 알림 전송"""
    try:
        url = f"https://ntfy.sh/{topic}"
        requests.post(
            url,
            data=message.encode('utf-8'),
            headers={
                "Title": title.encode('utf-8').decode('latin-1'),
                "Priority": "high",
                "Tags": "tada,shopping"
            },
            timeout=5
        )
    except Exception:
        pass

# 2. 가격 비교 및 분석 로직
if st.button("📊 실시간 가격 비교하기", use_container_width=True):
    urls = [url.strip() for url in urls_input.split("\n") if url.strip()]
    
    if not urls:
        st.warning("비교할 URL을 1개 이상 입력해 주세요.")
    else:
        with st.spinner(f"{len(urls)}개 상품 가격 조회 중..."):
            results = []
            for url in urls:
                info = get_naver_product_info(url)
                results.append(info)
            
            # 성공한 상품들 중 가격 비교
            valid_items = [r for r in results if r["price"] is not None]
            
            if valid_items:
                # 최저가 상품 탐색
                min_item = min(valid_items, key=lambda x: x["price"])
                
                st.subheader("👑 비교 결과: 최저가 상품")
                st.success(
                    f"**[{min_item['title']}]**\n\n"
                    f"💰 최저 가격: **{min_item['price']:,}원** (목표가: {target_price:,}원)"
                )
                
                # 목표가 도달 시 알림 및 이펙트
                if min_item["price"] <= target_price:
                    st.balloons()
                    msg = f"🏆 최저가 달성!\n상품: {min_item['title']}\n가격: {min_item['price']:,}원"
                    send_push(ntfy_topic, "🎉 최저가 상품 발견!", msg)
                    st.info("📲 ntfy 스마트폰 푸시 알림을 발송했습니다.")

                # 전체 비교 표 출력
                st.subheader("📋 전체 상품 가격 비교표")
                table_data = []
                for item in results:
                    is_lowest = "🏆 최저가" if (item["price"] is not None and item["price"] == min_item["price"]) else ""
                    table_data.append({
                        "상태": is_lowest,
                        "상품명": item["title"],
                        "가격": f"{item['price']:,}원" if item["price"] else "수집 실패",
                        "링크": item["url"]
                    })
                
                df = pd.DataFrame(table_data)
                st.dataframe(df, use_container_width=True)
            else:
                st.error("입력한 모든 URL에서 가격 정보를 불러오지 못했습니다.")

