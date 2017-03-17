#!/usr/bin/python3

# Student name and No.:     WANG Haicheng 3035140108
# Student name and No.:     N/A
# Development platform:     Ubuntu 1604
# Python version: 			Python 3.5.2
# Version: 					0.1


from tkinter import *
import sys
import socket
import re
from threading import Thread, Lock
from time import sleep
from functools import reduce
from select import select



#
# Global constant
#
BUFSIZ = 1024
PROTOCAL_END = '::\r\n'
PROTOCAL_TIME = 20
#
# Global variables
#
States = {'STARTED'    : 0,
		  'NAMED'      : 1,
		  'JOINED'	   : 2,
		  'CONNECTED'  : 3,
		  'TERMINATED' : 4 }

Actions = {'USER' 	   : 5,
		   'LIST' 	   : 6,
		   'JOIN' 	   : 7,
		   'SEND' 	   : 8,
		   'QUIT' 	   : 9,
		   'HANDSHAKE' : 10} 

Exceptions = {'INVALID_USERNAME'           : 11,
			  'SOCKET_ERROR'               : 12,
			  'BACKWARDLINK_NOT_EXIST'     : 13,
			  'BACKWARDLINK_ALREADY_EXIST' : 14,
			  'TIMEOUT'                    : 15}

# two core global variables
currentState = None
user = None
# two lock for maintaining user info and current state info
stateLock = Lock()
userInfoLock = Lock()

# user class
# maintaining user program basic info
# include:
# 1. roomserver ipv4 address and port
# 2. p2pclient listening port
# 3. user socket connecting to roomserver and
#    and socket as local server socket
# 4. username validation rules
class User():
	def __init__(self , serverIP, serverPort, 
					localIP , localPort):
		self._setip(localIP)
		self._setportnumber(localPort)
		self._username = None
		self._clientSocket = None
		self._serverSocket = None
		## here we define the username validation rule
		self.validation = re.compile("^[\x00-\x7F]+$")
		self._socketSetup(serverIP, serverPort)
	def _socketSetup(self, serverIP=None, serverPort=None, localIP=None, localPort=None):
		print("setting up user socket...")
		if (serverIP is not None and serverPort is not None):
			self._clientSocket = socket.socket()
			# connect with room server with clientSocket
			try:
				self._clientSocket.connect((serverIP, serverPort))
				print('finish setting user socket: connected to roomserver[',
					serverIP,',',serverPort,']')	
			except socket.error as errmsg:
				print('Failed to connect to roomServer: ', errmsg)
				print('try again')

				try:
					self._clientSocket.connect((serverIP, serverPort))
					print('finish setting user socket: connected to roomserver[',
						serverIP,',',serverPort,']')
				except:
					print('Failed to connect to roomServer again: ', errmsg)
					print("""p2pclient program shutdowns due to failure to connect to roomserver,
							please check if the server address and port are correct, or check if 
							the server is already working""")
					self._clientSocket.close()
					sys.exit(1)
			
		if (localPort is not None):
			self._serverSocket = socket.socket()
			try:
				self._serverSocket.bind((localIP,localPort))
				self._serverSocket.listen(10)
				print('finish setting user socket: open server port:', localPort)
			except socket.error as emsg:
				print("Socket bind error: ", emsg)
				print("try again")
				try:
					self._serverSocket.bind((localIP,localPort))
					self._serverSocket.listen(10)
					print('finish setting user socket: open server port:', localPort)
				except socket.error as emsg:
					print("Socket bind error again: ", emsg)
					print("""p2pclient program shutdowns due to failure to bind the listening socket
							, please check your socket usage and try another available port""")
					self._serverSocket.close()
					sys.exit(1)
		else:
			print('Ignore binding port for the time being')
	def _setname(self, name):
		self._username = name
	def _setip(self, ip):
		self._IP = ip
	def _setportnumber(self, port):
		self._port = port
	def _getname(self):
		return self._username
	def _getip(self):
		return self._IP
	def _getport(self):
		return self._port
	def _getClientSocket(self):
		return self._clientSocket
	def _getServerSocket(self):
		return self._serverSocket
	def hasUserName(self):
		return self._getname() is not None
	def setUserName(self, username):
		# check first
		if (self.validation.match(username) is None) or (':' in username):
			return Exceptions['INVALID_USERNAME']
		self._setname(username)
	def bindServerSocket(self):
		self._socketSetup(serverIP = None, serverPort = None,
							localIP = self._getip(), localPort = self._getport())


