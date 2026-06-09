from flask import Flask, request, send_file, jsonify
from pdf2image import convert_from_bytes
import pytesseract
from PIL import Image, ImageDraw, ImageFont
import pandas as pd
import io, re, os
from pypdf import PdfWriter, PdfReader
import openpyxl

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@app.route('/')
def index():
    return open(os.path.join(BASE_DIR, 'index.html'), encoding='utf-8').read()

@app.route('/processar', methods=['POST'])
def processar():
    try:
        pdf_bytes = request.files['pdf'].read()
        xlsx_file = request.files['excel']

        df = pd.read_excel(xlsx_file, dtype=str)
        df.columns = [c.lower().strip() for c in df.columns]
        col_cod  = next((c for c in df.columns if c in ['codigo','código','cod','code','sku']),  df.columns[0])
        col_prec = next((c for c in df.columns if c in ['preco','preço','price','valor','vl','vlr']), df.columns[1])

        precos = {}
        for _, row in df.iterrows():
            cod = str(row[col_cod]).strip().replace('.0','').replace(' ','')
            try:
                precos[cod] = float(str(row[col_prec]).replace(',','.').replace(' ',''))
            except: pass

        pages = convert_from_bytes(pdf_bytes, dpi=150)
        writer = PdfWriter()
        total_found, missing = 0, []

        for page_img in pages:
            img = page_img.copy()
            draw = ImageDraw.Draw(img)
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, lang='eng')

            for i, word in enumerate(data['text']):
                clean = word.strip()
                if re.match(r'^\d{5,7}$', clean):
                    if clean in precos:
                        h = data['height'][i]
                        fs = max(int(h * 0.85), 16)
                        try:
                            f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", fs)
                        except:
                            f = ImageFont.load_default()
                        texto = "- R$ {:.2f}".format(precos[clean]).replace('.', ',')
                        x = data['left'][i] + data['width'][i] + 5
                        y = data['top'][i]
                        draw.text((x, y), texto, fill=(212, 43, 43), font=f)
                        total_found += 1
                    elif clean not in missing:
                        missing.append(clean)

            buf = io.BytesIO()
            img.save(buf, format='PDF', resolution=150)
            buf.seek(0)
            reader = PdfReader(buf)
            writer.add_page(reader.pages[0])

        out = io.BytesIO()
        writer.write(out)
        out.seek(0)

        resp = send_file(out, mimetype='application/pdf',
                         as_attachment=True, download_name='lamina_precificada.pdf')
        resp.headers['X-Found']   = str(total_found)
        resp.headers['X-Missing'] = ','.join(missing)
        return resp

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/modelo')
def modelo():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Precos"
    ws.append(['codigo', 'preco'])
    ws.append(['389919', '45,90'])
    ws.append(['792322', '32,50'])
    buf = io.BytesIO()
    wb.save(buf); buf.seek(0)
    return send_file(buf,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True, download_name='modelo_precos.xlsx')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)
