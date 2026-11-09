import time
import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st

st.set_page_config(page_title="네이버 쇼핑 최저가 비교", page_icon="🛍️", layout="centered")
st.title("🛍️ 다중 상품 최저가 비교 알리미")

st.markdown("""
PC나 모바일 어디서든 복사한 **상품 주소(또는 주소가 포함된 텍스트 전체)**를 붙여넣으세요.
주소가 길거나 텍스트가 섞여 있어도 유효한 네이버 상품 주소만 자동으로 추출합니다.
""")

# 1. 단일 대형 입력창 (복사한 텍스트 통째로 붙여넣기 가능)
default_text = (
    "https://m.shopping.naver.com/window-products/cu/11764306439\n"
    "https://smartstore.naver.com/maeille/products/4862446698"
)

raw_input = st.text_area(
    "상품 URL 목록 붙여넣기",
    value=default_text,
    height=150,
    help="줄바꿈, 쉼표, 문맥 텍스트가 포함되어 있어도 https:// 주소만 자동 추출합니다."
)

# URL 자동 정제 로직 (다양한 네이버 주소 포맷 대응)
def extract_clean_urls(text):
    if not text:
        return []
    # http(s) 주소 패턴 추출 (공백, 쉼표, 따옴표 제외)
    matches = re.findall(r'https?://[^\s,"]+', text)
    valid_urls = []
    for m in matches:
        clean_url = m.rstrip('.)]')
        if clean_url not in valid_urls:
            valid_urls.append(clean_url)
    return valid_urls

extracted_urls = extract_clean_urls(raw_input)

if extracted_urls:
    st.caption(f"✅ 총 **{len(extracted_urls)}개**의 유효한 상품 주소가 인식되었습니다.")
else:
    st.caption("⚠️ 인식된 유효 URL이 없습니다.")

col_a, col_b = st.columns(2)
with col_a:
    target_price = st.number_input("목표 가격 (원)", value=3200, step=100)
with col_b:
    ntfy_topic = st.text_input("ntfy 알림 채널명", value="my_milk_alert_777")

# 차단 우회용 PC 웹 브라우저 헤더 세팅
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://search.shopping.naver.com/"
}

def get_naver_product_info(url):
    """다양한 네이버 쇼핑/스마트스토어 HTML 구조에서 가격을 다각도로 파싱하는 함수"""
    try:
        session = requests.Session()
        res = session.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        res.raise_for_status()
        html = res.text
        soup = BeautifulSoup(html, "html.parser")

        # 1. 상품 제목 파싱
        title = "네이버 쇼핑 상품"
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = og_title["content"].replace(" : 네이버 쇼핑", "").replace(" : 네이버 스마트스토어", "").strip()

        price = None

        # 2. OpenGraph 메타 태그 1차 수집
        for prop in ["og:price:amount", "product:price:amount", "product:sale_price:amount"]:
            meta = soup.find("meta", property=prop)
            if meta and meta.get("content"):
                digits = re.sub(r"[^\d]", "", meta["content"])
                if digits:
                    price = int(digits)
                    break

        # 3. JSON 구조 내부 키워드 2차 수집
        if price is None:
            matches = re.findall(r'"(?:discountedPrice|salePrice|discountPrice|rawPrice|benefitsViewPrice|mobileDiscountedPrice)":\s*(\d+)', html)
            if matches:
                valid_prices = [int(p) for p in matches if 100 <= int(p) <= 10000000]
                if valid_prices:
                    price = min(valid_prices)

        # 4. HTML 클래스 직접 3차 수집
        if price is None:
            price_tags = soup.select("._1LY7DqebLu, ._228w0AZ_e3, ._2HP-hn-bWZ, .total_price, .price, .discount_price")
            for tag in price_tags:
                digits = re.sub(r"[^\d]", "", tag.get_text())
                if digits and int(digits) >= 100:
                    price = int(digits)
                    break

        return {"title": title, "price": price, "url": url}
    except Exception:
        return {"title": "수집 불가 (접속 차단 또는 URL 오류)", "price": None, "url": url}

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
        st.warning("분석할 네이버 쇼핑 URL을 입력해 주세요.")
    else:
        with st.spinner(f"{len(extracted_urls)}개 상품 실시간 데이터 수집 중..."):
            results = [get_naver_product_info(u) for u in extracted_urls]
            valid_items = [r for r in results if r["price"] is not None]

            if valid_items:
                min_item = min(valid_items, key=lambda x: x["price"])
                st.subheader("👑 최저가 상품")
                st.success(f"**[{min_item['title']}]**\n\n💰 최저가: **{min_item['price']:,}원** (목표가: {target_price:,}원)")

                if min_item["price"] <= target_price:
                    st.balloons()
                    msg = f"🏆 최저가 달성!\n{min_item['title']}\n가격: {min_item['price']:,}원"
                    send_push(ntfy_topic, "🎉 최저가 달성!", msg)
                    st.info("📲 ntfy 스마트폰 푸시 알림을 전송했습니다.")

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
                st.error("입력한 URL에서 가격 정보를 읽어오지 못했습니다. 올바른 정식 상품 페이지 주소인지 확인해 주세요.")
