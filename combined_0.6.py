#!/usr/bin/env python3

# ---------------------------------------------------------------------------------------------
#
# DESCRIPTION:      Creates a PDF index of given PDF input files. Also
#                   removes password-protection from PDFs. 
#
# REQUIREMENTS:     [1a] [ARCH-BASED] Tesseract - 'tesseract'
#                   [1b] [DEBIAN-BASED] Tesseract - 'tesseract-ocr'
#                   [2a] [ARCH-BASED] LaTeX - 'texlive-basic', 'texlive-binextra'
#                   [2b] [DEBIAN-BASED] LaTeX - 'makeindex', 'pdflatex'
#
# SETUP:            python3 -m venv myenv
#                   source myvenv/bin/activate
#                   pip3 install -r requirements.txt
#
# BASIC USAGE:      # Create index from source PDFs
#                   python3 combined.py -b 1 2 n -s <file1> <file2> <filen> -o1 CSV -o2 index.pdf
#                   
#                   # Unlock PDF files
#                   python3 combined.py -s <file1> <file2> <filen> -p <password_file>
#
# ---------------------------------------------------------------------------------------------

import os
import sys
import csv
import argparse
import re
from datetime import datetime
import subprocess
from time import sleep
import fitz
import nltk
from textblob import TextBlob
import numpy as np
import cv2
from pytesseract import image_to_string
from tqdm import tqdm

# Function to unlock PDFs
def unlock_pdf(password, source_file):
    try:
        with fitz.open(source_file) as doc:
            doc.authenticate(password)
            unlocked_pdf_path = source_file[:-4] + "_unlocked.pdf"
            doc.save(unlocked_pdf_path)
        return True, unlocked_pdf_path
    except Exception as e:
        print(f"[ERROR] An error occured while unlocking the PDF: {e}")
        return False, None

