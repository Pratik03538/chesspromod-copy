# Exact function source extracted from original main.py.

def progress(stage, detail="", key=None, interval=None, force=False):
    if not VERBOSE_LOGS and stage not in {"STATE", "PROMOTION"}:
        return

    if interval is None:
        interval = PROGRESS_INTERVAL

    if key is None:
        key = stage

    now = time.perf_counter()
    last = _progress_times.get(key, 0.0)
    text = f"[{stage}] {detail}" if detail else f"[{stage}]"

    if (
        force
        or text != _progress_last_text.get(key)
        or now - last >= interval
    ):
        _progress_times[key] = now
        _progress_last_text[key] = text
        print(
            f"[{time.strftime('%H:%M:%S')}] {text}",
            flush=True
        )


def draw_overlay(
    display_frame,
    board_coords,
    grid,
    locked,
    black_perspective,
    scan_ms,
    status,
    stockfish_color,
    human_color,
    analysis_state=None
):
    x, y, w, h = board_coords

    sq_w = w / 8.0
    sq_h = h / 8.0

    grid_color = (
        (0, 255, 0)
        if locked
        else (0, 255, 255)
    )

    cv2.rectangle(
        display_frame,
        (x, y),
        (x + w, y + h),
        grid_color,
        2
    )

    for i in range(1, 8):
        cv2.line(
            display_frame,
            (
                x,
                y + int(i * sq_h)
            ),
            (
                x + w,
                y + int(i * sq_h)
            ),
            grid_color,
            1
        )

        cv2.line(
            display_frame,
            (
                x + int(i * sq_w),
                y
            ),
            (
                x + int(i * sq_w),
                y + h
            ),
            grid_color,
            1
        )

    if grid is not None:
        for row in range(8):
            for col in range(8):
                symbol = grid[row][col]

                if not symbol:
                    continue

                fx1 = int(
                    x + col * sq_w
                )

                fy1 = int(
                    y + row * sq_h
                )

                color = (
                    (0, 255, 255)
                    if symbol.isupper()
                    else (0, 0, 255)
                )

                cv2.putText(
                    display_frame,
                    symbol,
                    (
                        fx1
                        + int(sq_w / 3),
                        fy1
                        + int(sq_h / 1.5)
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.70,
                    color,
                    2
                )

    cv2.rectangle(
        display_frame,
        (0, 0),
        (
            display_frame.shape[1],
            48
        ),
        (0, 0, 0),
        -1
    )

    cv2.putText(
        display_frame,
        status,
        (8, 18),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.42,
        (0, 255, 255),
        1
    )

    if analysis_state is not None:
        panel_bottom = max(
            52,
            y - 4
        )

        panel_top = max(
            46,
            panel_bottom - 58
        )

        cv2.rectangle(
            display_frame,
            (0, panel_top),
            (
                display_frame.shape[1],
                panel_bottom
            ),
            (15, 15, 15),
            -1
        )

        eval_text = analysis_state.get(
            "eval_text",
            "--"
        )

        favor = analysis_state.get(
            "favor",
            "--"
        )

        quality = analysis_state.get(
            "quality",
            "--"
        )

        last_move = analysis_state.get(
            "last_move",
            "--"
        )

        best_move = analysis_state.get(
            "best_move",
            "--"
        )

        depth = analysis_state.get(
            "depth",
            "--"
        )

        pv = analysis_state.get(
            "pv",
            "--"
        )

        line1 = (
            f"EVAL {eval_text}   "
            f"FAVOR {favor}"
        )

        line2 = (
            f"LAST {last_move}   "
            f"QUALITY {quality}   "
            f"DEPTH {depth}"
        )

        line3 = (
            f"BEST {best_move}   "
            f"LINE (NOT PLAYED) {pv}"
        )

        cv2.putText(
            display_frame,
            line1,
            (
                8,
                panel_top + 17
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (255, 255, 255),
            1
        )

        cv2.putText(
            display_frame,
            line2,
            (
                8,
                panel_top + 35
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            (0, 255, 255),
            1
        )

        cv2.putText(
            display_frame,
            line3,
            (
                8,
                panel_top + 52
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.34,
            (220, 220, 220),
            1
        )

    bottom_color = (
        "BLACK"
        if stockfish_color == chess.BLACK
        else "WHITE"
    )

    top_color = (
        "BLACK"
        if human_color == chess.BLACK
        else "WHITE"
    )

    cv2.putText(
        display_frame,
        (
            f"TOP:{top_color} HUMAN  "
            f"BOTTOM:{bottom_color} STOCKFISH"
        ),
        (8, 38),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.40,
        (255, 255, 255),
        1
    )


def format_board_for_screen(
    board,
    black_perspective
):
    lines = []

    if black_perspective:
        ranks = range(0, 8)
        files = range(7, -1, -1)
    else:
        ranks = range(7, -1, -1)
        files = range(0, 8)

    for rank in ranks:
        row = []

        for file_ in files:
            piece = board.piece_at(
                chess.square(
                    file_,
                    rank
                )
            )

            row.append(
                piece.symbol()
                if piece
                else "."
            )

        lines.append(
            " ".join(row)
        )

    return "\n".join(lines)


def format_move_history(
    board
):
    temp = chess.Board(
        INITIAL_FEN
    )

    moves = []
    move_number = 1

    for idx, move in enumerate(
        board.move_stack
    ):
        if temp.turn == chess.WHITE:
            san = temp.san(
                move
            )

            moves.append(
                f"{move_number}. {san}"
            )

        else:
            san = temp.san(
                move
            )

            if moves:
                moves[-1] += (
                    f" {san}"
                )
            else:
                moves.append(
                    f"{move_number}... {san}"
                )

            move_number += 1

        temp.push(
            move
        )

    return (
        " ".join(moves)
        if moves
        else "-"
    )


def print_game_state(
    board,
    stockfish_color,
    human_color,
    black_perspective,
    message="",
    analysis_state=None
):
    os.system(
        "cls"
        if os.name == "nt"
        else "clear"
    )

    print(
        "============================================================"
    )

    print(
        "             LOCAL CHESS - HUMAN vs STOCKFISH"
    )

    print(
        "============================================================"
    )

    print(
        f"Stockfish: "
        f"{'WHITE' if stockfish_color == chess.WHITE else 'BLACK'}"
        f" | Human: "
        f"{'WHITE' if human_color == chess.WHITE else 'BLACK'}"
    )

    if message:
        print(
            f"\n{message}\n"
        )

    turn_text = (
        "WHITE"
        if board.turn == chess.WHITE
        else "BLACK"
    )

    controller = (
        "STOCKFISH"
        if board.turn == stockfish_color
        else "HUMAN"
    )

    print(
        f"Turn: {turn_text} / {controller}"
    )

    if SHOW_TERMINAL_FEN:
        print(
            f"FEN: {board.fen()}"
        )

    if analysis_state is not None:
        print(
            "\n[ANALYSIS]"
        )

        print(
            f"EVAL: "
            f"{analysis_state.get('eval_text', '--')} "
            f"| FAVOR: "
            f"{analysis_state.get('favor', '--')} "
            f"| QUALITY: "
            f"{analysis_state.get('quality', '--')}"
        )

        print(
            f"LAST: "
            f"{analysis_state.get('last_move', '--')} "
            f"| BEST: "
            f"{analysis_state.get('best_move', '--')} "
            f"| DEPTH: "
            f"{analysis_state.get('depth', '--')}"
        )

        print(
            "ENGINE LINE (PREDICTION): "
            f"{analysis_state.get('pv', '--')}"
        )

    print(
        f"\n[MOVES] "
        f"{format_move_history(board)}"
    )

    if SHOW_TERMINAL_BOARD:
        print(
            "\n[VERIFIED BOARD]"
        )

        print(
            format_board_for_screen(
                board,
                black_perspective
            )
        )

    print()


