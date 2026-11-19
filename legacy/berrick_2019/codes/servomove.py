import time
import pigpio 
#import RPi.gpio as GPIO
#GPIO.setmode(GPIO.BCM)
#GPIO.setwarnings(False)

#eyey PIN 17 (up 2  mid 6  down 9)
#eyex PIN 19 (left 8,5 mid 6 right 5
#lft-rght PIN 27 (left 6 mid 9 right 12)--------------------1300 sx - 2400 dx  
#neck PIN 22 (down 2 mid 6 down 8)
#mouth PIN 26 (close 10 - open 6)

class servo:

	def __init__(self, pin):
			self.pin = pin
		#	self.framelength = framelength
			self.servo = pigpio.pi()
					
	def getPos(self):
		
		return self.servo.get_servo_pulsewidth(self.pin)
		#print("servo pulse width : " , self.servo.get_servo_pulsewidth(self.pin))
		
		
	def setup(self, init):
		self.servo.set_servo_pulsewidth(self.pin,init)

	def setServoAngleHeadX(self, futpos, pos ,step , error):
		
		
		if futpos < pos - error:
			while futpos < pos - error : 
				pos -= step
				#print("pos :" , pos,"futpos : ", futpos)		
				self.servo.set_servo_pulsewidth(self.pin, pos)
				time.sleep(0.015)
			return
		elif futpos > pos + error:	
			while futpos > pos + error:
				pos += step		
				#print("pos :" , pos, "futpos : ", futpos)			
				self.servo.set_servo_pulsewidth(self.pin,pos)
				time.sleep(0.015)
			return
		else:
			return
				
	def setServoAngleHeadY(self, futpos, pos ,step , error):
		if futpos < pos - error:
			while futpos < pos - error : 
				pos -= step
				#print("pos :" , pos,"futpos : ", futpos)		
				self.servo.set_servo_pulsewidth(self.pin, pos)
				if pos > futpos:
					return
				time.sleep(0.015)
			return
		elif futpos > pos + error:	
			while futpos > pos + error:
				pos += step		
				#print("pos :" , pos, "futpos : ", futpos)			
				self.servo.set_servo_pulsewidth(self.pin,pos)
				if pos < futpos:
					return
				time.sleep(0.015)
			return
		else:
			return
			
	def setServoAngleMouth(self,currpos,step): #1100 chiusa 2100 aperta
		if 1900 < currpos :
			while currpos > 1100:
				currpos -= step		
				self.servo.set_servo_pulsewidth(self.pin,currpos)
				time.sleep(0.01)
			return
		elif 1500 > currpos:
			while currpos < 2100:
				currpos += step
				self.servo.set_servo_pulsewidth(self.pin,currpos)
				time.sleep(0.01)
			return
			
		return

	def stop(self):
		self.servo.stop()
		

