import re

import streamlit as st

import essay_ui
import session_store
from storage import USERS_PATH, db_error, load_json, save_json

st.set_page_config(
    page_title="小論文添削システム",
    page_icon="✍️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# マスターパスワード・教師パスワード・合言葉は、ソースコードに直接書かず
# Secretsで管理する
MASTER_PASSWORD = st.secrets.get("MASTER_PASSWORD", "")
ESSAY_TEACHER_PASSWORD = st.secrets.get("ESSAY_TEACHER_PASSWORD", "")
SECRET_WORD = st.secrets.get("SECRET_WORD", "")


def check_password_and_login():
    """3つの入り口（管理者・添削担当教師・生徒）を持つ認証機能"""
    users = load_json(USERS_PATH, {})

    # URLパラメータからの自動復元
    # （URLにはパスワードそのものではなく、session_storeが発行したランダムな
    #   不透明トークンだけが入る。トークン自体からパスワードは分からない）
    query_params = st.query_params
    if "token" in query_params and not st.session_state.get("logged_in"):
        resolved = session_store.resolve_session(query_params["token"])
        if resolved:
            sid, is_admin_session, is_teacher_session = resolved
            if is_admin_session and MASTER_PASSWORD:
                st.session_state["logged_in"] = True
                st.session_state["student_id"] = "admin"
                st.session_state["student_name"] = "管理者"
                st.session_state["is_admin"] = True
                st.session_state["is_teacher"] = False
            elif is_teacher_session and ESSAY_TEACHER_PASSWORD:
                st.session_state["logged_in"] = True
                st.session_state["student_id"] = "essay_teacher"
                st.session_state["student_name"] = "添削担当の先生"
                st.session_state["is_admin"] = False
                st.session_state["is_teacher"] = True
            elif not is_admin_session and not is_teacher_session and sid in users:
                st.session_state["logged_in"] = True
                st.session_state["student_id"] = sid
                st.session_state["student_name"] = users[sid]
                st.session_state["is_admin"] = False
                st.session_state["is_teacher"] = False

    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if not st.session_state["logged_in"]:
        st.title("✍️ 小論文添削システムへようこそ")

        tab1, tab2 = st.tabs(["🔒 ログイン", "✨ 新規会員登録（要合言葉）"])

        with tab1:
            st.markdown("### 登録済みのパスワードでログイン")
            login_pass = st.text_input("パスワード", type="password", key="login_pass")
            if st.button("ログイン", key="btn_login"):
                if MASTER_PASSWORD and login_pass == MASTER_PASSWORD:
                    st.session_state["logged_in"] = True
                    st.session_state["student_id"] = "admin"
                    st.session_state["student_name"] = "管理者"
                    st.session_state["is_admin"] = True
                    st.session_state["is_teacher"] = False
                    st.query_params.token = session_store.create_session("admin", is_admin=True)
                    st.rerun()
                elif ESSAY_TEACHER_PASSWORD and login_pass == ESSAY_TEACHER_PASSWORD:
                    st.session_state["logged_in"] = True
                    st.session_state["student_id"] = "essay_teacher"
                    st.session_state["student_name"] = "添削担当の先生"
                    st.session_state["is_admin"] = False
                    st.session_state["is_teacher"] = True
                    st.query_params.token = session_store.create_session("essay_teacher", is_teacher=True)
                    st.rerun()
                elif login_pass in users:
                    st.session_state["logged_in"] = True
                    st.session_state["student_id"] = login_pass
                    st.session_state["student_name"] = users[login_pass]
                    st.session_state["is_admin"] = False
                    st.session_state["is_teacher"] = False
                    st.query_params.token = session_store.create_session(login_pass)
                    st.rerun()
                else:
                    st.error("パスワードが違います。")

        with tab2:
            st.markdown("### 自分専用のアカウントを作ろう！")

            app_settings = load_json("app_settings.json", {"allow_registration": True})

            if not app_settings.get("allow_registration", True):
                st.warning("🙏 **現在、新規会員登録は締め切っています。**\n\n登録に関するお問い合わせは先生に直接ご連絡ください。")
            else:
                st.info("💡 先生から教わった「合言葉」が必要です。")
                new_name = st.text_input("あなたの名前（ニックネーム可）", key="reg_name")
                new_pass = st.text_input("好きなパスワード（6文字以上、英字と数字を必ず含めること）", type="password", key="reg_pass")
                secret_word = st.text_input("合言葉", type="password", key="reg_secret")

                if st.button("登録してはじめる", key="btn_register"):
                    if not new_name or not new_pass or not secret_word:
                        st.error("すべての項目を入力してください。")
                    elif secret_word != SECRET_WORD:
                        st.error("合言葉が間違っています。先生に確認してください。")
                    elif len(new_pass) < 6:
                        st.error("パスワードは6文字以上にしてください。")
                    elif not (re.search(r'[A-Za-z]', new_pass) and re.search(r'[0-9]', new_pass)):
                        st.error("パスワードには、アルファベット（英字）と数字を両方とも含めてください。")
                    elif new_pass in users or new_pass == MASTER_PASSWORD or (ESSAY_TEACHER_PASSWORD and new_pass == ESSAY_TEACHER_PASSWORD):
                        st.error("そのパスワードは既に使われています。別のパスワードを考えてね！")
                    else:
                        users[new_pass] = new_name
                        save_json(USERS_PATH, users)
                        st.success("登録が完了しました！さっそく始めましょう！")
                        st.session_state["logged_in"] = True
                        st.session_state["student_id"] = new_pass
                        st.session_state["student_name"] = new_name
                        st.session_state["is_admin"] = False
                        st.session_state["is_teacher"] = False
                        st.query_params.token = session_store.create_session(new_pass)
                        st.rerun()

        return False
    return True


def main():
    if db_error:
        st.error(
            f"🚨 **データベース接続エラー**\n\nデータベース（Firestore）に正しく接続できていません。"
            f"以下のエラーメッセージをコピーして開発者にお知らせください。\n\n`{db_error}`"
        )

    if not check_password_and_login():
        return

    student_id = st.session_state["student_id"]
    student_name = st.session_state["student_name"]
    is_admin = st.session_state.get("is_admin", False)
    is_teacher = st.session_state.get("is_teacher", False)

    st.sidebar.title(f"ようこそ、{student_name}さん！")

    if is_admin:
        menu_options = ["⚙️ 管理ダッシュボード", "📝 添削レビュー"]
    elif is_teacher:
        # 添削担当教師は、提出の閲覧・コメント追加のみに権限を限定する
        menu_options = ["📝 添削レビュー"]
    else:
        menu_options = ["✍️ 小論文添削", "📊 対策レポート"]

    page = st.sidebar.radio("メニュー", menu_options)

    if st.sidebar.button("ログアウト"):
        session_store.delete_session(st.query_params.get("token"))
        st.session_state.clear()
        st.query_params.clear()
        st.rerun()

    api_key = st.secrets.get("GEMINI_API_KEY", "")

    if page == "⚙️ 管理ダッシュボード":
        st.title("⚙️ 管理ダッシュボード")

        st.subheader("システム設定")
        app_settings = load_json("app_settings.json", {"allow_registration": True})
        allow_registration = st.toggle(
            "✨ 新規会員登録の受付を許可する", value=app_settings.get("allow_registration", True)
        )
        if allow_registration != app_settings.get("allow_registration", True):
            app_settings["allow_registration"] = allow_registration
            save_json("app_settings.json", app_settings)
            st.toast("システム設定を更新しました！", icon="✅")
            st.rerun()

        st.markdown("---")
        st.subheader("登録済みの生徒")
        users = load_json(USERS_PATH, {})
        if not users:
            st.info("まだ登録している生徒はいません。")
        else:
            for password, name in sorted(users.items(), key=lambda item: item[1]):
                st.write(f"- {name}（パスワード: `{password}`）")

    elif page == "📝 添削レビュー":
        essay_ui.render_teacher_review_page()

    elif page == "✍️ 小論文添削":
        essay_ui.render_practice_page(student_id, student_name, api_key)

    elif page == "📊 対策レポート":
        essay_ui.render_report_page(student_id, student_name, api_key)


if __name__ == "__main__":
    main()
