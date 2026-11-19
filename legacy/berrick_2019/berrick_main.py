# USAGE
# python berrick_main.py --cascade haarcascade_frontalface_default.xml
			#50hz settings
#eyey PIN 26 (up 2  mid 6  down 9)   #sarebbe 17, ma ho sbagliato e ho invertito sulla scheda
#eyex PIN 19 (left 8,5 mid 6 right 5
#lft-rght PIN 27 (left 6 mid 9 right 12)
#neck PIN 22 (down 2 mid 6 down 8)
#mouth PIN 17 (close 10 - open 6)

# import necessary packages
from multiprocessing import Manager
from multiprocessing import Process
from imutils.video import VideoStream
from codes.objcenter import ObjCenter
from codes.pid import PID
from codes.servomove import servo
from codes.test  import test

#import codes.keyboardtest
#from imutils.video import FPS   # per testare gli fps

from rpi_ws281x import *

# LED strip configuration:
LED_COUNT      = 14      # Number of LED pixels.
LED_PIN        = 10      # GPIO pin connected to the pixels (must support PWM!).
LED_FREQ_HZ    = 800000  # LED signal frequency in hertz (usually 800khz)
LED_DMA        = 10   # DMA channel to use for generating signal (try 10)
LED_BRIGHTNESS = 180     # Set to 0 for darkest and 255 for brightest
LED_INVERT     = False   # True to invert the signal (when using NPN transistor level shift)
LED_CHANNEL    = 0
LED_STRIP      = ws.SK6812_STRIP_RGBW

#pixels = neopixel.NeoPixel(Board.D21, 7)
import argparse
import signal
import time
import sys
import cv2
import getch



headx = servo(27)
heady = servo(22)
mouth = servo(17)
#fps = FPS().start()

#Funzione colore neopixel
def colorWipe(strip, color, wait_ms=2):
	"""Wipe color across display a pixel at a time."""
	for i in range(strip.numPixels()):
		strip.setPixelColor(i, color)
		strip.show()
		time.sleep(wait_ms/1000.0)



# function to handle keyboard interrupt


def signal_handler(sig, frame):
	# print a status message
	print("[INFO] You pressed `ctrl + c`! Exiting...")
	
	colorWipe(strip, Color(0, 0, 0))  # turn off eye led

	#fps.stop()
	#print("[INFO] elapsed time: {:.2f}".format(fps.elapsed()))
	#print("[INFO] approx. FPS: {:.2f}".format(fps.fps()))
	
	# disable the servos
	
	#eyey.stop()
	#eyex.stop()
	headx.stop()
	heady.stop()
	mouth.stop()
	
	
	# exit
	sys.exit()

