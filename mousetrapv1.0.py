# mousetrap.py v1.0 Code for a Raspberry Pi Pico W.
# Sends an email msg to recipient@gmail.com if either of the mousetrap beam sensors has been broken.
# It also mails a minute later to inform if any further movement is detected in the trap.
# A battery measurement is also performed which sends a 'change battery' email if the voltage drops below a set level.
# Detects if battery switched on. If not, defaults to mouse-counting mode (ie) beam break detection is active until trap is reset 
# or battery switched on. Used when away from home. 

import machine
import umail
import network
import time
import utime
from machine import Pin,ADC,RTC
import ntptime

# Hardware definition
trap_ID1 = Pin(17, Pin.IN, Pin.PULL_UP) # connect to ground if mousetrap 2 or 4, otherwise leave disconnected
trap_ID2 = Pin(18, Pin.IN, Pin.PULL_UP) # connect to ground if mousetrap 3 or 4, otherwise leave disconnected
led = Pin("LED", machine.Pin.OUT)
break_sensor1 = Pin(15, Pin.IN, Pin.PULL_UP)
break_sensor2 = Pin(14, Pin.IN, Pin.PULL_UP)
solenoid1 = Pin(16, Pin.OUT, Pin.PULL_DOWN)
solenoid2 = Pin(13, Pin.OUT, Pin.PULL_DOWN)
battery = Pin(28, Pin.IN)   # this is needed to turn the ADC input to high impedance
battery = ADC(28) # GP28 ADC 4.5v solenoid battery scaled to 3v

# Mousetrap ID.  A '1' represents an open circuit connection on that GPIO
if trap_ID1.value() == 1 and trap_ID2.value() == 1:
    trap = 'Mousetrap 1'
elif trap_ID1.value() == 0 and trap_ID2.value() == 1:
    trap = 'Mousetrap 2'
elif trap_ID1.value() == 0 and trap_ID2.value() == 0:
    trap = 'Mousetrap 3'
elif trap_ID1.value() == 1 and trap_ID2.value() == 0:
    trap = 'Mousetrap 4'
else:
    trap = 'Mousetrap X'

# Network credentials
ssid = 'network_name' # Network name
password = 'network_password' # Network password

# Email details
sender_email = 'sender@gmail.com' # email address of the sender
sender_name = 'sender_name' # Sender
sender_app_password = 'email_account_app_password' # Sender's email account app password
recipient_email ='recipient@gmail.com' # Recipient's email address
email_subject ='Mouse mail' # Subject of the email
message_1 = '%s has tripped. A 60 second count has started to detect further movement.' % trap

# Misc
toggle = 1
state = 'waiting'
trip_count = 0  # the number of times the beam is broken (only used in 'mouse-counting' (non-trapping) mode) 
loop_cycles = 0
hour_count = 0
ntptime.host = '0.pool.ntp.org' # Define time server
if trap == 'Mousetrap 1':
    battery_cal = 5.35
elif trap == 'Mousetrap 2':
    battery_cal = 5.25
elif trap == 'Mousetrap 3':
    battery_cal = 5.1
elif trap == 'Mousetrap 4':
    battery_cal = 5.4
else:
    battery_cal = 5.0

print('Starting', trap)

# Get battery voltage
def get_bat_volts():
    battery_voltage = (battery.read_u16()/65535)*battery_cal
    battery_voltage = round(battery_voltage, 2)
    return (battery_voltage)
        
# Get current time from internet
def get_time():
    try:
        ntptime.settime() # set RTC from NTP
        year, month, day, dow, hour, mins, secs = RTC().datetime()[0:7]
        f_time = '{:02}/{:02}/{:02} {:02}:{:02}:{:02}'.format(day, month, year % 100, hour, mins, secs)
    except:
        print('Error syncing time, default values set')
        f_time = '{:02}/{:02}/{:02} {:02}:{:02}:{:02}'.format(1, 1, 2000 % 100, 0, 0, 0)
    return(f_time, year)

def connect_wifi(ssid, password):
    # Connect to the network using the provided credentials
    station = network.WLAN(network.STA_IF)
    station.active(True)
    station.connect(ssid, password)
    # Wait for the connection to be established
    while station.isconnected() == False:
        pass
    print('Connection successful') # Print a message if the connection is successful
    print(station.ifconfig()) # Print the network configuration
    return(station.ifconfig()[0])

def sendmail(sender_email, sender_app_password, recipient_email, sender_name, message):
    # Connect to Gmail's SSL port
    smtp = umail.SMTP('smtp.gmail.com', 465, ssl=True)
    # Login to the email account using the app password
    smtp.login(sender_email, sender_app_password)
    # Specify the recipient email address
    smtp.to(recipient_email)
    # Write the email header
    smtp.write("From:" + sender_name + "<"+ sender_email+">\n")
    smtp.write("Subject:" + email_subject + "\n")
    # Write the body of the email
    smtp.write('\n\n' + formatted_time + '\n\n' + message)
    # Send the email
    smtp.send()
    # Quit the email session
    smtp.quit()
    return()

