import time
import cv2
import copy
import SocketServer
import threading
import pygame
from threading import Thread

import Constants as CONSTANTS
from Constants import LOGGER
import MotorModes as MOTOR_MODES

from Motor import Motor
from MotorHandler import MotorHandler
from Sensor import Sensor
from SensorHandler import SensorHandler
from RobotState import RobotState
from SerialHandler import SerialHandler
from NetworkHandler import NetworkHandler
from MessageQueue import MessageQueue
from JoystickReader import JoystickReader
from NetworkClient import NetworkClient
from NetworkMessage import NetworkMessage
from Servo import Servo
from TargetPipeline import TargetFinder
from AngleWithTarget import center
import BeepCodes as BEEPCODES

from time import gmtime, strftime
#from main import inboundMessageQueue

LOGGER.Low("Beginning Program Execution")
#*************************CAMERA STUFF*************************************
cameraOutput = ""
targetAngle = -1.0
side = ""
#**************************************************************************

#Threading stuff... i still don't know this
motorHandlerLock = threading.Lock()
#sensorHandlerLock = threading.Lock()
#cameraHandlerLock = threading.Lock()
#LOGGER.Low("Motor Handler Lock: " + str(motorHandlerLock))


def motorCommunicationThread():
    while True:
        motorHandlerLock.acquire()
        #get the messages of each motor status from the HERO and update our motor values
        inboundMotorMessage = motorSerialHandler.getMessage()
        motorHandler.updateMotors(inboundMotorMessage)

        #Get our motor state message and send that to the HERO
        outboundMotorMessage = motorHandler.getMotorStateMessage()
        motorSerialHandler.sendMessage(outboundMotorMessage)

        motorHandlerLock.release()

def sensorCommunicationThread():
    while True:
#        sensorHandlerLock.acquire()
        inboundSensorMessage = sensorSerialHandler.getMessage()
#        LOGGER.Debug(inboundSensorMessage)
        sensorHandler.updateSensors(inboundSensorMessage)
#        LOGGER.Debug(printSensorValues)
        outboundSensorMessage = sensorHandler.getServoStateMessage()
#        LOGGER.Debug(outboundSensorMessage)
        sensorSerialHandler.sendMessage(outboundSensorMessage)
#        sensorHandlerLock.release()

def ceaseAllMotorFunctions():
    #Stop all motors
    leftDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, 0.0)
    rightDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, 0.0)
    #collectorDepthMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, 0.0)
    #collectorScoopsMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, 0.0)
    #winchMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, 0.0)

#initialize handlers
LOGGER.Debug("Initializing handlers...")
motorHandler = MotorHandler()
sensorHandler = SensorHandler()


if CONSTANTS.USING_SENSOR_BOARD:
    LOGGER.Debug("Initializing sensor serial handler...")
    sensorSerialHandler = SerialHandler(CONSTANTS.SENSOR_BOARD_PORT)
    sensorSerialHandler.initSerial()

if CONSTANTS.USING_MOTOR_BOARD:
    LOGGER.Debug("Initializing motor serial handler...")
    motorSerialHandler = SerialHandler(CONSTANTS.MOTOR_BOARD_PORT)
    motorSerialHandler.initSerial()


#initialize network comms & server thread
if CONSTANTS.USING_NETWORK_COMM:
    networkClient = NetworkClient(CONSTANTS.CONTROL_STATION_IP, CONSTANTS.CONTROL_STATION_PORT)
    inboundMessageQueue = MessageQueue()
    networkClient.setInboundMessageQueue(inboundMessageQueue)
    outboundMessageQueue = MessageQueue()
    lastReceivedMessageNumber = -1
    currentReceivedMessageNumber = -1
    stateStartTime = -1

# setup some variables that will be used with each iteration of the loop
#currentMessage = NetworkMessage("")

