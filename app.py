import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px

# 1. 페이지 설정
st.set_page_config(page_title="태호님의 글로벌 투자 OS", layout="wide")

# 2. 구글 스프레드시트 ID
KR_SHEET_ID = "1tBxMnO3g8JpWA0zV2tIO96veEP2KeR6kfd9H1OnPXK4"
US_SHEET_ID = "1OfV4YUnc-gvQJ5ZdEZ6HU3ezK6lUp6WcHFcll-83Ibw"

@st.cache_data(ttl=60)
def load_data(sheet_id):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
    df = pd.read_csv(url)
    return df.dropna(subset=[df.columns[0]])

# 3. 실시간 가격 및 전일 종가 가져오기
def get_stock_data(tickers, is_us=False):
    ticker_map = {
        "삼성전자": "005930.KS", "LS": "006260.KS", "LS ELECTRIC": "010120.KS",
        "HD현대일렉트릭": "267260.KS", "SK하이닉스": "000660.KS", "DL이앤씨": "375500.KS",
        "롯데정밀화학": "004000.KS", "LG전자": "066570.KS", "NAVER": "035420.KS",
        "카카오": "035720.KS", "두산에너빌리티": "034020.KS", "현대차2우B": "005387.KS",
        "한국전력": "015760.KS", "TIGER반도체TOP10": "396500.KS"
    }
    data_dict = {}
    for t in tickers:
        if t in ['예수금', 'Cash', 'TOTAL', '합계']: continue
        try:
            symbol = t if is_us else ticker_map.get(t, f"{t}.KS")
            ticker_obj = yf.Ticker(symbol)
            hist = ticker_obj.history(period="2d")
            if len(hist) >= 2:
                data_dict[t] = {'current': hist['Close'].iloc[-1], 'prev_close': hist['Close'].iloc[-2]}
            elif len(hist) == 1:
                data_dict[t] = {'current': hist['Close'].iloc[-1], 'prev_close': hist['Close'].iloc[-1]}
        except: pass
    return data_dict

# 4. 포트폴리오 가공 엔진 (비중 칼럼 추가)
def process_portfolio(df, stock_data, is_us=False, aggregate_cash=False):
    temp = df.copy()
    if is_us:
        temp = temp.rename(columns={'Symbol': '티커', 'Remarks': '종목명', 'Qty': '보유수량', 'Price Paid': '평균단가', 'Last Price': '현재가'})
        id_col, cash_name = '티커', 'Cash'
    else:
        temp = temp.rename(columns={'현재가': '기존현재가'})
        id_col, cash_name = '종목명', '예수금'
    
    temp['보유수량'] = pd.to_numeric(temp['보유수량'], errors='coerce').fillna(0)
    temp['평균단가'] = pd.to_numeric(temp['평균단가'], errors='coerce').fillna(0)
    
    def get_val(row, target):
        name = row[id_col]
        if name == cash_name: return row['평균단가']
        fallback = row['현재가'] if is_us else row['기존현재가']
        return stock_data.get(name, {}).get(target, fallback)

    temp['실시간현재가'] = temp.apply(lambda x: get_val(x, 'current'), axis=1)
    temp['전일종가'] = temp.apply(lambda x: get_val(x, 'prev_close'), axis=1)
    
    temp['매수금액'] = temp['보유수량'] * temp['평균단가']
    temp['평가금액'] = temp['보유수량'] * temp['실시간현재가']
    
    # [통합 탭 전용] 예수금 합산 처리
    if aggregate_cash and not is_us:
        cash_mask = temp['종목명'] == '예수금'
        if cash_mask.any():
            stocks = temp[~cash_mask]
            cash_total = temp.loc[cash_mask, '매수금액'].sum()
            agg_cash = temp[cash_mask].iloc[0:1].copy()
            if '계좌명' in agg_cash.columns: agg_cash['계좌명'] = '통합'
            agg_cash['보유수량'], agg_cash['평균단가'], agg_cash['실시간현재가'] = 1, cash_total, cash_total
            agg_cash['매수금액'], agg_cash['평가금액'] = cash_total, cash_total
            temp = pd.concat([stocks, agg_cash], ignore_index=True)

    # 지표 계산
    total_eval_sum = temp['평가금액'].sum()
    temp['비중(%)'] = (temp['평가금액'] / total_eval_sum * 100) if total_eval_sum != 0 else 0
    temp['평가손익'] = temp['평가금액'] - temp['매수금액']
    temp['수익률(%)'] = (temp['평가손익'] / temp['매수금액'] * 100).fillna(0)
    temp['전일대비'] = (temp['실시간현재가'] - temp['전일종가']) * temp['보유수량']
    temp['전일변동(%)'] = ((temp['실시간현재가'] / temp['전일종가'] - 1) * 100).fillna(0)
    
    clean_df = temp.copy()
    
    # 합계 계산
    t_buy, t_eval = temp['매수금액'].sum(), temp['평가금액'].sum()
    t_day = temp['전일대비'].sum()
    t_profit = t_eval - t_buy
    t_ratio = (t_profit / t_buy * 100) if t_buy != 0 else 0
    t_day_ratio = (t_day / (t_eval - t_day) * 100) if (t_eval - t_day) != 0 else 0

    summary_data = {'종목명': 'TOTAL', '매수금액': t_buy, '평가금액': t_eval, '비중(%)': 100.0, '평가손익': t_profit, '수익률(%)': t_ratio, '전일대비': t_day, '전일변동(%)': t_day_ratio}
    summary_df = pd.DataFrame([summary_data])
    
    base_cols = ['종목명', '보유수량', '비중(%)', '평균단가', '매수금액', '실시간현재가', '평가금액', '평가손익', '수익률(%)', '전일대비', '전일변동(%)', '섹터']
    final_cols = (['티커'] + base_cols) if is_us else base_cols
    if '계좌명' in temp.columns: final_cols = ['계좌명'] + final_cols
    
    return pd.concat([temp, summary_df], ignore_index=True)[final_cols], clean_df

