from PIL import Image


def stretch_rank_bar(
    bar: Image.Image,
    width: int,
    height: int,
) -> Image.Image:
    """保留四周边缘，只拉伸 bar 中央的 1px 条带。"""
    source_width, source_height = bar.size
    center_x = source_width // 2
    center_y = source_height // 2

    wide = Image.new("RGBA", (width, source_height))
    wide.paste(bar.crop((0, 0, center_x, source_height)), (0, 0))
    wide.paste(
        bar.crop((center_x, 0, source_width, source_height)),
        (width - (source_width - center_x), 0),
    )
    if width > source_width:
        wide.paste(
            bar.crop((center_x - 1, 0, center_x, source_height)).resize(
                (width - source_width, source_height)
            ),
            (center_x, 0),
        )

    result = Image.new("RGBA", (width, height))
    result.paste(wide.crop((0, 0, width, center_y)), (0, 0))
    result.paste(
        wide.crop((0, center_y, width, source_height)),
        (0, height - (source_height - center_y)),
    )
    if height > source_height:
        result.paste(
            wide.crop((0, center_y - 1, width, center_y)).resize(
                (width, height - source_height)
            ),
            (0, center_y),
        )
    return result
