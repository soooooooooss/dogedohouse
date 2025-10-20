import streamlit as st
import json, gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime

# --- 既存のコード（Google Sheets認証など） ---
# Google Sheets認証設定
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# st.secretsに対応
try:
    credentials_dict = st.secrets["gcp_service_account"]
    credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
except:
    credentials = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)

client = gspread.authorize(credentials)

# スプレッドシートを開く
SHEET_NAME = "dogedohouse_data"
sheet = client.open(SHEET_NAME).sheet1

# --- データの読み込みと前処理 ---
data = sheet.get_all_records()
# データがない場合は空のDataFrameを作成
if not data:
    df = pd.DataFrame(columns=["借りた人", "貸した人", "金額（円）", "日時", "状態"])
else:
    df = pd.DataFrame(data)

# 金額を数値に変換（エラーは無視してNaNにする）
df["金額（円）"] = pd.to_numeric(df["金額（円）"], errors='coerce')
# "未返済"のデータのみを対象にする
df_unpaid = df[df["状態"] == "未返済"].copy()


# --- Streamlit アプリのUI部分 ---
st.title("🐶 dogedohouse")
st.write("4人のお金の貸し借りをリアルタイムで管理！")

st.subheader("📝 貸し借り一覧")
# 返済済みのものも含めて全データを表示
st.dataframe(df)


# --- ▼▼▼ ここから集計機能を追加 ▼▼▼ ---

st.subheader("📊 集計結果")

# メンバーリスト
members = ["よしい", "しゅんき", "のがみ", "そう"]
balances = {member: 0 for member in members}

if not df_unpaid.empty:
    # 各メンバーの収支を計算
    for index, row in df_unpaid.iterrows():
        lender = row["貸した人"]
        borrower = row["借りた人"]
        amount = row["金額（円）"]

        if lender in balances:
            balances[lender] += amount
        if borrower in balances:
            balances[borrower] -= amount

    # 収支を2列で表示
    cols = st.columns(len(members))
    for i, (member, balance) in enumerate(balances.items()):
        with cols[i]:
            st.metric(label=member, value=f"{balance:,.0f} 円")

    st.markdown("---") # 区切り線

    # --- 精算処理 ---
    st.subheader("💸 精算タイム！")

    # 貸している人（プラス）と借りている人（マイナス）に分ける
    creditors = {name: balance for name, balance in balances.items() if balance > 0}
    debtors = {name: balance for name, balance in balances.items() if balance < 0}

    transactions = []
    
    # 精算アルゴリズム
    while creditors and debtors:
        # 貸している額が最も大きい人と、借りている額が最も大きい人を見つける
        creditor_name, creditor_amount = max(creditors.items(), key=lambda item: item[1])
        debtor_name, debtor_amount = min(debtors.items(), key=lambda item: item[1])

        # 送金額を決定（貸し額と借り額の小さい方）
        transfer_amount = min(creditor_amount, -debtor_amount)

        # 取引を記録
        transactions.append(f"**{debtor_name}** → **{creditor_name}** に **{transfer_amount:,.0f} 円** 支払う")

        # 残高を更新
        creditors[creditor_name] -= transfer_amount
        debtors[debtor_name] += transfer_amount

        # 残高が0になったらリストから削除
        if creditors[creditor_name] < 1: # 浮動小数点数の誤差を考慮
            del creditors[creditor_name]
        if debtors[debtor_name] > -1:
            del debtors[debtor_name]

    if transactions:
        for t in transactions:
            st.info(t)
    else:
        st.success("🎉 精算は完了しています！")

else:
    st.info("未返済のデータがありません。")

# --- ▲▲▲ ここまでが集計機能 ---


st.markdown("---") # 区切り線

# 新規登録フォーム
st.subheader("✍️ 新しい貸し借りを登録")
col1, col2, col3 = st.columns(3)
with col1:
    borrower = st.selectbox("借りた人", members)
with col2:
    lender = st.selectbox("貸した人", members)
with col3:
    amount = st.number_input("金額（円）", min_value=0, step=100)
    
if st.button("登録"):
    if borrower != lender and amount > 0:
        # 日時と状態をリストに追加
        new_row = [borrower, lender, int(amount), datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "未返済"]
        sheet.append_row(new_row, value_input_option='USER_ENTERED')
        st.success("登録しました！ ページを再読み込みすると反映されます。")
        st.balloons()
    elif borrower == lender:
        st.warning("😅 貸した人と借りた人は違う人を選んでください。")
    else:
        st.warning("💰 金額を入力してください。")