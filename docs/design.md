# HamRig design system

The Qt desktop UI uses the same design tokens and component language as HamRig
Gateway 3 and its amplifier panel. The reference is Gateway commit `6e28350`:

- `hamrig_gateway3/webui/theme.css`: portal token values dated 2026-10-05.
- `hamrig_gateway3/webui/app.css`: forms, primary actions, focus and surfaces.
- `hamrig_gateway3/drivers/amp/web/amps.css`: amplifier readouts, selected
  controls, status colours and TX emphasis (portal origin `7a213648`).

`src/openpw2/gui/theme.py` contains the shared values, using underscore names
for the equivalent CSS custom properties. `theme.qss` contains the Qt component
rules; Python's `Template` expands tokens because QSS has no `var()` support.
Qt uses integer alpha values from 0 to 255 in its rgba colours.

| Role | HamRig value / treatment |
|---|---|
| Main / secondary / card / hover | #16161A / #1F1F24 / #24242B / #31313A |
| Main / secondary / muted text | #F2F2F7 / #AEAEB2 / #8E8E93 |
| Primary action / accent outline | #8B1D1D / #E05252 |
| Normal meters / Operate | #34C759 |
| Standby / tuning / demo indication | #F59E0B (amplifier warning token) |
| RX / TX and protection | #0A84FF / #FF3B30 |
| Cards / controls / tabs | rounded 14 / 9 / 10 px, subtle light borders |
| Interface / numeric readouts | Inter / JetBrains Mono font stacks |

Like the offline Gateway UI, fonts fall back to installed system fonts
(Segoe UI and Consolas on Windows). No CDN or downloaded fonts are required.
Colours accompany readable state labels. Selected controls remain identifiable
when TX interlocks disable them. Keyboard focus uses the accent outline.
No new measurement thresholds or hardware commands are introduced by the theme.

The desktop layout remains compact and native. It does not load portal CSS or
require HamRig at runtime. To update the design, compare the source tokens and
amplifier state styles, change the mapping, then render and inspect the actual
Qt widgets with `python tools/render_demo.py`.
