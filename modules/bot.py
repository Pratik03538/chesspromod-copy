# Exact function source extracted from original main.py.

def promotion_symbol(
    move,
    color
):
    if move.promotion is None:
        return None

    return chess.Piece(
        move.promotion,
        color
    ).symbol()


def promotion_candidate_squares(move):
    rank = chess.square_rank(
        move.to_square
    )

    file_ = chess.square_file(
        move.to_square
    )

    result = []

    if rank == 7:
        for step in range(4):
            candidate_rank = rank - step

            if candidate_rank >= 0:
                result.append(
                    chess.square(
                        file_,
                        candidate_rank
                    )
                )

    elif rank == 0:
        for step in range(4):
            candidate_rank = rank + step

            if candidate_rank <= 7:
                result.append(
                    chess.square(
                        file_,
                        candidate_rank
                    )
                )

    else:
        for direction in (-1, 1):
            for step in range(4):
                candidate_rank = (
                    rank
                    + direction * step
                )

                if 0 <= candidate_rank <= 7:
                    result.append(
                        chess.square(
                            file_,
                            candidate_rank
                        )
                    )

    return list(
        dict.fromkeys(result)
    )


def find_promotion_choice(
    sct,
    hwnd,
    move,
    promotion_color,
    board_coords,
    black_perspective,
    allow_fallback=True
):
    expected = promotion_symbol(
        move,
        promotion_color
    )

    if expected is None:
        return None

    frame = capture_screen(
        sct,
        hwnd
    )

    if frame is None:
        return None

    templates = get_scaled_templates(
        board_coords[2] / 8.0,
        board_coords[3] / 8.0
    )

    candidates = promotion_candidate_squares(
        move
    )

    scored = []

    for square in candidates:
        crop = get_square_crop(
            frame,
            board_coords,
            square,
            black_perspective
        )

        if crop is None:
            continue

        detected, score = classify_square(
            crop,
            templates,
            expected_symbol=expected
        )

        if detected == expected:
            scored.append(
                (
                    float(score),
                    square
                )
            )

    if scored:
        scored.sort(
            key=lambda item: item[0]
        )

        return scored[0][1]

    if allow_fallback and PROMOTION_FALLBACK:
        ordered = {
            chess.QUEEN: 0,
            chess.ROOK: 1,
            chess.BISHOP: 2,
            chess.KNIGHT: 3,
        }

        index = ordered.get(
            move.promotion
        )

        if (
            index is not None
            and index < len(candidates)
        ):
            fallback_square = candidates[index]

            print(
                f"[PROMOTION] fallback selected {expected}"
            )

            return fallback_square

    return None


