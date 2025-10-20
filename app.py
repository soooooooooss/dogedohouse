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
df["金額（円）"] = pd.to_numeric(df["金額（円）"], errors='coerce').fillna(0)


# --- Streamlit アプリのUI部分 ---
st.title("ど外道の会-ワリカ")
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
        lender = row["貸した人"]
        borrower = row["借りた人"]
        amount = row["金額（円）"]
        if lender in balances:
            balances[lender] += amount
        if borrower in balances:
            balances[borrower] -= amount
    
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
        
        # 未返済の項目を一行ずつ表示
        for index, row in df_unpaid_management.iterrows():
            # 各データは裏側で取得
            borrower = row['借りた人']
            lender = row['貸した人']
            amount = int(row['金額（円）'])
            memo = row.get('内容', '')

            # Markdownを使って色付きの表示テキストを生成
            borrower_colored = f"<span style='color: #F63366;'><b>{borrower}</b></span>" # 赤色
            lender_colored = f"<span style='color: #0068C9;'><b>{lender}</b></span>"   # 青色
            
            display_text_md = f"{borrower_colored} が {lender_colored} に **{amount:,}円** 払う"
            if memo:
                display_text_md += f" <span style='font-size: 0.9em; opacity: 0.7;'>({memo})</span>" # 内容は少し小さく表示

            # UIのレイアウトを2つのカラムに
            col_details, col_action = st.columns([4, 1.5])
            
            with col_details:
                # st.text() の代わりに st.markdown() を使用
                st.markdown(display_text_md, unsafe_allow_html=True)
                
            with col_action:
                # ボタンを配置
                if st.button("返済完了", key=f"repay_{index}"):
                    sheet.update_cell(index + 2, status_col_index, "返済済み")
                    st.toast(f"取引を「返済済み」に更新しました！")
                    st.rerun()

st.markdown("---")


# --- ▼▼▼【機能修正】新規登録フォーム（チェックボックス対応） ▼▼▼ ---
st.subheader("✍️ 貸し借り登録")
st.write("複数人が立て替えた場合や、割り勘の場合に使えます。")

# session_stateが初期化されていなければ初期化
if 'transactions_to_add' not in st.session_state:
    st.session_state.transactions_to_add = []

# --- 入力フォーム ---
# ▼▼▼【変更点】ラベルをst.markdownで色付け ▼▼▼
st.markdown("<span style='color: #0068C9;'>**支払った人**</span>", unsafe_allow_html=True)
lenders = st.multiselect(
    " ", # ラベルはmarkdownで表示するのでここは空にする
    members,
    key="lenders",
    label_visibility="collapsed" # デフォルトのラベルを非表示に
)

st.markdown("<span style='color: #F63366;'>**支払い対象者**</span>", unsafe_allow_html=True)
participants = st.multiselect(
    " ", # ラベルはmarkdownで表示するのでここは空にする
    members,
    key="participants",
    label_visibility="collapsed" # デフォルトのラベルを非表示に
)
# ▲▲▲【変更点】ここまで ▲▲▲

col1, col2 = st.columns(2)
with col1:
    total_amount = st.number_input("合計金額（円）", min_value=0, step=100)
with col2:
    memo = st.text_input("内容（任意）")

# --- 計算ボタン ---
if st.button("① 貸し借りを計算する"):
    # バリデーション
    if not lenders:
        st.warning("支払った人を1人以上選択してください。")
    elif not participants:
        st.warning("対象者を1人以上選択してください。")
    elif total_amount <= 0:
        st.warning("💰 金額を1円以上入力してください。")
    else:
        # --- 割り勘計算ロジック ---
        balances = {member: 0 for member in members}
        num_lenders = len(lenders)
        base_payment = total_amount // num_lenders
        remainder_payment = total_amount % num_lenders
        for i, lender in enumerate(lenders):
            payment = base_payment
            if i < remainder_payment:
                payment += 1
            balances[lender] += payment
        num_participants = len(participants)
        base_share = total_amount // num_participants
        remainder_share = total_amount % num_participants
        for i, participant in enumerate(participants):
            share = base_share
            if i < remainder_share:
                share += 1
            balances[participant] -= share
        creditors = {name: balance for name, balance in balances.items() if balance > 0}
        debtors = {name: balance for name, balance in balances.items() if balance < 0}
        
        calculated_rows = []
        while creditors and debtors:
            creditor_name, creditor_amount = max(creditors.items(), key=lambda item: item[1])
            debtor_name, debtor_amount = min(debtors.items(), key=lambda item: item[1])
            transfer_amount = min(creditor_amount, -debtor_amount)
            if transfer_amount >= 1:
                new_row = [
                    debtor_name, creditor_name, transfer_amount, memo,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "未返済"
                ]
                calculated_rows.append(new_row)
            creditors[creditor_name] -= transfer_amount
            debtors[debtor_name] += transfer_amount
            if creditors[creditor_name] < 1: del creditors[creditor_name]
            if debtors[debtor_name] > -1: del debtors[debtor_name]
        
        st.session_state.transactions_to_add = calculated_rows
        if not calculated_rows:
            st.info("貸し借りは発生しませんでした。")

# --- チェックボックスでの登録 ---
if st.session_state.transactions_to_add:
    st.markdown("---")
    st.write("登録したい項目にチェックを入れてください。")
    
    selected_transactions = []
    
    for i, transaction in enumerate(st.session_state.transactions_to_add):
        borrower, lender, amount, memo_text, _, _ = transaction
        
        label = f"{borrower} → {lender} に {amount:,}円"
        if memo_text:
            label += f" ({memo_text})"
        
        if st.checkbox(label, key=f"check_{i}", value=True):
             selected_transactions.append(transaction)

    if st.button("② チェックした項目を登録する"):
        if selected_transactions:
            sheet.append_rows(selected_transactions, value_input_option='USER_ENTERED')
            st.success(f"{len(selected_transactions)}件の貸し借りデータを登録しました！")
            st.balloons()
            st.session_state.transactions_to_add = []
            st.rerun()
        else:
            st.warning("登録する項目が選択されていません。")