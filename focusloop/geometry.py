"""Pure geometry helper for positioning the tray menu on screen."""


def tray_menu_position(
    cursor_x: int,
    cursor_y: int,
    screen_x: int,
    screen_y: int,
    screen_width: int,
    screen_height: int,
    menu_width: int,
    menu_height: int,
    *,
    margin: int = 24,
    gap: int = 32,
) -> tuple[int, int]:
    """Place a popup above the cursor, within the screen's available area.

    All screen coordinates are global, and the available area excludes the
    Windows taskbar. The whole menu is lifted above the click point.
    """
    min_x = screen_x + margin
    max_x = max(min_x, screen_x + screen_width - menu_width - margin)
    min_y = screen_y + margin
    max_y = max(min_y, screen_y + screen_height - menu_height - margin)
    preferred_x = cursor_x - menu_width + 16
    preferred_y = cursor_y - menu_height - gap
    return (
        min(max(preferred_x, min_x), max_x),
        min(max(preferred_y, min_y), max_y),
    )
