#!/usr/bin/env python

#################################################################
###    spyer.py         Raspberry Pi Spycam                   ###
###    11/01/2018       Author: Rick Tilley                   ###
#################################################################
###                                                           ###
###  This program connects to a raspberry pi camera and       ###
###  motion sensor.  It will wait for motion and start        ###
###  spycam.recording video along with taking snapshots.      ###
###      Sent by email and stored in the ./snap folder.       ###
###  Video is stored in the ./tmp      folder.  A separate    ###
###  program may move the video captures to cloud storage.    ###
###  Program configuration is found in the spyer.config file. ###
###                                                           ###
###  Program has been going through some revisions as i'm     ###
###  finding better methods to monitor PIR and record video.  ###
###  There is still some cleanup of this code to be done...   ###
###                                                           ###
###  cloud feature not implemented yet.  still under developm ###
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
import re

SEEK_CUR = 1


class SpyCam:
    'Camera functions and objects'
    detected = 0
    camera = None
    recording = 0
    __stream = None
    name = None

    def __init__(self):
        self.name = "Spycam v0.5 by Rick Tilley"
        self.detected = 0
        self.recording = 0
        self.camera = picamera.PiCamera()
    #    camera.resolution = (1920, 1080)
    #    camera.resolution = (1280, 720)
    #    camera.framerate = 60
        self.camera.resolution = (1296, 730)
        self.camera.framerate = 15
#        self.stream = picamera.PiCameraCircularIO(self.camera, size=170000000, bitrate=17000000)
        self.stream = picamera.PiCameraCircularIO(self.camera, seconds=20)
        self.camera.start_recording(self.stream, format='h264')
    def __del__(self):
        self.camera.stop_recording()

    def clearStream(self):
#        self.stream.seek(0, SEEK_CUR)
        self.stream.seek(0)
        self.stream.truncate()

    def recordBuffer(self, outfile):
        with self.stream.lock as lock:
            rc = 0
            for frame in self.stream.frames:
                rc = rc + 1
            uc = 0
            bc = 0
            header = None
            self.stream.seek(0)
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

class Emailer:
    email_server = None
    email_sender = None
    email_receiver = None
    part = None
    spycam = None
    email_thread = None

    def __init__(self, cam):
        self.spycam = cam
        spin = open("spyer.config", "r")
        p1 = spin.readline().rstrip('\n')
        self.email_server = spin.readline().rstrip('\n')
        self.email_sender = spin.readline().rstrip('\n')
        self.email_receiver = spin.readline().rstrip('\n')
        spin.close()
        self.part = open("spyer.hash", "r")
        p2 = self.part.read()
        self.part.close()
        obj = AES.new(p1, AES.MODE_CFB, 'This is an IV456')
        self.part = obj.decrypt(p2)
        self.email_thread = threading.Thread(target=self.sendemail)

    def sendsnap(self):
        if not self.email_thread.is_alive():
            try:
                self.email_thread.start();
            except RuntimeError:
                self.email_thread = threading.Thread(target=self.sendemail)
                self.email_thread.start();

    def sendemail(self):
        if __debug__:
            log("Sending e-mail")
        now = datetime.datetime.now()
        fn = './snaps/homeimage_%s.jpg' % now.strftime('%Y%m%d_%H%M%S')
        self.spycam.camera.capture(fn, use_video_port=True)
        send = smtplib.SMTP_SSL(self.email_server)
        send.login(self.email_sender, self.part)
        msg = MIMEMultipart()
        msg['subject'] = 'Activity detected at home'
        msg['From'] = self.email_sender 
        msg['To'] = self.email_receiver
        msg.preamble = 'Here is the latest %s' % fn
        fp = open(fn, 'rb')
        img = MIMEImage(fp.read())
        fp.close()
        msg.attach(img)
        send.sendmail(self.email_sender, self.email_receiver, msg.as_string())


class MotionDetector:
    motiontime = None
    spycam = None
    motioncount = 0
    motionstopped = 0

    def __init__(self, cam):
        self.spycam = cam
        PIR_OUT_PIN = 11    # pin11
        self.motiontime = datetime.datetime.now()
        self.motioncount = 0
        self.spycam.detected = 0
        #GPIO.setmode(GPIO.BCM)   # Alternative numbering method
        GPIO.setmode(GPIO.BOARD)       # Numbers GPIOs by physical location
        GPIO.setup(PIR_OUT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)    # Set BtnPin's mode is input
        GPIO.add_event_detect(PIR_OUT_PIN, GPIO.RISING, callback=self.motion_detected)
