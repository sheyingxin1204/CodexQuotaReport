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

    shield = [
        (WIDTH // 2, 58),
        (WIDTH - 98, 142),
        (WIDTH - 98, 278),
        (WIDTH // 2, 440),
        (98, 278),
        (98, 142),
    ]
    draw.polygon(shield, outline=(255, 255, 255, 245), width=48)

    center = (WIDTH // 2, HEIGHT // 2 + 12)
    draw.arc(
        (center[0] - 116, center[1] - 116, center[0] + 116, center[1] + 116),
        start=135,
        end=45,
        fill=(23, 37, 84, 255),
        width=40,
    )
    draw.line(
        [
            (center[0] - 62, center[1] - 6),
            (center[0] - 18, center[1] + 42),
            (center[0] + 76, center[1] - 58),
        ],
        fill=(23, 37, 84, 255),
        width=36,
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
