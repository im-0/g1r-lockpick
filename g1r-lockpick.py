#!/usr/bin/python3

import atexit
import readline
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from heapq import heappop, heappush
from os import path
from pathlib import Path
from sys import exit, stderr, stdin, stdout
from time import monotonic_ns
from typing import TypeVar, final

_READLINE_HISTORY_FILE = path.join(Path.home(), ".g1r-lockpick.history")
_READLINE_HISTORY_LEN = 1000

# 3 bits per plate packed into 32bit integers.
_PLATE_BITS = 3
_PLATE_MASK = (0b1 << _PLATE_BITS) - 1
_MAX_PLATES = 7
_LOCK_MASK = (0b1 << (_PLATE_BITS * _MAX_PLATES)) - 1

_PLATE_MIN = 1
_PLATE_SOLVED = 4
_PLATE_MAX = 7

_U32_MAX = (0b1 << 32) - 1


def _main():
    _init_readline()

    last_ret_code = 0
    try:
        while True:
            lock, n_plates = _input(
                (
                    f"Enter pin positions [{_PLATE_MIN}..{_PLATE_MAX}] from bottom left to top right",
                ),
                _parse_lock_plates,
            )

            last_ret_code = 1
            try:
                _unlock(lock, n_plates)
                last_ret_code = 0
            except EOFError:
                print()

            print()
    except (EOFError, KeyboardInterrupt):
        print()
    exit(last_ret_code)


def _init_readline():
    if not (stdin.isatty() and stdout.isatty()):
        return

    try:
        try:
            readline.read_history_file(_READLINE_HISTORY_FILE)
        except OSError:
            pass

        readline.set_history_length(_READLINE_HISTORY_LEN)
        _ = atexit.register(readline.write_history_file, _READLINE_HISTORY_FILE)
    except Exception as e:  # noqa: BLE001
        print(f"readline initialization failed: {e}", file=stderr)


def _parse_lock_plates(plates: str) -> tuple[int, int]:
    n_plates = len(plates)
    if n_plates == 0:
        raise _Err("No lock plates")
    if n_plates > _MAX_PLATES:
        raise _Err(f"Too many plates: got {n_plates} but maximum is {_MAX_PLATES}")

    lock = 0
    for plate_i, plate_pos in enumerate(plates):
        plate_pos = int(plate_pos)
        if plate_pos < _PLATE_MIN:
            raise _Err(
                f"Value of plate #{plate_i + 1} is wrong: got {plate_pos} < {_PLATE_MIN}"
            )
        if plate_pos > _PLATE_MAX:
            raise _Err(
                f"Value of plate #{plate_i + 1} is wrong: got {plate_pos} > {_PLATE_MAX}"
            )

        lock = _lock_set(lock, plate_i, plate_pos)

    return lock, n_plates


def _unlock(lock_initial: int, n_plates: int):
    lock_solved = 0
    for _ in range(n_plates):
        lock_solved <<= _PLATE_BITS
        lock_solved |= _PLATE_SOLVED

    lock, interlocks = _probe_interlocks(lock_initial, lock_solved, n_plates)

    restart = True
    solution = None
    while restart:
        print("Current lock state:")
        print()
        _lock_print(lock, n_plates)

        if solution is None:
            print("Solving...")
            time_passed = monotonic_ns()
            solution = _bfs(lock, lock_solved, interlocks, n_plates)
            time_passed = monotonic_ns() - time_passed
            print(f"Time passed: {time_passed / 1_000_000_000:.03f}s ({time_passed}ns)")
            print()

        restart = False
        for step_i, (lock, plate_i, plate_off) in enumerate(solution):
            _print_plate_move(lock, n_plates, plate_i, plate_off)

            step_i += 1
            restart = _input(
                (
                    f"Press Enter after applying step {step_i}/{len(solution)}",
                    "or write `r` to restart from the initial state",
                ),
                _unlock_parse_cmd,
            )
            if restart:
                if lock != lock_initial:
                    lock = lock_initial
                    solution = None
                break

    if solution == []:
        print("Already solved!")
    elif solution is not None:
        print(f"Should be solved after {len(solution)} steps!")