# initialize motors
LOGGER.Debug("Initializing motor objects...")
leftDriveMotor       = Motor("LeftDriveMotor",       CONSTANTS.LEFT_DRIVE_DEVICE_ID,       MOTOR_MODES.K_PERCENT_VBUS)
rightDriveMotor      = Motor("RightDriveMotor",      CONSTANTS.RIGHT_DRIVE_DEVICE_ID,      MOTOR_MODES.K_PERCENT_VBUS)
#collectorScoopsMotor = Motor("CollectorScoopsMotor", CONSTANTS.COLLECTOR_SCOOPS_DEVICE_ID, MOTOR_MODES.K_PERCENT_VBUS)
#collectorDepthMotor  = Motor("CollectorDepthMotor",  CONSTANTS.COLLECTOR_DEPTH_DEVICE_ID,  MOTOR_MODES.K_PERCENT_VBUS)
#winchMotor           = Motor("WinchMotor",           CONSTANTS.WINCH_DEVICE_ID,            MOTOR_MODES.K_PERCENT_VBUS)

# initialize motor handler and add motors

LOGGER.Debug("Linking motors to motor handler...")
motorHandler.addMotor(leftDriveMotor)
motorHandler.addMotor(rightDriveMotor)
#motorHandler.addMotor(collectorScoopsMotor)
#motorHandler.addMotor(collectorDepthMotor)
#motorHandler.addMotor(winchMotor)

# initialize encoder reset flags
driveEncoderResetFlag = False
scoopEncoderResetFlag = False
depthEncoderResetFlag = False
winchEncoderResetFlag = False

# initialize sensors
LOGGER.Debug("Initializing sensor objects...")
IMU = Sensor("IMU")

#rightDriveCurrentSense = Sensor("RightDriveCurrentSense")
#collectorDepthCurrentSense = Sensor("CollectorDepthCurrentSense")
#collectorScoopsCurrentSense = Sensor("CollectorScoopsCurrentSense")
#winchMotorCurrentSense = Sensor("WinchMotorCurrentSense")
#scoopReedSwitch = Sensor("ScoopReedSwitch")
#bucketMaterialDepthSense = Sensor("BucketMaterialDepthSense")

#initialize servos
#ratchetServo = Servo()
camServo = Servo()
#camServo2 = Servo()
#camServo3 = Servo()
#camServo4 = Servo()

# initialize sensor handler and add sensors
LOGGER.Debug("Linking sensor objects to sensor handler...")
sensorHandler.addSensor(IMU)
#sensorHandler.addSensor(rightDriveCurrentSense)
#sensorHandler.addSensor(collectorDepthCurrentSense)
#sensorHandler.addSensor(collectorScoopsCurrentSense)
#sensorHandler.addSensor(winchMotorCurrentSense)
#sensorHandler.addSensor(scoopReedSwitch)
#sensorHandler.addSensor(bucketMaterialDepthSense)

#sensorHandler.addServo(ratchetServo)
sensorHandler.addServo(camServo)
#sensorHandler.addServo(camServo2)
#sensorHandler.addServo(camServo3)
#sensorHandler.addServo(camServo4)

# initialize robotState
LOGGER.Debug("Initializing robot state...")
robotState = RobotState()

def cameraCommunicationThread():
    global frame
    global cameraOutput
    LOGGER.Debug("Starting Cameraaaaaaaaaaaa")
    pipeline = TargetFinder()
    while cap.isOpened():
        cameraHandlerLock.acquire()
        have_frame, frame = cap.read()
        ret, jpeg = cv2.imencode(".jpg",frame)
        cameraOutput = jpeg.tobytes()
        #LOGGER.Debug(str(len(frame)))
        cameraHandlerLock.release()

#initialize some opencv stuff
if CONSTANTS.USING_CAMERA:
    LOGGER.Debug("Initializing Camera")
    cap = cv2.VideoCapture(0)
    pipeline = TargetFinder()
    #cap.release()
    #camThread = Thread(target=cameraCommunicationThread)
    #camThread.daemon = True
    #camThread.start()



# initialize joystick, if using joystick
if CONSTANTS.USING_JOYSTICK:
    LOGGER.Debug("Initializing joystick...")
    pygame.init()
    pygame.joystick.init()
    joystick1 = pygame.joystick.Joystick(0)
    joystick1.init()
    jReader = JoystickReader(joystick1)

ceaseAllMotorFunctions()

if CONSTANTS.USING_MOTOR_BOARD:
    LOGGER.Debug("Initializing motor board thread...")
    #Sets up an isr essentially using the motorCommunicationThread()
    motorCommThread = Thread(target=motorCommunicationThread)
    motorCommThread.daemon = True
    motorCommThread.start()

