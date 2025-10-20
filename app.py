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
st.title("ど外道の会")
st.write("💰金返せ")

st.subheader("📝 貸し借り履歴")
st.dataframe(df, hide_index=True)

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
    st.subheader("💸 精算")
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
        st.success("🎉 精算完了！")
else:
    st.info("未返済のデータがありません。")

st.markdown("---")

# --- ▼▼▼【新機能】返済管理セクション ▼▼▼ ---
st.subheader("✅ 返済管理")

df_unpaid_management = df[df["状態"] == "未返済"].copy()

if df_unpaid_management.empty:
    st.success("未返済の項目はありません。")
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
col_header_details, col_header_action = st.columns([4, 1.5]) # カラムを2つに変更
col_header_details.write("**詳細**")
col_header_action.write("**アクション**")

# 未返済の項目を一行ずつ表示
for index, row in df_unpaid_management.iterrows():
    # 各データは裏側で取得するだけ
    borrower = row['借りた人']
    lender = row['貸した人']
    amount = int(row['金額（円）'])
    memo = row.get('内容', '')

    # 表示する文章を作成
    display_text = f"{borrower}が{lender}に{amount:,}円払う"
    if memo:
        display_text += f" ({memo})"
    
    # UIのレイアウトを2つのカラムに変更
    col_details, col_action = st.columns([4, 1.5])
    
    with col_details:
        st.text(display_text) # 1つ目のカラムに生成した文章を配置
        
    with col_action:
        # 2つ目のカラムにボタンを配置
        if st.button("返済完了にする", key=f"repay_{index}"):
            sheet.update_cell(index + 2, status_col_index, "返済済み")
            st.toast(f"取引を「返済済み」に更新しました！")
            st.rerun()

st.markdown("---")


# --- ▼▼▼【機能修正】新規登録フォーム ▼▼▼ ---
st.subheader("✍️ 貸し借り登録")
with st.form("new_transaction_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
        borrower = st.selectbox("借りた人", members, key="borrower")
        lender = st.selectbox("貸した人", members, key="lender")
    with col2:
        amount = st.number_input("金額（円）", min_value=0, step=100)
        # 「内容」の入力欄を追加
        memo = st.text_input("内容 (任意)")

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