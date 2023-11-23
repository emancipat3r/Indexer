#! /usr/bin/env python3
# Usage: python3 pdf_to_csv.py -b 1 -s /path/to/file.pdf [ -p password ]

import sys
import os
import re
import fitz
import argparse
import csv
from textblob import TextBlob
from datetime import datetime
import numpy as np
import cv2
from pytesseract import image_to_string

course_pattern = r'[A-Z]{3}[0-9]{3} \| [a-zA-Z, ]+\n'

top_bounds = [320,550,250,2300]
title_bounds = [382,500,307,1660]
title_left = [382,500,312,313]
title_sep = [382,500,1661,1668]

def _get_page_title(page):
    img = _get_page_image(page)
    boxes = _get_image_boxes(img[
        top_bounds[0]:top_bounds[1],
        top_bounds[2]:top_bounds[3]
    ])
    
    # Filter and check if there are two boxes
    boxes = [cnt for cnt in boxes if cnt[0] < 200 and cnt[2] > 500 and cnt[3] > 50]
    if not len(boxes):
        return None
    
    # Get cords for title bar
    title_box = _get_title_box(boxes)
    img = img[
        title_box[0]:title_box[1],
        title_box[2]:title_box[3]
    ]
    
    # Invert image
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
    #img_inv = cv2.bitwise_not(img_gray)
    return img_gray

def _get_image_boxes(img):
    ret,th1 = cv2.threshold(img,127,255,cv2.THRESH_BINARY)
    ret,th2 = cv2.threshold(th1,127,255,cv2.THRESH_BINARY_INV)
    kernel = np.ones((5,5),np.uint8)
    img_dialated = cv2.dilate(th2,kernel,iterations = 1)
    contours, heirarchy = cv2.findContours(img_dialated,cv2.RETR_TREE,cv2.CHAIN_APPROX_SIMPLE)
    contours=[cv2.boundingRect(cnt) for cnt in contours]
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
        if len(re.sub(r'[0-9a-zA-Z\-_\|\[\]\+\.\(\),\'"~ ]+','',word)) > 0:
            continue
        if re.findall(r'\d+\.\d+\.\d+\.\d+', word):
            continue
        if word[0] == '-':
            continue
        if word == word[0] * len(word):
            continue
        if word.startswith('0x'):
            continue
        word = re.sub(r'^\'|\'$','',word).strip()
        res.append(word)
    return res

def parse_page(content):
    text = re.sub('\s*[\n0-9]*\n© [0-9]{4} [\w\s0-9\n]+© SANS Institute [0-9]{4}\n[a-f0-9]+\n.+@.+\n[0-9]+\n\w+ \w+\n.+\nlive\nLicensed To: \w+ \w+ <.+@.+> \w+ [0-9]+, [0-9]{4}\nLicensed To: \w+ \w+ <.+@.+> \w+ [0-9]+, [0-9]{4}\n','', content)
    pg_num = (re.findall(r'\n\d+\n©\s', content) or [''])[0].replace('\n','').replace('©','').strip()
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
                    print('\r' + ' ' * 100, end='')
                    print(f'\r{str(i)}: [NONE]')
                    continue
            text = page.get_text()
            if not course_title:
                course_title = (re.findall(course_pattern, text) or [''])[0]
                if not course_title:
                    continue
            if not title:
                if 'tables of contents' in text.lower():
                    continue
                if 'about the course' in text.lower():
                    continue
                if 'course outline' in text.lower():
                    continue
                if 'course roadmap' in text.lower():
                    continue
                if 'please work on below exercise.' in text.lower():
                    continue
            el = parse_page(text)
            print('\r' + ' ' * 100, end='')
            print(f'\r{str(i)}: {el["page"]}: {title}')
            pages.append({'title': title, **el})
        course_code = course_title.split('|')[0].strip()
    return pages, course_code, course_title, str(len([p for p in pages if p['title']]))

def main():
    #global common
    # Get App home
    app_home = os.path.dirname(os.path.realpath(__file__))

    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('-b', '--book', help='Book number', required=True)
    parser.add_argument('-s', '--source', help='Source PDF file', required=True)
    parser.add_argument('-p', '--password', help='Password for PDF file')
    args = parser.parse_args()

    if not os.path.exists(args.source):
        print(f'File {args.source} does not exist')
        sys.exit(1)
    
    # Read PDF
    print(f'Reading {args.source}')
    pages, course_code, course_title, page_count = read_book(args.source)
    print(f'\n{page_count} pages found')

    # Init course folder if not exists
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
    
    with open(os.path.join(course_folder, f"{args.book}.csv") ,'w') as csv_file:
        writer = csv.writer(csv_file)
        for page in pages:
            writer.writerow([page['page'], page['title'], *list(set(page['words']))])
    print(f'Wrote CSV file {args.book}.csv')

if __name__ == '__main__':
    main()