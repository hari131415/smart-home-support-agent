---
device_type: thermostat
model: Kestrel Thermostat T3
---

# Kestrel Thermostat T3 User Manual

## Specifications

- Display: 2.4 inch color touchscreen
- Connectivity: Wi-Fi 2.4 GHz (802.11 b/g/n). 5 GHz networks are not supported.
- Power: 24 VAC from the HVAC system via the C-wire. A Power Extender Kit (PEK-2) is included for systems without a C-wire.
- Supported systems: conventional gas, oil and electric furnaces, heat pumps with auxiliary heat, up to 2 heat / 2 cool stages.
- Not compatible with: line-voltage systems (120 V or 240 V baseboard heaters) and millivolt systems such as some gas fireplaces.
- Temperature range: setpoints between 45°F and 90°F (7°C to 32°C).
- Operating humidity: 5% to 90% non-condensing.

## Installation and wiring

Turn off power to your HVAC system at the breaker before removing the old thermostat. Take a photo of the existing wiring before disconnecting anything.

Connect each labeled wire to the matching terminal on the T3 base plate: R (or Rh/Rc), W, Y, G, and C. If you have separate Rh and Rc wires, remove the factory jumper between them. For heat pumps, connect the reversing valve wire to the O/B terminal and choose "O" or "B" during setup based on your system's documentation.

If you do not have a C-wire, install the PEK-2 at the furnace control board using the included diagram. Without a C-wire or the PEK-2 the thermostat will run on its internal battery and shut down within 24 hours.

## First-time setup

1. Restore power at the breaker. The T3 shows the Kestrel logo and then the language screen.
2. Open the Kestrel Home app, tap Add Device, then Thermostat.
3. Scan the QR code on the back of the faceplate or enter the 8-digit setup code.
4. Choose your 2.4 GHz Wi-Fi network and enter the password.
5. Answer the system questions (heat type, heat pump, number of stages). The app runs a wiring check and shows any missing terminals.

Setup usually takes about 10 minutes.

## Schedules and modes

The T3 supports Heat, Cool, Auto (heat-cool) and Off modes. In Auto, the heat and cool setpoints must be at least 3°F (1.5°C) apart.

Schedules can have up to 6 setpoints per day. Eco mode uses separate Eco temperatures (default 62°F heat / 80°F cool) when everyone is away, based on phone location from the app.

A temporary hold keeps your manual change until the next scheduled setpoint. A permanent hold is available from Settings > Hold.

## Display and status messages

- Blinking green ring: connecting to Wi-Fi.
- Solid orange flame icon: heating is running.
- Blue snowflake icon: cooling is running.
- "Delayed" with a countdown: compressor protection is active. The T3 waits 5 minutes between compressor cycles to protect the equipment. This is normal.
- "E74" on screen: no power detected on the C-wire or R wire. Check the wiring and the HVAC breaker.
- "E21": the system has been calling for heat for 60 minutes without the room temperature rising.
- Battery icon with a red bar: internal battery is below 3.6 V and the thermostat is not getting enough power.

## Troubleshooting

**Thermostat shows offline in the app.** Confirm your router is broadcasting a 2.4 GHz network. On the thermostat go to Settings > Network and check the signal strength; below 2 bars, move the router or add a mesh point. Restart the thermostat by pressing and holding the display for 10 seconds.

**System doesn't turn on.** Check that the mode is not set to Off and the setpoint is above (heat) or below (cool) the current temperature. If "Delayed" is shown, wait for the 5 minute compressor timer.

**Short cycling (turns on and off quickly).** Open Settings > Equipment and increase the minimum cycle time to 10 minutes. Also confirm the thermostat is not mounted near a heat source like a lamp, a sunny window, or a supply vent.

**Temperature reading looks wrong.** Allow 1 hour after installation for the sensor to settle. You can add an offset of up to ±5°F in Settings > Sensor > Temperature offset.

**Display is blank.** This almost always means the T3 is not getting power. Check the HVAC breaker and the furnace door switch, then check the R and C wires.

## Reset

Restart: press and hold the display for 10 seconds.

Factory reset: go to Settings > Reset > Factory reset and confirm. This erases schedules, Wi-Fi credentials and the wiring configuration. You'll need to remove the device from the Kestrel Home app and set it up again.

## Firmware updates

Firmware updates install automatically between 2 AM and 4 AM local time. The thermostat keeps heating or cooling during the update but the screen may restart. To check the current version go to Settings > About.

## Warranty

The T3 has a 2 year limited warranty from the date of purchase.
