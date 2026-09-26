# Exact function source extracted from original main.py.

def human_piece_type(
    board,
    move
):
    piece = board.piece_at(
        move.from_square
    )

    return (
        piece.piece_type
        if piece is not None
        else None
    )


def human_direct_state_confirmed(
    frame,
    board,
    move,
    board_coords,
    black_perspective,
    templates
):
    """
    Targeted final check for fast PAWN/ROOK moves.
    """
    source_piece = board.piece_at(
        move.from_square
    )

    if source_piece is None:
        return (
            False,
            "source piece missing from internal board"
        )

    source_crop = get_square_crop(
        frame,
        board_coords,
        move.from_square,
        black_perspective
    )

    target_crop = get_square_crop(
        frame,
        board_coords,
        move.to_square,
        black_perspective
    )

    source_detected, source_score = classify_square(
        source_crop,
        templates
    )

    if source_detected is not None:
        return (
            False,
            (
                f"source still shows "
                f"{source_detected} "
                f"({source_score:.3f})"
            )
        )

    expected_target = expected_symbol_after(
        board,
        move,
        move.to_square
    )

    if expected_target is None:
        return (
            False,
            "expected destination piece missing"
        )

    target_detected, target_score = classify_square(
        target_crop,
        templates,
        expected_symbol=expected_target
    )

    if target_detected != expected_target:
        return (
            False,
            (
                f"target "
                f"{target_detected or '-'} != "
                f"{expected_target} "
                f"({target_score:.3f})"
            )
        )

    return (
        True,
        (
            f"source empty; target "
            f"{expected_target} "
            f"({target_score:.3f})"
        )
    )


def fast_human_move_rescan(
    sct,
    hwnd,
    board,
    baseline_frame,
    board_coords,
    black_perspective,
    legal_moves
):
    """Ultra-fast human move detection before the slower legacy scanner.

    The first pass uses a vectorized 128x128 board diff. Only legal moves whose
    source and destination are among the strongest changed squares are tested.
    Exact piece-state verification is then performed only on the top few
    candidates. A second fresh frame must confirm the same candidate before the
    move is returned.
    """
    if baseline_frame is None or not legal_moves:
        return None, None

    start = time.perf_counter()
    last_frame = None
    last_candidates = []

    while (
        time.perf_counter() - start
        < HUMAN_FAST_RESCAN_CONFIRM_TIMEOUT
    ):
        frame = capture_screen(
            sct,
            hwnd
        )

        if frame is None:
            time.sleep(HUMAN_FAST_RESCAN_POLL)
            continue

        last_frame = frame

        changed = fast_square_motion_scores(
            baseline_frame,
            frame,
            board_coords,
            black_perspective
        )

        if changed is None:
            time.sleep(HUMAN_FAST_RESCAN_POLL)
            continue

        ranked = sorted(
            (
                (score, square)
                for square, score in changed.items()
                if score >= HUMAN_FAST_RESCAN_THRESHOLD
            ),
            reverse=True,
            key=lambda item: item[0]
        )

        if len(ranked) < 2:
            time.sleep(HUMAN_FAST_RESCAN_POLL)
            continue

        top_squares = {
            square
            for _, square in ranked[:HUMAN_FAST_RESCAN_TOP_SQUARES]
        }

        candidates = []

        for move in legal_moves:
            if (
                move.from_square not in top_squares
                or move.to_square not in top_squares
            ):
                continue

            source_change = changed.get(
                move.from_square,
                0.0
            )
            target_change = changed.get(
                move.to_square,
                0.0
            )

            if (
                source_change < HUMAN_FAST_RESCAN_THRESHOLD
                or target_change < HUMAN_FAST_RESCAN_THRESHOLD
            ):
                continue

            affected = expected_changed_squares(
                board,
                move
            )

            total_change = sum(
                changed.get(square, 0.0)
                for square in affected
            )

            candidates.append(
                (
                    total_change,
                    move
                )
            )

        if not candidates:
            time.sleep(HUMAN_FAST_RESCAN_POLL)
            continue

        candidates.sort(
            reverse=True,
            key=lambda item: item[0]
        )
        last_candidates = candidates[:HUMAN_FAST_RESCAN_TOP_MOVES]

        # Exact post-state check only on the strongest candidates.
        for _, move in last_candidates:
            ok, _ = fast_expected_post_state_confirmed(
                baseline_frame,
                frame,
                board,
                move,
                board_coords,
                black_perspective
            )

            if not ok:
                continue

            # Confirm the same candidate on one more fresh frame.
            confirm_deadline = (
                time.perf_counter()
                + HUMAN_FAST_RESCAN_CONFIRM_TIMEOUT
            )

            while (
                time.perf_counter() < confirm_deadline
            ):
                confirm_frame = capture_screen(
                    sct,
                    hwnd
                )

                if confirm_frame is None:
                    continue

                confirm_ok, confirm_reason = fast_expected_post_state_confirmed(
                    baseline_frame,
                    confirm_frame,
                    board,
                    move,
                    board_coords,
                    black_perspective
                )

                if confirm_ok:
                    # IMPORTANT: source/destination alone are not enough.
                    # The current scrcpy frame must match the complete chess
                    # position expected after this exact human move. This
                    # prevents a visually-near candidate such as Qh5 from
                    # being committed when the real screen move was Qg4/Qg5.
                    full_ok, full_reason = full_board_state_confirmed(
                        confirm_frame,
                        expected_board_after_move(board, move),
                        board_coords,
                        black_perspective
                    )

                    if full_ok:
                        progress(
                            "HUMAN",
                            (
                                f"FAST verified {move.uci()} | "
                                f"scrcpy full-board PASS 64/64"
                            ),
                            key="human_fast_verify",
                            force=True
                        )
                        return (
                            move,
                            confirm_frame
                        )

                    progress(
                        "HUMAN",
                        (
                            f"FAST rejected {move.uci()} | "
                            f"scrcpy full-board mismatch | {full_reason}"
                        ),
                        key="human_fast_reject",
                        force=True
                    )

                # Once this candidate no longer matches, don't wait the whole
                # confirmation window; another move/candidate may be visible.
                break

        time.sleep(
            HUMAN_FAST_RESCAN_POLL
        )

    return None, None


