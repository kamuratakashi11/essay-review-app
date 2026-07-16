import io
import os
import tempfile
import fitz  # PyMuPDF
from PIL import Image


def convert_pdf_to_image(uploaded_file, scale=2.0):
    # PDFの中身がストリームだと正常に全ページ読み込めない場合があるため、一度一時ファイルに保存する
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name

    doc = None
    try:
        doc = fitz.open(tmp_path)
        images = []
        mat = fitz.Matrix(scale, scale)
        for i in range(len(doc)):
            page = doc[i]
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data)).convert("RGB")
            # 一括送信時にデータ容量オーバー（Payload Too Large等）で弾かれるのを防ぐため画像サイズを圧縮
            img.thumbnail((1500, 1500))
            images.append(img)
        return images
    except Exception:
        return []
    finally:
        # Windowsエラー対策: 削除する前に必ずファイルを閉じる
        if doc is not None:
            doc.close()
        # 処理が終わったら確実に一時ファイルを削除
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
