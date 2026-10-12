#!/bin/sh

set -e -u

# New Camp, Cave Tavern Door Lock 02
/usr/bin/time ./g1r-lockpick.py <<EOF
u
5 5 6 2 7 7
< 0 0 0 0 0
0 < < 0 0 >
0 < > 0 > <
< 0 > < 0 0
> 0 0 0 < >
0 0 > 0 0 <











EOF

echo
echo "All tests passed!"