# state class
# containing current state info
# include:
# 1. current room name (default None)
# 2. current room info (a list [MSID, userAName, userAIp, userAPort,
# 								userBName, userBIp, userBPort,...])
# 3. forward Links(for stage 2)
# 4. backward Links List (for stage 2)
# 5. msgID (TODO: for stage 2)
class State():
	def __init__(self):
		self._setstate(States['STARTED'])
		self._setroomname(None)
		self._setroominfo(None)
		self._setmsgid(0)
		self._linksetup()
	def _setstate(self,state):
		self._state = state
	def _getstate(self):
		return self._state
	def _setroomname(self,name):
		self._roomname = name
	def _getroomname(self):
		return self._roomname
	def _setroominfo(self,info):
		print('setting room info')
		print('info is ', info)
		self._roominfo = info
		print('after setting, roominfo is', self._roominfo)
	def _getroominfo(self):
		return self._roominfo
	def _setforwardlink(self, forwardLink):
		if forwardLink is None:
			self._forwardlink = forwardLink
		else:
			print("Error: cannot set forward link second time")
	def _linksetup(self):
		self._backwardlinks = []
		self._setforwardlink(None)
	def _setmsgid(self, msgID):
		self._msgid = msgID
	def _getmsgid(self):
		return self._msgid
	def _getforwardlink(self):
		return self._forwardlink
	def _addbackwardlinks(self, hash):
		if hash in self._backwardlinks:
			return Exceptions['BACKWARDLINK_ALREADY_EXIST']
		else:
			self._backwardlinks.append(hash)
			print('add new backward link with hash', hash)
	def _removebackwardlinks(self, hash):
		if hash not in self._backwardlinks:
			return Exceptions['BACKWARDLINK_NOT_EXIST']
		else:
			self._backwardlinks.remove(hash)
			print('remove backward link with hash', hash)
	def _getbackwardlinks(self):
		return self._backwardlinks
	def stateTransition(self, action):
		self._setstate(transition(self._getstate(),action))
	def updateRoomName(self, roomName):
		self._setroomname(roomName)
	def updateRoomInfo(self, roomInfo):
		if self._getroominfo() is None:
			self._setroominfo(roomInfo)
		elif self._getroominfo()[0] != roomInfo[0]:
			self._setroominfo(roomInfo)
		else:
			print('room member list: duplicated info, do not update')
	def isAfter(self, state):
		return self._getstate() > state
	def inRoom(self):
		return self._getroomname() is not None
	def updateMsgID(self, msgID):
		if self._getmsgid() < msgID:
			self._setmsgid(msgID)

#
# This is the hash function for generating a unique
# Hash ID for each peer.
# Source: http://www.cse.yorku.ca/~oz/hash.html
#
# Concatenate the peer's username, str(IP address), 
# and str(Port) to form the input to this hash function
#
def sdbm_hash(instr):
	hash = 0
	for c in instr:
		hash = int(ord(c)) + (hash << 6) + (hash << 16) - hash
	return hash & 0xffffffffffffffff

def getHashList(roomInfo):
	return 	list(map(lambda x: sdbm_hash(x), 
				map(lambda x: reduce(lambda m, n: m+n, x),
					[roomInfo[y:y+3] for y in range(1,len(roomInfo),3)])))
# five facilited state transition functions:
def FromStarted(action):
	return {Actions['LIST']: States['STARTED'], 
			Actions['USER']: States['NAMED'],
			Actions['QUIT']: States['TERMINATED']}[action]

def FromNamed(action):
	return {Actions['LIST']: States['NAMED'],
			Actions['USER']: States['NAMED'],
			Actions['JOIN']: States['JOINED'],
			Actions['QUIT']: States['TERMINATED']}[action]

def FromJoined(action):
	return {Actions['LIST']: States['JOINED'],
			Actions['SEND']: States['JOINED'],
			Actions['HANDSHAKE']: States['CONNECTED'],
			Actions['QUIT']: States['TERMINATED']}[action]

