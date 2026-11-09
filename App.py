import time
import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st

st.set_page_config(page_title="다중 최저가 비교 모니터링", page_icon="🛍️", layout="centered")

st.title("🛍️ 다중 상품 최저가 비교 알리미")
st.write("여러 개의 상품 URL을 입력하면 실시간 가격을 비교하여 **최저가 상품**을 찾아냅니다.")

# 기본 예시 URL
default_urls = (
    "https://m.shopping.naver.com/window-products/cu/11764306439\n"
    "https://m.shopping.naver.com/window-products/cu/11764306439"
)

# 1. 텍스트 입력 영역
urls_input = st.text_area(
    "1. 비교할 상품 URL 목록 (띄어쓰기, 줄바꿈, 쉼표 등 자유롭게 붙여넣기 가능)",
    value=default_urls,
    height=150,
    help="모바일 화면에서 URL이 긴 탓에 여러 줄로 끊겨 보여도 알아서 주소별로 분할 인식합니다."
)

# 정규식을 사용해 유효한 URL 자동 추출
extracted_urls = re.findall(r'https?://[^\s,]+', urls_input)

# 인식된 URL 개수 안내
if extracted_urls:
    st.caption(f"✅ 총 **{len(extracted_urls)}개**의 유효한 URL 주소가 인식되었습니다.")
else:
    st.caption("⚠️ 인식된 URL이 없습니다. 올바른 주소를 입력해 주세요.")

target_price = st.number_input("2. 목표 가격 (원)", value=3200, step=100)
ntfy_topic = st.text_input("3. 핸드폰 ntfy 알림 채널명", value="my_milk_alert_777")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
    )
}

def get_naver_product_info(url:
