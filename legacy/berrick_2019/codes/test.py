import time
import imutils
import os
import getch
#import codes.keyboardtest
import sys
import curses

class test:
	
	def __init__(self,starttime):
		self.starttime = starttime
		self.endtime = 0
		
	def testKeyboard(self,flagm):
		
		logberrick = open("berricklogtest.txt","w")
		#logkeyboard = open("keyboardlogtest.txt","w")

		try:
				#exec('keyboardtest.py')
				#os.system('python keyboardtest.py')
				for count in range(5,0,-1):
					print(count ,"..")
					time.sleep(1)
				self.starttime = time.time()

				while self.endtime - self.starttime < 180.0:
					
					immFlag = flagm.value
					#print("immflag:",immFlag)
					if immFlag == 1 :
						logberrick.write("1 ")
						myinput = getch.getch()
						logberrick.write(myinput)
						print("Robot : 1  Human : " + myinput)
						logberrick.write("\n")
					else:
						logberrick.write("0 ")
						myinput = getch.getch()
						logberrick.write(myinput)
						print("Robot : 0 - Human : " + myinput)
						logberrick.write("\n")
				
					curses.initscr()
					curses.flushinp()
					curses.endwin()

					self.endtime = time.time()
					time.sleep(0.5)
				
				print("End test")
				self.starttime = 0
				logberrick.close()				
			
		except EOFError:
			pass
		
