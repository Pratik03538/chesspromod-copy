# Exact function source extracted from original main.py.

def move_transition_strength(
    before_frame,
    after_frame,
    board,
    move,
    board_coords,
    black_perspective
):
    affected = expected_changed_squares(
        board,
        move
    )

    total = 0.0
    minimum = 0.0
    values = {}

    for square in affected:
        value = square_change_score(
            before_frame,
            after_frame,
            board_coords,
            square,
            black_perspective
        )

        values[square] = value
        total += value

    if affected:
        minimum = min(
            values.values()
        )

    return (
        total,
        minimum,
        values
    )


def move_visual_score(
    before_frame,
    after_frame,
    board,
    move,
    board_coords,
    black_perspective,
    templates
):
    changed = expected_changed_squares(
        board,
        move
    )

    observed = {
        square: square_change_score(
            before_frame,
            after_frame,
            board_coords,
            square,
            black_perspective
        )
        for square in changed
    }

    target_change = observed.get(
        move.to_square,
        0.0
    )

    source_change = observed.get(
        move.from_square,
        0.0
    )

    if target_change < TARGET_CHANGE_THRESHOLD:
        return None

    if (
        not board.is_castling(move)
        and not board.is_en_passant(move)
    ):
        if source_change < SOURCE_CHANGE_THRESHOLD:
            return None

    expected_target = expected_symbol_after(
        board,
        move,
        move.to_square
    )

    target_match = 0.0

    if expected_target is not None:
        target_crop = get_square_crop(
            after_frame,
            board_coords,
            move.to_square,
            black_perspective
        )

        detected_symbol, score = classify_square(
            target_crop,
            templates
        )

        if detected_symbol is None:
            return None

        if (
            detected_symbol.lower()
            != expected_target.lower()
        ):
            return None

        target_match = max(
            0.0,
            MATCH_THRESHOLD - score
        )

    if board.is_castling(move):
        rook_square = (
            chess.F1
            if (
                board.turn == chess.WHITE
                and board.is_kingside_castling(move)
            )
            else chess.D1
            if board.turn == chess.WHITE
            else chess.F8
            if board.is_kingside_castling(move)
            else chess.D8
        )

        rook_change = observed.get(
            rook_square,
            0.0
        )

        if rook_change < CHANGE_THRESHOLD:
            return None

        king_expected = (
            "K"
            if board.turn == chess.WHITE
            else "k"
        )

        rook_expected = (
            "R"
            if board.turn == chess.WHITE
            else "r"
        )

        king_crop = get_square_crop(
            after_frame,
            board_coords,
            move.to_square,
            black_perspective
        )

        rook_crop = get_square_crop(
            after_frame,
            board_coords,
            rook_square,
            black_perspective
        )

        king_symbol, king_score = classify_square(
            king_crop,
            templates
        )

        rook_symbol, rook_score = classify_square(
            rook_crop,
            templates
        )

        if not king_symbol or not rook_symbol:
            return None

        if (
            king_symbol.lower()
            != king_expected.lower()
        ):
            return None

        if (
            rook_symbol.lower()
            != rook_expected.lower()
        ):
            return None

        return (
            target_change
            + rook_change
            + target_match
        )

    if board.is_en_passant(move):
        captured_square = (
            move.to_square - 8
            if board.turn == chess.WHITE
            else move.to_square + 8
        )

        captured_change = observed.get(
            captured_square,
            0.0
        )

        if captured_change < CHANGE_THRESHOLD:
            return None

        return (
            target_change
            + captured_change
            + target_match
        )

    return (
        target_change
        + max(
            source_change,
            0.0
        )
        + target_match
    )


