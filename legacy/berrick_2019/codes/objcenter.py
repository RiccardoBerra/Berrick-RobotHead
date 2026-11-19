# import necessary packages
import imutils
import time
import cv2

class ObjCenter:
	def __init__(self, haarPath, flagtime , midtime):
		# load OpenCV's Haar cascade face detector
		self.detector = cv2.CascadeClassifier(haarPath)
		self.flag = flagtime
		self.midtime = midtime

	def update(self, frame, frameCenter):
		# convert the frame to grayscale
		gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

		# detect all faces in the input frame
		
		rects = self.detector.detectMultiScale3(gray, scaleFactor=1.05,
			minNeighbors=9, minSize=(30, 30),
			flags=cv2.CASCADE_SCALE_IMAGE,
			outputRejectLevels=True)
		report = open("report.txt","a")
		
		#print("Init flatime: " , self.flag)
		#print("Init midtime:" , self.midtime)
		
		# check to see if a face was found
		if len(rects[0]) > 0:
			
			if self.flag == 0:
				self.midtime = time.time()
				self.flag = 1
				#print("flagtime :" ,  self.flag)
			
			
			#Da sistemare
			weight = rects[2][0] #confidence level
			#report.write("Face detected. Confidence Level : ")
			report.write(str(weight))
			report.write("\n")
			#print(type(rects))

			# extract the bounding box coordinates of the face and
			# use the coordinates to determine the center of the
			# face
			#print(rects[0].shape)
			(x, y, w, h) = rects[0][0]
			faceX = int((x + w) / 2)
			faceY = int((y + h) / 2)
			#print(rects[2][0]) #confidenza val
			# return the center (x, y)-coordinates of the face
		

				
			return ((faceX, faceY), rects[0][0], rects[2][0])
			
				
		if self.flag == 1:
			end = time.time()
			timeelapsed = end - self.midtime
			self.midtime = 0.0
			# print("Tempo passato :" , timeelapsed)
			end = 0.0
			self.flag = 0
			# sistemare scrittura
			report.write("Time detection: ")
			report.write(str("%05.2f" % timeelapsed))
			report.write("\n")
			
			
			
		report.close()
		# otherwise no faces were found, so return the center of the
		# frame
		return (frameCenter, None, None )