# Class to convert PDF to CSV
class PDFProcessor:
    course_pattern = r'[A-Z]{3}[0-9]{3} \| [a-zA-Z, ]+\n'
    top_bounds = [320, 550, 250, 2300]
    title_bounds = [382, 500, 307, 1660]
    title_left = [382, 500, 312, 313]
    title_sep = [382, 500, 1661, 1668]

    # Initialize class with specified OCR DPI and bounding box
    def __init__(self, top_bounds, ocr_dpi, stopwords):
        self.top_bounds = top_bounds
        self.ocr_dpi = ocr_dpi
        self.stopwords = stopwords

    # Extract title of a page using OCR
    def get_page_title(self, page):
        img = self.get_page_image(page)
        boxes = self.get_image_boxes(img[
            self.top_bounds[0]:self.top_bounds[1],
            self.top_bounds[2]:self.top_bounds[3]
        ])
        boxes = [count for count in boxes if count[0] < 200 and count[2] > 500 and count[3] > 50]
        if not len(boxes):
            return None
        title_box = self.get_title_box(boxes)
        img = img[
            title_box[0]:title_box[1],
            title_box[2]:title_box[3]
        ]
        img = cv2.bitwise_not(img)
        raw = image_to_string(img, lang='eng')
        title = ' '.join([element for element in raw.replace('\x0c','').split('\n') if element.strip()])
        if 'table of contents' in title.lower():
            return None
        if 'about the course' in title.lower():
            return None
        if 'course outline' in title.lower():
            return None
        if title.lower().startswith('welcome to '):
            return None
        if ' ' * len(title) == title:
            return None
        return title
       
    # Convert PDF page to image
    def get_page_image(self, page):
        img_bytes = np.frombuffer(page.get_pixmap(dpi=self.ocr_dpi).pil_tobytes("JPEG"), dtype=np.uint8)
        img = cv2.imdecode(img_bytes, cv2.IMREAD_COLOR)
        img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return img_gray

    # Get bounding boxes for image content
    def get_image_boxes(self, img):
        ret, th1 = cv2.threshold(img, 127, 255, cv2.THRESH_BINARY)
        ret, th2 = cv2.threshold(th1, 127, 255, cv2.THRESH_BINARY_INV)
        kernel = np.ones((5, 5), np.uint8)
        img_dilated = cv2.dilate(th2, kernel, iterations=1)
        contours, _ = cv2.findContours(img_dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        contours = [cv2.boundingRect(cnt) for cnt in contours]
        return contours

    # Determine which bounding box likely contains the title
    def get_title_box(self, boxes):
        title_box = sorted(boxes, key=lambda x: x[2], reverse=True)[0]
        return [
            self.top_bounds[0] + title_box[1],
            self.top_bounds[0] + title_box[1] + title_box[3],
            self.top_bounds[2] + title_box[0],
            self.top_bounds[2] + title_box[0] + title_box[2]
        ]

    # Extract meaningful words from a given text
    def parse_words(self, text):
        words_to_filter = []
        words = [a.lower().strip() for a in list(TextBlob(text).noun_phrases) if len(a) > 1]
        words += [a.lower().strip() for a in TextBlob(text).words if len(a) > 1]
        words = list(set(words))
        
        for i in range(len(words)):
            word = words[i]
            if word in self.stopwords:
                continue
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
            words_to_filter.append(word)
        
        return words_to_filter

    # Parse a single page of a PDF
    def parse_page(self, content):
        text = re.sub('\s*[\n0-9]*\n© [0-9]{4} [\w\s0-9\n]+© SANS Institute [0-9]{4}\n[a-f0-9]+\n.+@.+\n[0-9]+\n\w+ \w+\n.+\nlive\nLicensed To: \w+ \w+ <.+@.+> \w+ [0-9]+, [0-9]{4}\nLicensed To: \w+ \w+ <.+@.+> \w+ [0-9]+, [0-9]{4}\n', '', content)
        pg_num = (re.findall(r'\n\d+\n©\s', content) or [''])[0].replace('\n', '').replace('©', '').strip()
        words = self.parse_words(text)
        return {
            'page': pg_num,
            'words': words,
            'raw': content
        }

    # Process an entire PDF file and read its contents
    def read_book(self, pdf_path, quiet=False):
        if not os.path.exists(pdf_path):
            print(f"[ERROR] File {pdf_path} does not exist.")
            return
        with fitz.open(pdf_path) as doc:
            pages = []
            first = False
            course_title = ""
            for i in range(doc.page_count):
                page = doc.load_page(i)
                title = self.get_page_title(page)
                if not first:
                    if title:
                        first = True
                    else:
                        if not quiet:
                            print(f'{i}: [NONE]')
                        continue
                text = page.get_text()
                if not course_title:
                    course_title = (re.findall(self.course_pattern, text) or [''])[0]
                    if not course_title:
                        continue
                element = self.parse_page(text)
                if not quiet:
                    print(f'{i}: {element["page"]}: {title}')
                pages.append({'title': title, **element})
            course_code = course_title.split('|')[0].strip()
        return pages, course_code, course_title, (len([p for p in pages if p['title']]))


# Class to create LaTeX index
class IndexCreator:
    # Initialize class with the course code, output PDF file, and maximum pages
    def __init__(self, course_code, output_pdf, MAX_PAGES):
        self.course_code = course_code
        self.output_pdf = output_pdf
        self.MAX_PAGES = int(MAX_PAGES)

    # Build a dictionary of words from the provided PDF(s) and their parsed pages
    def build_word_dictionary(self, book, pages, wd=None):
        word_dictionary = {}
        if wd is not None:
            word_dictionary = wd
        for p in pages:
            for w in p[2:]:
                if w is not None:
                    if w == p[0]:
                        continue
                    if w not in word_dictionary:
                        word_dictionary[w] = {
                            'count': 1,
                            'books': {
                                book: {
                                    p[0]: 1
                                }
                            }
                        }
                    continue
                word_dictionary[w]['count'] += 1
                if book not in word_dictionary[w]['books']:
                    word_dictionary[w]['books'][book] = {
                        p[0]: 1
                    }
                    continue
                if p[0] not in word_dictionary[w]['books'][book]:
                    word_dictionary[w]['books'][book][p[0]] = 1
                else:
                    word_dictionary[w]['books'][book][p[0]] += 1
        return word_dictionary

    # Filter the word dictionary based on given parameters
    def filter_word_dictionary(self, word_dictionary, min_count=1, max_count=10, max_length=30):
        res = {}
        for w in word_dictionary:
            if ' ' in w:
                continue
            if word_dictionary[w]['count'] < min_count:
                continue
            if len(w) > max_length:
                continue
            page_count = sum([len(word_dictionary[w]['books'][b]) for b in word_dictionary[w]['books']])
            if page_count < max_count:
                res[w] = word_dictionary[w]
        return res

    # Read all generated CSV files from the course path
    def read_all_csvs(self, course_path):
        word_dictionary = {}
        titles = []
        i = 1
        while os.path.exists(os.path.join(course_path, f'{i}.csv')):
            pages = []
            try:
                with open(os.path.join(course_path, f'{i}.csv')) as f:
                    csv_reader = csv.reader(f, delimiter=',', quotechar='"')
                    for row in csv_reader:
                        pages.append(row)
            except FileNotFoundError:
                print(f"[ERROR] CSV file {i}.csv not found in {course_path}")
            except PermissionError:
                print(f"[ERROR] Permission denied when trying to read {i}.csv")
            except Exception as e:
                print(f"[ERROR] An error occurred while reading the CSV file: {e}")

            titles.append([{'page': a[0], 'title': a[1]} for a in pages if len(a) > 1 and a[1]])
            word_dictionary = self.build_word_dictionary(i, pages, word_dictionary)
            i += 1
        return titles, word_dictionary

    # Create LaTeX index title entries
    def make_title_entries(self, titles):
        res = []
        for i in range(len(titles)):
            for title in titles[i]:
                res.append('\indexentry{1' + str(i) + 'A@\\textbf{Book ' + str(i + 1) + '}!' + title['page'] + '@' + title['title'] + '|book{' + str(i + 1) + '}}{' + title['page'] + '}')
        return res

    # Create LaTeX index listing entries
    def make_index_entries(self, word_dictionary):
        res = []
        for w in word_dictionary:
            for b in word_dictionary[w]['books']:
                for p in word_dictionary[w]['books'][b]:
                    res.append('\indexentry{' + w.replace('_','\_').replace('"','\\"') + '|book{' + str(b) + '}}{' + str(p) + '}')
        return res

    # Create LaTeX index
    def create(self):
        course_path = os.path.join('courses', self.course_code)

        # Create the 'courses' directory if it doesn't exist
        if not os.path.exists('courses'):
            os.makedirs('courses')

        # Create the course-specific directory if it doesn't exist
        if not os.path.exists(course_path):
            os.makedirs(course_path)

        # Check if the course path exists
        if not os.path.exists(course_path):
            print('Course does not exist')
            sys.exit(1)

        # Read all CSVs
        try:
            titles, books = self.read_all_csvs(course_path)
        except Exception as e:
            print(f"An error occurred while reading CSV files: {e}")
            sys.exit(1)
            
        # Filter word dictionary
        try:
            books = self.filter_word_dictionary(books, min_count=1, max_count=self.MAX_PAGES)
        except Exception as e:
            print(f"An error occurred while filtering the word dictionary: {e}")
            sys.exit(1)

        # Make title and index entries
        try:
            title_entries = self.make_title_entries(titles)
            index_entries = self.make_index_entries(books)
        except Exception as e:
            print(f"An error occurred while making title or index entries: {e}")
            sys.exit(1)

        res = '\n'.join(title_entries) + '\n' + '\n'.join(index_entries)
        
        # Write to the main.idx file
        try:
            with open(os.path.join(course_path, 'main.idx'), 'w') as idx_file:
                idx_file.write(res)
        except IOError as e:
            print(f"An error occurred while writing to the main.idx file: {e}")
            sys.exit(1)

        # Run shell commands for LaTeX and PDF creation
        try:
            subprocess.run(['makeindex', 'main.idx', '-s', 'std.ist'], check=True)
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] An error occurred while running 'makeindex': {e}")
            sys.exit(1)

        try:
            subprocess.run(['cp', 'main.tex', 'main.tex'], check=True)
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] An error occurred while running 'cp': {e}")
            sys.exit(1)

        try:
            subprocess.run(['pdflatex', '-synctex=1', '-interaction=nonstopmode', 'main.tex'], check=True)
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] An error occurred while running LaTeX commands: {e}")
            sys.exit(1)

        # Remove temporary files
        try:
            for f in ['main.aux', 'main.log', 'main.ilg', 'main.tex', 'main.ind', 'main.synctex.gz']:
                os.remove(os.path.join(course_path, f))
        except FileNotFoundError as e:
            print(f"An error occurred while deleting temporary files: {e}")

        # Move the PDF
        try:
            os.rename(os.path.join(course_path, 'main.pdf'), self.output_pdf)
        except OSError as e:
            print(f"An error occurred while renaming/moving the file: {e}")

