#!/usr/bin/python3

import readline
from collections.abc import Generator
from sys import exit
from time import monotonic_ns
from typing import final

# 3 bits per plate packed into 32bit integers.
# BFS also adds a three-bit plate number.
_PLATE_BITS = 3
_PLATE_MASK = (0b1 << _PLATE_BITS) - 1
_MAX_PLATES = 7
_LOCK_MASK = (0b1 << (_PLATE_BITS * _MAX_PLATES)) - 1

_PLATE_MIN = 1
_PLATE_SOLVED = 4
_PLATE_MAX = 7

_STUCK = -1
_LOCKPICK_BROKE = -2

_U32_MAX = (0b1 << 32) - 1


def _main():
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

    lock_initial = 0
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

        lock_initial = _lock_set(lock_initial, plate_i, plate_pos)

    # Try to detect plate connections.
    lock = lock_initial
    interlocks = _interlocks_new(n_plates)
    unprobed = list(range(n_plates))
    selected_plate_i = 0
    while unprobed:
        # If there is exactly one plate with pin on the edge - try to probe it first.
        one_edge_plate_found = False
        edge_plate_i = None
        for plate_i in range(n_plates):
            plate_pos = _lock_get(lock, plate_i)
            if plate_pos in (_PLATE_MIN, _PLATE_MAX):
                if one_edge_plate_found:
                    edge_plate_i = None
                else:
                    one_edge_plate_found = True
                    edge_plate_i = plate_i
        unprobed.sort(
            key=lambda unprobed_plate_i: 0 if unprobed_plate_i == edge_plate_i else 1
        )

        valid_moves: list[tuple[int, int, int]] = []
        for plate_i in unprobed:
            plate_pos = _lock_get(lock, plate_i)
            valid_moves.extend(
                _valid_moves(lock, interlocks, n_plates, plate_i, plate_pos)
            )
        assert valid_moves, "Logic error: no valid moves during probe"

        try:
            for _, plate_i, dir in valid_moves:
                if dir == 1:
                    _lock_print(lock, n_plates, {plate_i: "<- move left"})
                else:
                    _lock_print(lock, n_plates, {plate_i: "-> move right"})

                try:
                    lock = _input_probe_result(lock, interlocks, n_plates, plate_i, dir)
                    selected_plate_i = plate_i
                    unprobed.remove(plate_i)
                    # State changed => find new valid moves.
                    break
                except (_ProbeStuck, _ProbeLockpickBroke) as e:
                    stuck_plate_pos = _lock_get(lock, e.stuck_plate)
                    if stuck_plate_pos == _PLATE_MIN:
                        # Plate tried to move right.
                        stuck_plate_dir = -1
                    else:
                        # Plate tried to move left.
                        stuck_plate_dir = 1
                    _interlocks_set(
                        interlocks,
                        n_plates,
                        plate_i,
                        e.stuck_plate,
                        stuck_plate_dir * dir,
                    )

                    if isinstance(e, _ProbeStuck):
                        # Some plate stuck but picking continues => try next valid move.
                        continue
                    else:
                        raise
        except _ProbeLockpickBroke:
            # Some plate stuck and lockpick broke => restart with initial lock state.
            lock = lock_initial

    print("Detected plate interlocks:")
    print()
    _interlocks_print(interlocks, n_plates)
    print("Current lock state:")
    print()
    _lock_print(lock, n_plates)
    print("Solving...")
    time_passed = monotonic_ns()
    solution = _bfs(lock, selected_plate_i, interlocks, n_plates)
    time_passed = monotonic_ns() - time_passed
    print(f"Time passed: {time_passed / 1_000_000_000:.03}s ({time_passed}ns)")
    print()

    for step_i, (n_shifts, lock, plate_i, dir) in enumerate(solution):
        if n_shifts == 1:
            times = "1 time"
        else:
            times = f"{n_shifts} times"
        if dir == 1:
            _lock_print(lock, n_plates, {plate_i: f"<- move left {times}"})
        else:
            _lock_print(lock, n_plates, {plate_i: f"-> move right {times}"})

        step_i += 1
        if step_i != len(solution):
            print(f"Press Enter after applying step {step_i}/{len(solution)}")
            _ = _input("s> ")

    print("Solved!")


