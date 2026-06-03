import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import time
import requests
import os
from datetime import datetime, timedelta

# 1. 초기 설정 (버전 7.6 업데이트: 비중 컬럼 테이블 노출 및 정렬 최적화)
st.set_page_config(page_title="Taeho's Investment OS v7.6", layout="wide")
st.title("🌎 태호님의 글로벌 투자 OS v7.6")

if st.sidebar.button("🔄 데이터 강제 새로고침"):
    st.cache_data.clear()
    st.rerun()

log_area = st.sidebar.empty()
def log(msg): log_area.info(f"🛰️ {msg}")

KR_ID = "1tBxMnO3g8JpWA0zV2tIO96veEP2KeR6kfd9H1OnPXK4"
US_ID = "1OfV4YUnc-gvQJ5ZdEZ6HU3ezK6lUp6WcHFcll-83Ibw"
HISTORY_FILE = "assets_history.csv"
WEBAPP_URL = "https://script.google.com/macros/s/AKfycbyHQYiSH9YqO-NcMvRXkDZPP-qteVXAQwxIucaPuTa3BIuh96eySVtbzWIPman10N1fWg/exec" 

def clean_numeric(val):
    if pd.isna(val): return 0
    clean_str = str(val).replace(',', '').replace('$', '').replace('₩', '').replace('원', '').strip()
    try: return float(clean_str)
    except: return 0

@st.cache_data(ttl=60)
def load_raw_sheet(sid):
    try:
        url = f"https://docs.google.com/spreadsheets/d/{sid}/export?format=csv"
        df = pd.read_csv(url)
        df.columns = [str(c).strip() for c in df.columns]
        return df.dropna(subset=[df.columns[0]]).reset_index(drop=True)
    except Exception as e:
        st.error(f"시트 로딩 실패: {e}")
        return pd.DataFrame()

def get_kr_ticker_code(name):
    m = {"삼성전자": "005930", "SK하이닉스": "000660", "LS": "006260", "LSELECTRIC": "010120", "HD현대일렉트릭": "267260", "한국전력": "015760", "리노공업": "058470", "두산에너빌리티": "034020", "DL이앤씨": "375500", "LG전자": "066570", "현대차2우B": "005387", "TIGER반도체TOP10": "396500", "HANAROFNK반도체": "395270", "클래시스": "214150", "이루다": "164060"}
    clean_name = str(name).replace(" ", "").replace("-", "").upper()
    if clean_name in m: return m[clean_name]
    return None

def get_live_prices(ticker_list, is_us=False):
    results = {}
    for t in ticker_list:
        symbol = str(t).strip()
        if symbol.upper() in ['CASH', 'NAN', ''] : continue
        if is_us:
            try:
                hist = yf.Ticker(symbol).history(period="5d")
                if not hist.empty:
                    cur_p = hist['Close'].iloc[-1]
                    prev_p = hist['Close'].iloc[-2]
                    results[symbol] = {"cur": cur_p, "prev": prev_p, "chg": cur_p - prev_p, "pct": ((cur_p - prev_p) / prev_p * 100)}
            except: continue
        else:
            code = get_kr_ticker_code(symbol)
            if code:
                try:
                    res = requests.get(f"https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{code}", timeout=3).json()
                    item = res['result']['areas'][0]['datas'][0]
                    results[symbol] = {"cur": item['nv'], "prev": item['pcv'], "chg": item['nv'] - item['pcv'], "pct": ((item['nv'] - item['pcv']) / item['pcv'] * 100)}
                except: pass
    return results

