# NFC business card

Write this URL to the NFC tag (NFC Tools → Write → Add a record → URL):

```
https://sergiodep.github.io/wallet-pass/card/
```

Tap → iPhone banner → the page opens straight into a fly-in metal card that tilts with the phone.
Tap the card to flip it (QR on the back). Buttons: save contact (native contact sheet with photo),
WhatsApp, call, LinkedIn, GitHub, email, and "view in your space" (AR Quick Look of the card).

## Edit your details

1. Edit `card/profile.json` (currently DEMO values: email, LinkedIn).
2. Rebuild the generated assets (card faces, contact, AR model):
   ```
   pip install usd-core pillow qrcode numpy
   python3 tools/build_card.py
   ```
3. Update the `og:` tags at the top of `card/index.html` (link previews in WhatsApp/iMessage).
4. Commit and push. GitHub Pages can take up to ~10 minutes to refresh.

## Other things in this repo

- `card.pkpass`, `sergio.vcf`: direct links (Wallet pass, plain contact).
- `tag/`: earlier "tap to discover" surprise page.
