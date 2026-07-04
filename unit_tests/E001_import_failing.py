#! /usr/bin/env python -m pydblclick
import pprint as pp
from os import system

pp.pprint(globals())

system("echo hello world")

def myfunction():
    system("echo hello again")
    
myfunction()