def fast_expected_post_state_confirmed(
    before_frame,
    after_frame,
    board,
    move,
    board_coords,
    black_perspective
):
    """Fast closed-loop post-move verification without a 64-template scan."""
    if before_frame is None or after_frame is None:
        return False, "missing verification frame"

    observed_changes = fast_square_motion_scores(
        before_frame, after_frame, board_coords, black_perspective
    )
    if observed_changes is None:
        return False, "fast board motion map unavailable"

    affected = set(expected_changed_squares(board, move))
    unexpected = []
    for square, change in observed_changes.items():
        if square in affected:
            continue
        if change >= FAST_UNEXPECTED_STRONG_DIFF:
            unexpected.append((square, change))

    # Any strong change outside the squares that this move is allowed to touch
    # means a wrong click or an unexpected board transition occurred.
    if len(unexpected) > FAST_MAX_UNEXPECTED_CHANGED_SQUARES:
        preview = ', '.join(
            f"{chess.square_name(sq)}:{change:.3f}"
            for sq, change in unexpected[:4]
        )
        return False, f"unexpected board change {preview}"

    templates = get_scaled_templates(
        board_coords[2] / 8.0, board_coords[3] / 8.0
    )

    # Exact piece-state verification only on the affected squares.
    def expected_piece_at(frame, square, expected_symbol):
        crop = get_square_crop(
            frame, board_coords, square, black_perspective
        )
        if expected_symbol is None:
            detected, score = classify_square(crop, templates)
            return detected is None, detected, score
        detected, score = classify_square(
            crop, templates, expected_symbol=expected_symbol,
            match_threshold=FULL_BOARD_EXPECTED_MATCH_THRESHOLD
        )
        return detected == expected_symbol, detected, score

    source_piece = board.piece_at(move.from_square)
    source_ok, source_detected, source_score = expected_piece_at(after_frame, move.from_square, None)
    if not source_ok:
        return False, f"source not empty after move ({source_detected or '-'}:{source_score:.3f})"

    expected_target = expected_symbol_after(board, move, move.to_square)
    if expected_target is not None:
        target_ok, target_detected, target_score = expected_piece_at(after_frame, move.to_square, expected_target)
        if not target_ok:
            return False, f"destination mismatch ({target_detected or '-'}:{target_score:.3f}, expected {expected_target})"

    if board.is_castling(move):
        rook_to = (
            chess.F1 if board.turn == chess.WHITE and board.is_kingside_castling(move) else
            chess.D1 if board.turn == chess.WHITE else
            chess.F8 if board.is_kingside_castling(move) else chess.D8
        )
        rook_expected = "R" if board.turn == chess.WHITE else "r"
        rook_ok, rook_detected, rook_score = expected_piece_at(after_frame, rook_to, rook_expected)
        if not rook_ok:
            return False, f"castling rook mismatch ({rook_detected or '-'}:{rook_score:.3f})"

    if board.is_en_passant(move):
        captured_square = move.to_square - 8 if board.turn == chess.WHITE else move.to_square + 8
        captured_ok, captured_detected, captured_score = expected_piece_at(after_frame, captured_square, None)
        if not captured_ok:
            return False, f"en-passant captured square not empty ({captured_detected or '-'}:{captured_score:.3f})"

    return True, "fast physical post-state confirmed"


def fast_preclick_board_confirmed(
    reference_frame,
    frame,
    board,
    move,
    board_coords,
    black_perspective
):
    """Fast check that the board is still the last verified internal position."""
    if reference_frame is None or frame is None:
        return False, "missing pre-click frame"

    changes = fast_square_motion_scores(
        reference_frame, frame, board_coords, black_perspective
    )
    if changes is None:
        return False, "fast board motion map unavailable"

    # Ignore the current source/destination only for the safety preview; on a
    # true pre-click frame they must still contain the internal pieces below.
    unexpected = [
        (sq, value)
        for sq, value in changes.items()
        if value >= FAST_UNEXPECTED_STRONG_DIFF
    ]
    if unexpected:
        preview = ', '.join(
            f"{chess.square_name(sq)}:{value:.3f}"
            for sq, value in unexpected[:4]
        )
        return False, f"physical board changed before click ({preview})"

    templates = get_scaled_templates(
        board_coords[2] / 8.0, board_coords[3] / 8.0
    )
    source_piece = board.piece_at(move.from_square)
    if source_piece is None:
        return False, "internal source piece missing"
    source_crop = get_square_crop(
        frame, board_coords, move.from_square, black_perspective
    )
    source_detected, _ = classify_square(source_crop, templates)
    if source_detected != source_piece.symbol():
        return False, f"source mismatch {source_detected or '-'} != {source_piece.symbol()}"

    if board.piece_at(move.to_square) is None:
        target_crop = get_square_crop(
            frame, board_coords, move.to_square, black_perspective
        )
        target_detected, target_score = classify_square(
            target_crop,
            templates,
            match_threshold=EMPTY_DEST_MATCH_THRESHOLD
        )
        if target_detected is not None:
            return False, (
                f"destination unexpectedly occupied by "
                f"{target_detected} ({target_score:.3f})"
            )

    return True, "physical board still matches internal position"


