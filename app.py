import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import os
from datetime import datetime

# 1. 초기 설정
st.set_page_config(page_title="Taeho's Investment OS v4.3", layout="wide")
st.title("🌎 태호님의 글로벌 투자 OS v4.3")

log_area = st.sidebar.empty()
def log(msg): log_area.info(f"🛰️ {msg}")

KR_ID = "1tBxMnO3g8JpWA0zV2tIO96veEP2KeR6kfd9H1OnPXK4"
US_ID = "1OfV4YUnc-gvQJ5ZdEZ6HU3ezK6lUp6WcHFcll-83Ibw"
HISTORY_FILE = "asset_history.csv"

# 2. 데이터 시트 로드
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

# 3. 시세 엔진 (전 종목 매핑 재확인 및 보강)
def get_live_prices(ticker_list, is_us=False):
    if not ticker_list: return {}
    
    # [핵심] 한국 종목 정밀 매핑 사전 (한국전력 및 ETF 포함)
    m = {
        # 대형주 및 관심종목
        "삼성전자": "005930.KS", "SK하이닉스": "000660.KS", "LS": "006260.KS", 
        "LS ELECTRIC": "010120.KS", "LSELECTRIC": "010120.KS", "HD현대일렉트릭": "267260.KS",
        "한국전력": "015760.KS", "KEPCO": "015760.KS", # 한국전력 추가
        "리노공업": "058470.KQ", "두산에너빌리티": "034020.KS", "DL이앤씨": "375500.KS",
        "LG전자": "066570.KS", "현대차2우B": "005387.KS",
        
        # 반도체 및 테마 ETF (공백/특수문자 대응)
        "TIGER반도체TOP10": "396500.KS", "TIGER반도체": "396500.KS",
        "HANAROFnK반도체": "395270.KS", "HANAROFnK-반도체": "395270.KS",
        "HANARO반도체": "395270.KS", "KODEX반도체": "091160.KS"
    }
    
    results = {}
    for t in ticker_list:
        symbol = str(t).strip()
        if symbol.upper() == 'CASH': continue
        
        # 이름 기반 매핑 시도 (공백/하이픈 제거 후 비교)
        clean_name = symbol.replace(" ", "").replace("-", "")
        target = symbol if is_us else m.get(clean_name, f"{symbol}.KS")
        
        try:
            ticker_obj = yf.Ticker(target)
            # 장 마감 후나 휴장일 데이터 누락 방지를 위해 5일치 조회
            hist = ticker_obj.history(period="5d")
            if not hist.empty:
                current_p = hist['Close'].dropna().iloc[-1]
                prev_p = hist['Close'].dropna().iloc[-2] if len(hist) > 1 else current_p
                results[symbol] = {"cur": current_p, "prev": prev_p}
        except:
            continue
    return results

# 4. 연산 엔진 (비중 및 CASH 로직 유지)
def build_portfolio(df, prices, account_filter=None, is_us=False):
    if df.empty: return pd.DataFrame()
    temp = df.copy()
    if account_filter:
        temp = temp[temp['계좌명'].astype(str).str.contains(account_filter, na=False)]
    
    ticker_col = 'Symbol' if is_us else '종목명'
    name_col = '종목명' if '종목명' in temp.columns else ticker_col
    qty_col = 'Qty' if 'Qty' in temp.columns else ('보유수량' if '보유수량' in temp.columns else temp.columns[2])
    price_cols = [c for c in temp.columns if 'Price' in c and 'Paid' in c]
    avg_col = price_cols[0] if is_us and price_cols else ('평균단가' if '평균단가' in temp.columns else temp.columns[3])
    
    rows = []
    for _, row in temp.iterrows():
        symbol_raw = str(row.get(ticker_col, "")).strip()
        name_raw = str(row.get(name_col, symbol_raw)).strip()
        qty = pd.to_numeric(row.get(qty_col, 0), errors='coerce') or 0
        avg_p = pd.to_numeric(row.get(avg_col, 0), errors='coerce') or 0
        sheet_now = pd.to_numeric(row.get('현재가', avg_p), errors='coerce') or avg_p
        
        is_cash = (symbol_raw.upper() == 'CASH') or (str(row.get('섹터', '')).upper() == 'CASH')
        
        if is_cash:
            rows.append({
                "종목": "통합 예수금", "보유수량": int(qty), "평균단가": avg_p, "매수금액": qty * avg_p,
                "현재가": avg_p, "평가금액": qty * avg_p, "평가손익": 0, "당일손익": 0, "섹터": "Cash"
            })
        else:
            # 실시간 시세 매칭, 실패 시 시트의 현재가(혹은 단가) 사용
            p_info = prices.get(symbol_raw if is_us else name_raw, {"cur": sheet_now, "prev": sheet_now})
            cur_p, prev_p = p_info['cur'], p_info['prev']
            rows.append({
                "종목": name_raw, "보유수량": int(qty), "평균단가": avg_p, "매수금액": qty * avg_p,
                "현재가": cur_p, "평가금액": qty * cur_p, 
                "평가손익": (qty * cur_p) - (qty * avg_p),
                "당일손익": (cur_p - prev_p) * qty, "섹터": str(row.get('섹터', '기타')).strip()
            })
    
    res = pd.DataFrame(rows)
    if not account_filter:
        res = res.groupby(["종목", "섹터"]).agg({"보유수량": "sum", "매수금액": "sum", "현재가": "max", "평가금액": "sum", "당일손익": "sum", "평가손익": "sum"}).reset_index()
        res["평균단가"] = (res["매수금액"] / res["보유수량"]).fillna(0)
    
    res['수익률(%)'] = (res['평가손익'] / res['매수금액'] * 100).fillna(0)
    res["당일변화(%)"] = (res["당일손익"] / (res["평가금액"] - res["당일손익"]) * 100).fillna(0)
    total_eval = res["평가금액"].sum()
    res["비중(%)"] = (res["평가금액"] / total_eval * 100).fillna(0)
    
    total = pd.DataFrame([{
        "종목": "TOTAL", "보유수량": None, "평균단가": None, "매수금액": res["매수금액"].sum(), "현재가": None, 
        "평가금액": total_eval, "평가손익": res["평가손익"].sum(),
        "수익률(%)": (res["평가손익"].sum() / res["매수금액"].sum() * 100) if res["매수금액"].sum() != 0 else 0,
        "당일변화(%)": (res["당일손익"].sum() / (res["평가금액"].sum() - res["당일손익"].sum()) * 100) if (res["평가금액"].sum() - res["당일손익"].sum()) != 0 else 0,
        "당일손익": res["당일손익"].sum(), "비중(%)": 100.0, "섹터": "Total"
    }])
    return pd.concat([res, total], ignore_index=True)[["종목", "보유수량", "평균단가", "매수금액", "현재가", "평가금액", "평가손익", "수익률(%)", "당일변화(%)", "당일손익", "비중(%)", "섹터"]]

