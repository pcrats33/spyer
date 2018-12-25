#!/usr/bin/python

#################################################################
###    spyerdaemon.py   Raspberry Pi Spycam                   ###
###    11/01/2018       Author: Rick Tilley                   ###
#################################################################
###                                                           ###
###  This program moves videos out of the temp directory      ###
###  and sends it out.  Runs continuously as a helper program.###
###                                                           ###
#################################################################

from os import listdir
from os.path import isfile, join
import os
from time import sleep

spin = open("spyer.config", "r")
for skip in range(1,5):
    x = spin.readline().rstrip('\n')
    print "ignoring: %s" % x
rsa = spin.readline().rstrip('\n')
ip = spin.readline().rstrip('\n')
mypath = "/home/pi/spyer/tmp/"
vidpath = "/home/pi/spyer/captures/"
homepath = "/home/pi/"
print "rsa = %s" % rsa
print "ip = %s" % ip
sleep(22)
while True:
    dirz = [f for f in listdir(mypath) if isfile(join(mypath, f))]
    loading = []
    if any(dirz):
        for f in dirz:
            if ".loading" in f:
                loading.append(f)
                loading.append(f[:-len(".loading")])
        for f in dirz:
            if f not in loading:
                command = "scp -i %s %s spyer@%s:%s" % (homepath + rsa, mypath + f, ip, "/home/spyer/captures/")
                print "exec %s" % command
                ret = os.system(command)
                if ret == 0:
                    try:
                        ret = os.rename(mypath + f, vidpath + f)
                    except (OSError, e):
                        print("[%s] unable to move file %s to %s" % (str(e.errorno), mypath + f, vidpath + f))
                sleep(3)
    sleep(15)