def select_promotion_piece(
    sct,
    hwnd,
    move,
    promotion_color,
    board_coords,
    black_perspective,
    allow_fallback=True
):
    if move.promotion is None:
        return True

    expected = promotion_symbol(
        move,
        promotion_color
    )

    if expected is None:
        return False

    piece_name = chess.piece_name(
        move.promotion
    ).upper()

    progress(
        "PROMOTION",
        (
            f"Stockfish requested {piece_name} "
            f"({expected}); waiting for promotion menu"
        ),
        key="promotion_stage",
        force=True
    )

    for attempt in range(
        1,
        PROMOTION_RETRIES + 1
    ):
        time.sleep(
            PROMOTION_WAIT
        )

        square = find_promotion_choice(
            sct,
            hwnd,
            move,
            promotion_color,
            board_coords,
            black_perspective,
            allow_fallback=allow_fallback
        )

        if square is None:
            progress(
                "PROMOTION",
                (
                    f"menu choice {expected} not detected; "
                    f"attempt {attempt}/{PROMOTION_RETRIES}"
                ),
                key="promotion_loop",
                interval=0.20,
                force=True
            )

            continue

        px, py = square_screen_center(
            square,
            board_coords,
            black_perspective,
            hwnd
        )

        print(
            f"[PROMOTION] selecting {piece_name}"
        )

        if not focus_scrcpy(hwnd):
            continue

        left_click_screen(
            px,
            py
        )

        # Confirm what piece actually appeared on the destination square.
        # If a promotion click selected the wrong piece, stop immediately.
        # Retrying the menu click after a completed promotion is unsafe because
        # the promotion menu is already closed and the next click lands on the
        # normal board.
        promotion_ok = False
        promotion_reason = "promotion state not yet confirmed"
        promotion_deadline = time.perf_counter() + 0.10

        promotion_types = (
            chess.QUEEN,
            chess.ROOK,
            chess.BISHOP,
            chess.KNIGHT,
        )

        while time.perf_counter() < promotion_deadline:
            check_frame = capture_screen(
                sct,
                hwnd
            )

            if check_frame is None:
                time.sleep(
                    SCAN_INTERVAL
                )
                continue

            target_crop = get_square_crop(
                check_frame,
                board_coords,
                move.to_square,
                black_perspective
            )

            templates = get_scaled_templates(
                board_coords[2] / 8.0,
                board_coords[3] / 8.0
            )

            source_crop = get_square_crop(
                check_frame,
                board_coords,
                move.from_square,
                black_perspective
            )

            source_piece, _ = classify_square(
                source_crop,
                templates
            )

            detected_promotions = []

            for piece_type in promotion_types:
                symbol = chess.Piece(
                    piece_type,
                    promotion_color
                ).symbol()

                detected_piece, detected_score = classify_square(
                    target_crop,
                    templates,
                    expected_symbol=symbol,
                    match_threshold=BOT_POST_MATCH_THRESHOLD
                )

                if detected_piece == symbol:
                    detected_promotions.append(
                        (
                            float(detected_score),
                            symbol
                        )
                    )

            if (
                source_piece is None
                and detected_promotions
            ):
                detected_promotions.sort(
                    key=lambda item: item[0]
                )

                detected_score, detected_symbol = (
                    detected_promotions[0]
                )

                if detected_symbol == expected:
                    promotion_ok = True
                    promotion_reason = (
                        f"source=empty destination={expected} "
                        f"({detected_score:.3f})"
                    )
                    break

                print(
                    f"[PROMOTION] WRONG PIECE detected: "
                    f"expected={expected} actual={detected_symbol}; "
                    "game position not advanced"
                )
                return False

            time.sleep(
                SCAN_INTERVAL
            )

        if promotion_ok:
            time.sleep(
                CLICK_SETTLE_DELAY
            )

            progress(
                "PROMOTION",
                f"selected {piece_name}; {promotion_reason}",
                key="promotion_stage",
                force=True
            )

            return True

        progress(
            "PROMOTION",
            (
                f"{piece_name} click not confirmed; "
                f"attempt {attempt}/{PROMOTION_RETRIES}"
            ),
            key="promotion_loop",
            force=True
        )

    progress(
        "PROMOTION",
        (
            f"FAILED to select {piece_name}; "
            "game position not advanced"
        ),
        key="promotion_stage",
        force=True
    )

    return False


def _verify_source_click_selected(
    sct,
    hwnd,
    move,
    before_frame,
    board_coords,
    black_perspective
):
    """Confirm the intended SOURCE square was actually selected.

    A fast motion map is used first. The intended source must be the only
    changed board square, and it must remain the dominant changed square for
    two consecutive frames. This is deliberately strict: when Stockfish asks
    for Bxg5, a click that lands on the queen must never be allowed to reach
    the destination click and become Qxg5.
    """
    if sct is None or before_frame is None:
        return True, "source-click visual check unavailable"

    try:
        source_piece = move.from_square
    except Exception:
        return False, "invalid source square"

    start = time.perf_counter()
    deadline = start + BOT_SOURCE_SELECT_TIMEOUT
    stable_samples = 0
    last_reason = "source selection transition not detected"

    while time.perf_counter() < deadline:
        frame = capture_screen(sct, hwnd)
        if frame is None:
            time.sleep(BOT_SOURCE_SELECT_POLL)
            continue

        changes = fast_square_motion_scores(
            before_frame,
            frame,
            board_coords,
            black_perspective
        )
        if changes is None:
            last_reason = "source selection motion map unavailable"
            time.sleep(BOT_SOURCE_SELECT_POLL)
            continue

        source_change = changes.get(source_piece, 0.0)

        other_changes = sorted(
            (
                (change, square)
                for square, change in changes.items()
                if square != source_piece
                and change >= BOT_SOURCE_SELECT_CHANGE_MIN
            ),
            reverse=True,
            key=lambda item: item[0]
        )

        dominant_other = other_changes[0][0] if other_changes else 0.0
        source_is_dominant = (
            source_change >= BOT_SOURCE_SELECT_CHANGE_MIN
            and dominant_other <= source_change * BOT_SOURCE_SELECT_DOMINANCE_RATIO
        )

        if (
            source_is_dominant
            and len(other_changes) <= BOT_SOURCE_SELECT_MAX_EXTRA_CHANGES
        ):
            stable_samples += 1
            if stable_samples >= BOT_SOURCE_SELECT_STABLE_SAMPLES:
                last_reason = (
                    f"source selected {chess.square_name(source_piece)} "
                    f"change={source_change:.4f}; stable={stable_samples}"
                )
                return True, last_reason

            last_reason = (
                f"source selection seen; waiting stable sample "
                f"{stable_samples}/{BOT_SOURCE_SELECT_STABLE_SAMPLES}; "
                f"change={source_change:.4f}"
            )
        else:
            stable_samples = 0
            if other_changes:
                preview = ", ".join(
                    f"{chess.square_name(sq)}:{change:.4f}"
                    for change, sq in other_changes[:3]
                )
                last_reason = (
                    f"wrong/extra square changed; source="
                    f"{source_change:.4f}; {preview}"
                )
            else:
                last_reason = (
                    f"source change too weak: "
                    f"{source_change:.4f}"
                )

        time.sleep(BOT_SOURCE_SELECT_POLL)

    return False, last_reason


