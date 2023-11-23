import os
import sys
import csv
import fitz
import argparse
import re
from datetime import datetime
import nltk
from textblob import TextBlob
import numpy as np
import cv2
from pytesseract import image_to_string

nltk.download('brown')

# Function to decrypt PDF
def decrypt_pdf(password, source_file):
    with fitz.open(source_file) as doc:
        doc.authenticate(password)
        doc.save(source_file[:-4] + "_decrypted.pdf")

# Function to convert PDF to CSV
def pdf_to_csv(book_num, source_file, course, output_csv):
    nltk.download('brown')
    course_pattern = r'[A-Z]{3}[0-9]{3} \| [a-zA-Z, ]+\n'
    top_bounds = [320, 550, 250, 2300]
    title_bounds = [382, 500, 307, 1660]
    title_left = [382, 500, 312, 313]
    title_sep = [382, 500, 1661, 1668]

    def _get_page_title(page):
        img = _get_page_image(page)
        boxes = _get_image_boxes(img[
            top_bounds[0]:top_bounds[1],
            top_bounds[2]:top_bounds[3]
        ])
        boxes = [cnt for cnt in boxes if cnt[0] < 200 and cnt[2] > 500 and cnt[3] > 50]
        if not len(boxes):
            return None
        title_box = _get_title_box(boxes)
        img = img[
            title_box[0]:title_box[1],
            title_box[2]:title_box[3]
        ]
        img = cv2.bitwise_not(img)
        raw = image_to_string(img, lang='eng')
        text = ' '.join([el for el in raw.replace('\x0c','').split('\n') if el.strip()])
        if 'table of contents' in text.lower():
            return None
        if 'about the course' in text.lower():
            return None
        if 'course outline' in text.lower():
            return None
        if text.lower().startswith('welcome to '):
            return None
        if ' ' * len(text) == text:
            return None
        return text

    def _get_page_image(page):
        img_bytes = np.frombuffer(page.get_pixmap(dpi=300).pil_tobytes("JPEG"), dtype=np.uint8)
        img = cv2.imdecode(img_bytes, cv2.IMREAD_COLOR)
        img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return img_gray

    def _get_image_boxes(img):
        ret, th1 = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)
        ret, th2 = cv2.threshold(th1, 127, 255, cv2.THRESH_BINARY_INV)
        kernel = np.ones((5, 5), np.uint8)
        img_dilated = cv2.dilate(th2, kernel, iterations=1)
        contours, _ = cv2.findContours(img_dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        contours = [cv2.boundingRect(cnt) for cnt in contours]
        return contours

    def _get_title_box(boxes):
        title_box = sorted(boxes, key=lambda x: x[2], reverse=True)[0]
        return [
            top_bounds[0] + title_box[1],
            top_bounds[0] + title_box[1] + title_box[3],
            top_bounds[2] + title_box[0],
            top_bounds[2] + title_box[0] + title_box[2]
        ]

    def parse_words(text):
        res = []
        words = [a.lower().strip() for a in list(TextBlob(text).noun_phrases) if len(a) > 1]
        words += [a.lower().strip() for a in TextBlob(text).words if len(a) > 1]
        words = list(set(words))
        for i in range(len(words)):
            word = words[i]
            if len(re.sub(r'[0-9a-zA-Z\-_\|\[\]\+\.\(\),\'"~ ]+', '', word)) > 0:
                continue
            if re.findall(r'\d+\.\d+\.\d+\.\d+', word):
                continue
            if word[0] == '-':
                continue
            if word == word[0] * len(word):
                continue
            if word.startswith('0x'):
                continue
            word = re.sub(r'^\'|\'$', '', word).strip()
            res.append(word)
        return res

    def parse_page(content):
        text = re.sub('\s*[\n0-9]*\n© [0-9]{4} [\w\s0-9\n]+© SANS Institute [0-9]{4}\n[a-f0-9]+\n.+@.+\n[0-9]+\n\w+ \w+\n.+\nlive\nLicensed To: \w+ \w+ <.+@.+> \w+ [0-9]+, [0-9]{4}\nLicensed To: \w+ \w+ <.+@.+> \w+ [0-9]+, [0-9]{4}\n', '', content)
        pg_num = (re.findall(r'\n\d+\n©\s', content) or [''])[0].replace('\n', '').replace('©', '').strip()
        words = parse_words(text)
        return {
            'page': pg_num,
            'words': words,
            'raw': content
        }

    def read_book(pdf_path):
        with fitz.open(pdf_path) as doc:
            pages = []
            first = False
            course_title = ""
            for i in range(doc.page_count):
                page = doc.load_page(i)
                title = _get_page_title(page)
                if not first:
                    if title:
                        first = True
                    else:
                        print(f'{i}: [NONE]')
                        continue
                text = page.get_text()
                if not course_title:
                    course_title = (re.findall(course_pattern, text) or [''])[0]
                    if not course_title:
                        continue
                el = parse_page(text)
                print(f'{i}: {el["page"]}: {title}')
                pages.append({'title': title, **el})
            course_code = course_title.split('|')[0].strip()
        return pages, course_code, course_title, str(len([p for p in pages if p['title']]))
    
    if not os.path.exists(source_file):
        print(f'File {source_file} does not exist')
        return
    print(f'Reading {source_file}')
    pages, course_code, course_title, page_count = read_book(source_file)
    print(f'{page_count} pages found')

    app_home = os.path.dirname(os.path.realpath(__file__))
    course_folder = os.path.join(app_home, 'courses', course_code)

    if not os.path.exists(course_folder):
        os.makedirs(course_folder)
        cont = "\def\coursecode{" + course_code + "}\n"
        cont += "\def\coursetitle{" + course_title + "}\n"
        cont += "\def\coursedate{}%" + datetime.now().strftime('%Y') + "}"
        cont += "\def\courseversion{I01_02}"
        with open(os.path.join(course_folder, 'data.tex'), 'w') as f:
            f.write(cont)
        print(f'Created course folder {course_folder}')

    if not os.path.exists(output_csv):
        os.makedirs(output_csv)

    csv_file_path = os.path.join(output_csv, f"{book_num}.csv")
    with open(csv_file_path, 'w') as csv_file:
        writer = csv.writer(csv_file)
        for page in pages:
            writer.writerow([page['page'], page['title'], *list(set(page['words']))])
    print(f'Wrote CSV file {book_num}.csv')

# Function to create LaTeX index
def create_index(args_course, output_pdf, course_code):
    MAX_PAGES = 10

    def make_big_dic(book, pages, bd=None):
        big_dic = {}
        if bd is not None:
            big_dic = bd
        for p in pages:
            for w in p[2:]:
                if w == p[0]:
                    continue
                if w not in big_dic:
                    big_dic[w] = {
                        'cnt': 1,
                        'books': {
                            book: {
                                p[0]: 1
                            }
                        }
                    }
                    continue
                big_dic[w]['cnt'] += 1
                if book not in big_dic[w]['books']:
                    big_dic[w]['books'][book] = {
                        p[0]: 1
                    }
                    continue
                if p[0] not in big_dic[w]['books'][book]:
                    big_dic[w]['books'][book][p[0]] = 1
                else:
                    big_dic[w]['books'][book][p[0]] += 1
        return big_dic

    def shrink_that_massive_dic(big_dic, min_cnt=1, max_cnt=10, max_len=30):
        res = {}
        for w in big_dic:
            if ' ' in w:
                continue
            if big_dic[w]['cnt'] < min_cnt:
                continue
            if len(w) > max_len:
                continue
            pg_cnt = sum([len(big_dic[w]['books'][b]) for b in big_dic[w]['books']])
            if pg_cnt < max_cnt:
                res[w] = big_dic[w]
        return res

    def read_all_csvs(course_path):
        big_dic = {}
        titles = []
        i = 1
        while os.path.exists(os.path.join(course_path, f'{i}.csv')):
            pages = []
            with open(os.path.join(course_path, f'{i}.csv')) as f:
                csv_reader = csv.reader(f, delimiter=',', quotechar='"')
                for row in csv_reader:
                    pages.append(row)

            titles.append([{'page': a[0], 'title': a[1]} for a in pages if len(a) > 1 and a[1]])
            big_dic = make_big_dic(i, pages, big_dic)
            i += 1
        return titles, big_dic

    def make_title_entries(titles):
        res = []
        for i in range(len(titles)):
            for title in titles[i]:
                res.append('\indexentry{1' + str(i) + 'A@\\textbf{Book ' + str(i + 1) + '}!' + title['page'] + '@' + title['title'] + '|book{' + str(i + 1) + '}}{' + title['page'] + '}')
        return res

    def make_index_entries(big_dic):
        res = []
        for w in big_dic:
            for b in big_dic[w]['books']:
                for p in big_dic[w]['books'][b]:
                    res.append('\indexentry{' + w.replace('_','\_').replace('"','\\"') + '|book{' + str(b) + '}}{' + str(p) + '}')
        return res

    app_home = os.path.dirname(os.path.realpath(__file__))
    course_path = os.path.join(app_home, 'courses', course_code)

    if not os.path.exists(course_path):
        print('Course does not exist')
        sys.exit(1)

    titles, books = read_all_csvs(course_path)
    books = shrink_that_massive_dic(books, min_cnt=1, max_cnt=20)
    title_entries = make_title_entries(titles)
    index_entries = make_index_entries(books)
    res = '\n'.join(title_entries) + '\n' + '\n'.join(index_entries)
    with open(os.path.join(course_path,'main.idx'),'w') as idx_file:
        idx_file.write(res)

    cwd = os.getcwd()
    os.chdir(course_path)
    os.system('makeindex main.idx -s ' + os.path.join(app_home,'resources','std.ist'))
    os.system('cp ' + os.path.join(app_home,'resources','main.tex') + ' main.tex')
    os.system('pdflatex -synctex=1 -interaction=nonstopmode main.tex')
    for f in ['main.aux','main.log','main.ilg','main.tex','main.ind','main.synctex.gz']:
        os.remove(f)
    os.chdir(cwd)
    os.rename(os.path.join(course_path, 'main.pdf'), output_pdf)

# Main function
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-p', '--password', help='Password for PDF file')
    parser.add_argument('-b', '--books', nargs='+', help='Book numbers', required=True)
    parser.add_argument('-s', '--source', nargs='+', help='Source PDF files', required=True)
    parser.add_argument('-c', '--course', help='Course code', required=True)
    parser.add_argument('-o1', '--output_csv', help='Output directory for CSV files', required=False, default=".")
    parser.add_argument('-o2', '--output_pdf', help='Output path/filename for finished PDF index', required=False, default="index.pdf")
    args = parser.parse_args()

    if args.password:
        for source_file in args.source:
            decrypt_pdf(args.password, source_file)

    for book_num, source_file in zip(args.books, args.source):
        pages, course_code, course_title, page_count = pdf_to_csv(book_num, source_file, args.course, args.output_csv)

    create_index(args.course, args.output_pdf, course_code)

if __name__ == '__main__':
    main()
