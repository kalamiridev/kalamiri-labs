# Bridge HomeKit accessories to MQTT

Containerized service that pairs with HomeKit accessories on the local network
and makes them MQTT devices: their state is published as JSON, and commands
on `<device>/set` are written back to the accessory. Without Home Assistant,
and without an Apple device.

Common properties use the names and values of
[Zigbee2MQTT](https://www.zigbee2mqtt.io/) (`local_temperature`, `occupancy`,
`state`), so anything that understands Zigbee2MQTT devices understands these
too. Home Assistant MQTT discovery is optional.

## Architecture

```text
HomeKit accessory (Wi-Fi / Ethernet)
        |  HAP, found with mDNS
        v
homekit-mqtt
        |
        v
MQTT  <--  commands on <device>/set
```

## Requirements

- Docker and Docker Compose on a host in the same network (VLAN) as the
  accessories. HomeKit accessories announce themselves with mDNS, which does
  not cross networks, so the container uses the host network.
- An MQTT broker reachable from the host.
- The accessory's setup code (the 8 digits on the device or in its app).
- An accessory that is not paired with another controller. A HomeKit accessory
  accepts one controller: remove it from Apple Home or from the Home Assistant
  HomeKit Device integration first.

Accessories on Wi-Fi or Ethernet are supported. Bluetooth-only accessories are
not.

## Quick start

1. Create the data directory, owned by the container user (UID 10001). It holds
   the pairing keys, so keep it private:

   ```bash
   mkdir data
   sudo chown 10001:10001 data
   ```

2. Copy `compose.yaml`, create `.env` with at least `MQTT_HOST`, and start the
   service:

   ```bash
   docker compose up -d
   ```

   Until an accessory is paired, the log says
   `No paired accessories in /data/pairing.json yet` once a minute.

3. Find the accessory:

   ```bash
   docker compose exec homekit-mqtt python -m homekit_mqtt discover
   ```

   ```text
   af:8c:00:57:45:12  My ecobee  ECB601  (not paired)
   ```

4. Pair it with its setup code and a short alias of your choice:

   ```bash
   docker compose exec homekit-mqtt python -m homekit_mqtt pair -d af:8c:00:57:45:12 -p 123-45-678 -a ecobee
   ```

5. Restart the service to load the new pairing:

   ```bash
   docker compose restart homekit-mqtt
   ```

   The log lists the devices: `Devices: My ecobee (12 properties)`.

To release an accessory, for example to pair it with Apple Home again:

```bash
docker compose exec homekit-mqtt python -m homekit_mqtt unpair -a ecobee
docker compose restart homekit-mqtt
```

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `MQTT_HOST` | required | Broker host name or address |
| `MQTT_PORT` | `1883` | Broker port |
| `MQTT_USERNAME`, `MQTT_PASSWORD` | empty | Broker login |
| `MQTT_TLS_ENABLED` | `false` | TLS with the system CA certificates |
| `MQTT_CLIENT_ID` | `homekit-mqtt` | MQTT client ID |
| `MQTT_BASE_TOPIC` | `homekit` | Topic under which devices are published |
| `HA_DISCOVERY_ENABLED` | `true` | Publish Home Assistant MQTT discovery |
| `HA_DISCOVERY_PREFIX` | `homeassistant` | Home Assistant discovery prefix |
| `HOMEKIT_POLL_INTERVAL` | `60` | Seconds between reads of all values, each read published again (10–3600); changes arrive as events in between |
| `HOMEKIT_INCLUDE_VENDOR` | `false` | Also publish manufacturer-specific characteristics |
| `HOMEKIT_DATA_DIR` | `/data` | Pairing keys and the optional devices file |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` |

### Device names, limits and properties

A device is named after its HomeKit accessory. To rename it, to narrow the
setpoints a thermostat accepts over MQTT, or to leave properties out of its
messages, create `data/devices.json`, keyed by accessory name or by
`<alias>:<aid>`:

```json
{
  "My ecobee": {
    "name": "Living Room Thermostat",
    "limits": {
      "occupied_heating_setpoint": [18, 24],
      "occupied_cooling_setpoint": [22, 28]
    },
    "exclude": ["temperature_display_units", "target_humidity", "fan_state"]
  }
}
```

Names must not contain `/`, `+` or `#`. Restart the service after a change.

## MQTT topics

