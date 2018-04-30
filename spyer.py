#!/usr/bin/env python

#################################################################
###    spyer.py         Raspberry Pi Spycam                   ###
###    4/29/2018        Author: Rick Tilley                   ###
#################################################################
###                                                           ###
###  This program connects to a raspberry pi camera and       ###
###  motion sensor.  It will wait for motion and start        ###
###  recording video along with taking snapshots.  Snapshots  ###
###  are sent by email and stored in the ./snap folder.       ###
###  Video is stored in the ./captures folder.  A separate    ###
###  program may move the video captures to cloud storage.    ###
###  Program configuration is found in the spyer.config file. ###
###                                                           ###
###  Program has been going through some revisions as i'm     ###
###  finding better methods to monitor PIR and record video.  ###
###  There is still some cleanup of this code to be done...   ###
###                                                           ###
###                                                           ###
#################################################################


import datetime
import picamera
from time import sleep
import RPi.GPIO as GPIO
from Crypto.Cipher import AES
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
import shutil
import threading
import os
import io

PIR_OUT_PIN = 11    # pin11

detected = 0
camera = picamera.PiCamera()
recording = 0

def setup():

#    camera.resolution = (1920, 1080)
#    camera.resolution = (1280, 720)
#    camera.framerate = 60
    camera.resolution = (1296, 730)
    camera.framerate = 10


def sendsnap():
    global camera
    global email_server
    global email_sender
    global email_receiver
    global part
    if __debug__:
        print "Sending e-mail"
    now = datetime.datetime.now()
    fn = './snaps/homeimage_%s.jpg' % now.strftime('%Y%m%d_%H%M%S')
    camera.capture(fn, use_video_port=True)
    send = smtplib.SMTP_SSL(email_server)
    send.login(email_sender, part)
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

def motion_detected(PIR_PIN):
    if __debug__:
        print "Motion Detected!"
    global motiontime
    global detected
    motiontime = datetime.datetime.now()
    if (not detected):
        detected = 1
#        delaystart = delaynow = datetime.datetime.now()
        


def motion_detection():
    global motiontime
    global detected
    motiontime = datetime.datetime.now()
    detected = 0
    #GPIO.setmode(GPIO.BCM)
    GPIO.setmode(GPIO.BOARD)       # Numbers GPIOs by physical location
    GPIO.setup(PIR_OUT_PIN, GPIO.IN)    # Set BtnPin's mode is input
    GPIO.add_event_detect(PIR_OUT_PIN, GPIO.RISING, callback=motion_detected)

def outOfSpace():
    df = os.popen("df -h /")
    line = df.readline()
    line = df.readline()
    dfInfo = line.split()[0:6]
    space = dfInfo[3] + " "
    if space.find('G') < 1 or (dfInfo[3].find('G') == 1 and int(dfInfo[3][0]) < 4):
        return True
    return False


def loop():
    # initialize loop, load values from config file
    spin = open("spyer.config", "r")
    p1 = spin.readline().rstrip('\n')
    global camera
    global email_server
    global email_sender
    global email_receiver
    global part
    global detected
    global motiontime
    global outfile
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
    stream = picamera.PiCameraCircularIO(camera, seconds=20)
    camera.start_recording(stream, format='h264')
    motion_detection()
#    motion_thread = threading.Thread(target=motion_detection)
#    motion_thread.start()
    email_thread = threading.Thread(target=sendsnap)
    # infite loop until Ctrl-C interrupt, this is our camera loop.
    while True:
        if outOfSpace():
            raise ValueError('Drive out of space.  Closing program.') 
        camera.wait_recording(4)
        if __debug__:
            print "looping detected value: %d" % detected
        if detected and not recording:
            if __debug__:
                print "starting to buffer capture"
            if not email_thread.is_alive():
                try:
                    email_thread.start();
                except RuntimeError:
                    email_thread = threading.Thread(target=sendsnap)
                    email_thread.start();
            starttime = datetime.datetime.now()
            tmpvid = 'home_%s.h264' % starttime.strftime("%Y%m%d_%H%M%S")
            outfile = io.open('./tmp/%s' % tmpvid, 'wb')
            recording = 1
 
        if detected and recording:
            camera.wait_recording(16)
            for frame in stream.frames:
                if frame.frame_type == picamera.PiVideoFrameType.sps_header:
                    stream.seek(frame.position)
                    break
            while True:
                buf = stream.read1()
                if not buf:
                    break
                outfile.write(buf)
            # Wipe the circular stream once we're done
            stream.seek(0)
            stream.truncate()
#            stream.copy_to('./tmp/%s' % tmpvid)
            nowtime = datetime.datetime.now()
#            nowstr = nowtime.strftime("%Y%m%d_%H%M%S")
            if (nowtime - motiontime).total_seconds() > 30 or (nowtime - starttime).total_seconds() > 300:
                detected = 0
                recording = 0
                outfile.close()
                if __debug__:
                    print "closing buffer capture, going idle."
                if outOfSpace():
                    raise ValueError('Drive out of space.  Closing program.') 
            


# end main loop

def destroy():
    global camera
    global outfile
    global recording
    if recording:
        for frame in stream.frames:
            if frame.frame_type == picamera.PiVideoFrameType.sps_header:
                stream.seek(frame.position)
                break
        while True:
            buf = stream.read1()
            if not buf:
                break
            outfile.write(buf)
        outfile.close()
    camera.stop_recording()
    GPIO.cleanup()                     # Release resource

if __name__ == '__main__':     # Program start from here
    setup()
    try:
        loop()
    except ValueError as e:
        print ('ERROR THROWN: ' + repr(e))
    except KeyboardInterrupt:  # When 'Ctrl+C' is pressed, the child program destroy() will be  executed.
        print "Spy camera shutting down."
#            camera.stop_preview()
    finally:
        destroy()


