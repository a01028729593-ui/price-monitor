import time
import re
import requests
from bs4 import BeautifulSoup
import streamlit as st

st.set_page_config(page_title="최저가 모니터링", page_icon="🥛", layout="centered")

st.title("🥛 네이버 쇼핑 우유 최저가 알리미")
st.write("원하는 상품 링크와 목표가를 입력하고 실시간 조회를 확인하세요.")

target_url = st.text_input(
    "1. 네이버 쇼핑 상품 URL", 
    value="https://m.shopping.naver.com/window-products/cu/11764306439"
)
target_price = st.number_input("2. 목표 가격 (원)", value=3200, step=100)
ntfy_topic = st.text_input("3. 핸드폰 ntfy 알림 채널명", value="my_milk_alert_777")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
    )
}

def get_naver_price(url: str):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        html_text = response.text
        soup = BeautifulSoup(html_text, "html.parser")
        
        for meta_prop in ["og:price:amount", "product:price:amount"]:
            meta_tag = soup.find("meta", property=meta_prop)
            if meta_tag and meta_tag.get("content"):
                digits = re.sub(r"[^\d]", "", meta_tag["content"])
                if digits:
                    return int(digits)

        price_matches = re.findall(r'"(?:discountedPrice|salePrice|price|rawPrice)":\s*(\d+)', html_text)
        if price_matches:
            valid_prices = [int(p) for p in price_matches if int(p) >= 500]
            if valid_prices:
                return min(valid_prices)

        return None
    except Exception:
        return None

def send_push(topic: str, message: str):
    try:
        url = f"https://ntfy.sh/{topic}"
        requests.post(
            url,
            data=message.encode('utf-8'),
            headers={
                "Title": "🎉 최저가 달성 알림!".encode('utf-8').decode('latin-1'),
                "Priority": "high",
                "Tags": "tada,milk"
            },
            timeout=5
        )
    except Exception:
        pass

col1, col2 = st.columns(2)

with col1:
    if st.button("🔍 지금 바로 가격 확인", use_container_width=True):
        with st.spinner("가격 조회 중..."):
            price = get_naver_price(target_url)
            if price:
                st.success(f"현재가: **{price:,}원** (목표가: {target_price:,}원)")
                if price <= target_price:
                    st.balloons()
                    send_push(ntfy_topic, f"현재가 {price:,}원! 목표가 이하 달성")
                    st.info("📲 핸드폰 상단바 푸시 알림을 발송했습니다.")
            else:
                st.error("가격 데이터를 읽지 못했습니다. URL을 확인해 주세요.")

with col2:
    if st.button("🚀 자동 모니터링 테스트 (5회)", use_container_width=True):
        status_area = st.empty()
        for i in range(5):
            price = get_naver_price(target_url)
            current_time = time.strftime("%H:%M:%S")
            if price:
                status_area.write(f"[{current_time}] ({i+1}/5회) 현재가: **{price:,}원**")
                if price <= target_price:
                    send_push(ntfy_topic, f"현재가 {price:,}원! 목표가 이하 달성")
            else:
                status_area.write(f"[{current_time}] 수집 실패")
            time.sleep(5)
        st.success("테스트가 완료되었습니다.")