def periodic_full_board_catchup_scan(
    sct,
    hwnd,
    board,
    board_coords,
    black_perspective,
    pending_bot_move=None,
    first_frame=None,
    legal_moves=None
):
    """Recover an already-settled move from complete 64-square board state.

    This is deliberately a recovery layer, not a replacement for the normal
    temporal detector. The last committed python-chess board remains the
    reference. The screen is scanned twice; legal move hypotheses are tested
    against those observations; and the winning expected board must pass the
    existing strict full-board verifier.

    During a frozen Stockfish move, two positions are tested:
      internal -> pending Stockfish move
      internal -> pending Stockfish move -> one legal human reply

    The function only returns a verified hypothesis. It never mutates ``board``.
    """
    if board is None or board_coords is None:
        return None

    if legal_moves is None:
        legal_moves = list(board.legal_moves)

    if pending_bot_move is None and not legal_moves:
        return None

    frame_a = first_frame
    if frame_a is None:
        frame_a = capture_screen(sct, hwnd)
    if frame_a is None:
        return None

    grid_a, conf_a, scan_a_ms = scan_board(
        frame_a,
        board_coords
    )
    observed_a = grid_conf_dict(
        grid_a,
        conf_a,
        black_perspective
    )

    time.sleep(TURN_RESCAN_CONFIRM_DELAY)

    frame_b = capture_screen(sct, hwnd)
    if frame_b is None:
        return None

    grid_b, conf_b, scan_b_ms = scan_board(
        frame_b,
        board_coords
    )
    observed_b = grid_conf_dict(
        grid_b,
        conf_b,
        black_perspective
    )

    def raw_mismatch(observed, expected_board):
        count = 0
        for square in chess.SQUARES:
            observed_symbol, _ = observed.get(
                square,
                (None, 999.0)
            )
            piece = expected_board.piece_at(square)
            expected_symbol = (
                piece.symbol()
                if piece is not None
                else None
            )
            if observed_symbol != expected_symbol:
                count += 1
        return count

    def robust_mismatch(frame, observed, expected_board):
        mismatches = []
        exact = 0

        templates = get_scaled_templates(
            board_coords[2] / 8.0,
            board_coords[3] / 8.0
        )

        for square in chess.SQUARES:
            observed_symbol, observed_conf = observed.get(
                square,
                (None, 999.0)
            )
            piece = expected_board.piece_at(square)
            expected_symbol = (
                piece.symbol()
                if piece is not None
                else None
            )

            if observed_symbol == expected_symbol:
                exact += 1
                continue

            # Occupied expected squares get the same exact expected-piece
            # fallback used by strict full-board verification. This handles
            # isolated template confusion such as bishop/rook.
            if expected_symbol is not None:
                crop = get_square_crop(
                    frame,
                    board_coords,
                    square,
                    black_perspective
                )
                detected, _ = classify_square(
                    crop,
                    templates,
                    expected_symbol=expected_symbol,
                    match_threshold=FULL_BOARD_EXPECTED_MATCH_THRESHOLD
                )
                if detected == expected_symbol:
                    exact += 1
                    continue

            mismatches.append((
                square,
                expected_symbol,
                observed_symbol,
                observed_conf
            ))

        return len(mismatches), exact, mismatches

    candidates = []

    # Human turn: internal board -> one legal human move. Never use this
    # branch while a frozen/pending Stockfish move is being recovered.
    if pending_bot_move is None and board.turn in (chess.WHITE, chess.BLACK):
        for move in legal_moves:
            expected_after = expected_board_after_move(board, move)
            candidates.append({
                "kind": "HUMAN_ONLY",
                "bot_move": None,
                "human_move": move,
                "expected_board": expected_after,
                "raw_pair": raw_mismatch(observed_a, expected_after)
                    + raw_mismatch(observed_b, expected_after),
            })

    # Stockfish turn with a frozen move: test bot-only and bot+human.
    if pending_bot_move is not None:
        if not isinstance(pending_bot_move, chess.Move):
            try:
                pending_bot_move = chess.Move.from_uci(
                    str(pending_bot_move)
                )
            except Exception:
                pending_bot_move = None

    if pending_bot_move is not None and pending_bot_move in board.legal_moves:
        bot_after = expected_board_after_move(
            board,
            pending_bot_move
        )

        candidates.append({
            "kind": "BOT_ONLY",
            "bot_move": pending_bot_move,
            "human_move": None,
            "expected_board": bot_after,
            "raw_pair": raw_mismatch(observed_a, bot_after)
                + raw_mismatch(observed_b, bot_after),
        })

        for human_move in bot_after.legal_moves:
            final_board = expected_board_after_move(
                bot_after,
                human_move
            )
            candidates.append({
                "kind": "BOT_PLUS_HUMAN",
                "bot_move": pending_bot_move,
                "human_move": human_move,
                "expected_board": final_board,
                "raw_pair": raw_mismatch(observed_a, final_board)
                    + raw_mismatch(observed_b, final_board),
            })

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: item["raw_pair"]
    )

    evaluated = []
    for item in candidates[:TURN_RESCAN_TOP_CANDIDATES]:
        ma, ea, da = robust_mismatch(
            frame_a,
            observed_a,
            item["expected_board"]
        )
        mb, eb, db = robust_mismatch(
            frame_b,
            observed_b,
            item["expected_board"]
        )

        ranked = dict(item)
        ranked.update({
            "mismatch_a": ma,
            "mismatch_b": mb,
            "exact_a": ea,
            "exact_b": eb,
            "details_a": da,
            "details_b": db,
            "score": ma * 100 + mb * 100 - ea - eb,
        })
        evaluated.append(ranked)

    evaluated.sort(
        key=lambda item: (item["score"], item["raw_pair"])
    )

    best = evaluated[0]
    second_score = (
        evaluated[1]["score"]
        if len(evaluated) > 1
        else 999999
    )
    margin = second_score - best["score"]

    if (
        best["mismatch_a"] > TURN_RESCAN_MAX_MISMATCH
        or best["mismatch_b"] > TURN_RESCAN_MAX_MISMATCH
    ):
        preview = " ".join(
            f"{chess.square_name(sq)}:{exp or '-'}->{obs or '-'}({conf:.3f})"
            for sq, exp, obs, conf in best["details_b"][:6]
        )
        progress(
            "RECOVERY",
            (
                f"2s FULL RESCAN | WAITING | best={best['kind']} "
                f"bot={best['bot_move'].uci() if best['bot_move'] else '-'} "
                f"human={best['human_move'].uci() if best['human_move'] else '-'} "
                f"A={best['mismatch_a']}/64 B={best['mismatch_b']}/64 "
                f"preview={preview or '-'} "
                f"scan={scan_a_ms:.1f}/{scan_b_ms:.1f}ms"
            ),
            key="turn_rescan_wait",
            force=True
        )
        return None

    full_ok, full_reason = full_board_state_confirmed(
        frame_b,
        best["expected_board"],
        board_coords,
        black_perspective
    )

    if not full_ok:
        progress(
            "RECOVERY",
            (
                f"2s FULL RESCAN | candidate rejected | "
                f"bot={best['bot_move'].uci() if best['bot_move'] else '-'} "
                f"human={best['human_move'].uci() if best['human_move'] else '-'} | "
                f"{full_reason}"
            ),
            key="turn_rescan_reject",
            force=True
        )
        return None

    progress(
        "RECOVERY",
        (
            f"2s FULL RESCAN VERIFIED | kind={best['kind']} "
            f"bot={best['bot_move'].uci() if best['bot_move'] else '-'} "
            f"human={best['human_move'].uci() if best['human_move'] else '-'} "
            f"A={best['exact_a']}/64 B={best['exact_b']}/64 "
            f"margin={margin:.0f} scan={scan_a_ms:.1f}/{scan_b_ms:.1f}ms"
        ),
        key="turn_rescan_verify",
        force=True
    )

    return {
        "kind": best["kind"],
        "bot_move": best["bot_move"],
        "human_move": best["human_move"],
        "frame": frame_b,
        "reason": (
            "2-second full-board rescan + two-frame legal-state match + "
            "strict full-board verification"
        ),
    }