def FromConnected(action):
	return {Actions['LIST']: States['CONNECTED'],
			Actions['SEND']: States['CONNECTED'],
			Actions['HANDSHAKE']: States['CONNECTED'],
			Actions['QUIT']: States['TERMINATED']}[action]

# state transition function, critical, calling should be protected by logic
def transition(currentState, action):
	return {States['STARTED']: lambda x: FromStarted(x),
	 		States['NAMED']: lambda x: FromNamed(x),
	 		States['JOINED']: lambda x: FromJoined(x),
	 		States['CONNECTED']: lambda x: FromConnected(x)}[currentState](action)


# facilitation function for handshake process in stage 2
def findPosition(roomInfo, name, ip, port):
	for i in range(1,len(roomInfo),3):
		print(roomInfo[i], roomInfo[i+1], roomInfo[i+2])
		if name == roomInfo[i] and ip == roomInfo[i+1] and port == int(roomInfo[i+2]):
			return int((i-1)/3)
	return None
#
# functions for socket sending and receiving with block
# similar to C and C++ marco just for reducing duplication
#
def socketOperation(socket, sendMessage, receive = True):
	try:
		socket.send(sendMessage.encode('ascii'))
	except socket.error as errmsg:
		print('socket sending error: ', errmsg)
		return Exceptions['SOCKET_ERROR']
	if receive:
		try:
			responseData = socket.recv(BUFSIZ)
		except socket.error as errmsg:
			print('socket receving error: ', errmsg)
			return Exceptions['SOCKET_ERROR']
		return responseData.decode('ascii')

#
# functions for blocking socket to send and recv message
# with timeout option, return Exception['TIMEOUT'] if timeout
# para: timeout - seconds 
#
def socketOperationTimeout(socket, sendMessage, timeout):
	readList = [socket]
	try:
		socket.send(sendMessage.encode('ascii'))
	except socket.error as errmsg:
		print('socket sending error: ', errmsg)
		return Exceptions['SOCKET_ERROR']
	available = select(readList, [], [], timeout)
	if available:
		sockfd = readList[0]
		try:
			responseData = sockfd.recv(BUFSIZ)
			return responseData.decode('ascii')
		except socket.error as errmsg:
			print('socket receving error: ', errmsg)
			return Exceptions['SOCKET_ERROR']
	else:
		return Exceptions['TIMEOUT']
#
# functions for facilitation threads of keep alive procedure
# resend 'JOIN' request ever 20 seconds after successfully joining
#
def keepAliveThread():
	global currentState, user
	print('keep alive thread start working ... ')
	while True:
		sleep(PROTOCAL_TIME)
		userInfoLock.acquire()
		clientSocket = user._getClientSocket()
		message = ':'.join([currentState._getroomname(), user._getname(), user._getip(), str(user._getport())])
		requestMessage = 'J:' + message + PROTOCAL_END
		responseMessage = socketOperation(clientSocket, requestMessage)
		if (responseMessage[0] != 'M'):
			CmdWin.insert(1.0, "\nFailed to join: roomserver error")
			userInfoLock.release()
			return
		userInfoLock.release()
		stateLock.acquire()
		currentState.updateRoomInfo(responseMessage.replace(PROTOCAL_END,'').split(':')[1:])
		stateLock.release()
		print('Thread: keep alive action finish')



