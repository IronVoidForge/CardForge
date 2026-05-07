# PC + Mobile Startup and Network Integrations

CardForge is designed to run on a workstation while phones/tablets use the mobile operator UI over your LAN or VPN.

## Recommended startup

Generate launchers once:

```bash
cardforge launcher write --host <your-pc-lan-ip> --port 8765
```

This writes files under:

```text
workspace/launchers/
  Start_CardForge_Both.bat
  Start_CardForge_Mobile.bat
  Start_CardForge_Desktop.bat
  Start_CardForge_Both.sh
  Start_CardForge_Mobile.sh
  Start_CardForge_Desktop.sh
  Open_CardForge_Mobile.html
  README.txt
```

On Windows, double-click:

```text
Start_CardForge_Both.bat
```

Then open:

```text
Desktop: http://localhost:8765/
Mobile:  http://<your-pc-lan-ip>:8765/m
```

The HTML opener only opens the mobile URL. It does not start the Python server by itself.

## Direct serve commands

Desktop only:

```bash
cardforge ui serve --mode desktop --host 127.0.0.1 --port 8765
```

Mobile only:

```bash
cardforge ui serve --mode mobile --host 0.0.0.0 --port 8765 --password "choose-a-local-password"
```

Desktop and mobile together:

```bash
cardforge ui serve --mode both --host 0.0.0.0 --port 8765 --password "choose-a-local-password"
```

## Integration settings

Open the desktop UI:

```text
/projects/<project_slug>/integrations
```

You can save:

- LM Studio base URL, generation model, review model, timeout, max tokens, and optional bearer token.
- ComfyUI base URL, input directory, output directory, timeout, poll interval, and optional bearer token.

Settings are written to:

```text
workspace/config/integrations.json
```

Environment variables still override saved settings when present.

## CLI equivalents

```bash
cardforge llm configure \
  --base-url http://192.168.1.42:1234/v1 \
  --model your-generation-model \
  --review-model your-review-model

cardforge comfy configure \
  --base-url http://192.168.1.42:8188 \
  --input-dir C:\ComfyUIInstall\input \
  --output-dir C:\ComfyUIInstall\output

cardforge llm health --json
cardforge comfy health --json
```

## Security notes

- Use a UI password for LAN/mobile mode.
- Prefer Tailscale/WireGuard/ZeroTier over public port forwarding.
- Do not expose CardForge directly to the public internet.
- Keep raw workflow editing and destructive maintenance on desktop, not mobile.