def ultra_board_delta_recovery(
    sct,
    hwnd,
    board,
    baseline_frame,
    board_coords,
    black_perspective,
    legal_moves,
    first_frame=None
):
    """Recover a missed human move from the full-board state delta.

    The last committed internal board is treated as the reference position.
    We scan the current board, find which squares differ from that internal
    position, and ask python-chess which legal move best explains those exact
    differences. A second independent frame must support the same move.

    Motion is used as an additional signal, but a settled final position can
    still be accepted when the temporal motion signal is weak: the unchanged
    final board is cross-validated against the internal board and a second
    full scan before the move is declared.
    """
    if baseline_frame is None or not legal_moves:
        return None, None

    frame = first_frame
    if frame is None:
        frame = capture_screen(sct, hwnd)
    if frame is None:
        return None, None

    def scan_observation(scan_frame):
        grid, confidence, scan_ms = scan_board(
            scan_frame,
            board_coords
        )
        observed = grid_conf_dict(
            grid,
            confidence,
            black_perspective
        )
        return observed, confidence, scan_ms

    observed_a, confidence_a, scan_a_ms = scan_observation(frame)

    internal_symbols = {
        square: (
            board.piece_at(square).symbol()
            if board.piece_at(square) is not None
            else None
        )
        for square in chess.SQUARES
    }

    # Differences between the physical board and the last committed internal
    # board. Confidence is retained so a weak template mismatch does not get
    # treated as hard evidence against a candidate move.
    diff_a = {}
    for square in chess.SQUARES:
        observed_symbol, observed_conf = observed_a.get(
            square,
            (None, 999.0)
        )
        expected_symbol = internal_symbols[square]
        if observed_symbol == expected_symbol:
            continue
        if (
            observed_symbol is None
            or expected_symbol is None
            or observed_conf <= HUMAN_ULTRA_DELTA_CONF_MAX
        ):
            diff_a[square] = (
                observed_symbol,
                observed_conf
            )

    if len(diff_a) < HUMAN_ULTRA_DELTA_MIN_EXACT:
        progress(
            "HUMAN",
            (
                f"ULTRA DELTA | internal-vs-screen changed="
                f"{', '.join(chess.square_name(sq) for sq in diff_a) or '-'} "
                "| insufficient changed squares; WAITING"
            ),
            key="human_ultra_delta_wait",
            force=True
        )
        return None, None

    time.sleep(HUMAN_ULTRA_DELTA_CONFIRM_DELAY)
    frame_b = capture_screen(sct, hwnd)
    if frame_b is None:
        return None, None
    observed_b, confidence_b, scan_b_ms = scan_observation(frame_b)

    diff_b = {}
    for square in chess.SQUARES:
        observed_symbol, observed_conf = observed_b.get(
            square,
            (None, 999.0)
        )
        expected_symbol = internal_symbols[square]
        if observed_symbol == expected_symbol:
            continue
        if (
            observed_symbol is None
            or expected_symbol is None
            or observed_conf <= HUMAN_ULTRA_DELTA_CONF_MAX
        ):
            diff_b[square] = (
                observed_symbol,
                observed_conf
            )

    def candidate_metrics(observed, move, diff_squares):
        expected_after = expected_board_after_move(
            board,
            move
        )
        affected = set(expected_changed_squares(board, move))

        exact_affected = 0
        changed_affected = 0
        missing = 0
        extra = 0
        after_mismatch = 0

        for square in chess.SQUARES:
            observed_symbol, observed_conf = observed.get(
                square,
                (None, 999.0)
            )
            expected_symbol = (
                expected_after.piece_at(square).symbol()
                if expected_after.piece_at(square) is not None
                else None
            )

            if observed_symbol == expected_symbol:
                if square in affected:
                    exact_affected += 1
                continue

            # Count a board-state mismatch only when the classifier has some
            # usable confidence. Very weak classifications are treated as
            # uncertain rather than hard evidence against the candidate.
            if (
                observed_symbol is not None
                and observed_conf > HUMAN_ULTRA_DELTA_CONF_MAX
            ):
                continue

            after_mismatch += 1
            if square in affected:
                changed_affected += 1

        for square in affected:
            observed_symbol, observed_conf = observed.get(
                square,
                (None, 999.0)
            )
            expected_symbol = (
                expected_after.piece_at(square).symbol()
                if expected_after.piece_at(square) is not None
                else None
            )

            if observed_symbol != expected_symbol:
                missing += 1

        for square in diff_squares:
            if square not in affected:
                extra += 1

        # Strong reward for explaining the exact source/destination change;
        # missing/extra changed squares are penalized but tolerated slightly
        # because the full-board template classifier can be imperfect.
        score = (
            exact_affected * 28.0
            + changed_affected * 8.0
            - missing * 10.0
            - extra * 7.0
            - after_mismatch * 1.25
        )

        return {
            "score": score,
            "affected": affected,
            "exact_affected": exact_affected,
            "changed_affected": changed_affected,
            "missing": missing,
            "extra": extra,
            "after_mismatch": after_mismatch,
            "expected_after": expected_after,
        }

    # Rank legal moves by how well their expected resulting position explains
    # the observed internal-board delta. This is independent of the engine's
    # predicted reply, so a surprising but legal human move can still be found.
    candidates_a = []

    for move in legal_moves:
        ma = candidate_metrics(observed_a, move, diff_a)
        mb = candidate_metrics(observed_b, move, diff_b)
        combined = ma["score"] + mb["score"]
        candidates_a.append((combined, move, ma, mb))

    candidates_a.sort(
        reverse=True,
        key=lambda item: item[0]
    )

    if not candidates_a:
        return None, None

    best_total, best_move, best_a, best_b = candidates_a[0]
    second_total = (
        candidates_a[1][0]
        if len(candidates_a) > 1
        else -999.0
    )
    margin = best_total - second_total

    # The moved squares must be visible as actual differences from the
    # internal board in both frames, and the expected post-state must explain
    # those differences in both scans.
    required_exact = max(
        HUMAN_ULTRA_DELTA_MIN_EXACT,
        len(best_a["affected"]) - 1
    )

    changed_names = ','.join(
        chess.square_name(square)
        for square in sorted(diff_a)
    )
    changed_names_b = ','.join(
        chess.square_name(square)
        for square in sorted(diff_b)
    )

    motion = fast_square_motion_scores(
        baseline_frame,
        frame_b,
        board_coords,
        black_perspective
    )
    source_motion = (
        motion.get(best_move.from_square, 0.0)
        if motion is not None
        else 0.0
    )
    target_motion = (
        motion.get(best_move.to_square, 0.0)
        if motion is not None
        else 0.0
    )
    motion_total = source_motion + target_motion

    progress(
        "HUMAN",
        (
            f"ULTRA DELTA | internal-change={changed_names} "
            f"confirm-change={changed_names_b} "
            f"candidate={best_move.uci()} "
            f"A={best_a['exact_affected']}/{len(best_a['affected'])} "
            f"B={best_b['exact_affected']}/{len(best_b['affected'])} "
            f"missing={best_a['missing']}/{best_b['missing']} "
            f"extra={best_a['extra']}/{best_b['extra']} "
            f"margin={margin:.2f} "
            f"motion={motion_total:.4f} "
            f"scan={scan_a_ms:.1f}/{scan_b_ms:.1f}ms"
        ),
        key="human_ultra_delta_candidate",
        force=True
    )

    if (
        best_a["exact_affected"] < required_exact
        or best_b["exact_affected"] < required_exact
        or best_a["missing"] > HUMAN_ULTRA_DELTA_MAX_MISSING
        or best_b["missing"] > HUMAN_ULTRA_DELTA_MAX_MISSING
        or best_a["extra"] > HUMAN_ULTRA_DELTA_MAX_EXTRA
        or best_b["extra"] > HUMAN_ULTRA_DELTA_MAX_EXTRA
        or margin < HUMAN_ULTRA_DELTA_MARGIN
    ):
        progress(
            "HUMAN",
            "ULTRA DELTA | candidate not sufficiently explained; continuing WAITING",
            key="human_ultra_delta_wait",
            force=True
        )
        return None, None

    # Static final-state cross-check. This is deliberately independent from
    # the normal motion classifier so an already-settled fast human move can
    # still be recovered.
    full_ok, full_reason = full_board_state_confirmed(
        frame_b,
        best_a["expected_after"],
        board_coords,
        black_perspective
    )

    motion_supported = (
        source_motion >= HUMAN_ULTRA_DELTA_MOTION_FLOOR
        or target_motion >= HUMAN_ULTRA_DELTA_MOTION_FLOOR
    )

    if not full_ok:
        progress(
            "HUMAN",
            (
                f"ULTRA DELTA | state rejected {best_move.uci()} | "
                f"{full_reason}"
            ),
            key="human_ultra_delta_reject",
            force=True
        )
        return None, None

    # The full-board state and two-scan delta already provide strong physical
    # evidence. Motion is a useful extra signal when available, but it is not
    # mandatory for a move that is visibly settled and stable in both scans.
    progress(
        "HUMAN",
        (
            f"ULTRA DELTA VERIFIED {best_move.uci()} | "
            f"internal-board delta + dual scan + full-board "
            f"state PASS | motion={'YES' if motion_supported else 'WEAK'}"
        ),
        key="human_ultra_delta_verify",
        force=True
    )

    return best_move, frame_b