def _input_probe_result(
    lock: int, interlocks: list[int], n_plates: int, plate_i: int, dir: int
) -> int:
    print(
        "and enter the space separated plate shifts [<, 0, >] from bottom left to top right"
    )
    print(f"or `s <STUCK PLATE [1..{n_plates}]>` if stuck")
    print(f"or `b <STUCK PLATE [1..{n_plates}]>` if lockpick broke")
    shifts = _input("u> ")
    shifts = shifts.strip().lower().split()
    if not shifts:
        raise _Err("No lock plate shifts")

    if (len(shifts) == 2) and (shifts[0] in ("s", "b")):
        stuck_plate = int(shifts[1])
        if stuck_plate < 1:
            raise _Err(f"Index of stuck plate is wrong: got {stuck_plate} < 1")
        if stuck_plate > n_plates:
            raise _Err(f"Index of stuck plate is wrong: got {stuck_plate} > {n_plates}")
        stuck_plate -= 1

        if shifts[0] == "s":
            raise _ProbeStuck(stuck_plate)
        if shifts[0] == "b":
            raise _ProbeLockpickBroke(stuck_plate)

    if len(shifts) != n_plates:
        raise _Err("Wrong number of plates")

    for shift_i, shift in enumerate(shifts):
        if shift == "<":
            shift_dir = 1
        elif shift == "0":
            shift_dir = 0
        elif shift == ">":
            shift_dir = -1
        else:
            raise _Err(f'Unknown change direction of plate #{shift_i + 1}: "{shift}"')

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
                f"Plate #{plate_i + 1} cannot move in this direction, already at the left edge"
            )
        if plate_pos > _PLATE_MAX:
            raise _Err(
                f"Plate #{plate_i + 1} cannot move in this direction, already at the right edge"
            )
        lock = _lock_set(lock, shift_i, plate_pos)

    return lock


@final
class _ProbeStuck(Exception):
    def __init__(self, stuck_plate: int):
        super().__init__("Probe stuck")
        self.stuck_plate = stuck_plate


@final
class _ProbeLockpickBroke(Exception):
    def __init__(self, stuck_plate: int):
        super().__init__("Probe lockpick broke")
        self.stuck_plate = stuck_plate


def _bfs(
    lock_start: int, selected_plate_i: int, interlocks: list[int], n_plates: int
) -> list[tuple[int, int, int, int]]:
    lock_solved = 0
    plate_shift = _PLATE_BITS * n_plates
    lock_mask = (0b1 << plate_shift) - 1
    for _ in range(n_plates):
        lock_solved <<= _PLATE_BITS
        lock_solved |= _PLATE_SOLVED

    n_nodes = 0b1 << ((n_plates + 1) * _PLATE_BITS)

    cur_nodes = [0] * n_nodes
    next_nodes = [0] * n_nodes
    dist = [_U32_MAX] * n_nodes

    lock_start |= selected_plate_i << plate_shift

    n_cur_nodes = 1
    cur_nodes[0] = lock_start
    dist[lock_start] = 0

    while n_cur_nodes:
        n_next_nodes = 0

        for cur_node_i in range(n_cur_nodes):
            cur_node = cur_nodes[cur_node_i]
            if cur_node & lock_mask == lock_solved:
                print(f"Found solution with {dist[cur_node]} key presses")
                return _bfs_extract_solution(
                    lock_start,
                    plate_shift,
                    lock_mask,
                    cur_node,
                    interlocks,
                    n_plates,
                    dist,
                )

            for neighbor_node, _ in _bfs_moves(
                cur_node, plate_shift, lock_mask, interlocks, n_plates
            ):
                if dist[neighbor_node] == _U32_MAX:
                    # Not visited yet.
                    dist[neighbor_node] = dist[cur_node] + 1
                    next_nodes[n_next_nodes] = neighbor_node
                    n_next_nodes += 1

        cur_nodes, next_nodes = next_nodes, cur_nodes
        n_cur_nodes = n_next_nodes

    raise _Err("No solution found!")


def _bfs_extract_solution(
    lock: int,
    plate_shift: int,
    lock_mask: int,
    lock_solved: int,
    interlocks: list[int],
    n_plates: int,
    dist: list[int],
) -> list[tuple[int, int, int, int]]:
    steps: list[tuple[int, int, int, int]] = []
    while lock_solved != lock:
        found_step = False
        for neighbor_node, dir in _bfs_moves(
            lock_solved, plate_shift, lock_mask, interlocks, n_plates
        ):
            dir = -dir

            if dist[neighbor_node] == dist[lock_solved] - 1:
                plate_i = neighbor_node >> plate_shift
                neighbor_node_plain = neighbor_node & lock_mask

                if dir != 0:
                    if steps and (steps[-1][2:4] == (plate_i, dir)):
                        steps[-1] = steps[-1][0] + 1, neighbor_node_plain, plate_i, dir
                    else:
                        steps.append((1, neighbor_node_plain, plate_i, dir))

                found_step = True
                lock_solved = neighbor_node
                break
        assert found_step, "Logic error: unable to extract solution"
    steps.reverse()
    return steps


