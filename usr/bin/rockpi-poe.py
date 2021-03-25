#!/usr/bin/env python3
import os
import re
import sys
import time
import syslog
import RPi.GPIO as GPIO  # pylint: disable=import-error
from pathlib import Path
from configparser import ConfigParser

conf = {}
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(13, GPIO.OUT, initial=GPIO.LOW)
pin13 = GPIO.PWM(13, 75)
p1 = re.compile(r't=(\d+)\n$')


def enable_poe():
    with open('/boot/config.txt', 'r') as f:
        content = f.read()

    if 'dtoverlay=w1-gpio' not in content:
        with open('/boot/config.txt', 'w') as f:
            f.write(content.strip() + '\ndtoverlay=w1-gpio')

    os.system('modprobe w1-gpio')
    os.system('modprobe w1-therm')


def read_sensor_temp():
    w1_slave = conf.get('w1_slave')
    if not w1_slave:
        try:
            w1_slave = next(Path('/sys/bus/w1/devices/').glob('28*/w1_slave'))
        except Exception:
            w1_slave = 'not exist'
            syslog.syslog('The sensor will take effect after reboot.')
        conf['w1_slave'] = w1_slave

    if w1_slave == 'not exist':
        return 42
    else:
        with open(w1_slave) as f:
            t = int(p1.search(f.read()).groups()[0]) / 1000.0
        return t


def read_soc_temp():
    with open('/sys/class/thermal/thermal_zone0/temp') as f:
        t = int(f.read().strip()) / 1000.0
    return t


def read_temp():
    t1 = read_sensor_temp()
    t2 = read_soc_temp()
    return max(t1, t2)


def read_conf():
    try:
        cfg = ConfigParser()
        cfg.read('/etc/rockpi-poe.conf')
        conf['lv0'] = cfg.getint('fan', 'lv0')
        conf['lv1'] = cfg.getint('fan', 'lv1')
        conf['lv2'] = cfg.getint('fan', 'lv2')
        conf['lv3'] = cfg.getint('fan', 'lv3')
    except Exception:
        conf['lv0'] = 40
        conf['lv1'] = 45
        conf['lv2'] = 50
        conf['lv3'] = 55


def change_dc(dc, cache={}):
    if dc != cache.get('dc'):
        pin13.ChangeDutyCycle(dc)
        cache['dc'] = dc


def turn_off():
    try:
        GPIO.setup(22, GPIO.OUT)
        GPIO.output(22, GPIO.LOW)
    finally:
        pin13.stop()
    

def turn_on():
    try:
        GPIO.setup(22, GPIO.OUT)
        GPIO.output(22, GPIO.HIGH)
    finally:  # BCM22 not available on v1.3 
        pin13.start(100)

    read_conf()

    while True:
        t = read_temp()
        if t >= conf['lv3']:
            print('100%')
            change_dc(100)
        elif t >= conf['lv2']:
            print('75%')
            change_dc(75)
        elif t >= conf['lv1']:
            print('50%')
            change_dc(50)
        elif t >= conf['lv0']:
            print('25%')
            change_dc(25)
        else:
            print('turn off')
            change_dc(0)
        time.sleep(10)


def main():
    try:
        target = sys.argv[1].strip()
        if target == 'start':
            turn_on()
        elif target == 'stop':
            turn_off()
        elif target == 'enable':
            enable_poe()
    except KeyboardInterrupt:
        GPIO.cleanup()
    except Exception as ex:
        print(ex)
        print('using python3 rockpi-poe.py start|stop|enable')


if __name__ == '__main__':
    main()
