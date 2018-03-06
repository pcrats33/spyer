#!/usr/bin/env python

#################################################################
###    spyer.py         Raspberry Pi Spycam                   ###
###    2/5/2018         Author: Rick Tilley                   ###
#################################################################
###                                                           ###
###  This program connects to a raspberry pi camera and       ###
###  motion sensor.  It will wait for motion and start        ###
###  recording video along with taking snapshots.  Snapshots  ###
###  are sent by email and stored in the ./snapshots folder.  ###
###  Video is stored in the ./captures folder.  A separate    ###
###  program may move the video captures to cloud storage.    ###
###  Program configuration is found in the spyer.config file. ###
###                                                           ###
#################################################################


import datetime
from picamera import PiCamera
from time import sleep
import RPi.GPIO as GPIO
from Crypto.Cipher import AES
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
import shutil

PIR_OUT_PIN = 11    # pin11
SHUTTER_SPEED = 2
TIME_RECORD = 10
MOTION_SPEED = 20

camera = PiCamera()
recording = 0

def setup():
    GPIO.setmode(GPIO.BOARD)       # Numbers GPIOs by physical location
    GPIO.setup(PIR_OUT_PIN, GPIO.IN)    # Set BtnPin's mode is input
#    camera.resolution = (1920, 1080)
    camera.resolution = (1280, 720)
    camera.framerate = 60

def switchbuffer(a, b):
    timediff = a - b
    if recording == 0:
        if timediff.total_seconds() >= SHUTTER_SPEED:
            return 1
        else:
            return 0
    elif recording == 1:            
        if timediff.total_seconds() >= TIME_RECORD:
            return 1
        else:
            return 0

def sendsnap(fn, turn):
    send = smtplib.SMTP_SSL(email_server)
    send.login(email_sender, turn)
    msg = MIMEMultipart()
    msg['subject'] = 'Activity detected at home'
    msg['From'] = email_sender 
    msg['To'] = email_receiver
    msg.preamble = 'Here is the latest %s' % fn
    fp = open(fn, 'rb')
    img = MIMEImage(fp.read())
    fp.close()
    msg.attach(img)
    send.sendmail(email_sender, email_receiver, msg.as_string())

def camsleep(t, active):
    if active:
        camera.wait_recording(t)
    else:
        sleep(t)

def loop():
    # initialize loop, load values from config file
    lastchange = datetime.datetime.now() - datetime.timedelta(seconds=SHUTTER_SPEED)
    spin = open("spyer.config", "r")
    p1 = spin.readline().rstrip('\n')
    global email_server
    global email_sender
    global email_receiver
    email_server = spin.readline().rstrip('\n')
    email_sender = spin.readline().rstrip('\n')
    email_receiver = spin.readline().rstrip('\n')
    spin.close()
    part = open("spyer.hash", "r")
    p2 = part.read()
    part.close()
    obj = AES.new(p1, AES.MODE_CFB, 'This is an IV456')
    part = obj.decrypt(p2)
    recording = 0
    detected = 0
    tmpvid = ""
    print "Starting spy camera."
    # infite loop until Ctrl-C interrupt, this is our camera loop.
    while True:
        if not detected and recording:
            now = datetime.datetime.now()
            if switchbuffer(now, lastchange):
                #camera.stop_preview()
                camera.stop_recording()
#                shutil.move('./tmp/%s' % tmpvid, './captures/%s' % tmpvid)
                recording = 0
                lastchange = now
                # print 'Movement not detected turning off camera'
        elif detected and not recording:
            now = datetime.datetime.now()
            if switchbuffer(now, lastchange):
                #camera.start_preview()
                tmpvid = 'home_%s.h264' % now.strftime('%Y%m%d_%H%M%S')
                camera.start_recording('./tmp/%s' % tmpvid)
                recording = 1
                lastchange = now
                camf = './snaps/homeimage_%s.jpg' % now.strftime('%Y%m%d_%H%M%S')
                camera.capture(camf, use_video_port=True)
                sendsnap(camf, part)
                # print 'Movement detected! Camera activated.'

        delaystart = delaynow = datetime.datetime.now()
        detected = 0
        lapse = 0
        # wait at least MOTION_SPEED seconds before reacting again
        while lapse < MOTION_SPEED and (recording or not detected):
            camsleep(1, recording)
            delaynow = datetime.datetime.now()
            lapse = (delaynow - delaystart).total_seconds()
#            if lapse % 6 == 0:
#                camera.annotate_text = delaynow.strftime("%Y-%m-%d %H:%M:%S")
            if not detected:
                detected = 0 if GPIO.input(PIR_OUT_PIN) == GPIO.LOW else 1
        # break videos into MOTION_SPEED Length segments
        if detected and recording:
            tmp = 'home_%s.h264' % now.strftime('%Y%m%d_%H%M%S')
            camera.split_recording('./tmp/%s' % tmp)
            camsleep(2, recording)
#            shutil.move('./tmp/%s' % tmpvid, './captures/%s' % tmpvid)
            tmpvid = tmp

# end main loop

def destroy():
    GPIO.cleanup()                     # Release resource

if __name__ == '__main__':     # Program start from here
    setup()
    try:
        loop()
    except KeyboardInterrupt:  # When 'Ctrl+C' is pressed, the child program destroy() will be  executed.
        print "Spy camera shutting down."
        if recording == 1:
            camera.stop_recording()
#            camera.stop_preview()
        destroy()
