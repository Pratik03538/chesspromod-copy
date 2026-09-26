# Exact function source extracted from original main.py.

def get_scaled_templates(sq_w, sq_h):
    global cached_sq_size, cached_templates

    key = (int(sq_w), int(sq_h))

    if key == cached_sq_size and cached_templates:
        return cached_templates

    scaled = {}
    scales = (0.60, 0.70, 0.80, 0.90)

    for symbol, img in RAW_TEMPLATES.items():
        h, w = img.shape[:2]

        if h <= 0 or w <= 0:
            continue

        scaled[symbol] = []
        aspect = w / float(h)

        for scale in scales:
            target_h = max(5, int(sq_h * scale))
            target_w = max(5, int(target_h * aspect))

            resized = cv2.resize(
                img,
                (target_w, target_h),
                interpolation=cv2.INTER_AREA
            )

            gray = cv2.cvtColor(
                resized[:, :, :3],
                cv2.COLOR_BGR2GRAY
            )

            _, mask = cv2.threshold(
                resized[:, :, 3],
                80,
                255,
                cv2.THRESH_BINARY
            )

            scaled[symbol].append({
                "gray": gray,
                "mask": mask,
                "size": (target_w, target_h)
            })

    cached_sq_size = key
    cached_templates = scaled
    return scaled


def get_scrcpy_screen_origin(hwnd):
    if not hwnd or not user32:
        return None

    rect = wintypes.RECT()

    if not user32.GetClientRect(
        hwnd,
        ctypes.byref(rect)
    ):
        return None

    point = wintypes.POINT(0, 0)

    if not user32.ClientToScreen(
        hwnd,
        ctypes.byref(point)
    ):
        return None

    return int(point.x), int(point.y)


def left_click_screen(x, y):
    # Direct Win32 dispatch. No artificial cursor/hold sleeps.
    user32.SetCursorPos(int(x), int(y))
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
    return True


def capture_screen(sct, hwnd=None):
    if hwnd and user32 and user32.IsWindow(hwnd):
        rect = wintypes.RECT()

        user32.GetClientRect(
            hwnd,
            ctypes.byref(rect)
        )

        point = wintypes.POINT(
            rect.left,
            rect.top
        )

        user32.ClientToScreen(
            hwnd,
            ctypes.byref(point)
        )

        width = rect.right - rect.left
        height = rect.bottom - rect.top

        if width <= 0 or height <= 0:
            return None

        raw = np.asarray(
            sct.grab({
                "left": point.x,
                "top": point.y,
                "width": width,
                "height": height
            })
        )

    else:
        raw = np.asarray(
            sct.grab(
                sct.monitors[1]
            )
        )

    return raw[:, :, :3].copy()


def classify_square(
    img_crop,
    current_templates,
    expected_symbol=None,
    match_threshold=MATCH_THRESHOLD
):
    if img_crop is None or img_crop.size == 0:
        return None, 999.0

    ch, cw = img_crop.shape[:2]

    # SPEED OPTIMIZATION:
    # scan_board() can now pass an already grayscale crop so the same
    # cv2.cvtColor() is not executed 64 times per full scan.
    if img_crop.ndim == 2:
        gray = img_crop
    else:
        gray = cv2.cvtColor(
            img_crop,
            cv2.COLOR_BGR2GRAY
        )

    if expected_symbol is None:
        margin_y = int(ch * 0.20)
        margin_x = int(cw * 0.20)

        if (
            ch > margin_y * 2
            and cw > margin_x * 2
        ):
            core = gray[
                margin_y:ch - margin_y,
                margin_x:cw - margin_x
            ]

            if float(np.std(core)) < EMPTY_STD_THRESHOLD:
                return None, 999.0

    symbols = (
        (expected_symbol,)
        if expected_symbol
        else current_templates.keys()
    )

    best_symbol = None
    best_score = float("inf")

    for symbol in symbols:
        variants = current_templates.get(symbol)

        if not variants:
            continue

        if symbol.lower() == "p":
            center_tolerance = PAWN_CENTER_TOLERANCE
        elif symbol.lower() == "r":
            center_tolerance = ROOK_CENTER_TOLERANCE
        else:
            center_tolerance = TEMPLATE_CENTER_TOLERANCE

        for tmpl in variants:
            tmpl_gray = tmpl["gray"]
            tmpl_mask = tmpl["mask"]
            th, tw = tmpl["size"]

            if th >= ch or tw >= cw:
                continue

            try:
                result = cv2.matchTemplate(
                    gray,
                    tmpl_gray,
                    cv2.TM_SQDIFF_NORMED,
                    mask=tmpl_mask
                )

                min_val, _, min_loc, _ = cv2.minMaxLoc(
                    result
                )

                match_cx = (
                    float(min_loc[0])
                    + (tw * 0.5)
                )

                match_cy = (
                    float(min_loc[1])
                    + (th * 0.5)
                )

                dx = (
                    abs(match_cx - cw * 0.5)
                    / max(1.0, float(cw))
                )

                dy = (
                    abs(match_cy - ch * 0.5)
                    / max(1.0, float(ch))
                )

                center_error = max(
                    dx,
                    dy
                )

                if center_error > center_tolerance:
                    continue

                if min_val < best_score:
                    best_score = float(min_val)
                    best_symbol = symbol

            except Exception:
                pass

    if (
        best_symbol is not None
        and best_score < match_threshold
    ):
        return best_symbol, best_score

    return None, best_score