# Main function to handle CLI arguments and execute the script
def main():
    def parse_cli_args():
        # CLI arguments
        parser = argparse.ArgumentParser()
        parser.add_argument('-p', '--password', help='Password for PDF file')
        parser.add_argument('-b', '--books', nargs='+', help='Book number(s)', required=False)
        parser.add_argument('-s', '--source', nargs='+', help='Source PDF files', required=True)
        parser.add_argument('-c', '--course', help='Course code', required=False)
        parser.add_argument('-o1', '--output_csv', help='Output directory for CSV files', required=False, default=".")
        parser.add_argument('-o2', '--output_pdf', help='Output path/filename for finished PDF index', required=False, default="index.pdf")
        parser.add_argument('-f', '--freq_limit', type=int, help='Set limit for occurances of words', required=False, default=10)
        parser.add_argument('--stopwords', type=str, help='Path to the stopword text file', required=False)
        return parser.parse_args()

    def read_stopwords(stopwords_file):
        # Read stopwords from stopword file
        stopwords = []
        if os.path.exists(stopwords_file):
            with open(stopwords_file, 'r') as f:
                stopwords = f.read().splitlines()
        else:
            print(f"[WARNING] Stopword file {args.stopwords} does not exist. Ignoring.")
        return stopwords

    def unlock_pdfs(args):
        # Unlock PDFs if password is provided
        for source_file in args.source:
            success, unlock_pdf_path = unlock_pdf(args.password, source_file)
            if not success:
                print(f"[ERROR] Skipping processing for {source_file} due to unlocking failure.")


    def process_pdfs(args, stopwords):
        # Process each PDF file
        for book_num, source_file in zip(args.books, args.source):
            # Check if the source file exists
            if not os.path.exists(source_file):
                print(f'[ERROR] File {source_file} does not exist')
                continue
            # Initialize PDFProcessor with specified top bounds, OCR DPI, and stopwords
            pdf_processor = PDFProcessor(top_bounds=[320, 550, 250, 2300], ocr_dpi=300, stopwords=stopwords)
            # Open PDF file using fitz/pymupdf library
            with fitz.open(source_file) as doc:
                print(f'Reading {source_file}')
                
                # Process the entire PDF and get details like course_code, course_title, etc.
                pages, course_code, course_title, page_count = pdf_processor.read_book(source_file)
                print(f'{page_count} pages found')
                
                # Check if specified output directory exists; if not, create it
                output_csv = args.output_csv
                if not os.path.exists(output_csv):
                    try:
                        os.makedirs(output_csv)
                    except OSError as e:
                        print(f"[ERROR] An error occurred while creating the directory: {e}")
                        sys.exit(1)
                
                # Generate the CSV file path
                csv_file_path = os.path.join(output_csv, f"{book_num}.csv")
                
                # Write the parsed data to a CSV file
                try:
                    with open(csv_file_path, 'w') as csv_file:
                        writer = csv.writer(csv_file)
                        for page in pages:
                            writer.writerow([page['page'], page['title'], *list(set(page['words']))])
                    print(f'Wrote CSV file {book_num}.csv')
                except FileNotFoundError:
                    print(f"[ERROR] Could not find the directory to write the CSV file: {csv_file_path}")
                except PermissionError:
                    print(f"[ERROR] Permission denied when trying to write to {csv_file_path}")
                except Exception as e:
                    print(f"[ERROR] An error occurred while writing the CSV file: {e}")

    def create_index(args):
        # Initialize IndexCreator
        index_creator = IndexCreator(args.course, args.output_pdf, int(args.freq_limit))
        index_creator.create()

    try:
        args = parse_cli_args()
        # Read stopwords from stopword file
        stopwords = read_stopwords(args.stopwords) if args.stopwords else []
        # Validate book and source PDF counts
        if args.books and len(args.books) != len(args.source):
            print("[ERROR] The number of books must match the number of source PDF files")
            sys.exit(1)
        # Download NLTK data if necessary
        if args.output_pdf:
            try:
                nltk.data.find('corpora/brown')
            except LookupError:
                nltk.download('brown')
        if args.password:
            unlock_pdfs(args)
        process_pdfs(args, stopwords)
        create_index(args)
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == '__main__':
    main()
