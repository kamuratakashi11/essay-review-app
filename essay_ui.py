import os

from PIL import Image
import streamlit as st

import essay_data
import gemini_service
from image_utils import convert_pdf_to_image

FACULTY_OPTIONS = ["医療系", "教育系", "法学系", "経済・経営系", "人文・社会科学系", "理工系", "その他・未定"]

# 手書き原稿用紙のマス目を判読するには、通常の解答写真より高い解像度が必要
MANUSCRIPT_SCALE = 3.0


def _load_uploaded_images(uploaded_files, scale=2.0):
    images = []
    for uf in uploaded_files:
        if uf.name.lower().endswith(".pdf"):
            images.extend(convert_pdf_to_image(uf, scale=scale))
        else:
            images.append(Image.open(uf))
    return images


def _render_faculty_form(student_id):
    st.info("💡 まず、志望する学部・分野を教えてください。テーマ生成の参考にします。")
    faculty = st.selectbox("志望分野", FACULTY_OPTIONS, key="essay_faculty_select")
    detail = st.text_input("詳細（例: 看護学部、○○大学法学部 など）", key="essay_faculty_detail_input")
    if st.button("登録する", key="essay_faculty_submit"):
        essay_data.set_target_faculty(student_id, faculty, detail)
        st.rerun()


def _reset_practice_session():
    for key in list(st.session_state.keys()):
        if key.startswith("essay_practice_"):
            del st.session_state[key]


def render_practice_page(student_id, student_name, api_key):
    st.title("✍️ 小論文添削")

    if not api_key:
        st.error("システムエラー: 裏側のAI設定（APIキー）が完了していません。先生に報告してください。")
        return

    target_faculty, target_faculty_detail = essay_data.get_target_faculty(student_id)

    if not target_faculty:
        _render_faculty_form(student_id)
        return

    with st.expander(f"志望分野: {target_faculty}（{target_faculty_detail or '詳細未設定'}） を変更する"):
        _render_faculty_form(student_id)

    # 採点済みの結果が残っている場合は、そちらを優先して表示する
    if "essay_practice_grade_result" in st.session_state:
        _render_grade_result(student_id, student_name, target_faculty, target_faculty_detail, api_key)
        return

    mode = st.radio(
        "取り組むテーマ",
        ["AIが出したテーマに取り組む", "自分で用意した過去問に取り組む"],
        key="essay_practice_mode",
    )
    is_brought_in = mode == "自分で用意した過去問に取り組む"

    theme_text = None
    if is_brought_in:
        theme_text = _render_brought_in_theme_section(api_key)
    else:
        theme_text = _render_ai_theme_section(student_id, target_faculty, target_faculty_detail, api_key)

    if not theme_text:
        return

    st.markdown("---")
    st.subheader("📝 提出")
    essay_text = _render_submission_section(api_key)
    if essay_text is None:
        return

    if st.button("🎯 添削してもらう", type="primary", key="essay_practice_grade_btn"):
        with st.spinner("先生が添削中です…"):
            try:
                result = gemini_service.grade_essay(
                    theme_text, essay_text, target_faculty, target_faculty_detail, api_key,
                    is_brought_in=is_brought_in,
                )
            except Exception as e:
                st.error(gemini_service.describe_gemini_error(e))
                return

        if result.get("off_topic"):
            st.warning(f"⚠️ この内容では採点できませんでした: {result.get('off_topic_reason') or 'テーマと関係が確認できませんでした。'}")
            return

        st.session_state["essay_practice_grade_result"] = result
        st.session_state["essay_practice_graded_theme_text"] = theme_text
        st.session_state["essay_practice_graded_essay_text"] = essay_text
        st.session_state["essay_practice_graded_is_brought_in"] = is_brought_in
        st.rerun()


def _render_manuscript_template_download():
    if os.path.exists(essay_data.MANUSCRIPT_TEMPLATE_PATH):
        with open(essay_data.MANUSCRIPT_TEMPLATE_PATH, "rb") as f:
            st.download_button(
                "📄 800字詰め原稿用紙のテンプレートをダウンロード（ノートアプリに読み込んで手書き用）",
                data=f.read(),
                file_name="essay_manuscript_template.pdf",
                mime="application/pdf",
                key="essay_practice_template_download",
            )


