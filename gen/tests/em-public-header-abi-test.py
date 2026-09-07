#!/usr/bin/env python3
import difflib
from pathlib import Path
import re
import sys


def tokens(filename):
    source = Path(filename).read_text()
    source = re.sub(r'/\*.*?\*/|//[^\n]*', '', source, flags=re.S)
    return re.findall(r'\w+|[^\s\w]', source)


def main():
    runtime, decoder = sys.argv[1:]
    expected, actual = tokens(runtime), tokens(decoder)
    if expected != actual:
        print('FAIL: EasyMesh runtime and decoder public headers differ', file=sys.stderr)
        print('\n'.join(difflib.unified_diff(expected, actual, runtime, decoder, n=3)), file=sys.stderr)
        return 1
    print('PASS: EasyMesh runtime and decoder public headers have identical C/C++ tokens')
    return 0


if __name__ == '__main__':
    sys.exit(main())
