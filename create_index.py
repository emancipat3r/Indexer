import os
import sys
import csv

# Usage: python3 create_index.py CODE

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
            print(title)
            res.append('\indexentry{1' + str(i) + 'A@\\textbf{Book ' + str(i + 1) + '}!' + title['page'] + '@' + title['title'] + '|book{' + str(i + 1) + '}}{' + title['page'] + '}')
    return res

def make_index_entries(big_dic):
    res = []
    for w in big_dic:
        for b in big_dic[w]['books']:
            for p in big_dic[w]['books'][b]:
                res.append('\indexentry{' + w.replace('_','\_').replace('"','\\"') + '|book{' + str(b) + '}}{' + str(p) + '}')
    return res

def main():
    # Get App home
    app_home = os.path.dirname(os.path.realpath(__file__))

    if len(sys.argv) < 2:
        print('Please provide a course code')
        for code in os.listdir(os.path.join(app_home, 'courses')):
            if os.path.isdir(os.path.join(app_home, 'courses', code)):
                print(code)
        sys.exit(1)
    course_code = sys.argv[1]
    course_path = os.path.join(app_home, 'courses', course_code)

    if not os.path.exists(course_path):
        print('Course does not exist')
        sys.exit(1)
    
    # Read all CSVs
    titles, books = read_all_csvs(course_path)
    print(f'Found {len(books)} books')

    # Filter out words that appear in more than 10 pages
    books = shrink_that_massive_dic(books, min_cnt=1, max_cnt=20)

    # Generate title entries
    title_entries = make_title_entries(titles)

    # Generate index entries
    index_entries = make_index_entries(books)

    # Write to file
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
    os.rename(os.path.join(course_path,'main.pdf'), os.path.join(cwd,course_code + '-index.pdf'))

if __name__ == '__main__':
    main()