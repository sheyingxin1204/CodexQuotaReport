from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


WIDTH = 512
HEIGHT = 512
RADIUS = 112


def _gradient_background(draw: ImageDraw.ImageDraw) -> None:
    start = (37, 99, 235)
    end = (13, 148, 136)
    for y in range(HEIGHT):
        ratio = y / (HEIGHT - 1)
        color = tuple(
            round(start[channel] + (end[channel] - start[channel]) * ratio)
            for channel in range(3)
        )
        draw.line([(0, y), (WIDTH, y)], fill=color)


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def build_icon() -> Image.Image:
    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    base = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(base)
    _gradient_background(draw)
    image.paste(base, (0, 0), _rounded_mask(WIDTH, RADIUS))

    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    ring_box = (116, 116, WIDTH - 116, HEIGHT - 116)
    draw.arc(
        ring_box,
        start=20,
        end=300,
        fill=(255, 255, 255, 235),
        width=56,
    )
    dot_radius = 34
    center = (WIDTH // 2, HEIGHT // 2)
    draw.ellipse(
        (
            center[0] - dot_radius,
            center[1] - dot_radius,
            center[0] + dot_radius,
            center[1] + dot_radius,
        ),
        fill=(255, 255, 255, 245),
    )

    check = (0, 255, 0, 0)
    draw.line(
        [
            (center[0] - 72, center[1] - 6),
            (center[0] - 22, center[1] + 48),
            (center[0] + 86, center[1] - 62),
        ],
        fill=(23, 37, 84, 255),
        width=42,
        joint="curve",
    )
    image.paste(overlay, (0, 0), overlay)

    shadow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw_shadow = ImageDraw.Draw(shadow)
    draw_shadow.rounded_rectangle((0, 18, WIDTH - 1, HEIGHT - 1), radius=RADIUS, fill=(0, 0, 0, 70))
    image = Image.alpha_composite(shadow, image)
    return image.resize((256, 256), Image.LANCZOS)


def main() -> None:
    output = Path(__file__).resolve().parents[1] / "build" / "icon.ico"
    output.parent.mkdir(parents=True, exist_ok=True)
    image = build_icon()
    image.save(
        output,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(output)


if __name__ == "__main__":
    main()
