import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import time
import requests
import os
from datetime import datetime

# 1. 초기 설정 (버전 7.0 업데이트: 디스플레이 유지 원칙 적용)
st.set_page_config(page_title="Taeho's Investment OS v7.0", layout="wide")
st.title("🌎 태호님의 글로벌 투자 OS v7.0")

if st.sidebar.button("🔄 데이터 강제 새로고침"):
    st.cache_data.clear()
    st.rerun()

log_area = st.sidebar.empty()
def log(msg): log_area.info(f"🛰️ {msg}")

KR_ID = "1tBxMnO3g8JpWA0zV2tIO96veEP2KeR6kfd9H1OnPXK4"
US_ID = "1OfV4YUnc-gvQJ5ZdEZ6HU3ezK6lUp6WcHFcll-83Ibw"
HISTORY_FILE = "assets_history.csv"

def clean_numeric(val):
    if pd.isna(val): return 0
    clean_str = str(val).replace(',', '').replace('$', '').replace('₩', '').replace('원', '').strip()
    try:
        return float(clean_str)
    except:
        return 0

# 2. 데이터 시트 로드
@st.cache_data(ttl=30)
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
    m = {
        "삼성전자": "005930", "SK하이닉스": "000660", "LS": "006260", 
        "LSELECTRIC": "010120", "HD현대일렉트릭": "267260", "한국전력": "015760",
        "리노공업": "058470", "두산에너빌리티": "034020", "DL이앤씨": "375500",
        "LG전자": "066570", "현대차2우B": "005387", "TIGER반도체TOP10": "396500",
        "HANAROFNK반도체": "395270", "클래시스": "214150", "이루다": "164060"
    }
    clean_name = str(name).replace(" ", "").replace("-", "").upper()
    if clean_name in m: return m[clean_name]
    try:
        url = f"https://ac.finance.naver.com/ac?q={name}&q_enc=utf-8&st=111&frm=stock&r_format=json&r_enc=utf-8"
        res = requests.get(url, timeout=2).json()
        if res.get('items') and len(res['items'][0]) > 0:
            return res['items'][0][0][1][0]
    except: pass
    return None

# 3. 시세 엔진
def get_live_prices(ticker_list, is_us=False):
    if not ticker_list: return {}
    results = {}
    for t in ticker_list:
        symbol = str(t).strip()
        if symbol.upper() in ['CASH', 'NAN', ''] : continue
        if is_us:
            for attempt in range(3):
                try:
                    t_obj = yf.Ticker(symbol)
                    hist = t_obj.history(period="5d")
                    if not hist.empty:
                        prices = hist['Close'].dropna()
                        cur_p = prices.iloc[-1]
                        prev_p = prices.iloc[-2] if len(prices) > 1 else cur_p
                        results[symbol] = {"cur": cur_p, "prev": prev_p, "chg": cur_p - prev_p, "pct": ((cur_p - prev_p) / prev_p * 100) if prev_p != 0 else 0}
                        break
                except: time.sleep(0.5); continue
        else:
            code = get_kr_ticker_code(symbol)
            if code:
                try:
                    url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{code}"
                    res = requests.get(url, timeout=3).json()
                    item = res['result']['areas'][0]['datas'][0]
                    results[symbol] = {"cur": item['nv'], "prev": item['pcv'], "chg": item['cv'], "pct": item['cr']}
                except: pass
    return results