def ultra_human_background_rescan(
    sct,
    hwnd,
    board,
    baseline_frame,
    board_coords,
    black_perspective,
    legal_moves
):
    """Full-board recovery pass for a human move missed by fast detection.

    Detector 1: vectorized board motion identifies the squares that really
    changed and keeps only legal moves whose source and destination both moved.

    Detector 2: one complete 64-square scan checks the resulting position
    against each motion candidate. Only a move passing both detectors is then
    sent through the existing physical verification gate.
    """
    if baseline_frame is None or not legal_moves:
        return None, None

    ultra_start = time.perf_counter()
    frame = capture_screen(sct, hwnd)
    if frame is None:
        return None, None

    changed = fast_square_motion_scores(
        baseline_frame,
        frame,
        board_coords,
        black_perspective
    )

    if changed is None:
        return None, None

    changed_ranked = sorted(
        (
            (score, square)
            for square, score in changed.items()
            if score >= HUMAN_ULTRA_CHANGE_THRESHOLD
        ),
        reverse=True,
        key=lambda item: item[0]
    )

    if len(changed_ranked) < 2:
        delta_move, delta_frame = ultra_board_delta_recovery(
            sct,
            hwnd,
            board,
            baseline_frame,
            board_coords,
            black_perspective,
            legal_moves,
            first_frame=frame
        )
        if delta_move is not None and delta_frame is not None:
            detect_human_move._last_detection_source = "ULTRA_DELTA"
            return delta_move, delta_frame

        progress(
            "HUMAN",
            "ULTRA RESCAN | no board motion detected; continuing WAITING",
            key="human_ultra_wait",
            force=True
        )
        return None, None

    top_squares = {
        square
        for _, square in changed_ranked[:HUMAN_ULTRA_TOP_SQUARES]
    }

    motion_candidates = []

    for move in legal_moves:
        source_change = changed.get(move.from_square, 0.0)
        target_change = changed.get(move.to_square, 0.0)

        if (
            move.from_square not in top_squares
            or move.to_square not in top_squares
            or source_change < HUMAN_ULTRA_MOTION_MIN
            or target_change < HUMAN_ULTRA_MOTION_MIN
        ):
            continue

        affected = expected_changed_squares(board, move)
        total_motion = sum(
            changed.get(square, 0.0)
            for square in affected
        )

        motion_candidates.append(
            (total_motion, move, source_change, target_change)
        )

    if not motion_candidates:
        delta_move, delta_frame = ultra_board_delta_recovery(
            sct,
            hwnd,
            board,
            baseline_frame,
            board_coords,
            black_perspective,
            legal_moves,
            first_frame=frame
        )
        if delta_move is not None and delta_frame is not None:
            detect_human_move._last_detection_source = "ULTRA_DELTA"
            return delta_move, delta_frame

        progress(
            "HUMAN",
            "ULTRA RESCAN | board changed, but no legal source->target motion pair",
            key="human_ultra_wait",
            force=True
        )
        return None, None

    motion_candidates.sort(reverse=True, key=lambda item: item[0])
    motion_candidates = motion_candidates[:HUMAN_ULTRA_TOP_MOVES]

    # Detector 2: full-board scan. This is deliberately performed only when
    # real board motion was already found, so a static board does not pay this
    # cost every time the normal waiting loop runs.
    grid, confidence, scan_ms = scan_board(
        frame,
        board_coords
    )

    best_scan = None
    for total_motion, move, source_change, target_change in motion_candidates:
        hypothesis = board_hypothesis_score(
            board,
            move,
            grid,
            confidence,
            black_perspective
        )

        score = (
            hypothesis["normalized"] * 100.0
            + min(18.0, total_motion * 70.0)
            + hypothesis["exact"] * 0.12
            - hypothesis["mismatch"] * 0.025
        )

        item = (
            score,
            move,
            hypothesis,
            total_motion,
            source_change,
            target_change
        )

        if best_scan is None or score > best_scan[0]:
            best_scan = item

    if best_scan is None:
        return None, None

    best_score, best_move, best_hypothesis, total_motion, source_change, target_change = best_scan
    second_scores = []

    for total_motion_i, move_i, source_i, target_i in motion_candidates:
        if move_i == best_move:
            continue
        hypothesis_i = board_hypothesis_score(
            board,
            move_i,
            grid,
            confidence,
            black_perspective
        )
        score_i = (
            hypothesis_i["normalized"] * 100.0
            + min(18.0, total_motion_i * 70.0)
            + hypothesis_i["exact"] * 0.12
            - hypothesis_i["mismatch"] * 0.025
        )
        second_scores.append(score_i)

    second_score = max(second_scores) if second_scores else -999.0
    margin = best_score - second_score

    progress(
        "HUMAN",
        (
            f"ULTRA RESCAN | changed={len(changed_ranked)} "
            f"candidate={best_move.uci()} "
            f"motion={total_motion:.4f} "
            f"src={source_change:.4f} "
            f"dst={target_change:.4f} "
            f"board={best_hypothesis['normalized']:.3f} "
            f"margin={margin:.2f} scan={scan_ms:.1f}ms"
        ),
        key="human_ultra_candidate",
        force=True
    )

    # Final safety detector: exact expected source/destination state and no
    # strong unexpected motion. This prevents a random animation/highlight from
    # being declared as a chess move.
    if (
        source_change < HUMAN_ULTRA_MOTION_MIN
        or target_change < HUMAN_ULTRA_MOTION_MIN
        or best_hypothesis["normalized"] < 0.62
        or margin < HUMAN_ULTRA_MOVE_MARGIN
    ):
        delta_move, delta_frame = ultra_board_delta_recovery(
            sct,
            hwnd,
            board,
            baseline_frame,
            board_coords,
            black_perspective,
            legal_moves,
            first_frame=frame
        )
        if delta_move is not None and delta_frame is not None:
            detect_human_move._last_detection_source = "ULTRA_DELTA"
            return delta_move, delta_frame

        progress(
            "HUMAN",
            "ULTRA RESCAN | candidate not strong enough; continuing WAITING",
            key="human_ultra_wait",
            force=True
        )
        return None, None

    post_ok, post_reason = fast_expected_post_state_confirmed(
        baseline_frame,
        frame,
        board,
        best_move,
        board_coords,
        black_perspective
    )

    full_ok, full_reason = full_board_state_confirmed(
        frame,
        expected_board_after_move(board, best_move),
        board_coords,
        black_perspective
    )

    if not post_ok or not full_ok:
        delta_move, delta_frame = ultra_board_delta_recovery(
            sct,
            hwnd,
            board,
            baseline_frame,
            board_coords,
            black_perspective,
            legal_moves,
            first_frame=frame
        )
        if delta_move is not None and delta_frame is not None:
            detect_human_move._last_detection_source = "ULTRA_DELTA"
            return delta_move, delta_frame

        progress(
            "HUMAN",
            (
                f"ULTRA RESCAN | rejected {best_move.uci()} | "
                f"motion={'PASS' if post_ok else post_reason}; "
                f"full={'PASS' if full_ok else full_reason}"
            ),
            key="human_ultra_reject",
            force=True
        )
        time.sleep(HUMAN_ULTRA_SCAN_COOLDOWN)
        return None, None

    # Re-use the existing physical verification gate one final time. It still
    # returns only after the screen itself confirms the move, and the caller
    # pushes the move only after receiving this verified frame.
    physical_ok, verified_frame, physical_reason = verify_human_move_on_screen(
        sct,
        hwnd,
        expected_board_after_move(board, best_move),
        baseline_frame,
        board_coords,
        black_perspective,
        best_move,
        board.copy(stack=False)
    )

    if not physical_ok:
        delta_move, delta_frame = ultra_board_delta_recovery(
            sct,
            hwnd,
            board,
            baseline_frame,
            board_coords,
            black_perspective,
            legal_moves,
            first_frame=frame
        )
        if delta_move is not None and delta_frame is not None:
            detect_human_move._last_detection_source = "ULTRA_DELTA"
            return delta_move, delta_frame

        progress(
            "HUMAN",
            (
                f"ULTRA RESCAN | physical verification rejected "
                f"{best_move.uci()} | {physical_reason}"
            ),
            key="human_ultra_reject",
            force=True
        )
        return None, None

    progress(
        "HUMAN",
        (
            f"ULTRA VERIFIED {best_move.uci()} | "
            f"motion + full-board + physical verification passed | "
            f"total={time.perf_counter() - ultra_start:.3f}s"
        ),
        key="human_ultra_verify",
        force=True
    )

    return (
        best_move,
        verified_frame if verified_frame is not None else frame
    )


