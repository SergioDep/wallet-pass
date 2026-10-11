# NFC tag surprises

Write this URL to the NFC tag once:

```
https://sergiodep.github.io/wallet-pass/tag/
```

Each tap opens a "Toca para descubrir" screen, and the next tap launches one experience:

| id       | What happens on iPhone                                   | Other phones        |
|----------|----------------------------------------------------------|---------------------|
| `ar`     | AR Quick Look: a beating 3D heart floats in the room     | falls back to show  |
| `wallet` | Add to Apple Wallet sheet for `card.pkpass`               | falls back to show  |
| `show`   | Fireworks + message, tilt the phone to steer them         | works               |

## Change behaviour — edit `tag/config.json`

- `mode`: `"random"` (never repeats the last one on that phone), `"cycle"` (in order, per phone), or `"fixed"`.
- `fixed`: experience to use when `mode` is `"fixed"`.
- `experiences`: which ones are in the pool.
- `message.title` / `message.subtitle`: text for the fireworks show.

GitHub Pages caches for up to ~10 minutes after a push.

Force one for testing: `.../tag/?x=ar`, `?x=wallet`, `?x=show`.
