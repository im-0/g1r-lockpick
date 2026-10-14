#!/usr/bin/python3

import atexit
import readline
from collections.abc import Iterable
from os import path
from pathlib import Path
from sys import exit, stderr, stdin, stdout
from time import monotonic_ns
from typing import final

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

    print("`h` for help")
    last_ret_code = 0
    try:
        while True:
            cmd = _input(" > ")
            cmd = cmd.strip().lower()
            if not cmd:
                continue

            if cmd == "h":
                print("Supported commands:")
                print("    h - print this help message")
                print("    q - quit")
                print("    u - start unlocking a new lock")
            elif cmd == "q":
                break
            elif cmd == "u":
                try:
                    last_ret_code = 1
                    _cmd_unlock()
                    last_ret_code = 0
                    print()
                except (_Err, ValueError) as e:
                    print(f"ERROR: {e}")
                    print()
                except (EOFError, KeyboardInterrupt):
                    print()
            else:
                print(f'Unknown command "{cmd}", enter `h` for help')
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


def _cmd_unlock():
    print(
        "Enter the space separated pin positions [1..7] from bottom left to top right"
    )
    plates = _input("u> ")
    plates = plates.split()
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

    lock_solved = 0
    for _ in range(n_plates):
        lock_solved <<= _PLATE_BITS
        lock_solved |= _PLATE_SOLVED

    lock, interlocks = _probe_interlocks(lock, lock_solved, n_plates)

    print("Current lock state:")
    print()
    _lock_print(lock, n_plates)
    print("Solving...")
    time_passed = monotonic_ns()
    solution = _bfs(lock, lock_solved, interlocks, n_plates)
    time_passed = monotonic_ns() - time_passed
    print(f"Time passed: {time_passed / 1_000_000_000:.03f}s ({time_passed}ns)")
    print()

    for step_i, (lock, plate_i, plate_off) in enumerate(solution):
        _print_plate_move(lock, n_plates, plate_i, plate_off)

        step_i += 1
        if step_i != len(solution):
            print(f"Press Enter after applying step {step_i}/{len(solution)}")
            _ = _input("s> ")

    print(f"Should be solved after step {len(solution)}/{len(solution)}!")


def _probe_interlocks(
    lock_initial: int, lock_solved: int, n_plates: int
) -> tuple[int, list[int]]:
    lock = lock_initial
    interlocks = _interlocks_new(n_plates)
    unprobed = _bits_from_iter(range(n_plates))

    while lock != lock_solved:
        solution = _bfs_probe(lock, interlocks, n_plates, unprobed)
        if not solution:
            break

        for step_i, (lock, plate_i, plate_off) in enumerate(solution[:-1]):
            _print_plate_move(lock, n_plates, plate_i, plate_off)

            step_i += 1
            print(
                f"Press Enter after applying correcting step {step_i}/{len(solution) - 1}"
            )
            _ = _input("s> ")

        lock, plate_i, plate_off = solution[-1]
        dir = plate_off // abs(plate_off)
        _print_plate_move(lock, n_plates, plate_i, dir)

        try:
            lock, unprobed = _input_probe_result(
                lock, unprobed, interlocks, n_plates, plate_i, dir
            )
            _interlocks_print(interlocks, n_plates, unprobed)
        except (_ProbeStuck, _ProbeLockpickBroke) as e:
            for stuck_plate in e.stuck_plates:
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

            if isinstance(e, _ProbeStuck):
                # Some plate stuck but picking continues => try next valid move.
                pass
            else:
                # Some plate stuck and lockpick broke => restart with initial lock state.
                lock = lock_initial

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


def _bfs_probe(
    lock_start: int,
    interlocks: list[int],
    n_plates: int,
    unprobed_start: int,
) -> list[tuple[int, int, int]]:
    dist = {(lock_start, unprobed_start): 0}

    cur_nodes = [(lock_start, unprobed_start)]
    next_nodes = []
    next_dist = 1
    moves: list[tuple[int, int, int]] = []

    while cur_nodes:
        # TODO: Apply heuristics here on `cur_nodes` instead of inside `_bfs_probe_populate_moves()`.
        while cur_nodes:
            cur_node, cur_unprobed = cur_nodes.pop()
            if (cur_unprobed != unprobed_start) or (cur_unprobed == 0):
                return _bfs_probe_extract_solution(
                    cur_node,
                    interlocks,
                    n_plates,
                    dist,
                    cur_unprobed,
                )

            _bfs_probe_populate_moves(cur_node, interlocks, n_plates, moves)
            while moves:
                lock, plate_i, _ = moves.pop()
                unprobed = _bits_unset(cur_unprobed, plate_i)
                if (lock, unprobed) not in dist:
                    # Not visited yet.
                    dist[(lock, unprobed)] = next_dist
                    next_nodes.append((lock, unprobed))

        cur_nodes, next_nodes = next_nodes, cur_nodes
        next_dist += 1

    assert False, "Logic error: probe BFS failed"