def square_geometry(
    board_coords,
    square,
    black_perspective
):
    """
    Same geometry calculation as before, but cached.

    board_coords and perspective are part of the cache key so changing
    the grid or orientation cannot reuse stale coordinates.
    """
    x, y, w, h = board_coords

    key = (
        int(x),
        int(y),
        int(w),
        int(h),
        int(square),
        bool(black_perspective)
    )

    cached = _SQUARE_GEOMETRY_CACHE.get(key)

    if cached is not None:
        return cached

    sq_w = w / 8.0
    sq_h = h / 8.0

    file_ = chess.square_file(square)
    rank_ = chess.square_rank(square)

    if black_perspective:
        col = 7 - file_
        row = rank_
    else:
        col = file_
        row = 7 - rank_

    x1 = int(
        x + col * sq_w
    )

    y1 = int(
        y + row * sq_h
    )

    x2 = int(
        x + (col + 1) * sq_w
    )

    y2 = int(
        y + (row + 1) * sq_h
    )

    result = (
        x1,
        y1,
        x2,
        y2
    )

    if len(_SQUARE_GEOMETRY_CACHE) > 2048:
        _SQUARE_GEOMETRY_CACHE.clear()

    _SQUARE_GEOMETRY_CACHE[key] = result

    return result


def get_square_crop(
    frame,
    board_coords,
    square,
    black_perspective
):
    if frame is None:
        return None

    x1, y1, x2, y2 = square_geometry(
        board_coords,
        square,
        black_perspective
    )

    crop = frame[
        y1:y2,
        x1:x2
    ]

    # Read-only view is sufficient for all current callers.
    # Avoiding .copy() reduces per-square allocation.
    return crop if crop.size else None


def _get_cached_square_gray(
    frame,
    board_coords,
    square,
    black_perspective
):
    """
    Cache the exact small grayscale patch used by square_change_score().

    This is one of the largest safe speed improvements because the same
    square transition is otherwise recalculated many times while testing
    legal moves.
    """
    frame_id = id(frame)

    entry = _FRAME_SQUARE_CACHE.get(frame_id)

    if entry is None or entry["frame"] is not frame:
        entry = {
            "frame": frame,
            "patches": {}
        }

        _FRAME_SQUARE_CACHE[frame_id] = entry

        while len(_FRAME_SQUARE_CACHE) > _FRAME_SQUARE_CACHE_MAX:
            oldest_key = next(
                iter(_FRAME_SQUARE_CACHE)
            )
            _FRAME_SQUARE_CACHE.pop(
                oldest_key,
                None
            )

    patch_key = (
        tuple(int(v) for v in board_coords),
        int(square),
        bool(black_perspective)
    )

    cached = entry["patches"].get(
        patch_key
    )

    if cached is not None:
        return cached

    crop = get_square_crop(
        frame,
        board_coords,
        square,
        black_perspective
    )

    if crop is None:
        return None

    small = cv2.resize(
        crop,
        (
            SQUARE_DIFF_SIZE,
            SQUARE_DIFF_SIZE
        ),
        interpolation=cv2.INTER_AREA
    )

    gray = cv2.cvtColor(
        small,
        cv2.COLOR_BGR2GRAY
    )

    entry["patches"][patch_key] = gray

    return gray


def square_change_score(
    before_frame,
    after_frame,
    board_coords,
    square,
    black_perspective
):
    if (
        before_frame is None
        or after_frame is None
    ):
        return 0.0

    before_gray = _get_cached_square_gray(
        before_frame,
        board_coords,
        square,
        black_perspective
    )

    after_gray = _get_cached_square_gray(
        after_frame,
        board_coords,
        square,
        black_perspective
    )

    if (
        before_gray is None
        or after_gray is None
    ):
        return 0.0

    diff = cv2.absdiff(
        before_gray,
        after_gray
    )

    return float(
        np.mean(diff) / 255.0
    )