def _render_ai_theme_section(student_id, target_faculty, target_faculty_detail, api_key):
    current_theme = essay_data.get_current_theme(student_id)
    if not current_theme or current_theme.get("source") != "ai_auto":
        with st.spinner("AIがテーマを考えています…"):
            try:
                weakness_tags = essay_data.get_recent_weakness_tags(student_id)
                genre_hints = essay_data.get_genre_hints(student_id)
                theme_text = gemini_service.generate_essay_theme(
                    target_faculty, target_faculty_detail, weakness_tags, genre_hints, api_key
                )
            except Exception as e:
                st.error(gemini_service.describe_gemini_error(e))
                return None
        essay_data.save_current_theme(student_id, theme_text, source="ai_auto")
        current_theme = essay_data.get_current_theme(student_id)

    st.markdown(f"### 今回のテーマ\n\n{current_theme['theme_text']}")
    if st.button("🔄 別のテーマに変える", key="essay_practice_new_theme"):
        with st.spinner("AIが新しいテーマを考えています…"):
            try:
                weakness_tags = essay_data.get_recent_weakness_tags(student_id)
                genre_hints = essay_data.get_genre_hints(student_id)
                theme_text = gemini_service.generate_essay_theme(
                    target_faculty, target_faculty_detail, weakness_tags, genre_hints, api_key
                )
                essay_data.save_current_theme(student_id, theme_text, source="ai_auto")
                st.rerun()
            except Exception as e:
                st.error(gemini_service.describe_gemini_error(e))
    _render_manuscript_template_download()
    return current_theme["theme_text"]


def _render_brought_in_theme_section(api_key):
    st.caption("実在の入試問題の設問文・課題文が写っている写真かPDFをアップロードしてください。読み取った原文はこの添削にのみ使用し、保存はしません。")
    uploaded = st.file_uploader(
        "問題文の写真・PDF", type=["png", "jpg", "jpeg", "pdf"], key="essay_practice_brought_in_upload"
    )
    if uploaded and "essay_practice_brought_in_text" not in st.session_state:
        images = _load_uploaded_images([uploaded])
        if not images:
            st.error("画像の読み込みに失敗しました。")
            return None
        if st.button("この画像から問題文を読み取る", key="essay_practice_ocr_theme_btn"):
            with st.spinner("問題文を読み取っています…"):
                try:
                    problem_text = gemini_service.read_problem_statement_image(images[0], api_key)
                except Exception as e:
                    st.error(gemini_service.describe_gemini_error(e))
                    return None
            st.session_state["essay_practice_brought_in_text"] = problem_text
            st.rerun()
        return None

    if "essay_practice_brought_in_text" in st.session_state:
        edited = st.text_area(
            "読み取った問題文（誤読があれば修正してください）",
            value=st.session_state["essay_practice_brought_in_text"],
            key="essay_practice_brought_in_text_area",
            height=150,
        )
        st.session_state["essay_practice_brought_in_text"] = edited
        _render_manuscript_template_download()
        return edited
    return None


