import os
import uuid
from datetime import datetime

from storage import BASE_DIR, load_json, save_json

# 全生徒共通の固定ルーブリック（教師カスタマイズは今回なし）
RUBRIC_CRITERIA = [
    {"key": "structure", "label": "構成・展開", "max": 25},
    {"key": "logic", "label": "論理性・説得力", "max": 30},
    {"key": "originality", "label": "独自性", "max": 20},
    {"key": "expression", "label": "表現力・文章力", "max": 15},
    {"key": "relevance", "label": "課題理解・テーマ適合性", "max": 10},
]

REVIEW_QUEUE_PATH = os.path.join(BASE_DIR, "essay_review_queue.json")

# ノートアプリ（GoodNotes等）で書く生徒向けに配布する、800字詰め原稿用紙のテンプレート
MANUSCRIPT_TEMPLATE_PATH = os.path.join(BASE_DIR, "essay_manuscript_template.pdf")

# 教師レビューキューに溜め続けると際限なく肥大化するため、古いレビュー済みエントリは
# 一定件数を超えたら間引く（未レビューのエントリは常に残す）
REVIEW_QUEUE_MAX_REVIEWED = 500


def _profile_path(student_id):
    return os.path.join(BASE_DIR, f"essay_profile_{student_id}.json")


def _submissions_path(student_id):
    return os.path.join(BASE_DIR, f"essay_submissions_{student_id}.json")


def _load_profile_doc(student_id):
    return load_json(_profile_path(student_id), {})


def _save_profile_doc(student_id, doc):
    save_json(_profile_path(student_id), doc)


# --- 生徒プロフィール（志望学部・分野） ---

def get_target_faculty(student_id):
    doc = _load_profile_doc(student_id)
    return doc.get("target_faculty", ""), doc.get("target_faculty_detail", "")


def set_target_faculty(student_id, faculty, detail):
    doc = _load_profile_doc(student_id)
    doc["target_faculty"] = faculty
    doc["target_faculty_detail"] = detail
    doc["updated_at"] = datetime.now().isoformat()
    _save_profile_doc(student_id, doc)


# --- 生徒ごとの軽量ドキュメント: 現在のテーマ・対策レポートキャッシュ ---

def get_current_theme(student_id):
    return _load_profile_doc(student_id).get("current_theme")


def save_current_theme(student_id, theme_text, source):
    doc = _load_profile_doc(student_id)
    doc["current_theme"] = {
        "theme_text": theme_text,
        "source": source,  # "ai_auto" or "brought_in"
        "created_at": datetime.now().isoformat(),
    }
    doc["updated_at"] = datetime.now().isoformat()
    _save_profile_doc(student_id, doc)


def get_report_cache(student_id):
    return _load_profile_doc(student_id).get("report_cache")


def save_report_cache(student_id, content, based_on_count):
    doc = _load_profile_doc(student_id)
    doc["report_cache"] = {
        "content": content,
        "generated_at": datetime.now().isoformat(),
        "based_on_submission_count": based_on_count,
    }
    doc["updated_at"] = datetime.now().isoformat()
    _save_profile_doc(student_id, doc)


# --- 生徒ごとの提出履歴（本文・添削文を含む重いデータ） ---

def load_submissions(student_id):
    return load_json(_submissions_path(student_id), {}).get("items", [])


def add_submission(student_id, submission):
    """submission辞書にはid/created_atを自動付与する。呼び出し元は残りのフィールド
    （theme_text, input_mode, essay_text, char_count, manuscript_sheets, scores,
    total_score, strengths, weakness_tags, ai_feedback_summary, brought_in_problem,
    genre_hint_for_future, teacher_review）を渡すこと。"""
    doc = load_json(_submissions_path(student_id), {})
    items = doc.get("items", [])
    record = dict(submission)
    record["id"] = str(uuid.uuid4())
    record["created_at"] = datetime.now().isoformat()
    record.setdefault("teacher_review", None)
    items.append(record)
    doc["items"] = items
    save_json(_submissions_path(student_id), doc)
    return record


def get_recent_weakness_tags(student_id, n=3):
    items = load_submissions(student_id)
    recent = items[-n:] if items else []
    tags = []
    for item in recent:
        tags.extend(item.get("weakness_tags") or [])
    return tags[:10]


def get_genre_hints(student_id, n=3):
    items = load_submissions(student_id)
    hints = [item.get("genre_hint_for_future") for item in reversed(items) if item.get("genre_hint_for_future")]
    return hints[:n]


def summarize_submissions_for_report(items, limit=15):
    """対策レポート生成用に、本文全文を含まない軽量なサマリー行のリストを作る
    （プロンプトの肥大化・不要なコスト増を避けるため）。"""
    lines = []
    for item in items[-limit:]:
        date = (item.get("created_at") or "")[:10]
        score = item.get("total_score", "?")
        tags = "、".join(item.get("weakness_tags") or []) or "特になし"
        lines.append(f"{date}: 総合{score}点 / 弱点: {tags}")
    return lines


def attach_teacher_review_to_submission(student_id, submission_id, teacher_comment):
    doc = load_json(_submissions_path(student_id), {})
    items = doc.get("items", [])
    for item in items:
        if item.get("id") == submission_id:
            item["teacher_review"] = {
                "comment": teacher_comment,
                "commented_at": datetime.now().isoformat(),
            }
            break
    doc["items"] = items
    save_json(_submissions_path(student_id), doc)


# --- 教師レビュー用の軽量共有インデックス ---

def load_review_queue():
    return load_json(REVIEW_QUEUE_PATH, {}).get("items", [])


def _save_review_queue(items):
    save_json(REVIEW_QUEUE_PATH, {"items": items})


def enqueue_for_review(student_id, student_name, submission_id, total_score):
    items = load_review_queue()
    items.append({
        "student_id": student_id,
        "student_name": student_name,
        "submission_id": submission_id,
        "created_at": datetime.now().isoformat(),
        "total_score": total_score,
        "reviewed": False,
    })

    reviewed_items = [i for i in items if i.get("reviewed")]
    if len(reviewed_items) > REVIEW_QUEUE_MAX_REVIEWED:
        unreviewed_items = [i for i in items if not i.get("reviewed")]
        items = unreviewed_items + reviewed_items[-REVIEW_QUEUE_MAX_REVIEWED:]

    _save_review_queue(items)


def mark_reviewed(student_id, submission_id):
    items = load_review_queue()
    for item in items:
        if item.get("student_id") == student_id and item.get("submission_id") == submission_id:
            item["reviewed"] = True
            break
    _save_review_queue(items)


def attach_teacher_comment(student_id, submission_id, teacher_comment):
    """レビューキューへの既読反映と、提出本体へのコメント保存をまとめて行う。"""
    attach_teacher_review_to_submission(student_id, submission_id, teacher_comment)
    mark_reviewed(student_id, submission_id)