def scan_board(frame, board_coords):
    start = time.perf_counter()

    x, y, w, h = board_coords

    sq_w = w / 8.0
    sq_h = h / 8.0

    templates = get_scaled_templates(
        sq_w,
        sq_h
    )

    # SPEED OPTIMIZATION:
    # Convert the complete screenshot to grayscale once.
    # Individual square matching now reuses this grayscale image.
    gray_frame = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2GRAY
    )

    board_grid = []
    confidence_grid = []

    for row in range(8):
        row_data = []
        row_conf = []

        for col in range(8):
            x1 = int(
                x + col * sq_w
            )
            y1 = int(
                y + row * sq_h
            )
            x2 = int(
                x + (col + 1) * sq_w
            )
            y2 = int(
                y + (row + 1) * sq_h
            )

            # Use the precomputed grayscale frame.
            crop_gray = gray_frame[
                y1:y2,
                x1:x2
            ]

            symbol, score = classify_square(
                crop_gray,
                templates
            )

            row_data.append(symbol)
            row_conf.append(score)

        board_grid.append(row_data)
        confidence_grid.append(row_conf)

    elapsed = (
        time.perf_counter() - start
    ) * 1000.0

    return (
        board_grid,
        confidence_grid,
        elapsed
    )


def square_screen_center(
    square,
    board_coords,
    black_perspective,
    scrcpy_hwnd,
    screen_origin=None
):
    """
    Return a random point inside the centered 40%-area circle.

    The circle is centered in the chess square and its area is exactly
    40% of the square area. Points are sampled uniformly by area, so
    pickup and drop are random but remain strictly inside the circle.

    screen_origin is optional so click_move() can calculate the window
    origin once instead of calling GetClientRect/ClientToScreen twice.
    """
    if screen_origin is None:
        screen_origin = get_scrcpy_screen_origin(
            scrcpy_hwnd
        )

    if screen_origin is None:
        raise RuntimeError(
            "Could not determine scrcpy screen origin."
        )

    origin_x, origin_y = screen_origin

    x, y, w, h = board_coords

    sq_w = w / 8.0
    sq_h = h / 8.0

    file_ = chess.square_file(square)
    rank_ = chess.square_rank(square)

    if black_perspective:
        col = 7 - file_
        row = rank_
    else:
        col = file_
        row = 7 - rank_

    # Every pickup/drop point is sampled uniformly by area inside the
    # centered circle. The circle area is exactly 40% of the square area,
    # so points stay around the centre but are genuinely random instead of
    # repeatedly hitting one fixed centre point. A fresh point is generated
    # on every click attempt, including retries.
    angle = random.uniform(0.0, 2.0 * math.pi)
    radius = (
        CLICK_CIRCLE_RADIUS_FRACTION
        * (random.uniform(0.0, 1.0) ** 1.35)
    )

    rx = 0.5 + radius * math.cos(angle)
    ry = 0.5 + radius * math.sin(angle)

    px = (
        origin_x
        + x
        + (col + rx) * sq_w
    )

    py = (
        origin_y
        + y
        + (row + ry) * sq_h
    )

    return int(px), int(py)


def grid_conf_dict(
    grid,
    confidence_grid,
    black_perspective=False
):
    if grid is None:
        return {}

    # SPEED OPTIMIZATION:
    # The same grid/confidence objects are evaluated against many legal
    # moves. Build this mapping once per grid.
    key = (
        id(grid),
        id(confidence_grid),
        bool(black_perspective)
    )

    cached = _GRID_CONF_CACHE.get(
        key
    )

    if cached is not None:
        cached_grid = cached[0]
        cached_conf = cached[1]

        if (
            cached_grid is grid
            and cached_conf is confidence_grid
        ):
            return cached[2]

    values = {}

    for row in range(8):
        for col in range(8):
            symbol = grid[row][col]

            confidence = 999.0

            if confidence_grid is not None:
                confidence = confidence_grid[row][col]

            if black_perspective:
                file_ = 7 - col
                rank_ = row
            else:
                file_ = col
                rank_ = 7 - row

            square = chess.square(
                file_,
                rank_
            )

            values[square] = (
                symbol,
                confidence
            )

    _GRID_CONF_CACHE[key] = (
        grid,
        confidence_grid,
        values
    )

    while len(_GRID_CONF_CACHE) > _GRID_CONF_CACHE_MAX:
        oldest_key = next(
            iter(_GRID_CONF_CACHE)
        )

        _GRID_CONF_CACHE.pop(
            oldest_key,
            None
        )

    return values


def fast_square_motion_scores(before_frame, after_frame, board_coords, black_perspective):
    visual_scores = fast_board_motion_map(before_frame, after_frame, board_coords)
    if visual_scores is None:
        return None
    scores = {}
    for square in chess.SQUARES:
        file_ = chess.square_file(square)
        rank_ = chess.square_rank(square)
        if black_perspective:
            col = 7 - file_
            row = rank_
        else:
            col = file_
            row = 7 - rank_
        scores[square] = visual_scores[(row, col)]
    return scores