def color_profit(val):
    if isinstance(val, (int, float)):
        if val > 0: return 'color: #00FF00'
        if val < 0: return 'color: #FF0000'
    return ''

# UI 구성
st.title("🚀 태호님의 글로벌 투자 OS")
tab_kr, tab_us = st.tabs(["🇰🇷 한국 포트폴리오", "🇺🇸 미국 포트폴리오"])

common_format = {'보유수량':'{:,.0f}', '비중(%)':'{:.1f}%', '평균단가':'{:,.0f}', '매수금액':'{:,.0f}', '실시간현재가':'{:,.0f}', '평가금액':'{:,.0f}', '평가손익':'{:,.0f}', '수익률(%)':'{:.2f}%', '전일대비':'{:,.0f}', '전일변동(%)':'{:.2f}%'}
us_format = {**common_format, '보유수량':'{:,.2f}', '평균단가':'${:,.2f}', '매수금액':'${:,.2f}', '실시간현재가':'${:,.2f}', '평가금액':'${:,.2f}', '평가손익':'${:,.2f}'}

with tab_kr:
    df_kr_raw = load_data(KR_SHEET_ID)
    kr_data = get_stock_data(df_kr_raw['종목명'].unique())
    sub_total, sub1, sub2, sub3 = st.tabs(["통합", "하나(전략)", "하나(일반)", "키움"])
    
    def display_kr_tab(target_df, data, aggregate=False):
        col1, col2 = st.columns([3, 1])
        res, clean = process_portfolio(target_df, data, aggregate_cash=aggregate)
        with col1:
            st.dataframe(res.style.format(common_format).map(color_profit, subset=['평가손익', '수익률(%)', '전일대비', '전일변동(%)']), use_container_width=True)
        with col2:
            st.plotly_chart(px.pie(clean, values='평가금액', names='섹터', hole=0.4), use_container_width=True)

    with sub_total: display_kr_tab(df_kr_raw, kr_data, aggregate=True)
    with sub1: display_kr_tab(df_kr_raw[df_kr_raw['계좌명'].str.contains("38011760")], kr_data)
    with sub2: display_kr_tab(df_kr_raw[df_kr_raw['계좌명'].str.contains("38083150")], kr_data)
    with sub3: display_kr_tab(df_kr_raw[df_kr_raw['계좌명'].str.contains("5851")], kr_data)

with tab_us:
    df_us_raw = load_data(US_SHEET_ID)
    us_data = get_stock_data(df_us_raw['Symbol'].unique(), is_us=True)
    col1, col2 = st.columns([3, 1])
    res_us, clean_us = process_portfolio(df_us_raw, us_data, is_us=True)
    with col1:
        st.dataframe(res_us.style.format(us_format).map(color_profit, subset=['평가손익', '수익률(%)', '전일대비', '전일변동(%)']), use_container_width=True)
    with col2:
        st.plotly_chart(px.pie(clean_us, values='평가금액', names='섹터', hole=0.4), use_container_width=True)