if CONSTANTS.USING_SENSOR_BOARD:
    LOGGER.Debug("Initializing sensor board thread...")
    #sets up an isr essentially using the sensorCommunicationThread
    sensorCommThread = Thread(target=sensorCommunicationThread)
    sensorCommThread.daemon = True
    sensorCommThread.start()


# final line before entering main loop
robotEnabled = True


BEEPCODES.happy1()
LOGGER.Debug("Initialization complete, entering main loop...")
camServo.setSetpoint(0)
test_speed_val = -1.0
foundTarget = False




while robotEnabled:
   # camServo.setSetpoint(10)
    loopStartTime = time.time()
    #print strftime("%H:%M:%S.", gmtime()) + str(int((time.time()*1000) % 1000)) + ": ",

    currentState = robotState.getState()
    lastState = robotState.getLastState()

    # winchMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, 50)

    # +----------------------------------------------+
    # |                Communication                 |
    # +----------------------------------------------+

    if CONSTANTS.USING_NETWORK_COMM:
        connected = False
        while(not connected):
            try:
                if(outboundMessageQueue.isEmpty()):
                    #LOGGER.Low("Sent to control station "+ str(motorHandler.getMotorNetworkMessage())+"$"+str(sensorHandler.getSensorNetworkMessage()))
                    networkClient.send(motorHandler.getMotorNetworkMessage()+"$"+sensorHandler.getSensorNetworkMessage()+"<camServo:"+str(targetAngle)+">\n\r")
                else:
                    networkClient.send(outboundMessageQueue.getNext())
                connected = True
            except:
                LOGGER.Critical("Could not connect to network, attempting to reconnect...")
                ceaseAllMotorFunctions()


    # +----------------------------------------------+
    # |              Current State Logic             |
    # +----------------------------------------------+
    # State machine handles the robot's current states
    if CONSTANTS.USING_NETWORK_COMM and connected:

        if(not inboundMessageQueue.isEmpty()):
            currentMessage = inboundMessageQueue.getNext()
            #currentMessage.printMessage()
            lastReceivedMessageNumber = currentReceivedMessageNumber
            currentReceivedMessageNumber = currentMessage.messageNumber

        #new message has arrived, process
        if(lastReceivedMessageNumber != currentReceivedMessageNumber):

            stateStartTime = time.time()
            robotState.setState(currentMessage.type)
