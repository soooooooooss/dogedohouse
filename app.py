import streamlit as st
import json
from pathlib import Path

# ==============================
# dogedohouse - 4人用お金貸し借りアプリ
# ==============================

DATA_FILE = Path("data.json")
MEMBERS = ["よしい", "しゅんき", "のがみ", "そう"] 

# データ初期化
if not DATA_FILE.exists():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump([], f, ensure_ascii=False, indent=2)

def load_data():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

st.set_page_config(page_title="dogedohouse", page_icon="🐕‍🦺")
st.title("🐕‍🦺 dogedohouse - 4人用お金の貸し借りアプリ")

tab1, tab2 = st.tabs(["📥 貸し借りを追加", "📊 現在の状況"])

# ==============================
# 貸し借り登録タブ
# ==============================
with tab1:
    st.header("📥 新しい貸し借りを追加")
    lender = st.selectbox("貸した人", MEMBERS)
    borrower = st.selectbox("借りた人", [m for m in MEMBERS if m != lender])
    amount = st.number_input("金額（円）", min_value=100, step=100)
    note = st.text_input("メモ（任意）")

    if st.button("💾 登録する"):
        data = load_data()
        data.append({"貸した": lender, "借りた": borrower, "金額": amount, "メモ": note})
        save_data(data)
        st.success(f"{lender} → {borrower} に {amount} 円を登録しました！")

# ==============================
# 貸し借り一覧タブ
# ==============================
with tab2:
    st.header("📊 現在の貸し借り一覧")
    data = load_data()

    if not data:
        st.info("現在、貸し借りデータはありません。")
    else:
        st.table(data)
        idx_to_delete = st.number_input("返済済みの取引番号（行番号）", min_value=0, max_value=len(data)-1, step=1)
        if st.button("✅ 返済済みにする"):
            record = data[idx_to_delete]
            del data[idx_to_delete]
            save_data(data)
            st.success(f"{record['借りた']} が {record['貸した']} に返済しました！")

st.caption("© 2025 dogedohouse")