def _bfs_moves(
    lock: int, plate_shift: int, lock_mask: int, interlocks: list[int], n_plates: int
) -> Generator[tuple[int, int]]:
    plate_i = lock >> plate_shift
    lock &= lock_mask

    if plate_i > 0:
        yield lock | ((plate_i - 1) << plate_shift), 0
    if plate_i < n_plates - 1:
        yield lock | ((plate_i + 1) << plate_shift), 0

    plate_i_shifted = plate_i << plate_shift
    for next_lock_state, _, dir in _valid_moves(
        lock, interlocks, n_plates, plate_i, _lock_get(lock, plate_i)
    ):
        yield next_lock_state | plate_i_shifted, dir


def _valid_moves(
    lock: int, interlocks: list[int], n_plates: int, plate_i: int, plate_pos: int
) -> Generator[tuple[int, int, int]]:
    if plate_pos == _PLATE_MIN:
        dirs = (1,)
    elif plate_pos == _PLATE_MAX:
        dirs = (-1,)
    else:
        dirs = (1, -1)

    for dir in dirs:
        next_lock_state = _lock_from_iter(
            (
                affected_pos + dir * effect_dir
                for affected_pos, effect_dir in zip(
                    _lock_iter(lock, n_plates),
                    _interlocks_iter_cols(interlocks, n_plates, plate_i),
                )
            )
        )
        if next_lock_state == _STUCK:
            continue
        yield next_lock_state, plate_i, dir


def _lock_print(state: int, n_plates: int, annotations: dict[int, str] | None = None):
    if annotations is None:
        annotations = {}

    for plate_i in reversed(range(n_plates)):
        plate_off = _lock_get(state, plate_i) - 1
        plate = ["O" if i == plate_off else "-" for i in range(_PLATE_MAX)]
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


def _lock_iter(state: int, n_plates: int) -> Generator[int]:
    for _ in range(n_plates):
        yield state & _PLATE_MASK
        state >>= _PLATE_BITS


def _lock_set(state: int, plate_i: int, plate_pos: int) -> int:
    shift = plate_i * _PLATE_BITS
    return state & (_LOCK_MASK ^ (_PLATE_MASK << shift)) | (plate_pos << shift)


def _lock_from_iter(plates: Generator[int]) -> int:
    state = 0
    for plate_i, plate_pos in enumerate(plates):
        if (plate_pos < _PLATE_MIN) or (plate_pos > _PLATE_MAX):
            return _STUCK
        state |= plate_pos << (plate_i * _PLATE_BITS)
    return state


def _interlocks_new(n_plates: int) -> list[int]:
    matrix = [0] * (n_plates * n_plates)
    for plate_i in range(n_plates):
        _interlocks_set(matrix, n_plates, plate_i, plate_i, 1)
    return matrix


def _interlocks_print(matrix: list[int], n_plates: int):
    lines: list[str] = []
    line = ""
    for i, elem in enumerate(matrix):
        if elem == 0:
            line += "    "
        else:
            line += f" {elem: >2} "

        if (i + 1) % n_plates == 0:
            lines.append(line)
            line = ""

    print("          " + "----" * n_plates)
    for i, line in reversed(list(enumerate(lines))):
        print(f"    {i + 1} -- |{line}|")
    print("    |     " + "----" * n_plates)
    print("    |     " + "  | " * n_plates)
    print("    \\     " + "".join(f"  {i + 1} " for i in range(n_plates)))
    print("     \\   " + "    " * n_plates + "\\")
    print("      \\   " + "    " * n_plates + "affected")
    print("       moved by player")
    print()


def _interlocks_iter_cols(
    matrix: list[int], n_plates: int, row_i: int
) -> Generator[int]:
    start = row_i * n_plates
    for i in range(start, start + n_plates):
        yield matrix[i]


def _interlocks_set(
    matrix: list[int], n_plates: int, row_i: int, col_i: int, value: int
):
    matrix[row_i * n_plates + col_i] = value


@final
class _Err(Exception):
    pass


def _input(prompt: str) -> str:
    result = input(prompt)
    print()
    return result


_main()