#
# TODO: thread for handshake procedure
# follow the logic of spec
#
def handShakeThread():
	# get info of chatroom
	global currentState, user
	# find myself position in the roomInfo
	userInfoLock.acquire()
	myName = user._getname()
	myIp = user._getip()
	myPort = user._getport()
	userInfoLock.release()
	successFlag = 0
	startListen = 0
	while 1:
		# update roominfo again
		stateLock.acquire()
		roomName = currentState._getroomname()
		roomInfo = currentState._getroominfo()
		msgID = currentState._getmsgid()


		backwardLinkHashList = currentState._getbackwardlinks()


		stateLock.release()
		myPosition = findPosition(roomInfo, myName, myIp, myPort)
		# print("myposition," , myPosition)
		# calculate hash of each user in the chatroom
		hashList = getHashList(roomInfo)
		myHash = hashList[myPosition]
		indexHashList = zip(range(len(hashList)), hashList)
		gList = sorted(indexHashList, key=lambda x : x[1])
		print('gList',gList)
		start = (gList.index((myPosition, myHash)) + 1) % len(gList)
		print('start',start)
		# probe and connect
		handShakeSocket = socket.socket()
		while gList[start][0] != myPosition:
			print('HandShake: approach user',roomInfo[1+3*start:4+3*start])
			if gList[start][1] in backwardLinkHashList:
				print('HandShake: try with one connection but find it already in backward list, try another')
				start = (start + 1) % len(gList)
				continue
			else:
				# try to approach by connecting
				realIndex = gList[start][0]*3 + 1
				# print('realIndex',realIndex)
				# print('roomInfo', roomInfo)
				try:
					handShakeSocket.connect((roomInfo[realIndex+1], int(roomInfo[realIndex+2])))
				except socket.error as errmsg:
					print('HandShake: try to connect with[', roomInfo[realIndex+1],
						',',roomInfo[realIndex+2],
						']but failed, try another')
					start = (start + 1) % len(gList)
					handShakeSocket = socket.socket()
					continue
				
				#### run peer to peer handshake
				message = ":".join([roomName,myName,myIp,str(myPort),str(msgID)])
				requestMessage = 'P:' + message + PROTOCAL_END
				### issue: what if there is no response?
				responseMessage = socketOperationTimeout(handShakeSocket, requestMessage,1)
				if responseMessage is Exceptions['TIMEOUT']:
					print("HandShake: timeout, try another socket")
					handShakeSocket = socket.socket()
					start = (start + 1) % len(gList)
					continue
				if responseMessage is Exceptions['SOCKET_ERROR']:
					print('HandShake: try peer-to-peer handshake with [', roomInfo[realIndex+1],
						',',roomInfo[realIndex+2],
						'] but failed, try another')
					start = (start + 1) % len(gList)
					continue
				if responseMessage[0] == 'S':
					print('HandShake: successfully connect with a peer through peer-to-peer handshake with',
						roomInfo[realIndex])
					message = responseMessage.replace(PROTOCAL_END, '').split(':')[1:]
					stateLock.acquire()
					currentState.updateMsgID(int(message[0]))
					currentState._setforwardlink(handShakeSocket)
					stateLock.release()
					successFlag = 1
				break
				
					
		if not startListen:
			userInfoLock.acquire()
			user.bindServerSocket()
			userInfoLock.release()
			serverThread = Thread(target=serverSocketThread, name='server')
			serverThread.start()
			startListen = 1
		if successFlag == 1:
			stateLock.acquire()
			currentState.stateTransition(Actions['HANDSHAKE'])
			currentState._setforwardlink(handShakeSocket)
			stateLock.release()
			break
		else:
			print('HandShake: failed to find a forward link with one loop, do it again', PROTOCAL_TIME,'seconds later')
			print('startListen', startListen)
			sleep(PROTOCAL_TIME)