def build_portfolio(df, prices, account_filter=None, is_us=False):
    if df.empty: return pd.DataFrame()
    temp = df.copy()
    if account_filter: temp = temp[temp['계좌명'].astype(str).str.contains(account_filter, na=False)]
    
    rows = []
    cash_eval = 0
    id_col = 'Symbol' if is_us else '종목명'
    qty_col = 'Qty' if 'Qty' in temp.columns else ('보유수량' if '보유수량' in temp.columns else temp.columns[2])
    avg_col = 'Price Paid' if 'Price Paid' in temp.columns else ('평균단가' if '평균단가' in temp.columns else temp.columns[3])
    
    for _, row in temp.iterrows():
        id_val = str(row.get(id_col, "")).strip()
        name_val = str(row.get('종목명', id_val))
        qty = clean_numeric(row.get(qty_col, 0))
        avg_p = clean_numeric(row.get(avg_col, 0))
        
        if id_val.upper() in ['CASH', '예수금'] or '예수금' in name_val:
            cash_eval += (qty * avg_p)
        else:
            p_info = prices.get(id_val, {"cur": avg_p, "chg": 0, "pct": 0})
            cur_p = p_info['cur']
            rows.append({
                "섹터": row.get('섹터', '미분류'), "종목": name_val, "보유수량": qty, "평균단가": avg_p, 
                "매수금액": qty * avg_p, "현재가": cur_p, "평가금액": qty * cur_p, 
                "평가손익": (qty * cur_p) - (qty * avg_p), "당일손익": p_info.get('chg', 0) * qty, 
                "당일변화(%)": p_info.get('pct', 0), "수익률(%)": (((cur_p / avg_p) - 1) * 100) if avg_p != 0 else 0
            })
    
    res = pd.DataFrame(rows)
    if not res.empty:
        res = res.groupby(["종목", "섹터"]).agg({
            "보유수량": "sum", "매수금액": "sum", "평가금액": "sum", 
            "평가손익": "sum", "당일손익": "sum", "당일변화(%)": "mean", "수익률(%)": "mean"
        }).reset_index()
        res["평균단가"] = res["매수금액"] / res["보유수량"]
        res["현재가"] = res["평가금액"] / res["보유수량"]
    
    cash_df = pd.DataFrame([{"섹터": "Cash", "종목": "통합 예수금", "보유수량": 0, "평균단가": 0, "매수금액": 0, "현재가": 0, "평가금액": cash_eval, "평가손익": 0, "당일손익": 0, "당일변화(%)": 0, "수익률(%)": 0}])
    res = pd.concat([res, cash_df], ignore_index=True)
    
    total_eval = res["평가금액"].sum()
    res["비중(%)"] = (res["평가금액"] / total_eval * 100)
    res = res.sort_values(by="평가금액", ascending=False)
    
    total = pd.DataFrame([{
        "섹터": "Total", "종목": "TOTAL", "매수금액": res["매수금액"].sum(), "평가금액": total_eval, 
        "평가손익": res["평가손익"].sum(), "당일손익": res["당일손익"].sum(), 
        "수익률(%)": (res["평가손익"].sum() / res["매수금액"].sum() * 100) if res["매수금액"].sum() != 0 else 0,
        "비중(%)": 100.0
    }])
    return pd.concat([res, total], ignore_index=True)

def track_asset_history_hybrid(total_value):
    today = (datetime.utcnow() + timedelta(hours=9)).strftime("%Y-%m-%d")
    if WEBAPP_URL:
        try: requests.post(WEBAPP_URL, json={"date": today, "total_value": total_value}, timeout=5)
        except: pass
    try:
        read_url = f"https://docs.google.com/spreadsheets/d/{KR_ID}/gviz/tq?tqx=out:csv&sheet=AssetHistory"
        df_h = pd.read_csv(read_url, parse_dates=['date'])
        df_h.to_csv(HISTORY_FILE, index=False)
    except:
        df_h = pd.read_csv(HISTORY_FILE, parse_dates=['date']) if os.path.exists(HISTORY_FILE) else pd.DataFrame(columns=["date", "total_value"])
    return df_h

