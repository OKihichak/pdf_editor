import os
from flask import Flask, request, render_template, send_from_directory
import fitz  # PyMuPDF
import cv2
import numpy as np
from PIL import Image
from qreader import QReader

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['PROCESSED_FOLDER'] = 'uploads'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

qreader = QReader()


def detect_and_redact_qr_code(page, zoom=8.0):
    text = page.get_text().lower()
    is_expert_page = "expertenkarten" in text

    if is_expert_page:
        rect_qr_top = fitz.Rect(430, 315, 585, 390)
        rect_qr_bottom = fitz.Rect(430, 650, 585, 770)
        page.add_redact_annot(rect_qr_top, fill=(1, 1, 1))
        page.add_redact_annot(rect_qr_bottom, fill=(1, 1, 1))
        return

    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    detector = cv2.QRCodeDetector()
    data, points, _ = detector.detectAndDecode(img_cv)

    if data and points is not None:
        pts = points[0].astype(int)
        x, y, w, h = cv2.boundingRect(pts)
        scale_x = page.rect.width / pix.width
        scale_y = page.rect.height / pix.height
        margin = 6

        qr_rect = fitz.Rect(
            (x - margin) * scale_x,
            (y - margin) * scale_y,
            (x + w + margin) * scale_x,
            (y + h + margin) * scale_y
        )
        page.add_redact_annot(qr_rect, fill=(1, 1, 1))


def process_pdf_all_in_one(input_pdf_path, output_pdf_path, logo_image_path="static/ensago_logo.png"):
    terms_to_delete = [
        "syte report", "transforming real estate with ai", "syte app", "syte", "syte-"
    ]
    doc = fitz.open(input_pdf_path)
    new_doc = fitz.open()

    skipped_inhalt = False
    for i, page in enumerate(doc):
        text = page.get_text("text").lower()
        if "inhalt" in text and not skipped_inhalt:
            skipped_inhalt = True
            continue
        if "sanierungspotenziale" in text:
            continue
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if lines and lines[0].startswith("kontakt"):
            break
        new_doc.insert_pdf(doc, from_page=i, to_page=i)

    if new_doc.page_count == 0:
        return False

    rect_logo_top = fitz.Rect(420, 30, 580, 160)
    rect_logo_bottom = fitz.Rect(20, 780, 90, 820)

    for page_num in range(len(new_doc)):
        page = new_doc[page_num]

        for term in terms_to_delete:
            matches = page.search_for(term)
            for rect in matches:
                page.add_redact_annot(rect, fill=(1, 1, 1))

        page.add_redact_annot(rect_logo_bottom, fill=(1, 1, 1))
        if page_num == 0:
            page.add_redact_annot(rect_logo_top, fill=(1, 1, 1))

        detect_and_redact_qr_code(page)

        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE)

        page.insert_text(fitz.Point(35, 805), "EnSaGo Report",
                         fontsize=8, fontname="helv", color=(0, 0, 0))

        if page_num == 0:
            try:
                page.insert_image(rect_logo_top, filename=logo_image_path)
                page.insert_text(fitz.Point(475, 125), "Invest Green, Earn More",
                                 fontsize=7.5, fontname="helv", color=(0, 0, 0))
                page.insert_text(fitz.Point(510, 135), "www.ensago.de",
                                 fontsize=6.5, fontname="helv", color=(0, 0, 0))
            except Exception as e:
                print(f"⚠️ Could not insert logo image: {e}")

    new_doc.save(output_pdf_path, garbage=3, deflate=True)
    return True


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        uploaded_file = request.files["pdf"]
        if uploaded_file.filename.endswith(".pdf"):
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], uploaded_file.filename)
            uploaded_file.save(input_path)

            output_path = os.path.join(app.config['PROCESSED_FOLDER'], "processed_" + uploaded_file.filename)

            if process_pdf_all_in_one(input_path, output_path):
                return render_template("index.html", download_link="processed_" + uploaded_file.filename)
            else:
                return "❌ No content was processed. Check your file."

    return render_template("index.html")


@app.route("/uploads/<filename>")
def download_file(filename):
    return send_from_directory(app.config['PROCESSED_FOLDER'], filename, as_attachment=True)


if __name__ == "__main__":
    app.run(debug=True)
