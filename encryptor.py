#!/usr/bin/env python

import sys
from Crypto.Cipher import AES

if len(sys.argv) < 2:
  print "Requires one argument to encrypt."
  exit (-1)

spin = open("spyer.config", "r")
p1 = spin.readline().rstrip('\n')
spin.close()

ps = sys.argv[1]
obj = AES.new(p1, AES.MODE_CFB, 'This is an IV456')
p2 = obj.encrypt(ps)

part = open("spyerReady.hash", "w")
part.write(p2)
part.close()
