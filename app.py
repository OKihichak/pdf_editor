import io
from flask import Flask, request, render_template, send_file
import fitz  # PyMuPDF
import cv2
import numpy as np
from PIL import Image

app = Flask(__name__)
app.config['LOGO_PATH'] = 'static/ensago_logo.png'

def detect_and_redact_qr_code(page, zoom=5.0):  # reduced zoom to save memory
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


def process_pdf_memory(file_stream, logo_image_path="static/ensago_logo.png"):
    terms_to_delete = [
        "syte report", "transforming real estate with ai", "syte app", "syte", "syte-"
    ]

    doc = fitz.open(stream=file_stream.read(), filetype="pdf")
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
        return None

    rect_logo_top = fitz.Rect(420, 30, 580, 160)
    rect_logo_bottom = fitz.Rect(20, 780, 90, 820)

    for page_num in range(len(new_doc)):
        page = new_doc[page_num]

        for term in terms_to_delete:
            for rect in page.search_for(term):
                page.add_redact_annot(rect, fill=(1, 1, 1))

        page.add_redact_annot(rect_logo_bottom, fill=(1, 1, 1))
        if page_num == 0:
            page.add_redact_annot(rect_logo_top, fill=(1, 1, 1))

        detect_and_redact_qr_code(page)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE)

        page.insert_text(fitz.Point(35, 805), "EnSaGo Report", fontsize=8, fontname="helv", color=(0, 0, 0))

        if page_num == 0:
            try:
                page.insert_image(rect_logo_top, filename=logo_image_path)
                page.insert_text(fitz.Point(475, 125), "Invest Green, Earn More", fontsize=7.5, fontname="helv", color=(0, 0, 0))
                page.insert_text(fitz.Point(510, 135), "www.ensago.de", fontsize=6.5, fontname="helv", color=(0, 0, 0))
            except Exception as e:
                print(f"⚠️ Could not insert logo image: {e}")

    output_stream = io.BytesIO()
    new_doc.save(output_stream, garbage=3, deflate=True)
    output_stream.seek(0)
    return output_stream


# --- Kontakt to Glossar Processor ---
def extract_and_clean_kontakt_to_glossar(file_stream, logo_image_path="static/ensago_logo.png"):
    doc = fitz.open(stream=file_stream.read(), filetype="pdf")
    start_page = None
    end_page = None

    for i, page in enumerate(doc):
        text = page.get_text("text").lower().strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if start_page is None and lines and lines[0].startswith("kontakt"):
            start_page = i + 1
            continue
        if "glossar" in text and start_page is not None:
            end_page = i
            break

    if start_page is None or end_page is None or end_page <= start_page:
        return None

    new_doc = fitz.open()
    new_doc.insert_pdf(doc, from_page=start_page, to_page=end_page - 1)

    rect_logo = fitz.Rect(480, 20, 580, 40)
    rect_subheading = fitz.Rect(10, 50, 400, 70)

    for page_index, page in enumerate(new_doc):
        if page_index == 0:
            page.add_redact_annot(rect_logo, fill=(1, 1, 1))
            page.add_redact_annot(rect_subheading, fill=(1, 1, 1))
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE)
            page.insert_image(rect_logo, filename=logo_image_path)

    output_stream = io.BytesIO()
    new_doc.save(output_stream, garbage=3, deflate=True)
    output_stream.seek(0)
    return output_stream



@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        uploaded_file = request.files.get("pdf")
        if uploaded_file and uploaded_file.filename.endswith(".pdf"):
            result = process_pdf_memory(uploaded_file)
            if result:
                original_filename = uploaded_file.filename.rsplit("/", 1)[-1]
                processed_filename = f"processed_{original_filename}"

                return send_file(
                    result,
                    as_attachment=True,
                    download_name=processed_filename,
                    mimetype="application/pdf"
                )
            else:
                return "❌ No valid content to process."

    return render_template("index.html")

@app.route("/finance-report", methods=["GET", "POST"])
def finance_report():
    if request.method == "POST":
        uploaded_file = request.files.get("pdf")
        if uploaded_file and uploaded_file.filename.endswith(".pdf"):
            result = extract_and_clean_kontakt_to_glossar(uploaded_file.stream, app.config['LOGO_PATH'])
            if result:
                return send_file(
                    result,
                    as_attachment=True,
                    download_name=f"finance_cleaned_{uploaded_file.filename}",
                    mimetype="application/pdf"
                )
            else:
                return "❌ Could not find 'Kontakt' to 'Glossar' section in this file.", 400

    return render_template("finance_report.html")