def display_view(df, title=None, unit="KRW"):
    if df.empty: return
    if title: st.subheader(f"📍 {title}")
    t_data = df[df["종목"] == "TOTAL"].iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    sym = "원" if unit == "KRW" else "$"
    
    if unit == "KRW":
        c1.metric("총 평가금액", f"{t_data['평가금액']:,.0f} {sym}", delta=f"{t_data['당일손익']:,.0f}")
        c2.metric("총 매수금액", f"{t_data['매수금액']:,.0f} {sym}")
        c3.metric("총 평가손익", f"{t_data['평가손익']:,.0f} {sym}")
    else:
        c1.metric("총 평가금액", f"${t_data['평가금액']:,.2f}", delta=f"${t_data['당일손익']:,.2f}")
        c2.metric("총 매수금액", f"${t_data['매수금액']:,.2f}")
        c3.metric("총 평가손익", f"${t_data['평가손익']:,.2f}")
    c4.metric("수익률", f"{t_data['수익률(%)']:.1f}%")

    # 테이블에 비중(%) 포함 및 포맷팅
    fmt = {'보유수량': '{:,.0f}', '비중(%)': '{:.1f}%', '평균단가': '{:,.0f}' if unit == "KRW" else '{:,.2f}', 
           '매수금액': '{:,.0f}' if unit == "KRW" else '{:,.2f}', 
           '현재가': '{:,.0f}' if unit == "KRW" else '{:,.2f}', 
           '평가금액': '{:,.0f}' if unit == "KRW" else '{:,.2f}', 
           '평가손익': '{:,.0f}' if unit == "KRW" else '{:,.2f}', 
           '수익률(%)': '{:.1f}%', '당일변화(%)': '{:.1f}%', '당일손익': '{:,.0f}' if unit == "KRW" else '{:,.2f}'}

    styled_df = df.style.format(fmt, na_rep="-").map(
        lambda v: f'color: {"#00FF00" if v > 0 else "#FF0000"}' if isinstance(v, (int, float)) and v != 0 else "", 
        subset=['평가손익', '당일손익', '당일변화(%)', '수익률(%)']
    ).apply(lambda x: ['background-color: #222222; font-weight: bold' if x.name == df.index[-1] else '' for _ in x], axis=1)

    st.dataframe(styled_df, use_container_width=True)
    pie_data = df[~df["종목"].isin(["TOTAL", "통합 예수금"])].copy()
    if not pie_data.empty:
        st.plotly_chart(px.pie(pie_data, values='평가금액', names='섹터', hole=0.4, title=f"📊 {title} 섹터 비중"), use_container_width=True)

# 메인 실행
df_kr_raw, df_us_raw = load_raw_sheet(KR_ID), load_raw_sheet(US_ID)
prices_kr = get_live_prices(df_kr_raw['종목명'].unique().tolist())
prices_us = get_live_prices(df_us_raw['Symbol'].unique().tolist(), is_us=True)
rate = 1385.0 

df_kr_total = build_portfolio(df_kr_raw, prices_kr)
df_us_total = build_portfolio(df_us_raw, prices_us, is_us=True)

total_val = df_kr_total[df_kr_total["종목"]=="TOTAL"]["평가금액"].iloc[0] + (df_us_total[df_us_total["종목"]=="TOTAL"]["평가금액"].iloc[0] * rate)
history_df = track_asset_history_hybrid(total_val) 

st.markdown(f"### 🏦 통합 자산 현황: **{total_val:,.0f} 원**")
main_tabs = st.tabs(["🇰🇷 한국 주식", "🇺🇸 미국 주식", "📈 총 자산 추이"])

with main_tabs[0]:
    sub = st.tabs(["종목별 통합", "하나(전략)", "하나(일반)", "키움"])
    with sub[0]: display_view(df_kr_total, "한국 주식 통합")
    with sub[1]: display_view(build_portfolio(df_kr_raw, prices_kr, "38011760"), "하나(전략)")
    with sub[2]: display_view(build_portfolio(df_kr_raw, prices_kr, "38083150"), "하나(일반)")
    with sub[3]: display_view(build_portfolio(df_kr_raw, prices_kr, "5851"), "키움")

with main_tabs[1]: display_view(df_us_total, "미국 주식 통합", unit="USD")
with main_tabs[2]:
    st.subheader("📊 총 자산 역사적 추이 (AssetHistory 탭)")
    fig = px.line(history_df, x="date", y="total_value", markers=True)
    st.plotly_chart(fig, use_container_width=True)