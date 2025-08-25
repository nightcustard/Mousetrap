VERSION = 'Mousetrap-I_v1.0' # update this as necessary
#---------------------------------about---------------------------------
# Script:  mousetrap-i_v1.0.py
# Version: 1.0
# Created: 14/08/2025
# Updated: 
# Author:  Mike Armour

# Sends an email msg if the mousetrap beam sensor has been triggered.
# It also mails a minute later to inform if any further movement is detected in the trap.
# A battery measurement is also performed which sends a 'change battery' email if the voltage drops below a set level. 
# Detects if the battery is switched on. If not, defaults to mouse-activity mode (ie) beam break detection is active until trap is reset or battery is switched on.
# Used when away from home.
# The trap_ID1 pin is connected to ground if the mousetrap is number 2 or 4, otherwise is left disconnected.
# The trap_ID2 pin is connected to ground if the mousetrap is number 3 or 4, otherwise is left disconnected.
# Daily status message sent at 12am (see 'status_hour' variable - 11 in summer time, 12 in winter time)
# Daily reconnection with WiFi network added to reduce instances where the mousetrap stops responding on WiFi. 
#----------------------------------------------------------------------

import machine, umail, network, time, utime, ntptime, os
from machine import Pin, ADC, RTC

# Global constants and network credentials
SSID = 'your SSID'
PASSWORD = 'your WiFi password'
SENDER_EMAIL = 'sender@gmail.com' # email address of the sender
SENDER_NAME = 'Sender name'
SENDER_APP_PASSWORD = 'xxxx xxxx xxxx xxxx' # sender@gmail.com email account app password
RECIPIENT_EMAIL = 'recipient@gmail.com' # probably your email address
NTP_HOST = '0.pool.ntp.org' # Time server

# Hardware shared by all traps (e.g., LED)
led = Pin("LED", machine.Pin.OUT)
toggle = 1 # Used by the LED on/off logic

# Trap configuration data
TRAP_CONFIGS = {
    (0, 0): ('Mousetrap 1', 'single'),
    (0, 1): ('Mousetrap 2', 'dual'),
    (1, 0): ('Mousetrap 3', 'tba'),
    (1, 1): ('Mousetrap 4', 'dual')
}

TRAP_DATA = {
    'Mousetrap 1': {'battery_cal': 5.0, 'loop_cycles_1h': 35751},
    'Mousetrap 2': {'battery_cal': 5.0, 'loop_cycles_1h': 35751},
    'Mousetrap 3': {'battery_cal': 5.0, 'loop_cycles_1h': 35751},
    'Mousetrap 4': {'battery_cal': 5.0, 'loop_cycles_1h': 35751}
}

DEFAULT_DATA = {'battery_cal': 5.0, 'loop_cycles_1h': 35751}

# Utility functions

def connect_wifi(ssid, password):
    station = network.WLAN(network.STA_IF)
    station.active(True)
    station.connect(ssid, password)
    max_count = 10
    for count in range(max_count):
        time.sleep(1)
        if station.isconnected():
            print('Connection successful')
            print(station.ifconfig())
            return station.ifconfig()[0] # IP address
    return 'Not connected'

def network_connect():
    max_attempts = 10
    for count in range(max_attempts):
        print(f'Attempt {count + 1} to connect to the WiFi network.')
        ip = connect_wifi(SSID, PASSWORD)
        if ip != "Not connected":
            print(f'Successfully connected with IP: {ip}')
            return ip
        time.sleep(1)
    print("Mousetrap is suspended as can't connect to wifi")
    time.sleep(10000000) # Place the mousetrap in a very long sleep.
    return None

def sendmail(subject, message):
    try:
        year, month, day, _, hour, mins, secs = RTC().datetime()[:7]
		hour = hour + GMT_OFFSET # Set to local time
        formatted_time = '{:02}/{:02}/{:02} {:02}:{:02}:{:02}'.format(day, month, year % 100, hour, mins, secs)
        smtp = umail.SMTP('smtp.gmail.com', 465, ssl=True)
        smtp.login(SENDER_EMAIL, SENDER_APP_PASSWORD)
        smtp.to(RECIPIENT_EMAIL)
        smtp.write(f'From: {SENDER_NAME} <{SENDER_EMAIL}>\n')
        smtp.write(f'Subject: {subject}\n')
        smtp.write(f'\n\n{formatted_time} (Local time)\n\n{message}')
        smtp.send()
        smtp.quit()
        return 'OK'
    except Exception as e:
        print(f'Error sending mail: {e}')
        return 'Not_OK'