def _unlock_parse_cmd(cmd: str) -> bool:
    if cmd == "r":
        return True
    if cmd == "":
        return False
    raise _Err(f'Unknown command: "{cmd}"')


def _probe_interlocks(
    lock_initial: int, lock_solved: int, n_plates: int
) -> tuple[int, list[int]]:
    lock = lock_initial
    plate_i = 0
    interlocks = _interlocks_new(n_plates)
    unprobed = _bits_from_iter(range(n_plates))

    while lock != lock_solved:
        solution = _dijkstra_probe(lock, plate_i, interlocks, n_plates, unprobed)
        if not solution:
            break

        for step_i, (lock, plate_i, plate_off) in enumerate(solution[:-1]):
            _print_plate_move(lock, n_plates, plate_i, plate_off)

            step_i += 1
            _ = _input(
                (
                    f"Press Enter after applying correcting step {step_i}/{len(solution) - 1}",
                ),
            )

        lock, plate_i, plate_off = solution[-1]
        dir = plate_off // abs(plate_off)
        _print_plate_move(lock, n_plates, plate_i, dir)

        lock, unprobed = _input(
            (
                "Write plate shifts [<, ., >] from bottom left to top right",
                f"or `p <PLATE [1..{n_plates}]> [<, ., >] ...` to set connections manually",
                f"or `s <STUCK PLATE [1..{n_plates}]> ...` if stuck",
                f"or `b <STUCK PLATE [1..{n_plates}]> ...` if lockpick broke",
                "or `r` to continue from the initial state",
            ),
            lambda cmd, lock=lock, lock_initial=lock_initial, unprobed=unprobed, plate_i=plate_i, dir=dir: (
                _probe_interlocks_parse_cmd(
                    cmd,
                    lock,
                    lock_initial,
                    unprobed,
                    interlocks,
                    n_plates,
                    plate_i,
                    dir,
                )
            ),
        )

    return lock, interlocks


def _print_plate_move(lock: int, n_plates: int, plate_i: int, plate_off: int):
    if abs(plate_off) == 1:
        times = "1 time"
    else:
        times = f"{abs(plate_off)} times"
    if plate_off > 0:
        _lock_print(lock, n_plates, {plate_i: f"<- move left {times}"})
    else:
        _lock_print(lock, n_plates, {plate_i: f"-> move right {times}"})


