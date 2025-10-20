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
try:
    sheet = client.open(SHEET_NAME).sheet1
except gspread.exceptions.SpreadsheetNotFound:
    st.error(f"エラー: スプレッドシート '{SHEET_NAME}' が見つかりません。")
    st.stop()


# --- データの読み込みと前処理 ---
data = sheet.get_all_records()
if not data:
    # ヘッダー列を定義
    columns = ["借りた人", "貸した人", "金額（円）", "内容", "日時", "状態"]
    df = pd.DataFrame(columns=columns)
else:
    df = pd.DataFrame(data)

# データがない場合や列が不足している場合に備える
required_cols = ["借りた人", "貸した人", "金額（円）", "状態"]
for col in required_cols:
    if col not in df.columns:
        st.error(f"エラー: スプレッドシートに必須の列 '{col}' がありません。")
        st.stop()

# 金額を数値に変換
df["金額（円）"] = pd.to_numeric(df["金額（円）"], errors='coerce')


# --- Streamlit アプリのUI部分 ---
st.title("🐶 dogedohouse")
st.write("4人のお金の貸し借りをリアルタイムで管理！")

st.subheader("📝 貸し借り全履歴")
st.dataframe(df)

# --- 集計結果（既存の機能）---
st.subheader("📊 集計結果")
df_unpaid = df[df["状態"] == "未返済"].copy()
members = ["よしい", "しゅんき", "のがみ", "そう"]
balances = {member: 0 for member in members}

if not df_unpaid.empty:
    for index, row in df_unpaid.iterrows():
        balances[row["貸した人"]] += row["金額（円）"]
        balances[row["借りた人"]] -= row["金額（円）"]
    
    cols = st.columns(len(members))
    for i, (member, balance) in enumerate(balances.items()):
        with cols[i]:
            st.metric(label=member, value=f"{balance:,.0f} 円")

    st.markdown("---")
    st.subheader("💸 精算タイム！")
    creditors = {name: balance for name, balance in balances.items() if balance > 0}
    debtors = {name: balance for name, balance in balances.items() if balance < 0}
    transactions = []
    while creditors and debtors:
        creditor_name, creditor_amount = max(creditors.items(), key=lambda item: item[1])
        debtor_name, debtor_amount = min(debtors.items(), key=lambda item: item[1])
        transfer_amount = min(creditor_amount, -debtor_amount)
        transactions.append(f"**{debtor_name}** → **{creditor_name}** に **{transfer_amount:,.0f} 円** 支払う")
        creditors[creditor_name] -= transfer_amount
        debtors[debtor_name] += transfer_amount
        if creditors[creditor_name] < 1: del creditors[creditor_name]
        if debtors[debtor_name] > -1: del debtors[debtor_name]

    if transactions:
        for t in transactions: st.info(t)
    else:
        st.success("🎉 精算は完了しています！")
else:
    st.info("未返済のデータがありません。")

st.markdown("---")

# --- ▼▼▼【新機能】返済管理セクション ▼▼▼ ---
st.subheader("✅ 返済管理")

df_unpaid_management = df[df["状態"] == "未返済"].copy()

if df_unpaid_management.empty:
    st.success("素晴らしい！未返済の項目はありません。")
else:
    try:
        header = sheet.row_values(1)
        status_col_index = header.index("状態") + 1
    except (ValueError, gspread.exceptions.APIError):
        st.error("スプレッドシートのヘッダーから「状態」列を見つけられませんでした。")
        status_col_index = None

    if status_col_index:
        st.write("↓のリストから完了した取引を「返済済み」に変更できます。")
        
        # リストのヘッダーを表示
        col1, col2, col3, col4, col5 = st.columns([1.5, 1.5, 1, 2.5, 1.5])
        col1.write("**借りた人**")
        col2.write("**貸した人**")
        col3.write("**金額**")
        col4.write("**内容**")
        col5.write("**アクション**")

        # 未返済の項目を一行ずつ表示
        for index, row in df_unpaid_management.iterrows():
            col1, col2, col3, col4, col5 = st.columns([1.5, 1.5, 1, 2.5, 1.5])
            col1.text(row['借りた人'])
            col2.text(row['貸した人'])
            col3.text(f"{row['金額（円）']:,}円")
            # 「内容」列がなくてもエラーにならないように .get() を使用
            col4.text(row.get('内容', 'ー')) 
            
            # 「返済完了」ボタン
            if col5.button("返済完了にする", key=f"repay_{index}"):
                # gspreadの行は1から始まる & ヘッダーがあるので+2する
                sheet.update_cell(index + 2, status_col_index, "返済済み")
                st.toast(f"取引を「返済済み」に更新しました！ページが再読み込みされます。")
                st.rerun() # ページを再読み込みして表示を更新

st.markdown("---")


# --- ▼▼▼【機能修正】新規登録フォーム ▼▼▼ ---
st.subheader("✍️ 新しい貸し借りを登録")
with st.form("new_transaction_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
        borrower = st.selectbox("借りた人", members, key="borrower")
        lender = st.selectbox("貸した人", members, key="lender")
    with col2:
        amount = st.number_input("金額（円）", min_value=0, step=100)
        # 「内容」の入力欄を追加
        memo = st.text_input("内容（例：ランチ代、交通費など）")

    submitted = st.form_submit_button("登録する")
    if submitted:
        if borrower != lender and amount > 0:
            # 登録データに「内容」を追加
            new_row = [borrower, lender, int(amount), memo, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "未返済"]
            sheet.append_row(new_row, value_input_option='USER_ENTERED')
            st.success("登録しました！")
            st.balloons()
        elif borrower == lender:
            st.warning("😅 貸した人と借りた人は違う人を選んでください。")
        else:
            st.warning("💰 金額を入力してください。")