# Main programme

# Connect to the network
ip = connect_wifi(ssid, password)

# Synchronise RTC with NTP time
f_time = get_time() # returns time as a tuple. [0] is formatted time; [1] is the year (used for dealing with time sync issues)
formatted_time = f_time[0]
#print ('formatted_time is ', formatted_time)
f_year = f_time[1]
#print ('year is ', f_year)
if f_year == 2000 and t_count < 10: # try ten more times to sync the time.
    t_count += 1
    print('Attempt %s to time sync with the NTP server.') % t_count
    time.sleep(2)
    f_time = get_time() # try to get the time again
    
# Measure the solenoid battery voltage
battery_voltage = get_bat_volts()
if battery_voltage > 2.0:
    mode = 'mousetrap'
else:
    mode = 'mouse-counting'

# Send start-up email
message = '%s has started in %s mode, is connected to the network as %s and is waiting for a mouse. Solenoid battery voltage is %s volts' % (trap, mode, ip, str(battery_voltage))
sendmail(sender_email, sender_app_password, recipient_email, sender_name, message)
print('mail sent: ',message)

while True: # Main loop
    battery_voltage = get_bat_volts()
    if battery_voltage > 2.0: mode = 'mousetrap'
    else: mode = 'mouse-counting'
    year, month, day, dow, hour, mins, secs = RTC().datetime()[0:7]
    formatted_time = "{:02}/{:02}/{:02} {:02}:{:02}:{:02}".format(day, month, year % 100, hour, mins, secs)
    if break_sensor1.value() == 0 or break_sensor2.value() == 0: # mouse detected/beam interrupted
        if mode == 'mousetrap':  # mousetrap mode
            led.on()
            solenoid1.on()
            solenoid2.on()
            time.sleep(0.2)
            solenoid1.off()
            solenoid2.off()
            print('beam triggered')
            sendmail(sender_email, sender_app_password, recipient_email, sender_name, message_1)  
            print('email sent: ',message_1)
            state = 'triggered'
        else:  # mouse-counting mode
            trip_count += 1
            time.sleep(1)
            #print('trip count = ', trip_count)
    else:
        loop_cycles +=1
        time.sleep(0.1)
    # turn led on/off every 2 seconds    
    if loop_cycles % 20 == 0: # modulo 20, will return 0 every 20 loop_cycles 
        toggle = 1 - toggle # alternates 1, 0, 1, 0 etc every pass
        if toggle == 1: led.on()
        if toggle == 0: led.off()
    if loop_cycles == 36000: # 36000 Check battery voltage once an hour (when loop_cycles = 36000)
        loop_cycles = 0
        hour_count += 1
        battery_voltage = (battery.read_u16()/65535)*battery_cal
        battery_voltage = round(battery_voltage, 2)
        #print('Battery voltage = ',battery_voltage)
        if battery_voltage > 1 and battery_voltage < 4.3: # Don't email if the battery is off or missing
            message = '%s solenoid battery voltage is %s volts. Consider replacement' % (trap, str(battery_voltage))
            sendmail(sender_email, sender_app_password, recipient_email, sender_name, message)
            print('email sent: ',message)
        if hour_count == 24: # 24 Send a status message every day
            hour_count = 0
            if mode == 'mousetrap':
                message = '%s is waiting to catch a mouse. The battery voltage is %s.' % (trap, battery_voltage)
                sendmail(sender_email, sender_app_password, recipient_email, sender_name, message)
                print('email sent: ',message)
            else:
                message = '%s is in mouse-counting mode. The trip count is %s' % (trap, trip_count)
                sendmail(sender_email, sender_app_password, recipient_email, sender_name, message)
                print('email sent: ',message)
    if state == 'triggered' and mode == 'mousetrap': # actions to undertake when mouse detected
        led.off()
        break_count = 0
        time.sleep(1) # allow time for mouse to scarper if door jams.
        for n in range(600): # 600 = 60 second loop. Check for further beam-breaking.
            if break_sensor1.value() == 0 or break_sensor2.value() == 0: # beam interrupted
                break_count += 1
            time.sleep(0.1)
        if break_count != 0:
            message = '%s is now in wait mode, waiting for furry friend relocation - additional movement detected.' % trap
        else:
            message = '%s is now in wait mode, waiting for reset - no additional movement detected.' % trap      
        sendmail(sender_email, sender_app_password, recipient_email, sender_name, message)
        print('email sent: ',message)
        time.sleep(10000000) # place the mousetrap in suspension