def _dijkstra_probe(
    lock_initial: int,
    plate_i_initial: int,
    interlocks: list[int],
    n_plates: int,
    unprobed_initial: int,
) -> list[tuple[int, int, int]]:
    @dataclass(order=True)
    class Queued:
        prio: int
        lock: int = field(compare=False)
        plate_i: int = field(compare=False)
        unprobed: int = field(compare=False)

    dist = {(lock_initial, plate_i_initial, unprobed_initial): 0}
    queue = [
        Queued(
            prio=0,
            lock=lock_initial,
            plate_i=plate_i_initial,
            unprobed=unprobed_initial,
        )
    ]
    prev: dict[tuple[int, int, int], tuple[int, int, int, int]] = {}

    while queue:
        cur_node = heappop(queue)

        if (cur_node.unprobed != unprobed_initial) or (cur_node.unprobed == 0):
            lock, plate_i, unprobed = cur_node.lock, cur_node.plate_i, cur_node.unprobed

            solution: list[tuple[int, int, int]] = []
            while dist[(lock, plate_i, unprobed)]:
                lock, prev_plate_i, unprobed, plate_off = prev[
                    (lock, plate_i, unprobed)
                ]
                solution.append((lock, plate_i, plate_off))
                plate_i = prev_plate_i
            solution.reverse()
            return solution

        moves: list[tuple[int, int, int]] = []
        _bfs_populate_moves(cur_node.lock, interlocks, n_plates, moves)
        cur_dist = dist[(cur_node.lock, cur_node.plate_i, cur_node.unprobed)]
        for lock, plate_i, plate_off in moves:
            move_dist = cur_dist
            # 1. Prefer less switches between the game and the solver.
            move_dist += 10000
            # 2. Prefer plates further from center.
            move_dist += 1000 * (
                _PLATE_SOLVED
                - _PLATE_MIN
                - abs(_PLATE_SOLVED - _lock_get(cur_node.lock, plate_i))
            )
            # 3. Prefer shorter plate moves.
            move_dist += 100 * abs(plate_off)
            # 4. Prefer moves towards center.
            move_dist += 10 * abs(_PLATE_SOLVED - _lock_get(lock, plate_i))
            # 5. Prefer plates that are closer together.
            move_dist += abs(plate_i - cur_node.plate_i)

            unprobed = _bits_unset(cur_node.unprobed, plate_i)
            old_move_dist = dist.get((lock, plate_i, unprobed))
            if (old_move_dist is None) or (move_dist < old_move_dist):
                prev[(lock, plate_i, unprobed)] = (
                    cur_node.lock,
                    cur_node.plate_i,
                    cur_node.unprobed,
                    plate_off,
                )
                dist[(lock, plate_i, unprobed)] = move_dist
                heappush(
                    queue,
                    Queued(
                        prio=move_dist, lock=lock, plate_i=plate_i, unprobed=unprobed
                    ),
                )

    assert False, "Logic error: probe Dijkstra failed"


def _probe_interlocks_parse_cmd(
    cmd: str,
    lock: int,
    lock_initial: int,
    unprobed: int,
    interlocks: list[int],
    n_plates: int,
    plate_i: int,
    dir: int,
) -> tuple[int, int]:
    if cmd == "r":
        return lock_initial, unprobed
    elif (len(cmd) > 2) and (cmd[0] == "p"):
        set_plate = int(cmd[1])
        if (set_plate < 1) or (set_plate > n_plates):
            raise _Err(
                f"Wrong number of plate to set: got {set_plate}, must be [1..{n_plates}]"
            )
        set_plate -= 1

        for shift_i, shift_dir in _probe_interlocks_parse_shifts(cmd[2:], n_plates):
            _interlocks_set(interlocks, n_plates, set_plate, shift_i, -shift_dir)

        unprobed = _bits_unset(unprobed, set_plate)
    elif (len(cmd) > 1) and (cmd[0] in ("s", "b")):
        for stuck_plate in cmd[1:]:
            stuck_plate = int(stuck_plate)
            if stuck_plate < 1:
                raise _Err(f"Index of stuck plate is wrong: got {stuck_plate} < 1")
            if stuck_plate > n_plates:
                raise _Err(
                    f"Index of stuck plate is wrong: got {stuck_plate} > {n_plates}"
                )
            stuck_plate -= 1

            stuck_plate_pos = _lock_get(lock, stuck_plate)
            if stuck_plate_pos == _PLATE_MIN:
                # Plate tried to move right.
                stuck_plate_dir = -1
            elif stuck_plate_pos == _PLATE_MAX:
                # Plate tried to move left.
                stuck_plate_dir = 1
            else:
                raise _Err(
                    f"Plate #{stuck_plate + 1} cannot be stuck: pin is not in edge position"
                )

            _interlocks_set(
                interlocks,
                n_plates,
                plate_i,
                stuck_plate,
                stuck_plate_dir * dir,
            )

        if cmd[0] == "b":
            lock = lock_initial
    elif len(cmd) == n_plates:
        for shift_i, shift_dir in _probe_interlocks_parse_shifts(cmd, n_plates):
            plate_pos = _lock_get(lock, shift_i) + shift_dir
            if plate_pos < _PLATE_MIN:
                raise _Err(
                    f"Plate #{shift_i + 1} cannot move in this direction, already at the left edge"
                )
            if plate_pos > _PLATE_MAX:
                raise _Err(
                    f"Plate #{shift_i + 1} cannot move in this direction, already at the right edge"
                )

            if shift_i == plate_i:
                if shift_dir != dir:
                    raise _Err(f"Plate #{plate_i + 1} moved in unexpected direction")
                # Diagonal already set to 1s.
            else:
                _interlocks_set(interlocks, n_plates, plate_i, shift_i, shift_dir * dir)

            # Adjust current position.
            lock = _lock_set(lock, shift_i, plate_pos)

        unprobed = _bits_unset(unprobed, plate_i)
    else:
        raise _Err("Wrong number of plates")

    _interlocks_print(interlocks, n_plates, unprobed)
    return lock, unprobed


