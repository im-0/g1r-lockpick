#!/bin/sh

[ "${TIME_IMPL}" = "" ] && TIME_IMPL=$( which time 2>/dev/null )
[ "${TIME_IMPL}" = "" ] && TIME_IMPL="time"

[ "${PY3_IMPL}" = "" ] && PY3_IMPL=$( which pypy3 2>/dev/null )
[ "${PY3_IMPL}" = "" ] && PY3_IMPL="python3"

TIMEOUT_CMD="timeout --kill-after=2s 10s"

set -x -e -u

CMD="${TIME_IMPL} ${TIMEOUT_CMD} ${PY3_IMPL} ./g1r-lockpick.py"

echo "**** Time implementation: ${TIME_IMPL}"
echo "**** Python 3 implementation: ${PY3_IMPL}"
echo

echo "!!!! New Camp, Cave Tavern Door Lock 02"
${CMD} <<EOF
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
