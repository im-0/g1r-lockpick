#!/bin/sh

set -e -u

# New Camp, Cave Tavern Door Lock 02
/usr/bin/time pypy3 ./g1r-lockpick.py <<EOF
u
5 5 6 2 7 7
s
0 0 < 0 0 >
0 < > 0 > <
> 0 0 0 0 0
b
s
0 < < 0 0 >
< 0 0 0 > <
b
> 0 < > 0 0




























EOF

echo
echo "All tests passed!"