def _probe_interlocks_parse_shifts(
    shifts: str, n_plates: int
) -> Iterable[tuple[int, int]]:
    if len(shifts) != n_plates:
        raise _Err(f"Wrong number of plates: got {len(shifts)}, expected {n_plates}")

    for shift_i, shift in enumerate(shifts):
        if shift == "<":
            shift_dir = 1
        elif shift == ".":
            shift_dir = 0
        elif shift == ">":
            shift_dir = -1
        else:
            raise _Err(f'Unknown change direction of plate #{shift_i + 1}: "{shift}"')

        yield shift_i, shift_dir


def _bfs(
    lock_start: int,
    lock_solved: int,
    interlocks: list[int],
    n_plates: int,
) -> list[tuple[int, int, int]]:
    n_nodes = 0b1 << (n_plates * _PLATE_BITS)
    dist = [_U32_MAX] * n_nodes

    cur_nodes = [lock_start]
    next_nodes = []
    dist[lock_start] = 0
    next_dist = 1
    moves: list[tuple[int, int, int]] = []

    while cur_nodes:
        while cur_nodes:
            cur_node = cur_nodes.pop()
            if cur_node == lock_solved:
                return _bfs_extract_solution(
                    cur_node,
                    interlocks,
                    n_plates,
                    dist,
                )

            _bfs_populate_moves(cur_node, interlocks, n_plates, moves)
            while moves:
                lock, _, _ = moves.pop()
                if dist[lock] == _U32_MAX:
                    # Not visited yet.
                    dist[lock] = next_dist
                    next_nodes.append(lock)

        cur_nodes, next_nodes = next_nodes, cur_nodes
        next_dist += 1

    raise _Err("No solution found!")


def _bfs_extract_solution(
    lock_solved: int,
    interlocks: list[int],
    n_plates: int,
    dist: list[int],
) -> list[tuple[int, int, int]]:
    steps: list[tuple[int, int, int]] = []
    while dist[lock_solved]:
        found_step = False

        moves: list[tuple[int, int, int]] = []
        _bfs_populate_moves(lock_solved, interlocks, n_plates, moves)
        for lock, plate_i, plate_off in moves:
            plate_off = -plate_off

            if dist[lock] == dist[lock_solved] - 1:
                steps.append((lock, plate_i, plate_off))

                found_step = True
                lock_solved = lock
                break
        assert found_step, "Logic error: unable to extract solution"
    steps.reverse()
    return steps


def _bfs_populate_moves(
    lock: int, interlocks: list[int], n_plates: int, moves: list[tuple[int, int, int]]
):
    for plate_i in range(n_plates):
        for dir in (-1, 1):
            for plate_off in range(1, _PLATE_MAX):
                plate_off *= dir

                next_lock = lock
                for next_lock_plate_i in range(n_plates):
                    effect_dir = interlocks[plate_i * n_plates + next_lock_plate_i]
                    if effect_dir == 0:
                        continue

                    next_lock_plate_shift = next_lock_plate_i * _PLATE_BITS

                    next_lock_plate_pos = (lock >> next_lock_plate_shift) & _PLATE_MASK
                    next_lock_plate_pos += plate_off * effect_dir
                    if (next_lock_plate_pos < _PLATE_MIN) or (
                        next_lock_plate_pos > _PLATE_MAX
                    ):
                        next_lock = None
                        break

                    next_lock = next_lock & (
                        ~(_PLATE_MASK << next_lock_plate_shift)
                    ) | (next_lock_plate_pos << next_lock_plate_shift)

                if next_lock is None:
                    break
                moves.append((next_lock, plate_i, plate_off))


