# Remote setup: main laptop, LattePanda, X1

Three machines. Tell Claude Code on each one: "set up this machine per docs/remote-setup.md (section X)".

- **Main laptop:** edit, commit, push. No VPN, no tunnels, never on the phone hotspot.
- **LattePanda (home network):** runs tests, validation and HIL with the boards attached.
- **X1 (personal laptop):** HIL web UI through Tailscale; may use the phone hotspot.

## LattePanda

- [ ] Linux; `sudo apt install git python3.12 python3.12-venv libglu1-mesa libxcursor1 libxft2 libxinerama1`; Node 26 (NodeSource apt repo, `deb.nodesource.com/node_26.x`).
- [ ] `git clone https://github.com/yusnimawl/srm-forge.git && cd srm-forge`
- [ ] `python3.12 -m venv .venv && . .venv/bin/activate && python -m pip install -e ".[dev,ngsolve,web,hil]"`
- [ ] `sh hil/setup.sh`
- [ ] `cd web && npm ci && npm run build && cd ..`
- [ ] `sudo usermod -aG dialout $USER` (serial ports for the Teensy and Nucleo), log out and in, plug in both boards.
- [ ] `sudo cp hil/.runtime/lib/python3.*/site-packages/platformio/assets/system/99-platformio-udev.rules /etc/udev/rules.d/ && sudo udevadm control --reload-rules && sudo udevadm trigger`: without it the Teensy bootloader (16c0:0478) and the ST-LINK are root-only and Build & Flash hangs; it also keeps ModemManager off both serial ports. Unplug and replug both boards after.
- [ ] Install Claude Code, log in, turn Remote Control on.
- [ ] Install Tailscale: `sudo tailscale up --ssh`; note the machine name.
- [ ] No sleep, auto-login.
- [ ] Check: `python -m pytest -m "not slow"` passes; `srmweb` serves on 127.0.0.1:8000.

Keep `SRMWEB_HOST` at 127.0.0.1: HIL and custom controllers refuse a non-loopback host.

## X1

- [ ] Install Tailscale, same account.
- [ ] `ssh -L 8000:127.0.0.1:8000 <user>@<lattepanda>` and open http://127.0.0.1:8000.
- [ ] Optional: Claude Code for dev work.

## Phone

- [ ] Tailscale and the Claude app.
- [ ] Hotspot for the X1 only, never the main laptop.

## Main laptop

- [ ] No Tailscale, no tunnels, no phone hotspot.
- [ ] Commit and push to GitHub; drive the LattePanda session through Remote Control in the Claude app (it pulls and runs).