def click_move(
    move,
    board_coords,
    black_perspective,
    scrcpy_hwnd,
    sct=None,
    promotion_color=None
):
    if not focus_scrcpy(
        scrcpy_hwnd
    ):
        print(
            "[BOT ERROR] Could not focus scrcpy window."
        )
        return False

    screen_origin = get_scrcpy_screen_origin(
        scrcpy_hwnd
    )

    if screen_origin is None:
        print(
            "[BOT ERROR] Could not determine scrcpy screen origin."
        )
        return False

    # Keep the original drag behavior, but avoid a perfectly straight
    # source->target cursor path. A tiny perpendicular offset is used at
    # the midpoint, so the gesture remains fast while looking less robotic.
    sx, sy = square_screen_center(
        move.from_square,
        board_coords,
        black_perspective,
        scrcpy_hwnd,
        screen_origin=screen_origin
    )

    tx, ty = square_screen_center(
        move.to_square,
        board_coords,
        black_perspective,
        scrcpy_hwnd,
        screen_origin=screen_origin
    )

    dx = float(tx - sx)
    dy = float(ty - sy)
    distance = max(
        1.0,
        math.hypot(dx, dy)
    )

    # Small sideways deviation: 2-6 px, capped so short moves stay tight.
    offset = min(
        6.0,
        max(
            2.0,
            distance * 0.035
        )
    )

    nx = -dy / distance
    ny = dx / distance

    bend_sign = random.choice((-1.0, 1.0))

    mid_x = (
        (sx + tx) * 0.5
        + nx * offset * bend_sign
    )
    mid_y = (
        (sy + ty) * 0.5
        + ny * offset * bend_sign
    )

    print(
        f"[BOT DRAG] {move.uci()} "
        f"source=({sx},{sy}) "
        f"mid=({int(mid_x)},{int(mid_y)}) "
        f"target=({tx},{ty})"
    )

    user32.SetCursorPos(
        0,
        0
    )

    # Move to source.
    user32.SetCursorPos(
        int(sx),
        int(sy)
    )

    time.sleep(
        0.020
    )

    # One continuous drag gesture.
    user32.mouse_event(
        MOUSEEVENTF_LEFTDOWN,
        0,
        0,
        0,
        0
    )

    time.sleep(
        0.035
    )

    # Slightly bent midpoint instead of a perfectly straight cursor line.
    user32.SetCursorPos(
        int(mid_x),
        int(mid_y)
    )

    time.sleep(
        0.012
    )

    # Final destination while still holding the mouse button.
    user32.SetCursorPos(
        int(tx),
        int(ty)
    )

    time.sleep(
        0.020
    )

    user32.mouse_event(
        MOUSEEVENTF_LEFTUP,
        0,
        0,
        0,
        0
    )

    user32.SetCursorPos(
        0,
        0
    )

    # Let scrcpy/Android settle the completed drag before verification.
    time.sleep(
        0.018
    )

    if move.promotion is not None:
        if promotion_color is None:
            promotion_color = chess.WHITE

        if sct is None:
            print(
                "[PROMOTION ERROR] "
                "Screen capture context unavailable."
            )
            return False

        promotion_ok = select_promotion_piece(
            sct,
            scrcpy_hwnd,
            move,
            promotion_color,
            board_coords,
            black_perspective
        )

        user32.SetCursorPos(
            0,
            0
        )

        return promotion_ok

    return True


def safe_drop_fraction(
    current_cp
):
    current_eval = (
        current_cp / 100.0
    )

    if current_eval < 2.0:
        return 0.10

    if current_eval < 3.0:
        return 0.15

    if current_eval < 4.0:
        return 0.20

    if current_eval < 5.0:
        return 0.25

    return 0.30