# 4. 연산 엔진 (칼럼 순서 영구 고정)
def build_portfolio(df, prices, account_filter=None, is_us=False):
    if df.empty: return pd.DataFrame()
    temp = df.copy()
    if account_filter:
        temp = temp[temp['계좌명'].astype(str).str.contains(account_filter, na=False)]
    
    cols = temp.columns.tolist()
    id_col = 'Symbol' if is_us else '종목명'
    qty_col = 'Qty' if 'Qty' in cols else ('보유수량' if '보유수량' in cols else cols[2])
    avg_col = 'Price Paid' if 'Price Paid' in cols else ('평균단가' if '평균단가' in cols else cols[3])
    
    rows = []
    for _, row in temp.iterrows():
        id_val = str(row.get(id_col, "")).strip()
        name_val = str(row.get('종목명', id_val)).strip()
        qty = clean_numeric(row.get(qty_col, 0))
        avg_p = clean_numeric(row.get(avg_col, 0))
        sector_val = str(row.get('섹터', row.get('Sector', '미분류'))).strip()
        
        if (id_val.upper() == 'CASH') or (sector_val.upper() == 'CASH') or ("예수금" in name_val):
            rows.append({"섹터": "Cash", "종목": "통합 예수금", "보유수량": 0, "평균단가": 0, "매수금액": 0, "현재가": qty * avg_p, "평가금액": qty * avg_p, "평가손익": 0, "당일손익": 0, "당일변화(%)": 0, "id": "CASH"})
        else:
            p_info = prices.get(id_val, {"cur": avg_p, "prev": avg_p, "chg": 0, "pct": 0})
            cur_p = p_info['cur']
            rows.append({"섹터": sector_val, "종목": name_val, "보유수량": qty, "평균단가": avg_p, "매수금액": qty * avg_p, "현재가": cur_p, "평가금액": qty * cur_p, "평가손익": (qty * cur_p) - (qty * avg_p), "당일손익": p_info['chg'] * qty, "당일변화(%)": p_info['pct'], "id": id_val})
    
    res = pd.DataFrame(rows)
    if res.empty: return pd.DataFrame()
    res = res.groupby(["id", "섹터"]).agg({"종목": "first", "보유수량": "sum", "매수금액": "sum", "현재가": "last", "평가금액": "sum", "당일손익": "sum", "평가손익": "sum", "당일변화(%)": "mean"}).reset_index()
    res["평균단가"] = (res["매수금액"] / res["보유수량"]).fillna(0)
    res.loc[res['id'] == 'CASH', ['현재가', '보유수량', '평균단가', '당일변화(%)']] = None
    res['priority'] = res['id'].apply(lambda x: 1 if x == "CASH" else 0)
    res = res.sort_values(by=['priority', '평가금액'], ascending=[True, False]).drop(columns=['priority', 'id'])
    total_eval = res["평가금액"].sum()
    res["비중(%)"] = (res["평가금액"] / total_eval * 100).fillna(0)
    res['수익률(%)'] = (res['평가손익'] / res['매수금액'] * 100).fillna(0)
    
    total = pd.DataFrame([{"섹터": "Total", "종목": "TOTAL", "매수금액": res["매수금액"].sum(), "평가금액": total_eval, "평가손익": res["평가손익"].sum(), "당일손익": res["당일손익"].sum(), "비중(%)": 100.0, "수익률(%)": (res["평가손익"].sum() / res["매수금액"].sum() * 100) if res["매수금액"].sum() != 0 else 0, "당일변화(%)": (res["당일손익"].sum() / (total_eval - res["당일손익"].sum()) * 100) if (total_eval - res["당일손익"].sum()) != 0 else 0}])
    
    final_df = pd.concat([res, total], ignore_index=True)
    ordered_cols = ['섹터', '종목', '보유수량', '평균단가', '매수금액', '현재가', '평가금액', '평가손익', '수익률(%)', '당일변화(%)', '당일손익', '비중(%)']
    for col in ordered_cols:
        if col not in final_df.columns: final_df[col] = 0
    return final_df[ordered_cols]

# 5. 기록 엔진
def track_asset_history(total_value):
    today = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(HISTORY_FILE):
        df_h = pd.read_csv(HISTORY_FILE)
    else:
        df_h = pd.DataFrame(columns=["date", "total_value"])
    if today in df_h['date'].values:
        df_h.loc[df_h['date'] == today, 'total_value'] = total_value
    else:
        df_h = pd.concat([df_h, pd.DataFrame([{"date": today, "total_value": total_value}])], ignore_index=True)
    df_h.to_csv(HISTORY_FILE, index=False)
    return df_h