# Get current time from internet
def get_time():
    try:
        ntptime.settime() # set RTC from NTP
        year, month, day, dow, hour, mins, secs = RTC().datetime()[0:7]
        hour = hour + GMT_OFFSET # Set to local time
        f_time = '{:02}/{:02}/{:02} {:02}:{:02}:{:02}'.format(day, month, year % 100, hour, mins, secs)
    except:
        print('Error syncing time, default values set')
        f_time = '{:02}/{:02}/{:02} {:02}:{:02}:{:02}'.format(1, 1, 2000 % 100, 0, 0, 0)
        year = 2000
    return(f_time, year)

# Synchronise the Real-Time Clock (RTC) with an NTP server; Returns a tuple: The formatted time and year on success, or (None, None) on failure.
def sync_ntp_time(max_attempts=10):
    for attempt in range(1, max_attempts + 1):
        formatted_time, year = get_time()
        if year != 2000:
            print(f'Time synchronization successful. Current time: {formatted_time}')
            return formatted_time, year # Return on success
        print(f'Attempt {attempt} to sync with NTP failed. Retrying...')
        time.sleep(2)   
    print(f'Failed to synchronize with NTP after {max_attempts} attempts.')
    return None, None # Return failure indicator

class Mousetrap:
    def __init__(self, trap_id1_pin, trap_id2_pin, break_sensor1_pin, break_sensor2_pin, solenoid1_pin, solenoid2_pin, battery_pin, ip):
        self.ip = ip # LAN IP address of mousetrap
        self.trap_id_key = (trap_id1_pin.value(), trap_id2_pin.value()) # hardware pull-downs to identify trap
        self.name, self.trap_type = TRAP_CONFIGS.get(self.trap_id_key, ('Mousetrap X', 'tba'))
        self.trap_info = TRAP_DATA.get(self.name, DEFAULT_DATA)
        self.battery_cal = self.trap_info['battery_cal']
        self.loop_cycles_1h = self.trap_info['loop_cycles_1h'] # determined by trial and error

        self.break_sensor1 = Pin(break_sensor1_pin, Pin.IN, Pin.PULL_UP)
        self.break_sensor2 = Pin(break_sensor2_pin, Pin.IN, Pin.PULL_UP)
        self.solenoid1 = Pin(solenoid1_pin, Pin.OUT, Pin.PULL_DOWN)
        self.solenoid2 = Pin(solenoid2_pin, Pin.OUT, Pin.PULL_DOWN)
        self.battery_adc = ADC(battery_pin) # GP28 ADC 4.5v solenoid battery scaled by potential divider to 3v
        
        self.battery_voltage = 0
        self.mode = 'mousetrap'
        self.loop_cycles = 0 # Main programme cycle count
        self.trip_count = 0 # the number of times the beam is broken (only used in 'mouse-activity' (non-trapping) mode)
        self.state_A = 0 # state_A & B become 1 when respective beam is triggered (to stop repeat triggers)
        self.state_B = 0
        self.msgsent = 0 # Flag to prevent multiple status messages being sent

        self.status_hour = 11 # Hour of the day to send daily status message (GMT)
        self.status_mins = 0 # See above, minutes
        self.solenoid_on_time = 0.2 # in seconds. Determined experimentally.
        self.motion_check_secs = 600 # 1 second = 10 counts; (ie) 60 seconds

        print(f"{VERSION}: Starting {self.name} with battery calibration: {self.battery_cal} and loop cycles: {self.loop_cycles_1h}")

    def get_battery_voltage(self):
        voltage = (self.battery_adc.read_u16() / 65535) * self.battery_cal
        self.battery_voltage = round(voltage, 2)
        if self.battery_voltage > 2.0:
            self.mode = 'mousetrap'
            if self.battery_voltage < 4.3:
                message = f'{self.name} solenoid battery voltage is {self.battery_voltage} volts. Consider replacement.'
                subject = f'{self.name} @ {self.ip} battery message'
                sendmail(subject, message)
        else:
            self.mode = 'mouse-activity'


    def check_sensors(self):
        triggered_A = self.break_sensor1.value() == 0 and self.state_A != 2 # True if beam of single trap is currently interrupted for the first time 
        triggered_B = self.break_sensor2.value() == 0 and self.state_B != 2 # Ditto for beam 2 of a dual trap
        if triggered_A or triggered_B:
            if self.mode == 'mousetrap':
                led.on()
                if triggered_A and self.state_A == 0: # Fire solenoid if beam has been interrupted for the first time
                    self.solenoid1.on()
                if triggered_B and self.state_B == 0: # Likewise for beam 2 of a dual trap
                    self.solenoid2.on()
                time.sleep(self.solenoid_on_time) # Adjust for minimum on time consistent with reliable operation
                self.solenoid1.off() # turn solenoid off
                self.solenoid2.off()

                if triggered_A and self.state_A == 0:
                    print('beam A triggered')
                    subject = f'beam 1 of {self.name} @ {self.ip} has tripped'
                    message = 'A 60 second count has started to detect further movement.'
                    sendmail(subject, message)
                    self.state_A = 1 # flag to indicate solenoid has fired
                if triggered_B and self.state_B == 0:
                    print('beam B triggered')
                    subject = f'beam 2 of {self.name} @ {self.ip} has tripped'
                    message = 'A 60 second count has started to detect further movement.'
                    sendmail(subject, message)
                    self.state_B = 1
            else: # mouse-activity mode
                self.trip_count += 1
                time.sleep(1)

    def mouse_detect(self): # checks for further beam breaking after the solenoid has fired to confirm a capture
        if (self.state_A == 1 or self.state_B == 1) and self.mode == 'mousetrap': # True if either beam sensor has been triggered. Only actioned once.
            if self.state_A == 1: self.state_A = 2 # Sets a flag to ensure this function and the solenoid firing are only actioned once.
            if self.state_B == 1: self.state_B = 2 # ditto for the other solenoid of dual traps

            led.off()
            break_count = 0
            time.sleep(1)

            for _ in range(self.motion_check_secs):
                if self.break_sensor1.value() == 0 or self.break_sensor2.value() == 0:
                    break_count += 1
                time.sleep(0.1)

            if break_count != 0:
                subject = f'{self.name} @ {self.ip} has probably got a mouse!'
                message = f'{self.name} is now in wait mode - additional movement detected.'
            else:
                message = f'{self.name} is now in wait mode - no additional movement detected.'
                subject = f"{self.name} @ {self.ip} - It's probably not a mouse"

            sendmail(subject, message)
            if self.trap_type == 'single' or (self.state_A == 2 and self.state_B == 2):
                print(f'{self.name} is suspended')
                time.sleep(10000000) # there's no exit() function in micro python, so the script is put to sleep.

    def send_status(self, hour, mins): # Sends a daily status email
        if hour == self.status_hour and mins == self.status_mins and self.msgsent == 0:
            network_connect() # reconnects to the WiFi network (a bodge to overcome random losses of connection)
            if self.mode == 'mousetrap':
                message = f'{self.name} is waiting to catch a mouse. The battery voltage is {self.battery_voltage}.'
                subject = f'{self.name} @ {self.ip} is waiting'
            else:
                message = f'{self.name} is in mouse-activity mode. The trip count is {self.trip_count}.'
                subject = f'{self.name} @ {self.ip} mouse-activity mode'
            sendmail(subject, message)
            self.msgsent = 1
        elif mins - self.status_mins >= 1: # trap to prevent multiple emails being sent during the time between hour:secs and hour:secs+1 
            self.msgsent = 0

    def update(self): # Increment loop counter, check battery voltage hourly, check sensors & check for post-trigger activity
        self.loop_cycles += 1
        if self.loop_cycles == self.loop_cycles_1h: # True once an hour 
            self.loop_cycles = 0
            self.get_battery_voltage()
        self.check_sensors()
        self.mouse_detect()

