#!/usr/bin/env python

#################################################################
###    spyer.py         Raspberry Pi Spycam                   ###
###    4/29/2018        Author: Rick Tilley                   ###
#################################################################
###                                                           ###
###  This program connects to a raspberry pi camera and       ###
###  motion sensor.  It will wait for motion and start        ###
###  spycam.recording video along with taking snapshots.  Snapshots  ###
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

#class Emailer:
#    email_server
#    email_sender
#    email_receiver
#    part
#
#    def __init__(self):


class SpyCam:
    'Camera functions and objects'
    detected = 0
    camera = None
    recording = 0
    __stream = None

    def __init__(self):
        self.detected = 0
        self.recording = 0
        self.camera = picamera.PiCamera()
    #    camera.resolution = (1920, 1080)
    #    camera.resolution = (1280, 720)
    #    camera.framerate = 60
        self.camera.resolution = (1296, 730)
        self.camera.framerate = 10
        self.stream = picamera.PiCameraCircularIO(self.camera, seconds=20)
        self.camera.start_recording(self.stream, format='h264')
    def __del__(self):
        self.camera.stop_recording()

    def clearStream(self):
        self.stream.truncate()
        self.stream.seek(0)

    def recordBuffer(self, outfile):
        with self.stream.lock as lock:
            rc = 0
            for frame in self.stream.frames:
                rc = rc + 1
            uc = 0
            bc = 0
            header = None
            for frame in self.stream.frames:
                bc = bc + 1
                if frame.frame_type == picamera.PiVideoFrameType.sps_header:
                    header = frame.position
                    self.stream.seek(header)
                    break
            while True:
                buf = self.stream.read1()
                if not buf:
                    break
                uc = uc + 1
                outfile.write(buf)
            # get other part of circlular stream
            self.stream.seek(0)
            while uc < rc:
                buf = self.stream.read1()
                if not buf:
                    break
                uc = uc + 1
                outfile.write(buf)

            self.clearStream()

        # Wipe the circular stream once we're done
        if __debug__:
            log("Frames: %i    Header Frame: %i    Writen Frames: %i" % (rc, bc, uc))

        
    def wait(self, sec):
        self.camera.wait_recording(sec)
        




spycam = SpyCam()
LogFile = "spyerLog.txt"


def log(message):
    with open(LogFile, "a") as myfile:
        myfile.write("%s\n" % message);
    print "%s" % message

def sendsnap():
    global spycam
    global email_server
    global email_sender
    global email_receiver
    global part
    if __debug__:
        log("Sending e-mail")
    now = datetime.datetime.now()
    fn = './snaps/homeimage_%s.jpg' % now.strftime('%Y%m%d_%H%M%S')
    spycam.camera.capture(fn, use_video_port=True)
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
    global motiontime
    global spycam
    global motioncount
    if motioncount != 1:
        motiontime = datetime.datetime.now()
    motioncount += 1
    if __debug__:
        log("Motion Detected! %s" % motiontime)
        log("motion count %s" % motioncount)
    if not spycam.detected and motioncount > 0:
        spycam.detected = 1


def motion_detection():
    global motiontime
    global motioncount
    global spycam
    PIR_OUT_PIN = 11    # pin11
    motiontime = datetime.datetime.now()
    motioncount = 0
    spycam.detected = 0
    #GPIO.setmode(GPIO.BCM)   # Alternative numbering method
    GPIO.setmode(GPIO.BOARD)       # Numbers GPIOs by physical location
    GPIO.setup(PIR_OUT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)    # Set BtnPin's mode is input
    GPIO.add_event_detect(PIR_OUT_PIN, GPIO.FALLING, callback=motion_detected)

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
    global spycam
    global email_server
    global email_sender
    global email_receiver
    global part
    global motiontime
    global motioncount
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
    tmpvid = ""
    log("Starting spy camera.")


    motion_detection()
#    motion_thread = threading.Thread(target=motion_detection)
#    motion_thread.start()
    email_thread = threading.Thread(target=sendsnap)
    # infite loop until Ctrl-C interrupt, this is our camera loop.
    polla = pollb = b = a = datetime.datetime.now()
    captures = 0
    while True:
        if outOfSpace():
            raise ValueError('Drive out of space.  Closing program.') 
        b = c = datetime.datetime.now()
        while (b-c).total_seconds() < 10 and spycam.detected == 0:
            b = datetime.datetime.now()
            spycam.camera.annotate_text = b.strftime("%Y%m%d_%H:%M:%S")
            spycam.wait(1)
#        if __debug__:
#            log("looping spycam.detected value: %d") % spycam.detected
        if spycam.detected and not spycam.recording:
            if not email_thread.is_alive():
                try:
                    email_thread.start();
                except RuntimeError:
                    email_thread = threading.Thread(target=sendsnap)
                    email_thread.start();
            starttime = motiontime
            if __debug__:
                log("starting to buffer capture : %s" % starttime)
            tmpvid = 'home_%s.h264' % starttime.strftime("%Y%m%d_%H%M%S")
            outfile = io.open('./tmp/%s' % tmpvid, 'wb')
            spycam.recording = 1
 
        if spycam.detected and spycam.recording:
            b = datetime.datetime.now()
            while (b-a).total_seconds() < 20:
                b = datetime.datetime.now()
                spycam.camera.annotate_text = b.strftime("%Y%m%d_%H:%M:%S")
                spycam.wait(1)
            a = datetime.datetime.now()
            captures += 1
            spycam.recordBuffer(outfile)
#            stream.copy_to('./tmp/%s' % tmpvid)
            nowtime = datetime.datetime.now()
            motioncount = 0
#            nowstr = nowtime.strftime("%Y%m%d_%H%M%S")
            if (nowtime - motiontime).total_seconds() > 35 or (nowtime - starttime).total_seconds() > 90:
                spycam.detected = 0
                spycam.recording = 0
                outfile.close()
                if __debug__:
                    log("closing buffer capture, going idle. : %s, last motion: %s" % (nowtime.strftime("%H:%M:%S"), motiontime.strftime("%H:%M:%S")))
                if outOfSpace():
                    raise ValueError('Drive out of space.  Closing program.') 

        # keep trailing buffer short
        if not spycam.detected:
            spycam.clearStream()
        pollb = datetime.datetime.now() 
        # forget a motion trigger (for double motion detection)
        if (pollb - motiontime).total_seconds > 20 and motioncount and not spycam.recording:
            motioncount = 0
        # don't allow for constant video taping in case of PIR malfunction 
        if (pollb - polla).total_seconds > 3600:
            polla = pollb
            if captures > 50:
                raise ValueError('Too much activity, there may be a sensor malfunction.')
            captures = 0

# end main loop

def destroy():
    global outfile
    global spycam
    if spycam.recording:
        spycam.recordBuffer(outfile)
        outfile.close()

    GPIO.cleanup()                     # Release resource

if __name__ == '__main__':     # Program start from here
    try:
        loop()
    except ValueError as e:
        print ('ERROR THROWN: ' + repr(e))
    except KeyboardInterrupt:  # When 'Ctrl+C' is pressed, the child program destroy() will be  executed.
        log("Spy camera shutting down.")
#            camera.stop_preview()
    finally:
        destroy()


