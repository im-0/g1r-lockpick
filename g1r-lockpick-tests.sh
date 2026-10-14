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

#
# Synthetic tests
#

echo "!!!! Synthetic, Solved 1 plate"
${CMD} <<EOF
u
4
EOF
echo

echo "!!!! Synthetic, Solved 7 plates"
${CMD} <<EOF
u
4 4 4 4 4 4 4
EOF
echo

echo "!!!! Synthetic, Required connections on centered plates"
${CMD} <<'EOF'
u
1 3 4 4
< < . .
> > . .
s 1
< > < <
. . > >
EOF
echo

echo "!!!! Synthetic, Solved by probe moving left"
${CMD} <<EOF
u
4 3
. <
EOF
echo

echo "!!!! Synthetic, Solved by probe moving right"
${CMD} <<EOF
u
4 5
. >
EOF
echo

#
# Lock from the game
#

echo "!!!! New Camp, Cave Tavern Door Lock 02"
${CMD} <<EOF
u
5 5 6 2 7 7
> . . . . .
s 6
b 6
< . > < . .
s 6
. . < . . >
< . . . > <
. < < . . >
. < > . > <









EOF
echo

echo "!!!! New Camp, Gorn Chest"
${CMD} <<EOF
u
4 5 7 6 6 1
s 6
. . > < < .
. . . > . .
s 6
> . . . . <
. . < > > >
< . . . > .
. < . > > <






EOF
echo

echo "!!!! Old Camp, Skip Chest"
${CMD} <<EOF
u
1 4 1 6 4 1
s 3
. . < . > .
< > > . . .
. < . . . .
s 3
. . . < < .
. > . . . <

. . < < < <








EOF
echo

echo "!!!! Old Camp, Raven Chest"
${CMD} <<EOF
u
7 6 4 7 2 7 5
s 4
. > . . . . .
. . . > . . .
s 6
s 1
. . . < > > .
. . . . . . >
> . > . . . .
s 4
< . . > . > .

> . < > > > <








EOF
echo

echo
echo "**** All tests passed!"