def serverSocketThread():
	global user, currentState
	print("Server Thread: start working ...")
	userInfoLock.acquire()
	serverSocket = user._getServerSocket()
	clientSocket = user._getClientSocket()
	userInfoLock.release()
	stateLock.acquire()
	forwardLinkSocket = currentState._getforwardlink()
	roomName = currentState._getroomname()
	roomInfo = currentState._getroominfo()
	stateLock.release()
	hashList = getHashList(roomInfo)
	readList = [serverSocket]
	if (forwardLinkSocket):
		readList.append(forwardLinkSocket)
	while 1:
		print('Server Thread: listening ...')
		try:
			readable, writeable, exceptions = select(readList,[],[],PROTOCAL_TIME)
		except socket.error as errmsg:
			print("Server thread: encounter error", errmsg)

		if readable:
			print('Server Thread: catch sth')
			print (readable)
			for sockfd in readable:
				# 
				readable.remove(sockfd)
				if sockfd is serverSocket:
					backwardLink, address = sockfd.accept()
					requestData = backwardLink.recv(BUFSIZ)
					requestMessage = requestData.decode('ascii')
					# validate message
					pattern = "^P:[^:]+:[^:]+:(\d+\.){3}\d+:\d+:\d+::\r\n$"
					if (re.match(pattern, requestMessage) is None):
						print('Server Thread: receive a invlid request', requestMessage)
						print('Server Thread: refuse that request by ignoring it')
						backwardLink.close()
						continue
					# check if there exist in the room info
					message = requestMessage.replace(PROTOCAL_END, '').split(':')[1:]
					roomNameGet = message[0]
					backwardLinkUserName = message[1]
					backwardLinkIp = message[2]
					backwardLinkPort = int(message[3])
					backwardLinkMsgID = int(message[4])
					stateLock.acquire()
					roomInfo = currentState._getroominfo()
					stateLock.release()
					if (findPosition(roomInfo, backwardLinkUserName, backwardLinkIp, backwardLinkPort) is None):
						print('Server Thread: finding that there is no info of newly backward link, update roominfo and check again')
						stateLock.acquire()
						message_ = ':'.join([currentState._getroomname(), user._getname(), user._getip(), str(user._getport())])
						requestMessage = 'J:' + message_ + PROTOCAL_END
						responseMessage = socketOperation(clientSocket, requestMessage)
						if (responseMessage[0] != 'M'):
							print("Server Thread: Failed to join: roomserver error, try again")
							responseMessage = socketOperation(clientSocket, requestMessage)
							if (responseMessage[0] != 'M'):
								print("Server Thread: Failed to join: roomserver error, discard current action")
								backwardLink.close()
								stateLock.release()
								continue
						currentState.updateRoomInfo(responseMessage.replace(PROTOCAL_END,'').split(':')[1:])
						roomInfo = currentState._getroominfo()
						stateLock.release()
						print('Server Thread: Joined finish and check the info again')
					if (findPosition(roomInfo, backwardLinkUserName, backwardLinkIp, backwardLinkPort) is None):
						print('Server Thread: No info for the newly coming backward link')
						print('Server Thread: refuse that request by ignoring it')
						backwardLink.close()
						continue
					else:
						print('Server Thread: match the info of newly coming backward link')
						print('Server Thread: establish connection ...')
						# establish connection with that socket
						stateLock.acquire()
						currentState._addbackwardlinks(backwardLink)
						msgID = currentState._getmsgid()
						responseMessage = "S:" + str(msgID) + "::\r\n"
						output = socketOperation(backwardLink, responseMessage, receive = False)
						if output == Exceptions["SOCKET_ERROR"]:
							print('Server Thread: Failed to send back data')
							handShakeSocket = socket.socket()
							continue
						# state transition if neccessary
						currentState.stateTransition(Actions['HANDSHAKE'])
						stateLock.release()
						# update readlist
						readList.append(backwardLink)
						print('Server Thread: successfully connected a new backward link')
				else:
					print('Server Thread: Get an text message')
					messageData = sockfd.recv(BUFSIZ)
					message = messageData.decode('ascii')
					messageHeader = message.replace(PROTOCAL_END, '').split(':')[0:6]
					# check if in the same room
					if messageHeader[0] != "T":
						print('Server Thread: Unknown message')
						continue
					if messageHeader[1] != roomName:
						print('Server Thread: Bad message from other chatroom')
						CmdWin.insert(1.0, "\nError: Received an message from other chatroom\n")
						continue
					if not messageHeader[2] in hashList:
						print('Server Thread: Get an message with unknow sender, check roomserver for update')
						stateLock.acquire()
						message_ = ':'.join([currentState._getroomname(), user._getname(), user._getip(), str(user._getport())])
						requestMessage = 'J:' + message_ + PROTOCAL_END
						responseMessage = socketOperation(clientSocket, requestMessage)
						if (responseMessage[0] != 'M'):
							print("Server Thread: Failed to join: roomserver error, try again")
							responseMessage = socketOperation(clientSocket, requestMessage)
							if (responseMessage[0] != 'M'):
								print("Server Thread: Failed to join: roomserver error, discard current action")
								stateLock.release()
								continue
						currentState.updateRoomInfo(responseMessage.replace(PROTOCAL_END,'').split(':')[1:])
						roomInfo = currentState._getroominfo()
						stateLock.release()
						print('Server Thread: Joined finish and check the info again')
						hashList = getHashList(roomInfo)
					if not messageHeader[2] in hashList:
						print('Server Thread: Receive an message from an unknown sender, discard it')
						continue
					stateLock.acquire()
					if int(messageHeader[4]) <= currentState._getmsgid():
						print('Server Thread: Receive a previous message, discard it')
						CmdWin.insert(1.0, '\nReceive a previous message!\n')
						stateLock.release()
						continue
					currentState.updateMsgID(int(messageHeader[4]))
					stateLock.release()
					senderName = roomInfo[hashList.index(messageHeader[2])*3+1]
					content = message.replace(':'.join(messageHeader), '').replace(PROTOCAL_END, '')
					if len(content) == int(messageHeader[5]):
						MsgWin.insert(1.0, '\n['+senderName+']: '+content)
					else:
						print("Display Error: the length content does not match the header")

		else:
			print ("Server Thread: idling")


