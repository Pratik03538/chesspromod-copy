# Exact function source extracted from original main.py.

def grid_to_dict(
    grid,
    black_perspective=False
):
    pieces = {}

    if grid is None:
        return pieces

    for row in range(8):
        for col in range(8):
            symbol = grid[row][col]

            if symbol is None:
                continue

            if black_perspective:
                file_ = 7 - col
                rank_ = row
            else:
                file_ = col
                rank_ = 7 - row

            pieces[
                chess.square(
                    file_,
                    rank_
                )
            ] = symbol

    return pieces


def expected_changed_squares(
    board,
    move
):
    squares = {
        move.from_square,
        move.to_square
    }

    if board.is_castling(move):
        if board.is_kingside_castling(move):
            rook_from = (
                chess.H1
                if board.turn == chess.WHITE
                else chess.H8
            )

            rook_to = (
                chess.F1
                if board.turn == chess.WHITE
                else chess.F8
            )

        else:
            rook_from = (
                chess.A1
                if board.turn == chess.WHITE
                else chess.A8
            )

            rook_to = (
                chess.D1
                if board.turn == chess.WHITE
                else chess.D8
            )

        squares.update({
            rook_from,
            rook_to
        })

    if board.is_en_passant(move):
        captured = (
            move.to_square - 8
            if board.turn == chess.WHITE
            else move.to_square + 8
        )

        squares.add(
            captured
        )

    return squares


def expected_board_after_move(
    board,
    move
):
    after = board.copy(
        stack=False
    )

    after.push(move)

    return after


def expected_symbol_after(
    board,
    move,
    square
):
    after = expected_board_after_move(
        board,
        move
    )

    piece = after.piece_at(
        square
    )

    return (
        piece.symbol()
        if piece
        else None
    )


def board_hypothesis_score(
    board,
    move,
    grid,
    confidence_grid,
    black_perspective
):
    expected_board = expected_board_after_move(
        board,
        move
    )

    observed = grid_conf_dict(
        grid,
        confidence_grid,
        black_perspective
    )

    score = 0.0
    maximum = 0.0
    exact = 0
    type_match = 0
    empty_match = 0
    mismatch = 0

    for square in chess.SQUARES:
        expected_piece = expected_board.piece_at(
            square
        )

        expected_symbol = (
            expected_piece.symbol()
            if expected_piece
            else None
        )

        observed_symbol, observed_conf = observed.get(
            square,
            (None, 999.0)
        )

        if expected_symbol is None:
            maximum += 1.0

            if observed_symbol is None:
                score += 1.0
                empty_match += 1
            else:
                score -= 1.6
                mismatch += 1

            continue

        maximum += 3.2

        if observed_symbol is None:
            score -= 2.0
            mismatch += 1

        elif observed_symbol == expected_symbol:
            quality = max(
                0.0,
                MATCH_THRESHOLD - observed_conf
            )

            score += (
                3.2
                + min(
                    0.35,
                    quality
                )
            )

            exact += 1

        elif (
            observed_symbol.lower()
            == expected_symbol.lower()
        ):
            score += 2.15
            type_match += 1

        else:
            score -= 1.8
            mismatch += 1

    normalized = (
        score / maximum
        if maximum > 0
        else 0.0
    )

    return {
        "score": score,
        "normalized": normalized,
        "exact": exact,
        "type_match": type_match,
        "empty": empty_match,
        "mismatch": mismatch
    }


def board_frame_change_score(
    before_frame,
    after_frame
):
    if (
        before_frame is None
        or after_frame is None
    ):
        return 1.0

    if (
        before_frame.shape
        != after_frame.shape
    ):
        return 1.0

    small_before = cv2.resize(
        before_frame,
        (96, 96),
        interpolation=cv2.INTER_AREA
    )

    small_after = cv2.resize(
        after_frame,
        (96, 96),
        interpolation=cv2.INTER_AREA
    )

    gray_before = cv2.cvtColor(
        small_before,
        cv2.COLOR_BGR2GRAY
    )

    gray_after = cv2.cvtColor(
        small_after,
        cv2.COLOR_BGR2GRAY
    )

    return float(
        np.mean(
            cv2.absdiff(
                gray_before,
                gray_after
            )
        ) / 255.0
    )


def _fast_board_gray(frame, board_coords, size=FAST_VERIFY_SIZE):
    if frame is None:
        return None
    x, y, w, h = board_coords
    x1 = max(0, int(x))
    y1 = max(0, int(y))
    x2 = min(frame.shape[1], int(x + w))
    y2 = min(frame.shape[0], int(y + h))
    if x2 <= x1 or y2 <= y1:
        return None
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA)


def fast_board_motion_map(before_frame, after_frame, board_coords):
    before = _fast_board_gray(before_frame, board_coords)
    after = _fast_board_gray(after_frame, board_coords)
    if before is None or after is None:
        return None
    diff = cv2.absdiff(before, after).astype(np.float32) / 255.0
    cell = FAST_VERIFY_SIZE // 8
    scores = {}
    for row in range(8):
        for col in range(8):
            value = float(np.mean(diff[row*cell:(row+1)*cell, col*cell:(col+1)*cell]))
            # Map visual row/col to chess square later in caller.
            scores[(row, col)] = value
    return scores