def _render_submission_section(api_key):
    input_mode = st.radio(
        "提出方法", ["テキスト入力", "写真・PDFをアップロード（800字詰め原稿用紙）"], key="essay_practice_input_mode"
    )

    if input_mode == "テキスト入力":
        text = st.text_area("小論文本文", key="essay_practice_text_input", height=300)
        char_count = len(text)
        sheets = char_count / 800
        st.caption(f"{char_count}字 / 800字詰め原稿用紙 約{sheets:.1f}枚相当")
        return text if text.strip() else None

    st.caption("紙に手書きした写真、またはノートアプリ（GoodNotes等）から書き出したPDF・画像をアップロードしてください（複数ページ可）。")

    uploaded_files = st.file_uploader(
        "原稿用紙の写真・PDF（複数ページ可、ページ順にアップロード）",
        type=["png", "jpg", "jpeg", "pdf"],
        accept_multiple_files=True,
        key="essay_practice_manuscript_upload",
    )

    if "essay_practice_ocr_text" not in st.session_state:
        if uploaded_files and st.button("原稿を読み取る", key="essay_practice_ocr_btn"):
            images = _load_uploaded_images(uploaded_files, scale=MANUSCRIPT_SCALE)
            if not images:
                st.error("画像の読み込みに失敗しました。")
                return None
            with st.spinner("原稿を読み取っています…"):
                try:
                    ocr_result = gemini_service.transcribe_manuscript_paper(images, api_key)
                except Exception as e:
                    st.error(gemini_service.describe_gemini_error(e))
                    return None
            st.session_state["essay_practice_ocr_text"] = ocr_result["transcribed_text"]
            if ocr_result.get("low_confidence_notes"):
                st.session_state["essay_practice_ocr_notes"] = ocr_result["low_confidence_notes"]
            st.rerun()
        return None

    if st.session_state.get("essay_practice_ocr_notes"):
        st.warning(f"⚠️ 読み取りに自信が持てなかった箇所があります: {st.session_state['essay_practice_ocr_notes']}")

    edited_text = st.text_area(
        "読み取った本文（誤読があれば修正してから提出してください）",
        value=st.session_state["essay_practice_ocr_text"],
        key="essay_practice_ocr_text_area",
        height=300,
    )
    char_count = len(edited_text)
    st.caption(f"{char_count}字 / 800字詰め原稿用紙 約{char_count / 800:.1f}枚相当")
    st.session_state["essay_practice_ocr_text"] = edited_text
    return edited_text if edited_text.strip() else None


def _render_grade_result(student_id, student_name, target_faculty, target_faculty_detail, api_key):
    result = st.session_state["essay_practice_grade_result"]
    theme_text = st.session_state["essay_practice_graded_theme_text"]
    essay_text = st.session_state["essay_practice_graded_essay_text"]
    is_brought_in = st.session_state["essay_practice_graded_is_brought_in"]

    st.subheader(f"📊 採点結果: {result['total_score']}点")
    for criterion in essay_data.RUBRIC_CRITERIA:
        score_entry = result["scores"].get(criterion["key"], {})
        st.markdown(f"**{criterion['label']}: {score_entry.get('points', 0)} / {criterion['max']}点**")
        st.caption(score_entry.get("comment", ""))

    if result.get("strengths"):
        st.markdown("**良かった点**")
        for s in result["strengths"]:
            st.markdown(f"- {s}")

    if result.get("weakness_tags"):
        st.markdown("**改善が必要な点**")
        for w in result["weakness_tags"]:
            st.markdown(f"- {w}")

    st.markdown("**総合講評**")
    st.markdown(result.get("feedback_summary", ""))

    # まだこの結果を保存していなければ、提出履歴に保存する（rerun時の重複保存を防ぐ）
    if not st.session_state.get("essay_practice_saved"):
        actual_input_mode = "image" if st.session_state.get("essay_practice_input_mode", "").startswith("写真") else "text"
        submission = {
            "theme_text": theme_text if not is_brought_in else "（生徒が持ち込んだ実在の入試問題のため、原文は保存していません）",
            "input_mode": actual_input_mode,
            "essay_text": essay_text,
            "char_count": len(essay_text),
            "manuscript_sheets": round(len(essay_text) / 400, 1),
            "scores": result["scores"],
            "total_score": result["total_score"],
            "strengths": result.get("strengths", []),
            "weakness_tags": result.get("weakness_tags", []),
            "ai_feedback_summary": result.get("feedback_summary", ""),
            "brought_in_problem": is_brought_in,
            "genre_hint_for_future": result.get("genre_hint") if is_brought_in else None,
        }
        record = essay_data.add_submission(student_id, submission)
        essay_data.enqueue_for_review(student_id, student_name, record["id"], result["total_score"])

        # 直前の弱点を踏まえて次のテーマを事前生成しておく
        try:
            weakness_tags = essay_data.get_recent_weakness_tags(student_id)
            genre_hints = essay_data.get_genre_hints(student_id)
            next_theme = gemini_service.generate_essay_theme(
                target_faculty, target_faculty_detail, weakness_tags, genre_hints, api_key
            )
            essay_data.save_current_theme(student_id, next_theme, source="ai_auto")

            submissions = essay_data.load_submissions(student_id)
            summaries = essay_data.summarize_submissions_for_report(submissions)
            report = gemini_service.generate_progress_report(student_name, target_faculty, summaries, api_key)
            essay_data.save_report_cache(student_id, report, based_on_count=len(submissions))
        except Exception:
            # 次テーマ・レポートの事前生成に失敗しても、採点結果自体は既に保存済みなので握りつぶす
            pass

        st.session_state["essay_practice_saved"] = True

    if st.button("➡️ 次のテーマに進む", key="essay_practice_next_theme"):
        _reset_practice_session()
        st.rerun()


