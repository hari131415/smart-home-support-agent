---
device_type: hub
model: Kestrel Hub H1
---

# Kestrel Hub H1 User Manual

## Specifications

- Radios: Wi-Fi 2.4/5 GHz, Ethernet 10/100, Zigbee 3.0, Thread (border router), Bluetooth LE
- Supports up to 100 connected devices
- Matter controller and bridge: exposes Kestrel Zigbee devices to other Matter platforms
- Power: 5V/2A USB-C adapter (included). Backup battery keeps the hub running about 4 hours in a power outage.

## Setup

Place the hub centrally in your home, at least 3 feet (1 m) away from your Wi-Fi router and other wireless equipment to reduce interference. Ethernet is recommended when possible.

1. Plug in the hub. The light turns solid amber after about 1 minute.
2. In the app, tap Add Device > Hub and scan the QR code on the bottom.
3. Choose Ethernet or Wi-Fi. When the light turns solid green the hub is online.

## Status light

- Solid amber: starting up or waiting for setup.
- Blinking amber: setup in progress.
- Solid green: online.
- Blinking green: pairing mode (adding a device).
- Solid red: no internet connection.
- Blinking red: firmware update failed; hub will retry automatically.
- Purple: running on backup battery.

## Adding devices

Tap Add Device in the app and choose the device type, or tap "Scan for devices" to put the hub in pairing mode for 3 minutes. Zigbee devices should be within 30 feet (9 m) of the hub or a repeater during pairing.

## Matter

To share Kestrel devices with another platform, open Hub Settings > Matter > Generate pairing code. The code is valid for 15 minutes. Up to 5 Matter platforms can control the same device.

## Range and repeaters

Mains-powered Zigbee and Thread devices (like Color Bulbs B2) act as repeaters and extend the mesh. Battery-powered devices (locks, sensors) don't repeat. If a device keeps dropping, add a mains-powered device halfway between it and the hub.

Zigbee channels can conflict with 2.4 GHz Wi-Fi. If you have many dropouts, change the Zigbee channel to 15, 20 or 25 in Hub Settings > Advanced > Zigbee channel. After changing channels, battery devices may take up to 1 hour to reconnect.

## Troubleshooting

**Solid red light.** The hub can't reach the internet. Check your router and modem. If using Ethernet, try a different cable or port. Local automations keep running while the hub is offline.

**Devices show "No response."** Check the hub is online first. Then check the device's battery and its distance to the nearest repeater. Power-cycle the hub by unplugging for 10 seconds.

**Can't add a device.** Make sure the device is in pairing mode and within 30 feet of the hub. Remove it from any previous hub first, since Zigbee devices can only be paired to one hub at a time.

**Hub was offline after a power outage.** The backup battery lasts about 4 hours. If the outage was longer, the hub restarts automatically when power comes back; it can take up to 5 minutes for all devices to reconnect.

## Reset

Restart: unplug for 10 seconds.

Factory reset: press and hold the reset pinhole on the bottom for 15 seconds until the light blinks red three times. This removes all paired devices and automations. You'll need to re-pair every device.

## Warranty

2 year limited warranty.