# 5. UI 렌더링 (동일)
def display_view(df, title=None, unit="KRW"):
    if df.empty: return
    t_data = df[df["종목"] == "TOTAL"].iloc[0]
    if title:
        st.subheader(f"📍 {title}")
        c1, c2, c3, c4 = st.columns(4)
        sym = "원" if unit == "KRW" else "$"
        c1.metric("총 평가금액", f"{t_data['평가금액']:,.0f} {sym}" if unit=="KRW" else f"${t_data['평가금액']:,.2f}", delta=f"{t_data['당일손익']:,.0f}" if unit=="KRW" else f"${t_data['당일손익']:,.2f}")
        c2.metric("총 매수금액", f"{t_data['매수금액']:,.0f} {sym}" if unit=="KRW" else f"${t_data['매수금액']:,.2f}")
        c3.metric("총 평가손익", f"{t_data['평가손익']:,.0f} {sym}" if unit=="KRW" else f"${t_data['평가손익']:,.2f}")
        c4.metric("누적 수익률", f"{t_data['수익률(%)']:.1f}%")
    
    fmt = {'보유수량':'{:,.0f}', '평균단가':'{:,.1f}', '매수금액':'{:,.1f}', '현재가':'{:,.1f}', '평가금액':'{:,.1f}', '평가손익':'{:,.1f}', '수익률(%)':'{:.1f}%', '당일변화(%)':'{:.1f}%', '당일손익':'{:,.1f}', '비중(%)':'{:.1f}%'}
    if unit == "KRW":
        for k in ['평균단가', '매수금액', '현재가', '평가금액', '평가손익', '당일손익']: fmt[k] = '{:,.0f}'
    else:
        for k in ['평균단가', '매수금액', '현재가', '평가금액', '평가손익', '당일손익']: fmt[k] = '${:,.2f}'
    
    st.dataframe(df.style.format(fmt, na_rep="-").map(lambda v: f'color: {"#00FF00" if v > 0 else "#FF0000"}' if isinstance(v, (int, float)) and v != 0 else "", subset=['평가손익', '수익률(%)', '당일손익', '당일변화(%)']).apply(lambda x: ['background-color: #222222; font-weight: bold' if x.name == df.index[-1] else '' for i in x], axis=1), use_container_width=True)

# 6. 메인 실행
log("실시간 시세 연동 재점검 중...")
df_kr_raw, df_us_raw = load_raw_sheet(KR_ID), load_raw_sheet(US_ID)
prices_kr = get_live_prices(df_kr_raw['종목명'].unique().tolist())
prices_us = get_live_prices(df_us_raw['Symbol'].unique().tolist(), is_us=True)

try: rate = yf.Ticker("USDKRW=X").history(period="1d")['Close'].iloc[-1]
except: rate = 1385.0

df_kr_total = build_portfolio(df_kr_raw, prices_kr)
df_us_total = build_portfolio(df_us_raw, prices_us, is_us=True)

# 자산 현황 출력
total_krw = df_kr_total[df_kr_total["종목"]=="TOTAL"]["평가금액"].sum() + (df_us_total[df_us_total["종목"]=="TOTAL"]["평가금액"].sum() * rate)
st.markdown(f"### 🏦 통합 자산 현황: **{total_krw:,.0f} 원**")
st.divider()

t1, t2 = st.tabs(["🇰🇷 한국 주식", "🇺🇸 미국 주식"])
with t1: display_view(df_kr_total, title="한국 주식 통합")
with t2: display_view(df_us_total, title="미국 주식 통합", unit="USD")
log("시세 업데이트 완료")