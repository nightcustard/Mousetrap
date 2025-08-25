This code is written in MicroPython and is intended to be run on the mousetrap described in my Mousetrap Instructable.
The code:
Waits for a break-beam signal caused by a mouse.
Sends a signal in response to the MOSFET driver which in turn fires the solenoid, closing the door of the trap.
Sends an email to alert you the trap needs inspecting.
Sends a routine, daily email telling you it's functional.

It is loaded onto a Pi Pico W or Pi Pico 2 W via Thonny or equivalent.