#
# Functions to handle user input
#

def do_User():

	global currentState, user

	invalidMessage = ['invalid username',
					  'change username after join']
	outstr = "\n[User] username: " + userentry.get()
	CmdWin.insert(1.0, outstr)
	username = userentry.get()
	# check if is joined.
	stateLock.acquire()
	if currentState.isAfter(States['NAMED']):
		CmdWin.insert(1.0, '\nFailed: ' + invalidMessage[1] + '\n')
		print('\nFailed: ' + invalidMessage[1])
		stateLock.release()
		return
	stateLock.release()
	# change the username
	userInfoLock.acquire()
	flag = user.hasUserName()
	if (user.setUserName(username) is Exceptions['INVALID_USERNAME']):
		CmdWin.insert(1.0, '\nFailed: ' + invalidMessage[0] +'\n')
		print('\nFailed: ' + invalidMessage[0])
		userInfoLock.release()
		return
	userInfoLock.release()
	# set state to named
	stateLock.acquire()
	currentState.stateTransition(Actions['USER'])
	stateLock.release()
	# clear the entry if success
	userentry.delete(0, END)
	# give some output in CmdWin
	if flag:
		CmdWin.insert(1.0, '\nSuccess: change name to '+username+' \n')
		print('\nSuccess: change name to '+username+' \n')
	else:
		CmdWin.insert(1.0, '\nSuccess: set your nickname as '+username+' \n')
		print('\nSuccess: set your nickname as '+username+' \n')

# function for debuging in the command line
def do_User_Debug(username):

	global currentState, user

	invalidMessage = ['invalid username',
					  'change username after join']
	# outstr = "\n[User] username: "+userentry.get()
	# CmdWin.insert(1.0, outstr)
	# username = userentry.get()
	# check if is joined.
	stateLock.acquire()
	if currentState.isAfter(States['JOINED']):
		print('Failed: ' + invalidMessage[1])
		stateLock.release()
		return
	stateLock.release()
	# change the username
	userInfoLock.acquire()
	if (user.setUserName(username) is Exceptions['INVALID_USERNAME']):
		print('Failed: ' + invalidMessage[0])
		userInfoLock.release()
		return
	userInfoLock.release()
	# set state to named
	stateLock.acquire()
	currentState.stateTransition(Actions['USER'])
	stateLock.release()
	userentry.delete(0, END)


def do_List():

	global user, currentState

	CmdWin.insert(1.0, "\nPress List")
	userInfoLock.acquire()
	clientSocket = user._getClientSocket()
	requestMessage = 'L' + PROTOCAL_END
	print(requestMessage)
	responseMessage = socketOperation(clientSocket, requestMessage)
	userInfoLock.release()
	presentMessage = '\n'.join(responseMessage.replace(PROTOCAL_END,'').split(':')[1:])
	CmdWin.insert(1.0, "\nHere are the active chatrooms:\n"+presentMessage+'\n')
	print("\nHere are the active chatrooms:\n"+presentMessage)
	# no need actually but standard for state transition procedure
	stateLock.acquire()
	currentState.stateTransition(Actions['LIST'])
	stateLock.release()

# function for debuging in the command line
def do_List_Debug():

	global user, currentState

	CmdWin.insert(1.0, "\nPress List")
	userInfoLock.acquire()
	clientSocket = user._getClientSocket()
	requestMessage = 'L' + PROTOCAL_END
	responseMessage = socketOperation(clientSocket, requestMessage)
	userInfoLock.release()
	presentMessage = '\n'.join(responseMessage.replace(PROTOCAL_END,'').split(':')[1:])
	print("\nHere are the active chatrooms:\n"+presentMessage+'\n')

	# no need actually but stard
	stateLock.acquire()
	currentState.stateTransition(Actions['LIST'])
	stateLock.release()

