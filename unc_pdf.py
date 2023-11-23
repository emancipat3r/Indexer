#!/usr/bin/env python3
# Usage: python3 unc_pdf.py <password> <path/to/file.pdf>
# Description: Decrypts a PDF.

import os, sys
import fitz
import argparse

def main():
    # Parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('password', help='Password for PDF file')
    parser.add_argument('source', help='Source PDF file')
    args = parser.parse_args()

    # Check if file exists
    if not os.path.exists(args.source):
        print(f'File {args.source} does not exist')
        sys.exit(1)
    
    # Check if password is provided
    if not args.password:
        print('Password is required')
        sys.exit(1)
    
    # Decrypt PDF if needed
    unencrypted_path = args.source[:-4] + '_nopass.pdf'
    if os.path.exists(unencrypted_path):
        print('Unencrypted file already exists')
        sys.exit(1)
    
    with fitz.open(args.source) as doc:
        # Check if file is encrypted
        if not doc.is_encrypted:
            print('File is not encrypted')
            sys.exit(1)
        
        # Decrypt PDF
        doc.authenticate(args.password)

        # Check if password is correct
        if doc.is_encrypted:
            print('Incorrect password')
            sys.exit(1)
        
        # Save decrypted PDF
        doc.save(unencrypted_path)
    
    # Move unencrypted file to source file
    os.rename(unencrypted_path, args.source)

if __name__ == '__main__':
    main()
        