def screen_still_before_move(
    frame,
    board,
    move,
    board_coords,
    black_perspective
):
    # The caller passes the last verified baseline frame. For compatibility,
    # keep this function as the exact-piece guard; the fast pre-click board
    # reference check is performed against baseline_frame at the call site.
    if frame is None:
        return False

    templates = get_scaled_templates(
        board_coords[2] / 8.0, board_coords[3] / 8.0
    )
    source_piece = board.piece_at(move.from_square)
    if source_piece is None:
        return False

    source_crop = get_square_crop(
        frame, board_coords, move.from_square, black_perspective
    )
    source_detected, _ = classify_square(source_crop, templates)
    if source_detected != source_piece.symbol():
        return False

    if board.piece_at(move.to_square) is None:
        target_crop = get_square_crop(
            frame, board_coords, move.to_square, black_perspective
        )
        target_detected, _ = classify_square(
            target_crop,
            templates,
            match_threshold=EMPTY_DEST_MATCH_THRESHOLD
        )
        if target_detected is not None:
            return False

    return True


def full_board_state_confirmed(

    frame,
    expected_board,
    board_coords,
    black_perspective
):
    """Require the physical screen to match the expected chess position.

    The normal 64-square scan is still performed, but occupied squares are
    additionally checked against the exact piece that python-chess expects.
    This resolves isolated template confusions such as a rook being read as
    a bishop while still rejecting genuine board drift.
    """
    if frame is None:
        return False, "missing frame for full-board validation"

    grid, confidence_grid, scan_ms = scan_board(
        frame,
        board_coords
    )

    observed = grid_conf_dict(
        grid,
        confidence_grid,
        black_perspective
    )

    templates = get_scaled_templates(
        board_coords[2] / 8.0,
        board_coords[3] / 8.0
    )

    mismatches = []

    for square in chess.SQUARES:
        expected_piece = expected_board.piece_at(square)
        expected_symbol = (
            expected_piece.symbol()
            if expected_piece is not None
            else None
        )

        observed_symbol, observed_conf = observed.get(
            square,
            (None, 999.0)
        )

        if observed_symbol == expected_symbol:
            continue

        # For occupied expected squares, re-check ONLY the expected piece
        # template. The generic scan can confuse visually similar templates
        # (e.g. rook/bishop) even though the correct expected piece is present.
        if expected_symbol is not None:
            crop = get_square_crop(
                frame,
                board_coords,
                square,
                black_perspective
            )

            expected_detected, expected_score = classify_square(
                crop,
                templates,
                expected_symbol=expected_symbol,
                match_threshold=FULL_BOARD_EXPECTED_MATCH_THRESHOLD
            )

            if expected_detected == expected_symbol:
                continue

        mismatches.append((
            chess.square_name(square),
            expected_symbol or "-",
            observed_symbol or "-",
            observed_conf
        ))

    if mismatches:
        preview = "; ".join(
            f"{sq}:{exp}->{obs}"
            for sq, exp, obs, _ in mismatches[:6]
        )
        if len(mismatches) > 6:
            preview += f"; +{len(mismatches) - 6} more"
        return False, (
            f"full-board mismatch {len(mismatches)}/64 ({preview})"
        )

    return True, f"full-board match 64/64 scan={scan_ms:.1f}ms"


def verify_human_move_on_screen(
    sct,
    hwnd,
    expected_board,
    frame,
    board_coords,
    black_perspective,
    move,
    before_board
):
    """Fast human post-move physical verification.

    The last verified frame is used as the reference. Every board square is
    checked for unexpected pixel movement in one vectorized 128x128 diff,
    while exact piece templates are checked only on the move's affected
    squares. Internal board is still advanced only after this gate passes.
    """
    start = time.perf_counter()
    deadline = start + max(HUMAN_MOVE_TIMEOUT, 0.55)
    last_frame = frame
    last_reason = "human post-move position not yet visible"

    if move is None:
        return False, frame, "missing human move for fast verification"

    baseline_frame = frame
    while time.perf_counter() < deadline:
        candidate_frame = capture_screen(sct, hwnd)
        if candidate_frame is None:
            time.sleep(BOT_RECOVERY_POLL)
            continue
        last_frame = candidate_frame

        ok, reason = fast_expected_post_state_confirmed(
            baseline_frame,
            candidate_frame,
            before_board,
            move,
            board_coords,
            black_perspective
        )
        if ok:
            # Final authority is the actual scrcpy board image, not only the
            # two affected squares. Require the complete expected position
            # before the internal python-chess board is ever advanced.
            full_ok, full_reason = full_board_state_confirmed(
                candidate_frame,
                expected_board,
                board_coords,
                black_perspective
            )
            if full_ok:
                return True, candidate_frame, (
                    "scrcpy full-board match 64/64; "
                    + reason
                )
            last_reason = full_reason
        else:
            last_reason = reason

        time.sleep(BOT_RECOVERY_POLL)

    return False, last_frame, last_reason