def do_Join():
	global currentState, user

	CmdWin.insert(1.0, "\nPress JOIN")
	#check username
	userInfoLock.acquire()
	if not user.hasUserName():
		CmdWin.insert(1.0, "\nError: Please input username first!\n")
		print("\nError: Please input username first!\n")
		userInfoLock.release()
		return
	userInfoLock.release()
	# check if it is already in a chatroom
	stateLock.acquire()
	if currentState.inRoom():
		CmdWin.insert(1.0, "\nError: You are already in the chat room!\n")
		print("\nError: You are already in the chat room!\n")
		stateLock.release()
		return
	stateLock.release()
	# get and validate the name of chatroom
	roomName = userentry.get()
	if (re.match('^[\x00-\x7f]+$', roomName) is None) or (':' in roomName):
		CmdWin.insert(1.0, "\nFailed: invalid room name")
		print("\nFailed: invalid room name")
		return
	# send request to roomserver
	userInfoLock.acquire()
	clientSocket = user._getClientSocket()
	message = ':'.join([roomName, user._getname(), user._getip(), str(user._getport())])
	requestMessage = 'J:' + message + PROTOCAL_END
	responseMessage = socketOperation(clientSocket, requestMessage)
	userInfoLock.release()
	if (responseMessage[0] != 'M'):
		CmdWin.insert(1.0, "\nFailed to join: roomserver error")
		return
	presentMessage = '\n'.join(responseMessage.replace(PROTOCAL_END,'').split(':')[2::3])
	CmdWin.insert(1.0, '\nJoin Success!\nHere are members in the room:\n' + presentMessage+ '\n' )
	print('\nJoin Success!\nHere are members in the room:\n' + presentMessage)
	# change the state if success
	stateLock.acquire()
	currentState.updateRoomName(roomName)
	currentState.updateRoomInfo(responseMessage.replace(PROTOCAL_END,'').split(':')[1:])
	currentState.stateTransition(Actions['JOIN'])
	stateLock.release()
	# clear the entry if success
	userentry.delete(0, END)
	# open the keep alive thread
	keepAlive = Thread(target=keepAliveThread, name='keepAlive')
	keepAlive.start()
	# open the handshake thread
	handShake = Thread(target=handShakeThread, name='handShake')
	handShake.start()
# function for debuging in the command line
def do_Join_Debug(roomName):
	global currentState, user
	# send request to roomserver
	userInfoLock.acquire()
	clientSocket = user._getClientSocket()
	message = ':'.join([roomName, user._getname(), user._getip(), str(user._getport())])
	requestMessage = 'J:' + message + PROTOCAL_END
	responseMessage = socketOperation(clientSocket, requestMessage)
	userInfoLock.release()
	if (responseMessage[0] != 'M'):
		print("\nFailed to join: roomserver error")
		return
	presentMessage = '\n'.join(responseMessage.replace(PROTOCAL_END,'').split(':')[2::3])
	print("\nJoin Success!\nHere are members in the room:\n" + presentMessage + '\n')
	# change the state if success
	stateLock.acquire()
	currentState.stateTransition(Actions['JOIN'])	
	currentState.updateRoomName(roomName)
	currentState.updateRoomInfo(responseMessage.replace(PROTOCAL_END,'').split(':')[1:])
	stateLock.release()

	# clear the entry if success
	userentry.delete(0, END)
	# open the keep alive thread
	keepAlive = Thread(target=keepAliveThread, name='keepAlive')
	keepAlive.start()
	# open the handshake thread
	handShake = Thread(target=handShakeThread, name='handShake')
	handShake.start()

