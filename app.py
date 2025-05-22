import io
from flask import Flask, request, render_template, send_file
import fitz  # PyMuPDF
import cv2
import numpy as np
from PIL import Image

app = Flask(__name__)
app.config['LOGO_PATH'] = 'static/ensago_logo.png'

def detect_and_redact_qr_code(page, zoom=4.0):  # reduced zoom to save memory
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


#FINANCE REPORT


import fitz  # PyMuPDF
import io
import cv2
import numpy as np
from PIL import Image


def process_finance_report(file_stream, logo_path="static/ensago_logo.png", blur_finance=False):
    original = fitz.open(stream=file_stream.read(), filetype="pdf")
    subset = fitz.open()

    kontakt_triggered = False
    skipped_inhalt = False
    start_after_kontakt = None
    end_before_glossar = None

    # Step 1: Extract all pages up to (but not including) Glossar
    for i, page in enumerate(original):
        text = page.get_text("text").lower()
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        if "inhalt" in text and not skipped_inhalt:
            skipped_inhalt = True
            continue

        if "sanierungspotenziale" in text:
            continue

        if not kontakt_triggered and lines and lines[0].startswith("kontakt"):
            kontakt_triggered = True
            start_after_kontakt = i + 1
            continue

        if kontakt_triggered and "glossar" in text:
            end_before_glossar = i
            break

        if not kontakt_triggered:
            subset.insert_pdf(original, from_page=i, to_page=i)

    if start_after_kontakt is not None and end_before_glossar is not None:
        subset.insert_pdf(original, from_page=start_after_kontakt, to_page=end_before_glossar - 1)

    # Step 2: Detect last Expertenkarten page
    last_expertenkarten_page = -1
    for i, page in enumerate(subset):
        if "expertenkarten" in page.get_text().lower():
            last_expertenkarten_page = i

    # Step 3: Apply redactions first (MUST be done before rendering)
    terms_to_delete = [
        "syte report", "Transforming Real Estate with AI", "syte App", "www.syte.ms", "syte"
    ]
    rect_logo_top = fitz.Rect(420, 30, 580, 160)
    rect_logo_bottom = fitz.Rect(20, 780, 90, 820)
    rect_subtitle = fitz.Rect(10, 20, 800, 90)

    for i, page in enumerate(subset):
        # Redaction boxes
        for term in terms_to_delete:
            for rect in page.search_for(term):
                page.add_redact_annot(rect, fill=(1, 1, 1))

        if i == last_expertenkarten_page + 1:
            page.add_redact_annot(rect_subtitle, fill=(1, 1, 1))

        page.add_redact_annot(rect_logo_bottom, fill=(1, 1, 1))
        if i == 0:
            page.add_redact_annot(rect_logo_top, fill=(1, 1, 1))

        detect_and_redact_qr_code(page)
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE)

    # Step 4: Now render pages to final output (blur or copy)
    output = fitz.open()

    for i, page in enumerate(subset):
        if blur_finance and i > last_expertenkarten_page + 1:
            # Convert page to image and apply blur
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            blurred = cv2.GaussianBlur(img_cv, (21, 21), 0)
            blurred_img = Image.fromarray(cv2.cvtColor(blurred, cv2.COLOR_BGR2RGB))

            img_bytes = io.BytesIO()
            blurred_img.save(img_bytes, format="PNG")
            img_bytes.seek(0)

            page_rect = page.rect
            new_page = output.new_page(width=page_rect.width, height=page_rect.height)
            insert_rect = fitz.Rect(0, 0, page_rect.width, page_rect.height)
            new_page.insert_image(insert_rect, stream=img_bytes.read(), keep_proportion=False)
            continue

        # Copy redacted page safely
        output.insert_pdf(subset, from_page=i, to_page=i)
        if len(output) == 0:
            continue  # skip overlay if page wasn't copied

        output_page = output[-1]  # last added page

        # Overlay
        output_page.insert_text(fitz.Point(35, 805), "EnSaGo Report", fontsize=8, fontname="helv", color=(0, 0, 0))

        if i == 0:
            output_page.insert_image(rect_logo_top, filename=logo_path)
            output_page.insert_text(fitz.Point(475, 125), "Invest Green, Earn More", fontsize=7.5, fontname="helv", color=(0, 0, 0))
            output_page.insert_text(fitz.Point(510, 135), "www.ensago.de", fontsize=6.5, fontname="helv", color=(0, 0, 0))

        if i == last_expertenkarten_page + 1:
            output_page.insert_text(fitz.Point(460, 70), "* Alle Preise sind Nettopreise", fontsize=7.5, fontname="helv", color=(0, 0, 0))

    # Return memory stream
    output_stream = io.BytesIO()
    output.save(output_stream, garbage=3, deflate=True)
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
        blur_finance = request.form.get("blur_finance") == "on"

        if uploaded_file and uploaded_file.filename.endswith(".pdf"):
            original_name = uploaded_file.filename.rsplit("/", 1)[-1]
            prefix = "blurred_finance_report_" if blur_finance else "finance_report_"
            result_filename = f"{prefix}{original_name}"

            result = process_finance_report(uploaded_file, blur_finance=blur_finance)

            return send_file(result, as_attachment=True,
                             download_name=result_filename,
                             mimetype="application/pdf")

    return render_template("finance_report.html")