def detect_human_move(
    sct,
    hwnd,
    board,
    baseline_frame,
    board_coords,
    black_perspective
):
    if baseline_frame is None:
        return None, None

    start = time.perf_counter()
    detect_human_move._last_detection_source = None

    # Keep the ultra-rescan schedule across repeated calls to this function.
    # The main loop calls detect_human_move() in short chunks; this state makes
    # the recovery pass happen every ~2 seconds for the same human turn.
    position_key = board.fen()
    state = getattr(detect_human_move, "_ultra_state", None)
    if state is None or state.get("position_key") != position_key:
        state = {
            "position_key": position_key,
            "turn_started": time.perf_counter(),
            "next_ultra": time.perf_counter() + HUMAN_ULTRA_RESCAN_INTERVAL,
        }
        detect_human_move._ultra_state = state

    progress(
        "HUMAN",
        "starting move scanner",
        key="human_stage",
        force=True
    )

    confirmations = {}
    last_candidate = None
    last_scan_time = 0.0
    last_fallback_scan = 0.0

    # SPEED OPTIMIZATION:
    # Legal moves do not change while the same board position is being
    # observed, so calculate them once for this detection session.
    legal_moves = list(
        board.legal_moves
    )

    # After the normal detector has had its chance for the current human turn,
    # run the scheduled ultra recovery pass at the beginning of the next scan
    # chunk. Keeping this check outside the 1.25s local loop guarantees the
    # recovery pass is not starved between repeated detector calls.
    now = time.perf_counter()
    if now >= state["next_ultra"]:
        # EXTRA 2-second complete-board recovery. It is intentionally before
        # the existing motion-based ultra pass so an already-settled move
        # can still be reconstructed from the current board state.
        catchup = periodic_full_board_catchup_scan(
            sct,
            hwnd,
            board,
            board_coords,
            black_perspective,
            pending_bot_move=None,
            first_frame=None,
            legal_moves=legal_moves
        )
        state["next_ultra"] = now + HUMAN_ULTRA_RESCAN_INTERVAL

        if catchup is not None and catchup["kind"] == "HUMAN_ONLY":
            detect_human_move._last_detection_source = "PERIODIC_FULL_RESCAN"
            return catchup["human_move"], catchup["frame"]

        ultra_move, ultra_frame = ultra_human_background_rescan(
            sct,
            hwnd,
            board,
            baseline_frame,
            board_coords,
            black_perspective,
            legal_moves
        )
        if ultra_move is not None and ultra_frame is not None:
            return ultra_move, ultra_frame

    # Fast rescan FIRST. This catches a real human move without waiting for
    # the slower legacy rank/64-square template pipeline.
    fast_move, fast_frame = fast_human_move_rescan(
        sct,
        hwnd,
        board,
        baseline_frame,
        board_coords,
        black_perspective,
        legal_moves
    )

    if (
        fast_move is not None
        and fast_frame is not None
    ):
        return fast_move, fast_frame

    while (
        time.perf_counter() - start
        < HUMAN_MOVE_TIMEOUT
    ):
        now = time.perf_counter()

        frame = capture_screen(
            sct,
            hwnd
        )

        if frame is None:
            time.sleep(
                SCAN_INTERVAL
            )
            continue

        ranked = rank_changed_squares(
            baseline_frame,
            frame,
            board_coords,
            black_perspective
        )

        strong_change = (
            len(ranked) >= 2
            and ranked[0][0] >= HUMAN_FALLBACK_CHANGE_THRESHOLD
            and ranked[1][0] >= HUMAN_FALLBACK_CHANGE_THRESHOLD
        )

        fallback_mode = False

        # --------------------------------------------------------
        # NORMAL PATH
        # --------------------------------------------------------
        if strong_change:
            settled = get_settled_frame(
                sct,
                hwnd,
                frame,
                timeout=HUMAN_SETTLE_TIMEOUT
            )

            candidate_frame = (
                settled
                if settled is not None
                else frame
            )

            grid, confidence, scan_ms = scan_board(
                candidate_frame,
                board_coords
            )

            last_scan_time = scan_ms

            candidates = []

            for move in legal_moves:
                (
                    transition_total,
                    transition_min,
                    transition_values
                ) = move_transition_strength(
                    baseline_frame,
                    candidate_frame,
                    board,
                    move,
                    board_coords,
                    black_perspective
                )

                if transition_total < 0.004:
                    continue

                hypothesis = board_hypothesis_score(
                    board,
                    move,
                    grid,
                    confidence,
                    black_perspective
                )

                combined = (
                    hypothesis["normalized"] * 100.0
                    + min(
                        12.0,
                        transition_total * 45.0
                    )
                    + hypothesis["exact"] * 0.08
                    - hypothesis["mismatch"] * 0.03
                )

                candidates.append(
                    (
                        combined,
                        move,
                        hypothesis,
                        transition_values
                    )
                )

        # --------------------------------------------------------
        # TARGETED FALLBACK
        # --------------------------------------------------------
        else:
            now = time.perf_counter()

            if (
                now - last_fallback_scan
                < HUMAN_FALLBACK_SCAN_INTERVAL
            ):
                progress(
                    "HUMAN",
                    (
                        f"scanning... "
                        f"{now - start:.2f}s | "
                        "waiting for stable move"
                    ),
                    key="human_loop"
                )

                time.sleep(
                    SCAN_INTERVAL
                )

                continue

            last_fallback_scan = now

            top_squares = [
                square
                for score, square in ranked[
                    :HUMAN_FALLBACK_TOP_SQUARES
                ]
                if score >= HUMAN_FALLBACK_CHANGE_THRESHOLD
            ]

            if not top_squares:
                progress(
                    "HUMAN",
                    (
                        f"scanning... "
                        f"{now - start:.2f}s | "
                        "no stable move yet"
                    ),
                    key="human_loop"
                )

                time.sleep(
                    SCAN_INTERVAL
                )

                continue

            fallback_moves = []

            for move in legal_moves:
                if (
                    move.from_square not in top_squares
                    and move.to_square not in top_squares
                ):
                    continue

                (
                    transition_total,
                    transition_min,
                    transition_values
                ) = move_transition_strength(
                    baseline_frame,
                    frame,
                    board,
                    move,
                    board_coords,
                    black_perspective
                )

                source_change = transition_values.get(
                    move.from_square,
                    0.0
                )

                target_change = transition_values.get(
                    move.to_square,
                    0.0
                )

                if (
                    source_change
                    < HUMAN_FALLBACK_CHANGE_THRESHOLD
                    or
                    target_change
                    < HUMAN_FALLBACK_CHANGE_THRESHOLD
                ):
                    continue

                fallback_moves.append(
                    (
                        transition_total,
                        move,
                        transition_values
                    )
                )

            if not fallback_moves:
                progress(
                    "HUMAN",
                    (
                        f"scanning... "
                        f"{now - start:.2f}s | "
                        "no targeted recovery candidate"
                    ),
                    key="human_loop"
                )

                time.sleep(
                    SCAN_INTERVAL
                )

                continue

            candidate_frame = frame

            grid, confidence, scan_ms = scan_board(
                candidate_frame,
                board_coords
            )

            last_scan_time = scan_ms

            fallback_mode = True
            candidates = []

            for (
                transition_total,
                move,
                transition_values
            ) in fallback_moves:

                hypothesis = board_hypothesis_score(
                    board,
                    move,
                    grid,
                    confidence,
                    black_perspective
                )

                combined = (
                    hypothesis["normalized"] * 100.0
                    + min(
                        14.0,
                        transition_total * 60.0
                    )
                    + hypothesis["exact"] * 0.10
                    - hypothesis["mismatch"] * 0.025
                )

                candidates.append(
                    (
                        combined,
                        move,
                        hypothesis,
                        transition_values
                    )
                )

        if not candidates:
            time.sleep(
                SCAN_INTERVAL
            )
            continue

        candidates.sort(
            reverse=True,
            key=lambda item: item[0]
        )

        (
            best_score,
            best_move,
            best_hypothesis,
            best_transition
        ) = candidates[0]

        progress(
            "HUMAN",
            (
                f"candidate={best_move.uci()} "
                f"score={best_score:.2f} "
                f"board={best_hypothesis['normalized']:.3f} "
                f"candidates={len(candidates)}"
                + (
                    " fallback"
                    if fallback_mode
                    else ""
                )
            ),
            key="human_candidate",
            interval=0.45
        )

        second_score = (
            candidates[1][0]
            if len(candidates) > 1
            else -999.0
        )

        margin = (
            best_score
            - second_score
        )

        piece_type = human_piece_type(
            board,
            best_move
        )

        is_pawn_or_rook = (
            piece_type
            in (
                chess.PAWN,
                chess.ROOK
            )
        )

        if fallback_mode:
            source_change = best_transition.get(
                best_move.from_square,
                0.0
            )

            target_change = best_transition.get(
                best_move.to_square,
                0.0
            )

            candidate_ok = (
                best_hypothesis["normalized"] >= 0.70
                and margin >= 1.0
                and source_change >= HUMAN_FALLBACK_CHANGE_THRESHOLD
                and target_change >= HUMAN_FALLBACK_CHANGE_THRESHOLD
            )

        else:
            candidate_ok = (
                best_hypothesis["normalized"] >= 0.74
                and margin >= 1.0
                and len(best_transition) >= 2
            )

        if candidate_ok:
            key = best_move.uci()

            if key == last_candidate:
                confirmations[key] = (
                    confirmations.get(key, 0)
                    + 1
                )
            else:
                confirmations = {
                    key: 1
                }

                last_candidate = key

            if (
                confirmations[key]
                >= HUMAN_CONFIRM_SAMPLES
            ):
                final_frame = get_settled_frame(
                    sct,
                    hwnd,
                    candidate_frame,
                    timeout=HUMAN_SETTLE_TIMEOUT
                )

                if final_frame is None:
                    final_frame = candidate_frame

                (
                    final_grid,
                    final_confidence,
                    final_scan_ms
                ) = scan_board(
                    final_frame,
                    board_coords
                )

                final_hypothesis = board_hypothesis_score(
                    board,
                    best_move,
                    final_grid,
                    final_confidence,
                    black_perspective
                )

                if (
                    final_hypothesis["normalized"]
                    >= 0.72
                ):
                    expected_human_board = expected_board_after_move(
                        board,
                        best_move
                    )

                    (
                        physical_ok,
                        verified_frame,
                        physical_reason
                    ) = verify_human_move_on_screen(
                        sct,
                        hwnd,
                        expected_human_board,
                        baseline_frame,
                        board_coords,
                        black_perspective,
                        best_move,
                        board.copy(stack=False)
                    )

                    if physical_ok:
                        progress(
                            "HUMAN",
                            (
                                f"verified {best_move.uci()} | "
                                f"{physical_reason}"
                            ),
                            key="human_stage",
                            force=True
                        )

                        return (
                            best_move,
                            verified_frame
                            if verified_frame is not None
                            else final_frame
                        )

                    progress(
                        "HUMAN",
                        (
                            f"candidate {best_move.uci()} rejected by "
                            f"physical board check: {physical_reason}"
                        ),
                        key="human_physical_reject",
                        force=True
                    )

                if is_pawn_or_rook:
                    templates = get_scaled_templates(
                        board_coords[2] / 8.0,
                        board_coords[3] / 8.0
                    )

                    (
                        transition_total,
                        _,
                        final_transition
                    ) = move_transition_strength(
                        baseline_frame,
                        final_frame,
                        board,
                        best_move,
                        board_coords,
                        black_perspective
                    )

                    final_source_change = (
                        final_transition.get(
                            best_move.from_square,
                            0.0
                        )
                    )

                    final_target_change = (
                        final_transition.get(
                            best_move.to_square,
                            0.0
                        )
                    )

                    (
                        direct_ok,
                        direct_reason
                    ) = human_direct_state_confirmed(
                        final_frame,
                        board,
                        best_move,
                        board_coords,
                        black_perspective,
                        templates
                    )

                    if (
                        direct_ok
                        and transition_total >= 0.0025
                        and final_source_change
                        >= HUMAN_FALLBACK_CHANGE_THRESHOLD
                        and final_target_change
                        >= HUMAN_FALLBACK_CHANGE_THRESHOLD
                        and final_hypothesis["normalized"]
                        >= 0.68
                    ):
                        expected_human_board = expected_board_after_move(
                            board,
                            best_move
                        )

                        (
                            physical_ok,
                            verified_frame,
                            physical_reason
                        ) = verify_human_move_on_screen(
                            sct,
                            hwnd,
                            expected_human_board,
                            baseline_frame,
                            board_coords,
                            black_perspective,
                            best_move,
                            board.copy(stack=False)
                        )

                        if physical_ok:
                            progress(
                                "HUMAN",
                                (
                                    f"verified "
                                    f"{best_move.uci()} "
                                    "via pawn/rook recovery | "
                                    f"{physical_reason}"
                                ),
                                key="human_stage",
                                force=True
                            )

                            return (
                                best_move,
                                verified_frame
                                if verified_frame is not None
                                else final_frame
                            )

                        progress(
                            "HUMAN",
                            (
                                f"pawn/rook candidate {best_move.uci()} "
                                "rejected by physical board check: "
                                f"{physical_reason}"
                            ),
                            key="human_physical_reject",
                            force=True
                        )

                progress(
                    "HUMAN",
                    (
                        f"candidate {best_move.uci()} "
                        "failed final check: "
                        f"{final_hypothesis['normalized']:.3f}"
                    ),
                    key="human_final"
                )

        time.sleep(
            SCAN_INTERVAL
        )

    return None, None