def obj_center(args, objX, objY, centerX, centerY, flagtime , midtime , widthF , heightF):
	# signal trap to handle keyboard interrupt
	signal.signal(signal.SIGINT, signal_handler)

	# start the video stream and wait for the camera to warm up
	vs = VideoStream(usePiCamera=True).start()
	time.sleep(2.0)

	# initialize the object center finder
	obj = ObjCenter(args["cascade"] , flagtime.value ,midtime.value)

	# loop indefinitely
	while True:
		# grab the frame from the threaded video stream and flip it
		# vertically (since our camera was upside down)
		frame = vs.read()

		# calculate the center of the frame as this is where we will
		# try to keep the object
		
		#Centro x = 160 y= 120
		#frame  x= 320 y = 240
		(H, W) = frame.shape[:2]
		centerX.value = W // 2
		centerY.value = H // 2
		
		# find the object's location
		objectLoc = obj.update(frame, (centerX.value, centerY.value))
		((objX.value, objY.value), rect, confidence) = objectLoc

		# extract the bounding box and draw it
		if rect is not None:
			(x, y, w, h) = rect
			cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0),
				2)
			cv2.putText(frame, "%05.2f" % confidence, (x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)
			#print("rect x ",x)  coordinate della box nel frame
			#print("rect y ",y)  coordinate della box nel frame
		#	print("Larghezza frame : ", w)
			weightF = w
			heightF = h
		#fps.update()  #refresh numero fps
 
		# display the frame to the screen
		cv2.imshow("Berrick head", frame)
		cv2.waitKey(1)

def pid_process(output, p, i, d, objCoord, centerCoord):
	# signal trap to handle keyboard interrupt
	signal.signal(signal.SIGINT, signal_handler)

	# create a PID and initialize it
	p = PID(p.value, i.value, d.value)
	p.initialize()

	# loop indefinitely
	while True:
		# calculate the error
		error = centerCoord.value - objCoord.value
		#print(" Error : " , error)
		# update the value
		output.value = p.update(error)

#def in_range(val, start, end):
	# determine the input vale is in the supplied range
#	return (val >= start and val <= end)
def in_range(val, start, end):
	# determine the input vale is in the supplied range
	return (val >= start and val <= end)
	
	
def go(eyeX, eyeY, widthF, heightF, flagm):
	# signal trap to handle keyboard interrupt
	signal.signal(signal.SIGINT, signal_handler)
	prova = 1
	time.sleep(6)
#	print(" --------- : Movement start : ---------")
#	print(" Init pos : " , headx.getPos())
	
	while True:
		if prova == 0:
			#mouth.setServoAngleMouth(1100,50)
			colorWipe(strip, Color(0, 0, 0))  # 
			prova = 1
			#print("prova 1 :", prova)
			flagm.value = 0
			time.sleep(0.2)
		while eyeX.value > 1 or eyeY.value > 1 :
			posX = headx.getPos()
			#posY = heady.getPos()
			
			deltax = eyeX.value - 163 
			#deltay = eyeY.value - 269
			
			if prova == 1:
				#mouth.setServoAngleMouth(1950,50)
				colorWipe(strip, Color(255, 0, 0))  # Blue wipe
				prova = 0
				time.sleep(0.015)
			
			flagm.value = 1
			if deltax > widthF.value or deltax < - widthF.value:
				xMov = posX + deltax
				if in_range(xMov, 1200 , 2400):			
					headx.setServoAngleHeadX(xMov , posX, 3 , 50)
				
	#		if deltay > heightF.value or deltay < - heightF.value:
	#			yMov = posY + deltay
	#			if in_range(yMov ,800 , 2000):
	#				heady.setServoAngleHeadY(yMov, posY, -5 , 60)
		
	#		Stringa debug
	#		print("eyeX.value : " , eyeX.value , " deltax : " , deltax , " xMov : ", xMov  )#," eyeY.value :" , eyeY.value , " delta y : ", deltay , " yMov : ", yMov)

			time.sleep(0.05)


def testf(test1,mydata,starttime,flagm):
	time.sleep(4)
	
	if mydata == "0":
		print("Berrick start detection ")
		return
	elif mydata == "1":
		print("Keyboard test start:")
		test1.testKeyboard(flagm)

	



# check to see if this is the main body of execution
if __name__ == "__main__":
	# construct the argument parser and parse the arguments
	ap = argparse.ArgumentParser()
	ap.add_argument("-c", "--cascade", type=str, required=True,
		help="path to input Haar cascade for face detection")
	args = vars(ap.parse_args())
	
	strip = Adafruit_NeoPixel(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL, LED_STRIP)
	strip.begin()
	
	try:
		print("Which test you want to do? 1 : keyboard " )	
		mydata = input("Digit a number : ")
		print("mydata", mydata)
	except EOFError:
			pass

	
	
	#print("Versione opencv: ", cv2.__version__)

	# start a manager for managing process-safe variables
	with Manager() as manager:
		

		
		
		headx.setup(1850)
		#heady.setup(1350)
		mouth.setup(2100)
		#image flag
		flagm = manager.Value("i",0)
		starttime = manager.Value("f",0)
		test1 = test(starttime)

		# set integer values for the object center (x, y)-coordinates
		centerX = manager.Value("i", 0)
		centerY = manager.Value("i", 0)
		
		widthF = manager.Value("i",0)
		heightF = manager.Value("i",0)
		
		# set integer values for the object's (x, y)-coordinates
		objX = manager.Value("i", 0)
		objY = manager.Value("i", 0)

		# pan and tilt values will be managed by independed PIDs
		eyeX = manager.Value("i", 0)
		eyeY = manager.Value("i", 0)

		# set PID values for panning
		eyeXP = manager.Value("f", 2.9)
		eyeXI = manager.Value("f", 0.0)
		eyeXD = manager.Value("f", 0.0)

		# set PID values for tilting
		eyeYP = manager.Value("f", 5.63)
		eyeYI = manager.Value("f", 0.0)
		eyeYD = manager.Value("f", 0.0)
		
		#Time variable
		flagtime = manager.Value("i",0)
		midtime = manager.Value("f",0.0)
		
		#test
		
		# we have 4 independent processes
		# 1. objectCenter  - finds/localizes the object
		# 2. xEye       - PID control loop determines panning angle
		# 3. yEye       - PID control loop determines tilting angle
		# 4. setServos     - drives the servos to proper angles based
		#                    on PID feedback to keep object in center
		processObjectCenter = Process(target=obj_center,
			args=(args, objX, objY, centerX, centerY, flagtime, midtime, widthF,heightF))
			
		processXeye = Process(target=pid_process, #asse x
			args=(eyeX, eyeXP, eyeXI, eyeXD, objX, centerX))
		
		#processYeye = Process(target=pid_process, #asse y
		#	args=(eyeY, eyeYP, eyeYI, eyeYD, objY, centerY))
			
		processSetServos = Process(target=go, args=(eyeX, eyeY , widthF , heightF, flagm))
		
		processTest = Process(target=testf, args=(test1,mydata,starttime,flagm))
		
		# start all 5 processes
		processObjectCenter.start()
		processXeye.start()
		#processYeye.start()
		processSetServos.start()
		processTest.start()
		
		# join all 5 processes
		processObjectCenter.join()
		processXeye.join()
		#processYeye.join()
		processSetServos.join()
		processTest.join()

		

