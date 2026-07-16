"""
ログイン状態をURLパラメータ（?token=...）で復元するためのセッショントークン管理。

以前はURLのtokenにパスワードそのもの（生徒の場合はstudent_idと同一）を
入れていたため、アドレスバー・ブラウザ履歴・画面共有等でパスワードが
そのまま見えてしまっていた。

署名付きトークン（HMAC等）に変えるだけでは不十分な点に注意が必要:
署名は「改ざんされていないか」は保証できても、Base64は暗号化ではないため
「中身を第三者が読めないようにする」ことはできない。生徒のパスワードを
そのままペイロードに入れてしまうと、署名を付けても結局パスワードが
読めてしまう。

そこで、パスワードや student_id を一切含まない、ランダムな不透明トークンを
発行し、その対応関係（トークン→student_id）だけをサーバー側（Firestore）に
保存する方式にする。URLにはこのランダムトークンしか出ないため、たとえ
盗み見られてもパスワードは一切分からない。
"""

import secrets as pysecrets
import time

from storage import load_json, save_json, SESSIONS_PATH

DEFAULT_TTL_SECONDS = 30 * 24 * 3600  # 30日


def create_session(student_id, is_admin=False, is_teacher=False, ttl_seconds=DEFAULT_TTL_SECONDS):
    """新しいセッショントークンを発行して保存し、トークン文字列を返す。"""
    sessions = load_json(SESSIONS_PATH, {})
    token = pysecrets.token_urlsafe(32)
    sessions[token] = {
        "student_id": student_id,
        "is_admin": is_admin,
        "is_teacher": is_teacher,
        "expires_at": time.time() + ttl_seconds,
    }
    save_json(SESSIONS_PATH, sessions)
    return token


def resolve_session(token):
    """トークンが有効なら (student_id, is_admin, is_teacher) を、無効・期限切れなら None を返す。"""
    if not token:
        return None
    sessions = load_json(SESSIONS_PATH, {})
    entry = sessions.get(token)
    if not entry:
        return None
    if entry.get("expires_at", 0) < time.time():
        return None
    return entry.get("student_id"), bool(entry.get("is_admin", False)), bool(entry.get("is_teacher", False))


def delete_session(token):
    """ログアウト時などに、サーバー側のセッションを無効化する。"""
    if not token:
        return
    sessions = load_json(SESSIONS_PATH, {})
    if token in sessions:
        del sessions[token]
        save_json(SESSIONS_PATH, sessions)