def get_settled_frame(
    sct,
    hwnd,
    first_frame,
    timeout=0.10
):
    start = time.perf_counter()

    progress(
        "SETTLE",
        (
            "waiting for stable frame "
            f"({timeout:.2f}s)"
        ),
        key="settle",
        force=True
    )

    previous = first_frame
    stable_count = 0
    last = first_frame

    while (
        time.perf_counter() - start
        < timeout
    ):
        frame = capture_screen(
            sct,
            hwnd
        )

        if frame is None:
            continue

        change = board_frame_change_score(
            previous,
            frame
        )

        last = frame

        if change < 0.0015:
            stable_count += 1
        else:
            stable_count = 0

        progress(
            "SETTLE",
            (
                f"change={change:.4f} "
                f"stable={stable_count}/2"
            ),
            key="settle_loop",
            interval=0.10
        )

        if stable_count >= 2:
            progress(
                "SETTLE",
                "stable frame acquired",
                key="settle",
                force=True
            )

            return frame

        previous = frame

    progress(
        "SETTLE",
        "timeout; using latest frame",
        key="settle",
        force=True
    )

    return last


def opponent_recent_accuracy(
    match_history
):
    if not match_history:
        return None, 0

    recent = match_history[
        -OPPONENT_ACCURACY_WINDOW:
    ]

    n = len(recent)

    weights = list(
        range(1, n + 1)
    )

    total_weight = float(
        sum(weights)
    )

    weighted = sum(
        score * weight
        for score, weight
        in zip(
            recent,
            weights
        )
    )

    return (
        weighted / total_weight,
        n
    )