# Main program execution
if __name__ == '__main__':
      
    # Initialize hardware pins, sync RTC and create a Mousetrap object
    trap_id1 = Pin(17, Pin.IN, Pin.PULL_UP)
    trap_id2 = Pin(18, Pin.IN, Pin.PULL_UP)
    break_sensor1 = Pin(15, Pin.IN, Pin.PULL_UP)
    break_sensor2 = Pin(14, Pin.IN, Pin.PULL_UP)
    solenoid1 = Pin(16, Pin.OUT, Pin.PULL_DOWN)
    solenoid2 = Pin(13, Pin.OUT, Pin.PULL_DOWN)
    battery = Pin(28, Pin.IN) # this is needed to turn the ADC input to high impedance
    
    ip = network_connect()
    
    formatted_time, year = sync_ntp_time() # Synchronise RTC with NTP time (time is GMT); Returns a tuple.
    if year == 'None':
        formatted_time, year = '00/00/00 00:00:00','0000'

    trap_instance = Mousetrap(trap_id1, trap_id2, 15, 14, 16, 13, 28, ip)

    # Initial checks and email
    trap_instance.get_battery_voltage()
    subject = f'{trap_instance.name} @ {trap_instance.ip} startup message'
    message = f'{VERSION}: {trap_instance.name} has started in {trap_instance.mode} mode and is waiting for a mouse. Solenoid battery voltage is {trap_instance.battery_voltage} volts'
    sendmail(subject, message)
    
    while True:
        # LED heartbeat - visual indication mousetrap is running
        if trap_instance.loop_cycles % 20 == 0: # True every 20 cycles (~ every two seconds)
            toggle = 1 - toggle
            if toggle == 1: led.on()
            else: led.off()
        year, month, day, _, hour, mins, secs = RTC().datetime()[:7]
		hour = hour + GMT_OFFSET # Set to local time
        trap_instance.send_status(hour, mins)
        trap_instance.update() # Increment loop counter, check battery voltage hourly, check sensors & check for post-trigger activity
        time.sleep(0.1)
