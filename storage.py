import os
import streamlit as st
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_PATH = os.path.join(BASE_DIR, "users.json")
SESSIONS_PATH = os.path.join(BASE_DIR, "sessions.json")

FIRESTORE_COLLECTION = "essay_app_data"


def init_firestore():
    try:
        if not firebase_admin._apps:
            if "FIREBASE_KEY" not in st.secrets:
                return None, "Secretsに [FIREBASE_KEY] が見つかりません。TOMLの形式を確認してください。"

            cert_dict = dict(st.secrets["FIREBASE_KEY"])
            if "private_key" not in cert_dict:
                return None, "FIREBASE_KEY の中に private_key が見つかりません。"

            # JSONからTOMLへの変換時の改行文字を元に戻す
            if "\\n" in cert_dict["private_key"]:
                cert_dict["private_key"] = cert_dict["private_key"].replace("\\n", "\n")

            cred = credentials.Certificate(cert_dict)
            firebase_admin.initialize_app(cred)
        return firestore.client(), None
    except Exception as e:
        return None, f"Firestore初期化エラー: {e}"


db_client, db_error = init_firestore()


def load_json(path, default_val):
    if db_client is None:
        return default_val

    doc_name = os.path.basename(path).replace(".json", "")
    try:
        doc_ref = db_client.collection(FIRESTORE_COLLECTION).document(doc_name)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            return data.get("data", default_val)
        return default_val
    except Exception as e:
        st.error(f"🚨 **DB読み込みエラー ({doc_name})**: {e}")
        return default_val


def save_json(path, data):
    if db_client is None:
        st.session_state["_pending_storage_error"] = f"🚨 **DB保存エラー**: Firestoreが初期化されていません（{db_error}）"
        return

    doc_name = os.path.basename(path).replace(".json", "")
    try:
        doc_ref = db_client.collection(FIRESTORE_COLLECTION).document(doc_name)
        doc_ref.set({"data": data})
    except Exception as e:
        message = f"🚨 **DB保存エラー ({doc_name})**: {e}"
        # st.rerun()が直後に呼ばれる呼び出し元だとst.error()の表示が一瞬で消えてしまうため、
        # 次の再描画でも表示できるようセッションに保持しておく
        st.session_state["_pending_storage_error"] = message
        st.error(message)