def do_Send():
	global currentState, user
	CmdWin.insert(1.0, "\nPress Send")
	inputData = userentry.get()
	if len(inputData.strip(' ')) == 0:
		CmdWin.insert(1.0, "\nSend Error: Invalid message!")
		return
	# check stage
	stateLock.acquire()
	checkFlag = currentState.isAfter(States['NAMED'])
	stateLock.release()
	if not checkFlag:
		CmdWin.insert(1.0, "\nSend Error: You are not in any chatroom, please join a chatroom first!")
		userentry.delete(0, END)
		return
	# check for all back and forward link
	stateLock.acquire()
	forwardLink = currentState._getforwardlink()
	backwardLinks = currentState._getbackwardlinks()
	stateLock.release()
	sendingList = []
	if not forwardLink is None:
		sendingList.append(forwardLink)
	if len(backwardLinks) > 0 :
		sendingList = sendingList + backwardLinks
	# get all infos desired by sending Textmessage
	stateLock.acquire()
	roomName = currentState._getroomname()
	msgID = currentState._getmsgid()
	stateLock.release()
	userInfoLock.acquire()
	userName = user._getname()
	userIp = user._getip()
	userPort = user._getport()
	userInfoLock.release()

	# construct the protocal message
	originHID = sdbm_hash(username+userIp+str(userPort))
	message = [roomName, str(originHID), userName, str(msgID), str(len(inputData)), inputData]
	requestMessage = 'T:' + ':'.join(message) + PROTOCAL_END
	for socket in sendingList:
		output = socketOperation(socket, requestMessage, receive = False)
		if output == Exceptions['SOCKET_ERROR']:
			print('Send Error: cannot sent the message to', socket.getsockname())
	MsgWin.insert(1.0, '\n['+userName+']: '+inputData)


def do_Quit():
	CmdWin.insert(1.0, "\nPress Quit")
	cleanUp()
	sys.exit(0)

# TODO clean up procedure to close all socket fds
def cleanUp():
	pass
#
# Set up of Basic UI
#
win = Tk()
win.title("MyP2PChat")

#Top Frame for Message display
topframe = Frame(win, relief=RAISED, borderwidth=1)
topframe.pack(fill=BOTH, expand=True)
topscroll = Scrollbar(topframe)
MsgWin = Text(topframe, height='15', padx=5, pady=5, fg="red", exportselection=0, insertofftime=0)
MsgWin.pack(side=LEFT, fill=BOTH, expand=True)
topscroll.pack(side=RIGHT, fill=Y, expand=True)
MsgWin.config(yscrollcommand=topscroll.set)
topscroll.config(command=MsgWin.yview)

#Top Middle Frame for buttons
topmidframe = Frame(win, relief=RAISED, borderwidth=1)
topmidframe.pack(fill=X, expand=True)
Butt01 = Button(topmidframe, width='8', relief=RAISED, text="User", command=do_User)
Butt01.pack(side=LEFT, padx=8, pady=8);
Butt02 = Button(topmidframe, width='8', relief=RAISED, text="List", command=do_List)
Butt02.pack(side=LEFT, padx=8, pady=8);
Butt03 = Button(topmidframe, width='8', relief=RAISED, text="Join", command=do_Join)
Butt03.pack(side=LEFT, padx=8, pady=8);
Butt04 = Button(topmidframe, width='8', relief=RAISED, text="Send", command=do_Send)
Butt04.pack(side=LEFT, padx=8, pady=8);
Butt05 = Button(topmidframe, width='8', relief=RAISED, text="Quit", command=do_Quit)
Butt05.pack(side=LEFT, padx=8, pady=8);

#Lower Middle Frame for User input
lowmidframe = Frame(win, relief=RAISED, borderwidth=1)
lowmidframe.pack(fill=X, expand=True)
userentry = Entry(lowmidframe, fg="blue")
userentry.pack(fill=X, padx=4, pady=4, expand=True)

#Bottom Frame for displaying action info
bottframe = Frame(win, relief=RAISED, borderwidth=1)
bottframe.pack(fill=BOTH, expand=True)
bottscroll = Scrollbar(bottframe)
CmdWin = Text(bottframe, height='15', padx=5, pady=5, exportselection=0, insertofftime=0)
CmdWin.pack(side=LEFT, fill=BOTH, expand=True)
bottscroll.pack(side=RIGHT, fill=Y, expand=True)
CmdWin.config(yscrollcommand=bottscroll.set)
bottscroll.config(command=CmdWin.yview)

def main():
	if len(sys.argv) != 4:
		print("P2PChat.py <server address> <server port no.> <my port no.>")
		sys.exit(2)
	global currentState, user
	currentState = State()
	user = User(sys.argv[1], int(sys.argv[2]), socket.gethostbyname(socket.gethostname()),int(sys.argv[3]))
	# win.mainloop()
	do_User_Debug('abc')
	do_List_Debug()
	do_Join_Debug('aaaaa')

if __name__ == "__main__":
	main()