# 6. UI 및 차트 엔진 (파이 차트 복구 완료)
def display_view(df, title=None, unit="KRW"):
    if df.empty: return
    if title: st.subheader(f"📍 {title}")
    
    # 상단 요약 지표
    t_data = df[df["종목"].str.upper() == "TOTAL"].iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    sym = "원" if unit == "KRW" else "$"
    c1.metric("총 평가금액", f"{t_data['평가금액']:,.0f} {sym}" if unit=="KRW" else f"${t_data['평가금액']:,.2f}", delta=f"{t_data['당일손익']:,.0f}" if unit=="KRW" else f"${t_data['당일손익']:,.2f}")
    c2.metric("총 매수금액", f"{t_data['매수금액']:,.0f} {sym}" if unit=="KRW" else f"${t_data['매수금액']:,.2f}")
    c3.metric("총 평가손익", f"{t_data['평가손익']:,.0f} {sym}" if unit=="KRW" else f"${t_data['평가손익']:,.2f}")
    c4.metric("수익률", f"{t_data['수익률(%)']:.1f}%")
    
    # 데이터 테이블
    fmt = {'보유수량':'{:,.0f}', '평균단가':'{:,.2f}', '매수금액':'{:,.2f}', '현재가':'{:,.2f}', '평가금액':'{:,.2f}', '평가손익':'{:,.2f}', '수익률(%)':'{:.1f}%', '당일변화(%)':'{:.1f}%', '당일손익':'{:,.2f}', '비중(%)':'{:.1f}%'}
    if unit == "KRW":
        for k in ['평균단가', '매수금액', '현재가', '평가금액', '평가손익', '당일손익']: fmt[k] = '{:,.0f}'
    
    st.dataframe(df.style.format(fmt, na_rep="-").map(
        lambda v: f'color: {"#00FF00" if v > 0 else "#FF0000"}' if isinstance(v, (int, float)) and v != 0 else "", 
        subset=['평가손익', '수익률(%)', '당일손익', '당일변화(%)']
    ).apply(lambda x: ['background-color: #222222; font-weight: bold' if x.name == df.index[-1] else '' for i in x], axis=1), use_container_width=True)
    
    # [복구] 섹터별 파이 차트
    pie_data = df[~df["종목"].str.upper().isin(["TOTAL", "통합 예수금", "통합예수금"])].copy()
    if not pie_data.empty:
        fig = px.pie(pie_data, values='평가금액', names='섹터', hole=0.4, title=f"📊 {title} 섹터 비중")
        st.plotly_chart(fig, use_container_width=True)

# 7. 메인 실행 로직
df_kr_raw, df_us_raw = load_raw_sheet(KR_ID), load_raw_sheet(US_ID)
prices_kr = get_live_prices(df_kr_raw['종목명'].unique().tolist())
prices_us = get_live_prices(df_us_raw['Symbol'].unique().tolist(), is_us=True)

try: rate = yf.Ticker("USDKRW=X").history(period="1d")['Close'].iloc[-1]
except: rate = 1385.0

df_kr_total = build_portfolio(df_kr_raw, prices_kr)
df_us_total = build_portfolio(df_us_raw, prices_us, is_us=True)

total_krw_val = df_kr_total[df_kr_total["종목"].str.upper() == "TOTAL"]["평가금액"].sum() + (df_us_total[df_us_total["종목"].str.upper() == "TOTAL"]["평가금액"].sum() * rate)
history_df = track_asset_history(total_krw_val)

st.markdown(f"### 🏦 통합 자산 현황: **{total_krw_val:,.0f} 원**")
st.divider()

main_tabs = st.tabs(["🇰🇷 한국 주식", "🇺🇸 미국 주식", "📈 총 자산 추이"])

with main_tabs[0]:
    sub = st.tabs(["종목별 통합", "하나(전략)", "하나(일반)", "키움"])
    with sub[0]: display_view(df_kr_total, title="한국 주식 통합")
    with sub[1]: display_view(build_portfolio(df_kr_raw, prices_kr, "38011760"), title="하나(전략)")
    with sub[2]: display_view(build_portfolio(df_kr_raw, prices_kr, "38083150"), title="하나(일반)")
    with sub[3]: display_view(build_portfolio(df_kr_raw, prices_kr, "5851"), title="키움")

with main_tabs[1]:
    display_view(df_us_total, title="미국 주식 통합", unit="USD")

with main_tabs[2]:
    st.subheader("📊 총 자산 역사적 추이 (KRW 합산)")
    if not history_df.empty:
        plot_df = history_df.copy()
        plot_df['total_m'] = plot_df['total_value'] / 1_000_000
        fig = px.line(plot_df, x="date", y="total_m", markers=True, 
                      title="일일 자산 총액 변화 (단위: 백만원)",
                      labels={"total_m": "자산 총액 (M)", "date": "날짜"},
                      text="total_m")
        fig.update_traces(texttemplate='%{text:.2f}M', textposition='top center')
        fig.update_layout(yaxis_tickformat='.2f', hovermode="x unified")
        st.plotly_chart(fig, use_container_width=True)
        with st.expander("📝 과거 기록 데이터 확인"):
            st.table(history_df.sort_values(by="date", ascending=False))
    else:
        st.info("기록된 자산 추이 데이터가 아직 없습니다.")

log("v7.0 업데이트 완료: 섹터 파이 차트 복구 및 디스플레이 유지 원칙 적용")