#            print currentMessage.type

            if(currentMessage.type == "MSG_STOP"):
                LOGGER.Debug("Received a MSG_STOP")

            elif(currentMessage.type == "MSG_DRIVE_TIME"):
                LOGGER.Debug("Received a MSG_DRIVE_TIME")

            elif(currentMessage.type == "MSG_ROTATE_TIME"):
                LOGGER.Debug("Received a MSG_ROTATE_TIME")
                currAngle = 0

            elif(currentMessage.type == "MSG_SCOOP_TIME"):
                LOGGER.Debug("Received a MSG_SCOOP_TIME")

            elif(currentMessage.type == "MSG_DEPTH_TIME"):
                LOGGER.Debug("Received a MSG_DEPTH_TIME")

            elif(currentMessage.type == "MSG_BUCKET_TIME"):
                LOGGER.Debug("Received a MSG_BUCKET_TIME")
                currAngle = 0
                turned = False

            elif(currentMessage.type == "MSG_DRIVE_DISTANCE"):
                LOGGER.Low("Received a MSG_DRIVE_DISTANCE")
                leftDriveMotor.setMode(MOTOR_MODES.K_POSITION)
                rightDriveMotor.setMode(MOTOR_MODES.K_POSITION)
                #before we start executing anything in the message for DriveDistance below
                #the encoder reset must be sent to the motor board.
                driveEncoderResetFlag = True
                LOGGER.Low("About to acquire motor handler lock")
                motorHandlerLock.acquire()
                LOGGER.Low("About to send message to Reset Encoders")
                motorSerialHandler.sendMessage("<ResetDriveEncoders>\n")
                LOGGER.Low("SENT MESSAGE TO RESET")
                motorHandlerLock.release()

            elif(currentMessage.type == "MSG_BUCKET_POSITION"):
                #winchMotor.setMode(MOTOR_MODES.K_POSITION)
                #winchEncoderResetFlag = True
                #LOGGER.Low("Acquiring Lock")
                #motorHandlerLock.acquire()
                #motorSerialHandler.sendMessage("<ResetWinchEncoder>\n")
                #motorHandlerLock.release()
                LOGGER.Low("Releasing Lock")

            elif(currentMessage.type == "MSG_MOTOR_VALUES"):
                LOGGER.Debug("Received a MSG_MOTOR_VALUES")
                print "MADE IT 1"

            elif(currentMessage.type == "MSG_RATCHET_POSITION"):
                LOGGER.Debug("Received a MSG_RATCHET_POSITION")
                currAngle = 0
                turned = False

            else:
                LOGGER.Moderate("Received an invalid message.")

        #
        # MSG_STOP:
        # Stop all motors immediately
        #
        if(currentMessage.type == "MSG_STOP"):
            ceaseAllMotorFunctions()
            outboundMessageQueue.add("Finished\n")

        #
        # MSG_DRIVE_TIME:
        # Drive forward/backward with both motors at the same value
        # Data 0: The time in seconds the robot should drive
        # Data 1: The power/speed to drive at
        #
        elif(currentMessage.type == "MSG_DRIVE_TIME"):
            currentMessage.printMessage()
            if(time.time() < stateStartTime + currentMessage.messageData[0]):
                driveSpeed = currentMessage.messageData[1]
                leftDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, driveSpeed)
                rightDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, -driveSpeed)
            else:
                ceaseAllMotorFunctions()
                outboundMessageQueue.add("Finished\n")

        #
        # MSG_ROTATE_TIME:
        # Drive forward/backward with both motors at the same value
        # Data 0: The time in seconds the robot should drive
        # Data 1: The power/speed to drive at
        #
        elif(currentMessage.type == "MSG_ROTATE_TIME"):
 #           currentMessage.printMessage()
            desAngle = currentMessage.messageData[0]
            LOGGER.Debug(str(desAngle))
            if(currAngle<desAngle):
                currAngle += IMU.getValue()*(time.time()-stateStartTime)
                stateStartTime = time.time()
                LOGGER.Debug("Current Angle "+str(currAngle))
                #otateSpeed  = currentMessage.messageData[1]
                leftDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, .4)
                rightDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, .4)

           # if(time.time() < stateStartTime + currentMessage.messageData[0]):
            #    rotateSpeed  = currentMessage.messageData[1]
             #   leftDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, rotateSpeed)
              #  rightDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, rotateSpeed)
            else:
                ceaseAllMotorFunctions()
                outboundMessageQueue.add("Finished\n")


        #
        # MSG_SCOOP_TIME:
        # Drive the scoops for a set time at a specified speed
        # Data 0: The time in seconds the scoop motor should run
        # Data 1: The power/speed to run the motor at
        #
        elif(currentMessage.type == "MSG_SCOOP_TIME"):
            currentMessage.printMessage()
            if(time.time() < stateStartTime + currentMessage.messageData[0]):
                scoopSpeed = currentMessage.messageData[1]
                collectorScoopsMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, scoopSpeed)
            else:
                ceaseAllMotorFunctions()
                outboundMessageQueue.add("Finished\n")
        #
        # MSG_DEPTH_TIME:
        # Drive the depth motor for a set time at a specified power/speed
        # Data 0: The time in seconds the depth motor should run
        # Data 1: The power/speed to run the motor at
        #
        elif(currentMessage.type == "MSG_DEPTH_TIME"):
            currentMessage.printMessage()
            if(time.time() < stateStartTime + currentMessage.messageData[0]):
                depthSpeed = currentMessage.messageData[1]
                collectorDepthMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, depthSpeed)
            else:
                ceaseAllMotorFunctions()
                outboundMessageQueue.add("Finished\n")
        #
        # MSG_BUCKET_TIME:
        # Drive the bucket for a set time at a specified speed
        # Data 0: The time in seconds the bucket motor should run
        # Data 1: The power/speed to run the motor at
        #
        elif(currentMessage.type == "MSG_BUCKET_TIME"):
            #currentMessage.printMessage()
            if not turned:
                if side == "Left":
                    #LL
                    if targetAngle > 105 and targetAngle <= 130:
                #Do the turn (Left 130 deg)
                        if(currAngle<130):
                            currAngle += abs(IMU.getValue()*(time.time()-stateStartTime))
                            stateStartTime = time.time()
                            LOGGER.Debug("Current Angle "+str(currAngle))
                            leftDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, 0.4)
                            rightDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, 0.4)
                        else:
                            turned = True
                    #LU
                    elif targetAngle > 80 and targetAngle <= 105:
                #Do the turn (Right 140 deg)
                        if(currAngle<140):
                            currAngle += abs(IMU.getValue()*(time.time()-stateStartTime))
                            stateStartTime = time.time()
                            LOGGER.Debug("Current Angle "+str(currAngle))
                            leftDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, -0.4)
                            rightDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, -0.4)
                        else:
                            turned = True
                    #LR
                    elif targetAngle > 45 and targetAngle <= 80:
                #Do the turn (Right 50)
                        if(currAngle<50):
                            currAngle += abs(IMU.getValue()*(time.time()-stateStartTime))
                            stateStartTime = time.time()
                            LOGGER.Debug("Current Angle "+str(currAngle))
                            leftDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, -0.4)
                            rightDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, -0.4)
                        else:
                            turned = True
                    #LD
                    else:
                #Do the turn (Left 40)
                        if(currAngle<40):
                            currAngle += abs(IMU.getValue()*(time.time()-stateStartTime))
                            stateStartTime = time.time()
                            LOGGER.Debug("Current Angle "+str(currAngle))
                            leftDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, 0.4)
                            rightDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, 0.4)
                        else:
                            turned = True
                elif side == "Right":
                    #RR
                    if targetAngle > 5 and targetAngle <= 35:
                #Do the turn (Right 130 deg)
                        if(currAngle<130):
                            currAngle += abs(IMU.getValue()*(time.time()-stateStartTime))
                            stateStartTime = time.time()
                            LOGGER.Debug("Current Angle "+str(currAngle))
                            leftDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, -0.4)
                            rightDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, -0.4)
                        else:
                            turned = True
                    #RU
                    elif targetAngle >35  and targetAngle <= 70:
                #Do the turn (Left 140 deg)
                        if(currAngle<140):
                            currAngle += abs(IMU.getValue()*(time.time()-stateStartTime))
                            stateStartTime = time.time()
                            LOGGER.Debug("Current Angle "+str(currAngle))
                            leftDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, 0.4)
                            rightDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, 0.4)
                        else:
                            turned = True
                    #RL
                    elif targetAngle > 70 and targetAngle <=95:
                #Do the turn (Left 50)
                        if(currAngle<50):
                            currAngle += abs(IMU.getValue()*(time.time()-stateStartTime))
                            stateStartTime = time.time()
                            LOGGER.Debug("Current Angle "+str(currAngle))
                            leftDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, 0.4)
                            rightDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, 0.4)
                        else:
                            turned = True
                    #RD
                    else:
                #Do the turn (Right 40)
                        if(currAngle<40):
                            currAngle += abs(IMU.getValue()*(time.time()-stateStartTime))
                            stateStartTime = time.time()
                            LOGGER.Debug("Current Angle "+str(currAngle))
                            leftDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, -0.4)
                            rightDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, -0.4)
                        else:
                            turned = True
            else:
                ceaseAllMotorFunctions()
                outboundMessageQueue.add("Finished\n")

        elif(currentMessage.type == "MSG_DRIVE_DISTANCE"):
            currentMessage.printMessage()
            positionVal = -currentMessage.messageData[0]

            LOGGER.Low("Check setpoint: " + str(positionVal))
            LOGGER.Low("Check left enc: " + str(leftDriveMotor.position))
            LOGGER.Low("Check right enc: " + str(rightDriveMotor.position))

            if(driveEncoderResetFlag):
                ceaseAllMotorFunctions()
                if((abs(leftDriveMotor.position) < 1) and (abs(rightDriveMotor.position) < 1)):
                    LOGGER.Low("Encoders reset.")
                    driveEncoderResetFlag = False
                    leftDriveMotor.setSetpoint(MOTOR_MODES.K_POSITION, positionVal)
                    rightDriveMotor.setSetpoint(MOTOR_MODES.K_POSITION, -positionVal)

            elif( (abs(leftDriveMotor.position) < abs(0.95 * positionVal)) or
                  (abs(rightDriveMotor.position) < abs(0.95 * positionVal))):
                pass

            else:
                ceaseAllMotorFunctions()
                outboundMessageQueue.add("Finished\n")


        elif(currentMessage.type == "MSG_BUCKET_POSITION"):
            if camServo.getSetpoint()<180 and not foundTarget:
                camServo.setSetpoint(camServo.getSetpoint()+1)

                #*************************CAMERA STUFF HERE*************
                contours = -1
                if not cap.isOpened():
                    LOGGER.Low("Camera Not Opened")
                if cap.isOpened():
                    LOGGER.Low("Camera Opened")
                    _, frame = cap.read()
                    contours = pipeline.process(frame)
                    print "Num of Contours: ", len(contours)
                    if len(contours) == 2:
                        cv2.imwrite("Contours.jpg", frame)
                        targetAngle = float(camServo.getSetpoint())
                        side = center(contours)
                        foundTarget = True
                        LOGGER.Low("We are on the " + side + " side")
                        LOGGER.Low("Found target at " + str(targetAngle))
                        cap.release()
                elif contours == -1 and cap.isOpened():
                    LOGGER.Debug("COULD NOT FIND TARGET!!")

                #********************************************************
                time.sleep(.15)
            elif camServo.getSetpoint() >= 180 or foundTarget:
                if not foundTarget:
                    LOGGER.Debug("COULD NOT FIND TARGET")
                cap.release()
           # currentMessage.printMessage()
           # positionVal = currentMessage.messageData[0]
           # LOGGER.Low("Check Setpoint: " + str(positionVal))
           # LOGGER.Low("Check Encoder:  " + str(winchMotor.position))
           # LOGGER.Low("Check Velocity: " + str(winchMotor.speed))

            #if(winchEncoderResetFlag):
            #    ceaseAllMotorFunctions()
            ##    if(abs(winchMotor.position) < 1):
            #        LOGGER.Low("Winch Encoder Reset.")
            #        winchEncoderResetFlag = False
            #elif(not abs(winchMotor.position - positionVal) < 2):
            #    winchMotor.setSetpoint(MOTOR_MODES.K_POSITION, positionVal)

                ceaseAllMotorFunctions()
                outboundMessageQueue.add("Finished\n")

        elif(currentMessage.type == "MSG_MOTOR_VALUES"):
            leftDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, currentMessage.messageData[0])
            #rightDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS,currentMessage.messageData[1])
            #collectorScoopsMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS,currentMessage.messageData[2])
            #collectorDepthMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS,currentMessage.messageData[3])
            #winchMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS,currentMessage.messageData[4])

        elif(currentMessage.type == "MSG_RATCHET_POSITION"):
            if not turned:
                if side == "Left":
                    if(currAngle<30):
                        currAngle += abs(IMU.getValue()*(time.time()-stateStartTime))
                        stateStartTime = time.time()
                        LOGGER.Debug("Current Angle "+str(currAngle))
                        leftDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, -0.4)
                        rightDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, -0.4)
                    else:
                        turned = True
                if side == "Right":
                    if(currAngle<40):
                        currAngle += abs(IMU.getValue()*(time.time()-stateStartTime))
                        stateStartTime = time.time()
                        LOGGER.Debug("Current Angle "+str(currAngle))
                        leftDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, 0.4)
                        rightDriveMotor.setSetpoint(MOTOR_MODES.K_PERCENT_VBUS, 0.4)
                    else:
                        turned = True
            else:
                ceaseAllMotorFunctions()
                outboundMessageQueue.add("Finished\n")


    if CONSTANTS.USING_JOYSTICK:
        y1,y2 = jReader.getAxisValues()
        # leftDriveMotor.setSpeed(y1)
        # rightDriveMotor.setSpeed(y2)
        # collectorDepthMotor.setSpeed(0)
        # collectorScoopsMotor.setSpeed(0)
        winchMotor.setSpeed(y1)


    #loopEndTime = time.time()
    #loopExecutionTime = loopEndTime - loopStartTime
    #sleepTime = CONSTANTS.LOOP_DELAY_TIME - loopExecutionTime
    #if(sleepTime > 0):
    #    time.sleep(sleepTime)