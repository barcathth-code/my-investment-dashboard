import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px

# 1. 페이지 설정
st.set_page_config(page_title="태호님의 글로벌 투자 OS", layout="wide")

# 2. 구글 스프레드시트 ID
KR_SHEET_ID = "1tBxMnO3g8JpWA0zV2tIO96veEP2KeR6kfd9H1OnPXK4"
US_SHEET_ID = "1OfV4YUnc-gvQJ5ZdEZ6HU3ezK6lUp6WcHFcll-83Ibw"

@st.cache_data(ttl=600)
def load_data(sheet_id):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    df = pd.read_csv(url)
    return df.dropna(subset=[df.columns[0]])

# 3. 실시간 가격 가져오기
def get_live_prices(tickers, is_us=False):
    ticker_map = {
        "삼성전자": "005930.KS", "LS": "006260.KS", "LS ELECTRIC": "010120.KS",
        "HD현대일렉트릭": "267260.KS", "SK하이닉스": "000660.KS", "DL이앤씨": "375500.KS",
        "롯데정밀화학": "004000.KS", "LG전자": "066570.KS", "NAVER": "035420.KS",
        "카카오": "035720.KS", "두산에너빌리티": "034020.KS", "현대차2우B": "005387.KS",
        "한국전력": "015760.KS"
    }
    price_dict = {}
    for t in tickers:
        if t in ['예수금', 'Cash', 'TOTAL', '합계']: continue
        try:
            symbol = t if is_us else ticker_map.get(t, f"{t}.KS")
            data = yf.Ticker(symbol).history(period="1d")
            if not data.empty: price_dict[t] = data['Close'].iloc[-1]
        except: pass
    return price_dict

# 4. 포트폴리오 가공 엔진
def process_portfolio(df, prices, is_us=False):
    temp = df.copy()
    if is_us:
        temp = temp.rename(columns={'Symbol': '티커', 'Remarks': '종목명', 'Qty': '보유수량', 'Price Paid': '평균단가', 'Last Price': '현재가'})
        id_col, cash_name = '티커', 'Cash'
    else:
        temp = temp.rename(columns={'현재가': '기존현재가'})
        id_col, cash_name = '종목명', '예수금'
    
    temp['보유수량'] = pd.to_numeric(temp['보유수량'], errors='coerce').fillna(0)
    temp['평균단가'] = pd.to_numeric(temp['평균단가'], errors='coerce').fillna(0)
    
    # 실시간 시세 반영
    ref_col = '현재가' if is_us else '기존현재가'
    temp['현재가'] = temp.apply(lambda x: prices.get(x[id_col], x[ref_col]) if x[id_col] != cash_name else x['평균단가'], axis=1)
    
    temp['매수금액'] = temp['보유수량'] * temp['평균단가']
    temp['평가금액'] = temp['보유수량'] * temp['현재가']
    temp['평가손익'] = temp['평가금액'] - temp['매수금액']
    temp['수익률(%)'] = (temp['평가손익'] / temp['매수금액']).fillna(0) * 100
    
    # 합계 행 제외한 데이터 (차트용)
    clean_df = temp.copy()
    
    # 합계 행 추가
    total_buy, total_eval = temp['매수금액'].sum(), temp['평가금액'].sum()
    summary_data = {'종목명': 'TOTAL', '보유수량': 0, '평균단가': 0, '현재가': 0, '매수금액': total_buy, '평가금액': total_eval, '평가손익': total_eval - total_buy, '수익률(%)': (total_eval/total_buy - 1)*100 if total_buy != 0 else 0}
    
    final_cols = (['티커', '종목명'] if is_us else ['종목명']) + ['보유수량', '평균단가', '매수금액', '현재가', '평가금액', '평가손익', '수익률(%)', '섹터']
    if '계좌명' in temp.columns: final_cols = ['계좌명'] + final_cols
    
    return pd.concat([temp, pd.DataFrame([summary_data])], ignore_index=True)[final_cols], clean_df

# 5. 컬러링 함수
def color_profit(val):
    if isinstance(val, (int, float)):
        if val > 0: return 'color: #00FF00'
        if val < 0: return 'color: #FF0000'
    return ''

# ---------------------------------------------------------
# UI 구성
# ---------------------------------------------------------
st.title("🌎 태호님의 글로벌 투자 실시간 대시보드")

tab_kr, tab_us = st.tabs(["🇰🇷 한국 포트폴리오", "🇺🇸 미국 포트폴리오"])

# --- 한국 섹션 ---
with tab_kr:
    df_kr_raw = load_data(KR_SHEET_ID)
    kr_prices = get_live_prices(df_kr_raw['종목명'].unique())
    kr_format = {'보유수량':'{:,.0f}', '평균단가':'{:,.0f}', '매수금액':'{:,.0f}', '현재가':'{:,.0f}', '평가금액':'{:,.0f}', '평가손익':'{:,.0f}', '수익률(%)':'{:.2f}%'}

    # 한국 포트폴리오 내 서브 탭 복원
    sub_total, sub1, sub2, sub3 = st.tabs(["통합", "하나(전략)", "하나(일반)", "키움"])
    
    # 각 탭별 디스플레이 로직 (함수화하여 재사용)
    def display_kr_tab(target_df, prices):
        col1, col2 = st.columns([2, 1])
        res, clean = process_portfolio(target_df, prices)
        with col1:
            st.dataframe(res.style.format(kr_format).map(color_profit, subset=['평가손익', '수익률(%)']), use_container_width=True)
        with col2:
            fig = px.pie(clean, values='평가금액', names='섹터', hole=0.4)
            st.plotly_chart(fig, use_container_width=True)

    with sub_total:
        display_kr_tab(df_kr_raw, kr_prices)
    
    with sub1:
        display_kr_tab(df_kr_raw[df_kr_raw['계좌명'].str.contains("38011760")], kr_prices)
        
    with sub2:
        display_kr_tab(df_kr_raw[df_kr_raw['계좌명'].str.contains("38083150")], kr_prices)
        
    with sub3:
        display_kr_tab(df_kr_raw[df_kr_raw['계좌명'].str.contains("5851")], kr_prices)

# --- 미국 섹션 ---
with tab_us:
    df_us_raw = load_data(US_SHEET_ID)
    us_prices = get_live_prices(df_us_raw['Symbol'].unique(), is_us=True)
    us_format = {'Qty':'{:,.2f}','Price Paid':'${:,.2f}','매수금액':'${:,.2f}','현재가':'${:,.2f}','평가금액':'${:,.2f}','평가손익':'${:,.2f}','수익률(%)':'{:.2f}%'}
    
    col1, col2 = st.columns([2, 1])
    res_us, clean_us = process_portfolio(df_us_raw, us_prices, is_us=True)
    
    with col1:
        st.subheader("미국 주식 현황")
        st.dataframe(res_us.style.format(us_format).map(color_profit, subset=['평가손익', '수익률(%)']), use_container_width=True)
        
    with col2:
        st.subheader("섹터별 비중")
        fig_us = px.pie(clean_us, values='평가금액', names='섹터', hole=0.4)
        st.plotly_chart(fig_us, use_container_width=True)