def _bfs_probe_extract_solution(
    lock_solved: int,
    interlocks: list[int],
    n_plates: int,
    dist: dict[tuple[int, int], int],
    unprobed_solved: int,
) -> list[tuple[int, int, int]]:
    solution: list[tuple[int, int, int]] = []
    while dist[(lock_solved, unprobed_solved)]:
        found_step = False

        moves: list[tuple[int, int, int]] = []
        _bfs_probe_populate_moves(lock_solved, interlocks, n_plates, moves)
        for lock, plate_i, plate_off in moves:
            plate_off = -plate_off

            for unprobed in (unprobed_solved, _bits_set(unprobed_solved, plate_i)):
                if (
                    dist.get((lock, unprobed))
                    == dist[(lock_solved, unprobed_solved)] - 1
                ):
                    solution.append((lock, plate_i, plate_off))

                    found_step = True
                    lock_solved = lock
                    unprobed_solved = unprobed
                    break

            if found_step:
                break
        assert found_step, "Logic error: unable to extract probe solution"

    solution.reverse()
    return solution


def _bfs_probe_populate_moves(
    lock: int, interlocks: list[int], n_plates: int, moves: list[tuple[int, int, int]]
):
    _bfs_populate_moves(lock, interlocks, n_plates, moves)

    # Prefer moves towards center.
    moves.sort(
        key=lambda m: (
            0
            if abs(_PLATE_SOLVED - _lock_get(m[0], m[1]))
            < abs(_PLATE_SOLVED - _lock_get(lock, m[1]))
            else 1
        )
    )

    # Prefer moving edge plate if there is exactly one.
    edge_plate_i = None
    for plate_i in range(n_plates):
        if _lock_get(lock, plate_i) in (_PLATE_MIN, _PLATE_MAX):
            if edge_plate_i is None:
                edge_plate_i = plate_i
            else:
                edge_plate_i = ()
    if edge_plate_i not in (None, ()):
        moves.sort(key=lambda m: 0 if m[1] == edge_plate_i else 1)


def _input_probe_result(
    lock: int,
    unprobed: int,
    interlocks: list[int],
    n_plates: int,
    plate_i: int,
    dir: int,
) -> tuple[int, int]:
    # TODO: Multiple plates can stuck simultaneously.
    print(
        "and enter the space separated plate shifts [<, ., >] from bottom left to top right"
    )
    print(
        f"or `p <PLATE [1..{n_plates}]> [<, ., >] [<, ., >] ...` to set connections manually"
    )
    print(f"or `s <STUCK PLATE [1..{n_plates}]> ...` if stuck")
    print(f"or `b <STUCK PLATE [1..{n_plates}]> ...` if lockpick broke")
    shifts = _input("u> ")
    shifts = shifts.strip().lower().split()
    if not shifts:
        raise _Err("No lock plate shifts")

    if (len(shifts) > 2) and (shifts[0] == "p"):
        set_plate = int(shifts[1])
        if (set_plate < 1) or (set_plate > n_plates):
            raise _Err(
                f"Wrong number of plate to set: got {set_plate}, must be [1..{n_plates}]"
            )
        set_plate -= 1

        for shift_i, shift_dir in _parse_shifts(shifts[2:], n_plates):
            _interlocks_set(interlocks, n_plates, set_plate, shift_i, -shift_dir)

        return lock, _bits_unset(unprobed, set_plate)

    if (len(shifts) > 1) and (shifts[0] in ("s", "b")):
        stuck_plates: list[int] = []
        for stuck_plate in shifts[1:]:
            stuck_plate = int(stuck_plate)
            if stuck_plate < 1:
                raise _Err(f"Index of stuck plate is wrong: got {stuck_plate} < 1")
            if stuck_plate > n_plates:
                raise _Err(
                    f"Index of stuck plate is wrong: got {stuck_plate} > {n_plates}"
                )
            stuck_plate -= 1

            stuck_plates.append(stuck_plate)

        if shifts[0] == "s":
            raise _ProbeStuck(stuck_plates)
        if shifts[0] == "b":
            raise _ProbeLockpickBroke(stuck_plates)

    if len(shifts) != n_plates:
        raise _Err("Wrong number of plates")

    for shift_i, shift_dir in _parse_shifts(shifts, n_plates):
        if shift_i == plate_i:
            if shift_dir != dir:
                raise _Err(f"Plate #{plate_i + 1} moved in unexpected direction")
            # Diagonal already set to 1s.
        else:
            _interlocks_set(interlocks, n_plates, plate_i, shift_i, shift_dir * dir)

        # Adjust current position.
        plate_pos = _lock_get(lock, shift_i) + shift_dir
        if plate_pos < _PLATE_MIN:
            raise _Err(
                f"Plate #{shift_i + 1} cannot move in this direction, already at the left edge"
            )
        if plate_pos > _PLATE_MAX:
            raise _Err(
                f"Plate #{shift_i + 1} cannot move in this direction, already at the right edge"
            )
        lock = _lock_set(lock, shift_i, plate_pos)

    return lock, _bits_unset(unprobed, plate_i)


def _parse_shifts(shifts: list[str], n_plates: int) -> Iterable[tuple[int, int]]:
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


@final
class _ProbeStuck(Exception):
    def __init__(self, stuck_plates: list[int]):
        super().__init__("Probe stuck")
        self.stuck_plates = stuck_plates


@final
class _ProbeLockpickBroke(Exception):
    def __init__(self, stuck_plates: list[int]):
        super().__init__("Probe lockpick broke")
        self.stuck_plates = stuck_plates


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


def _bits_set(bits: int, set_bit_pos: int) -> int:
    return bits | (0b1 << set_bit_pos)


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
            + f"[ {plate} ]",
            end=end,
        )
        if annotation is not None:
            print(("  " * plate_off) + f" {annotation}")

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


def _input(prompt: str) -> str:
    result = input(prompt)
    if not stdin.isatty():
        print(result)
    print()
    return result


_main()
