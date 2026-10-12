#!/bin/sh

[ "${TIME_IMPL}" = "" ] && TIME_IMPL=$( which time 2>/dev/null )
[ "${TIME_IMPL}" = "" ] && TIME_IMPL="time"

[ "${PY3_IMPL}" = "" ] && PY3_IMPL=$( which pypy3 2>/dev/null )
[ "${PY3_IMPL}" = "" ] && PY3_IMPL="python3"

set -e -u

echo "**** Time implementation: ${TIME_IMPL}"
echo "**** Python 3 implementation: ${PY3_IMPL}"
echo

echo "!!!! New Camp, Cave Tavern Door Lock 02"
${TIME_IMPL} ${PY3_IMPL} ./g1r-lockpick.py <<EOF
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

echo
echo "**** All tests passed!"
