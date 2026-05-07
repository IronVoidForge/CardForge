# Mobile Operator Requirement

CardForge now treats mobile access as a first-class product requirement.

## Architecture

The workstation runs the production stack:

- CardForge server and SQLite database
- workspace files and rendered exports
- LM Studio API on the local network
- ComfyUI API on the local network

The phone/tablet is a mobile operator console:

- review cards and art
- approve/reject/request rework
- run or retry jobs
- inspect renders and lab outputs
- trigger prepared LM Studio/ComfyUI jobs through the workstation

CardForge is not intended to run models on the mobile device.

## Start the mobile UI

Recommended LAN/mobile command:

```bash
cardforge mobile serve --password "choose-a-local-password"
```

This binds to `0.0.0.0:8765`, enables the mobile-first UI, and requires login.
Open the printed `/m` URL on your phone while it is on the same LAN or VPN.

Development-only, no-login mode:

```bash
cardforge mobile serve --no-auth
```

## Install like an app

Open the `/m` URL on the phone, then use the browser menu:

- iOS Safari: Share → Add to Home Screen
- Android Chrome: menu → Install app / Add to Home screen

CardForge includes a web app manifest and service worker shell so the installed icon opens the mobile UI like an app.

## Clickable mobile launcher file

Create a small HTML launcher file:

```bash
cardforge mobile launcher --host 192.168.1.42 --port 8765
```

This writes:

```text
workspace/CardForge_Mobile_Launcher.html
```

Copy that file to a phone or shared folder. Tapping it opens the CardForge Mobile URL. The workstation server must already be running.

## Security expectations

Use a VPN such as Tailscale/WireGuard for access away from home. Do not port-forward CardForge directly to the public internet.

Mobile mode supports:

- password login
- signed session cookie
- CSRF tokens for mutating form posts
- same-site cookies
- safe workspace asset serving

High-risk operations such as template activation, lab promotion application, final locks, live Comfy submission, and running all jobs should remain deliberate operator actions.