def screen_matches_expected_bot_move(
    frame,
    board,
    move,
    board_coords,
    black_perspective,
    before_frame=None
):
    if frame is None:
        return False, "missing frame"

    if before_frame is None:
        return False, "missing pre-move reference frame"

    fast_ok, fast_reason = fast_expected_post_state_confirmed(
        before_frame,
        frame,
        board,
        move,
        board_coords,
        black_perspective
    )
    if not fast_ok:
        return False, fast_reason

    # Pending/recovery confirmation must use the same strict final authority
    # as the normal bot path. Never commit a move from a loose two-square
    # match, especially when Bxg5 could physically become Qxg5.
    expected_after = expected_board_after_move(
        board,
        move
    )
    full_ok, full_reason = full_board_state_confirmed(
        frame,
        expected_after,
        board_coords,
        black_perspective
    )
    if not full_ok:
        return False, (
            "fast post-state passed but scrcpy full-board rejected: "
            + full_reason
        )

    return True, (
        "scrcpy full-board match 64/64; "
        + fast_reason
    )


def transition_confirmed(

    before_frame,
    after_frame,
    board,
    move,
    board_coords,
    black_perspective
):
    affected = expected_changed_squares(
        board,
        move
    )

    changes = {}

    for square in affected:
        changes[square] = square_change_score(
            before_frame,
            after_frame,
            board_coords,
            square,
            black_perspective
        )

    target_change = changes.get(
        move.to_square,
        0.0
    )

    source_change = changes.get(
        move.from_square,
        0.0
    )

    if target_change < TARGET_CHANGE_THRESHOLD:
        return (
            False,
            "destination did not visually change"
        )

    if board.is_castling(move):
        rook_to = (
            chess.F1
            if (
                board.turn == chess.WHITE
                and board.is_kingside_castling(move)
            )
            else chess.D1
            if board.turn == chess.WHITE
            else chess.F8
            if board.is_kingside_castling(move)
            else chess.D8
        )

        if (
            changes.get(
                rook_to,
                0.0
            )
            < CHANGE_THRESHOLD
        ):
            return (
                False,
                "castling rook transition not detected"
            )

        return (
            True,
            f"transition confirmed {target_change:.3f}"
        )

    if board.is_en_passant(move):
        captured = (
            move.to_square - 8
            if board.turn == chess.WHITE
            else move.to_square + 8
        )

        if (
            changes.get(
                captured,
                0.0
            )
            < CHANGE_THRESHOLD
        ):
            return (
                False,
                "en-passant captured square did not change"
            )

        return (
            True,
            f"transition confirmed {target_change:.3f}"
        )

    if source_change >= SOURCE_CHANGE_THRESHOLD:
        return (
            True,
            (
                f"transition confirmed "
                f"{source_change:.3f}/"
                f"{target_change:.3f}"
            )
        )

    return (
        False,
        "source and destination transition not both detected"
    )


def verify_bot_move(
    sct,
    hwnd,
    board,
    move,
    before_frame,
    board_coords,
    black_perspective
):
    """Fast closed-loop bot verification.

    Uses one cheap whole-board motion map plus exact classification only on
    affected squares. Internal board is not advanced until this succeeds.
    """
    start = time.perf_counter()
    deadline = start + BOT_VERIFY_TIMEOUT
    last_frame = None
    last_reason = "post-move state not yet confirmed"

    while time.perf_counter() < deadline:
        after_frame = capture_screen(sct, hwnd)
        if after_frame is None:
            time.sleep(BOT_RECOVERY_POLL)
            continue

        last_frame = after_frame
        ok, reason = fast_expected_post_state_confirmed(
            before_frame,
            after_frame,
            board,
            move,
            board_coords,
            black_perspective
        )
        if ok:
            # Normal moves use the fast closed-loop screen validation. Because
            # before_frame is a previously verified complete board, the 64-square
            # motion map proves that no unrelated square changed, and exact
            # source/destination classification proves the requested piece moved.
            # Captures/castling/promotion still get the strict full-board check.
            strict_full = True

            if not strict_full:
                return True, after_frame, reason

            expected_after = expected_board_after_move(
                board,
                move
            )
            full_ok, full_reason = full_board_state_confirmed(
                after_frame,
                expected_after,
                board_coords,
                black_perspective
            )

            if full_ok:
                return True, after_frame, (
                    "scrcpy full-board match 64/64; "
                    + reason
                )

            last_reason = (
                "fast post-state passed but scrcpy full-board rejected: "
                + full_reason
            )
        else:
            last_reason = reason
        time.sleep(BOT_RECOVERY_POLL)

    return False, last_frame, last_reason


