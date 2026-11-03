# Installing NinjaDash on the mini PC (Arch Linux / CachyOS)

## 1. Get the files onto the mini PC

Pick one:

- **USB stick:** copy `ninjadash-0.1.0.tar.gz` onto it, plug it into the mini PC, copy it to your home folder.
- **Over the network** (from the PC that has the file; replace `user` and `minipc` with the mini PC's login and name or IP):
  ```
  scp ninjadash-0.1.0.tar.gz user@minipc:
  ```
- **From GitHub** (the repo is private, so the mini PC needs a GitHub login): `git clone https://github.com/Bot320/NinjaDash.git`

Then unpack it on the mini PC:

```
tar xzf ninjadash-0.1.0.tar.gz
cd ninjadash-0.1.0
```

## 2. Install

Choose how the screen should work:

| Command | What you get |
|---|---|
| `sudo ./deploy/install.sh` | **Kiosk (recommended):** at boot the TV shows only the dashboard, full screen. No desktop runs, which saves memory on 4 GB. If a desktop login screen (e.g. SDDM) is enabled, the script asks before disabling it. |
| `sudo ./deploy/install.sh --desktop yourname` | Keeps your desktop. The dashboard opens full screen when `yourname` logs in. Alt+F4 closes it. |
| `sudo ./deploy/install.sh --backend-only` | Only the dashboard service. Open `http://localhost:8080` in any browser yourself. Good for a first test. |

The script installs `python`, `curl`, `cage`, `chromium`, `inter-font` and `noto-fonts` with pacman,
creates two service users (`ninjadash`, `ninjadash-kiosk`), copies the program to `/opt/ninjadash`
and starts the service. Running it again later **updates** NinjaDash and keeps your settings.

Until the API client is filled in, the dashboard shows **example data** with an amber
"Example data" note at the top, so you can check the screen straight away.

## 3. Connect it to NinjaOne

1. In NinjaOne (https://eu.ninjarmm.com): **Administration → Apps → API → Client App IDs → Add**
   - Application platform: **API Services (machine-to-machine)**
   - Name: **NinjaDash**
   - Scopes: **Monitoring** only
   - Allowed grant types: **Client Credentials**
   - Save, and copy the Client ID and the Client Secret (the secret is only shown once).
2. On the mini PC:
   ```
   sudo ninjadash edit
   ```
   Fill in `NINJA_CLIENT_ID=` and `NINJA_CLIENT_SECRET=`, then save (Ctrl+O, Enter, Ctrl+X).
3. Test it:
   ```
   sudo ninjadash check
   ```
   This logs in, counts your devices and alerts, and shows what each tile will show. It changes nothing in NinjaOne.
4. Apply it:
   ```
   sudo ninjadash restart
   ```
5. Kiosk mode only: `sudo reboot`. After the reboot the TV shows the dashboard.

## Everyday commands

| Command | Does |
|---|---|
| `sudo ninjadash check` | Tests the connection and lists alerts that no rule sorts yet |
| `sudo ninjadash check --fields` | Also shows NinjaOne's field names (useful when something looks wrong) |
| `sudo ninjadash edit` | Edits the settings (API client, theme, port) |
| `sudo ninjadash restart` | Applies changed settings or rules |
| `sudo ninjadash status` | Shows whether the service and the kiosk run |
| `sudo ninjadash logs` | Follows the log (Ctrl+C to stop) |

On the kiosk screen, **Ctrl+Alt+F2** switches to a text console for maintenance. The dashboard
stays on tty1, and Ctrl+Alt+F1 goes back to it.

## Your own alert rules

Edit `/etc/ninjadash/classify.toml` (`sudo nano /etc/ninjadash/classify.toml`) and then run `sudo ninjadash restart`.
The file has examples for Veeam, Synology and pinning devices to the server panel.
`sudo ninjadash check` lists the alerts that no rule sorts yet.

## Files

| Path | What |
|---|---|
| `/etc/ninjadash/ninjadash.env` | Settings incl. API secret (root and the `ninjadash` user only) |
| `/etc/ninjadash/classify.toml` | Your alert rules |
| `/opt/ninjadash/` | Program (replaced on every update) |
| `/var/lib/ninjadash/history.sqlite` | 14-day incident history |
| `ninjadash.service`, `ninjadash-kiosk.service` | systemd services |

## Remove

```
sudo /opt/ninjadash/deploy/uninstall.sh            # keeps settings
sudo /opt/ninjadash/deploy/uninstall.sh --purge    # removes everything
```
If the installer disabled your desktop login screen, the uninstaller turns it back on.

## Troubleshooting

- **Black screen / no dashboard after reboot:** press Ctrl+Alt+F2, log in, run `sudo ninjadash status`
  and `journalctl -b -u ninjadash-kiosk`.
- **"Login to NinjaOne failed (401)":** the Client ID or Secret is wrong, or the app isn't a
  machine-to-machine app with the Monitoring scope.
- **Edges of the picture are cut off on the TV:** set the TV's picture size to *Just Scan* / *Screen Fit* / *PC*.
- **Amber "Last NinjaOne sync … ago":** the mini PC lost internet or NinjaOne is unreachable. It retries on its own.
