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
4
EOF
echo

echo "!!!! Synthetic, Solved 7 plates"
${CMD} <<EOF
4444444
EOF
echo

echo "!!!! Synthetic, Required connections on centered plates"
${CMD} <<'EOF'
1344
<<..
>>..
<><<
..>>

EOF
echo

echo "!!!! Synthetic, Solved by probe moving left"
${CMD} <<EOF
43
.<
EOF
echo

echo "!!!! Synthetic, Solved by probe moving right"
${CMD} <<EOF
45
.>
EOF
echo

#
# Lock from the game
#

echo "!!!! New Camp, Cave Tavern Door Lock 02"
${CMD} <<EOF
556277
s6
..<..>
<...><
b6
<.><..
>.....
s6
.<<..>
.<>.><











EOF
echo

echo "!!!! New Camp, Gorn Chest"
${CMD} <<EOF
457661
..><<.
...>..
s6
>....<
..<>>>
s6
<...>.
.<.>><







EOF
echo

echo "!!!! Old Camp, Skip Chest"
${CMD} <<EOF
141641
s3
..<.>.
<>>...
.>...<
s3
.<....
..<<<<
...>>.









EOF
echo

echo "New Camp, Tavern underwater chest #1"
${CMD} <<EOF
43725
p5..<.>
p4<..>>
p3<>>>.
p2>>.<.
p1><<..









EOF
echo

echo "New Camp, Tavern second floor door"
${CMD} <<EOF
73111
>><..
s5
..>.<
..<<>
..<..
b5
<><<<
s1

<><<<






EOF
echo

echo "!!!! Old Camp, Raven Chest"
${CMD} <<EOF
7647275
s4
...>...
...<>>.
s14
.>.....
......>
>.>....
<..>.>.

<.><<<>











EOF
echo

echo
echo "**** All tests passed!"