def render_report_page(student_id, student_name, api_key):
    st.title("📊 小論文 対策レポート")

    cache = essay_data.get_report_cache(student_id)
    if not cache:
        st.info("まだ対策レポートがありません。まずは「✍️ 小論文添削」ページで1回挑戦してください。")
        return

    st.caption(f"直近{cache.get('based_on_submission_count', 0)}件の提出をもとに作成（最終更新: {cache.get('generated_at', '')[:16].replace('T', ' ')}）")
    st.markdown(cache.get("content", ""))

    if st.button("🔄 レポートを最新の状態に再生成する", key="essay_report_regen"):
        if not api_key:
            st.error("システムエラー: 裏側のAI設定（APIキー）が完了していません。先生に報告してください。")
            return
        target_faculty, _ = essay_data.get_target_faculty(student_id)
        submissions = essay_data.load_submissions(student_id)
        if not submissions:
            st.warning("まだ提出履歴がありません。")
            return
        with st.spinner("レポートを再生成しています…"):
            try:
                summaries = essay_data.summarize_submissions_for_report(submissions)
                report = gemini_service.generate_progress_report(student_name, target_faculty, summaries, api_key)
                essay_data.save_report_cache(student_id, report, based_on_count=len(submissions))
                st.rerun()
            except Exception as e:
                st.error(gemini_service.describe_gemini_error(e))


def render_teacher_review_page():
    st.title("📝 添削レビュー")

    queue = essay_data.load_review_queue()
    unreviewed = [i for i in queue if not i.get("reviewed")]
    reviewed = [i for i in queue if i.get("reviewed")]

    tab_unreviewed, tab_reviewed = st.tabs([f"未レビュー（{len(unreviewed)}）", f"レビュー済み（{len(reviewed)}）"])

    with tab_unreviewed:
        _render_review_list(unreviewed)
    with tab_reviewed:
        _render_review_list(reviewed)


def _render_review_list(entries):
    if not entries:
        st.caption("対象がありません。")
        return

    for entry in sorted(entries, key=lambda e: e.get("created_at", ""), reverse=True):
        label = f"{entry['student_name']}さん（{entry.get('created_at', '')[:16].replace('T', ' ')}） - 総合{entry.get('total_score', '?')}点"
        with st.expander(label):
            submissions = essay_data.load_submissions(entry["student_id"])
            submission = next((s for s in submissions if s.get("id") == entry["submission_id"]), None)
            if not submission:
                st.caption("提出データが見つかりませんでした。")
                continue

            st.markdown(f"**テーマ**\n\n{submission.get('theme_text', '')}")
            st.markdown(f"**本文**\n\n{submission.get('essay_text', '')}")
            st.markdown("**AIスコア内訳**")
            for criterion in essay_data.RUBRIC_CRITERIA:
                score_entry = submission.get("scores", {}).get(criterion["key"], {})
                st.caption(f"{criterion['label']}: {score_entry.get('points', 0)} / {criterion['max']}点 — {score_entry.get('comment', '')}")
            st.markdown(f"**AI総合講評**\n\n{submission.get('ai_feedback_summary', '')}")

            existing_review = submission.get("teacher_review")
            comment_key = f"essay_teacher_comment_{entry['submission_id']}"
            comment = st.text_area(
                "コメント",
                value=(existing_review or {}).get("comment", ""),
                key=comment_key,
            )
            if st.button("保存する", key=f"essay_teacher_save_{entry['submission_id']}"):
                essay_data.attach_teacher_comment(entry["student_id"], entry["submission_id"], comment)
                st.success("保存しました。")
                st.rerun()
