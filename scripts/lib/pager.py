"""Interactive scrollable pager for session listings."""
import shutil
import textwrap

_SESSION_ID_WIDTH = 38
_PREFIX_WIDTH = _SESSION_ID_WIDTH

_HEADER = "{:<{iw}}{}".format(
    "SESSION ID", "SUMMARY",
    iw=_SESSION_ID_WIDTH,
)


def format_row(session_id, summary, summary_width):
    # type: (str, str, int) -> list
    """Format a single row into display lines with text wrapping.

    Returns a list of strings. The first line contains both columns;
    continuation lines are indented to the summary column.
    """
    if summary_width < 10:
        summary_width = 10

    wrapped = textwrap.wrap(summary, width=summary_width) if summary else []

    first_summary = wrapped[0] if wrapped else ""
    first_line = "{:<{iw}}{}".format(
        session_id, first_summary,
        iw=_SESSION_ID_WIDTH,
    )
    lines = [first_line]

    indent = " " * _PREFIX_WIDTH
    for continuation in wrapped[1:]:
        lines.append(indent + continuation)

    return lines


def run_pager(rows):
    # type: (list) -> None
    """Display rows in an interactive curses pager, or fall back to plain output."""
    import sys
    if not sys.stdout.isatty():
        _print_plain(rows)
        return

    try:
        import curses
        curses.wrapper(_curses_main, rows)
    except Exception:
        _print_plain(rows)


def _print_plain(rows):
    # type: (list) -> None
    """Print all rows as plain text with wrapping."""
    term_width = shutil.get_terminal_size((80, 24)).columns
    summary_width = max(term_width - _PREFIX_WIDTH, 10)

    print(_HEADER)
    print("-" * term_width)

    for row in rows:
        lines = format_row(
            row["session_id"], row["summary"], summary_width
        )
        for line in lines:
            print(line)


def _curses_main(stdscr, rows):
    """Curses-based scrollable pager."""
    import curses

    curses.curs_set(0)
    curses.use_default_colors()

    def render():
        stdscr.erase()
        height, width = stdscr.getmaxyx()
        summary_width = max(width - _PREFIX_WIDTH, 10)

        # Build all display lines from rows
        all_lines = []
        # Track which display-line index starts each logical row
        row_starts = []
        for row in rows:
            row_starts.append(len(all_lines))
            lines = format_row(
                row["session_id"], row["summary"], summary_width
            )
            all_lines.extend(lines)

        content_height = height - 3  # header + separator + footer
        if content_height < 1:
            content_height = 1

        total_lines = len(all_lines)

        # Clamp scroll_pos
        max_scroll = max(total_lines - content_height, 0)
        if scroll_pos[0] > max_scroll:
            scroll_pos[0] = max_scroll
        if scroll_pos[0] < 0:
            scroll_pos[0] = 0

        # Draw header (line 0)
        header = _HEADER[:width]
        try:
            stdscr.addnstr(0, 0, header, width, curses.A_BOLD)
        except curses.error:
            pass

        # Draw separator (line 1)
        sep = "-" * (width - 1)
        try:
            stdscr.addnstr(1, 0, sep, width)
        except curses.error:
            pass

        # Draw content
        visible_start = scroll_pos[0]
        visible_end = min(visible_start + content_height, total_lines)
        for i, line_idx in enumerate(range(visible_start, visible_end)):
            display_line = all_lines[line_idx][:width - 1]
            try:
                stdscr.addnstr(2 + i, 0, display_line, width)
            except curses.error:
                pass

        # Compute visible row range for footer
        first_visible_row = 0
        last_visible_row = 0
        for ri, start in enumerate(row_starts):
            if start <= visible_start:
                first_visible_row = ri
            if start < visible_end:
                last_visible_row = ri

        footer = " [q] quit  [up/down] scroll  (showing {}-{} of {})".format(
            first_visible_row + 1, last_visible_row + 1, len(rows),
        )
        try:
            stdscr.addnstr(height - 1, 0, footer[:width - 1], width)
        except curses.error:
            pass

        stdscr.refresh()
        return all_lines, row_starts

    scroll_pos = [0]  # mutable for nested access

    all_lines, row_starts = render()

    while True:
        try:
            key = stdscr.getch()
        except KeyboardInterrupt:
            break

        if key in (ord("q"), ord("Q"), 27):  # q, Q, ESC
            break

        import curses as _curses
        height, width = stdscr.getmaxyx()
        content_height = max(height - 3, 1)
        total_lines = len(all_lines)
        max_scroll = max(total_lines - content_height, 0)

        if key in (_curses.KEY_DOWN, ord("j")):
            # Scroll down by one logical row
            current_row = 0
            for ri, start in enumerate(row_starts):
                if start <= scroll_pos[0]:
                    current_row = ri
            next_row = min(current_row + 1, len(row_starts) - 1)
            scroll_pos[0] = min(row_starts[next_row], max_scroll)
        elif key in (_curses.KEY_UP, ord("k")):
            # Scroll up by one logical row
            current_row = 0
            for ri, start in enumerate(row_starts):
                if start <= scroll_pos[0]:
                    current_row = ri
            prev_row = max(current_row - 1, 0)
            scroll_pos[0] = row_starts[prev_row]
        elif key == _curses.KEY_RESIZE:
            pass  # re-render will pick up new size

        all_lines, row_starts = render()