def _bits_from_iter(bits: Iterable[int]) -> int:
    return sum(0b1 << pos for pos in bits)


def _bits_get(bits: int, bit_pos: int) -> int:
    return (bits >> bit_pos) & 0b1


def _bits_unset(bits: int, unset_bit_pos: int) -> int:
    return bits & ~(0b1 << unset_bit_pos)


def _lock_print(state: int, n_plates: int, annotations: dict[int, str] | None = None):
    if annotations is None:
        annotations = {}

    for plate_i in reversed(range(n_plates)):
        plate_off = _lock_get(state, plate_i) - 1
        plate = [
            str(plate_off + 1) if i == plate_off else "-" for i in range(_PLATE_MAX)
        ]
        plate = " ".join(plate)

        annotation = annotations.get(plate_i)
        if annotation is None:
            end = "\n"
        else:
            end = ""
        print(
            f"    {plate_i + 1}: "
            + ("  " * (_PLATE_MAX - plate_off - 1))
            + f"[ {plate} ]"
            + ("  " * plate_off)
            + f" :{plate_i + 1}",
            end=end,
        )
        if annotation is not None:
            print(f" {annotation}")

    # Print lockpick
    for _ in range(2):
        print("       " + ("  " * _PLATE_MAX) + "|")

    print()


def _lock_get(state: int, plate_i: int) -> int:
    return (state >> (plate_i * _PLATE_BITS)) & _PLATE_MASK


def _lock_set(state: int, plate_i: int, plate_pos: int) -> int:
    shift = plate_i * _PLATE_BITS
    return state & (~(_PLATE_MASK << shift)) | (plate_pos << shift)


def _interlocks_new(n_plates: int) -> list[int]:
    matrix = [0] * (n_plates * n_plates)
    for plate_i in range(n_plates):
        _interlocks_set(matrix, n_plates, plate_i, plate_i, 1)
    return matrix


def _interlocks_print(matrix: list[int], n_plates: int, unprobed: int):
    plate_i = 0
    lines: list[str] = []
    line = ""
    for i, elem in enumerate(matrix):
        if (elem == 0) and _bits_get(unprobed, plate_i):
            line += " ? "
        else:
            line += (" . ", " > ", " < ")[elem]

        if (i + 1) % n_plates == 0:
            plate_i += 1
            lines.append(line)
            line = ""

    print("          " + "---" * n_plates)
    for i, line in reversed(list(enumerate(lines))):
        print(f"    {i + 1} -- |{line}|")
    print("    |     " + "---" * n_plates)
    print("    |     " + " | " * n_plates)
    print("    \\     " + "".join(f" {i + 1} " for i in range(n_plates)))
    print("     \\   " + "   " * n_plates + "\\")
    print("      \\   " + "   " * n_plates + "affected")
    print("       moved by player")
    print()


def _interlocks_set(
    matrix: list[int], n_plates: int, row_i: int, col_i: int, value: int
):
    matrix[row_i * n_plates + col_i] = value


@final
class _Err(Exception):
    pass


_R = TypeVar("_R")


def _input(prompt: Iterable[str], parser: Callable[[str], _R] = lambda _: None) -> _R:
    while True:
        try:
            for prompt_line in prompt:
                print(prompt_line)

            command = input(" > ")
            if not stdin.isatty():
                print(command)
            print()

            command = "".join(command.split()).lower()

            return parser(command)
        except (_Err, ValueError) as e:
            print(f"ERROR: {e}")
            print()


_main()
