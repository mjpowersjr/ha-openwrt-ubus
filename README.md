# OpenWrt (ubus) for Home Assistant

A modern [Home Assistant](https://www.home-assistant.io/) custom integration for [OpenWrt](https://openwrt.org/) routers via the ubus JSON-RPC interface. Installable through [HACS](https://hacs.xyz/).

## Features

| Platform | Entities | Description |
|---|---|---|
| `device_tracker` | 1 per WiFi client | Presence detection via hostapd, with consider-home logic |
| `sensor` | ~8 system + dynamic per-interface | Uptime, load, memory, firmware, WAN IP, TX/RX bytes, WiFi client counts |
| `binary_sensor` | 1 | WAN connectivity status |
| `switch` | 1 per WiFi radio | Enable/disable radios (2.4 GHz, 5 GHz, 6 GHz) via UCI |
| `button` | 1 | Reboot the router |
| `diagnostics` | &mdash; | Downloadable redacted diagnostic dump |

### Highlights

- **No external dependencies** &mdash; uses `aiohttp` (bundled with HA) for a custom async ubus JSON-RPC client
- **Config flow UI** &mdash; set up entirely through the HA interface (no YAML)
- **Two DataUpdateCoordinators** &mdash; fast polling (30s) for device tracking, slower (60s) for system stats
- **Modern `ScannerEntity`** for device tracking (not the deprecated `DeviceScanner` pattern)
- **Device registry** &mdash; each WiFi client and the router itself get proper device entries
- **DHCP hostname resolution** &mdash; resolves MAC addresses to hostnames via dnsmasq or odhcpd leases
- **Reauth flow** &mdash; prompts to re-enter credentials if the password changes
- **Options flow** &mdash; adjust scan intervals, consider-home time, and toggle device tracking without removing the integration

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Click the three-dot menu (top right) &rarr; **Custom repositories**
3. Add this repository URL with category **Integration**:
   ```
   https://github.com/mjpowersjr/ha-openwrt-ubus
   ```
4. Click **Download** on the integration card
5. Restart Home Assistant
6. Go to **Settings &rarr; Devices & Services &rarr; Add Integration** and search for **OpenWrt (ubus)**

### Manual

Copy the `custom_components/openwrt_ubus` directory into your Home Assistant `config/custom_components/` directory and restart.

## Router Setup

The integration communicates with your router over HTTP via the ubus JSON-RPC endpoint served by **uhttpd**. Three things need to be in place:

1. [uhttpd-mod-ubus installed](#1-install-uhttpd-mod-ubus)
2. [An rpcd login user](#2-create-an-rpcd-login)
3. [A ubus ACL file granting permissions](#3-create-a-ubus-acl-file)

All commands below are run on the router via SSH.

### 1. Install uhttpd-mod-ubus

```sh
opkg update
opkg install uhttpd-mod-ubus
```

Most OpenWrt installations already have this. Verify with:

```sh
opkg list-installed | grep uhttpd-mod-ubus
```

### 2. Create an rpcd login

You can use the existing `root` user or create a dedicated `ha` user. A dedicated user is recommended.

Generate a password hash (replace `YOUR_PASSWORD` with your chosen password):

```sh
uhttpd -m 'YOUR_PASSWORD'
```

This prints a hash like `$1$$CRCpAJrTHfY/gynGN3N/F1`. Add the login to `/etc/config/rpcd`:

```sh
uci add rpcd login
uci set rpcd.@login[-1].username='ha'
uci set rpcd.@login[-1].password='PASTE_HASH_HERE'
uci add_list rpcd.@login[-1].read='*'
uci add_list rpcd.@login[-1].write='*'
uci commit rpcd
/etc/init.d/rpcd restart
```

Or edit `/etc/config/rpcd` directly and add:

```
config login
    option username 'ha'
    option password '$1$$CRCpAJrTHfY/gynGN3N/F1'
    list read '*'
    list write '*'
```

Then restart rpcd:

```sh
/etc/init.d/rpcd restart
```

### 3. Create a ubus ACL file

Create `/usr/share/rpcd/acl.d/ha.json` with the permissions the integration needs:

```sh
cat > /usr/share/rpcd/acl.d/ha.json << 'EOF'
{
    "ha": {
        "description": "Home Assistant integration access",
        "read": {
            "file": {
                "/tmp/dhcp.leases": ["read"]
            },
            "ubus": {
                "system": ["board", "info"],
                "hostapd.*": ["get_clients"],
                "iwinfo": ["info", "scan"],
                "dhcp": ["ipv4leases"],
                "network.interface": ["dump", "status"],
                "network.device": ["status"],
                "network.wireless": ["status"],
                "uci": ["get"]
            }
        },
        "write": {
            "ubus": {
                "system": ["reboot"],
                "network.wireless": ["up", "down"],
                "uci": ["set", "commit"]
            }
        }
    }
}
EOF
```

Restart rpcd to pick up the new ACL:

```sh
/etc/init.d/rpcd restart
```

### Verify the setup

Test from your HA machine (or any machine on the same network):

```sh
# Should return a JSON response with a ubus_rpc_session (not error code 6)
curl -s -X POST -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"call","params":["00000000000000000000000000000000","session","login",{"username":"ha","password":"YOUR_PASSWORD"}]}' \
  http://ROUTER_IP:PORT/ubus
```

A successful response looks like:

```json
{"jsonrpc":"2.0","id":1,"result":[0,{"ubus_rpc_session":"abc123...","timeout":300,...}]}
```

If you get `{"result":[6]}`, the username/password is wrong or the password wasn't hashed correctly.

## GL-iNet Routers

GL-iNet routers (Flint, Flint 2, Slate, etc.) use **nginx** as their web frontend on ports 80/443, with **uhttpd** running on alternate ports. You need to find the uhttpd port:

```sh
netstat -tlnp | grep uhttpd
```

Typical output:

```
tcp  0  0  0.0.0.0:8080  0.0.0.0:*  LISTEN  uhttpd
tcp  0  0  0.0.0.0:8443  0.0.0.0:*  LISTEN  uhttpd
```

Use **port 8080** (HTTP) or **8443** (HTTPS) when adding the integration in Home Assistant.

## Configuration

When adding the integration, you'll be prompted for:

| Field | Description | Default |
|---|---|---|
| Host | Router IP or hostname | &mdash; |
| Port | uhttpd port (see note for GL-iNet) | `80` |
| Username | rpcd login username | `root` |
| Password | rpcd login password | &mdash; |
| Use HTTPS | Enable TLS | Off |
| Verify SSL | Validate the certificate | On |
| DHCP software | Used for hostname resolution | `dnsmasq` |

### Options (configurable after setup)

| Option | Description | Default |
|---|---|---|
| Track WiFi devices | Enable device tracker entities | On |
| Consider home (seconds) | Time to keep a client as "home" after it disconnects | `180` |
| Device tracker scan interval (seconds) | How often to poll for WiFi clients | `30` |
| Stats scan interval (seconds) | How often to poll system/network stats | `60` |

## Entities

### System sensors (diagnostic)

- **Uptime** &mdash; boot timestamp
- **Load average** (1m, 5m, 15m)
- **Memory usage** (%) and **Memory free** (MB)
- **Firmware version**

### Network sensors

- **Connected clients** &mdash; total WiFi client count
- **WAN IPv4 address**
- **TX/RX bytes** per network device (total increasing)
- **WiFi clients** per radio

### Binary sensor

- **WAN connected** &mdash; on when any `wan*` interface is up

### Device tracker

One entity per WiFi client, with extra attributes:
- Interface name, SSID, signal strength, RX/TX rates

### Switch

One per WiFi radio (e.g., "WiFi 2.4 GHz (radio0)"). Toggles the radio via UCI (`wireless.radioN.disabled`).

> **Note:** The toggle writes the UCI config and commits it. On some routers the change takes effect immediately; on others a `wifi reload` may be needed on the router for the radio to actually go up or down.

### Button

- **Reboot** &mdash; reboots the router

## Troubleshooting

### "Cannot connect" during setup

1. **Check the port.** If your router runs nginx (GL-iNet, some custom builds), uhttpd is likely on port 8080 or 8443, not 80.
2. **Check uhttpd-mod-ubus is installed.** Run `opkg list-installed | grep uhttpd-mod-ubus` on the router.
3. **Test with curl.** See the [verify the setup](#verify-the-setup) section above.

### "Invalid authentication"

1. **Check the password hash.** The rpcd password must be hashed with `uhttpd -m`. Plaintext passwords in `/etc/config/rpcd` will not work.
2. **Check the username matches** what you entered in the config flow.
3. **Restart rpcd** after making changes: `/etc/init.d/rpcd restart`.

### Login returns `[6]` (permission denied)

- The password is wrong or was entered as plaintext instead of a hash in rpcd config.
- The rpcd service wasn't restarted after config changes.

### No WiFi clients showing up

- The ACL file must grant read access to `hostapd.*` &rarr; `get_clients`.
- Verify hostapd interfaces exist: `ubus list | grep hostapd` on the router.
- The integration tries common interface names (`wlan0`, `wlan1`, `phy0-ap0`, etc.) and reads UCI wireless config to discover interfaces.

### Sensors show "unavailable"

- Check that the ACL grants access to the relevant ubus objects (`system`, `network.interface`, `network.device`, `iwinfo`).
- Look at the Home Assistant logs for error messages from `custom_components.openwrt_ubus`.

## Development

```sh
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v
```

## License

MIT