| Topic | Payload |
| --- | --- |
| `<base>/<device>` | State as JSON with `last_seen` (ISO 8601), retained |
| `<base>/<device>/availability` | `{"state": "online"}` or `{"state": "offline"}`, retained |
| `<base>/<device>/set` | Command: JSON with property names, e.g. `{"system_mode": "heat"}` |
| `<base>/homekit-mqtt/availability` | Availability of the service itself, retained; `offline` is its MQTT will |

After every command the device's state is read back and published, also when
nothing changed, so the sender sees the command answered. A value outside the
accessory's range, or one the property does not accept, is refused and logged.

### Properties

Each HomeKit accessory is one device. A property that appears in more than one
service of the device gets an endpoint suffix, as in Zigbee2MQTT: a power strip
has `state_l1` to `state_l5`. A security system is a device of its own, named
`<accessory> Alarm`, so that its `state` keeps the plain name.

| HomeKit | Property | Values |
| --- | --- | --- |
| Current temperature | `temperature`, in a thermostat `local_temperature` | °C |
| Current / target relative humidity | `humidity`, `target_humidity` | % |
| Target heating cooling state | `system_mode` | `off`, `heat`, `cool`, `auto` |
| Current heating cooling state | `running_state` | `idle`, `heat`, `cool`; `fan_only` when idle with the fan blowing |
| Target temperature (not in a thermostat) | `target_temperature` | °C |
| Thermostat setpoints | `occupied_heating_setpoint`, `occupied_cooling_setpoint` | °C, see below |
| Target fan state (thermostat) | `fan_mode` | `on`, `auto` |
| Occupancy, motion | `occupancy`, `motion` | `true`, `false` |
| Contact | `contact` | `true` when closed |
| Leak, smoke, carbon monoxide | `water_leak`, `smoke`, `carbon_monoxide` | `true`, `false` |
| CO2, CO, PM2.5, PM10, VOC | `co2`, `co`, `pm25`, `pm10`, `voc` | |
| Light level | `illuminance` | lx |
| Battery level, low battery | `battery`, `battery_low` | %, `true`/`false` |
| On, active | `state` | `ON`, `OFF` |
| Brightness, color temperature | `brightness_percent`, `color_temp` | %, mired |
| Lock | `lock_state` (read), `state` (set) | `locked`/`unlocked`/`jammed`, `LOCK`/`UNLOCK` |
| Window covering | `position` | 0–100, 100 is open |
| Garage door | `door_state` (read), `state` (set) | `open`/`closed`/…, `OPEN`/`CLOSE` |
| Security system | `state` | `disarmed`, `armed_home`, `armed_away`, `armed_night`, `triggered` |
| Rotation speed, swing mode | `speed`, `swing_mode` | %, `on`/`off` |
| Volume, mute, active input (TV) | `volume`, `mute`, `input` | |

Every other characteristic is published under the snake_case name of its
HomeKit type, for example `charging_state` or `audio_feedback`, and can be set
when the accessory allows writing it. Identification and names of services
are left out.

A thermostat's setpoints follow its mode, as Home Assistant shows a HomeKit
thermostat: in `heat` and `cool` both setpoints are the target temperature,
in `auto` they are the heating and cooling thresholds, and while it is `off`
they are `null` (a thermostat without thresholds always shows its target).
A command sets the mode first. Then, in `heat` the heating setpoint and in
`cool` the cooling setpoint is written to the target temperature, and the
other one is ignored; in `auto` the thresholds are written, the heating one
below the cooling one; while `off` setpoints are refused. The state also carries
`min_heat_setpoint_limit`, `max_heat_setpoint_limit`, `min_cool_setpoint_limit`
and `max_cool_setpoint_limit`, from the accessory or narrowed in
`devices.json`.

## Home Assistant

With discovery on, Home Assistant creates entities for thermostats (climate),
lights, switches and outlets, fans, locks, window coverings, garage doors,
security systems, sensors and binary sensors. Every property is on MQTT either
way.

## Development

```bash
pip install -r requirements.txt
python -m unittest discover -s tests -t .
```

The tests run the mapping, Home Assistant discovery and the service against
accessory descriptions of real devices (Ecobee, Meross, Aqara, Schlage, Velux,
Eve, HAA) with the `aiohomekit` test controller.

## License

MIT, see [LICENSE](LICENSE). Third-party notices are in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