#        GPIO.add_event_detect(PIR_OUT_PIN, GPIO.FALLING, callback=self.motion_stopped)
        log("Motion Detector started, has camera: %s" % self.spycam.name)

    def motion_detected(self, PIR_PIN):
        self.motionstopped = 0
        if self.motioncount != 1:
            self.motiontime = datetime.datetime.now()
        self.motioncount += 1
        if __debug__:
            log("Motion Detected! %s" % self.motiontime)
            log("motion count %s" % self.motioncount)
        if not self.spycam.detected and self.motioncount > 0:
            self.spycam.detected = 1

    def motion_stopped(self, PIR_PIN):
       self.motionstopped = 1
       log("Motion Stopped")

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
    global outfile
    global placeholder
    stage1path = "./tmp/"
    stage2path = "./captures/"
    tmpvid = ""
    log("Starting spy camera. Camera init name: %s" % spycam.name)
    motion = MotionDetector(spycam)
    email = Emailer(spycam)
    # infite loop until Ctrl-C interrupt, this is our camera loop.
    polla = pollb = b = a = datetime.datetime.now()
    captures = 0
    for f in os.listdir(stage1path):
        if re.search("\.loading", f):
            os.remove(os.path.join(stage1path, f))

    while True:
        if outOfSpace():
            raise ValueError('Drive out of space.  Closing program.') 
        b = c = datetime.datetime.now()
        while (b-c).total_seconds() < 10 and spycam.detected == 0:
            b = datetime.datetime.now()
            if not GPIO.input(11):
                motion.motionstopped = 1
#            log("GPIO %d" % GPIO.input(11))
            spycam.camera.annotate_text = b.strftime("%Y%m%d %H:%M:%S")
            spycam.wait(2)

        if spycam.detected and not spycam.recording:
            email.sendsnap()
            starttime = motion.motiontime
            spycam.camera.annotate_text = starttime.strftime("%Y%m%d %H:%M:%S")
            if __debug__:
                log("starting to buffer capture : %s" % starttime)
            tmpvid = 'home_%s.h264' % starttime.strftime("%Y%m%d_%H%M%S")
            outfile = io.open(stage1path +  tmpvid, 'wb')
            placeholder = stage1path + tmpvid + ".loading"
            loadingspot = io.open(placeholder, 'w')
            loadingspot.close()
            spycam.recording = 1
 
        if spycam.detected and spycam.recording:
            b = datetime.datetime.now()
            while (b-a).total_seconds() < 20:
#                log("GPIO %d" % GPIO.input(11))
                if not GPIO.input(11):
                    motion.motionstopped = 1
                b = datetime.datetime.now()
                spycam.camera.annotate_text = b.strftime("%Y%m%d %H:%M:%S")
                spycam.wait(2)
            log("writing buffer 20 second from %s to %s" % (a.strftime("%H:%M:%S"), b.strftime("%H:%M:%S")))
            captures += 1
            spycam.recordBuffer(outfile)
            a = datetime.datetime.now()
#            stream.copy_to('./tmp/%s' % tmpvid)
            nowtime = datetime.datetime.now()
            motion.motioncount = 0
            nowstr = nowtime.strftime("%Y%m%d %H%M%S")
            if (motion.motionstopped and (nowtime - motion.motiontime).total_seconds() > 35) or (nowtime - starttime).total_seconds() > 60:
                spycam.detected = 0
                spycam.recording = 0
                outfile.close()
                os.remove(placeholder)
                if __debug__:
                    log("closing buffer capture, going idle. : %s, last motion: %s" % (nowtime.strftime("%H:%M:%S"), motion.motiontime.strftime("%H:%M:%S")))
                if outOfSpace():
                    raise ValueError('Drive out of space.  Closing program.') 

        # keep trailing buffer short
        if not spycam.detected:
            spycam.clearStream()
            a = datetime.datetime.now()
        pollb = datetime.datetime.now() 
        # forget a motion trigger (for double motion detection)
        if (pollb - motion.motiontime).total_seconds > 20 and motion.motioncount and not spycam.recording:
            motion.motioncount = 0
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
    GPIO.cleanup()                     # Release resource
    if spycam.recording:
        spycam.recordBuffer(outfile)
        outfile.close()
        os.remove(placeholder)



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


