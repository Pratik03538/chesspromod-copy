# Exact function source extracted from original main.py.

def detect_board_orientation(

    grid,
    board
):
    def score(black_perspective):
        detected = grid_to_dict(
            grid,
            black_perspective
        )

        count = 0

        for square in chess.SQUARES:
            expected_piece = board.piece_at(
                square
            )

            expected = (
                expected_piece.symbol()
                if expected_piece
                else None
            )

            if (
                detected.get(square)
                == expected
            ):
                count += 1

        return count

    white_score = score(False)
    black_score = score(True)

    print(
        f"[ORIENTATION] "
        f"White={white_score}/64 "
        f"Black={black_score}/64"
    )

    return (
        black_score
        > white_score
    )


def stable_initial_scan(
    sct,
    hwnd,
    board_coords,
    timeout=ORIENTATION_TIMEOUT
):
    start = time.perf_counter()

    previous = None
    stable = 0
    best_frame = None
    best_grid = None

    while (
        time.perf_counter() - start
        < timeout
    ):
        frame = capture_screen(
            sct,
            hwnd
        )

        if frame is None:
            time.sleep(
                SCAN_INTERVAL
            )

            continue

        grid, _, _ = scan_board(
            frame,
            board_coords
        )

        signature = tuple(
            tuple(row)
            for row in grid
        )

        if signature == previous:
            stable += 1
        else:
            previous = signature
            stable = 1

        best_frame = frame
        best_grid = grid

        if stable >= 2:
            return (
                best_frame,
                best_grid
            )

        time.sleep(
            SCAN_INTERVAL
        )

    return (
        best_frame,
        best_grid
    )


def detect_bottom_stockfish_color(
    black_perspective
):
    return (
        chess.BLACK
        if black_perspective
        else chess.WHITE
    )


